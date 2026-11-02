# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``round``, ``floor`` and ``ceil``: moving a value to a whole step.

Section 11.1.8's own words. ``floor`` goes down and ``ceil`` goes up, which
for a negative value are different questions rather than one with a sign.
``round`` carries both the number of places and the tie rule, because both
move the money: half a penny is a penny under one rule and nothing under the
other, and an engine choosing for itself would be publishing a premium whose
last penny depends on who reads the file.

A negative ``decimals`` rounds to whole tens, hundreds and coarser steps, as
a spreadsheet's ``ROUND(x, -2)`` does: a double by the same reading, moved to
a multiple of ``10**n``, and a whole number in whole-number arithmetic, an
answer no ``i64`` holds flagged rather than wrapped.

**What is rounded is the value a spreadsheet holds.** ``round`` reads a double
as its fifteen-significant-digit decimal (:mod:`gaspatchio_jax.figures`) and
moves that decimal to its places by the tie rule: 2.675 is the double
2.67499999999999982..., which reads as 2.67500000000000, a half, so it is 2.68
at two places under either rule, and 0.285 is 0.28 under ``half_to_even`` and
0.29 under ``half_away_from_zero``. That is exact for every value below
``10**37`` at up to 22 places either side of the point; outside it the
engine's own scaling answers, and past ``10**308`` to the left, where no step
is a double, every finite value is under half a step and answers a nought.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio_jax.capability import Capability
from gaspatchio_jax.checks import flag
from gaspatchio_jax.figures import (
    EXACT_SCALE,
    POWERS_OF_TEN,
    TENS,
    at_or_above,
    held_figures,
)
from gaspatchio_jax.ieee import apart, divided
from gaspatchio_jax.lowerings import register
from gaspatchio_jax.typed import (
    INT64_MAX,
    INT64_MIN,
    Value,
    carried_to,
    require_carrier,
)

if TYPE_CHECKING:
    import jax

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.plan import LoweringContext
    from gaspatchio_jax.typed import Carrier

_ROUNDING: Final = "11.1.8"

# The two tie rules the clause names, and nothing else.
_HALF_TO_EVEN: Final = "half_to_even"
_HALF_AWAY: Final = "half_away_from_zero"

# The fraction at and above which a value rounds away from zero.
_HALF: Final = 0.5

# The fifteen-digit reading is moved to its places exactly below this
# magnitude; from it every double is a whole number and is its own answer.
_READ_BELOW: Final[float] = at_or_above(37)
# Below this a value's reading is under half a step at 22 places, the finest
# the exact route takes, so it rounds to a signed nought at every count of
# places that route takes; above it the reading is taken.
_NOUGHT_BELOW: Final[float] = 4e-23
# The most digits a step's whole count can be cut by: past it the count is
# nought at every place.
_DEEPEST_CUT: Final[int] = 17
# The largest power of ten a double holds.
_LARGEST_DECIMAL_POWER: Final[int] = 308
# The largest power of ten an i64 holds, and half of the next, the one whole
# number a tie can sit on at a step no i64 holds.
_I64_STEPS: Final[int] = 18
_I64_HALF_STEP: Final[int] = 5 * 10**18
# A step past 10**22 left of the point is taken down in two factors, this one
# first, so neither is below the least normal double.
_DOWN_FIRST: Final[float] = float(Fraction(1, 10**EXACT_SCALE))


# 11.1.8's operand domain, which is a number, and a flag read as its 0.0 or
# 1.0 (11.1.25), which each of the three carries to a double and answers as one.
_ROUNDED: Final[frozenset[Carrier]] = frozenset({"i64", "f64", "bool"})


def half_away_from_zero(values: jax.Array) -> jax.Array:
    """Return each value at its nearest whole number, a half going away from zero.

    Decided on the fraction itself, which is exact: ``|x| - floor(|x|)``
    loses nothing. ``floor(|x| + 0.5)`` is not the same rule, because the
    addition rounds -- ``0.49999999999999994 + 0.5`` is ``1.0`` -- and that
    sends a value just short of a half up, where the reference producer's
    rounding, and the clause, keep it down.
    """
    magnitude = jnp.abs(values)
    whole = jnp.floor(magnitude)
    return jnp.copysign(
        jnp.where(magnitude - whole >= _HALF, whole + 1.0, whole), values
    )


def _operand(call: Call, ctx: LoweringContext) -> Value:
    """Return the one operand these three take, a flag carried to a double."""
    operand = require_carrier(ctx.lower(call.args[0]), _ROUNDED, call.name, _ROUNDING)
    if operand.carrier == "bool":
        return carried_to(operand, "f64", clause=_ROUNDING)
    return operand


def _double(call: Call, ctx: LoweringContext) -> Value:
    """Return the one operand these three take, as a double."""
    return carried_to(_operand(call, ctx), "f64", clause=_ROUNDING)


@register(
    Capability(identifier="floor", arity=(1,), carriers=(_ROUNDED,), clause=_ROUNDING)
)
def _floor(call: Call, ctx: LoweringContext) -> Value:
    """Return the largest whole number not above the value.

    A whole number is already the largest whole number not above itself, so an
    ``i64`` operand comes back as it went in, in ``i64``. Widening it to a
    double would answer a type the record does not declare and lose the last
    digit of a large one for nothing.
    """
    operand = _operand(call, ctx)
    if operand.carrier == "i64":
        return operand
    doubled = carried_to(operand, "f64", clause=_ROUNDING)
    return Value(
        jnp.floor(doubled.array), "f64", doubled.shape, doubled.dtype, doubled.horizon
    )


@register(
    Capability(identifier="ceil", arity=(1,), carriers=(_ROUNDED,), clause=_ROUNDING)
)
def _ceil(call: Call, ctx: LoweringContext) -> Value:
    """Return the smallest whole number not below the value, as ``floor`` does."""
    operand = _operand(call, ctx)
    if operand.carrier == "i64":
        return operand
    doubled = carried_to(operand, "f64", clause=_ROUNDING)
    return Value(
        jnp.ceil(doubled.array), "f64", doubled.shape, doubled.dtype, doubled.horizon
    )


@register(
    Capability(
        identifier="round",
        arity=(1,),
        carriers=(_ROUNDED,),
        attrs={"mode": (_HALF_TO_EVEN, _HALF_AWAY)},
        # 11.1.8 defines every whole number of places: a negative one rounds
        # to tens and coarser steps.
        attr_bounds={"decimals": (None, None)},
        checks=("i64.range",),
        clause=_ROUNDING,
    )
)
def _round(call: Call, ctx: LoweringContext) -> Value:
    """Return the value at the nearest step, under the tie rule the node carries."""
    whole = _operand(call, ctx)
    attrs = dict(call.attrs)
    decimals = int(attrs.get("decimals", 0) or 0)
    away = attrs.get("mode") == _HALF_AWAY
    if whole.carrier == "i64":
        if decimals >= 0:
            # A whole number is already on every step at or after the point.
            return whole
        return Value(
            _whole_to_a_step(whole.array, -decimals, away=away),
            "i64",
            whole.shape,
            whole.dtype,
            whole.horizon,
        )
    operand = carried_to(whole, "f64", clause=_ROUNDING)
    values = operand.array
    if -EXACT_SCALE <= decimals <= EXACT_SCALE:
        rounded = _read_and_rounded(values, decimals, away=away)
    elif decimals < -_LARGEST_DECIMAL_POWER:
        # No step is a double; every finite value is under half of one.
        rounded = jnp.where(jnp.isfinite(values), values * 0.0, values)
    elif decimals < 0:
        rounded = _scaled_to_a_step(values, -decimals, away=away)
    else:
        rounded = _native(values, decimals, away=away)
    return Value(rounded, "f64", operand.shape, operand.dtype, operand.horizon)


def _whole_to_a_step(values: jax.Array, places: int, *, away: bool) -> jax.Array:
    """Return whole numbers at their nearest multiple of ``10**places``, exactly.

    Counted in ``int64``: the steps below, the rest, and a half decided by the
    tie rule. The least ``i64`` is read by the magnitude of the greatest,
    which differs from its own in a last digit that never sits on a half of
    any step. An answer no ``i64`` holds is flagged rather than wrapped. Past
    ``10**18`` the step is no ``i64``: at ``10**19`` a value moves to nought
    or to the step itself, which is flagged; past it every value is nought.
    """
    magnitude = jnp.where(values == INT64_MIN, INT64_MAX, jnp.abs(values))
    nought = jnp.zeros_like(values)
    if places > _I64_STEPS:
        if places == _I64_STEPS + 1:
            past = magnitude >= _I64_HALF_STEP if away else magnitude > _I64_HALF_STEP
            flag("i64.range", past)
        return nought
    step = POWERS_OF_TEN[places]
    count = magnitude // step
    twice_rest = 2 * (magnitude % step)
    tie = twice_rest == step
    up = (twice_rest > step) | (tie if away else tie & (count % 2 == 1))
    kept = count + up.astype(jnp.int64)
    fits = kept <= INT64_MAX // step
    flag("i64.range", ~fits)
    moved = jnp.where(fits, kept * step, nought)
    return jnp.where(values < 0, -moved, moved)


def _scaled_to_a_step(values: jax.Array, places: int, *, away: bool) -> jax.Array:
    """Return the native scaling past 22 places left of the point.

    The value scaled down by ``10**22`` and by the rest of the step, each the
    double nearest it, rounded to a whole number by the tie rule, and scaled
    back up by the double nearest ``10**places``: three products, as the
    reference producer writes them. Two factors down, because ``10**-308`` is
    below the least normal double and this engine reads one as nought. An
    answer the scaling carries past the largest double is the value itself.
    """
    first, rest = _DOWN_FIRST, float(Fraction(1, 10 ** (places - EXACT_SCALE)))
    up = float(10**places)
    # Held apart, or the compiler folds the two factors into one constant.
    scaled = apart(values * first, values) * rest
    steps = half_away_from_zero(scaled) if away else jnp.round(scaled)
    rounded = steps * up
    return jnp.where(jnp.isfinite(rounded), rounded, values)


def powered_ten(places: int) -> float:
    """Return ten to ``places`` as the reference producer's rounding scales by it.

    Squared and multiplied from the exponent's low bit, every product rounded
    to a double, as Rust's ``powi`` computes it -- the producer's scale past 22
    places. That is not the double nearest ``10**places`` from 33 places on
    (a correctly rounded ``pow`` gives that one), and not the host's ``pow``
    either: glibc's answers 1.0000000000000001e23 at 23 places, where ten to
    the 23rd lies halfway between two doubles. Products of doubles round the
    same on every machine, so this is one double everywhere. Past 308 places
    the product overflows to infinity, which is the producer's answer too.
    """
    product, square, left = 1.0, 10.0, places
    while True:
        if left & 1:
            product *= square
        left >>= 1
        if not left:
            return product
        square *= square


def _native(values: jax.Array, decimals: int, *, away: bool) -> jax.Array:
    """Return the value scaled, rounded to a whole number and scaled back.

    The engine's own route, taken past 22 places, where ``10**decimals`` is
    no double and the fifteen-digit reading is not moved exactly. The scale
    is :func:`powered_ten`'s, the producer's own. A value whose scaling
    leaves the finite range is its own answer, as the reference producer's
    rounding gives it. A division by a constant is a multiplication by its
    reciprocal to the compiler unless it is held apart: gaspatchio_jax.ieee.
    """
    # Past 10**308 the step is no double at all: every value is its own answer.
    factor = powered_ten(decimals) if decimals <= _LARGEST_DECIMAL_POWER else math.inf
    scaled = values * factor
    whole = half_away_from_zero(scaled) if away else jnp.round(scaled)
    rounded = divided(whole, factor)
    return jnp.where(jnp.isfinite(rounded), rounded, values)


def _read_and_rounded(values: jax.Array, decimals: int, *, away: bool) -> jax.Array:
    """Return the fifteen-digit reading moved to ``decimals`` places by the tie rule.

    The reading is ``held * 10**-k`` exactly; moved to ``decimals`` places it
    is ``held`` with its last ``k - decimals`` digits cut, a half going by the
    rule, and the answer is one correctly rounded product or quotient of the
    kept count by a power of ten a double holds. A reading already on a step
    is its own answer. Exact for every magnitude below ``10**37``; from it
    every double is a whole number and is its own answer, as the reference
    producer's rounding gives it, and so are nought, a NaN and an infinity.
    """
    magnitude = jnp.abs(values)
    usable = jnp.isfinite(magnitude) & (magnitude > 0)
    read = usable & (magnitude >= _NOUGHT_BELOW) & (magnitude < _READ_BELOW)
    held, k = held_figures(jnp.where(read, magnitude, 1.0))
    cut = k - decimals
    powers = jnp.asarray(POWERS_OF_TEN, dtype=jnp.int64)
    step = powers[jnp.clip(cut, 0, _DEEPEST_CUT)]
    count = held // step
    twice_rest = 2 * (held % step)
    if away:
        up = twice_rest >= step
    else:
        up = (twice_rest > step) | ((twice_rest == step) & (count % 2 == 1))
    kept = (count + up.astype(jnp.int64)).astype(jnp.float64)
    tens = jnp.asarray(TENS, dtype=jnp.float64)
    place = jnp.where(cut > 0, -decimals, -k)
    answer = jnp.where(
        place >= 0,
        kept * tens[jnp.clip(place, 0, EXACT_SCALE)],
        divided(kept, tens[jnp.clip(-place, 0, EXACT_SCALE)]),
    )
    signed = jnp.where(values < 0, -answer, answer)
    # The sign is read off its bit: a value below the least normal double is
    # nought to this engine's comparisons, and its answer keeps its sign.
    nought = jnp.where(jnp.signbit(values), -0.0, 0.0)
    tiny = jnp.isfinite(magnitude) & (magnitude < _NOUGHT_BELOW)
    return jnp.where(read, signed, jnp.where(tiny, nought, values))
