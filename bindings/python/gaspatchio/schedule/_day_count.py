# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""DayCount conventions for typed Schedule.

Each DayCount converts a (start_date, end_date) pair to a year fraction.
Used by Schedule to populate the per-period dt[t] series consumed by
time-aware rollforward operations like .grow(rate).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from difflib import get_close_matches


class DayCount(ABC):
    """Abstract day-count convention.

    Concrete subclasses are frozen dataclasses implementing :meth:`year_fraction`
    and :meth:`name`. Equality is type-based (two instances of the same subclass
    are equal); hashing is likewise type-based so that each convention hashes
    distinctly even though all subclasses carry no fields.

    Note: subclasses must explicitly define ``__hash__ = DayCount.__hash__``
    because ``@dataclass(frozen=True)`` generates a field-based ``__hash__``
    that would otherwise override this definition.
    """

    def __eq__(self, other: object) -> bool:
        """Return True iff ``other`` is the same day-count convention type."""
        return type(self) is type(other)

    def __hash__(self) -> int:
        """Hash based on the concrete type so each convention hashes distinctly."""
        return hash(type(self))

    @abstractmethod
    def year_fraction(self, start: date, end: date) -> float:
        """Return the year fraction between two dates under this convention."""

    @abstractmethod
    def name(self) -> str:
        """Return a stable short name used in canonical form / fingerprint."""


@dataclass(frozen=True)
class OneTwelfth(DayCount):
    """Constant 1/12 per month — actuarial default.

    Ignores varying month length. Matches US VM-20/VM-21, UK/EU SII, and
    IFRS 17 production practice (~80% of life-insurance models).
    """

    __hash__ = DayCount.__hash__

    def year_fraction(self, start: date, end: date) -> float:
        """Return 1/12 per calendar month between start and end.

        Whole-month count from start to end, signed.
        Treat day-of-month as a continuous interpolation within the month
        so cross-month-boundary calls (rare) still produce a meaningful fraction.
        (The kernel calls year_fraction at exact period boundaries, where the
        day-of-month adjustment is zero — so this is a defensive default.)
        """
        months = (end.year - start.year) * 12 + (end.month - start.month)
        return months / 12.0

    def name(self) -> str:
        """Return the stable short name for this convention."""
        return "OneTwelfth"


@dataclass(frozen=True)
class Actual365Fixed(DayCount):
    """Act/365F — actual days numerator, 365-day fixed denominator.

    UK / sterling and EIOPA-aligned sub-annual interpolation convention.
    Note: 'fixed' means the denominator is *always* 365, even across leap years —
    so a leap-year span of 366 days returns 366/365 > 1.0.
    """

    __hash__ = DayCount.__hash__

    def year_fraction(self, start: date, end: date) -> float:
        """Return actual days / 365 between start and end."""
        return (end - start).days / 365.0

    def name(self) -> str:
        """Return the stable short name for this convention."""
        return "Actual365Fixed"


@dataclass(frozen=True)
class Actual360(DayCount):
    """Act/360 — actual days numerator, 360-day fixed denominator.

    USD money-market convention; commonly used on the asset side
    (interest-rate swaps, money-market discount curves).
    """

    __hash__ = DayCount.__hash__

    def year_fraction(self, start: date, end: date) -> float:
        """Return actual days / 360 between start and end."""
        return (end - start).days / 360.0

    def name(self) -> str:
        """Return the stable short name for this convention."""
        return "Actual360"


@dataclass(frozen=True)
class Thirty360(DayCount):
    """30/360 ISDA Bond Basis.

    Each month is treated as 30 days, year as 360 days. Two end-of-month
    normalisations:
      - If D1 = 31, set D1 = 30
      - If D2 = 31 and D1 in {30, 31}, set D2 = 30

    Used for legacy bond / mortgage assets and some corporate-debt cashflows.
    """

    __hash__ = DayCount.__hash__

    def year_fraction(self, start: date, end: date) -> float:
        """Return 30/360 ISDA Bond Basis year fraction between start and end."""
        _max_day = 31
        _norm_day = 30
        d1 = _norm_day if start.day == _max_day else start.day
        d2 = end.day
        if d2 == _max_day and d1 in (_norm_day, _max_day):
            d2 = _norm_day
        days = (
            (end.year - start.year) * 360 + (end.month - start.month) * 30 + (d2 - d1)
        )
        return days / 360.0

    def name(self) -> str:
        """Return the stable short name for this convention."""
        return "Thirty360"


def _is_leap_year(year: int) -> bool:
    """Return True if year is a leap year per the proleptic Gregorian calendar."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


@dataclass(frozen=True)
class ActualActualISDA(DayCount):
    """Act/Act ISDA — actual days, split at year boundaries.

    For a period crossing a year boundary, the year fraction is the sum of:
      - days in the start year / (366 if start year is leap else 365)
      - days in the end year / (366 if end year is leap else 365)

    Precise leap-year handling — preferred for IFRS 17 / general use.
    """

    __hash__ = DayCount.__hash__

    def year_fraction(self, start: date, end: date) -> float:
        """Return Act/Act ISDA year fraction between start and end."""
        if start.year == end.year:
            denom = 366.0 if _is_leap_year(start.year) else 365.0
            return (end - start).days / denom

        # Cross-year period: split at Jan 1 of end.year
        boundary = date(end.year, 1, 1)
        first_part_days = (boundary - start).days
        first_part_denom = 366.0 if _is_leap_year(start.year) else 365.0
        second_part_days = (end - boundary).days
        second_part_denom = 366.0 if _is_leap_year(end.year) else 365.0

        # Multi-year periods: contribute full whole years between
        whole_years = end.year - start.year - 1
        return (
            first_part_days / first_part_denom
            + whole_years
            + second_part_days / second_part_denom
        )

    def name(self) -> str:
        """Return the stable short name for this convention."""
        return "ActualActualISDA"


_DAY_COUNT_BY_NAME: dict[str, type[DayCount]] = {
    "OneTwelfth": OneTwelfth,
    "Actual365Fixed": Actual365Fixed,
    "Actual360": Actual360,
    "Thirty360": Thirty360,
    "ActualActualISDA": ActualActualISDA,
}


def day_count_from_name(name: str) -> DayCount:
    """Resolve a day-count by canonical name. Used by canonical-form deserialisation."""
    cls = _DAY_COUNT_BY_NAME.get(name)
    if cls is None:
        suggestions = get_close_matches(name, list(_DAY_COUNT_BY_NAME), n=1, cutoff=0.5)
        hint = f" — did you mean '{suggestions[0]}'?" if suggestions else ""
        msg = f"unknown day-count '{name}'{hint}"
        raise ValueError(msg)
    return cls()


__all__ = [
    "Actual360",
    "Actual365Fixed",
    "ActualActualISDA",
    "DayCount",
    "OneTwelfth",
    "Thirty360",
    "day_count_from_name",
]
