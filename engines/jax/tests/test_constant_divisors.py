# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every lowering that divides divides as the reference producer does.

The operators are ``test_quotients.py``'s; these are the named operations
that divide inside themselves -- a monthly rate is the annual over twelve, a
discount is a value over ``(1 + r) ** t``, a rounding is a step over a power
of ten, a day count is days over 360 or 365. Each wrote its division as a
plain ``/``, and XLA's simplifier rewrote each by the divisor's form: a
literal into its reciprocal, a power into the opposite power. Every quotient
here was a unit in its last place from the producer's somewhere, and the
rounding moved a whole step where the scaled value sat near a half.

**Each corpus is searched for.** The draws kept are those where the faithful
quotient and the rewritten one differ, and each test asserts the search
filled its corpus. Every answer is held bit for bit against Python's
binary64, written as the producer writes the operation, and against the
producer itself through ``collect()``. Where a power stands in the divisor
its base and exponent are chosen so that the power is a double exactly --
``1.5 ** 3`` is ``3.375`` -- so that what is measured is the division, not
two libraries' ``pow``.

Two cannot follow that rule, and say so. The compound's exponent *is* the
quotient under test, ``t / 12``, and a power of a quotient that is not a
double exactly is not one either; the closed-form discount is ``v ** t``
set against a running product of ``v``, and the two differ only where the
powers are not exact. Each holds the producer to Python's bits everywhere and
this engine to them on the CPU; on a card the device's ``pow`` may sit a
place from the library's, which section 11.1.25 allows a power, so there the
engine is held to that clause's relative 1e-12 (``held_through_a_power``).
"""

from __future__ import annotations

import datetime as dt
import math
import sys
import zlib
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING, Final

import numpy as np
import polars as pl

from gaspatchio import ActuarialFrame
from tests.test_quotients import answers, both, on_a_card, power_held, same_bits

if TYPE_CHECKING:
    from collections.abc import Callable

_KEPT: Final = 48
_DRAWS: Final = 200_000

# Discount factors that are doubles exactly, so ``(1 + r) ** t`` is the same
# number from every ``pow``, and none a power of two, so dividing by one is
# not multiplying by an exact reciprocal.
_EXACT_FACTORS: Final = ((0.5, 3.0), (0.25, 2.0), (0.5, 5.0), (0.125, 4.0))


def _rng(label: str) -> np.random.Generator:
    """Return a generator seeded by name, so each corpus is its own and fixed."""
    return np.random.default_rng(zlib.crc32(label.encode()))


def searched(
    label: str,
    draw: Callable[[np.random.Generator], tuple[float, ...]],
    differs: Callable[..., bool],
) -> list[tuple[float, ...]]:
    """Return ``_KEPT`` draws where the faithful and the rewritten answer differ."""
    rng = _rng(label)
    found: list[tuple[float, ...]] = []
    for _ in range(_DRAWS):
        one = draw(rng)
        if differs(*one):
            found.append(one)
            if len(found) == _KEPT:
                break
    assert len(found) == _KEPT, (label, len(found))
    return found


def held(af: ActuarialFrame, want: dict[str, list[float]]) -> None:
    """Assert each column is Python's answer, on this engine and on the producer."""
    producer, engine = both(af)
    for column, expected in want.items():
        assert same_bits(answers(engine, column), expected), column
        assert same_bits(answers(producer, column), expected), column


def held_through_a_power(af: ActuarialFrame, want: dict[str, list[float]]) -> None:
    """As :func:`held`, for answers that went through a binary64 power.

    The producer to Python's bits, and this engine to them on the CPU; on a
    card, to section 11.1.25's relative 1e-12 for a power.
    """
    producer, engine = both(af)
    card = on_a_card()
    for column, expected in want.items():
        assert power_held(answers(engine, column), expected, card=card), column
        assert same_bits(answers(producer, column), expected), column


def half_away(value: float) -> float:
    """Return the nearest whole number, a half going away from zero, exactly."""
    magnitude = abs(value)
    whole = math.floor(magnitude)
    return math.copysign(
        whole + 1.0 if magnitude - whole >= 0.5 else float(whole), value
    )


def _amount(rng: np.random.Generator) -> tuple[float]:
    return (float(rng.uniform(-1.0, 1.0) * 10.0 ** rng.integers(-1, 7)),)


def test_to_monthly_simple_divides_by_twelve() -> None:
    found = searched(
        "to_monthly",
        lambda rng: (float(rng.uniform(0.0, 0.25)),),
        lambda r: r / 12.0 != r * (1.0 / 12.0),
    )
    rates = [r for (r,) in found]
    af = ActuarialFrame(pl.DataFrame({"r": rates}))
    af.monthly = af.r.finance.to_monthly(method="simple")
    held(af, {"monthly": [r / 12.0 for r in rates]})


def test_compound_divides_the_periods_by_the_frequency() -> None:
    def differs(t: float) -> bool:
        return 1.05 ** (t / 12.0) != 1.05 ** (t * (1.0 / 12.0))

    found = searched("compound", lambda rng: (float(rng.integers(1, 1200)),), differs)
    periods = [t for (t,) in found]
    af = ActuarialFrame(pl.DataFrame({"t": [periods]}))
    af.growth = af.t.finance.compound(rate=0.05, periods_per_year=12)
    held_through_a_power(af, {"growth": [1.05 ** (t / 12.0) for t in periods]})


def test_discount_and_present_value_divide_by_the_factor() -> None:
    """A literal rate and term make the factor a constant; columns make it a power."""
    for rate, term in _EXACT_FACTORS:
        factor = (1.0 + rate) ** term
        found = searched(
            f"discount {rate} {term}",
            _amount,
            lambda v, f=factor: v / f != v * (1.0 / f),
        )
        values = [v for (v,) in found]
        af = ActuarialFrame(
            pl.DataFrame({"v": values, "r": [rate] * _KEPT, "n": [term] * _KEPT})
        )
        af.literal = af.v.finance.discount(rate, term)
        af.by_column = af.v.finance.discount(af.r, af.n)
        af.present_value = af.finance.present_value("v", "r", "n")
        expected = [v / factor for v in values]
        producer, engine = both(af)
        for column in ("literal", "by_column", "present_value"):
            assert same_bits(answers(engine, column), expected), (column, rate, term)
            assert same_bits(answers(producer, column), expected), (column, rate, term)


def test_round_divides_by_its_step_under_either_tie_rule() -> None:
    def differs(x: float) -> bool:
        return round(x * 100.0) / 100.0 != round(x * 100.0) * 0.01

    found = searched(
        "round",
        lambda rng: (float(rng.integers(-(10**7), 10**7)) / 100.0 + 0.003,),
        differs,
    )
    xs = [x for (x,) in found] + [
        0.049999999999999996,
        -0.049999999999999996,
        0.25,
        -0.35,
    ]
    af = ActuarialFrame(pl.DataFrame({"x": xs}))
    af.even = af.x.round(2)
    af.away = af.x.round(2, mode="half_away_from_zero")
    af.tenth = af.x.round(1, mode="half_away_from_zero")
    held(
        af,
        {
            "even": [_read_and_moved(x, 2, ROUND_HALF_EVEN) for x in xs],
            "away": [_read_and_moved(x, 2, ROUND_HALF_UP) for x in xs],
            "tenth": [_read_and_moved(x, 1, ROUND_HALF_UP) for x in xs],
        },
    )


def _read_and_moved(x: float, places: int, rule: str) -> float:
    """Return 11.1.8's answer: the fifteen-digit reading moved to ``places``.

    The double is read as its fifteen-significant-digit decimal, a sixteenth
    digit of 5 or more going away from zero, and that decimal is rounded to
    ``places`` by the tie rule; the answer is the double nearest it, so the
    quotient that hands it back must be the correctly rounded one.
    """
    exact = Decimal(x)
    held = exact.quantize(
        Decimal((0, (1,), exact.adjusted() - 14)), rounding=ROUND_HALF_UP
    )
    return math.copysign(
        float(held.quantize(Decimal((0, (1,), -places)), rounding=rule)), x
    )


def test_round_sig_figs_divides_by_its_power_of_ten() -> None:
    def sig(x: float, digits: int) -> float:
        factor = 10.0 ** (digits - 1 - math.floor(math.log10(abs(x))))
        return half_away(x * factor) / factor

    def differs(x: float) -> bool:
        # The rewrite: a division by ``10 ** k`` is a multiplication by
        # ``10 ** -k``. A value within reach of a power of ten is left out,
        # where two libraries' ``log10`` could pick different digits.
        exponent = 3 - math.floor(math.log10(abs(x)))
        clear = abs(math.log10(abs(x)) - round(math.log10(abs(x)))) > 1e-9
        steps = half_away(x * 10.0**exponent)
        return clear and steps / 10.0**exponent != steps * 10.0**-exponent

    found = searched(
        "round_sig_figs",
        lambda rng: (float(rng.uniform(-1.0, 1.0) * 10.0 ** rng.integers(-6, 9)),),
        differs,
    )
    xs = [x for (x,) in found] + [2.5, -2.5, 0.49999999999999994]
    af = ActuarialFrame(pl.DataFrame({"x": xs}))
    af.four = af.x.round_sig_figs(4)
    af.one = af.x.round_sig_figs(1)
    held(af, {"four": [sig(x, 4) for x in xs], "one": [sig(x, 1) for x in xs]})


def test_yearfrac_divides_its_days_by_the_year() -> None:
    """Days over 360 or 365, and the 30/360 counts over 360, on every basis."""
    origin = dt.date(1990, 1, 1)

    def draw(rng: np.random.Generator) -> tuple[float, float]:
        return float(rng.integers(0, 15_000)), float(rng.integers(1, 12_000))

    def differs(start: float, days: float) -> bool:
        del start
        return days / 360.0 != days * (1.0 / 360.0) and days / 365.0 != days * (
            1.0 / 365.0
        )

    found = searched("yearfrac", draw, differs)
    starts = [origin + dt.timedelta(days=int(s)) for s, _ in found]
    ends = [
        s + dt.timedelta(days=int(d)) for s, (_, d) in zip(starts, found, strict=True)
    ]
    af = ActuarialFrame(pl.DataFrame({"s": starts, "e": ends}))
    bases = {
        "us": "30/360",
        "act_act": "act/act",
        "act_360": "act/360",
        "act_365": "act/365",
        "eu": "30e/360",
    }
    for column, basis in bases.items():
        af[column] = af.s.excel.yearfrac(af.e, basis=basis)

    def thirty_e(start: dt.date, end: dt.date) -> float:
        days = (
            360 * (end.year - start.year)
            + 30 * (end.month - start.month)
            + (min(end.day, 30) - min(start.day, 30))
        )
        return days / 360.0

    producer, engine = both(af)
    python = {
        "act_360": [(e - s).days / 360.0 for s, e in zip(starts, ends, strict=True)],
        "act_365": [(e - s).days / 365.0 for s, e in zip(starts, ends, strict=True)],
        "eu": [thirty_e(s, e) for s, e in zip(starts, ends, strict=True)],
    }
    for column, expected in python.items():
        assert same_bits(answers(engine, column), expected), column
    for column in bases:
        assert same_bits(answers(engine, column), answers(producer, column)), column


def _pv(
    rate: float, periods: float, payment: float, timing: int, future: float
) -> float:
    """Return 11.1.35's present value in the producer's grouping and functions.

    ``v^n`` as ``exp(-n log1p(r))`` and ``1 - v^n`` as ``-expm1(-n log1p(r))``;
    the flat form at a rate of nought only.
    """
    if rate == 0.0:
        return -(payment * periods + future)
    grown = periods * math.log1p(rate)
    annuity = (1.0 + rate * timing) * -math.expm1(-grown) / rate
    return -(payment * annuity + future * math.exp(-grown))


def near(af: ActuarialFrame, want: dict[str, list[float]], rel: float) -> None:
    """Assert each column is within ``rel`` of the answer, on both engines.

    ``exp``, ``log1p`` and ``expm1`` are the host's on the producer and XLA's
    here, and 11.1.12 holds the transcendental family to a relative band
    rather than to the bit (agreement.json records the ratio).
    """
    producer, engine = both(af)
    for column, expected in want.items():
        for side in (engine, producer):
            for got, wanted in zip(answers(side, column), expected, strict=True):
                assert abs(got - wanted) <= rel * abs(wanted), (column, got, wanted)


def test_excel_pv_divides_by_the_rate_as_the_producer_groups_it() -> None:
    """``pmt * ((1 + r*typ)(1 - v^n) / r) + fv * v^n``, each product rounded.

    The rates are 3, 7 and 15, none of whose reciprocals is a double; the
    division is the producer's, in its grouping, held to a few places of a
    double since the factors are transcendental (11.1.35).
    """

    def pv(
        rate: float, periods: float, payment: float, timing: int, future: float
    ) -> float:
        return _pv(rate, periods, payment, timing, future)

    def draw(rng: np.random.Generator) -> tuple[float, float, float]:
        return (
            float(rng.choice([3.0, 7.0, 15.0])),
            float(rng.integers(1, 30)),
            float(rng.uniform(-1e4, 1e4)),
        )

    def differs(rate: float, periods: float, payment: float) -> bool:
        factor = (1.0 + rate) ** -periods
        grouped = payment * ((1.0 - factor) / rate)
        return grouped != payment * (1.0 - factor) / rate

    found = searched("excel.pv", draw, differs)
    rate, periods, payment = (list(column) for column in zip(*found, strict=True))
    af = ActuarialFrame(pl.DataFrame({"r": rate, "n": periods, "pmt": payment}))
    af.end = af.r.excel.pv(af.n, af.pmt)
    af.due = af.r.excel.pv(af.n, af.pmt, typ=1)
    af.future = af.r.excel.pv(af.n, af.pmt, fv=1000.0)
    near(
        af,
        {
            "end": [pv(*one, 0, 0.0) for one in found],
            "due": [pv(*one, 1, 0.0) for one in found],
            "future": [pv(*one, 0, 1000.0) for one in found],
        },
        rel=1e-15,
    )


def _opening(rate: list[float]) -> list[float]:
    """Return the beginning-of-period factors, the running product of ``1/(1+r)``."""
    opening = [1.0]
    for r in rate[:-1]:
        opening.append(opening[-1] * (1.0 / (1.0 + r)))
    return opening


def test_prospective_value_divides_the_tail_by_the_opening_factor() -> None:
    """End of period: ``sum cf[s] * (v_open[s] * v[s])`` over ``v_open[t]``."""
    periods = 24
    rng = _rng("prospective_value")
    flows = [list(rng.uniform(0.0, 1e4, periods)) for _ in range(_KEPT)]
    rates = [list(rng.uniform(0.0, 0.01, periods)) for _ in range(_KEPT)]

    def valued(cf: list[float], rate: list[float], *, end: bool) -> list[float]:
        step = [1.0 / (1.0 + r) for r in rate]
        opening = _opening(rate)
        weighted = [
            c * (o * v) if end else c * o
            for c, o, v in zip(cf, opening, step, strict=True)
        ]
        tail, total = [0.0] * periods, 0.0
        for t in reversed(range(periods)):
            total += weighted[t]
            tail[t] = total
        return [x / o for x, o in zip(tail, opening, strict=True)]

    af = ActuarialFrame(pl.DataFrame({"cf": flows, "r": rates}))
    af.end = af.cf.projection.prospective_value(discount_rate=af.r)
    af.due = af.cf.projection.prospective_value(
        discount_rate=af.r, timing="beginning_of_period"
    )
    # What the old grouping, ``(cf * v_open) * v``, would have answered.
    regrouped = sum(
        (c * o) * v != c * (o * v)
        for cf, rate in zip(flows, rates, strict=True)
        for c, o, v in zip(
            cf, _opening(rate), [1.0 / (1.0 + r) for r in rate], strict=True
        )
    )
    assert regrouped > _KEPT, regrouped
    held(
        af,
        {
            "end": [
                x
                for cf, r in zip(flows, rates, strict=True)
                for x in valued(cf, r, end=True)
            ],
            "due": [
                x
                for cf, r in zip(flows, rates, strict=True)
                for x in valued(cf, r, end=False)
            ],
        },
    )


def test_excel_pv_meets_its_bound_at_every_nonzero_rate() -> None:
    """11.1.35's 1e-12 holds however near nought the rate is; nought is flat.

    ``1 + r`` rounded first lost the rate's last digits: 8.9e-5 relative at
    ``r = 1e-12``, and a step of 0.044 where the producer switched to the
    flat form below it. The exact answers are 80-digit decimal arithmetic
    over the doubles' own values.
    """
    payment = 1234.56

    def exact(rate: float, future: float) -> float:
        # Each double's own exact value, so the reference is the answer to
        # the inputs the engines were handed.
        with localcontext() as context:
            context.prec = 80
            r, p = Decimal(rate), Decimal(payment)
            if r == 0:
                return float(-(p * 120 + Decimal(future)))
            v = (1 + r) ** -120
            return float(-(p * (1 - v) / r + Decimal(future) * v))

    rates = [1e-13, -1e-13, 9.9e-13, 1e-12, 1e-9, 1e-5, 0.0, -0.0]
    rows = len(rates)
    af = ActuarialFrame(
        pl.DataFrame({"r": rates, "n": [120.0] * rows, "p": [1234.56] * rows})
    )
    af.end = af.r.excel.pv(af.n, af.p)
    af.future = af.r.excel.pv(af.n, af.p, fv=500.25)
    near(
        af,
        {
            "end": [exact(r, 0.0) for r in rates],
            "future": [exact(r, 500.25) for r in rates],
        },
        rel=1e-12,
    )
    producer, engine = both(af)
    for side in (engine, producer):
        assert answers(side, "end")[-2:] == [-(1234.56 * 120.0)] * 2


def test_a_literal_rate_is_valued_by_the_producer_s_closed_form() -> None:
    """``v = 1/(1+r)`` once and ``B[t] = v ** t``, not a running product of ``v``.

    The producer forms a written rate's boundary factors as powers, and a
    rate column's as a running product; the two differ in the last place
    from a few periods in, so the engine forms each the producer's way.
    """
    periods = 120
    rng = _rng("literal rate")
    flows = [list(rng.uniform(0.0, 1e4, periods)) for _ in range(_KEPT)]
    v = 1.0 / (1.0 + 0.004)
    opening = [v**t for t in range(periods)]
    running_product = [1.0]
    for _ in range(periods - 1):
        running_product.append(running_product[-1] * v)
    assert sum(a != b for a, b in zip(opening, running_product, strict=True)) > 10

    def valued(cf: list[float], *, end: bool) -> list[float]:
        weighted = [
            c * (o * v) if end else c * o for c, o in zip(cf, opening, strict=True)
        ]
        tail, total = [0.0] * periods, 0.0
        for t in reversed(range(periods)):
            total += weighted[t]
            tail[t] = total
        return [x / o for x, o in zip(tail, opening, strict=True)]

    af = ActuarialFrame(pl.DataFrame({"cf": flows}))
    af.end = af.cf.projection.prospective_value(discount_rate=0.004)
    af.due = af.cf.projection.prospective_value(
        discount_rate=0.004, timing="beginning_of_period"
    )
    held_through_a_power(
        af,
        {
            "end": [x for cf in flows for x in valued(cf, end=True)],
            "due": [x for cf in flows for x in valued(cf, end=False)],
        },
    )


def test_t_years_is_the_running_sum_of_the_year_fractions() -> None:
    """``[0, f, f + f, ...]``, added one period at a time, not ``k * f``."""
    periods = 240
    af = ActuarialFrame(pl.DataFrame({"term": [periods, periods]}))
    af = af.projection.set(
        valuation_date=dt.date(2025, 1, 1),
        until="term_months",
        until_value="term",
        frequency="monthly",
        per_policy=True,
    )
    af.t = af.projection.t_years()
    expected, total = [0.0], 0.0
    for _ in range(periods):
        total += 1.0 / 12.0
        expected.append(total)
    assert sum(t * (1.0 / 12.0) != e for t, e in enumerate(expected)) > 10
    held(af, {"t": expected * 2})


def test_forward_discount_factors_are_one_over_one_plus_the_rate() -> None:
    """``d[t] = product(1 / (1 + r[u]), u < t)``, as 11.1.30 states it.

    A power of ``1 + r`` to minus one is a libm ``pow``, and darwin's is not
    correctly rounded there, so the corpus is the rates where that ``pow``
    and the quotient differ on this machine -- every one on darwin, and on a
    platform whose ``pow`` is correctly rounded, none, where the quotient is
    still what both engines must give.
    """
    periods = 12
    rng = _rng("forward")
    draws = [float(r) for r in rng.uniform(0.0, 0.2, 400_000)]
    moved = [r for r in draws if (1.0 + r) ** -1.0 != 1.0 / (1.0 + r)]
    if sys.platform == "darwin":
        assert len(moved) >= periods * _KEPT, len(moved)
    corpus = (moved + draws)[: periods * _KEPT]
    rates = [corpus[i : i + periods] for i in range(0, len(corpus), periods)]

    def forward(rate: list[float]) -> list[float]:
        factors = [1.0]
        for r in rate[:-1]:
            factors.append(factors[-1] * (1.0 / (1.0 + r)))
        return factors

    af = ActuarialFrame(
        pl.DataFrame({"r": rates, "t": [list(range(periods))] * len(rates)})
    )
    af = af.finance.discount_factor(
        rate_col="r", periods_col="t", output_col="d", method="forward"
    )
    held(af, {"d": [x for rate in rates for x in forward(rate)]})
