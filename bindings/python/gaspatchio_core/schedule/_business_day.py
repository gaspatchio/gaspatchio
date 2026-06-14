# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""BusinessDayConvention — anniversary / period-boundary roll rules."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaspatchio_core.schedule._calendar import Calendar

# First weekday index that is a weekend (Saturday=5, Sunday=6)
_FIRST_WEEKEND_WEEKDAY: int = 5


class BusinessDayConvention(Enum):
    """How to roll a date that falls on a non-business day.

    Four conventions cover real actuarial use; all others (e.g.
    ``HalfMonthModifiedFollowing``, ``Nearest``) are fixed-income edge
    cases not in the curated set.
    """

    UNADJUSTED = "Unadjusted"
    FOLLOWING = "Following"
    MODIFIED_FOLLOWING = "ModifiedFollowing"
    PRECEDING = "Preceding"

    def canonical_name(self) -> str:
        """Return stable string name used in canonical-form fingerprinting."""
        return self.value

    def adjust(self, d: date, calendar: Calendar | None) -> date:
        """Return ``d`` rolled to a business day under this convention.

        ``calendar`` may be ``None``, in which case only weekend rules apply.
        """
        if self is BusinessDayConvention.UNADJUSTED:
            return d

        if self is BusinessDayConvention.FOLLOWING:
            return _roll_forward(d, calendar)

        if self is BusinessDayConvention.PRECEDING:
            return _roll_back(d, calendar)

        if self is BusinessDayConvention.MODIFIED_FOLLOWING:
            forward = _roll_forward(d, calendar)
            if forward.month == d.month:
                return forward
            return _roll_back(d, calendar)

        # Exhaustive — but mypy doesn't know that
        msg = f"unhandled convention {self!r}"
        raise AssertionError(msg)


def _is_business_day(d: date, calendar: Calendar | None) -> bool:
    """Return True if ``d`` is a business day under the given calendar.

    When ``calendar`` is ``None``, only weekend exclusion applies.
    """
    if d.weekday() >= _FIRST_WEEKEND_WEEKDAY:  # Saturday / Sunday
        return False
    if calendar is None:
        return True
    return calendar.is_business_day(d)


def _roll_forward(d: date, calendar: Calendar | None) -> date:
    """Advance ``d`` to the next business day (inclusive of ``d`` itself)."""
    while not _is_business_day(d, calendar):
        d = d + timedelta(days=1)
    return d


def _roll_back(d: date, calendar: Calendar | None) -> date:
    """Retreat ``d`` to the previous business day (inclusive of ``d`` itself)."""
    while not _is_business_day(d, calendar):
        d = d - timedelta(days=1)
    return d


__all__ = ["BusinessDayConvention"]
