# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Leap-year regression tests.

Phase 1 commitment: Date(2020, 2, 29) + 1 year = Date(2021, 2, 28).
Tested explicitly because this is the single most common date-handling bug
in actuarial schedules.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.schedule._day_count import (
    Actual365Fixed,
    ActualActualISDA,
)
from gaspatchio_core.schedule._schedule import Schedule


class TestLeapDayInception:
    """Regression: Feb-29 inception advances to Feb-28 after one year."""

    def test_feb_29_plus_one_year_is_feb_28(self) -> None:
        """Period 0 starts Feb 29 2020; period 12 boundary lands Feb 28 2021."""
        # Per Phase 1 commitment + Schedule design pass §"leap-year handling"
        sched = Schedule.from_inception(
            inception_column="inception",
            n_periods=12,
            frequency="1M",
        )
        policies = pl.DataFrame({"inception": [date(2020, 2, 29)]})
        result = policies.with_columns(dates=sched.period_dates_expr())
        dates = result.get_column("dates").to_list()[0]
        # Period 0 starts Feb 29 2020; boundary 12 lands Feb 28 2021.
        assert dates[0] == date(2020, 2, 29)
        assert dates[12] == date(2021, 2, 28)


class TestLeapCrossingYearFractions:
    """Regression: year-fraction conventions handle leap-year crossings correctly."""

    def test_actual_actual_isda_splits_at_year_boundary(self) -> None:
        """Act/Act ISDA over one full leap-calendar year (2024) sums to exactly 1.0."""
        # 12-period monthly schedule starting 2024-01-01 with exact_date anchor
        # so boundaries are Jan 1 ... Dec 1 ... Jan 1 2025.
        # All 366 days fall in 2024 (leap year, denominator 366): sum = 366/366 = 1.0
        sched = Schedule.from_calendar_grid(
            start_date=date(2024, 1, 1),
            n_periods=12,
            frequency="1M",
            anchor="exact_date",
            day_count=ActualActualISDA(),
        )
        yfs = sched.year_fractions()
        assert sum(yfs) == pytest.approx(1.0, abs=1e-6)  # exactly one year

    def test_actual_365_fixed_does_not_round_trip_to_one(self) -> None:
        """Act/365F over a leap-year span totals 366/365, not 1.0 — by design."""
        # 12-period monthly schedule that crosses a leap-year boundary at Act/365F
        # totals 366/365 != 1.0 — by design
        sched = Schedule.from_calendar_grid(
            start_date=date(2024, 1, 31),
            n_periods=12,
            frequency="1M",
            day_count=Actual365Fixed(),
        )
        yfs = sched.year_fractions()
        # 2024-01-31 to 2025-01-31 is 366 days (because of Feb 29) / 365 = 366/365
        assert sum(yfs) == pytest.approx(366 / 365, abs=1e-9)
