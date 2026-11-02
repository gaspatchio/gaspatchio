# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A day count that counts whole months, on a cadence whose periods are not months.

``OneTwelfth`` -- the default -- counts one twelfth of a year for each whole
calendar month a period spans. A weekly or daily period spans no whole month,
so the convention has no fraction to give it: it read 1/12 for the one period
that crossed a month end and 0 for every other, and ``t_years`` stood still at
1/12 -- ``[0, 1/12, 1/12, 1/12, 1/12]`` on four weeks. Asked for year
fractions, such a schedule now refuses and names the day counts that count
days. The convention is only consulted for year fractions, so the rest of a
weekly or daily axis -- its dates, its masks -- is untouched.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.schedule._day_count import Actual365Fixed, ActualActualISDA
from gaspatchio.schedule._schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Callable

START = date(2025, 1, 31)
SUB_MONTH = ["1W", "1D"]
NAMES = {"1W": "weekly", "1D": "daily"}


def _assert_names_the_move(message: str, frequency: str) -> None:
    assert "OneTwelfth" in message
    assert NAMES[frequency] in message
    assert "Actual365Fixed()" in message
    assert "ActualActualISDA()" in message
    assert "projection.set(schedule=" in message


@pytest.mark.parametrize("frequency", SUB_MONTH)
@pytest.mark.parametrize(
    "ask",
    [
        lambda s: s.year_fractions(),
        lambda s: s.cumulative_year_fractions(),
    ],
    ids=["year_fractions", "cumulative_year_fractions"],
)
def test_a_calendar_grid_refuses_one_twelfth_fractions(
    frequency: str, ask: Callable[[Schedule], list[float]]
) -> None:
    sched = Schedule.from_calendar_grid(
        start_date=START, n_periods=4, frequency=frequency
    )
    with pytest.raises(ValueError, match="whole calendar month") as refused:
        ask(sched)
    _assert_names_the_move(str(refused.value), frequency)


@pytest.mark.parametrize("frequency", SUB_MONTH)
def test_an_inception_grid_refuses_one_twelfth_fractions(frequency: str) -> None:
    sched = Schedule.from_inception(
        inception_column="inception", n_periods=4, frequency=frequency
    )
    with pytest.raises(ValueError, match="whole calendar month") as refused:
        sched.year_fractions_expr()
    _assert_names_the_move(str(refused.value), frequency)
    assert "Schedule.from_inception(" in str(refused.value)


@pytest.mark.parametrize("frequency", ["weekly", "daily"])
@pytest.mark.parametrize("method", ["t_years", "year_fractions"])
def test_a_projected_frame_refuses_at_the_line(frequency: str, method: str) -> None:
    # The default day count, on the kwargs form: the line that asks is refused.
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1, 2]}))
    af.projection.set(start_date=START, n_periods=4, frequency=frequency)
    with pytest.raises(ValueError, match="whole calendar month"):
        af.t = getattr(af.projection, method)()
    assert "t" not in af.columns


@pytest.mark.parametrize(
    ("frequency", "days"), [("1W", 7), ("1D", 1)], ids=["weekly", "daily"]
)
def test_a_day_count_that_counts_days_gives_an_increasing_time(
    frequency: str, days: int
) -> None:
    # The named move: every period its own fraction, and time that moves.
    sched = Schedule.from_calendar_grid(
        start_date=START, n_periods=4, frequency=frequency, day_count=Actual365Fixed()
    )
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1]}))
    af.projection.set(schedule=sched)
    af.t = af.projection.t_years()
    af.dt = af.projection.year_fractions()
    out = af.collect()
    assert out["dt"][0].to_list() == pytest.approx([days / 365] * 4)
    assert out["t"][0].to_list() == pytest.approx([k * days / 365 for k in range(5)])


def test_actual_actual_isda_is_accepted_on_a_weekly_axis() -> None:
    sched = Schedule.from_calendar_grid(
        start_date=START, n_periods=2, frequency="1W", day_count=ActualActualISDA()
    )
    assert sched.year_fractions() == pytest.approx([7 / 365, 7 / 365])


@pytest.mark.parametrize("frequency", SUB_MONTH)
def test_the_rest_of_the_axis_does_not_consult_the_day_count(frequency: str) -> None:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1]}))
    af.projection.set(start_date=START, n_periods=2, frequency=frequency)
    af.dates = af.projection.period_dates()
    af.in_force = af.projection.is_in_force()
    out = af.collect()
    assert len(out["dates"][0]) == 3
    assert out["in_force"][0].to_list() == [True, True]


@pytest.mark.parametrize(
    ("frequency", "fraction"), [("1M", 1 / 12), ("3M", 0.25), ("6M", 0.5), ("1Y", 1.0)]
)
def test_one_twelfth_on_a_month_aligned_cadence_is_unchanged(
    frequency: str, fraction: float
) -> None:
    sched = Schedule.from_calendar_grid(
        start_date=START, n_periods=3, frequency=frequency
    )
    assert sched.year_fractions() == [fraction] * 3
