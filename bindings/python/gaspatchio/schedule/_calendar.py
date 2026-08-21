# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Calendar typed primitive — holiday-aware business-day predicate.

Four built-in calendars are shipped: NullCalendar (default — every day
is a business day, matches VM-20/VM-21/IFRS 17 production practice),
TARGET (Eurozone), UnitedKingdom, and UnitedStates. JointCalendar and
BespokeCalendar are escape hatches for non-curated cases.
"""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import get_close_matches
from typing import TYPE_CHECKING

import holidays as _hols  # python-holidays

if TYPE_CHECKING:
    from datetime import date

# Saturday=5, Sunday=6
_WEEKEND_START_WEEKDAY = 5


class Calendar(ABC):
    """Abstract calendar. Concrete subclasses define holiday membership."""

    @abstractmethod
    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a business day under this calendar."""

    @abstractmethod
    def name(self) -> str:
        """Stable short name used in canonical-form fingerprinting."""


@dataclass(frozen=True)
class NullCalendar(Calendar):
    """Every day is a business day.

    Matches US VM-20/VM-21, UK/EU SII, and IFRS 17 production practice
    where premium-due, lapse, and death dates are *not* adjusted for
    weekends or holidays. Default in :class:`Schedule`.
    """

    def is_business_day(self, d: date) -> bool:  # noqa: ARG002 — every day is a business day
        """Return True unconditionally — NullCalendar has no holidays."""
        return True

    def name(self) -> str:
        """Return the stable canonical name for fingerprinting."""
        return "NullCalendar"


@functools.lru_cache(maxsize=4)
def _ecb_holidays_for_years(start_year: int, end_year: int) -> frozenset[date]:
    """Return TARGET2 closing days for the given year range.

    Cached — building the holiday set is non-trivial. Returns a frozenset
    so the result is hashable and cache-safe.
    """
    h: set[date] = set()
    for year in range(start_year, end_year + 1):
        h.update(_hols.financial_holidays("ECB", years=year))
    return frozenset(h)


@dataclass(frozen=True)
class TARGET(Calendar):
    """TARGET2 / Eurozone settlement calendar.

    Uses the python-holidays ECB / TARGET2 closing-day list:
    Jan 1, Good Friday, Easter Monday, May 1 (Labour Day),
    Dec 25 (Christmas), Dec 26 (Boxing Day).
    """

    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a TARGET2 business day."""
        if d.weekday() >= _WEEKEND_START_WEEKDAY:
            return False
        return d not in _ecb_holidays_for_years(d.year, d.year)

    def name(self) -> str:
        """Return the stable canonical name for fingerprinting."""
        return "TARGET"


@functools.lru_cache(maxsize=64)
def _uk_holidays_for_year(year: int) -> frozenset[date]:
    """Return England-and-Wales bank holidays for ``year``.

    Cached — building the holiday set is non-trivial. Returns a frozenset
    so the result is hashable and cache-safe.
    """
    return frozenset(_hols.country_holidays("GB", subdiv="ENG", years=year).keys())


@dataclass(frozen=True)
class UnitedKingdom(Calendar):
    """UK calendar — England-and-Wales bank holidays."""

    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a UK business day."""
        if d.weekday() >= _WEEKEND_START_WEEKDAY:
            return False
        return d not in _uk_holidays_for_year(d.year)

    def name(self) -> str:
        """Return the stable canonical name for fingerprinting."""
        return "UnitedKingdom"


@functools.lru_cache(maxsize=64)
def _us_holidays_for_year(year: int) -> frozenset[date]:
    """Return US federal holidays for ``year``.

    Cached — building the holiday set is non-trivial. Returns a frozenset
    so the result is hashable and cache-safe.
    """
    return frozenset(_hols.country_holidays("US", years=year).keys())


@dataclass(frozen=True)
class UnitedStates(Calendar):
    """US federal holiday calendar.

    Used for asset-side cashflow modelling. Liability-side projections
    typically use NullCalendar (no business-day adjustment).
    """

    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a US federal business day."""
        if d.weekday() >= _WEEKEND_START_WEEKDAY:
            return False
        return d not in _us_holidays_for_year(d.year)

    def name(self) -> str:
        """Return the stable canonical name for fingerprinting."""
        return "UnitedStates"


@dataclass(frozen=True)
class JointCalendar(Calendar):
    """Two-calendar union — a date is a holiday if it's a holiday in *either*."""

    left: Calendar
    right: Calendar

    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a business day in both constituent calendars."""
        return self.left.is_business_day(d) and self.right.is_business_day(d)

    def name(self) -> str:
        """Return the stable canonical name combining both constituent calendar names.

        Format: ``Joint(<left>,<right>)``.
        """
        return f"Joint({self.left.name()},{self.right.name()})"


@dataclass(frozen=True)
class BespokeCalendar(Calendar):
    """User-defined holiday set. Use ``label`` to give canonical-form a stable name."""

    holidays: frozenset[date]
    label: str | None = None

    def is_business_day(self, d: date) -> bool:
        """Return True iff ``d`` is a weekday not in the user-supplied holiday set."""
        if d.weekday() >= _WEEKEND_START_WEEKDAY:
            return False
        return d not in self.holidays

    def name(self) -> str:
        """Return the stable canonical name, including the label if one is set."""
        return f"Bespoke[{self.label}]" if self.label else "Bespoke"


_CALENDAR_BY_NAME: dict[str, type[Calendar]] = {
    "NullCalendar": NullCalendar,
    "TARGET": TARGET,
    "UnitedKingdom": UnitedKingdom,
    "UnitedStates": UnitedStates,
}


def calendar_from_name(name: str) -> Calendar:
    """Resolve a curated calendar by canonical name.

    Joint and Bespoke calendars are not in the curated set — they must be
    reconstructed from their structural args, which is the canonical form's job.
    """
    cls = _CALENDAR_BY_NAME.get(name)
    if cls is None:
        suggestions = get_close_matches(name, list(_CALENDAR_BY_NAME), n=1, cutoff=0.5)
        hint = f" — did you mean '{suggestions[0]}'?" if suggestions else ""
        msg = f"unknown calendar '{name}'{hint}"
        raise ValueError(msg)
    return cls()


__all__ = [
    "TARGET",
    "BespokeCalendar",
    "Calendar",
    "JointCalendar",
    "NullCalendar",
    "UnitedKingdom",
    "UnitedStates",
    "calendar_from_name",
]
