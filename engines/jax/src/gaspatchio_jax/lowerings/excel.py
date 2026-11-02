# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The four spreadsheet functions an actuarial model reaches for by name.

``excel.round`` is the rule a spreadsheet has and a language does not, in
two halves. A half goes **away from zero**, so 2.5 is 3 and -2.5 is -3, where
the banker's rounding most host languages default to answers 2 and -2. And
what is rounded is the value the spreadsheet holds -- the operand's
**fifteen significant digits** -- not the double: ``68049.31499999999…`` is
``68049.3150000000`` at fifteen digits, a half, and rounds to ``68049.32``.
Both differences show up in the last place of a reserve and nowhere a test
would look, which is why the arithmetic is written out here rather than
delegated. How the fifteen digits are decided without leaving binary64 is
:func:`_steps`'s account.

``excel.yearfrac`` is five day-count bases under one identifier, and 11.1.34
states each one as a rule rather than as a name: the two 30/360 conventions
differ in which endpoint's 31 becomes a 30 and under what condition, and
basis 1 is the spreadsheet's own actual/actual and specifically **not** a
schedule's ISDA year splitting. Like the spreadsheet's YEARFRAC, the answer
does not depend on the order the two days are given in: the earlier is the
start, and no answer is negative.

``excel.pv`` is the annuity formula with the timing flag the spreadsheet
carries, and ``excel.irr`` the rate that sets a stream's value to nothing. The
solver here is bisection over the clause's own bracket, which is what the
published vectors' reader uses: an engine that matched a producer's Newton
iteration would be agreeing with an implementation rather than with a root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import jax.numpy as jnp
from jax import lax

from gaspatchio_jax.capability import (
    DATE,
    EITHER_SHAPE,
    PER_PERIOD,
    PER_POLICY,
    Capability,
)
from gaspatchio_jax.checks import flag
from gaspatchio_jax.horizon import aligned, mask_to_neutral, periods_of
from gaspatchio_jax.ieee import apart, divided, multiplied
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.lowerings.dates import (
    civil_from_days,
    days_from_civil,
    is_leap,
    last_day_of,
)
from gaspatchio_jax.lowerings.reduction import running
from gaspatchio_jax.typed import JNP_OF, DomainRefused, Value, carried_to

if TYPE_CHECKING:
    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_ROUND_AND_PV: Final = "11.1.35"
_YEARFRAC: Final = "11.1.34"
_IRR: Final = "11.1.36"

# 11.1.35's own bounds on the rounding.
_DIGIT_FLOOR: Final = -10
_DIGIT_CEILING: Final = 10
_SCALED_LIMIT: Final = 2.0**52

# The significant digits a spreadsheet holds, and the scaled magnitudes where
# they stop being finer than the step (10^14) and become coarser (10^15).
_HELD_DIGITS: Final = 15
_FINER: Final = 1e14
_COARSER: Final = 1e15

# The two exact tables the decision reads: ten to the k, and half of ten to
# the minus k, for k up to 22, every one an exact double or a correctly
# rounded one.
_POWERS: Final = tuple(10.0**k for k in range(23))
_HALF_UNITS: Final = tuple(0.5 / 10.0**k for k in range(23))

# A double's mantissa is 53 bits; the decision reads it as a whole number.
_MANTISSA_BITS: Final = 53

# How near the fifteen-digit boundary binary64 declines to decide, as a share
# of the boundary's own width. The arithmetic carries at most a few units of
# 2^-53 there; 2^-48 is clear of them.
_UNDECIDED: Final = 2.0**-48

# Past this a whole-number comparison would leave int64.
_WHOLE_LIMIT: Final = 2.0**62

# 11.1.35's own operand domain for the annuity.
_PV_OPERANDS: Final[frozenset[Carrier]] = frozenset({"i64", "f64"})

# 11.1.34's five bases, and the text aliases it matches without case.
_BASIS_OF: Final[dict[str, int]] = {
    "us_nasd_30_360": 0,
    "30/360": 0,
    "act/act": 1,
    "actual/actual": 1,
    "actual/360": 2,
    "actual_360": 2,
    "act/360": 2,
    "actual/365": 3,
    "actual_365": 3,
    "act/365": 3,
    "european_30_360": 4,
    "30e/360": 4,
}
_BASES: Final[tuple[str, ...]] = tuple(
    [str(one) for one in range(5)] + sorted(_BASIS_OF)
)

# February, for the two 30/360 conventions' own adjustments.
_FEBRUARY: Final = 2

# Days in the two kinds of year, and the two 30/360 denominators.
_DAYS_360: Final = 360.0
_DAYS_365: Final = 365.0
_DAYS_366: Final = 366.0

# 11.1.36's bracket and the bound on the solver's work. Sixty halvings of a
# bracket 1.9 wide leave an interval under 2e-18, which is inside the clause's
# own 1e-6 rate budget by twelve orders of magnitude and is a fixed number of
# steps rather than a convergence test.
_IRR_LOW: Final = -0.9
_IRR_HIGH: Final = 1.0
_IRR_STEPS: Final = 60


def _named(carrier: str, like: Value) -> str:
    """Return the type name an answer stands under, in its operand's shape.

    A per-period answer's type is ``list[…]`` and a per-policy one's is the
    bare name. The two are one line apart and the value's own ``dtype`` is
    read where a nested call has no record to declare it.
    """
    return f"list[{carrier}]" if like.shape == "list" else carrier


@register(
    Capability(
        identifier="excel.round",
        arity=(1,),
        # 11.1.35 states finite Float64 cells: a number, not a truth value,
        # and the producer refuses a Boolean here too.
        carriers=(_PV_OPERANDS,),
        answers_carrier="f64",
        checks=("excel.round.scale", "excel.round.sixteenth"),
        attr_bounds={"num_digits": (_DIGIT_FLOOR, _DIGIT_CEILING)},
        attrs_required=("num_digits",),
        clause=_ROUND_AND_PV,
        note=(
            "the value's fifteen significant digits are rounded, as a "
            "spreadsheet holds them, and a half goes away from zero, which is "
            "not the host language's rule"
        ),
    )
)
def _round(call: Call, ctx: LoweringContext) -> Value:
    """Return the fifteen-digit value at the nearest step, a half going away."""
    value = carried_to(ctx.lower(call.args[0]), "f64", clause=_ROUND_AND_PV)
    written = dict(call.attrs)["num_digits"]
    digits = int(written) if isinstance(written, (int, float)) else 0
    magnitude = jnp.abs(value.array)
    # Each division through gaspatchio_jax.ieee, because XLA turns a division
    # by a constant into a multiplication by its reciprocal, and ``x * 0.1``
    # is not ``x / 10``: the steps a value rounds to would come back a unit of
    # their last place off. (An optimization barrier on the power hid the
    # constant too, but only until the compiler expanded it, which on jax
    # 0.4.38's CPU pipeline is straight after the first simplification.)
    power = _POWERS[abs(digits)]
    scaled = magnitude * power if digits >= 0 else divided(magnitude, power)
    flag("excel.round.scale", scaled >= _SCALED_LIMIT)
    steps, undecided = _steps(magnitude, scaled, digits)
    flag("excel.round.sixteenth", undecided)
    rounded = divided(steps, power) if digits >= 0 else steps * power
    answer = jnp.copysign(rounded, value.array)
    return Value(answer, "f64", value.shape, _named("f64", value), value.horizon)


def _whole(value: jax.Array) -> tuple[jax.Array, jax.Array]:
    """Return a double as its mantissa, a whole number, and the power of two."""
    fraction, exponent = jnp.frexp(value)
    mantissa = (fraction * 2.0**_MANTISSA_BITS).astype(jnp.int64)
    return mantissa, exponent.astype(jnp.int64) - _MANTISSA_BITS


def _residual(magnitude: jax.Array, scaled: jax.Array, digits: int) -> jax.Array:
    """Return what the scaling's one rounding lost: exact scaled minus ``scaled``.

    Ten to the k is five to the k times two to the k, and five to the tenth
    fits in 24 bits, so the exact product of a mantissa and five to the k
    differs from the rounded one by a whole number of the product's last unit
    that fits easily in int64. That difference is computed in int64 directly:
    the two products wrap past 2^63, but their difference is small, and a
    wrapped subtraction of two wrapped products is the exact one when the true
    answer is in range. A product is exact, so its residual is too; a quotient
    is a whole-number difference divided once by five to the k.
    """
    count = abs(digits)
    five = jnp.int64(5**count)
    mantissa, exponent = _whole(magnitude)
    held, held_exponent = _whole(scaled)
    if digits >= 0:
        shift = held_exponent - exponent - count
        shifted = (shift >= 0) & (shift < _MANTISSA_BITS + 10)
        left = jnp.left_shift(held, jnp.where(shifted, shift, 0))
        lost = jnp.where(shifted, mantissa * five - left, 0)
        return jnp.ldexp(jnp.asarray(lost, dtype=jnp.float64), exponent + count)
    shift = exponent - held_exponent - count
    shifted = (shift >= 0) & (shift < _MANTISSA_BITS + 10)
    left = jnp.left_shift(mantissa, jnp.where(shifted, shift, 0))
    lost = jnp.where(shifted, left - held * five, 0)
    return jnp.ldexp(
        divided(jnp.asarray(lost, dtype=jnp.float64), float(5**count)), held_exponent
    )


def _steps(
    magnitude: jax.Array, scaled: jax.Array, digits: int
) -> tuple[jax.Array, jax.Array]:
    """Return the steps the fifteen-digit value rounds to, and the cells undecided.

    Three regions of the scaled magnitude ``y = |x| * 10^digits``:

    * **Below 10^14** the fifteen digits are finer than the step, and the
      answer goes up exactly when ``y`` is at or past ``m + 0.5 - w``: ``m``
      the whole steps below it and ``w`` half a unit of the fifteenth digit.
      At or past that point the fifteen digits are the half or beyond it
      (a sixteenth digit of 5 goes away); short of it they are below the half.
      ``y`` is one rounding from exact, and :func:`_residual` restores what it
      lost, so the comparison is made on the exact value to within a few units
      of 2^-53 of ``w``. Only where that boundary is itself a double -- a
      value of 10^14 or more whose sixteenth digit is an exact 5, at a
      negative ``digits`` -- could the few units decide, and there it is
      compared in whole numbers instead.
    * **From 10^14 to 10^15** the fifteenth digit is the step, so the answer
      is ``y`` itself at the nearest whole, a half going away; ``y``'s own
      fraction decides unless it is exactly a half, where the residual's sign
      does.
    * **From 10^15** the fifteenth digit is ten steps, and the same holds of
      ``y`` at the nearest ten.

    A cell is undecided only where the exact value is within those few units
    of the boundary and the boundary is not a double: values a published
    corpus constructed to sit there, and no model's. Such a cell is flagged
    rather than answered.
    """
    count = abs(digits)
    lost = _residual(magnitude, scaled, digits)
    whole = jnp.floor(scaled)
    past_half = scaled - whole - 0.5
    digit = jnp.floor(jnp.log10(jnp.where(scaled > 0.0, scaled, 1.0)))
    digit = jnp.clip(digit, -1, _HELD_DIGITS - 2).astype(jnp.int64)
    half_unit = jnp.asarray(_HALF_UNITS)[_HELD_DIGITS - 1 - digit]
    margin = (past_half + lost) + half_unit
    decided = jnp.abs(margin) > _UNDECIDED * half_unit
    up = margin > 0.0
    if digits < 0:
        # The boundary is a double here: compare against it directly.
        leading = digit + count
        half_step = (
            jnp.asarray(_HALF_UNITS)[0]
            * jnp.asarray(_POWERS)[
                jnp.clip(leading - (_HELD_DIGITS - 1), 0, len(_POWERS) - 1)
            ]
        )
        tie = (whole + 0.5) * _POWERS[count]
        exact = (leading >= _HELD_DIGITS - 1) & (tie < _SCALED_LIMIT)
        up = jnp.where(exact, magnitude >= tie - half_step, up)
        # Past 2^52 every quantity is a whole number: compare in int64.
        integral = (leading >= _HELD_DIGITS) & ~exact & (magnitude < _WHOLE_LIMIT)
        held = jnp.where(integral, magnitude, 0.0).astype(jnp.int64)
        below = jnp.where(integral, whole, 0.0).astype(jnp.int64)
        boundary = (2 * below + 1) * jnp.int64(10**count // 2) - jnp.where(
            integral, half_step, 0.0
        ).astype(jnp.int64)
        up = jnp.where(integral, held >= boundary, up)
        decided = decided | exact | integral
    finer = whole + up
    exactly_half = past_half == 0.0
    at_the_step = whole + ((past_half > 0.0) | (exactly_half & (lost >= 0.0)))
    tens = jnp.fmod(scaled, 10.0)
    past_five = tens - 5.0
    at_ten_steps = (scaled - tens) + 10.0 * (
        (past_five > 0.0) | ((past_five == 0.0) & (lost >= 0.0))
    )
    below_finer = scaled < _FINER
    steps = jnp.where(
        below_finer, finer, jnp.where(scaled < _COARSER, at_the_step, at_ten_steps)
    )
    undecided = below_finer & jnp.isfinite(scaled) & ~decided
    return steps, undecided


@register(
    Capability(
        identifier="excel.pv",
        arity=(3,),
        # 11.1.35 states a finite rate, a nonnegative whole period count and
        # a finite payment: numbers, not truth values.
        carriers=(_PV_OPERANDS, _PV_OPERANDS, _PV_OPERANDS),
        # Each of the three may be held per policy or per period: per-period
        # operands are paired period by period, and one per policy beside them
        # reads as that policy's value in every period (11.1.35, 11.1.18).
        shapes=(EITHER_SHAPE, EITHER_SHAPE, EITHER_SHAPE),
        answers_carrier="f64",
        checks=("excel.pv.periods",),
        clause=_ROUND_AND_PV,
        note="cash paid and value received have opposite signs",
    )
)
def _pv(call: Call, ctx: LoweringContext) -> Value:
    """Return the present value of an annuity, under the stated payment timing.

    Per policy, or per period where any operand is held per period: the
    formula is the same at each cell, the per-period operands paired period by
    period and a per-policy one read as that policy's value in every period.
    """
    rate, periods, payment = (
        carried_to(ctx.lower(argument), "f64", clause=_ROUND_AND_PV)
        for argument in call.args
    )
    attrs = dict(call.attrs)
    future = float(attrs.get("fv") or 0.0)
    timing = float(attrs.get("typ") or 0)
    if timing not in (0.0, 1.0):
        raise DomainRefused(
            what=(
                f"excel.pv is written with typ={attrs.get('typ')!r}, and the "
                "clause states end-of-period payments as 0 and "
                "beginning-of-period as 1"
            ),
            move="write the timing the model means as 0 or 1",
            clause=_ROUND_AND_PV,
        )
    # Two per-period operands on different timelines are refused here, as the
    # reference producer refuses them (11.1.18).
    axis = aligned(rate, periods, payment)
    r, count, paid_each = axis.arrays
    negative = count < 0
    if axis.horizon is not None:
        # Only a policy's own periods: a cell past its horizon is no period.
        negative = negative & axis.horizon.active
    flag("excel.pv.periods", negative)
    # 11.1.35: the discount factor is exp(-n log1p(r)) and the paid-off
    # fraction -expm1(-n log1p(r)), as the reference producer takes them, so
    # neither rounds 1 + r first and the 1e-12 bound holds at every nonzero
    # rate however near nought; the flat form is the answer only at nought.
    # Per period the same holds cell by cell: a nought rate in one period
    # takes the flat form there and nowhere else.
    near_zero = r == 0.0
    safe = jnp.where(near_zero, 1.0, r)
    # Every product is rounded before anything reads it, as the reference
    # producer rounds it (gaspatchio_jax.ieee.multiplied): XLA's CPU backend
    # would otherwise fuse a multiply into the addition after it.
    grown = multiplied(count, jnp.log1p(r))
    factor = jnp.exp(-grown)
    paid_off = -jnp.expm1(-grown)
    # The reference producer's own grouping, ``pmt * ((1 + r*typ)(1 - v^n) / r)``,
    # and its division held apart: gaspatchio_jax.ieee.
    annuity_factor = divided(multiplied(1.0 + multiplied(r, timing), paid_off), safe)
    # Two products and their sum. Each is also held apart under the sum, which
    # varies per period wherever either product does, so a per-policy product
    # beside a per-period one is not hoisted out of the loop over the periods
    # and fused there. The sum is NaN wherever the answer is.
    paid = multiplied(paid_each, annuity_factor)
    left = multiplied(future, factor)
    witness = paid + left
    annuity = -(apart(paid, witness) + apart(left, witness))
    # The flat form's product held apart from its sum too, for the same reason.
    owed = multiplied(paid_each, count)
    flat = -(apart(owed, owed + future) + future)
    answer = jnp.where(near_zero, flat, annuity)
    dtype = "list[f64]" if axis.shape == "list" else "f64"
    return Value(answer, "f64", axis.shape, dtype, axis.horizon)


def _basis(call: Call) -> int:
    """Return the day-count basis one call names, by number or by alias.

    Raises:
        DomainRefused: If the basis is outside the five 11.1.34 states.

    """
    written = dict(call.attrs).get("basis")
    if isinstance(written, int) and not isinstance(written, bool):
        if 0 <= written <= 4:  # noqa: PLR2004 -- the clause's own five
            return written
    elif isinstance(written, str):
        found = _BASIS_OF.get(written.lower())
        if found is not None:
            return found
    raise DomainRefused(
        what=f"excel.yearfrac is written with basis={written!r}, which this "
        "clause does not name",
        move="write one of the five bases, by number or by its stated alias",
        clause=_YEARFRAC,
    )


def _thirty_360(
    start: tuple[jax.Array, jax.Array, jax.Array],
    end: tuple[jax.Array, jax.Array, jax.Array],
) -> jax.Array:
    """Return the 30/360 year fraction of two already-adjusted calendar days."""
    return divided(
        _DAYS_360 * (end[0] - start[0])
        + 30.0 * (end[1] - start[1])
        + (end[2] - start[2]),
        _DAYS_360,
    )


def _us_adjusted(
    start: tuple[jax.Array, jax.Array, jax.Array],
    end: tuple[jax.Array, jax.Array, jax.Array],
) -> tuple[tuple[jax.Array, ...], tuple[jax.Array, ...]]:
    """Return basis 0's adjustments, the spreadsheet's first match of five.

    In order: both days the 31st; the start the 31st; the start the 30th and
    the end the 31st; both February's last day; the start February's last
    day. Only the first that holds is applied, so an end day of 31 becomes 30
    only beside a start day the calendar wrote as 30 or 31 -- a start on
    February's last day leaves it 31.
    """
    start_year, start_month, start_day = start
    end_year, end_month, end_day = end
    start_is_february_end = (start_month == _FEBRUARY) & (
        start_day == last_day_of(start_year, start_month)
    )
    end_is_february_end = (end_month == _FEBRUARY) & (
        end_day == last_day_of(end_year, end_month)
    )
    end_to_thirty = ((end_day == 31) & (start_day >= 30)) | (  # noqa: PLR2004 -- the clause's own days
        start_is_february_end & end_is_february_end
    )
    start_to_thirty = (start_day == 31) | start_is_february_end  # noqa: PLR2004 -- as above
    end_day = jnp.where(end_to_thirty, 30, end_day)
    start_day = jnp.where(start_to_thirty, 30, start_day)
    return (start_year, start_month, start_day), (end_year, end_month, end_day)


def _actual_actual(
    opened: jax.Array,
    closed: jax.Array,
    start: tuple[jax.Array, jax.Array, jax.Array],
    end: tuple[jax.Array, jax.Array, jax.Array],
) -> jax.Array:
    """Return basis 1's year fraction, which is three rules with one denominator.

    The one-year rule holds where the end falls in the next year on or before
    the start's month and day -- the interval *appears* to be a year or less
    -- and not where it is merely 366 days or fewer: 25 September 2020 to
    26 September 2021 is 366 days over the two years' mean length.
    """
    elapsed = (closed - opened).astype(JNP_OF["f64"])
    start_year, start_month, start_day = start
    end_year, end_month, end_day = end
    same_year = start_year == end_year
    appears_a_year = (end_year == start_year + 1) & (
        (end_month < start_month)
        | ((end_month == start_month) & (end_day <= start_day))
    )
    in_year = jnp.where(is_leap(start_year), _DAYS_366, _DAYS_365)
    # A 29 February inside the closed interval, looked for in the two years
    # the interval can touch: within a year it cannot reach a third.
    leap_days = [
        days_from_civil(year, jnp.full_like(year, 2), jnp.full_like(year, 29))
        for year in (start_year, end_year)
    ]
    touches = jnp.zeros(opened.shape, dtype=bool)
    for year, day in zip((start_year, end_year), leap_days, strict=True):
        touches = touches | (is_leap(year) & (day >= opened) & (day <= closed))
    short = jnp.where(touches, _DAYS_366, _DAYS_365)
    spanned = (end_year - start_year + 1).astype(JNP_OF["f64"])
    # Gregorian counts through each endpoint, inclusive. Integer arithmetic
    # counts every leap year, including the century exceptions, in constant work.
    prior = start_year - 1
    leap_years = (end_year // 4 - end_year // 100 + end_year // 400) - (
        prior // 4 - prior // 100 + prior // 400
    )
    mean_year = divided(_DAYS_365 * spanned + leap_years, spanned)
    long_run = divided(elapsed, mean_year)
    short_run = jnp.where(same_year, divided(elapsed, in_year), divided(elapsed, short))
    return jnp.where(same_year | appears_a_year, short_run, long_run)


@register(
    Capability(
        identifier="excel.yearfrac",
        arity=(2,),
        carriers=(DATE, DATE),
        shapes=(EITHER_SHAPE, EITHER_SHAPE),
        answers_carrier="f64",
        attrs={"basis": _BASES},
        # The reference producer refuses an unlisted basis too (11.1.34).
        refused_alike={
            "attr:basis": "write basis as 0 to 4 or one of the aliases 11.1.34 lists"
        },
        # 11.1.34 states the text aliases "matched without case", and the
        # lowering reads them that way; the declaration has to say the same
        # thing or the table claims a form the runtime refuses.
        attrs_folded=("basis",),
        attrs_required=("basis",),
        clause=_YEARFRAC,
        note=(
            "basis 1 is the spreadsheet's own actual/actual and not a "
            "schedule's ISDA year splitting"
        ),
    )
)
def _yearfrac(call: Call, ctx: LoweringContext) -> Value:
    """Return the year fraction between two days on the stated day-count basis."""
    first = ctx.lower(call.args[0])
    second = ctx.lower(call.args[1])
    axis = aligned(first, second)
    opened = jnp.minimum(*axis.arrays)
    closed = jnp.maximum(*axis.arrays)
    basis = _basis(call)
    start = civil_from_days(opened)
    end = civil_from_days(closed)
    elapsed = (closed - opened).astype(JNP_OF["f64"])
    if basis == 2:  # noqa: PLR2004 -- the clause's own basis numbers
        fraction = divided(elapsed, _DAYS_360)
    elif basis == 3:  # noqa: PLR2004 -- as above
        fraction = divided(elapsed, _DAYS_365)
    elif basis == 1:
        fraction = _actual_actual(opened, closed, start, end)
    elif basis == 4:  # noqa: PLR2004 -- as above
        held = tuple(
            (year, month, jnp.where(day == 31, 30, day))  # noqa: PLR2004 -- the clause's own days
            for year, month, day in (start, end)
        )
        fraction = _thirty_360(held[0], held[1])
    else:
        adjusted = _us_adjusted(start, end)
        fraction = _thirty_360(adjusted[0], adjusted[1])  # type: ignore[arg-type]
    return Value(
        fraction,
        "f64",
        axis.shape,
        "list[f64]" if axis.shape == "list" else "f64",
        axis.horizon,
    )


# The move a per-period guess is refused with, by the declaration and by the
# lowering alike: the reference producer's own.
_ONE_GUESS: Final = "write the guess once per policy"


@register(
    Capability(
        identifier="excel.irr",
        arity=(1, 2),
        # 11.1.36's cashflows are list[f64] and its guess a scalar Float64.
        carriers=(_PV_OPERANDS, _PV_OPERANDS),
        shapes=(PER_PERIOD, PER_POLICY),
        # The reference producer refuses a guess held per period too; a run
        # of cashflows held once per policy it answers.
        refused_alike={"shape@1": _ONE_GUESS},
        answers="scalar",
        answers_carrier="f64",
        checks=(
            "excel.irr.bracket",
            "excel.irr.no_sign_change",
            "excel.irr.several_roots",
        ),
        clause=_IRR,
        note=(
            "bisection over the clause's own bracket, which is the published "
            "reader's method and not a producer's iteration"
        ),
    )
)
def _irr(call: Call, ctx: LoweringContext) -> Value:
    """Return the rate at which one regularly spaced stream values to nothing.

    Raises:
        DomainRefused: If a stream is outside the bounded solver domain --
            no sign change, more than one, or a root the clause's bracket
            does not hold. The clause makes each of those a null, and a null
            is a value this engine states no answer over.

    """
    cashflows = carried_to(ctx.lower(call.args[0]), "f64", clause=_IRR)
    if len(call.args) > 1 and ctx.lower(call.args[1]).shape == "list":
        raise DomainRefused(
            what=(
                "excel.irr is written over one value per period at operand 1, "
                "and a guess seeds one policy's stream"
            ),
            move=_ONE_GUESS,
            clause=_IRR,
        )
    if cashflows.shape != "list":
        raise DomainRefused(
            what="excel.irr is written over one value per policy, and a "
            "stream is one policy's own periods",
            move="write the per-period cashflow column the stream means",
            clause="11.1.18",
        )
    horizon = periods_of(cashflows)
    flows = mask_to_neutral(cashflows, horizon, 0.0).array
    _one_sign_change(flows, horizon.active)
    periods = jnp.arange(horizon.bucket, dtype=JNP_OF["f64"])[None, :]

    def value_at(rate: jax.Array) -> jax.Array:
        return jnp.sum(
            jnp.where(
                horizon.active, flows * jnp.power(1.0 + rate[:, None], -periods), 0.0
            ),
            axis=1,
        )

    low = jnp.full((flows.shape[0],), _IRR_LOW)
    high = jnp.full((flows.shape[0],), _IRR_HIGH)
    at_low = value_at(low)
    flag("excel.irr.bracket", jnp.sign(at_low) == jnp.sign(value_at(high)))

    def halve(
        bracket: tuple[jax.Array, jax.Array, jax.Array], _step: jax.Array
    ) -> tuple[tuple[jax.Array, jax.Array, jax.Array], None]:
        below, above, below_value = bracket
        middle = 0.5 * (below + above)
        at_middle = value_at(middle)
        goes_right = jnp.sign(at_middle) == jnp.sign(below_value)
        return (
            jnp.where(goes_right, middle, below),
            jnp.where(goes_right, above, middle),
            jnp.where(goes_right, at_middle, below_value),
        ), None

    (found, above, _), _ = lax.scan(halve, (low, high, at_low), jnp.arange(_IRR_STEPS))
    return Value(0.5 * (found + above), "f64", "scalar", "f64")


def _one_sign_change(flows: jax.Array, active: jax.Array) -> None:
    """Flag a stream the clause states no single rate for, in its own words.

    No change of sign at all has no root; more than one has several, and
    11.1.36 puts which one a guess selects outside this entry outright --
    ``[-100, 230, -132]`` has roots at 0.1 and 0.2 and this engine must not
    pick one of them. Two checks, because the two streams take two different
    next moves.
    """
    signs = jnp.where(active & (flows != 0.0), jnp.sign(flows), 0.0)
    # The last non-zero sign standing at or before each period: a cashflow of
    # nought is neither a payment nor a receipt and does not change the sign
    # the stream is on.
    _last, standing = running(
        signs,
        jnp.zeros((flows.shape[0],), dtype=signs.dtype),
        lambda carry, cell: jnp.where(cell == 0.0, carry, cell),
    )
    previous = jnp.concatenate(
        [jnp.zeros((flows.shape[0], 1), dtype=signs.dtype), standing[:, :-1]],
        axis=1,
    )
    turned = active & (signs != 0.0) & (previous != 0.0) & (signs != previous)
    changes = jnp.sum(jnp.where(turned, 1, 0), axis=1)
    # Two findings and not one: a stream that never turns has no root at all,
    # and a stream that turns twice has several with no way to choose between
    # them. One check with one move would give a reader the advice for the
    # other stream.
    flag("excel.irr.no_sign_change", changes == 0)
    flag("excel.irr.several_roots", changes > 1)
