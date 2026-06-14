# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Calendar tests — holiday membership and business-day identification."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule._calendar import (
    TARGET,
    BespokeCalendar,
    Calendar,
    JointCalendar,
    NullCalendar,
    UnitedKingdom,
    UnitedStates,
)


class TestNullCalendar:
    """Tests for the NullCalendar implementation."""

    def test_name(self) -> None:
        """NullCalendar must return the stable canonical name."""
        assert NullCalendar().name() == "NullCalendar"

    def test_every_weekday_is_business_day(self) -> None:
        """Weekdays must be recognised as business days."""
        cal = NullCalendar()
        assert cal.is_business_day(date(2025, 3, 17))  # Mon
        assert cal.is_business_day(date(2025, 3, 21))  # Fri

    def test_weekends_are_business_days_too(self) -> None:
        """NullCalendar treats every day as a business day — even weekends.

        Weekend rolling is handled by BusinessDayConvention with calendar=None.
        """
        cal = NullCalendar()
        assert cal.is_business_day(date(2025, 3, 15))  # Sat
        assert cal.is_business_day(date(2025, 3, 16))  # Sun

    def test_eq_and_hash(self) -> None:
        """Two NullCalendar instances must be equal and share the same hash."""
        assert NullCalendar() == NullCalendar()
        assert hash(NullCalendar()) == hash(NullCalendar())

    def test_subclass_of_calendar(self) -> None:
        """NullCalendar must be a concrete subclass of the Calendar ABC."""
        assert isinstance(NullCalendar(), Calendar)


class TestTARGET:
    """Tests for the TARGET2 / Eurozone calendar."""

    def test_name(self) -> None:
        """TARGET must return the stable canonical name."""
        assert TARGET().name() == "TARGET"

    def test_good_friday_2025_is_holiday(self) -> None:
        """2025-04-18 is Good Friday; TARGET2 is closed."""
        assert not TARGET().is_business_day(date(2025, 4, 18))

    def test_easter_monday_2025_is_holiday(self) -> None:
        """2025-04-21 is Easter Monday; TARGET2 is closed."""
        assert not TARGET().is_business_day(date(2025, 4, 21))

    def test_normal_weekday_is_business(self) -> None:
        """A normal weekday must be recognised as a business day."""
        assert TARGET().is_business_day(date(2025, 3, 17))  # Mon

    def test_christmas_is_holiday(self) -> None:
        """Christmas Day must be a holiday."""
        assert not TARGET().is_business_day(date(2025, 12, 25))


class TestUnitedKingdom:
    """Tests for the UnitedKingdom calendar (England and Wales bank holidays)."""

    def test_name(self) -> None:
        """UnitedKingdom must return the stable canonical name."""
        assert UnitedKingdom().name() == "UnitedKingdom"

    def test_good_friday_2025_is_holiday(self) -> None:
        """Good Friday must be a UK bank holiday."""
        assert not UnitedKingdom().is_business_day(date(2025, 4, 18))

    def test_early_may_bank_holiday_2025(self) -> None:
        """2025-05-05 is the early May bank holiday in the UK."""
        assert not UnitedKingdom().is_business_day(date(2025, 5, 5))

    def test_normal_weekday_is_business(self) -> None:
        """A normal weekday must be recognised as a business day."""
        assert UnitedKingdom().is_business_day(date(2025, 3, 17))


class TestUnitedStates:
    """Tests for the UnitedStates federal holiday calendar."""

    def test_name(self) -> None:
        """UnitedStates must return the stable canonical name."""
        assert UnitedStates().name() == "UnitedStates"

    def test_mlk_day_2025(self) -> None:
        """2025-01-20 is MLK Day — a federal holiday."""
        assert not UnitedStates().is_business_day(date(2025, 1, 20))

    def test_thanksgiving_2025(self) -> None:
        """2025-11-27 is Thanksgiving — 4th Thursday of November."""
        assert not UnitedStates().is_business_day(date(2025, 11, 27))

    def test_normal_weekday_is_business(self) -> None:
        """A normal weekday must be recognised as a business day."""
        assert UnitedStates().is_business_day(date(2025, 3, 17))


class TestJointCalendar:
    """Tests for JointCalendar — union of two calendars' holiday sets."""

    def test_name(self) -> None:
        """Name must combine the two constituent calendars' names."""
        c = JointCalendar(UnitedStates(), UnitedKingdom())
        assert c.name() == "Joint(UnitedStates,UnitedKingdom)"

    def test_holiday_in_either_is_holiday(self) -> None:
        """A day that is a holiday in either calendar must not be a business day."""
        c = JointCalendar(UnitedStates(), UnitedKingdom())
        # 2025-01-20 is MLK Day (US, not UK) — joint calls it a holiday
        assert not c.is_business_day(date(2025, 1, 20))
        # 2025-05-05 is UK May bank holiday (not US) — joint still calls it a holiday
        assert not c.is_business_day(date(2025, 5, 5))

    def test_business_day_only_when_business_in_both(self) -> None:
        """A day must be a business day only when both calendars treat it as such."""
        c = JointCalendar(UnitedStates(), UnitedKingdom())
        assert c.is_business_day(date(2025, 3, 17))  # Mon, not a holiday in either


class TestBespokeCalendar:
    """Tests for BespokeCalendar — user-defined holiday set."""

    def test_name_default(self) -> None:
        """Default name must be 'Bespoke' when no label is supplied."""
        c = BespokeCalendar(holidays=frozenset())
        assert c.name() == "Bespoke"

    def test_name_with_label(self) -> None:
        """Name must include the label in brackets when a label is supplied."""
        c = BespokeCalendar(holidays=frozenset(), label="MyCorp2025")
        assert c.name() == "Bespoke[MyCorp2025]"

    def test_supplied_holiday_blocks_business_day(self) -> None:
        """A date in the user-supplied holiday set must not be a business day."""
        c = BespokeCalendar(holidays=frozenset({date(2025, 7, 15)}))
        assert not c.is_business_day(date(2025, 7, 15))
        assert c.is_business_day(date(2025, 7, 16))

    def test_weekend_still_excluded(self) -> None:
        """Weekends must not be business days even with an empty holiday set."""
        c = BespokeCalendar(holidays=frozenset())
        assert not c.is_business_day(date(2025, 3, 15))  # Sat


class TestCalendarRegistry:
    """Tests for the calendar_from_name curated registry."""

    def test_resolve_curated_names(self) -> None:
        """All curated calendar names must resolve to the correct calendar instance."""
        from gaspatchio_core.schedule._calendar import calendar_from_name

        assert calendar_from_name("NullCalendar") == NullCalendar()
        assert calendar_from_name("TARGET") == TARGET()
        assert calendar_from_name("UnitedKingdom") == UnitedKingdom()
        assert calendar_from_name("UnitedStates") == UnitedStates()

    def test_unknown_name_raises_with_suggestions(self) -> None:
        """An unknown name must raise ValueError with the name in the message."""
        from gaspatchio_core.schedule._calendar import calendar_from_name

        with pytest.raises(ValueError, match="unknown calendar 'US'"):
            calendar_from_name("US")
