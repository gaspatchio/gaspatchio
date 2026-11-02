# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.yearfrac`` is the spreadsheet's YEARFRAC, as section 11.1.34 states it.

Checked against D. A. Wheeler's reverse-engineered algorithm -- the one
OpenFormula and Gnumeric follow -- written out below with nothing shared with
the lowering. Three things it holds that the earlier rules did not: the answer
does not depend on argument order (the earlier day is the start, and no answer
is negative); basis 0 lets a start on February's last day leave an end day of
31 alone; and basis 1 takes its one-year denominator where the end falls on or
before the start's anniversary, not wherever the interval is 366 days or fewer.
"""

from __future__ import annotations

import calendar
import datetime as dt
import random

import pytest

from tests.conftest import invocation


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
        if (
            (a.year == b.year and calendar.isleap(a.year))
            or _leap_day_between(a, b)
            or (b.month == 2 and b.day == 29)
        ):
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
    """Return the spreadsheet's YEARFRAC, Wheeler's way: the earlier day first."""
    if a > b:
        a, b = b, a
    if basis == 2:
        return (b - a).days / 360
    if basis == 3:
        return (b - a).days / 365
    return {0: _basis_0, 1: _basis_1, 4: _basis_4}[basis](a, b)


def _answers(pairs: list[tuple[dt.date, dt.date]], basis: int) -> list[float]:
    from gaspatchio.engines.protocol import FrameSink
    from gaspatchio_jax.engine import JaxEngine

    one = invocation(
        {
            "op": "call",
            "name": "excel.yearfrac",
            "args": [{"op": "col", "name": "s"}, {"op": "col", "name": "e"}],
            "attrs": {"basis": basis},
        },
        {
            "s": {"dtype": "date", "values": [a.isoformat() for a, _ in pairs]},
            "e": {"dtype": "date", "values": [b.isoformat() for _, b in pairs]},
        },
        "f64",
    )
    return (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()
    )


def _review_corpus() -> list[tuple[dt.date, dt.date]]:
    """Return the wave-5 review's 20,006 forward pairs (its seed and its draws)."""
    draw = random.Random(11)  # noqa: S311 -- the review's own draws, not a secret
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


@pytest.mark.parametrize("basis", [0, 1, 2, 3, 4])
def test_the_review_s_pairs_are_the_spreadsheet_s_in_either_order(basis: int) -> None:
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
        # Microsoft's own example, 1 January to 30 July 2012.
        (dt.date(2012, 1, 1), dt.date(2012, 7, 30), 0, 209 / 360),
        (dt.date(2012, 1, 1), dt.date(2012, 7, 30), 1, 211 / 366),
        (dt.date(2012, 1, 1), dt.date(2012, 7, 30), 3, 211 / 365),
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
def test_the_hand_values(
    start: dt.date, end: dt.date, basis: int, by_hand: float
) -> None:
    assert _answers([(start, end)], basis) == pytest.approx([by_hand], abs=1e-12)
