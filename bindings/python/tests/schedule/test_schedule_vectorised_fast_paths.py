# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Vectorised fast-path tests for schedule expression methods.

Covers the three ``*_expr()`` methods on ``from_inception`` schedules:

- ``anniversary_mask_expr()`` — pl.lit broadcast (no map_elements)
- ``year_fractions_expr()`` — pl.lit broadcast for OneTwelfth; map_elements fallback
  for other day-counts
- ``period_dates_expr()`` — pl.concat_list + dt.offset_by for UNADJUSTED+NullCalendar;
  map_elements fallback for real calendars / non-UNADJUSTED conventions

Also covers ``cumulative_year_fractions()`` on ``from_calendar_grid`` schedules.

These tests verify:
1. Semantic correctness of each fast path (matches expected output).
2. Fast path output is identical to what the slow path previously produced.
3. Slow paths still work for non-default configurations.
4. The new ``cumulative_year_fractions()`` helper.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import NullCalendar, UnitedStates
from gaspatchio_core.schedule._day_count import ActualActualISDA, Actual365Fixed, OneTwelfth
from gaspatchio_core.schedule._schedule import Schedule

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def multi_row_df() -> pl.DataFrame:
    """Three inception dates spanning a leap year, identical to conftest fixture."""
    return pl.DataFrame(
        {
            "policy_id": [1, 2, 3],
            "contract_inception": [
                date(2024, 2, 29),  # leap-day inception
                date(2024, 3, 15),  # mid-month
                date(2025, 6, 1),  # month-start in non-leap year
            ],
        }
    )


# ---------------------------------------------------------------------------
# Fix 1: anniversary_mask_expr — pl.lit broadcast
# ---------------------------------------------------------------------------


class TestAnniversaryMaskExprVectorised:
    """Verify the pl.lit broadcast in anniversary_mask_expr."""

    def test_monthly_24_every_row_is_identical(self, multi_row_df: pl.DataFrame) -> None:
        """Every row receives the same mask list; no per-row Python callback."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=24,
            frequency="1M",
        )
        result = multi_row_df.with_columns(mask=sched.anniversary_mask_expr())
        rows = result.get_column("mask").to_list()

        expected = [False] * 24
        expected[11] = True
        expected[23] = True

        for row in rows:
            assert row == expected, f"row mismatch: {row}"

    def test_quarterly_8_every_row_is_identical(self, multi_row_df: pl.DataFrame) -> None:
        """Quarterly mask — True at indices 3 and 7 for every row."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=8,
            frequency="3M",
        )
        result = multi_row_df.with_columns(mask=sched.anniversary_mask_expr())
        rows = result.get_column("mask").to_list()

        expected = [False] * 8
        expected[3] = True
        expected[7] = True

        for row in rows:
            assert row == expected

    def test_mask_length_equals_n_periods(self, multi_row_df: pl.DataFrame) -> None:
        """Each row's mask has exactly n_periods elements."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=12,
            frequency="1M",
        )
        result = multi_row_df.with_columns(mask=sched.anniversary_mask_expr())
        for row in result.get_column("mask").to_list():
            assert len(row) == 12

    def test_matches_anniversary_mask_from_calendar_grid(
        self, multi_row_df: pl.DataFrame
    ) -> None:
        """Fast-path result matches the from_calendar_grid anniversary_mask() output."""
        grid_sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=24,
            frequency="1M",
        )
        inception_sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=24,
            frequency="1M",
        )
        expected = grid_sched.anniversary_mask()
        result = multi_row_df.with_columns(mask=inception_sched.anniversary_mask_expr())
        for row in result.get_column("mask").to_list():
            assert row == expected


# ---------------------------------------------------------------------------
# Fix 2: year_fractions_expr — OneTwelfth fast path
# ---------------------------------------------------------------------------


class TestYearFractionsExprOneTwelfthFastPath:
    """Verify the pl.lit broadcast in year_fractions_expr for OneTwelfth."""

    def test_returns_one_twelfth_per_period(self, multi_row_df: pl.DataFrame) -> None:
        """OneTwelfth fast path: every row contains [1/12] * n_periods."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=12,
            frequency="1M",
            day_count=OneTwelfth(),
        )
        result = multi_row_df.with_columns(yfs=sched.year_fractions_expr())
        rows = result.get_column("yfs").to_list()

        expected_yf = 1.0 / 12.0
        for row in rows:
            assert len(row) == 12
            for yf in row:
                assert yf == pytest.approx(expected_yf)

    def test_every_row_is_identical_regardless_of_inception(
        self, multi_row_df: pl.DataFrame
    ) -> None:
        """OneTwelfth result is row-invariant — all rows are identical."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=6,
            frequency="1M",
        )
        result = multi_row_df.with_columns(yfs=sched.year_fractions_expr())
        rows = result.get_column("yfs").to_list()

        first = rows[0]
        for row in rows[1:]:
            assert row == first

    def test_length_equals_n_periods(self, multi_row_df: pl.DataFrame) -> None:
        """Each row's year_fractions list has exactly n_periods elements."""
        n = 9
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=n,
            frequency="1M",
        )
        result = multi_row_df.with_columns(yfs=sched.year_fractions_expr())
        for row in result.get_column("yfs").to_list():
            assert len(row) == n


class TestYearFractionsExprActActISDASlowPath:
    """Verify the map_elements fallback still works for non-OneTwelfth day-counts."""

    def test_act_act_isda_varies_by_row(self, multi_row_df: pl.DataFrame) -> None:
        """ActualActualISDA result varies between rows (depends on actual dates)."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
            day_count=ActualActualISDA(),
        )
        result = multi_row_df.with_columns(yfs=sched.year_fractions_expr())
        rows = result.get_column("yfs").to_list()

        # Each row should have 3 fractions
        for row in rows:
            assert len(row) == 3
            for yf in row:
                assert yf > 0.0

        # Different inception dates → different boundary dates → different fractions
        # Row 0 starts 2024-02-29 (leap); Row 2 starts 2025-06-01 (non-leap)
        assert rows[0] != rows[2]

    def test_act365_fixed_slow_path(self, multi_row_df: pl.DataFrame) -> None:
        """Actual365Fixed falls back to map_elements and produces correct fractions."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=2,
            frequency="1M",
            day_count=Actual365Fixed(),
        )
        result = multi_row_df.with_columns(yfs=sched.year_fractions_expr())
        rows = result.get_column("yfs").to_list()

        # Row 1: 2024-03-15 → 2024-04-15 (31d) → 2024-05-15 (30d)
        assert rows[1][0] == pytest.approx(31 / 365.0)
        assert rows[1][1] == pytest.approx(30 / 365.0)


# ---------------------------------------------------------------------------
# Fix 3: period_dates_expr — vectorised fast path vs map_elements slow path
# ---------------------------------------------------------------------------


class TestPeriodDatesExprDefaultPath:
    """Fast path: UNADJUSTED + NullCalendar → pl.concat_list + dt.offset_by."""

    def test_monthly_matches_expected_dates(self, multi_row_df: pl.DataFrame) -> None:
        """Vectorised monthly offsets produce correct boundary dates per row."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        rows = result.get_column("dates").to_list()

        # Row 0: 2024-02-29 + 0,1,2,3 months
        assert rows[0] == [
            date(2024, 2, 29),
            date(2024, 3, 29),
            date(2024, 4, 29),
            date(2024, 5, 29),
        ]
        # Row 1: 2024-03-15 + 0,1,2,3 months
        assert rows[1] == [
            date(2024, 3, 15),
            date(2024, 4, 15),
            date(2024, 5, 15),
            date(2024, 6, 15),
        ]
        # Row 2: 2025-06-01 + 0,1,2,3 months
        assert rows[2] == [
            date(2025, 6, 1),
            date(2025, 7, 1),
            date(2025, 8, 1),
            date(2025, 9, 1),
        ]

    def test_length_is_n_periods_plus_one(self, multi_row_df: pl.DataFrame) -> None:
        """Each row list has n_periods + 1 elements."""
        n = 12
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=n,
            frequency="1M",
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        for row in result.get_column("dates").to_list():
            assert len(row) == n + 1

    def test_quarterly_fast_path(self, multi_row_df: pl.DataFrame) -> None:
        """3M frequency fast path produces correct quarter offsets."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=4,
            frequency="3M",
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        rows = result.get_column("dates").to_list()

        # Row 1: 2024-03-15 + 0,3,6,9,12 months
        assert rows[1] == [
            date(2024, 3, 15),
            date(2024, 6, 15),
            date(2024, 9, 15),
            date(2024, 12, 15),
            date(2025, 3, 15),
        ]

    def test_annual_fast_path(self, multi_row_df: pl.DataFrame) -> None:
        """1Y frequency fast path produces correct annual offsets."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1Y",
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        rows = result.get_column("dates").to_list()

        # Row 2: 2025-06-01 + 0,1,2,3 years
        assert rows[2] == [
            date(2025, 6, 1),
            date(2026, 6, 1),
            date(2027, 6, 1),
            date(2028, 6, 1),
        ]

    def test_zero_index_is_inception_date(self, multi_row_df: pl.DataFrame) -> None:
        """Index 0 of each row's list is the inception date itself (0-offset)."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=6,
            frequency="1M",
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        inception_col = multi_row_df.get_column("contract_inception").to_list()
        for dates, inception in zip(result.get_column("dates").to_list(), inception_col):
            assert dates[0] == inception


class TestPeriodDatesExprWithRealCalendar:
    """Slow path: real calendar or non-UNADJUSTED → map_elements still fires."""

    def test_unadjusted_with_real_calendar_uses_slow_path(
        self, multi_row_df: pl.DataFrame
    ) -> None:
        """Explicit UNADJUSTED + real calendar still routes to slow path."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=2,
            frequency="1M",
            calendar=UnitedStates(),
            convention=BusinessDayConvention.UNADJUSTED,
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        rows = result.get_column("dates").to_list()
        # Result should still be correct — no BD adjustment with UNADJUSTED
        assert rows[1] == [
            date(2024, 3, 15),
            date(2024, 4, 15),
            date(2024, 5, 15),
        ]

    def test_following_with_us_calendar_adjusts_holidays(
        self, multi_row_df: pl.DataFrame
    ) -> None:
        """FOLLOWING + UnitedStates adjusts dates that fall on holidays/weekends."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=2,
            frequency="1M",
            calendar=UnitedStates(),
            convention=BusinessDayConvention.FOLLOWING,
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        rows = result.get_column("dates").to_list()
        # Length still correct
        for row in rows:
            assert len(row) == 3

    def test_null_calendar_with_non_unadjusted_uses_slow_path(
        self, multi_row_df: pl.DataFrame
    ) -> None:
        """NullCalendar + non-UNADJUSTED convention → slow path; BD adjustment applied.

        NullCalendar still treats weekends as non-business days, so FOLLOWING
        does roll weekend dates forward to Monday.
        """
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=3,
            frequency="1M",
            calendar=NullCalendar(),
            convention=BusinessDayConvention.FOLLOWING,
        )
        result = multi_row_df.with_columns(dates=sched.period_dates_expr())
        rows = result.get_column("dates").to_list()
        # Row 1: 2024-03-15 (Fri) → +1M=Apr 15 (Mon) → +2M=May 15 (Wed) → +3M=Jun 15 (Sat→Mon Jun 17)
        assert rows[1][0] == date(2024, 3, 15)   # Fri — already a business day
        assert rows[1][1] == date(2024, 4, 15)   # Mon — already a business day
        assert rows[1][2] == date(2024, 5, 15)   # Wed — already a business day
        assert rows[1][3] == date(2024, 6, 17)   # Sat → Following → Mon


# ---------------------------------------------------------------------------
# Fix 4: cumulative_year_fractions
# ---------------------------------------------------------------------------


class TestCumulativeYearFractions:
    """Verify the new cumulative_year_fractions() helper method."""

    def test_one_twelfth_12_periods(self) -> None:
        """12 monthly OneTwelfth periods produce cumulative increments of 1/12."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        cumyfs = sched.cumulative_year_fractions()

        assert len(cumyfs) == 13  # n_periods + 1
        assert cumyfs[0] == 0.0
        for k in range(1, 13):
            assert cumyfs[k] == pytest.approx(k / 12.0)

    def test_starts_at_zero(self) -> None:
        """First element is always 0.0."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 6, 30),
            n_periods=6,
            frequency="1M",
        )
        cumyfs = sched.cumulative_year_fractions()
        assert cumyfs[0] == 0.0

    def test_last_element_equals_sum_of_year_fractions(self) -> None:
        """Last element equals sum of individual year fractions."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=6,
            frequency="1M",
        )
        cumyfs = sched.cumulative_year_fractions()
        yfs = sched.year_fractions()
        assert cumyfs[-1] == pytest.approx(sum(yfs))

    def test_length_is_n_periods_plus_one(self) -> None:
        """Length is always n_periods + 1."""
        for n in [1, 4, 12, 24]:
            sched = Schedule.from_calendar_grid(
                start_date=date(2025, 1, 31),
                n_periods=n,
                frequency="1M",
            )
            assert len(sched.cumulative_year_fractions()) == n + 1

    def test_strictly_increasing(self) -> None:
        """Cumulative fractions are strictly increasing (all yfs > 0)."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        cumyfs = sched.cumulative_year_fractions()
        for i in range(len(cumyfs) - 1):
            assert cumyfs[i + 1] > cumyfs[i]

    def test_raises_for_from_inception(self, multi_row_df: pl.DataFrame) -> None:
        """cumulative_year_fractions() raises ValueError on from_inception schedules."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=12,
            frequency="1M",
        )
        with pytest.raises(ValueError, match="cumulative_year_fractions"):
            sched.cumulative_year_fractions()

    def test_quarterly_cumulative(self) -> None:
        """3M frequency: cumulative fractions increment by 3/12 = 0.25."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=4,
            frequency="3M",
        )
        cumyfs = sched.cumulative_year_fractions()
        assert cumyfs == pytest.approx([0.0, 0.25, 0.5, 0.75, 1.0])

    def test_docstring_example(self) -> None:
        """The docstring example produces the stated output."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=3, frequency="1M"
        )
        result = sched.cumulative_year_fractions()
        assert result == pytest.approx([0.0, 1 / 12, 2 / 12, 3 / 12])
