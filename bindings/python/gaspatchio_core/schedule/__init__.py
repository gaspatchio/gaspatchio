# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Typed time primitives — Schedule, Calendar, DayCount, BusinessDayConvention.

The rollforward kernel consumes :class:`Schedule` via the ``schedule=``
kwarg of ``rollforward(...)``. The classes here can also be used
standalone — :meth:`Schedule.period_dates`, :meth:`Schedule.year_fractions`,
and :meth:`Schedule.anniversary_mask` produce calendar-aware values
useful in any time-stepped model.
"""

from __future__ import annotations

from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import (
    TARGET,
    BespokeCalendar,
    Calendar,
    JointCalendar,
    NullCalendar,
    UnitedKingdom,
    UnitedStates,
    calendar_from_name,
)
from gaspatchio_core.schedule._day_count import (
    Actual360,
    Actual365Fixed,
    ActualActualISDA,
    DayCount,
    OneTwelfth,
    Thirty360,
    day_count_from_name,
)
from gaspatchio_core.schedule._schedule import Schedule

__all__ = [
    "TARGET",
    "Actual360",
    "Actual365Fixed",
    "ActualActualISDA",
    "BespokeCalendar",
    "BusinessDayConvention",
    "Calendar",
    "DayCount",
    "JointCalendar",
    "NullCalendar",
    "OneTwelfth",
    "Schedule",
    "Thirty360",
    "UnitedKingdom",
    "UnitedStates",
    "calendar_from_name",
    "day_count_from_name",
]
