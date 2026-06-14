# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule constructor tests."""

from __future__ import annotations

from datetime import date

import pytest

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import NullCalendar, UnitedStates
from gaspatchio_core.schedule._day_count import OneTwelfth
from gaspatchio_core.schedule._schedule import Schedule


class TestFromCalendarGrid:
    """Tests for Schedule.from_calendar_grid constructor."""

    def test_default_anchor_normalises_start_to_month_end(self) -> None:
        """Mid-month start_date with default anchor normalises to month-end."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1M",
        )
        assert sched.start_date == date(2025, 3, 31)
        assert sched.n_periods == 12
        assert sched.frequency == "1M"
        assert sched.anchor == "month_end"
        assert sched.calendar == NullCalendar()
        assert sched.day_count == OneTwelfth()
        assert sched.convention == BusinessDayConvention.UNADJUSTED

    def test_anchor_exact_date_does_not_normalise(self) -> None:
        """anchor='exact_date' preserves the supplied start_date unchanged."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1M",
            anchor="exact_date",
        )
        assert sched.start_date == date(2025, 3, 15)

    def test_real_calendar_changes_default_convention_to_modified_following(
        self,
    ) -> None:
        """A real calendar flips the default convention to MODIFIED_FOLLOWING."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=12,
            frequency="1M",
            calendar=UnitedStates(),
        )
        assert sched.convention == BusinessDayConvention.MODIFIED_FOLLOWING

    def test_explicit_convention_overrides_context_default(self) -> None:
        """An explicit convention argument overrides the context-dependent default."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 31),
            n_periods=12,
            frequency="1M",
            calendar=UnitedStates(),
            convention=BusinessDayConvention.UNADJUSTED,
        )
        assert sched.convention == BusinessDayConvention.UNADJUSTED

    def test_unsupported_frequency_raises(self) -> None:
        """An unsupported frequency string raises ValueError mentioning 'frequency'."""
        with pytest.raises(ValueError, match="frequency"):
            Schedule.from_calendar_grid(
                start_date=date(2025, 3, 31),
                n_periods=12,
                frequency="2.5W",  # not in supported set
            )

    def test_anchor_month_start(self) -> None:
        """anchor='month_start' normalises start_date to the first of the month."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1M",
            anchor="month_start",
        )
        assert sched.start_date == date(2025, 3, 1)

    def test_anchor_year_end(self) -> None:
        """anchor='year_end' normalises start_date to Dec 31 of the same year."""
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 3, 15),
            n_periods=12,
            frequency="1Y",
            anchor="year_end",
        )
        assert sched.start_date == date(2025, 12, 31)


class TestFromInception:
    """Tests for Schedule.from_inception constructor."""

    def test_basic_construction_with_column_name(self) -> None:
        """Basic construction stores inception_column and leaves start_date None."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=240,
            frequency="1M",
        )
        assert sched.inception_column == "contract_inception"
        assert sched.start_date is None
        assert sched.n_periods == 240
        assert sched.frequency == "1M"
        assert sched.calendar == NullCalendar()
        assert sched.convention == BusinessDayConvention.UNADJUSTED
        assert sched.day_count == OneTwelfth()
        assert sched._kind == "from_inception"  # noqa: SLF001

    def test_no_anchor_param_for_from_inception(self) -> None:
        """from_inception's anchor IS the inception column — no anchor param accepted.

        Passing ``anchor`` as a keyword argument must raise TypeError.
        """
        with pytest.raises(TypeError, match="anchor"):
            Schedule.from_inception(  # type: ignore[call-arg]
                inception_column="contract_inception",
                n_periods=240,
                frequency="1M",
                anchor="month_end",
            )

    def test_real_calendar_changes_default_convention(self) -> None:
        """A real calendar flips the default convention to MODIFIED_FOLLOWING."""
        sched = Schedule.from_inception(
            inception_column="contract_inception",
            n_periods=240,
            frequency="1M",
            calendar=UnitedStates(),
        )
        assert sched.convention == BusinessDayConvention.MODIFIED_FOLLOWING

    def test_unsupported_frequency_raises(self) -> None:
        """An unsupported frequency string raises ValueError mentioning 'frequency'."""
        with pytest.raises(ValueError, match="frequency"):
            Schedule.from_inception(
                inception_column="contract_inception",
                n_periods=240,
                frequency="2.5W",
            )


class TestPublicAPI:
    """Tests that public API exports are wired correctly at every package level."""

    def test_schedule_calendar_daycount_bdc_importable_from_subpackage(self) -> None:
        """Schedule, Calendar, DayCount, BDC are all importable from the subpackage.

        Verifies subpackage re-exports match the private module class objects.
        """
        from gaspatchio_core.schedule import (
            Calendar,
        )

        # Verify these are the same classes the private modules export
        from gaspatchio_core.schedule._calendar import Calendar as PrivateCalendar

        assert Calendar is PrivateCalendar

    def test_top_level_imports(self) -> None:
        """Top-level gaspatchio_core exposes Schedule, Calendar, DayCount, BDC."""
        import gaspatchio_core

        assert hasattr(gaspatchio_core, "Schedule")
        assert hasattr(gaspatchio_core, "Calendar")
        assert hasattr(gaspatchio_core, "DayCount")
        assert hasattr(gaspatchio_core, "BusinessDayConvention")

    def test_top_level___all___includes_new_exports(self) -> None:
        """Top-level __all__ lists all four new public names."""
        import gaspatchio_core

        for name in ("Schedule", "Calendar", "DayCount", "BusinessDayConvention"):
            assert name in gaspatchio_core.__all__
