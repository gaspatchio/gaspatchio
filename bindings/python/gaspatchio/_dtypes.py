# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The artifact's own names for column types, and the refusal when it has none.

An engine's display string for a type belongs to that engine. ``Utf8`` and
``String`` are one type under two names a release apart; ``Int8`` and
``Int64`` are one type as far as any reader of an exported model is
concerned; and none of those words mean anything to a consumer that never
heard of the engine that wrote them. Carrying them through would make the
artifact readable only by the thing that produced it, which is the one
property it must not have.

So the artifact names types itself, from a closed list of six scalars plus
``list[T]`` nested to three levels. Two rules follow from that list, and both
are deliberate:

- **Widths collapse.** Every integer is ``i64`` and every float ``f64``, so
  neither a producer nor a consumer may read storage width back out of the
  type. A model's answer does not depend on whether a column was stored in
  four bytes or eight, and a field that implied it did would invite a
  consumer to depend on something the producer never promised. The collapse
  stops where the *value* stops fitting, not where the width could stop
  fitting it: ``UInt64``, ``Int128`` and ``UInt128`` can hold numbers no
  ``i64`` carries, so a caller holding the column's values judges them
  instead of the width. Every value inside the signed 64-bit range is named
  ``i64`` -- the same name, and so the same canonical bytes, a hand-written
  ``.to_integer()`` would produce -- and the first value
  outside it is refused by its own number. A caller with no values in reach
  refuses the width itself, as it always did: the name is measured or it is
  not given.
- **A type with no name stops the export.** Not a lowercased engine string,
  not ``unknown``: a refusal that names the column, the type, the list of
  names there are, and the cast that would carry the value. ``unknown`` says
  the producer never determined a type -- true of a column defined and then
  dropped, and of a superseded definition unless the producer retained it
  and therefore did read one -- and using it for a type that
  was determined and could not be mapped would put a guess where the
  artifact's whole claim is that it can be checked.

The vocabulary has no time-delta type, so a duration column is refused with
the explicit-unit cast named. That cast is not a workaround: a count of days
carries its unit in the model where a reader can see it, and a bare duration
does not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import polars as pl

if TYPE_CHECKING:
    from gaspatchio.typing import PolarsDataType

# The scalar names an artifact may write. ``list[T]`` wraps any of these, and
# ordinary tuple order is what the refusal message reads out, so the list a
# reader is shown is the list this module enforces.
NEUTRAL_SCALAR_ORDER: Final[tuple[str, ...]] = (
    "bool",
    "i64",
    "f64",
    "str",
    "date",
    "datetime",
)

NEUTRAL_SCALARS: Final[frozenset[str]] = frozenset(NEUTRAL_SCALAR_ORDER)

# How a consumer with no date type of its own carries each name. The wire
# form of a value is an ISO-8601 string in every case -- that form is for the
# reader; this table is for the engine, which needs the epoch and the unit
# stated rather than inferred.
EXECUTION_TYPES: Final[dict[str, str]] = {
    "bool": "bool",
    "i64": "int64",
    "f64": "float64",
    "str": "utf8",
    "date": "int32 (days since 1970-01-01)",
    "datetime": "int64 (microseconds since 1970-01-01T00:00:00Z)",
}

# How deep ``list[T]`` may nest. A regular expression cannot express
# unbounded nesting, so the published schema's own pattern spells the levels
# out and stops at three; a producer that minted a fourth would be writing a
# type its own schema rejects.
MAX_LIST_DEPTH: Final[int] = 3

# The name the record carries where the producer never determined a type.
UNKNOWN: Final[str] = "unknown"

# The types that map by identity. Integers and floats are left out on
# purpose: they map by predicate, so a width polars adds later is carried
# without this table having to learn its name.
_BY_BASE_TYPE: Final[dict[type[pl.DataType], str]] = {
    pl.Boolean: "bool",
    pl.String: "str",
    pl.Date: "date",
    pl.Datetime: "datetime",
}

# The integer widths a collapse to ``i64`` would misdescribe *if the values
# needed the width*. ``i64`` is carried as ``int64`` (see EXECUTION_TYPES),
# and each of these can hold values that do not fit one -- polars' own
# ``.hash()`` produces a ``UInt64`` column whose values run past 2^63
# routinely. Naming such a column ``i64`` unmeasured would leave a JSON
# number beside a declared type that cannot hold it; naming it ``i64``
# having measured every value is the same claim the author's own
# ``.to_integer()`` makes, and produces the same bytes.
_TOO_WIDE_FOR_I64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.UInt64, pl.Int128, pl.UInt128}
)

# Where an ``i64`` stops having a name for the number. Every integer in an
# artifact travels as a signed 64-bit value, so this pair is the boundary a
# wider storage width is judged against -- the same boundary, for the same
# reason, that an assumption table's unsigned key is judged against in
# ``assumptions/_utils.py``.
I64_MAX: Final[int] = 2**63 - 1
I64_MIN: Final[int] = -(2**63)

# The two types that are a string with a dictionary in front of them. The
# dictionary is how the engine stored the column; the string is the value,
# and it is the value this vocabulary has a name for.
_A_STRING_UNDERNEATH: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Categorical, pl.Enum}
)


class UnmappedDtypeError(ValueError):
    """A column's type has no neutral name, so the artifact refuses to describe it.

    ``column`` is the column refused and ``move`` the sentence telling its
    author what to carry it as instead. Both are in the message too; they are
    kept apart from it so that a caller with room for one line can still
    carry the fix, rather than send the reader somewhere else to find it.
    """

    def __init__(
        self, message: str, *, column: str | None = None, move: str | None = None
    ) -> None:
        """Carry the message, and the column and the next move apart from it."""
        super().__init__(message)
        self.column = column
        self.move = move


_OUTPUT_BOUNDARY_GUIDANCE: Final[dict[type[pl.DataType], str]] = {
    pl.Null: (
        "Give all-null inputs an explicit dtype when constructing them, "
        "for example pl.Series(..., dtype=pl.Float64), or cast the column "
        "to the type you intend. For a list, declare its element type "
        "with pl.List(...). This applies even to unused columns. Null "
        "is a determined type, so it cannot be recorded as unknown."
    ),
    pl.Struct: (
        "Raw Struct output is outside portable output in this preview. "
        "For a compiled rollforward, assign named columns with "
        "compiled.expr_for(state) or compiled.increment_for(label). "
        "For other Struct data, select its fields as explicitly typed "
        "columns. Keep the raw Struct off the exported frame."
    ),
}


def _next_move(dtype: pl.DataType) -> str:
    """Return the sentence telling the author how to carry this type instead.

    Known unsupported types get specific guidance rather than generic advice,
    because the generic advice ("cast it to one of these") does not say to
    *what*, and for each of these there is one answer. A duration is always
    a count in an explicit unit -- which is also what puts the unit
    somewhere a reader can see it. An over-wide integer is an ``Int64``
    once the author has decided the values fit. An array is already the
    shape ``list[...]`` describes. And a category is a string: the
    dictionary in front of it is storage, so the cast loses nothing that
    was ever content.
    """
    base = dtype.base_type()
    guidance = _OUTPUT_BOUNDARY_GUIDANCE.get(base)
    if guidance is not None:
        return guidance
    if base is pl.Duration:
        return (
            "Cast it to a count in the unit you mean -- "
            ".polars_native().dt.total_days(), or .total_hours() or "
            ".total_seconds() through that same escape -- which carries the "
            "value as i64 and puts the unit in the model where a reader can "
            "see it. The date namespace belongs to Polars rather than to "
            "this vocabulary, which is why it is reached through "
            "polars_native() rather than written on the column. The "
            "vocabulary has no time-delta type deliberately: a duration "
            "whose unit lives in the engine rather than the model is not "
            "something a reader can check."
        )
    if base in _TOO_WIDE_FOR_I64:
        return (
            "Convert it with .to_integer() where you know the values fit "
            "-- signed 64-bit is the width every integer here travels in, "
            "and a conversion written in the model is what makes that fit "
            "an assumption a reader can see rather than one the exporter "
            "made for you. The conversion is checked rather than silent: a "
            "value no i64 carries refuses by name instead of wrapping, and "
            ".to_text() keeps every digit of one that never will."
        )
    if base is pl.Array:
        return (
            "An array is the list[...] this vocabulary already has with its "
            "length fixed, so .to_list() carries it unchanged in everything "
            "but the fixed length."
        )
    if base in _A_STRING_UNDERNEATH:
        return (
            "A category is a string with a dictionary in front of it, so "
            ".to_text() carries every value unchanged; what it drops is the "
            "engine's encoding of them, which was never content."
        )
    return (
        "Cast the column to one of these before the model finishes, or leave "
        "it off the frame."
    )


def _refuse(
    dtype: pl.DataType,
    column: str,
    reason: str,
    *,
    outer: pl.DataType | None = None,
) -> UnmappedDtypeError:
    """Build the refusal: what was met, on which column, and what to do next.

    ``outer`` is the type the column actually has, in the case where that is
    not the type that stopped the export: the thing with no name may be an
    element type inside a list, and the column is a list of them. Naming the
    element alone would send the author looking for a column that is not
    there and a cast that would not apply to it.
    """
    names = ", ".join(NEUTRAL_SCALAR_ORDER)
    met = dtype.base_type().__name__
    found = (
        f"has type {met}, which the calculation graph has no name for"
        if outer is None
        else (
            f"has type {outer}, whose element type {met} the calculation "
            f"graph has no name for"
        )
    )
    move = _next_move(dtype)
    return UnmappedDtypeError(
        f"Column {column!r} {found}. {reason} The types it can name "
        f"are {names}, and list[...] of any of those. {move}",
        column=column,
        move=move,
    )


def _refuse_a_value(column: str, offending: int) -> UnmappedDtypeError:
    """Build the refusal for a number no ``i64`` can carry.

    The shape an assumption table's unsigned key is already refused under
    (``assumptions/_utils.py``), because it is the same fact about the same
    boundary: what has no name here is the number, not the width somebody
    stored it in, so the number is what the sentence leads with. The cast
    offered is the one that keeps the digits -- text -- rather than the one
    that would silently lose them.
    """
    beyond = "larger" if offending > I64_MAX else "smaller"
    move = (
        "Keep the digits by holding the column as text -- .to_text() -- "
        "which carries every digit into the artifact unchanged."
    )
    return UnmappedDtypeError(
        f"Column {column!r} holds {offending}, which is {beyond} than the "
        "signed 64-bit integer every integer in this artifact travels as.\n"
        "\n"
        "A value has to be named exactly or the document states a number the "
        f"model never held, and outside [{I64_MIN}, {I64_MAX}] there is no "
        "exact numeric name left: this vocabulary calls every integer i64, "
        f"and an i64 cannot carry it.\n\n{move}",
        column=column,
        move=move,
    )


def _value_past_i64(values: pl.Series, depth: int) -> int | None:
    """Return a value outside signed 64-bit range, or None if every value fits.

    ``depth`` is how many ``list[...]`` levels the type was found under, so
    a column of lists is flattened that many times before its numbers are
    read: the question is about the values, and a list is where they are
    kept rather than one of them.

    Both ends are asked, because ``Int128`` is signed: a policy identifier
    runs off the top and a signed 128-bit column can run off the bottom,
    and either one is a number the record could not carry. Nulls are not
    values out of range -- ``max`` and ``min`` skip them, and an all-null
    column of any width casts to an all-null ``Int64`` -- so a column with
    no numbers in it fits, which is exactly what the cast it is being
    measured against would do.
    """
    for _ in range(depth):
        values = values.explode(empty_as_null=True)
    largest = values.max()
    if largest is not None and int(largest) > I64_MAX:  # type: ignore[arg-type]
        return int(largest)  # type: ignore[arg-type]
    smallest = values.min()
    if smallest is not None and int(smallest) < I64_MIN:  # type: ignore[arg-type]
        return int(smallest)  # type: ignore[arg-type]
    return None


def neutral_dtype(
    dtype: pl.DataType | None,
    *,
    column: str,
    values: pl.Series | None = None,
) -> str:
    """Return the artifact's own name for ``dtype``, or refuse.

    Args:
        dtype: The column's type as the engine resolved it, or None where
            no probe ever resolved one.
        column: The column the type belongs to, so a refusal can name it.
        values: The column itself, where the caller holds it. Only the
            integer widths wider than ``i64`` consult it, and only to ask
            whether every value fits one; a caller that does not hold the
            values passes nothing and those widths are refused on the width
            alone. The exporter holds the collected frame and passes it; a
            fingerprint taken off an unexecuted frame does not.

    Returns:
        A name from the closed vocabulary -- one of ``bool``, ``i64``,
        ``f64``, ``str``, ``date``, ``datetime``, or ``list[T]`` of one of
        those nested up to three deep -- or ``"unknown"`` where ``dtype``
        is None.

    Raises:
        UnmappedDtypeError: If ``dtype`` is a type the vocabulary has no
            name for, a list nested deeper than the schema can express, or
            a wide integer holding a value no ``i64`` carries.

    Examples:
        >>> import polars as pl
        >>> neutral_dtype(pl.Int32, column="policy_term")
        'i64'
        >>> neutral_dtype(pl.List(pl.Float64), column="account_value")
        'list[f64]'
        >>> neutral_dtype(None, column="reserve")
        'unknown'
        >>> policy_ids = pl.Series("policy_id", [7, 8], dtype=pl.UInt64)
        >>> neutral_dtype(pl.UInt64, column="policy_id", values=policy_ids)
        'i64'

    """
    if dtype is None:
        return UNKNOWN
    return _name(dtype, column=column, depth=0, values=values)


def _name(
    dtype: pl.DataType,
    *,
    column: str,
    depth: int,
    outer: pl.DataType | None = None,
    values: pl.Series | None = None,
) -> str:
    """Return the name for one type, recursing into a list's element type.

    ``outer`` carries the column's own type down the recursion, so a refusal
    raised on an element type can say which column type it was found inside.
    ``values`` carries the column itself, unflattened: only a wide integer
    asks for its numbers, so a list of ordinary floats is never exploded to
    answer a question nobody put.
    """
    base = dtype.base_type()

    if base is pl.List:
        if depth >= MAX_LIST_DEPTH:
            raise _refuse(
                dtype,
                column,
                "A list may nest three deep and this one nests deeper; "
                "three is what the published schema's own pattern can "
                "express, so a fourth level has no name to be written under.",
            )
        inner = getattr(dtype, "inner", None)
        if inner is None:
            raise _refuse(
                dtype,
                column,
                "Its element type was never resolved, and a list of "
                "nothing in particular is not a type this can name.",
            )
        found_in = dtype if outer is None else outer
        element = _name(
            inner, column=column, depth=depth + 1, outer=found_in, values=values
        )
        return f"list[{element}]"

    named = _BY_BASE_TYPE.get(base)
    if named is not None:
        return named
    if base in _TOO_WIDE_FOR_I64:
        if values is not None:
            offending = _value_past_i64(values, depth)
            if offending is None:
                return "i64"
            raise _refuse_a_value(column, offending)
        raise _refuse(
            dtype,
            column,
            "Every integer name it has is i64, which travels as a signed "
            "64-bit value, and this width holds numbers that do not fit "
            "one -- so naming it i64 would declare a type that cannot hold "
            "the value written beside it.",
            outer=outer,
        )
    # Every width of integer is i64 and every width of float f64, so these
    # two are predicates rather than four more table rows apiece.
    if dtype.is_integer():
        return "i64"
    if dtype.is_float():
        return "f64"

    raise _refuse(
        dtype,
        column,
        "Guessing a name for it would put an unchecked claim in the one "
        "document whose whole purpose is to be checked.",
        outer=outer,
    )


# The integer widths every value of which an ``i64`` holds exactly. A column
# of one of these arriving at the frame is read as ``Int64`` (see
# :func:`with_integers_as_i64`). The widths in ``_TOO_WIDE_FOR_I64`` are read
# as ``Int64`` only where the values are in hand and every one fits.
_NARROWER_THAN_I64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Int8, pl.Int16, pl.Int32, pl.UInt8, pl.UInt16, pl.UInt32}
)

# The float widths narrower than ``f64``. Every value of one is a double
# exactly, so a column of one arriving at the frame is read as ``Float64``,
# by the same rule and at the same doors as a narrow integer.
_NARROWER_THAN_F64: Final[frozenset[type[pl.DataType]]] = frozenset(
    {pl.Float16, pl.Float32}
)

# The most digits a fixed-point decimal of no places may carry and still have
# every value an ``i64`` holds (``10**18 - 1`` is below ``2**63``). A whole
# decimal past this precision is judged on its values, as a ``UInt64`` is.
_DIGITS_EVERY_I64_HOLDS: Final = 18


def _decimal_as_read(dtype: pl.Decimal, *, wide: bool) -> pl.DataType:
    """Return the type a fixed-point decimal is read as where it enters.

    Section 10 names no fixed-point decimal, so the value is read as the
    number it denotes: one with places as the double nearest it (a value
    past fifteen or sixteen significant figures loses the digits a double
    does not hold), one with none as the whole number it is -- an ``i64``
    where every value fits, and an ``Int128`` (every decimal of 38 digits
    fits one) judged by the rule for integers wider than ``i64`` where one
    may not.
    """
    if (dtype.scale or 0) > 0:
        return pl.Float64()
    precision = dtype.precision if dtype.precision is not None else 38
    if precision <= _DIGITS_EVERY_I64_HOLDS or wide:
        return pl.Int64()
    return pl.Int128()


def _a_wide_whole_decimal(dtype: pl.DataType) -> bool:
    """Return True for a decimal of no places whose digits may pass ``i64``."""
    return (
        isinstance(dtype, pl.Decimal)
        and (dtype.scale or 0) == 0
        and (dtype.precision is None or dtype.precision > _DIGITS_EVERY_I64_HOLDS)
    )


def _a_scalar_as_read(dtype: pl.DataType, *, wide: bool) -> pl.DataType | None:
    """Return the type a scalar column is read as where it enters, or None as it is."""
    base = dtype.base_type()
    if base in _NARROWER_THAN_I64 or (wide and base in _TOO_WIDE_FOR_I64):
        return pl.Int64()
    if base in _NARROWER_THAN_F64:
        return pl.Float64()
    if isinstance(dtype, pl.Decimal):
        return _decimal_as_read(dtype, wide=wide)
    return None


def integers_as_i64(dtype: pl.DataType, *, wide: bool = False) -> pl.DataType:
    """Return ``dtype`` with every integer narrower than ``i64`` read as ``Int64``.

    A float narrower than ``f64`` is read as ``Float64`` by the same rule:
    the record names it ``f64``, and a ``Float32`` column computed in its
    own four bytes would answer ``sum`` and ``exp`` to about seven figures
    while the record says the calculation was carried in a double.

    A fixed-point ``Decimal``, which section 10 does not name, is read as
    the number it denotes by the same rule: one with places as ``Float64``,
    one with none as ``Int64`` (``Int128`` where its digits may pass
    ``i64`` and ``wide`` is not given, so the rule for those widths judges
    it on its values).

    A list's or an array's element type is widened in place, so a book
    column of ``list[Int32]`` arrives as ``list[Int64]``; every other type
    comes back as it was handed in. With ``wide``, a ``UInt64``, ``Int128``
    or ``UInt128`` is read as ``Int64`` too: the caller has checked that
    every value fits (:func:`with_integers_as_i64`).
    """
    read = _a_scalar_as_read(dtype, wide=wide)
    if read is not None:
        return read
    element = getattr(dtype, "inner", None)
    if element is None:
        return dtype
    inner = integers_as_i64(element, wide=wide)
    if inner == element:
        return dtype
    if isinstance(dtype, pl.Array):
        return pl.Array(inner, dtype.shape)
    return pl.List(inner) if isinstance(dtype, pl.List) else dtype


def holds_a_decimal(dtype: pl.DataType) -> bool:
    """Say whether ``dtype`` is, or holds at any list depth, a fixed-point decimal."""
    if isinstance(dtype, pl.Decimal):
        return True
    element = getattr(dtype, "inner", None)
    return isinstance(element, pl.DataType) and holds_a_decimal(element)


def wider_than_i64_at(dtype: pl.DataType, depth: int = 0) -> int | None:
    """Return how many lists deep ``dtype`` holds an integer wider than ``i64``.

    The widths are ``UInt64``, ``Int128`` and ``UInt128``; None where it holds
    none of them. Those three are the widths an ``i64`` may not hold, so they
    are the ones whose values decide how a column is read and whether
    arithmetic may take it.
    """
    if dtype.base_type() in _TOO_WIDE_FOR_I64 or _a_wide_whole_decimal(dtype):
        return depth
    element = getattr(dtype, "inner", None)
    if not isinstance(element, pl.DataType):
        return None
    return wider_than_i64_at(element, depth + 1)


def with_integers_as_i64[FrameT: (pl.DataFrame, pl.LazyFrame)](
    frame: FrameT,
) -> FrameT:
    """Return ``frame`` with every integer column an ``i64`` holds read as ``Int64``.

    The record names every integer ``i64`` (section 10), and an engine that
    reads the record computes in ``i64``. A frame that kept an ``Int32``
    book column in its four bytes would compute ``sum_assured * 100`` in
    them and wrap at 2,147,483,647, while the record it writes says the
    calculation was carried in eight; one that kept a ``UInt64`` would
    answer ``7 - 10`` as 18,446,744,073,709,551,613. Reading the column as
    ``Int64`` where it arrives is what makes the run compute what its record
    states. A ``Float32`` or ``Float16`` column is read as ``Float64`` for
    the same reason: kept in its width, ``qx.list.sum()`` and
    ``cumulative_survival`` were carried in single precision while the
    record named a double. The reading is exact, so a column's content hash
    -- which already collapses widths -- and the book's digest do not move;
    only a results file, which stores what was computed, carries ``Int64``
    where it carried ``Int32`` and ``Float64`` where it carried ``Float32``.

    A ``UInt64``, ``Int128`` or ``UInt128`` column is judged on its values.
    A DataFrame's are in hand: where every value lies in ``[-2**63, 2**63 -
    1]`` the column is read as ``Int64``, and where one does not the column
    keeps the width it arrived in, so ``to_text`` writes that value by its
    digits and ``to_integer`` refuses it (sections 11.1.39 and 11.1.23). A
    LazyFrame's values are not in hand, so such a column keeps its width
    here and is judged when the plan runs: arithmetic, a sum, a running
    fold, a signed absolute value and a rollforward read it through a
    checked narrowing that refuses a value past ``i64`` by name rather than
    wrapping it (``frame/lowering/polars.py``), and a column no line wrote
    over is read by this same rule when the frame is collected
    (``ActuarialFrame._book_columns_judged``).

    A fixed-point ``Decimal`` column, which the record has no name for, is
    read where it arrives as the number it denotes: with places as the
    ``Float64`` nearest each value, with none as ``Int64`` -- or, where its
    digits may pass ``i64``, by the rule for the wide widths above. Its
    arithmetic then answers as the double's does (``1000.00 / 12`` is
    ``83.333...``, not the ``83.33`` the decimal's own two places kept), the
    book has a record, and the book's digest reads the value it entered as.

    A frame with nothing to read differently is handed back as it is, so a
    plan gains no step and a DataFrame no copy.
    """
    schema = frame.collect_schema()
    casts: dict[str, pl.DataType] = {}
    for name, dtype in schema.items():
        depth = wider_than_i64_at(dtype)
        fits = (
            depth is not None
            and isinstance(frame, pl.DataFrame)
            and _value_past_i64(frame[name], depth) is None
        )
        read = integers_as_i64(dtype, wide=fits)
        if read != dtype:
            casts[name] = read
    return frame.cast(pl.Schema(casts), strict=True) if casts else frame


def _zero_without_its_sign(expr: pl.Expr, dtype: PolarsDataType) -> pl.Expr | None:
    """Return ``expr`` with every float zero written ``+0.0``; None where it holds none.

    Polars' ``replace`` matches a value by equality, under which ``-0.0`` is
    ``0.0``, so every zero is replaced by the literal ``+0.0`` and every
    other value -- a NaN with its payload, an infinity, a null -- passes
    through as it is.
    """
    if dtype in (pl.Float32, pl.Float64):
        return expr.replace(0.0, 0.0)
    if isinstance(dtype, pl.List):
        inner = _zero_without_its_sign(pl.element(), dtype.inner)
        return None if inner is None else expr.list.eval(inner)
    if isinstance(dtype, pl.Array):
        inner = _zero_without_its_sign(pl.element(), dtype.inner)
        if inner is None:
            return None
        return expr.arr.to_list().list.eval(inner).list.to_array(dtype.size)
    return None


def series_with_signed_zeros_as_zero(series: pl.Series) -> pl.Series:
    """Return ``series`` with every negative zero at any depth written ``0.0``.

    See :func:`with_signed_zeros_as_zero`. A series holding no float is
    handed back as it is.
    """
    dtype = series.dtype
    if dtype in (pl.Float32, pl.Float64):
        return series.replace(0.0, 0.0)
    if isinstance(dtype, pl.List | pl.Array):
        inner = _zero_without_its_sign(pl.element(), dtype.inner)
        if inner is None:
            return series
        if isinstance(dtype, pl.Array):
            return series.arr.to_list().list.eval(inner).list.to_array(dtype.size)
        return series.list.eval(inner)
    return series


def with_signed_zeros_as_zero(frame: pl.DataFrame) -> pl.DataFrame:
    """Return ``frame`` with every negative zero in its float columns written ``0.0``.

    Spec section 12.3 hashes a column of data with a negative zero written
    as zero: in data a zero's sign is whatever the arithmetic that produced
    it left behind. So that one identity has one answer, the value is
    written that way where data enters too -- an assumption table's source
    and a column injected into a frame -- before it is hashed or read, and
    an operation that reads a sign (``sign``, ``to_text``) sees ``+0.0``
    there. A literal written into a formula and a compiled machine's
    settings are not data, and keep their sign (sections 12.1 and 12.2).

    Floats at any depth of a list or a fixed-width array are written the
    same way. A frame holding no float column is handed back as it is.
    """
    rewritten = [
        series_with_signed_zeros_as_zero(frame.get_column(name))
        for name, dtype in frame.schema.items()
        if _zero_without_its_sign(pl.element(), dtype) is not None
    ]
    return frame.with_columns(rewritten) if rewritten else frame
