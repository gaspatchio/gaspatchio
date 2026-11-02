# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``/``, ``//`` and ``%`` over doubles: one IEEE operation each, as 11.1.25 states.

Two compiler rewrites each move a quotient by a unit in its last place, and a
floor taken of a moved quotient lands on the neighbouring integer:

- a division by a constant becomes a multiplication by its reciprocal, so
  ``444391 / 10`` came back ``44439.100000000006``, and ``0.3 // 0.1`` came
  back ``3.0`` where the clause's floor of the rounded quotient is ``2.0``;
- the remainder ``a - b * floor(a / b)`` fuses into one multiply-add, which
  rounds once where the clause rounds the product and then the difference.

And the remainder was the library's exact one rather than the clause's
rounded one: ``1.0 % 0.1`` is ``0.0`` under 11.1.25, and was
``0.09999999999999995``.

**The corpus is searched for, not chosen.** Every case is a numerator and a
divisor where the clause's answer and a rewritten one differ -- the
reciprocal product, its floor, the fused remainder -- found in a seeded
sample, and each test asserts the search found its cases, so a corpus that
stopped discriminating fails rather than passing on nothing. Every answer is
held bit for bit against two references: Python's binary64 arithmetic, which
rounds every step and fuses nothing, and the reference producer, through
``collect()`` on the same frame.
"""

from __future__ import annotations

import math
import sys
import zlib
from fractions import Fraction
from typing import TYPE_CHECKING, Final

import jax
import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

# Divisors a model writes as literals -- months, percent, per mille, a tenth,
# a hundredth, two day counts -- and two with nothing decimal about them.
LITERALS: Final = (10.0, 12.0, 100.0, 1000.0, 0.1, 0.01, 3.0, 7.0, 360.0, 365.25)

OPERATORS: Final[dict[str, Callable[[object, object], object]]] = {
    "div": lambda a, b: a / b,  # type: ignore[operator]
    "floordiv": lambda a, b: a // b,  # type: ignore[operator]
    "mod": lambda a, b: a % b,  # type: ignore[operator]
}

# How many discriminating cases each divisor's corpus holds, and the periods
# of a per-period column.
_KEPT: Final = 24
_PERIODS: Final = 4

# How many of the literals must have discriminating cases for the search to
# count: every one does for ``/``, and five do for ``//`` and ``%``.
_DISCRIMINATING_LITERALS: Final = 5

# How far the search looks before it settles for what it found.
_DRAWS: Final = 30_000


def clause(name: str, a: float, b: float) -> float:
    """Return 11.1.25's float answer in Python's binary64, every step rounded."""
    if b == 0.0:
        if name == "mod" or a == 0.0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    quotient = a / b
    if name == "div" or not math.isfinite(quotient):
        return quotient if name != "mod" else math.nan
    # ``math.floor`` answers an int, which has no negative zero; the floor of
    # -0.0 is -0.0, and that sign reaches the remainder.
    floor = math.copysign(float(math.floor(quotient)), quotient)
    return floor if name == "floordiv" else a - b * floor


def fused(x: float, y: float, z: float) -> float:
    """Return ``x * y + z`` rounded once, as IEEE 754's fused multiply-add does.

    Worked exactly in rationals and rounded by ``float``, which rounds a
    quotient of two integers to the nearest double, ties to even -- the one
    rounding a fused multiply-add makes. ``math.fma`` gives the same double
    from Python 3.13 on; the engine supports 3.12, which has none. Finite
    operands only: the corpus below never fuses anything else. An exact
    nought takes the sign IEEE 754 gives a sum, negative only where the
    product and the addend are both negative noughts; a sum past the largest
    double is the infinity of its sign.
    """
    if not all(math.isfinite(one) for one in (x, y, z)):
        msg = f"fused() takes finite operands, not {(x, y, z)!r}"
        raise ValueError(msg)
    exact = Fraction(x) * Fraction(y) + Fraction(z)
    if exact == 0:
        product_negative = math.copysign(1.0, x) != math.copysign(1.0, y)
        both_negative = product_negative and math.copysign(1.0, z) < 0
        return -0.0 if both_negative and x * y == 0.0 and z == 0.0 else 0.0
    try:
        return float(exact)
    except OverflowError:
        return math.inf if exact > 0 else -math.inf


def rewritten(name: str, a: float, b: float) -> tuple[float, ...]:
    """Return the answers a rewrite, or another language's rule, would give.

    The reciprocal product for each of the three; for ``//`` and ``%`` also
    the floor of the reciprocal product, and Python's own ``//`` and ``%``,
    which floor the *exact* quotient -- ``1.0 // 0.1`` is ``9.0`` there and
    ``10.0`` under the clause; and for ``%`` the fused multiply-add.
    """
    reciprocal = a * (1.0 / b)
    if name == "div":
        return (reciprocal,)
    if name == "floordiv":
        return (float(math.floor(reciprocal)), a // b)
    return (
        fused(-b, float(math.floor(a / b)), a),
        a - b * float(math.floor(reciprocal)),
        a % b,
    )


def corpus(
    name: str, divisor: Callable[[np.random.Generator], float], label: str
) -> list[tuple[float, float]]:
    """Return ``_KEPT`` pairs where the clause and the rewritten answer differ.

    A third of the draws are spread over seven orders of magnitude; a third
    are a whole multiple of the divisor, rounded -- the amounts a model
    divides back by the divisor it built them with -- and a third are the
    double just below one, because a floor moves only where the quotient
    sits within a unit of an integer.
    """
    rng = np.random.default_rng(zlib.crc32(f"{name} {label}".encode()))
    found: list[tuple[float, float]] = []
    for draw in range(_DRAWS):
        b = divisor(rng)
        if draw % 3 == 1:
            a = float(rng.integers(-100_000, 100_000)) * b
        elif draw % 3 == 2:
            a = math.nextafter(float(rng.integers(-100_000, 100_000)) * b, -b)
        else:
            a = float(rng.uniform(-1.0, 1.0) * 10.0 ** rng.integers(-2, 6))
        faithful = clause(name, a, b)
        if not all(_normal(one) for one in (a, b, a / b, faithful)):
            continue
        if any(not same_bits([faithful], [one]) for one in rewritten(name, a, b)):
            found.append((a, b))
            if len(found) == _KEPT:
                return found
    return found


def _normal(value: float) -> bool:
    """Return whether a double is nought, non-finite, or normal -- not subnormal.

    XLA's CPU backend flushes subnormal operands and results to zero in every
    operation, this one or any other, so a corpus that reached them would be
    measuring that and not the quotient.
    """
    return value == 0.0 or not math.isfinite(value) or abs(value) >= sys.float_info.min


def same_bits(left: list[float], right: list[float]) -> bool:
    """Return whether two runs of doubles are the same doubles, a NaN as a NaN."""
    return len(left) == len(right) and all(
        (math.isnan(x) and math.isnan(y))
        or (x == y and math.copysign(1.0, x) == math.copysign(1.0, y))
        for x, y in zip(left, right, strict=True)
    )


# Section 11.1.25: "Power's finite f64 values use the same relative 1e-12
# agreement as the transcendental family". A binary64 power is held to that,
# not to its bits.
POWER_TOLERANCE: Final = 1e-12


def on_a_card() -> bool:
    """Return whether this engine runs on an accelerator rather than the CPU."""
    return jax.default_backend() != "cpu"


def power_held(left: list[float], right: list[float], *, card: bool) -> bool:
    """Return whether answers that went through a binary64 power are held.

    On the CPU, XLA's ``pow`` is the producer's to the bit, and so is every
    answer: the same doubles. On a card the device's own ``pow`` may sit a
    place from the library's, which 11.1.25 allows: each value within
    ``POWER_TOLERANCE`` of the other, relative to it, a NaN as a NaN. A
    division the answer also went through is then held only to that bound on
    the card, so a test whose point is the division keeps its exact check on
    the CPU and on the producer.
    """
    if not card:
        return same_bits(left, right)
    return len(left) == len(right) and all(
        (math.isnan(x) and math.isnan(y))
        or math.isclose(x, y, rel_tol=POWER_TOLERANCE, abs_tol=0.0)
        for x, y in zip(left, right, strict=True)
    )


def test_a_power_held_on_a_card_is_held_to_its_tolerance_and_no_further() -> None:
    """The card's reading, checked where it can be: on any backend.

    The T4 answered ``4.0 ** -2.0`` as ``0.06249999999999999``, a place from
    ``0.0625``: held on a card, not on the CPU. A value two parts in a
    trillion away is held on neither, and nor is a NaN against a number.
    """
    off_by_a_place = [0.06249999999999999]
    assert power_held(off_by_a_place, [0.0625], card=True)
    assert not power_held(off_by_a_place, [0.0625], card=False)
    assert not power_held([0.0625 * (1 + 2e-12)], [0.0625], card=True)
    assert not power_held([math.nan], [0.0625], card=True)
    assert power_held([math.nan, 1.0], [math.nan, 1.0], card=False)


def answers(frame: pl.DataFrame, column: str) -> list[float]:
    """Return one column's doubles in row order, a per-period column flattened."""
    values = frame[column].to_list()
    return (
        [one for row in values for one in row]
        if isinstance(values[0], list)
        else values
    )


def both(af: ActuarialFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return the reference producer's frame and this engine's, for one model."""
    return af.collect(), af.collect(engine="jax")


@pytest.mark.parametrize("name", list(OPERATORS))
def test_a_literal_divisor_divides_rather_than_multiplying_by_its_reciprocal(
    name: str,
) -> None:
    searched = {
        literal: corpus(name, lambda _rng, c=literal: c, repr(literal))
        for literal in LITERALS
    }
    kept = {literal: found for literal, found in searched.items() if found}
    assert len(kept) >= _DISCRIMINATING_LITERALS, {
        literal: len(found) for literal, found in searched.items()
    }
    # Every literal's column the same length, a short corpus repeated.
    numerators = {
        literal: [found[row % len(found)][0] for row in range(_KEPT)]
        for literal, found in kept.items()
    }
    af = ActuarialFrame(
        pl.DataFrame({f"a{i}": column for i, column in enumerate(numerators.values())})
    )
    for i, literal in enumerate(numerators):
        af[f"q{i}"] = OPERATORS[name](af[f"a{i}"], literal)
    producer, engine = both(af)
    for i, (literal, column) in enumerate(numerators.items()):
        want = [clause(name, a, literal) for a in column]
        assert same_bits(answers(engine, f"q{i}"), want), (name, literal)
        assert same_bits(answers(producer, f"q{i}"), want), (name, literal)


def _spread(rng: np.random.Generator) -> float:
    """Return a divisor over six orders of magnitude, either sign."""
    return float(rng.uniform(-10.0, 10.0) * 10.0 ** rng.integers(-3, 3))


@pytest.mark.parametrize("name", list(OPERATORS))
@pytest.mark.parametrize(
    "shape",
    ["policy/policy", "period/policy", "policy/period", "period/period"],
)
def test_a_column_divisor_is_one_ieee_operation_whatever_the_shapes(
    name: str, shape: str
) -> None:
    found = corpus(name, _spread, shape)
    assert len(found) == _KEPT, len(found)
    numerator_shape, divisor_shape = shape.split("/")

    def column(values: list[float], kind: str) -> list[float] | list[list[float]]:
        return [[one] * _PERIODS for one in values] if kind == "period" else values

    af = ActuarialFrame(
        pl.DataFrame(
            {
                "a": column([a for a, _ in found], numerator_shape),
                "b": column([b for _, b in found], divisor_shape),
            }
        )
    )
    af.q = OPERATORS[name](af.a, af.b)
    producer, engine = both(af)
    repeat = _PERIODS if "period" in shape else 1
    want = [clause(name, a, b) for a, b in found for _ in range(repeat)]
    assert same_bits(answers(engine, "q"), want)
    assert same_bits(answers(producer, "q"), want)


def test_the_clause_s_own_examples_and_the_mixed_integer_numerator() -> None:
    af = ActuarialFrame(
        pl.DataFrame(
            {"x": [0.3, 1.0, 1.0, 444391.0, 135.021], "n": [3, 10, 1, 444391, 7]}
        )
    )
    af.floor_tenth = af.x // 0.1
    af.mod_tenth = af.x % 0.1
    af.tenth = af.n / 10
    producer, engine = both(af)
    for frame in (producer, engine):
        assert frame["floor_tenth"].to_list() == [2.0, 10.0, 10.0, 4443910.0, 1350.0]
        assert frame["mod_tenth"].to_list()[:3] == [0.09999999999999998, 0.0, 0.0]
        assert frame["tenth"].to_list() == [0.3, 1.0, 0.1, 44439.1, 0.7]
    assert same_bits(answers(engine, "mod_tenth"), answers(producer, "mod_tenth"))


def test_zero_divisors_signs_and_non_finite_operands_answer_as_the_producer_does() -> (
    None
):
    """The clause's exceptional outputs, and the floor's sign rule.

    A zero divisor is a signed infinity, or NaN over nought, for ``/`` and
    ``//``, and NaN for ``%`` -- a literal nought too, which a compiler could
    otherwise fold away. Floor is not truncation: ``-7 // 3`` is ``-3``, and
    the remainder carries the divisor's sign. The non-finite operands are
    outside the clause's bounded domain; what is held is that this engine
    answers there what the reference producer answers.
    """
    nan, inf = math.nan, math.inf
    a = [1.0, -1.0, 0.0, 7.0, -7.0, 7.0, -7.0, 1.0, -0.0, nan, inf, 1.0, -inf]
    b = [0.0, 0.0, 0.0, 3.0, 3.0, -3.0, -3.0, -0.0, 2.0, 1.0, 2.0, inf, 3.0]
    af = ActuarialFrame(pl.DataFrame({"a": a, "b": b}))
    for name, operator in OPERATORS.items():
        af[name] = operator(af.a, af.b)
        af[f"{name}_nought"] = operator(af.a, 0.0)
        af[f"{name}_minus_nought"] = operator(af.a, -0.0)
    producer, engine = both(af)
    finite = [i for i in range(len(a)) if math.isfinite(a[i]) and math.isfinite(b[i])]
    for name in OPERATORS:
        assert same_bits(
            [answers(engine, name)[i] for i in finite],
            [clause(name, a[i], b[i]) for i in finite],
        ), name
        for suffix, nought in (("_nought", 0.0), ("_minus_nought", -0.0)):
            column = f"{name}{suffix}"
            assert same_bits(
                [answers(engine, column)[i] for i in finite],
                [clause(name, a[i], nought) for i in finite],
            ), column
        for column in (name, f"{name}_nought", f"{name}_minus_nought"):
            assert same_bits(answers(engine, column), answers(producer, column)), column
    assert engine["floordiv"].to_list()[3:7] == [2.0, -3.0, -3.0, 2.0]
    assert engine["mod"].to_list()[3:7] == [1.0, 2.0, -2.0, -1.0]


def test_a_quotient_of_a_quotient_is_two_quotients() -> None:
    """``(a / b) / c`` is two divisions, not ``a / (b * c)``.

    The compiler's simplifier rewrites a division whose numerator is itself a
    division into one division by a product, which rounds once fewer: a model
    that writes ``af.claims / af.lives / 12.0`` is owed two quotients, as the
    reference producer computes them. Held for a per-policy chain, a literal
    at the end of one, a per-period numerator over a per-policy divisor, and
    a divisor that is itself a quotient.
    """
    rng = np.random.default_rng(zlib.crc32(b"quotient of a quotient"))
    found: list[tuple[float, float, float]] = []
    while len(found) < _KEPT:
        a, b, c = (
            float(rng.uniform(0.5, 2.0) * 10.0 ** rng.integers(-3, 3)) for _ in range(3)
        )
        if a / b / c != a / (b * c) and a / b / 12.0 != a / (b * 12.0):
            found.append((a, b, c))
    a, b, c = (list(column) for column in zip(*found, strict=True))
    af = ActuarialFrame(
        pl.DataFrame({"a": a, "b": b, "c": c, "k": [[one] * _PERIODS for one in a]})
    )
    af.abc = af.a / af.b / af.c
    af.ab12 = af.a / af.b / 12.0
    af.kbc = af.k / af.b / af.c
    af.a_bc = af.a / (af.b / af.c)
    producer, engine = both(af)
    want = {
        "abc": [x / y / z for x, y, z in found],
        "ab12": [x / y / 12.0 for x, y, _ in found],
        "kbc": [x / y / z for x, y, z in found for _ in range(_PERIODS)],
        "a_bc": [x / (y / z) for x, y, z in found],
    }
    for column, expected in want.items():
        assert same_bits(answers(engine, column), expected), column
        assert same_bits(answers(producer, column), expected), column


@pytest.mark.parametrize(
    ("x", "y", "z", "hand"),
    [
        (0.1, 10.0, -1.0, 2.0**-54),
        (-0.1, 10.0, 1.0, -(2.0**-54)),
        (1.0, 1.0, -1.0, 0.0),
        (-0.0, 1.0, -0.0, -0.0),
        (0.0, -1.0, 0.0, 0.0),
        (-0.0, -1.0, -0.0, 0.0),
        (1e308, 10.0, -1e308, math.inf),
        (2.0, 3.0, 4.0, 10.0),
    ],
    ids=[
        "a tenth times ten less one rounds once: 2**-54, not 0.0",
        "its negative",
        "an exact nought is positive",
        "two negative noughts stay negative",
        "a negative nought and a positive one are positive",
        "a positive product of noughts and a negative nought are positive",
        "past the largest double is infinite, though the operands are finite",
        "exact arithmetic is itself",
    ],
)
def test_the_fused_reference_rounds_once(
    x: float, y: float, z: float, hand: float
) -> None:
    """The remainder's fused reference, by hand: 0.1 is 3602879701896397 / 2**55.

    Ten of it is 1 + 2 / 2**55 exactly, so less one it is 2**-54, which one
    rounding keeps and two roundings (the product to 1.0 first) lose.
    """
    assert 0.1 * 10.0 - 1.0 == 0.0
    assert same_bits([fused(x, y, z)], [hand])


@pytest.mark.skipif(
    not hasattr(math, "fma"), reason="math.fma is in Python 3.13 and later"
)
def test_the_fused_reference_is_math_fma_bit_for_bit() -> None:
    """Where the interpreter has ``math.fma``, the rational route is the same double."""
    fma = math.fma  # type: ignore[attr-defined,unused-ignore]
    rng = np.random.default_rng(zlib.crc32(b"fused against math.fma"))
    triples = [
        (-b, float(math.floor(a / b)), a)
        for name in OPERATORS
        for label, divisor in (("spread", _spread), ("tenth", lambda _rng: 0.1))
        for a, b in corpus(name, divisor, label)
    ]
    for _ in range(20_000):
        x, y = (
            float(rng.uniform(-1.0, 1.0) * 10.0 ** rng.integers(-8, 8)) for _ in "xy"
        )
        triples.append((x, y, -x * y))
        triples.append(
            (x, y, float(rng.uniform(-1.0, 1.0) * 10.0 ** rng.integers(-8, 8)))
        )
    assert len(triples) > 40_000
    for x, y, z in triples:
        assert same_bits([fused(x, y, z)], [fma(x, y, z)]), (x, y, z)
