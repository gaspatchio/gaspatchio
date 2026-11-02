# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the ten plain maths a projection is written with.

``af.exposure.abs()``, ``(1 + af.rate).log()``, ``af.variance.sqrt()`` --
each answers one value at a time, takes nothing but the value, and reads
in a formula exactly as it reads in a textbook. They reached the record as
engine fragments until now, for no reason but that nobody wrote the
lowering, and a fragment anywhere in a tree takes every column downstream
of it out of the portable subset.

**Three are exact and seven are not.** ``abs``, ``sign`` and
``round_sig_figs`` are decided by the value's own digits: any two engines
that agree on the input agree on the output, bit for bit -- for
``round_sig_figs`` of a double, over the magnitudes its fifteen-digit
reading is taken exactly (:func:`sig_figs_window`). ``cbrt``,
``exp``, ``log``, ``log10``, ``log1p``, ``norm_cdf`` and ``sqrt`` are
transcendental functions of a binary float, and two libraries computing one
of them correctly may still differ in the last place. The specification
states a relative tolerance for those seven (11.1.12) rather than pretending to a
bitwise contract no implementation can hold; ``sqrt`` is the exception
that could hold one -- IEEE 754 requires it correctly rounded -- and it
carries the family's tolerance anyway, because a consumer checking a
column has no way to know which function produced it.

**``log`` is the natural logarithm and nothing else.** Polars' method
takes a base, defaulting to *e*, and a call that names one is left where
it was: the vocabulary has an identifier for the logarithm an actuary
writes bare and no identifier for "the logarithm to a base carried as an
operand". Recording the default base as the literal 2.718281828459045
would be worse than declining -- it puts a truncated double in a document
whose whole purpose is that two producers writing one formula publish one
digest, and it makes ``ln`` unreproducible for any consumer that computes
a change of base rather than calling its own ``ln``. ``log10`` is its own
identifier for the same reason: it is a function an engine has, not a
division by a written-down constant.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import TYPE_CHECKING, Final, cast

import polars as pl

from gaspatchio._dtypes import I64_MAX, I64_MIN
from gaspatchio._semantic.ir import Col
from gaspatchio._semantic.operations import (
    NORM_CDF_OPERATION,
    PLAIN_MATH_OPERATIONS,
    ROUND_SIG_FIGS_OPERATION,
)
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.once import read_once
from gaspatchio.frame.lowering._polars.validation import (
    ABSOLUTE_VALUE_PAST_I64_RULE,
    WIDE_ABSOLUTE_VALUE_RULE,
    WIDE_CARRY_RULE,
    WIDE_SIG_FIGS_RULE,
    require_valid_rows,
    sig_figs_past_i64_refusal,
    tagged_refusal,
)
from gaspatchio.frame.lowering.polars import (
    LoweringError,
    a_flag_read_as_a_number,
    lower_arg_read_as_i64,
    register_elementwise,
    register_lowering,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext

_ABS = "abs"

for _operation in PLAIN_MATH_OPERATIONS:
    if _operation not in (ROUND_SIG_FIGS_OPERATION, NORM_CDF_OPERATION) and (
        _operation.identifier != _ABS
    ):
        register_elementwise(_operation.identifier, reads_a_number=True)


@register_lowering(_ABS)
def _lower_abs(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Drop the sign, one value at a time, on the shape the tree resolved.

    The one of the ten that can wrap: a signed integer's least value has no
    absolute value in its own width, and an ``Int128`` column answered
    ``abs(-2**127)`` as ``-2**127``. So a signed operand wider than ``i64``
    is read as the ``Int64`` its values fit, and refused by name where one
    does not, as arithmetic is (section 10). An unsigned one is its own
    absolute value and keeps its width. The least ``i64``, ``-2**63``, has no
    absolute value in an ``i64`` either -- ``abs`` answered ``-2**63`` -- so
    a policy holding it is refused by name rather than wrapped.
    """
    value_expr, shape = lower_arg_read_as_i64(
        node.args[0], ctx, rule=WIDE_ABSOLUTE_VALUE_RULE, signed_only=True
    )
    value_expr = a_flag_read_as_a_number(
        node.args[0], value_expr, shape, ctx, call=f"{node.name}()"
    )
    absolute = (
        value_expr.list.eval(pl.element().abs())
        if shape == "list"
        else value_expr.abs()
    )
    dtype = None if ctx is None else ctx.dtype_of_expr(value_expr)
    element = dtype.inner if isinstance(dtype, pl.List) else dtype
    if element != pl.Int64:
        return absolute
    least = value_expr.list.min() if shape == "list" else value_expr
    column = node.args[0].name if isinstance(node.args[0], Col) else None
    refused = require_valid_rows(
        (least != I64_MIN).fill_null(value=True),
        message=tagged_refusal(ABSOLUTE_VALUE_PAST_I64_RULE, column),
    )
    return pl.when(refused == 0).then(absolute)


@register_lowering(ROUND_SIG_FIGS_OPERATION.identifier)
def _lower_round_sig_figs(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Keep the leading digits the call names and zero the rest.

    Significant figures are not decimal places: three of them leave
    1234.567 as 1230.0 and 0.001234567 as 0.001234, so the count is read
    back off the record rather than being a step size a reader could
    mistake for ``round``'s.
    """
    digits = int(cast("int", dict(node.attrs)["digits"]))
    value_expr, shape = lower_arg_read_as_i64(
        node.args[0], ctx, rule=WIDE_SIG_FIGS_RULE
    )
    value_expr = a_flag_read_as_a_number(
        node.args[0], value_expr, shape, ctx, call=f"{node.name}()"
    )
    element = typed_element(node, value_expr, ctx)
    if element == pl.Int64:
        column = node.args[0].name if isinstance(node.args[0], Col) else None
        return _whole_numbers_to_sig_figs(value_expr, shape, digits, column)
    if element in (pl.Float64, pl.Float32):
        return in_double_precision(
            value_expr, shape, element, lambda x: _doubles_to_sig_figs(x, digits)
        )
    if shape == "list":
        return value_expr.list.eval(pl.element().round_sig_figs(digits))
    return value_expr.round_sig_figs(digits)


def typed_element(
    node: Call, value: pl.Expr, ctx: LoweringContext | None
) -> pl.DataType:
    """Return a rounded value's type, per policy or per period, or refuse by name.

    Rounding a double reads its fifteen-digit decimal and rounding a whole
    number keeps every digit, and the two are different arithmetic: an
    operand whose type the frame cannot state would be rounded by neither
    rule, so it is refused here rather than handed to Polars' own.
    """
    dtype = None if ctx is None else ctx.dtype_of_expr(value)
    if dtype is None:
        reason = (
            "the type of the value it rounds cannot be read, and a double is "
            "rounded by its fifteen-digit reading while a whole number keeps "
            "every digit, so neither rule can be chosen. Write the line on a "
            "column of an ActuarialFrame, where the type is known"
        )
        raise LoweringError(node, reason)
    return dtype.inner if isinstance(dtype, pl.List) else dtype  # type: ignore[return-value]


def in_double_precision(
    value: pl.Expr,
    shape: str,
    element: pl.DataType,
    rounded: Callable[[pl.Expr], pl.Expr],
) -> pl.Expr:
    """Round a double, or a single-precision value carried to one, one at a time.

    A ``Float32`` value is carried to ``Float64`` -- exact, every single is a
    double -- rounded by the double's rule, and handed back in its own width,
    as ``excel.round`` hands one back. Per period each row's list is rounded
    element by element.
    """

    def one(x: pl.Expr) -> pl.Expr:
        if element == pl.Float32:
            return rounded(x.cast(pl.Float64)).cast(pl.Float32)
        return rounded(x)

    if shape == "list":
        # A policy with no run is handed to the evaluation as an empty one and
        # given its null back after: a run that arithmetic left null --
        # ``(af.pols * af.prem)`` with one side absent -- carries values under
        # its null that Polars' evaluation read, and significant figures over
        # it panicked the in-memory engine ("expected `List`, got `f64` for
        # series with name `v`"). The run is read once (:func:`read_once`).
        def each(run: pl.Expr) -> pl.Expr:
            absent = run.is_null()
            present = pl.when(absent).then(pl.lit([], dtype=pl.List(element)))
            rounded = present.otherwise(run).list.eval(one(pl.element()))
            return pl.when(absent).then(None).otherwise(rounded)

        return read_once(value, answer=each)
    return one(value)


def _whole_numbers_to_sig_figs(
    value: pl.Expr, shape: str, digits: int, column: str | None
) -> pl.Expr:
    """Keep a whole number's leading figures in whole-number arithmetic.

    Polars rounds significant figures through a double and casts back, so
    a whole number came back wrong well inside the range a double names:
    781,098 to one figure was 799,999 and 8.5e15 was 8,999,999,999,999,999.
    The figures are counted and the rest cut off in ``Int64`` instead, a tie
    going away from zero (11.1.12), so the answer is exact; one that rounds
    up past ``i64`` is refused by name rather than wrapped.

    The value is read once, as a field of one struct, and every step reads
    the field: the figures are counted against eighteen powers of ten, so an
    expression that wrote the value out at each read repeated it a few
    hundred times, and a call over another's answer -- the total of rounded
    components, rounded -- multiplied that at every level until the plan
    reached tens of megabytes and never answered.
    """
    message = sig_figs_past_i64_refusal(column)
    rounded, fits = _sig_figs_exactly(pl.element(), digits)

    def per_period(run: pl.Expr) -> pl.Expr:
        every = run.list.eval(fits).list.all().fill_null(value=True)
        return run.list.eval(rounded) + require_valid_rows(every, message=message)

    def per_policy(one: pl.Expr) -> pl.Expr:
        kept, held = _sig_figs_exactly(one, digits)
        return kept + require_valid_rows(held, message=message)

    return read_once(value, answer=per_period if shape == "list" else per_policy)


def _doubles_to_sig_figs(x: pl.Expr, digits: int) -> pl.Expr:
    """Keep a double's leading figures as a spreadsheet reads them.

    Inside :func:`sig_figs_window` the answer is exact (11.1.12). Outside it
    -- below ``10**(digits - 23)``, or from ``10**37`` -- Polars' own
    ``round_sig_figs`` answers, which scales in binary64 and may sit a few
    units in the last place from the fifteen-digit reading, or on the other
    side of a half a few units from one. A floating-point residue where
    nought was meant (3e-24) rounds rather than stopping the run.
    """

    def chosen(value: pl.Expr) -> pl.Expr:
        answer, inside = _decimal_sig_figs(value, digits)
        return pl.when(inside).then(answer).otherwise(value.round_sig_figs(digits))

    return read_once(x, answer=chosen)


def _sig_figs_exactly(x: pl.Expr, digits: int) -> tuple[pl.Expr, pl.Expr]:
    """Return ``x`` kept to ``digits`` figures, and whether the answer is an ``i64``.

    The magnitude is read as ``2**63 - 1`` for the least ``i64``, whose own
    has no ``i64``: the two differ only in a last digit no rounding of them
    turns on. ``x`` is read once, and each step after it is a field of one
    struct, so the expression grows with the steps and not with how often
    each reads the one before.
    """
    stage = pl.struct(x.alias("x"))
    stage = stage.struct.with_fields(
        pl.when(pl.field("x") == I64_MIN)
        .then(pl.lit(I64_MAX, dtype=pl.Int64))
        .otherwise(pl.field("x").abs())
        .alias("magnitude")
    )
    figures = 1 + pl.sum_horizontal(
        [
            (pl.field("magnitude") >= pl.lit(10**place, dtype=pl.Int64)).cast(pl.Int64)
            for place in range(1, 19)
        ]
    )
    stage = stage.struct.with_fields(
        (figures - digits).clip(lower_bound=0).alias("cut")
    )
    stage = stage.struct.with_fields(
        pl.lit(10, dtype=pl.Int64).pow(pl.field("cut").cast(pl.UInt32)).alias("step")
    )
    stage = stage.struct.with_fields(
        (
            pl.field("magnitude") // pl.field("step")
            + (2 * (pl.field("magnitude") % pl.field("step")) >= pl.field("step")).cast(
                pl.Int64
            )
        ).alias("kept")
    )
    stage = stage.struct.with_fields(
        (pl.field("kept") <= pl.lit(I64_MAX, dtype=pl.Int64) // pl.field("step"))
        .fill_null(value=True)
        .alias("fits")
    )
    whole = (
        pl.when(pl.field("fits"))
        .then(pl.field("kept") * pl.field("step"))
        .otherwise(pl.lit(0, dtype=pl.Int64))
    )
    stage = stage.struct.with_fields(
        pl.when(pl.field("cut") == 0)
        .then(pl.field("x"))
        .when(pl.field("x") < 0)
        .then(-whole)
        .otherwise(whole)
        .alias("rounded")
    )
    return stage.struct.field("rounded"), stage.struct.field("fits")


# A double is exactly a sum of two halves of at most 26 bits each, cut by
# multiplying by this and subtracting (Veltkamp's split).
_SPLIT: Final[float] = 2.0**27 + 1.0
# The powers of ten a double holds exactly: 10**k for |k| <= 22.
_EXACT_SCALE: Final[int] = 22
_TENS: Final[tuple[float, ...]] = tuple(float(10**k) for k in range(_EXACT_SCALE + 1))
# The significant figures a spreadsheet holds of a double (11.1.35).
_HELD_FIGURES: Final[int] = 15
# The scaled value's figures, read as a whole number: 10**14 to below 10**15.
_FIFTEEN_FIGURES: Final[float] = 1e15
# How far below its logarithm the decimal exponent is guessed, so the guess is
# never above the true one and at most one below it.
_GUESS_BELOW: Final[float] = 2.0**-30
# The magnitude from which no scaling holds the figures exactly.
_TOP_EXPONENT: Final[int] = 37
# Five to the k for every scaling going up, as the double nearest it and the
# whole number it misses by, so the two add to it exactly (5**37 < 2**86).
_FIVES: Final[tuple[int, ...]] = tuple(range(_TOP_EXPONENT + 1))
_FIVE_HIGH: Final[tuple[float, ...]] = tuple(float(5**k) for k in _FIVES)
_FIVE_LOW: Final[tuple[float, ...]] = tuple(
    float(5**k - int(float(5**k))) for k in _FIVES
)


def _least_double_at_least(exponent: int) -> float:
    """Return the least double at or above ``10**exponent``."""
    exact = Fraction(10) ** exponent
    nearest = float(exact)
    return nearest if Fraction(nearest) >= exact else math.nextafter(nearest, math.inf)


def sig_figs_window(digits: int) -> tuple[float, float]:
    """Return the magnitudes, from and below, where ``digits`` figures are exact.

    The figures are read with ``10**k`` for ``k`` up to 37 going up and 22
    coming down, and handed back with one correctly rounded product or
    quotient by a power of ten a double holds: every magnitude from
    ``10**(digits - 23)`` (``10**-8`` at fifteen figures or more) to below
    ``10**37``. Each bound is a double, compared exactly.
    """
    figures = min(digits, _HELD_FIGURES)
    return (
        _least_double_at_least(figures - 1 - _EXACT_SCALE),
        _least_double_at_least(_TOP_EXPONENT),
    )


def _table(index: pl.Expr, values: tuple[float, ...]) -> pl.Expr:
    """Read ``values[index]`` one value at a time."""
    return index.replace_strict(
        list(range(len(values))), list(values), return_dtype=pl.Float64
    )


def _high(value: pl.Expr) -> pl.Expr:
    """Return the high half of a double: at most 26 bits (Veltkamp's split)."""
    cut = value * _SPLIT
    return cut - (cut - value)


def _product_error(a: str, b: str, product: str) -> pl.Expr:
    """Return ``a * b - product`` exactly, ``product`` the rounded ``a * b``.

    Dekker's product over the fields ``{a}_hi`` and ``{b}_hi``: each operand
    is cut into halves whose products a double holds, and the halves'
    products are taken off in an order that loses nothing.
    """
    ah, bh = pl.field(f"{a}_hi"), pl.field(f"{b}_hi")
    al, bl = pl.field(a) - ah, pl.field(b) - bh
    return ((ah * bh - pl.field(product)) + ah * bl + al * bh) + al * bl


def _two_sum(stage: pl.Expr, a: str, b: str, total: str, error: str) -> pl.Expr:
    """Add ``total``, the rounded ``a + b``, and ``error``, what it lost (Knuth)."""
    stage = stage.struct.with_fields((pl.field(a) + pl.field(b)).alias(total))
    b_part = pl.field(total) - pl.field(a)
    a_part = pl.field(total) - b_part
    lost = (pl.field(a) - a_part) + (pl.field(b) - b_part)
    return stage.struct.with_fields(lost.alias(error))


def _sign_of_sum(stage: pl.Expr, terms: tuple[str, str, str, str]) -> pl.Expr:
    """Add ``sign``: the exact sign of the four terms' sum, nought where it is nought.

    Shewchuk's growing expansion: each term is added to the expansion so far
    by exact two-sums, which leaves components whose bits do not overlap, so
    the largest one that is not nought outweighs all the others together.
    """
    one, two, three, four = terms
    stage = _two_sum(stage, two, one, "q1", "h1")
    stage = _two_sum(stage, three, "h1", "q2", "g1")
    stage = _two_sum(stage, "q2", "q1", "q3", "g2")
    stage = _two_sum(stage, four, "g1", "r1", "f1")
    stage = _two_sum(stage, "r1", "g2", "r2", "f2")
    stage = _two_sum(stage, "r2", "q3", "r3", "f3")
    largest = (
        pl.when(pl.field("r3") != 0)
        .then(pl.field("r3"))
        .when(pl.field("f3") != 0)
        .then(pl.field("f3"))
        .when(pl.field("f2") != 0)
        .then(pl.field("f2"))
        .otherwise(pl.field("f1"))
    )
    return stage.struct.with_fields(largest.sign().alias("sign"))


def _decimal_sig_figs(x: pl.Expr, digits: int) -> tuple[pl.Expr, pl.Expr]:
    """Return a double kept to ``digits`` figures, and where that is exact.

    The figures are a spreadsheet's (11.1.35): the value is read as its
    fifteen-significant-digit decimal, a sixteenth digit of 5 or more going
    away from zero, that decimal is rounded to ``digits`` figures, a half
    going away from zero (11.1.12), and the answer is the double nearest the
    result. 0.15 to one figure is 0.2, 2.675 to three is 2.68, and 781098.0
    to one is 800000.0.

    ``x * 10**k`` is scaled so its fifteen figures are its whole part, and
    carried exactly. Going up it is ``x * 2**k``, exact, times ``5**k`` held
    as the double nearest it plus what that misses by: two Dekker products.
    Coming down it is one correctly rounded quotient, and the product of the
    quotient back is what tells which side of it the value lies. Whether the
    scaled value reaches the half above its whole part is then the exact sign
    of four doubles' sum. The rest is whole-number arithmetic, and the answer
    one correctly rounded product or quotient of the kept figures by a power
    of ten a double holds. That holds over :func:`sig_figs_window`; the second
    expression is false outside it, where the lowering takes Polars' own. The
    steps are fields of one struct, so each is computed once however often a
    later one reads it.
    """
    figures = min(digits, _HELD_FIGURES)
    low, high = sig_figs_window(digits)
    m = pl.field("x").abs()
    usable = m.is_finite() & (m > 0)
    stage = pl.struct(x.alias("x"))
    stage = stage.struct.with_fields(
        usable.alias("usable"),
        (~usable | ((m >= low) & (m < high))).fill_null(value=True).alias("inside"),
        # A value outside the window is carried as 1.0, so no step overflows on
        # it; Polars' own route answers it.
        pl.when(usable & (m >= low) & (m < high)).then(m).otherwise(1.0).alias("v"),
    )
    guess = (pl.field("v").log10() - _GUESS_BELOW).floor().cast(pl.Int64)
    stage = stage.struct.with_fields((_HELD_FIGURES - 1 - guess).alias("k"))
    k = pl.field("k")
    upward = k >= 0
    up = k.clip(lower_bound=0)
    two = pl.lit(2, dtype=pl.Int64).pow(up.cast(pl.UInt32)).cast(pl.Float64)
    stage = stage.struct.with_fields(
        (pl.field("v") * two).alias("big"),
        _table(up, _FIVE_HIGH).alias("five"),
        _table(up, _FIVE_LOW).alias("rest"),
        _table((-k).clip(lower_bound=0), _TENS).alias("down"),
    )
    stage = stage.struct.with_fields(
        (pl.field("v") / pl.field("down")).alias("quotient")
    )
    left = pl.when(upward).then(pl.field("big")).otherwise(pl.field("quotient"))
    right = pl.when(upward).then(pl.field("five")).otherwise(pl.field("down"))
    stage = stage.struct.with_fields(left.alias("l"), right.alias("r"))
    stage = stage.struct.with_fields(
        (pl.field("l") * pl.field("r")).alias("p"),
        (pl.field("big") * pl.field("rest")).alias("c"),
        _high(pl.field("l")).alias("l_hi"),
        _high(pl.field("r")).alias("r_hi"),
        _high(pl.field("big")).alias("big_hi"),
        _high(pl.field("rest")).alias("rest_hi"),
    )
    lead = pl.when(upward).then(pl.field("p")).otherwise(pl.field("quotient"))
    unit = pl.when(lead >= _FIFTEEN_FIGURES).then(10.0).otherwise(1.0)
    whole = (lead / unit).floor() * unit
    stage = stage.struct.with_fields(
        _product_error("l", "r", "p").alias("p_err"),
        _product_error("big", "rest", "c").alias("c_err"),
        unit.alias("unit"),
        whole.alias("whole"),
        (whole + unit * 0.5).alias("half"),
        lead.alias("lead"),
    )
    stage = stage.struct.with_fields(
        (pl.field("p") - pl.field("half")).alias("t1"),
    )
    stage = _sign_of_sum(stage, ("t1", "p_err", "c", "c_err"))
    # Coming down the quotient is correctly rounded, so it is on the half's
    # side unless it is the half, where the remainder's sign decides.
    remainder = pl.field("v") - pl.field("p")
    down_sign = (
        pl.when(pl.field("lead") != pl.field("half"))
        .then((pl.field("lead") - pl.field("half")).sign())
        .otherwise((remainder - pl.field("p_err")).sign())
    )
    reached = pl.when(upward).then(pl.field("sign")).otherwise(down_sign) >= 0
    stage = stage.struct.with_fields(
        (pl.field("whole") + reached.cast(pl.Float64) * pl.field("unit"))
        .cast(pl.Int64)
        .alias("held")
    )
    sixteen = pl.field("held") >= pl.lit(10**_HELD_FIGURES, dtype=pl.Int64)
    cut = _HELD_FIGURES + sixteen.cast(pl.Int64) - figures
    stage = stage.struct.with_fields(
        pl.lit(10, dtype=pl.Int64).pow(cut.cast(pl.UInt32)).alias("step"),
        (cut - k).alias("place"),
    )
    rest = pl.field("held") % pl.field("step")
    stage = stage.struct.with_fields(
        (
            pl.field("held") // pl.field("step")
            + (2 * rest >= pl.field("step")).cast(pl.Int64)
        ).alias("kept"),
    )
    place = pl.field("place")
    beyond = (place - _EXACT_SCALE).clip(lower_bound=0)
    whole_kept = pl.field("kept") * pl.lit(10, dtype=pl.Int64).pow(
        beyond.cast(pl.UInt32)
    )
    answer = (
        pl.when(place >= 0)
        .then(whole_kept.cast(pl.Float64) * _table(place.clip(0, _EXACT_SCALE), _TENS))
        .otherwise(
            pl.field("kept").cast(pl.Float64)
            / _table((-place).clip(0, _EXACT_SCALE), _TENS)
        )
    )
    signed = pl.when(pl.field("x") < 0).then(-answer).otherwise(answer)
    stage = stage.struct.with_fields(
        pl.when(pl.field("usable"))
        .then(signed)
        .otherwise(pl.field("x"))
        .alias("answer")
    )
    return stage.struct.field("answer"), stage.struct.field("inside")


@register_lowering(NORM_CDF_OPERATION.identifier)
def _lower_norm_cdf(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Evaluate the standard normal distribution function in the native kernel.

    Polars has no ``erf`` or ``erfc`` to compose Φ from, and a composite of
    core operations is a deep expression tree whose cost grows faster than
    the book. The kernel answers a per-policy column and a per-period one
    alike, element by element, and is elementwise, so the streaming engine
    keeps running and the shape needs no branch here.
    """
    from gaspatchio.frame.lowering._polars.plugins import (  # noqa: PLC0415
        norm_cdf,
    )

    value_expr, shape = lower_arg_read_as_i64(node.args[0], ctx, rule=WIDE_CARRY_RULE)
    # The kernel reads doubles and whole numbers; an engine's fixed-point
    # decimal it refuses, so the line is refused before it runs.
    kinds.refuse_unless_a_number(
        line="norm_cdf()",
        operand=node.args[0],
        dtype=kinds.operand_dtype(node.args[0], value_expr, ctx),
        decimal=True,
    )
    return norm_cdf(
        a_flag_read_as_a_number(
            node.args[0], value_expr, shape, ctx, call=f"{node.name}()"
        )
    )
