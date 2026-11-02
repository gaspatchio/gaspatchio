# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What kind of value a fill, a branch or a bound is, and the refusal when two meet.

``af.rate.fill_null("n/a")`` over a column of decimals ran and handed back
text -- ``['1.0', 'n/a']`` -- because Polars makes a fill fit by finding a
type both sides can be written in, and every number can be written as text.
Nobody wrote that conversion. The JAX engine and the conformance reader
refuse the line; the frame that produced it did not. The same silent
widening, or worse a silent narrowing, waited in every operation that puts
one value where another stood: the two fills, a conditional's branches, a
period shift's ``fill_value``, a substitution's values and a clip's bounds.

**A kind is the family 11.1.26 and 11.1.28 keep apart**: a number (a whole
number, a decimal, or a flag, which this framework stores as a 0/1 indicator
whenever a comparison is assigned as a value), text, and a calendar date,
with a date-and-time, a duration and a time of day each their own. Two
operands of one kind meet as they always have -- a whole number beside a
decimal is the decimal, the declared widening of 11.1.13 and 11.1.28 -- and
two of different kinds are refused at the line, naming the move. Where an
operation keeps the receiver's own type rather than the pair's (``replace``,
``clip``), a decimal written into whole numbers or a number into flags would
be cut down to fit, so that narrowing is refused too.

**A comparison across kinds is refused the same way.** ``af.d < 3`` over a
column of dates ran and answered false for every policy, because Polars
compared each date's day count with 3. 11.1.26 infers no ordering between
two families, so the six comparisons and ``is_in``'s members are held to
one kind too -- a flag still counts as a number there, as it does in the
second engine's comparison table.

A null is not a kind: it stands in any column. A type this module does not
name (a struct, binary) is left to the engine, as is a fill whose type cannot
be resolved without data.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Final

import polars as pl

from gaspatchio._semantic.ir import BinOp, Col, EngineNative, Lit

if TYPE_CHECKING:
    from typing import Literal

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.frame.lowering.context import LoweringContext

    # Named for the type checker alone: a module-level alias has no stub, and
    # stubtest reads the runtime ``Literal`` object as a callable.
    _Kind = Literal["number", "text", "date", "datetime", "duration", "time"]

_PHRASE: dict[_Kind, str] = {
    "number": "a number",
    "text": "text",
    "date": "a date",
    "datetime": "a date and time",
    "duration": "a duration",
    "time": "a time of day",
}

# The type each kind of written value is held in, most specific first.
_LITERAL_TYPES: tuple[tuple[type, pl.DataType], ...] = (
    (bool, pl.Boolean()),
    (int, pl.Int64()),
    (float, pl.Float64()),
    (str, pl.String()),
    (dt.datetime, pl.Datetime()),
    (dt.date, pl.Date()),
    (dt.timedelta, pl.Duration()),
    (dt.time, pl.Time()),
)

# Within the numbers, how wide a type is: a flag fits in a whole number and a
# whole number in a decimal, and never the other way without losing something.
_FLAG, _WHOLE, _DECIMAL = 0, 1, 2


def literal_dtype(value: object) -> pl.DataType | None:
    """Return the type a value written into the formula is held in, or None.

    ``bool`` is read before ``int`` and ``datetime`` before ``date``, because
    each is a subclass of the other. ``None`` answers ``Null``: a missing
    value written as a fill is no conversion of anything.
    """
    if value is None:
        return pl.Null()
    for python_type, dtype in _LITERAL_TYPES:
        if isinstance(value, python_type):
            return dtype
    return None


def operand_dtype(
    node: OpNode, expr: pl.Expr, ctx: LoweringContext | None
) -> pl.DataType | None:
    """Return the type one operand resolves to, without evaluating anything.

    A literal is typed from the value written; anything else from the
    frame's schema through the context, and not at all without one.
    """
    if isinstance(node, Lit):
        return literal_dtype(node.value)
    if ctx is None:
        return None
    return ctx.dtype_of_expr(expr)


def _element(dtype: pl.DataType) -> pl.DataType:
    """Return a per-period column's element type, or the type itself."""
    return dtype.inner if isinstance(dtype, pl.List) else dtype  # type: ignore[return-value]


def kind_of(dtype: pl.DataType | None) -> _Kind | None:
    """Return the kind a type holds, its elements' kind for a per-period one."""
    if dtype is None:
        return None
    base = _element(dtype).base_type()
    if base.is_numeric() or base == pl.Boolean:
        return "number"
    kinds: dict[object, _Kind] = {
        pl.String: "text",
        pl.Categorical: "text",
        pl.Enum: "text",
        pl.Date: "date",
        pl.Datetime: "datetime",
        pl.Duration: "duration",
        pl.Time: "time",
    }
    return kinds.get(base)


def _width(dtype: pl.DataType) -> int:
    """Return how wide a number's type is: a flag, a whole number, a decimal."""
    base = _element(dtype).base_type()
    if base == pl.Boolean:
        return _FLAG
    if base.is_integer():
        return _WHOLE
    return _DECIMAL


def describe(dtype: pl.DataType) -> str:
    """Return what a type holds, in the words a refusal uses."""
    kind = kind_of(dtype)
    if kind != "number":
        return _PHRASE[kind] if kind is not None else str(dtype)
    return {
        _FLAG: "a flag (True/False)",
        _WHOLE: "a whole number",
        _DECIMAL: "a decimal",
    }[_width(dtype)]


def shown(node: OpNode | str) -> str:
    """Return how a refusal names an operand: its value, its column, or neither.

    A site that holds the value as written rather than as a node -- a
    substitution's pairs -- passes the text it should be named by.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, Lit):
        return repr(node.value)
    if isinstance(node, Col):
        return f"the column {node.name!r}"
    if isinstance(node, EngineNative):
        written = _a_literal_as_written(node)
        if written is not None:
            return written
    return "an expression"


def _a_literal_as_written(node: EngineNative) -> str | None:
    """Return the value a literal the tree holds as engine-native was written as.

    A date and time, a duration and a time of day have no literal of the
    tree's own (section 10), so one written into a formula --
    ``af.z > datetime(2025, 1, 1)`` -- is held as the engine's literal of it,
    and a refusal named it "an expression". It is the literal it is, read
    back by its value as a :class:`Lit` is. None for anything that reads a
    column or is not one value.
    """
    from gaspatchio.frame.lowering.ingress import NATIVE_REFS  # noqa: PLC0415 -- cycle

    entry = NATIVE_REFS.get(id(node))
    if node.deps or entry is None or entry[0] is not node:
        return None
    try:
        if not entry[1].meta.is_literal():
            return None
        values = pl.select(entry[1]).to_series()
    except pl.exceptions.PolarsError:
        return None
    return repr(values.item()) if values.len() == 1 else None


def apart(
    receiver: pl.DataType | None,
    fill: pl.DataType | None,
    *,
    keeps_receiver_type: bool = False,
    numbers: frozenset[int] | None = None,
) -> bool:
    """Return whether ``fill`` cannot stand where ``receiver`` stood unconverted.

    Two kinds apart always are. ``keeps_receiver_type`` is for an operation
    whose answer is the receiver's own type, where a wider number would be
    cut down to fit. ``numbers`` narrows which numbers the fill may be, for
    an operation whose domain states fewer than all three (``fill_nan``'s is
    whole numbers and decimals, 11.1.13). An operand whose type is unknown,
    or a null, is never apart from anything.
    """
    fill_kind, receiver_kind = kind_of(fill), kind_of(receiver)
    if fill is None or receiver is None or fill_kind is None or receiver_kind is None:
        return False
    if fill_kind != receiver_kind:
        return True
    if fill_kind != "number":
        return False
    if numbers is not None and _width(fill) not in numbers:
        return True
    return keeps_receiver_type and _width(fill) > _width(receiver)


def is_flag(dtype: pl.DataType | None) -> bool:
    """Return whether a type holds flags (True/False), per period or not."""
    return dtype is not None and _element(dtype).base_type() == pl.Boolean


def can_hold_nan(dtype: pl.DataType | None) -> bool | None:
    """Return whether ``fill_nan`` has an answer over a type, or None if unknown.

    A decimal holds NaN and a whole number never does, and 11.1.13 answers
    both: the whole numbers stand as they were. A flag, text, a date, a
    date-and-time, a duration and a time of day cannot hold one, and the
    engine has no NaN test over any of them, so ``fill_nan`` has no answer
    there. A type this module does not name is left to the engine.
    """
    kind = kind_of(dtype)
    if kind is None:
        return None
    return kind == "number" and not is_flag(dtype)


# How a refusal writes each comparison, as the model wrote it.
_SYMBOL: dict[str, str] = {
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
    "eq": "==",
    "ne": "!=",
}

# A value of each calendar kind, written as a model would write one.
_CALENDAR_EXAMPLE: dict[str, str] = {
    "date": "date(2025, 6, 1)",
    "datetime": "datetime(2025, 6, 1)",
}


def written(node: OpNode) -> str:
    """Return an operand as a model writes it: ``af.d``, ``3``, an expression."""
    if isinstance(node, Lit):
        # A date as a model imports and writes it, not as its repr spells it.
        return repr(node.value).removeprefix("datetime.")
    if isinstance(node, Col):
        return f"af.{node.name}" if node.name.isidentifier() else f"af[{node.name!r}]"
    if isinstance(node, BinOp) and node.op in _ARITHMETIC_SYMBOL:
        # An operand that is itself arithmetic, as the model wrote it.
        symbol = _ARITHMETIC_SYMBOL[node.op]
        return f"({written(node.left)} {symbol} {written(node.right)})"
    return "(the expression)"


def _comparison_move(
    left: OpNode, left_kind: _Kind, right: OpNode, right_kind: _Kind, symbol: str
) -> str:
    """Return the move for a comparison across two kinds, in written order.

    Every move named is one a model can write: the value in the column's own
    kind, ``.str.to_date()`` for text holding dates, ``to_text()`` for a
    number compared as a code. No declared conversion reads text as a
    number, so that one is named where the data is loaded.
    """
    kinds = {left_kind, right_kind}
    calendar = kinds & set(_CALENDAR_EXAMPLE)
    if len(calendar) == 1 and kinds & {"number", "text"}:
        kind = left_kind if left_kind in calendar else right_kind
        example = _CALENDAR_EXAMPLE[kind]
        if left_kind == kind:
            line = f"{written(left)} {symbol} {example}"
        else:
            line = f"{example} {symbol} {written(right)}"
        text = (
            "; if the text holds dates, read it as one first with .str.to_date()"
            if "text" in kinds
            else ""
        )
        return f"Compare it with {_PHRASE[kind]}: {line}{text}."
    if kinds == {"number", "text"}:
        sides = [written(left), written(right)]
        number_at = 0 if left_kind == "number" else 1
        number = (left, right)[number_at]
        sides[number_at] = (
            repr(str(number.value))
            if isinstance(number, Lit)
            else f"{sides[number_at]}.to_text()"
        )
        return (
            "If the number is a code, compare it as text: "
            f"{sides[0]} {symbol} {sides[1]}; if the text holds amounts, read "
            "them as numbers where the data is loaded, before the frame is "
            "built, and compare those."
        )
    return (
        "Compare two values of one kind: write the value as the kind the column holds."
    )


def comparison_refusal(
    *,
    op: str,
    left: OpNode,
    left_dtype: pl.DataType,
    right: OpNode,
    right_dtype: pl.DataType,
) -> TypeError | None:
    """Return the refusal for a comparison across two kinds, or None.

    Two operands of one kind compare as they always have, a whole number
    beside a decimal and a flag beside a number included. Two of different
    kinds have no order or equality between them (11.1.26), and Polars'
    answer -- a date's day count set against a number, or a refusal only
    when the frame runs -- is not one the formula wrote.
    """
    left_kind, right_kind = kind_of(left_dtype), kind_of(right_dtype)
    if left_kind is None or right_kind is None or left_kind == right_kind:
        return None
    symbol = _SYMBOL.get(op, op)
    move = _comparison_move(left, left_kind, right, right_kind, symbol)
    msg = (
        f"{written(left)} {symbol} {written(right)}: the comparison sets "
        f"{describe(left_dtype)} against {describe(right_dtype)}, and there is "
        "no order or equality between the two. Polars would answer only by "
        "converting one into the other's type, a conversion the formula never "
        f"wrote, so the line is refused. {move}"
    )
    return TypeError(msg)


# How a refusal writes each arithmetic operator, as the model wrote it.
_ARITHMETIC_SYMBOL: dict[str, str] = {
    "add": "+",
    "sub": "-",
    "mul": "*",
    "div": "/",
    "floordiv": "//",
    "mod": "%",
    "pow": "**",
}

# The logical operator a flag-on-flag line most often means, where it has one.
_LOGICAL_READING: dict[str, tuple[str, str]] = {
    "mul": ("both", "&"),
    "add": ("either", "|"),
}


def flag_arithmetic_refusal(*, op: str, left: OpNode, right: OpNode) -> TypeError:
    """Return the refusal for arithmetic between two per-policy flags.

    A flag beside a number reads as the 0 or 1 it indicates, but section
    11.1.25 does not admit a per-policy flag on both sides of one operation:
    Polars has no product, difference, floor quotient, remainder or power of
    two flags and fails where the frame runs, in its own words, and answers
    the sum as an unsigned count. The line is refused where it is written,
    naming the logical operator it may mean and the conversion that makes
    one flag an amount.
    """
    symbol = _ARITHMETIC_SYMBOL.get(op, op)
    first, second = written(left), written(right)
    conversion = f"when({first}).then(1.0).otherwise(0.0) {symbol} {second}"
    reading = _LOGICAL_READING.get(op)
    move = (
        f"If the line means {reading[0]}, write {first} {reading[1]} {second}; "
        f"if it means an amount, write the conversion: {conversion}."
        if reading is not None
        else f"Write the conversion that makes one of them an amount: {conversion}."
    )
    msg = (
        f"{first} {symbol} {second}: both operands are flags (True/False), one "
        "value per policy, and arithmetic between two flags is not admitted "
        "(section 11.1.25 of the specification). Polars would fail on it when "
        "the frame runs, or answer in a type no formula wrote, so the line is "
        f"refused. {move}"
    )
    return TypeError(msg)


# The kinds no arithmetic and no numeric call reads: a number is not text, a
# date, a date and time or a time of day, and Polars refused each pairing in
# its own words when the frame ran.
_NOT_NUMBERS: frozenset[str] = frozenset({"text", "date", "datetime", "time"})

# What a model writes instead of arithmetic on each kind that is not a number.
_NUMBER_OF: dict[str, str] = {
    "text": "the number the text stands for, carried as a number in the book",
    "date": (
        "a count read off the date -- the years or months elapsed since "
        "another date, as a whole number"
    ),
    "datetime": (
        "a count read off the date and time -- the units elapsed since "
        "another, as a whole number"
    ),
    "time": "a count read off the time of day, as a whole number",
    "duration": (
        "the count in the unit you mean -- .polars_native().dt.total_days(), "
        "or .total_hours() or .total_seconds() through that same escape, a "
        "whole number -- since the vocabulary has no time-delta type"
    ),
}

# The arithmetic Polars has a kernel for between a duration and a number: a
# duration scaled -- times a number on either side, or over one -- where both
# are one value per policy, and a run of durations times or over a number
# written on its right. Every other pairing failed in Polars' words when the
# frame ran ("+ not allowed on duration[us] and i64").
_A_DURATION_SCALED: frozenset[str] = frozenset({"mul", "div"})

# The arithmetic Polars has no kernel for over an engine's fixed-point decimal,
# per policy. Per period it has one only for a run with a number written on its
# right: the four operators below beside a whole number or a double, and a
# floor quotient or remainder beside a double.
_NO_DECIMAL_KERNEL: frozenset[str] = frozenset({"floordiv", "mod", "pow"})
_A_RUN_BESIDE_A_WRITTEN_NUMBER: frozenset[str] = frozenset({"add", "sub", "mul", "div"})


def is_decimal(dtype: pl.DataType | None) -> bool:
    """Say whether a type, or a per-period one's element, is a fixed-point decimal."""
    return dtype is not None and isinstance(_element(dtype), pl.Decimal)


def arithmetic_refusal(  # noqa: PLR0913 -- the operator, and each side as written, as typed and as shaped
    *,
    op: str,
    left: OpNode,
    left_dtype: pl.DataType | None,
    right: OpNode,
    right_dtype: pl.DataType | None,
    per_period: bool,
) -> TypeError | None:
    """Return the refusal for arithmetic Polars refuses in its own words, or None.

    ``af.n * af.code`` over text, ``af.issue + 1`` over dates and ``af.dur +
    af.rate_dec`` over a per-period whole number and a decimal each failed
    only when the frame ran, as ``arithmetic on dtypes str and i64 is not
    allowed`` or ``cannot add two list columns with non-numeric inner
    types``. Arithmetic is the numbers' (11.1.25): a number beside text, a
    date, a date and time or a time of day is refused where the line is
    written, naming the kind and the number to write instead; so is a number
    beside a duration, except where Polars scales the duration
    (:func:`_polars_scales_the_duration`); and so is an
    engine's fixed-point decimal where this engine has no kernel for it --
    per period at all, and per policy under ``//``, ``%`` and ``**``. Two
    operands neither of which is a number (two dates, a date and a
    duration) are left to the engine, as is an operand whose type is not
    read.
    """
    kinds = (kind_of(left_dtype), kind_of(right_dtype))
    symbol = _ARITHMETIC_SYMBOL.get(op, op)
    line = f"{written(left)} {symbol} {written(right)}"
    refused = _not_a_number_beside_a_number(
        line, (left, left_dtype), (right, right_dtype), op=op, per_period=per_period
    )
    if refused is not None:
        return refused
    # The decimal named is a run's where one side is a run of decimals.
    decimal = next(
        (
            (node, dtype)
            for node, dtype in sorted(
                ((left, left_dtype), (right, right_dtype)),
                key=lambda side: not isinstance(side[1], pl.List),
            )
            if is_decimal(dtype)
        ),
        None,
    )
    if decimal is None or kinds != ("number", "number"):
        return None
    if not per_period and op not in _NO_DECIMAL_KERNEL:
        return None
    if per_period and _a_run_beside_a_written_number(op, left_dtype, right):
        return None
    # Beside a double the pair is the double's, and Polars has its floor
    # quotient and remainder.
    beside_a_double = any(
        dtype is not None and _element(dtype).is_float()
        for dtype in (left_dtype, right_dtype)
    )
    if not per_period and op != "pow" and beside_a_double:
        return None
    where = (
        "per period, where this engine has no arithmetic over a decimal at all"
        if per_period
        else f"and this engine has no {symbol} over one"
    )
    move = (
        f"carry it as a double first -- ({written(decimal[0])} * 1.0) -- which "
        "reads it as its fifteen significant figures"
        if not per_period
        else "carry it as a double in the book the model runs over"
    )
    msg = (
        f"{line}: {shown(decimal[0])} is an engine's fixed-point decimal, "
        f"{where}; Polars would refuse it in its own words when the frame "
        f"runs, so the line is refused here. To compute with it, {move}."
    )
    return TypeError(msg)


def _not_a_number_beside_a_number(
    line: str,
    left: tuple[OpNode, pl.DataType | None],
    right: tuple[OpNode, pl.DataType | None],
    *,
    op: str,
    per_period: bool,
) -> TypeError | None:
    """Return the refusal for a number beside a value that is not one, or None.

    Text, a date, a date and time or a time of day beside a number is always
    refused; a duration beside one is refused except where Polars scales the
    duration and answers (:func:`_polars_scales_the_duration`).
    """
    kinds = (kind_of(left[1]), kind_of(right[1]))
    if "number" not in kinds:
        return None
    odd, odd_dtype = left if kinds[0] != "number" else right
    if "duration" in kinds:
        if _polars_scales_the_duration(
            op, kinds, (left[1], right[1]), right[0], per_period=per_period
        ):
            return None
        msg = (
            f"{line}: {shown(odd)} is a duration, and arithmetic reads numbers "
            "(section 11.1.25 of the specification); Polars would refuse the "
            "pair in its own words when the frame runs, so the line is refused "
            f"here. Write {_NUMBER_OF['duration']}, and the arithmetic over that."
        )
        return TypeError(msg)
    if not _NOT_NUMBERS & set(kinds):
        return None
    kind = kind_of(odd_dtype)
    what = describe(odd_dtype) if odd_dtype is not None else str(kind)
    msg = (
        f"{line}: {shown(odd)} is {what}, and arithmetic "
        "reads numbers (section 11.1.25 of the specification); Polars "
        "would refuse the pair in its own words when the frame runs, so "
        f"the line is refused here. Write {_NUMBER_OF[str(kind)]}, and the "
        "arithmetic over that."
    )
    return TypeError(msg)


def _polars_scales_the_duration(
    op: str,
    kinds: tuple[_Kind | None, _Kind | None],
    dtypes: tuple[pl.DataType | None, pl.DataType | None],
    right: OpNode,
    *,
    per_period: bool,
) -> bool:
    """Say whether a duration beside a number is one Polars scales, and answers.

    ``af.term * 2``, ``2 * af.term`` and ``af.term / af.n`` answered on the
    base as a duration -- one value per policy each -- and so did a run of
    durations times or over a number written on its right. Those still
    answer, as a run of decimals beside a written number does: they are
    Polars' own kernels, not a failure in its words, and the export names the
    duration column it cannot write. A number over a duration, and every
    ``+``, ``-``, ``//``, ``%`` and ``**``, failed when the frame ran.
    """
    if op not in _A_DURATION_SCALED:
        return False
    if not per_period:
        return op == "mul" or kinds[0] == "duration"
    left_dtype = dtypes[0]
    return (
        kinds[0] == "duration"
        and isinstance(left_dtype, pl.List)
        and isinstance(right, Lit)
        and isinstance(right.value, (int, float))
        and not isinstance(right.value, bool)
    )


def _a_run_beside_a_written_number(
    op: str, left_dtype: pl.DataType | None, right: OpNode
) -> bool:
    """Say whether a decimal run meets a number written on its right Polars computes.

    ``af.rates * 2``, ``af.rates / 2.0`` and ``-af.rates`` over a run of
    decimals answered before arithmetic between a number and a decimal run
    was refused, and they still answer: this engine has the kernel for a run
    on the left and a whole number or a double written on its right, and for
    a floor quotient or remainder by a written double.
    """
    if not (isinstance(left_dtype, pl.List) and is_decimal(left_dtype)):
        return False
    if not isinstance(right, Lit) or isinstance(right.value, bool):
        return False
    if op in _A_RUN_BESIDE_A_WRITTEN_NUMBER:
        return isinstance(right.value, (int, float))
    return op in {"floordiv", "mod"} and isinstance(right.value, float)


def not_a_number_refusal(
    *, line: str, operand: OpNode, dtype: pl.DataType
) -> TypeError:
    """Return the refusal for a numeric call over text, a date, a time or a duration.

    ``af.codes.cum_sum()`` over text and ``af.issue.abs()`` over dates
    failed only when the frame ran, as ```cum_sum` operation not supported
    for dtype `str```; ``af.code.exp()`` read "2.0" as a number and "A" as a
    null, and ``af.codes.list.mean()`` answered null.
    """
    kind = kind_of(dtype)
    instead = _NUMBER_OF.get(str(kind), "a number")
    msg = (
        f"{line}: the value it reads -- {shown(operand)} -- is "
        f"{describe(dtype)}, and {line} reads a number, so the line is refused "
        "where it is written; Polars would read it as a number of its own "
        "choosing, or refuse it in its own words when the frame runs. "
        f"Write {instead}, and {line} over that."
    )
    return TypeError(msg)


def refuse_unless_a_number(
    *,
    line: str,
    operand: OpNode,
    dtype: pl.DataType | None,
    decimal: bool = False,
    duration: bool = False,
) -> None:
    """Refuse a numeric call over a value that is not a number, at the line.

    ``decimal`` refuses an engine's fixed-point decimal too, for a call this
    engine has no kernel for over one (a running product). ``duration``
    refuses a duration, for a call that reads a number out of one: the
    vocabulary has no time-delta type (section 10), and Polars either failed
    in its own words (``sign``, ``round``, ``floor``, ``ceil``,
    ``round_sig_figs``, ``norm_cdf``, ``cum_prod``, ``cumulative_survival``)
    or read the duration as its count in its own storage unit, so that
    ``sqrt`` of five years answered 12563948.4, the root of a count of
    microseconds. A call whose answer is itself a duration -- ``abs``, a
    total, a running total, a least, a greatest, an average -- is not
    refused: Polars answers it in the duration's own terms.
    """
    if dtype is None:
        return
    if kind_of(dtype) in _NOT_NUMBERS or (duration and kind_of(dtype) == "duration"):
        raise not_a_number_refusal(line=line, operand=operand, dtype=dtype)
    if decimal and is_decimal(dtype):
        msg = (
            f"{line}: the value it reads -- {shown(operand)} -- is an engine's "
            f"fixed-point decimal, and this engine has no {line} over one; "
            "Polars would refuse it in its own words when the frame runs, so "
            "the line is refused here. Carry it as a double first."
        )
        raise TypeError(msg)


# What a refusal says an operand held at the wrong shape holds.
PER_POLICY: Final = "one value per policy"
PER_PERIOD: Final = "one value per period"


# The clause each fold of one policy's own periods is stated in, and the move
# a fold over one value per policy is refused with.
FOLD_CLAUSE: Final[dict[str, str]] = {
    "sum": "11.1.14",
    "mean": "11.1.15",
    "min": "11.1.16",
    "max": "11.1.17",
    "cum_sum": "11.1.9",
    "cum_prod": "11.1.9",
}
FOLD_MOVE: Final = (
    "Fold the per-period column the model means: a fold down the rows of a "
    "model-point file is a different calculation, and this vocabulary does not "
    "name it."
)


def refuse_a_fold_over_one_value(name: str, operand: OpNode, shape: str) -> None:
    """Refuse a fold of one policy's periods handed one value per policy.

    Polars failed when the frame ran, in its own words (``list.eval operation
    not supported for dtype f64``); the line is refused where it is written.

    Raises:
        ValueError: Where the operand holds one value per policy.

    """
    if shape != "scalar":
        return
    raise shape_refusal(
        line=f"{name}()",
        does="folds one policy's own periods",
        clause=FOLD_CLAUSE[name],
        operand=operand,
        holds=PER_POLICY,
        move=FOLD_MOVE,
    )


def shape_refusal(  # noqa: PLR0913 -- one parameter per part of the sentence a refusal says
    *,
    line: str,
    does: str,
    clause: str,
    operand: OpNode | str,
    holds: str,
    move: str,
) -> ValueError:
    """Return the refusal for an operand held at a shape its operation does not read.

    The sentence names the operation and what it does, the clause stating it,
    the operand as written and the shape it holds, and the move -- where the
    line is written, rather than in Polars' words when the frame runs.
    """
    msg = (
        f"{line} {does} ({clause}), and {shown(operand)} holds {holds}, so the "
        f"line is refused. {move}"
    )
    return ValueError(msg)


def refusal(  # noqa: PLR0913 -- one parameter per part of the sentence a refusal says
    *,
    line: str,
    role: str,
    operand: OpNode | str,
    fill: pl.DataType,
    beside: str,
    receiver: pl.DataType,
    move: str,
    keeps_receiver_type: bool = False,
) -> TypeError:
    """Return the refusal for a value of one kind written where another stood.

    The sentence names the line, the operand as written, both kinds, the
    conversion that would have happened, and the move -- the one the line's
    own site knows best, so each site passes it. ``beside`` names what the
    operand meets: "the value it fills", "the other branch".
    """
    if kind_of(fill) == kind_of(receiver) and keeps_receiver_type:
        happens = (
            f"{line} keeps the column's own type, so it would be cut down to "
            f"{describe(receiver)} to fit"
        )
    else:
        happens = (
            "Polars would make the two fit by converting one into the other's type"
        )
    msg = (
        f"{line}: its {role} -- {shown(operand)} -- is {describe(fill)}, and "
        f"{beside} is {describe(receiver)}. {happens}, a "
        "conversion the formula never wrote, so the line is refused. "
        f"{move}"
    )
    return TypeError(msg)
