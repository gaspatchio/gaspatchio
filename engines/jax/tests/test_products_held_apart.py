# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A product a formula writes is rounded before anything else reads it.

11.1.25 states every operator as one binary64 operation, so ``a - b * c``
rounds the product and then the difference. XLA's CPU backend is entitled to
fuse the two into one multiply-add, which rounds once; the unit in the last
place it moves is inside every agreement band until a floor, a comparison or
a remainder reads it, and there it is a whole step.

The remainder's own dividend is the first case: ``(t * 12) % 12`` is the
position of a month in its year, and the remainder's subtraction fused with
the product in its dividend put month 13 at position 0 (audit C2-F3). The
corpus is searched for -- dividends written as a product whose fused and
rounded readings differ -- and each answer is held bit for bit against
Python's binary64 and against the reference producer.
"""

from __future__ import annotations

import datetime as dt
import math
import zlib
from typing import Final

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from tests.test_quotients import answers, both, clause, fused, same_bits

_KEPT: Final = 24
_DRAWS: Final = 50_000
_PERIODS: Final = 4


def _rng(label: str) -> np.random.Generator:
    """Return a generator seeded by name, so each corpus is its own and fixed."""
    return np.random.default_rng(zlib.crc32(label.encode()))


def _dividends(label: str, scale: float) -> list[float]:
    """Return ``x`` where ``(x * scale) % scale`` read fused differs from rounded.

    The rounded reading is the clause's: the product, then its remainder.
    The fused one keeps the product unrounded into the remainder's
    subtraction, ``fused(x, scale, -scale * floor(q))``. ``x`` is a whole
    count over ``scale`` -- a month over twelve, a percentage over a hundred
    -- which is where a model rebuilds a position from a time.
    """
    rng = _rng(label)
    found: list[float] = []
    for _ in range(_DRAWS):
        x = float(rng.integers(0, 100_000)) / scale
        product = x * scale
        floor = float(math.floor(product / scale))
        if clause("mod", product, scale) != fused(x, scale, -scale * floor):
            found.append(x)
            if len(found) == _KEPT:
                break
    assert len(found) == _KEPT, (label, len(found))
    return found


@pytest.mark.parametrize("scale", [12.0, 100.0, 7.0])
@pytest.mark.parametrize("shape", ["policy", "period"])
def test_a_product_dividend_is_rounded_before_its_remainder(
    shape: str, scale: float
) -> None:
    found = _dividends(f"{shape}/{scale}", scale)
    values = [[one] * _PERIODS for one in found] if shape == "period" else found
    af = ActuarialFrame(pl.DataFrame({"x": values}))
    af.r = (af.x * scale) % scale
    af.position = af.r.floor()
    producer, engine = both(af)
    repeat = _PERIODS if shape == "period" else 1
    want = [clause("mod", x * scale, scale) for x in found for _ in range(repeat)]
    assert same_bits(answers(engine, "r"), want)
    assert same_bits(answers(producer, "r"), want)
    floors = [float(math.floor(one)) for one in want]
    assert answers(engine, "position") == floors
    assert answers(producer, "position") == floors


def test_month_thirteen_is_position_one_in_its_year() -> None:
    """The audit's own case: ``floor((month / 12 * 12) % 12)`` is ``month % 12``."""
    book = pl.DataFrame({"pid": [1], "term_m": [36]})
    af = ActuarialFrame(book).projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="monthly",
    )
    af.t = af.month / 12.0
    af.position = ((af.t * 12.0) % 12.0).floor()
    producer, engine = both(af)
    want = [float(month % 12) for month in range(37)]
    assert answers(producer, "position") == want
    assert answers(engine, "position") == want


# Every product the formula writes, and every one a lowering writes
# beside a sum, is rounded before the sum reads it.


def _fusing(label: str) -> list[tuple[float, float, float]]:
    """Return ``(a, n, c)`` decimal draws where ``a + n * c`` fused differs.

    A loading in hundredths, a whole count of units and a rate in thousandths:
    the amounts a premium or a charge is written from, where a threshold at
    the spelled decimal is ordinary model code.
    """
    rng = _rng(label)
    found: list[tuple[float, float, float]] = []
    for _ in range(_DRAWS):
        a = float(rng.integers(0, 100)) / 100
        n = float(rng.integers(1, 21))
        c = float(rng.integers(1, 101)) / 1000
        if a + n * c != fused(n, c, a):
            found.append((a, n, c))
            if len(found) == _KEPT:
                break
    assert len(found) == _KEPT, (label, len(found))
    return found


@pytest.mark.parametrize("shape", ["policy", "period"])
def test_a_product_beside_a_sum_is_rounded_before_the_sum(shape: str) -> None:
    """``a + n * c``, ``n * c + a`` and ``a - n * c`` round twice, as 11.1.25 states.

    And the threshold at the decimal the line spells answers as the producer's
    does: ``0.5 + 5 * 0.011 >= 0.555`` is 0 on both engines (audit C2-F2).
    """
    found = _fusing(shape)

    def column(values: list[float]) -> list[float] | list[list[float]]:
        return [[one] * _PERIODS for one in values] if shape == "period" else values

    af = ActuarialFrame(
        pl.DataFrame(
            {
                "a": column([a for a, _, _ in found]),
                "n": column([n for _, n, _ in found]),
                "c": column([c for _, _, c in found]),
                "spelled": column([float(f"{a + n * c:.3f}") for a, n, c in found]),
            }
        )
    )
    af.after = af.a + af.n * af.c
    af.before = af.n * af.c + af.a
    af.less = af.a - af.n * af.c
    af.literal = af.a + af.n * 0.011
    af.reached = af.a + af.n * af.c >= af.spelled
    producer, engine = both(af)
    repeat = _PERIODS if shape == "period" else 1
    want = {
        "after": [a + n * c for a, n, c in found for _ in range(repeat)],
        "before": [n * c + a for a, n, c in found for _ in range(repeat)],
        "less": [a - n * c for a, n, c in found for _ in range(repeat)],
        "literal": [a + n * 0.011 for a, n, _ in found for _ in range(repeat)],
        "reached": [
            float(a + n * c >= float(f"{a + n * c:.3f}"))
            for a, n, c in found
            for _ in range(repeat)
        ],
    }
    for name, expected in want.items():
        assert same_bits(answers(engine, name), expected), name
        assert same_bits(answers(producer, name), expected), name


def test_the_audit_s_bonus_line_pays_on_both_engines() -> None:
    """``when(loading + units * rate >= 0.685)`` pays 100 where the sum is 0.685."""
    af = ActuarialFrame(
        pl.DataFrame(
            {"loading": [0.5, 0.5], "units": [5.0, 5.0], "rate": [0.011, 0.037]}
        )
    )
    af.prem = af.loading + af.units * af.rate
    af.ok = af.prem >= 0.555
    af.bonus = when(af.prem >= 0.685).then(100.0).otherwise(0.0)
    af.per_mille = (af.prem * 1000.0).floor()
    producer, engine = both(af)
    for frame in (producer, engine):
        assert frame["prem"].to_list() == [0.5549999999999999, 0.685]
        assert frame["ok"].to_list() == [0.0, 1.0]
        assert frame["bonus"].to_list() == [0.0, 100.0]
        assert frame["per_mille"].to_list() == [554.0, 685.0]


def _book(policies: int, periods: int, seed: str) -> pl.DataFrame:
    """Return a book of decimal amounts and rates, per policy and per period."""
    rng = _rng(seed)

    def runs(low: float, high: float, places: int) -> list[list[float]]:
        return [
            [round(float(x), places) for x in rng.uniform(low, high, periods)]
            for _ in range(policies)
        ]

    return pl.DataFrame(
        {
            "av0": [round(float(x), 2) for x in rng.uniform(100, 10_000, policies)],
            "prem": [round(float(x), 2) for x in rng.uniform(10, 500, policies)],
            "growth": runs(-0.02, 0.03, 4),
            "charge": runs(0.0, 0.01, 4),
            "cf": runs(-100.0, 1000.0, 2),
            "t": [round(float(x), 3) for x in rng.uniform(0.0, 40.0, policies)],
        }
    )


def _steps(av0: float, steps: list[tuple[float, float]], prem: float) -> list[float]:
    """Return ``av * g + prem`` period by period, every operation rounded."""
    out, av = [], av0
    for growth, _ in steps:
        av = av * growth + prem
        out.append(av)
    return out


def test_a_recurrence_rounds_its_product_before_its_addend() -> None:
    """11.1.20's ``carry * multiplier + addend``: two operations, two roundings."""
    book = _book(400, 24, "accumulate")
    af = ActuarialFrame(book)
    af.acc = af.cf.projection.accumulate(
        initial=af.av0, multiplier=af.growth, addend=af.prem
    )
    producer, engine = both(af)
    want = [
        one
        for av0, growth, prem in zip(
            book["av0"], book["growth"], book["prem"], strict=True
        )
        for one in _steps(av0, [(g, 0.0) for g in growth], prem)
    ]
    assert same_bits(answers(producer, "acc"), want)
    assert same_bits(answers(engine, "acc"), want)


def test_a_rollforward_rounds_each_growth_and_charge_before_the_next_step() -> None:
    """Grow, add, charge, add: each step rounded before the next reads the balance."""
    from gaspatchio import compile_rollforward

    book = _book(400, 24, "rollforward")
    af = ActuarialFrame(book).projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value=24,
        frequency="monthly",
    )
    builder = af.projection.rollforward(states={"av": af["av0"]})
    (
        builder["av"]
        .grow(af["growth"], label="growth")
        .add(af["prem"], label="prem")
        .charge(af["charge"], label="charge")
        .add(af["cf"], label="cf")
    )
    af.av = compile_rollforward(builder).expr_for("av")
    producer, engine = both(af)
    want: list[float] = []
    for av0, prem, growth, charge, cf in zip(
        book["av0"],
        book["prem"],
        book["growth"],
        book["charge"],
        book["cf"],
        strict=True,
    ):
        av = av0
        for g, m, flow in zip(growth, charge, cf, strict=True):
            av = av * (1.0 + g) + prem
            av = av * (1.0 - m) + flow
            want.append(av)
    assert same_bits(answers(producer, "av"), want)
    assert same_bits(answers(engine, "av"), want)


def test_a_curve_between_its_knots_is_the_producer_s_line() -> None:
    """``y0 + (y1 - y0) * (t - x0) / (x1 - x0)``, grouped and rounded as written."""
    from gaspatchio.curves import Curve

    tenors = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]
    rates = [0.031, 0.0337, 0.0349, 0.0361, 0.0377, 0.0391, 0.0413, 0.0402]
    curve = Curve.from_zero_rates(tenors=tenors, rates=rates)
    book = _book(2000, 1, "curve")
    af = ActuarialFrame(book.select("t"))
    af.spot = curve.spot_rate(af.t)

    def line(t: float) -> float:
        if t <= tenors[0]:
            return rates[0]
        if t >= tenors[-1]:
            return rates[-1]
        i = next(k for k, x in enumerate(tenors) if x > t)
        x0, x1, y0, y1 = tenors[i - 1], tenors[i], rates[i - 1], rates[i]
        return y0 + (y1 - y0) * (t - x0) / (x1 - x0)

    want = [line(t) for t in book["t"]]
    producer, engine = both(af)
    assert same_bits(answers(producer, "spot"), want)
    assert same_bits(answers(engine, "spot"), want)
