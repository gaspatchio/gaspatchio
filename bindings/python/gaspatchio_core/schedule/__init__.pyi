# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from datetime import date
from enum import Enum
from typing import Any, Literal

import polars as pl

class DayCount(ABC):
    @abstractmethod
    def year_fraction(self, start: date, end: date) -> float: ...
    @abstractmethod
    def name(self) -> str: ...

class OneTwelfth(DayCount):
    def year_fraction(self, start: date, end: date) -> float: ...
    def name(self) -> str: ...

class Actual365Fixed(DayCount):
    def year_fraction(self, start: date, end: date) -> float: ...
    def name(self) -> str: ...

class Actual360(DayCount):
    def year_fraction(self, start: date, end: date) -> float: ...
    def name(self) -> str: ...

class Thirty360(DayCount):
    def year_fraction(self, start: date, end: date) -> float: ...
    def name(self) -> str: ...

class ActualActualISDA(DayCount):
    def year_fraction(self, start: date, end: date) -> float: ...
    def name(self) -> str: ...

def day_count_from_name(name: str) -> DayCount: ...

class BusinessDayConvention(Enum):
    UNADJUSTED = "Unadjusted"
    FOLLOWING = "Following"
    MODIFIED_FOLLOWING = "ModifiedFollowing"
    PRECEDING = "Preceding"
    def canonical_name(self) -> str: ...
    def adjust(self, d: date, calendar: Calendar | None) -> date: ...

class Calendar(ABC):
    @abstractmethod
    def is_business_day(self, d: date) -> bool: ...
    @abstractmethod
    def name(self) -> str: ...

class NullCalendar(Calendar):
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

class TARGET(Calendar):
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

class UnitedKingdom(Calendar):
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

class UnitedStates(Calendar):
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

class JointCalendar(Calendar):
    left: Calendar
    right: Calendar
    def __init__(self, left: Calendar, right: Calendar) -> None: ...
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

class BespokeCalendar(Calendar):
    holidays: frozenset[date]
    label: str | None
    def __init__(self, holidays: frozenset[date], label: str | None = ...) -> None: ...
    def is_business_day(self, d: date) -> bool: ...
    def name(self) -> str: ...

def calendar_from_name(name: str) -> Calendar: ...

class Schedule:
    n_periods: int
    frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"]
    calendar: Calendar
    convention: BusinessDayConvention
    day_count: DayCount
    anchor: Literal["month_end", "exact_date", "month_start", "year_end"]
    start_date: date | None
    inception_column: str | None
    _kind: Literal["from_calendar_grid", "from_inception", "per_policy_grid"]
    until_kind: str | None
    until_value_column: str | None
    def __init__(
        self,
        n_periods: int,
        frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"],
        calendar: Calendar,
        convention: BusinessDayConvention,
        day_count: DayCount,
        anchor: Literal["month_end", "exact_date", "month_start", "year_end"],
        start_date: date | None,
        inception_column: str | None,
        _kind: Literal["from_calendar_grid", "from_inception", "per_policy_grid"] = ...,
        until_kind: str | None = ...,
        until_value_column: str | None = ...,
    ) -> None: ...
    @classmethod
    def from_calendar_grid(
        cls,
        *,
        start_date: date,
        n_periods: int,
        frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"],
        anchor: Literal["month_end", "exact_date", "month_start", "year_end"] = ...,
        calendar: Calendar | None = ...,
        convention: BusinessDayConvention | None = ...,
        day_count: DayCount | None = ...,
    ) -> Schedule: ...
    @classmethod
    def from_inception(
        cls,
        *,
        inception_column: str,
        n_periods: int,
        frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"],
        calendar: Calendar | None = ...,
        convention: BusinessDayConvention | None = ...,
        day_count: DayCount | None = ...,
    ) -> Schedule: ...
    @classmethod
    def from_per_policy_grid(
        cls,
        *,
        start_date: date,
        n_periods: int,
        frequency: Literal["1M", "3M", "6M", "1Y", "1D", "1W"],
        until_kind: str,
        until_value_column: str,
        calendar: Calendar | None = ...,
        convention: BusinessDayConvention | None = ...,
        day_count: DayCount | None = ...,
    ) -> Schedule: ...
    def period_dates(self) -> list[date]: ...
    def per_policy_period_dates_expr(self) -> pl.Expr: ...
    def per_policy_period_count_expr(self) -> pl.Expr: ...
    def period_dates_expr(self) -> pl.Expr: ...
    def year_fractions(self) -> list[float]: ...
    def year_fractions_expr(self) -> pl.Expr: ...
    def cumulative_year_fractions(self) -> list[float]: ...
    def anniversary_mask(self) -> list[bool]: ...
    def anniversary_mask_expr(self) -> pl.Expr: ...
    def next_anniversary_date(
        self,
        *,
        inception: date,
        valuation_date: date,
        n: int = ...,
    ) -> date: ...
    def is_in_force_expr(
        self,
        *,
        end_date_column: str | None = ...,
    ) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...

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
