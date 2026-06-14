# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""BusinessDayConvention adjustment tests."""

from __future__ import annotations

from datetime import date

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import UnitedStates


class TestBusinessDayConventionEnum:
    """Verify the enum members and their canonical names."""

    def test_four_values(self) -> None:
        """Enum must expose exactly four convention names."""
        assert {c.name for c in BusinessDayConvention} == {
            "FOLLOWING",
            "MODIFIED_FOLLOWING",
            "PRECEDING",
            "UNADJUSTED",
        }

    def test_canonical_names(self) -> None:
        """Each member must return the expected canonical string."""
        assert BusinessDayConvention.FOLLOWING.canonical_name() == "Following"
        assert (
            BusinessDayConvention.MODIFIED_FOLLOWING.canonical_name()
            == "ModifiedFollowing"
        )
        assert BusinessDayConvention.PRECEDING.canonical_name() == "Preceding"
        assert BusinessDayConvention.UNADJUSTED.canonical_name() == "Unadjusted"


class TestAdjustWithoutCalendar:
    """Adjustment with no calendar input — pure weekend handling."""

    def test_unadjusted_returns_input(self) -> None:
        """UNADJUSTED must return the input date unchanged, even on a weekend."""
        # 2025-03-15 is a Saturday
        d = date(2025, 3, 15)
        # No calendar -> UNADJUSTED always returns identity
        assert BusinessDayConvention.UNADJUSTED.adjust(d, calendar=None) == d


class TestAdjustWithWeekendOnlyRules:
    """Without a calendar, only weekend rules apply for non-Unadjusted."""

    def test_following_pushes_saturday_to_monday(self) -> None:
        """FOLLOWING must advance a Saturday to the next Monday."""
        # 2025-03-15 (Sat) -> 2025-03-17 (Mon)
        d = date(2025, 3, 15)
        adjusted = BusinessDayConvention.FOLLOWING.adjust(d, calendar=None)
        assert adjusted == date(2025, 3, 17)

    def test_preceding_pulls_saturday_to_friday(self) -> None:
        """PRECEDING must retreat a Saturday to the prior Friday."""
        d = date(2025, 3, 15)
        adjusted = BusinessDayConvention.PRECEDING.adjust(d, calendar=None)
        assert adjusted == date(2025, 3, 14)

    def test_modified_following_stays_in_month(self) -> None:
        """MODIFIED_FOLLOWING falls back when following crosses the month boundary."""
        # 2025-05-31 (Sat); following -> Jun 2; mod-following pulls back to May 30 (Fri)
        d = date(2025, 5, 31)
        adjusted = BusinessDayConvention.MODIFIED_FOLLOWING.adjust(d, calendar=None)
        assert adjusted == date(2025, 5, 30)

    def test_modified_following_uses_following_when_within_month(self) -> None:
        """MODIFIED_FOLLOWING pushes forward when the result stays in the same month."""
        # 2025-03-15 (Sat); pushes to Mon Mar 17 (still March)
        d = date(2025, 3, 15)
        adjusted = BusinessDayConvention.MODIFIED_FOLLOWING.adjust(d, calendar=None)
        assert adjusted == date(2025, 3, 17)


class TestAdjustWithRealCalendar:
    """Regression tests — BusinessDayConvention.adjust composes with real calendars."""

    def test_following_skips_us_holiday(self) -> None:
        """FOLLOWING must advance past a US federal holiday to the next business day."""
        # 2025-01-20 (Mon) is MLK Day in US -> Following should advance to Tue Jan 21
        d = date(2025, 1, 20)
        adjusted = BusinessDayConvention.FOLLOWING.adjust(d, calendar=UnitedStates())
        assert adjusted == date(2025, 1, 21)

    def test_preceding_skips_us_holiday(self) -> None:
        """PRECEDING must retreat past a US federal holiday to the prior business day.

        Jan 18-19 are weekend, so preceding business day is Friday Jan 17.
        """
        d = date(2025, 1, 20)
        adjusted = BusinessDayConvention.PRECEDING.adjust(d, calendar=UnitedStates())
        # Friday Jan 17 (preceding business day, since Jan 18-19 are weekend)
        assert adjusted == date(2025, 1, 17)

    def test_modified_following_with_us_calendar_stays_in_month(self) -> None:
        """MODIFIED_FOLLOWING must push to Dec 26 — not a US federal holiday in 2025."""
        # 2025-12-25 (Thu) — Christmas — push forward to Friday Dec 26.
        d = date(2025, 12, 25)
        adjusted = BusinessDayConvention.MODIFIED_FOLLOWING.adjust(
            d, calendar=UnitedStates()
        )
        assert adjusted == date(2025, 12, 26)
