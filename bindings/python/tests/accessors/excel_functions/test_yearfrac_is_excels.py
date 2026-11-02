# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.yearfrac`` is Excel's YEARFRAC, on the reference producer as on JAX.

Checked against D. A. Wheeler's reverse-engineered algorithm -- the one
OpenFormula and Gnumeric follow, and the one the wave-5 review measured
against -- written out below with nothing shared with the kernel. It does not
depend on argument order: ``YEARFRAC(valuation, issue)`` is the same number as
``YEARFRAC(issue, valuation)``, never its negative. Basis 0 lets a start on
February's last day leave an end day of 31 alone, and basis 1 takes its
one-year denominator only where the end falls on or before the start's
anniversary.

The Polars side is the Rust kernel.
"""

from __future__ import annotations

import calendar
import datetime as dt
import random

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


def _last_of_month(day: dt.date) -> bool:
    return day.day == calendar.monthrange(day.year, day.month)[1]


def _basis_0(a: dt.date, b: dt.date) -> float:
    d1, d2 = a.day, b.day
    if d1 == 31 and d2 == 31:
        d1, d2 = 30, 30
    elif d1 == 31:
        d1 = 30
    elif d1 == 30 and d2 == 31:
        d2 = 30
    elif a.month == b.month == 2 and _last_of_month(a) and _last_of_month(b):
        d1, d2 = 30, 30
    elif a.month == 2 and _last_of_month(a):
        d1 = 30
    return (
        (d2 + b.month * 30 + b.year * 360) - (d1 + a.month * 30 + a.year * 360)
    ) / 360


def _appears_a_year(a: dt.date, b: dt.date) -> bool:
    if a.year == b.year:
        return True
    return a.year + 1 == b.year and (
        a.month > b.month or (a.month == b.month and a.day >= b.day)
    )


def _leap_day_between(a: dt.date, b: dt.date) -> bool:
    first = dt.date(a.year, 3, 1)
    if calendar.isleap(a.year) and a < first <= b:
        return True
    last = dt.date(b.year, 3, 1)
    return calendar.isleap(b.year) and a < last <= b


def _basis_1(a: dt.date, b: dt.date) -> float:
    if _appears_a_year(a, b):
        if a.year == b.year and calendar.isleap(a.year):
            length = 366
        elif _leap_day_between(a, b) or (b.month == 2 and b.day == 29):
            length = 366
        else:
            length = 365
        return (b - a).days / length
    years = b.year - a.year + 1
    mean = (dt.date(b.year + 1, 1, 1) - dt.date(a.year, 1, 1)).days / years
    return (b - a).days / mean


def _basis_4(a: dt.date, b: dt.date) -> float:
    d1, d2 = min(a.day, 30), min(b.day, 30)
    return (
        (d2 + b.month * 30 + b.year * 360) - (d1 + a.month * 30 + a.year * 360)
    ) / 360


def _wheeler(a: dt.date, b: dt.date, basis: int) -> float:
    """Return Excel's YEARFRAC, Wheeler's way: the earlier day first."""
    if a > b:
        a, b = b, a
    if basis == 2:
        return (b - a).days / 360
    if basis == 3:
        return (b - a).days / 365
    return {0: _basis_0, 1: _basis_1, 4: _basis_4}[basis](a, b)


def _review_corpus() -> list[tuple[dt.date, dt.date]]:
    """Return the wave-5 review's 20,006 forward pairs (its seed and its draws)."""
    draw = random.Random(11)
    pairs = []
    for _ in range(20_000):
        a = dt.date(2015, 1, 1) + dt.timedelta(days=draw.randint(0, 4000))
        b = a + dt.timedelta(days=draw.randint(0, draw.choice([40, 370, 800])))
        pairs.append((a, b))
    d = dt.date
    return [
        *pairs,
        (d(2023, 2, 28), d(2024, 2, 29)),
        (d(2024, 2, 29), d(2025, 2, 28)),
        (d(2024, 2, 29), d(2024, 3, 31)),
        (d(2023, 2, 28), d(2023, 3, 31)),
        (d(2023, 1, 1), d(2023, 12, 31)),
        (d(2012, 1, 1), d(2012, 7, 30)),
    ]


def _answers(pairs: list[tuple[dt.date, dt.date]], basis: int) -> list[float]:
    af = ActuarialFrame(
        pl.DataFrame({"s": [a for a, _ in pairs], "e": [b for _, b in pairs]})
    )
    af.y = af.s.excel.yearfrac(af.e, basis=basis)
    return af.collect()["y"].to_list()


@pytest.mark.parametrize("basis", [0, 1, 2, 3, 4])
def test_the_review_s_pairs_are_excel_s_in_either_order(basis: int) -> None:
    pairs = _review_corpus()
    forward = _answers(pairs, basis)
    backward = _answers([(b, a) for a, b in pairs], basis)
    wrong = [
        (a, b, got)
        for (a, b), got in zip(pairs, forward, strict=True)
        if abs(got - _wheeler(a, b, basis)) > 1e-12
    ]
    assert wrong == []
    assert backward == forward


@pytest.mark.parametrize(
    ("start", "end", "basis", "by_hand"),
    [
        # February's last day starts it; the 31st that ends it stays 31.
        (dt.date(2024, 2, 29), dt.date(2024, 3, 31), 0, 31 / 360),
        # 366 days run past the anniversary: over the mean of 2020 and 2021.
        (dt.date(2020, 9, 25), dt.date(2021, 9, 26), 1, 366 / 365.5),
        # 29 February to 28 February: on the anniversary, and a leap day inside.
        (dt.date(2024, 2, 29), dt.date(2025, 2, 28), 1, 365 / 366),
        # A workbook's YEARFRAC(valuation, issue), converted as written.
        (dt.date(2025, 12, 31), dt.date(2020, 6, 30), 3, 2010 / 365),
    ],
)
def test_the_edges_the_review_found(
    start: dt.date, end: dt.date, basis: int, by_hand: float
) -> None:
    assert _answers([(start, end)], basis) == pytest.approx([by_hand], abs=1e-12)


@pytest.mark.parametrize(
    ("basis", "by_hand"), [(0, 209 / 360), (1, 211 / 366), (3, 211 / 365)]
)
def test_microsoft_s_own_example(basis: int, by_hand: float) -> None:
    # 1 January to 30 July 2012, the YEARFRAC page's example.
    pair = [(dt.date(2012, 1, 1), dt.date(2012, 7, 30))]
    assert _answers(pair, basis) == pytest.approx([by_hand], abs=1e-12)
