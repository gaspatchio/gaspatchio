# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule period_dates output tests."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import UnitedStates
from gaspatchio_core.schedule._schedule import Schedule

if TYPE_CHECKING:
    import polars as pl


class TestFromCalendarGridPeriodDates:
    """Tests for ``Schedule.period_dates()`` on from_calendar_grid schedules."""

    def test_monthly_12_periods_from_jan_31(self) -> None:
        """12 monthly periods from Jan 31 produce 13 boundary dates."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        dates = sched.period_dates()
        assert isinstance(dates, list)
        assert len(dates) == 13  # 12 periods -> 13 boundaries (bop[0] .. eop[11])
        assert dates[0] == date(2025, 1, 31)
        # Month-end propagated forward through Feb (month-end of Feb in non-leap = 28th)
        assert dates[1] == date(2025, 2, 28)
        assert dates[12] == date(2026, 1, 31)

    def test_quarterly_4_periods(self) -> None:
        """4 quarterly periods from Mar 31 produce 5 quarter-end boundary dates."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=4,
            frequency="3M",
        )
        dates = sched.period_dates()
        assert dates == [
            date(2025, 3, 31),
            date(2025, 6, 30),
            date(2025, 9, 30),
            date(2025, 12, 31),
            date(2026, 3, 31),
        ]

    def test_annual_3_periods(self) -> None:
        """3 annual periods from Dec 31 produce 4 year-end boundary dates."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 12, 31),
            n_periods=3,
            frequency="1Y",
        )
        dates = sched.period_dates()
        assert dates == [
            date(2025, 12, 31),
            date(2026, 12, 31),
            date(2027, 12, 31),
            date(2028, 12, 31),
        ]

    def test_business_day_convention_following_skips_us_holiday(self) -> None:
        """Following convention rolls Jan 1 2025 (US holiday) to Jan 2."""
        # Start Jan 1 2025 (US holiday — New Year's).
        # Following convention rolls to Jan 2.
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 1),
            n_periods=2,
            frequency="1M",
            calendar=UnitedStates(),
            convention=BusinessDayConvention.FOLLOWING,
            anchor="exact_date",  # don't normalise to month-end for this test
        )
        dates = sched.period_dates()
        # Jan 1 2025 -> Following -> Jan 2 (Thu, business day)
        assert dates[0] == date(2025, 1, 2)


class TestFromInceptionPeriodDatesExpr:
    """Tests for ``Schedule.period_dates_expr()`` on from_inception schedules."""

    def test_basic_per_row_dates(self, sample_policies: pl.DataFrame) -> None:
        """Per-row grids anchored on inception dates produce correct boundary lists."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
        )
        policies_with_dates = sample_policies.with_columns(
            period_dates=sched.period_dates_expr()
        )
        result = policies_with_dates.get_column("period_dates").to_list()

        # Three rows: leap-day inception, mid-month inception, month-start inception
        # Row 0: 2024-02-29 → +1M → 2024-03-29 → +1M → 2024-04-29 → +1M → 2024-05-29
        assert result[0] == [
            date(2024, 2, 29),
            date(2024, 3, 29),
            date(2024, 4, 29),
            date(2024, 5, 29),
        ]
        # Row 1: 2024-03-15 (Friday, NullCalendar so unadjusted)
        assert result[1] == [
            date(2024, 3, 15),
            date(2024, 4, 15),
            date(2024, 5, 15),
            date(2024, 6, 15),
        ]
        # Row 2: 2025-06-01 (Sunday, NullCalendar so unadjusted)
        assert result[2] == [
            date(2025, 6, 1),
            date(2025, 7, 1),
            date(2025, 8, 1),
            date(2025, 9, 1),
        ]

    def test_period_dates_count_matches_n_periods_plus_one(
        self, sample_policies: pl.DataFrame
    ) -> None:
        """Each row list has exactly n_periods + 1 boundary dates."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=12,
            frequency="1M",
        )
        policies_with_dates = sample_policies.with_columns(
            period_dates=sched.period_dates_expr()
        )
        for row_dates in policies_with_dates.get_column("period_dates").to_list():
            assert len(row_dates) == 13  # 12 periods → 13 boundaries
