# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowering for an assumption-table lookup.

``af.mort_rate = mortality.lookup(age=af.attained_age)`` builds
``Call("lookup", ...)``: the key expressions as node arguments in the
table's own key-column order, and the table's identity and miss policy as
typed attributes. The call into the Rust ``lookup_by_table_and_hash``
kernel lives here.

**What the identity attributes are, precisely.** ``table`` is the name the
lookup resolves by at execution time -- the same string the kernel is
handed. ``table_fingerprint`` is the content hash of the *processed*
frame, computed once when the ``Table`` was built (it is what the
supersede check already compares, so reading it at emission costs
nothing). It is deliberately **not** ``Table.source_sha()``: that covers
the name, the dimension set, and the value column as well. Two tables with the same
processed content and different names therefore share a fingerprint and
are told apart by ``table``; the pair is the identity.

Lowering checks both attributes before building the lazy expression. The
kernel checks the content and ordered key/value roles against the same
immutable registry snapshot it reads, so replacement after lowering refuses
at collection instead of silently changing the assumptions.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio._semantic.ir import Col, Lit
from gaspatchio.assumptions._data import _declared_text_columns
from gaspatchio.assumptions._dimensions import DataDimension
from gaspatchio.frame.lowering.artefacts import table_named, table_schema
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering
from gaspatchio.frame.lowering.rules import _SPEC_PATH, _counted, _listed

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.ir import AttrValue, Call, OpNode
    from gaspatchio.assumptions._data import TableData
    from gaspatchio.frame.lowering.context import LoweringContext

_REQUIRED_ATTRS: Final = ("table", "table_fingerprint", "on_missing", "fill_value")

_THE_FOUR: Final = "table, table_fingerprint, on_missing and fill_value"

_SIGNATURE: Final = (
    "The lookup row of the signature schedule in §11.1.11, and §11.1.24, "
    f"of {_SPEC_PATH} state what a lookup node carries."
)

# What each half of the identity pair is for, so a refusal about one of them
# says why it cannot be empty or of another type rather than restating the
# rule it broke. The pair itself is described at the top of this module.
_IDENTITY_ROLE: Final = {
    "table": "the name this read resolves by when the frame collects",
    "table_fingerprint": (
        "the content hash of the processed frame this read was written over"
    ),
}


def _refuse_malformed_attribute_set(node: Call) -> None:
    """Refuse a lookup whose attribute keys are not the four it carries.

    One refusal per defect, in the order a reader can act on: a key
    written twice first, because the caller reads the attributes as a
    mapping and a repeat collapses there into whichever of the two came
    last; then the keys of the four that never arrived, named together
    rather than one per attempt; then a key outside the four.
    """
    written = Counter(key for key, _ in node.attrs)
    repeated = [key for key, times in written.items() if times > 1]
    if repeated:
        msg = (
            f"lookup carries {_listed(repeated)} more than once: an attribute "
            "is one flat value under one key, so a second writing of the same "
            "key quietly replaces the first and nothing downstream can say "
            f"which of the two this read was written over. Write {_THE_FOUR} "
            f"once each. {_SIGNATURE}"
        )
        raise TypeError(msg)
    missing = [key for key in _REQUIRED_ATTRS if key not in written]
    if missing:
        noun = "attribute" if len(missing) == 1 else "attributes"
        msg = (
            f"lookup is missing the {noun} {_listed(missing)}: a lookup "
            f"carries {_THE_FOUR}, and none of the four takes a default -- "
            "filling one in here would answer the read under an identity or "
            f"a miss policy it never stated. {_SIGNATURE}"
        )
        raise TypeError(msg)
    unknown = [pair for pair in node.attrs if pair[0] not in _REQUIRED_ATTRS]
    if unknown:
        key, value = unknown[0]
        msg = (
            f"lookup does not carry the attribute {key!r}, which arrived here "
            f"as {value!r}: the four it carries are {_THE_FOUR}, and a fifth "
            "is configuration this operation has no meaning to give. Drop it, "
            "or write what it stood for as one of the four. "
            f"{_SIGNATURE}"
        )
        raise TypeError(msg)


def _identity_text(key: str, value: AttrValue) -> str:
    """Return a lookup's ``key`` half of the identity pair, or refuse it."""
    role = _IDENTITY_ROLE[key]
    if not isinstance(value, str):
        msg = (
            f"lookup's {key} attribute is not text: it arrived as "
            f"{type(value).__name__}, and what it carries is {role}, which "
            "only a string can name. Take it from the Table this read was "
            f"written against. {_SIGNATURE}"
        )
        raise TypeError(msg)
    if not value:
        msg = (
            f"lookup's {key} attribute is empty text: what it carries is "
            f"{role}, and an empty string names nothing -- there is no table "
            "for this read to answer from. Take it from the Table this read "
            f"was written against. {_SIGNATURE}"
        )
        raise TypeError(msg)
    return value


_TEXT_DTYPES: Final = (pl.String, pl.Categorical, pl.Enum)

_LITERAL_DTYPES: Final[dict[type, pl.DataType]] = {
    str: pl.String(),
    int: pl.Int64(),
    float: pl.Float64(),
}


def _key_dtype(
    arg: OpNode, expr: pl.Expr, ctx: LoweringContext | None
) -> pl.DataType | None:
    """Return the element type a lookup key holds, per policy or per period.

    A bare value needs no frame to be typed; a column or a computed key is
    asked of the frame it reads. A key no frame can type comes back ``None``
    and is not judged here: the kernel answers it, as a miss, the same way
    whichever storage the table has.
    """
    if isinstance(arg, Lit):
        # Keyed by exact type, so a bool (an int subclass) is not read as one.
        return _LITERAL_DTYPES.get(type(arg.value))
    if ctx is None:
        return None
    dtype = ctx.dtype_of_expr(expr)
    if not isinstance(dtype, pl.List):
        return dtype
    inner = dtype.inner
    return inner() if isinstance(inner, type) else inner


def _refuse_a_key_of_the_other_family(
    table: TableData,
    column: str,
    arg: OpNode,
    expr: pl.Expr,
    ctx: LoweringContext | None,
) -> None:
    """Refuse a key whose family -- text or number -- is not its dimension's.

    A text key never equals a number, and a number never equals text, so the
    read would miss on every row -- reported as a missing key under
    ``"raise"``, and as a silent NaN or fill under the other two policies. It
    is not a miss: §11.1.24 keeps a string query against a string key and a
    numeric query against a numeric one, and §11.1.28 refuses a key of the
    wrong family whatever the miss policy says. So it is refused here, when the
    lookup is written, with the way out -- and the same way whichever storage
    the table was given, since this is decided before either is asked.
    """
    if table._df is None:  # noqa: SLF001 - shared table data contract
        return
    held = table._df.schema.get(column)  # noqa: SLF001 - shared table data contract
    if held is None:
        return
    key_dtype = _key_dtype(arg, expr, ctx)
    if key_dtype is None:
        return
    key_is_text = isinstance(key_dtype, _TEXT_DTYPES)
    if held.is_numeric() and key_is_text:
        raise TypeError(_text_key_on_numbers(table, column, held, arg))
    if held == pl.String and key_dtype.is_numeric():
        raise TypeError(_number_key_on_text(table, column, key_dtype, arg))


def _read_in_the_table_s_kind(
    table: TableData,
    column: str,
    arg: OpNode,
    expr: pl.Expr,
    ctx: LoweringContext | None,
) -> pl.Expr:
    """Return a key as the table holds its dimension, or refuse it by kind.

    A key of the dimension's own kind is read in the table's unit: a date as
    its day count, a timestamp as its count in the table's unit -- the table
    holds each as that whole number. A key of another
    kind is refused by kind, with the conversion to write, whatever the miss
    policy says: a day count never equals a date, and the refusal of a miss,
    or a silent NaN, would be a wrong answer to a question nobody asked. A
    fixed-point decimal is read by its value, as a number. A text key and a
    number are refused by family, as before.
    """
    held = None if table._df is None else table._df.schema.get(column)  # noqa: SLF001 - shared table data contract
    key_dtype = _key_dtype(arg, expr, ctx)
    if held is None or key_dtype is None:
        return expr
    kind = table._key_kinds.get(column)  # noqa: SLF001 - shared table data contract
    if kind is None:
        _refuse_a_key_of_the_other_family(table, column, arg, expr, ctx)
        if key_dtype.is_temporal() or (key_dtype == pl.Boolean and held == pl.String):
            raise TypeError(
                _a_temporal_key_on_another_kind(table, column, held, key_dtype, arg)
            )
        if isinstance(key_dtype, pl.Decimal) and held.is_numeric():
            return _per_element(expr, ctx, lambda one: one.cast(pl.Float64))
        return expr
    if key_dtype.base_type() != kind.base_type():
        raise TypeError(
            _another_kind_on_a_temporal_key(table, column, kind, key_dtype, arg)
        )
    if (
        isinstance(kind, pl.Datetime)
        and isinstance(key_dtype, pl.Datetime)
        and (kind.time_zone is None) != (key_dtype.time_zone is None)
    ):
        raise TypeError(_naive_against_zoned(table, column, kind, key_dtype, arg))
    unit = getattr(kind, "time_unit", None)

    def in_the_table_s_unit(one: pl.Expr) -> pl.Expr:
        if unit is not None:
            one = one.dt.cast_time_unit(unit)
        return one.to_physical().cast(held)

    return _per_element(expr, ctx, in_the_table_s_unit)


def _per_element(
    expr: pl.Expr,
    ctx: LoweringContext | None,
    convert: Callable[[pl.Expr], pl.Expr],
) -> pl.Expr:
    """Apply ``convert`` to a key per policy, or to each period of a list key."""
    dtype = None if ctx is None else ctx.dtype_of_expr(expr)
    if isinstance(dtype, pl.List):
        return expr.list.eval(convert(pl.element()))
    return convert(expr)


def _kind_said(dtype: pl.DataType) -> str:
    """Name a key's kind the way a reader says it."""
    zone = getattr(dtype, "time_zone", None)
    named = {
        pl.Datetime: f"timestamps{f' in {zone}' if zone else ''} ({dtype})",
        pl.Date: "dates (Date)",
        pl.Duration: f"durations ({dtype})",
        pl.Time: "times of day (Time)",
        pl.Boolean: "flags (Boolean)",
    }.get(dtype.base_type())
    if named is not None:
        return named
    return (
        f"text ({dtype})" if isinstance(dtype, _TEXT_DTYPES) else f"numbers ({dtype})"
    )


def _another_kind_on_a_temporal_key(
    table: TableData,
    column: str,
    kind: pl.DataType,
    key_dtype: pl.DataType,
    arg: OpNode,
) -> str:
    """Word the refusal of a key of another kind against a date-like dimension."""
    dimension, _ = _dimension_spelling(table, column)
    return (
        f"Table {table.name!r} cannot be looked up on dimension {dimension!r} "
        f"with {_kind_said(key_dtype)}: the table holds {dimension!r} as "
        f"{_kind_said(kind)}, and {_key_name(arg)} is another kind. A key of "
        "another kind never equals one of these, whatever number it is held "
        "as, so it is refused rather than reported as a miss. Convert the key "
        "while setting up the model points, before the projection: "
        f"pl.col({_key_column_hint(arg)!r}).cast(pl.{kind.base_type()})."
    )


def _a_temporal_key_on_another_kind(
    table: TableData,
    column: str,
    held: pl.DataType,
    key_dtype: pl.DataType,
    arg: OpNode,
) -> str:
    """Word the refusal of a date-like key against a dimension of another kind."""
    dimension, _ = _dimension_spelling(table, column)
    hint = _key_column_hint(arg)
    if key_dtype == pl.Boolean:
        advice = f"pl.when(pl.col({hint!r})).then(<the label for true>)..."
    elif held == pl.String:
        advice = f"pl.col({hint!r}).dt.to_string(<the table's format>)"
    else:
        advice = (
            f"the number the table's keys count, such as pl.col({hint!r}).dt.year()"
        )
    return (
        f"Table {table.name!r} cannot be looked up on dimension {dimension!r} "
        f"with {_kind_said(key_dtype)}: {_key_name(arg)} holds them, and the "
        f"table holds {dimension!r} as {_kind_said(held)}. A key of that kind "
        "never equals one of these, so it is refused rather than reported as a "
        f"miss. Convert the key while setting up the model points: {advice}."
    )


def _naive_against_zoned(
    table: TableData,
    column: str,
    kind: pl.DataType,
    key_dtype: pl.DataType,
    arg: OpNode,
) -> str:
    """Word the refusal of a zone-naive timestamp against a zoned one."""
    dimension, _ = _dimension_spelling(table, column)
    return (
        f"Table {table.name!r} cannot be looked up on dimension {dimension!r} "
        f"with {_kind_said(key_dtype)}: the table holds {_kind_said(kind)}. A "
        "zone-naive timestamp and a zoned one name no instant to compare, so "
        "the key is refused rather than read in a zone it does not state. "
        "Give the key the table's zone while setting up the model points: "
        f"pl.col({_key_column_hint(arg)!r}).dt.replace_time_zone(...)."
    )


def _text_key_on_numbers(
    table: TableData, column: str, held: pl.DataType, arg: OpNode
) -> str:
    """Word the refusal of a text key against a dimension held as numbers.

    The commonest case is a table whose own column was text that spelled
    numbers -- maturity bands ``"1"`` and ``"5"`` -- which the build judged on
    those numbers (§15). The refusal says so, because nothing on the page
    shows it, and names the declaration that keeps the column text.
    """
    dimension, source = _dimension_spelling(table, column)
    msg = (
        f"Table {table.name!r} cannot be looked up on dimension {dimension!r} "
        f"with text: {_key_name(arg)} holds text, and the table holds "
        f"{dimension!r} as numbers. A text key never equals a number, so every "
        "row would miss."
    )
    if column in table._key_categories:  # noqa: SLF001 - shared table data contract
        msg += (
            f"\n\nThe table's own {source!r} column is text, but every cell "
            "spells a number, so the table was built on the numbers they name "
            f"({held}). If these are labels rather than quantities, declare "
            f"the dimension text when building the table:\n"
            f"    dimensions={{{dimension!r}: "
            f"DataDimension(column={source!r}, dtype=pl.String)}}"
        )
    return msg + (
        "\n\nIf they are numbers, convert the key column while setting up "
        "the model points, before the projection: "
        f"pl.col({_key_column_hint(arg)!r}).cast(pl.Float64)."
    )


def _number_key_on_text(
    table: TableData, column: str, key_dtype: pl.DataType, arg: OpNode
) -> str:
    """Word the refusal of a numeric key against a dimension held as text."""
    dimension, source = _dimension_spelling(table, column)
    msg = (
        f"Table {table.name!r} cannot be looked up on dimension {dimension!r} "
        f"with a number: {_key_name(arg)} holds numbers ({key_dtype}), and the "
        f"table holds {dimension!r} as text. A number never equals text, so "
        "every row would miss."
    )
    if column in _declared_text_columns(table._dimensions):  # noqa: SLF001 - shared table data contract
        msg += (
            f"\n\nThe dimension is declared text with DataDimension("
            f"column={source!r}, dtype=pl.String). If its cells are quantities "
            "rather than labels, drop dtype=pl.String and the table is built "
            "on the numbers they spell."
        )
    # A float spells 5 as "5.0", so it goes through a whole number first.
    cast = (
        ".cast(pl.Int64).cast(pl.String)"
        if key_dtype.is_float()
        else ".cast(pl.String)"
    )
    return msg + (
        "\n\nIf the key's values are the labels the table holds, convert the "
        "key column to text while setting up the model points, before the "
        f"projection: pl.col({_key_column_hint(arg)!r}){cast}."
    )


def _key_name(arg: OpNode) -> str:
    """Name a key the way the formula wrote it, where it has a name."""
    return f"af.{arg.name}" if isinstance(arg, Col) else "the key"


def _dimension_spelling(table: TableData, column: str) -> tuple[str, str]:
    """Name a processed key column the way the author wrote it: dimension, source."""
    for name, dim in table._dimensions.items():  # noqa: SLF001 - shared table data contract
        if isinstance(dim, DataDimension) and (dim.rename_to or dim.column) == column:
            return name, dim.column
    return column, column


def _key_column_hint(arg: OpNode) -> str:
    """Name the column a cast should convert: the key's own, or a placeholder."""
    return arg.name if isinstance(arg, Col) else "key"


@register_lowering("lookup")
def _lower_lookup(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Read one value per row out of an assumption table, by its keys.

    ``is_elementwise=True``: each row's lookup depends only on that row's
    keys, not on other rows. That is what lets the Polars streaming engine
    process the query in chunks instead of falling back to in-memory
    execution -- the single largest performance decision in the lookup
    path, so it is stated here rather than left implicit.
    """
    from polars.plugins import register_plugin_function  # noqa: PLC0415

    from gaspatchio.frame.lowering._polars.plugins import _get_lib  # noqa: PLC0415

    _refuse_malformed_attribute_set(node)
    attrs = dict(node.attrs)
    name = _identity_text("table", attrs["table"])
    fingerprint = _identity_text("table_fingerprint", attrs["table_fingerprint"])
    match attrs["on_missing"], attrs["fill_value"]:
        case (("raise" | "nan"), None):
            pass
        case "fill", float(fill) if math.isfinite(fill):
            pass
        case _:
            on_missing, fill_value = attrs["on_missing"], attrs["fill_value"]
            msg = (
                f"lookup carries on_missing={on_missing!r} beside "
                f"fill_value={fill_value!r}, which is not one of the three "
                "pairings a miss policy has: 'raise' with a null fill_value, "
                "'nan' with a null fill_value, or 'fill' with a finite "
                f"decimal. Write the pair this read means. {_SIGNATURE}"
            )
            raise TypeError(msg)
    table = table_named(name, fingerprint)
    key_columns, value_column = table_schema(name, fingerprint)
    if len(node.args) != len(key_columns):
        msg = (
            f"lookup carries {_counted(len(node.args), 'operand')} and the "
            f"processed table {name!r} has "
            f"{_counted(len(key_columns), 'key column')} "
            f"({_listed(key_columns)}): a lookup writes one operand per key "
            "column, in that table's own key-column order. Give the read one "
            f"key expression per key column. {_SIGNATURE}"
        )
        raise TypeError(msg)
    key_exprs = [
        _read_in_the_table_s_kind(table, column, arg, lower_arg(arg, ctx)[0], ctx)
        for column, arg in zip(key_columns, node.args, strict=True)
    ]

    return register_plugin_function(
        plugin_path=_get_lib(),
        function_name="lookup_by_table_and_hash",
        args=key_exprs,
        kwargs={
            "table_name": attrs["table"],
            "table_fingerprint": fingerprint,
            "key_columns": key_columns,
            "value_column": value_column,
            "on_missing": attrs["on_missing"],
            "fill_value": attrs["fill_value"],
        },
        is_elementwise=True,
    )
