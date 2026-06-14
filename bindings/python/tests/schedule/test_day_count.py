# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Per-convention year-fraction tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from gaspatchio_core.schedule._day_count import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
    DayCount,
    OneTwelfth,
    Thirty360,
)


class TestOneTwelfth:
    """Tests for the OneTwelfth day-count convention."""

    def test_name(self) -> None:
        """OneTwelfth.name() returns the expected string."""
        assert OneTwelfth().name() == "OneTwelfth"

    def test_year_fraction_is_constant_one_twelfth(self) -> None:
        """year_fraction returns exactly 1/12 regardless of month length."""
        dc = OneTwelfth()
        # OneTwelfth ignores the actual dates — it's structural, not date-driven
        assert dc.year_fraction(date(2025, 1, 31), date(2025, 2, 28)) == pytest.approx(
            1 / 12
        )
        assert dc.year_fraction(date(2025, 2, 28), date(2025, 3, 31)) == pytest.approx(
            1 / 12
        )
        assert dc.year_fraction(date(2024, 2, 29), date(2024, 3, 31)) == pytest.approx(
            1 / 12
        )

    def test_year_fraction_year_aware_for_annual_step(self) -> None:
        """12 months apart yields a year fraction of 1.0."""
        dc = OneTwelfth()
        # 12 months apart → 1.0
        assert dc.year_fraction(date(2025, 1, 31), date(2026, 1, 31)) == pytest.approx(
            1.0
        )

    def test_is_frozen_dataclass(self) -> None:
        """OneTwelfth is immutable — attribute assignment raises FrozenInstanceError."""
        dc = OneTwelfth()
        with pytest.raises(FrozenInstanceError):
            dc.something = 42  # type: ignore[attr-defined]

    def test_equal_instances_hash_equal(self) -> None:
        """Two OneTwelfth instances are equal and hash-equal."""
        assert OneTwelfth() == OneTwelfth()
        assert hash(OneTwelfth()) == hash(OneTwelfth())

    def test_subclass_of_day_count(self) -> None:
        """OneTwelfth is a subclass of DayCount."""
        assert isinstance(OneTwelfth(), DayCount)


class TestActual365Fixed:
    """Tests for the Actual365Fixed day-count convention."""

    def test_name(self) -> None:
        """Actual365Fixed.name() returns the expected string."""
        assert Actual365Fixed().name() == "Actual365Fixed"

    def test_one_calendar_year_in_non_leap(self) -> None:
        """365 days in a non-leap year returns 1.0."""
        # 365 days / 365 fixed = 1.0
        dc = Actual365Fixed()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(
            1.0
        )

    def test_one_calendar_year_crossing_leap(self) -> None:
        """366 days crossing a leap year returns 366/365 > 1.0."""
        # 366 days / 365 fixed > 1.0 — Act/365F is *fixed*, ignores leap years
        dc = Actual365Fixed()
        result = dc.year_fraction(date(2024, 1, 1), date(2025, 1, 1))
        assert result == pytest.approx(366 / 365)

    def test_one_month_january_to_february(self) -> None:
        """January to February (31 days) returns 31/365."""
        dc = Actual365Fixed()
        # 31 days / 365
        assert dc.year_fraction(date(2025, 1, 1), date(2025, 2, 1)) == pytest.approx(
            31 / 365
        )

    def test_eq_and_hash(self) -> None:
        """Actual365Fixed instances are equal/hash-equal; not equal to OneTwelfth."""
        assert Actual365Fixed() == Actual365Fixed()
        assert hash(Actual365Fixed()) == hash(Actual365Fixed())
        assert Actual365Fixed() != OneTwelfth()


class TestActual360:
    """Tests for the Actual360 day-count convention."""

    def test_name(self) -> None:
        """Actual360.name() returns the expected string."""
        assert Actual360().name() == "Actual360"

    def test_one_calendar_year_non_leap(self) -> None:
        """365 days / 360 > 1.0 — money-market convention overstates the year."""
        # 365 days / 360 > 1.0 — money-market convention overstates the year
        dc = Actual360()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(
            365 / 360
        )

    def test_30_day_month(self) -> None:
        """30-day month returns 30/360."""
        dc = Actual360()
        assert dc.year_fraction(date(2025, 4, 1), date(2025, 5, 1)) == pytest.approx(
            30 / 360
        )

    def test_31_day_month(self) -> None:
        """31-day month returns 31/360."""
        dc = Actual360()
        assert dc.year_fraction(date(2025, 1, 1), date(2025, 2, 1)) == pytest.approx(
            31 / 360
        )


class TestThirty360:
    """Tests for the Thirty360 (30/360 ISDA Bond Basis) day-count convention."""

    def test_name(self) -> None:
        """Thirty360.name() returns the expected string."""
        assert Thirty360().name() == "Thirty360"

    def test_full_year(self) -> None:
        """Bond basis: each month is 30 days; a full year returns 1.0."""
        # Bond basis: each month is 30 days; year is 360 days
        dc = Thirty360()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(
            1.0
        )

    def test_one_month_31day(self) -> None:
        """31-day calendar month counts as 30 days under bond basis."""
        # Even a 31-day calendar month counts as 30 days under bond basis
        dc = Thirty360()
        assert dc.year_fraction(date(2025, 1, 1), date(2025, 2, 1)) == pytest.approx(
            30 / 360
        )

    def test_end_of_month_normalisation_d1_31(self) -> None:
        """Per ISDA Bond basis: if D1 = 31, set D1 = 30."""
        # Per ISDA Bond basis: if D1 = 31, set D1 = 30
        dc = Thirty360()
        # Jan 31 -> Feb 28: D1=31->30, D2=28; days = (28 - 30) + 30*(2-1) + 360*0 = 28
        assert dc.year_fraction(date(2025, 1, 31), date(2025, 2, 28)) == pytest.approx(
            28 / 360
        )

    def test_end_of_month_normalisation_d2_31_when_d1_30(self) -> None:
        """If D1 = 30 or 31, and D2 = 31, set D2 = 30."""
        # If D1 = 30 or 31, and D2 = 31, set D2 = 30
        dc = Thirty360()
        # Jan 30 -> Mar 31: D1=30, D2=31->30, days = (30 - 30) + 30*(3-1) + 0 = 60
        assert dc.year_fraction(date(2025, 1, 30), date(2025, 3, 31)) == pytest.approx(
            60 / 360
        )


class TestActualActualISDA:
    """Tests for the ActualActualISDA day-count convention."""

    def test_name(self) -> None:
        """ActualActualISDA.name() returns the expected string."""
        assert ActualActualISDA().name() == "ActualActualISDA"

    def test_full_non_leap_year(self) -> None:
        """365 days entirely in a non-leap year returns 1.0."""
        # 365 days entirely in a non-leap year -> 1.0
        dc = ActualActualISDA()
        assert dc.year_fraction(date(2025, 1, 1), date(2026, 1, 1)) == pytest.approx(
            1.0
        )

    def test_full_leap_year(self) -> None:
        """366 days entirely in a leap year (2024) returns 1.0."""
        # 366 days entirely in a leap year (2024) -> 1.0
        dc = ActualActualISDA()
        assert dc.year_fraction(date(2024, 1, 1), date(2025, 1, 1)) == pytest.approx(
            1.0
        )

    def test_crossing_leap_boundary(self) -> None:
        """ISDA splits the period at the year boundary across leap/non-leap years."""
        # ISDA splits the period at the year boundary:
        # 2024-06-01 to 2025-06-01 -> portion in 2024 / 366 + portion in 2025 / 365
        dc = ActualActualISDA()
        days_in_2024 = (date(2025, 1, 1) - date(2024, 6, 1)).days  # 214
        days_in_2025 = (date(2025, 6, 1) - date(2025, 1, 1)).days  # 151
        expected = days_in_2024 / 366 + days_in_2025 / 365
        assert dc.year_fraction(date(2024, 6, 1), date(2025, 6, 1)) == pytest.approx(
            expected
        )

    def test_one_month_in_leap_february(self) -> None:
        """Feb 1 2024 to Mar 1 2024 (29 days, all in leap year) returns 29/366."""
        # Feb 1 2024 to Mar 1 2024 -> 29 days, all in leap year -> 29/366
        dc = ActualActualISDA()
        assert dc.year_fraction(date(2024, 2, 1), date(2024, 3, 1)) == pytest.approx(
            29 / 366
        )


class TestDayCountRegistry:
    """Tests for the day_count_from_name registry function."""

    def test_resolve_by_name_returns_instance(self) -> None:
        """day_count_from_name returns the correct DayCount instance for each name."""
        from gaspatchio_core.schedule._day_count import day_count_from_name

        assert day_count_from_name("OneTwelfth") == OneTwelfth()
        assert day_count_from_name("Actual365Fixed") == Actual365Fixed()
        assert day_count_from_name("Actual360") == Actual360()
        assert day_count_from_name("Thirty360") == Thirty360()
        assert day_count_from_name("ActualActualISDA") == ActualActualISDA()

    def test_unknown_name_raises_with_suggestions(self) -> None:
        """Unknown name raises ValueError with a close-match suggestion."""
        from gaspatchio_core.schedule._day_count import day_count_from_name

        with pytest.raises(
            ValueError,
            match="unknown day-count 'Act365' — did you mean 'Actual360'",
        ):
            day_count_from_name("Act365")
