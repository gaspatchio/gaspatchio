# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A double read as the fifteen significant figures a spreadsheet holds.

Two operations round a double by the digits a spreadsheet shows rather than
by its binary expansion: ``round_sig_figs`` (11.1.12) and ``round`` (11.1.8).
Both start from the same reading -- the double's exact decimal expansion cut
to fifteen significant digits, a sixteenth digit of 5 or more going away from
zero (11.1.35) -- and both need it exactly, because the reading is what
decides a near tie: 0.15 is the double 0.1499999999999999944..., which reads
as 0.150000000000000, a half.

:func:`held_figures` takes the reading without leaving binary64. The value is
scaled by ``10**k`` so its fifteen figures are its whole part, and the scaled
value is carried exactly: going up as ``x * 2**k``, exact, times ``5**k``
held as the double nearest it plus what that misses by, two Dekker products;
coming down as one correctly rounded quotient, whose product back tells which
side of it the value lies. Whether the scaled value reaches the half above its
whole part is then the exact sign of four doubles' sum. That holds for every
``k`` from -22 to 37: a magnitude from ``10**-22`` to below ``10**37``.
"""

from __future__ import annotations

import math
from fractions import Fraction
from typing import TYPE_CHECKING, Final

import jax.numpy as jnp

from gaspatchio_jax.ieee import apart, divided

if TYPE_CHECKING:
    import jax

__all__ = [
    "EXACT_SCALE",
    "HELD_FIGURES",
    "POWERS_OF_TEN",
    "TENS",
    "at_or_above",
    "held_figures",
]

# A double is exactly a sum of two halves of at most 26 bits each, cut by
# multiplying by this and subtracting (Veltkamp's split).
_SPLIT: Final[float] = 2.0**27 + 1.0
# The powers of ten a double holds exactly: 10**k for |k| <= 22.
EXACT_SCALE: Final[int] = 22
TENS: Final[tuple[float, ...]] = tuple(float(10**k) for k in range(EXACT_SCALE + 1))
# 10**0 through 10**18, every power of ten an i64 holds.
POWERS_OF_TEN: Final[tuple[int, ...]] = tuple(10**place for place in range(19))
# A spreadsheet holds fifteen significant figures of a double (11.1.35); scaled
# so they are its whole part, a value lies from 10**14 to below 10**15.
HELD_FIGURES: Final[int] = 15
_FIFTEEN_FIGURES: Final[float] = 1e15
# The decimal exponent is guessed this far below the logarithm, so the guess is
# never above the true exponent and at most one below it.
_GUESS_BELOW: Final[float] = 2.0**-30
# Going up by 10**k for k to 37 is a product by 2**k, exact, and one by 5**k,
# carried as the double nearest it and the whole number that double misses by.
_UP: Final[range] = range(38)
_TWOS: Final[tuple[float, ...]] = tuple(2.0**k for k in _UP)
_FIVE_HIGH: Final[tuple[float, ...]] = tuple(float(5**k) for k in _UP)
_FIVE_LOW: Final[tuple[float, ...]] = tuple(
    float(5**k - int(high)) for k, high in zip(_UP, _FIVE_HIGH, strict=True)
)


def at_or_above(power: int) -> float:
    """Return the least double at or above ``10**power``."""
    target = Fraction(10) ** power
    candidate = float(target)
    if Fraction(candidate) < target:
        return math.nextafter(candidate, math.inf)
    return candidate


def _product_error(a: jax.Array, b: jax.Array, product: jax.Array) -> jax.Array:
    """Return ``a * b - product`` exactly, ``product`` being the rounded ``a * b``.

    Dekker's product. Each cut is held apart from the subtraction that
    follows it, so the compiler can neither fuse the multiplication into it
    nor cancel the two subtractions; the four partial products are exact, so
    a fused multiply-add of any of them is the same number.
    """

    def halves(v: jax.Array) -> tuple[jax.Array, jax.Array]:
        cut = apart(v * _SPLIT, product)
        high = cut - apart(cut - v, product)
        return high, v - high

    ah, al = halves(a)
    bh, bl = halves(b)
    return ((ah * bh - product) + ah * bl + al * bh) + al * bl


def _two_sum(a: jax.Array, b: jax.Array) -> tuple[jax.Array, jax.Array]:
    """Return ``a + b`` rounded, and what the rounding lost, exactly (Knuth).

    The two differences are held apart, so the compiler cannot cancel
    ``total - (total - a)`` back to ``a``.
    """
    total = a + b
    b_part = apart(total - a, total)
    a_part = apart(total - b_part, total)
    return total, (a - a_part) + (b - b_part)


def _sign_of_sum(*terms: jax.Array) -> jax.Array:
    """Return the exact sign of four doubles' sum: -1, 0 or 1.

    Shewchuk's growing expansion: each term is added to the expansion so far
    by exact two-sums, which leaves components whose bits do not overlap, so
    the largest one that is not nought outweighs all the others together.
    """
    one, two, three, four = terms
    q1, h1 = _two_sum(two, one)
    q2, g1 = _two_sum(three, h1)
    q3, g2 = _two_sum(q2, q1)
    r1, f1 = _two_sum(four, g1)
    r2, f2 = _two_sum(r1, g2)
    r3, f3 = _two_sum(r2, q3)
    largest = jnp.where(r3 != 0, r3, jnp.where(f3 != 0, f3, jnp.where(f2 != 0, f2, f1)))
    return jnp.sign(largest)


def held_figures(v: jax.Array) -> tuple[jax.Array, jax.Array]:
    """Return a positive double's fifteen-digit reading as a whole number and a scale.

    ``held`` is the reading times ``10**k``, an ``int64`` of fifteen figures --
    or of sixteen ending in a nought, where the guessed scale was one short or
    a sixteenth digit carried -- and ``k`` the power: the reading is
    ``held * 10**-k`` exactly.
    ``v`` must be finite and lie from ``10**-22`` to below ``10**37``; a
    caller substitutes 1.0 for a value outside that and answers it another way.
    """
    k = HELD_FIGURES - 1 - jnp.floor(jnp.log10(v) - _GUESS_BELOW).astype(jnp.int64)
    upward = k >= 0
    up = jnp.maximum(k, 0)
    tens = jnp.asarray(TENS, dtype=jnp.float64)
    big = v * jnp.asarray(_TWOS, dtype=jnp.float64)[up]
    rest = jnp.asarray(_FIVE_LOW, dtype=jnp.float64)[up]
    down = tens[jnp.maximum(-k, 0)]
    quotient = divided(v, down)
    left = jnp.where(upward, big, quotient)
    right = jnp.where(upward, jnp.asarray(_FIVE_HIGH, dtype=jnp.float64)[up], down)
    # Each rounded product is held apart before it is added to or taken from,
    # so the compiler cannot fuse it into a multiply-add that skips its
    # rounding: the error beside it is the error of that rounding.
    p = apart(left * right, v)
    p_err = _product_error(left, right, p)
    c = apart(big * rest, v)
    c_err = _product_error(big, rest, c)
    lead = jnp.where(upward, p, quotient)
    unit = jnp.where(lead >= _FIFTEEN_FIGURES, 10.0, 1.0)
    whole = jnp.floor(divided(lead, unit)) * unit
    half = whole + unit * 0.5
    climbing = _sign_of_sum(p - half, p_err, c, c_err)
    # Coming down the quotient is correctly rounded, so it is on the half's
    # side unless it is the half, where the remainder's sign decides.
    falling = jnp.where(lead != half, jnp.sign(lead - half), jnp.sign((v - p) - p_err))
    reached = jnp.where(upward, climbing, falling) >= 0
    return (whole + jnp.where(reached, unit, 0.0)).astype(jnp.int64), k
