# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule.year_fractions() — dt[t] series consumed by .grow."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from gaspatchio_core.schedule._day_count import (
    Actual365Fixed,
    ActualActualISDA,
)
from gaspatchio_core.schedule._schedule import Schedule

if TYPE_CHECKING:
    import polars as pl


class TestYearFractionsCalendarGrid:
    """Tests for ``Schedule.year_fractions()`` on from_calendar_grid schedules."""

    def test_one_twelfth_default_returns_constant_one_twelfth(self) -> None:
        """Default OneTwelfth convention returns 1/12 for every period."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        yfs = sched.year_fractions()
        assert len(yfs) == 12
        for yf in yfs:
            assert yf == pytest.approx(1 / 12)

    def test_actual365fixed_varies_by_month(self) -> None:
        """Actual/365Fixed produces day-accurate fractions that vary by month length."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
            day_count=Actual365Fixed(),
        )
        yfs = sched.year_fractions()
        # Period 0: 2025-01-31 -> 2025-02-28 = 28 days / 365
        # Period 1: 2025-02-28 -> 2025-03-31 = 31 days / 365
        # Period 2: 2025-03-31 -> 2025-04-30 = 30 days / 365
        assert yfs == pytest.approx([28 / 365, 31 / 365, 30 / 365])

    def test_actual_actual_isda_handles_leap_crossing(self) -> None:
        """ActualActual/ISDA accounts for leap-year denominator correctly."""
        # Jan 31 2024 (leap) -> Feb 29 (29 days, leap year): 29/366
        sched = Schedule.from_calendar_grid(
            start_date=date(2024, 1, 31),
            n_periods=2,
            frequency="1M",
            day_count=ActualActualISDA(),
        )
        yfs = sched.year_fractions()
        # Period 0: 2024-01-31 -> 2024-02-29 = 29 days, all in leap -> 29/366
        assert yfs[0] == pytest.approx(29 / 366)


class TestYearFractionsFromInception:
    """Tests for ``Schedule.year_fractions_expr()`` on from_inception schedules."""

    def test_returns_polars_expr_yielding_list(
        self, sample_policies: pl.DataFrame
    ) -> None:
        """year_fractions_expr() maps per-policy inception dates to List<Float64>."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
        )
        result_df = sample_policies.with_columns(yfs=sched.year_fractions_expr())
        result = result_df.get_column("yfs").to_list()
        # OneTwelfth default -> all entries are 1/12
        for row in result:
            assert len(row) == 3
            for yf in row:
                assert yf == pytest.approx(1 / 12)
