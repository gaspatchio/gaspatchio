# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule typed primitive — period boundaries + day-count + calendar.

Two named constructors:
  - ``from_calendar_grid`` — shared grid for all policies; useful for cohort
    aggregation and SII reporting. Mid-month starts normalise to month-end by
    default to match US/UK/EU production practice.
  - ``from_inception`` — per-policy grid anchored on a column of inception
    dates. Anniversary semantics intrinsic.

Defaults and conventions:
  - Default convention: ``OneTwelfth + NullCalendar`` (matches ~80% of life
    insurance production).
  - Business-day default: ``Unadjusted`` with ``NullCalendar``,
    ``ModifiedFollowing`` with any real calendar.
  - Termination semantics: full-period; no partial-dt at lapse / contract
    boundary (not yet implemented).
  - Reporting-grid aggregation: not yet implemented.

``n_periods`` semantics:
  - ``period_dates_expr()`` returns lists of length ``n_periods + 1``
    (boundaries, inclusive of t=0 AND t=n).
  - ``year_fractions_expr()`` returns lists of length ``n_periods``
    (per-period widths).
  - ``anniversary_mask_expr()`` returns lists of length ``n_periods``
    (one bool per period).

When integrating with ``ActuarialFrame.date.create_timeline(
projection_end_value=N)``, which produces ``N + 1`` timeline steps, pass
``n_periods=N`` to ``Schedule.from_inception`` so that ``period_dates_expr``
returns ``N + 1`` boundaries that align with the timeline indices.
"""

from __future__ import annotations

import calendar as _stdlib_calendar
import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import polars as pl
from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

from gaspatchio_core._identity import canonical_bytes
from gaspatchio_core.schedule._business_day import BusinessDayConvention
from gaspatchio_core.schedule._calendar import Calendar, NullCalendar
from gaspatchio_core.schedule._day_count import DayCount, OneTwelfth

Anchor = Literal["month_end", "exact_date", "month_start", "year_end"]
Frequency = Literal["1M", "3M", "6M", "1Y", "1D", "1W"]

_SUPPORTED_FREQUENCIES: frozenset[str] = frozenset({"1M", "3M", "6M", "1Y", "1D", "1W"})

# Schedule frequency -> Polars `date_ranges` interval string (per_policy_grid).
_SCHED_FREQ_TO_INTERVAL: dict[str, str] = {
    "1M": "1mo",
    "3M": "3mo",
    "6M": "6mo",
    "1Y": "1y",
    "1W": "1w",
    "1D": "1d",
}

# Months spanned by one period, for the month-aligned frequencies. Lets the
# per-policy period count be computed by integer arithmetic instead of
# materialising a full date_ranges list just to take its length.
_SCHED_FREQ_MONTHS_PER_PERIOD: dict[str, int] = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}

# `until` semantics -> `dt.offset_by` unit suffix for the per-policy horizon.
_UNTIL_KIND_TO_OFFSET_UNIT: dict[str, str] = {"term_months": "mo", "term_years": "y"}

# Raised when end_date_column is passed to the in-force / boundary masks on a
# per_policy (jagged) schedule, where each policy's own horizon already bounds
# its projection — so a separate end date is both redundant and not honoured.
_PER_POLICY_END_DATE_MSG = (
    "end_date_column is not supported on per_policy (jagged) timelines: each "
    "policy's horizon already bounds its own projection. Model early "
    "termination via decrements, or build the projection with per_policy=False "
    "to use an explicit end_date_column boundary."
)

# Number of periods per frequency that constitute one contract anniversary (12 months).
_ANNIVERSARY_PERIODS: dict[str, int] = {
    "1Y": 1,
    "6M": 2,
    "3M": 4,
    "1M": 12,
    "1W": 52,
    "1D": 365,
}

# OneTwelfth year_fraction per period for month-aligned frequencies.
# 1W and 1D are intentionally absent — for those, the per-period count of
# month-boundary crossings depends on the inception date, so the fast path
# does not apply.
_ONETWELFTH_PER_PERIOD: dict[str, float] = {
    "1M": 1.0 / 12.0,
    "3M": 3.0 / 12.0,
    "6M": 6.0 / 12.0,
    "1Y": 1.0,
}


def _last_day_of_month(d: date) -> date:
    """Return the last calendar day of the month containing ``d``."""
    last = _stdlib_calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)


def _last_day_of_year(d: date) -> date:
    """Return Dec 31 of the year containing ``d``."""
    return date(d.year, 12, 31)


def _safe_anniversary(year: int, month: int, day: int) -> date:
    """Return ``date(year, month, day)``, or Feb 28 if Feb 29 in a non-leap year."""
    if month == 2 and day == 29 and not _stdlib_calendar.isleap(year):  # noqa: PLR2004
        return date(year, 2, 28)
    return date(year, month, day)


def _normalise_anchor(d: date, anchor: Anchor) -> date:
    """Return ``d`` shifted to the canonical anchor position within its period."""
    if anchor == "exact_date":
        return d
    if anchor == "month_end":
        return _last_day_of_month(d)
    if anchor == "month_start":
        return date(d.year, d.month, 1)
    if anchor == "year_end":
        return _last_day_of_year(d)
    msg = f"unsupported anchor {anchor!r}"
    raise ValueError(msg)


def _period_step_kwargs(frequency: Frequency) -> dict[str, int]:
    """Translate a frequency string into a ``relativedelta`` kwargs dict."""
    return {
        "1M": {"months": 1},
        "3M": {"months": 3},
        "6M": {"months": 6},
        "1Y": {"years": 1},
        "1D": {"days": 1},
        "1W": {"weeks": 1},
    }[frequency]


def _step_date(d: date, frequency: Frequency, anchor: Anchor) -> date:
    """Advance ``d`` by one period under ``frequency``.

    For monthly/yearly frequencies and a month-end / year-end anchor, the
    natural ``relativedelta`` rule already preserves the convention because
    Feb 28 + 1M = Mar 28, Mar 31 + 1M = Apr 30 (capped) — but to keep
    month-end stickiness we explicitly re-normalise to month-end after each
    step when the anchor demands it.
    """
    next_d: date = d + relativedelta(**_period_step_kwargs(frequency))
    if anchor == "month_end" and frequency in ("1M", "3M", "6M"):
        next_d = _last_day_of_month(next_d)
    if anchor == "year_end" and frequency == "1Y":
        next_d = _last_day_of_year(next_d)
    return next_d


def _default_convention(calendar: Calendar) -> BusinessDayConvention:
    """Return the context-dependent default business-day convention.

    ``NullCalendar`` → ``UNADJUSTED``; any real calendar → ``MODIFIED_FOLLOWING``.
    """
    if isinstance(calendar, NullCalendar):
        return BusinessDayConvention.UNADJUSTED
    return BusinessDayConvention.MODIFIED_FOLLOWING


def _build_period_offsets(
    frequency: Frequency,
    n_periods: int,
) -> list[relativedelta]:
    """Pre-compute the ``relativedelta`` offsets for each period boundary."""
    step = _period_step_kwargs(frequency)
    return [
        relativedelta(**{k: v * t for k, v in step.items()})
        for t in range(n_periods + 1)
    ]


def _offset_str(frequency: Frequency, i: int) -> str:
    """Return a Polars ``dt.offset_by`` duration string for period boundary ``i``.

    Maps a frequency + integer step count to the Polars offset string used
    in the vectorised :meth:`Schedule.period_dates_expr` fast path.

    Args:
        frequency: One of the supported schedule frequencies.
        i: Period index (0 = start = no offset, 1 = one period forward, …).

    Returns:
        A Polars-compatible offset string such as ``"3mo"``, ``"1y"``, ``"2w"``.
    """
    _freq_to_polars: dict[str, tuple[int, str]] = {
        "1M": (1, "mo"),
        "3M": (3, "mo"),
        "6M": (6, "mo"),
        "1Y": (1, "y"),
        "1W": (1, "w"),
        "1D": (1, "d"),
    }
    multiplier, unit = _freq_to_polars[frequency]
    return f"{multiplier * i}{unit}"


@dataclass(frozen=True)
class Schedule:
    """Typed schedule — periods, day-count, calendar, BD convention.

    Construct via :meth:`from_calendar_grid` (shared grid) or
    :meth:`from_inception` (per-policy column-anchored). Direct construction
    is intentionally awkward — use the classmethods.
    """

    n_periods: int
    frequency: Frequency
    calendar: Calendar
    convention: BusinessDayConvention
    day_count: DayCount
    anchor: Anchor
    # One of the next two is set; the other is None depending on constructor.
    start_date: date | None
    inception_column: str | None
    # Internal flag — distinguishes "from_calendar_grid" vs "from_inception"
    # vs "per_policy_grid" in canonical form without inferring from None-ness.
    _kind: Literal["from_calendar_grid", "from_inception", "per_policy_grid"] = field(
        default="from_calendar_grid"
    )
    # ``per_policy_grid`` only: shared ``start_date`` + per-policy horizon read
    # from a column. ``until_kind`` is the ``term_months`` / ``term_years``
    # semantics; ``until_value_column`` names the per-policy magnitude column.
    until_kind: str | None = None
    until_value_column: str | None = None

    @classmethod
    def from_calendar_grid(  # noqa: PLR0913
        cls,
        *,
        start_date: date,
        n_periods: int,
        frequency: Frequency,
        anchor: Anchor = "month_end",
        calendar: Calendar | None = None,
        convention: BusinessDayConvention | None = None,
        day_count: DayCount | None = None,
    ) -> Schedule:
        """Construct a shared schedule for all policies.

        Mid-month ``start_date`` is normalised per ``anchor`` (default: month-end)
        to match US/UK/EU production practice.
        """
        if frequency not in _SUPPORTED_FREQUENCIES:
            msg = (
                f"unsupported frequency {frequency!r};"
                f" expected one of {sorted(_SUPPORTED_FREQUENCIES)}"
            )
            raise ValueError(msg)

        cal: Calendar = calendar or NullCalendar()
        conv: BusinessDayConvention = convention or _default_convention(cal)
        dc: DayCount = day_count or OneTwelfth()
        normalised = _normalise_anchor(start_date, anchor)
        return cls(
            n_periods=n_periods,
            frequency=frequency,
            calendar=cal,
            convention=conv,
            day_count=dc,
            anchor=anchor,
            start_date=normalised,
            inception_column=None,
            _kind="from_calendar_grid",
        )

    @classmethod
    def from_inception(  # noqa: PLR0913
        cls,
        *,
        inception_column: str,
        n_periods: int,
        frequency: Frequency,
        calendar: Calendar | None = None,
        convention: BusinessDayConvention | None = None,
        day_count: DayCount | None = None,
    ) -> Schedule:
        """Per-policy schedule anchored on a column of inception dates.

        Each row gets its own period grid starting at ``inception_column[row]``.
        Anniversary semantics are intrinsic — the inception date IS the anchor,
        so no ``anchor`` parameter is accepted here.
        """
        if frequency not in _SUPPORTED_FREQUENCIES:
            msg = (
                f"unsupported frequency {frequency!r};"
                f" expected one of {sorted(_SUPPORTED_FREQUENCIES)}"
            )
            raise ValueError(msg)

        cal: Calendar = calendar or NullCalendar()
        conv: BusinessDayConvention = convention or _default_convention(cal)
        dc: DayCount = day_count or OneTwelfth()
        return cls(
            n_periods=n_periods,
            frequency=frequency,
            calendar=cal,
            convention=conv,
            day_count=dc,
            anchor="exact_date",  # placeholder — irrelevant for from_inception
            start_date=None,
            inception_column=inception_column,
            _kind="from_inception",
        )

    @classmethod
    def from_per_policy_grid(  # noqa: PLR0913
        cls,
        *,
        start_date: date,
        n_periods: int,
        frequency: Frequency,
        until_kind: str,
        until_value_column: str,
        calendar: Calendar | None = None,
        convention: BusinessDayConvention | None = None,
        day_count: DayCount | None = None,
    ) -> Schedule:
        """Per-policy *jagged* grid: shared ``start_date``, per-policy horizon.

        Every policy shares ``start_date`` but projects only as far as its own
        ``until_value_column`` (e.g. ``remaining_term_months``). Unlike
        :meth:`from_calendar_grid`, this yields **variable-length** list columns
        — a policy with 12 months left carries 13 boundary dates, not the
        portfolio-wide maximum. ``n_periods`` records the portfolio maximum for
        reference (e.g. error messages); per-row length comes from the column.

        Only ``term_months`` / ``term_years`` ``until_kind`` are supported.
        """
        if frequency not in _SUPPORTED_FREQUENCIES:
            msg = (
                f"unsupported frequency {frequency!r};"
                f" expected one of {sorted(_SUPPORTED_FREQUENCIES)}"
            )
            raise ValueError(msg)
        if until_kind not in _UNTIL_KIND_TO_OFFSET_UNIT:
            msg = (
                f"per_policy grids support until in "
                f"{sorted(_UNTIL_KIND_TO_OFFSET_UNIT)}, got {until_kind!r}"
            )
            raise ValueError(msg)

        cal: Calendar = calendar or NullCalendar()
        conv: BusinessDayConvention = convention or _default_convention(cal)
        dc: DayCount = day_count or OneTwelfth()
        return cls(
            n_periods=n_periods,
            frequency=frequency,
            calendar=cal,
            convention=conv,
            day_count=dc,
            anchor="exact_date",  # placeholder — start_date IS the anchor
            start_date=start_date,
            inception_column=None,
            _kind="per_policy_grid",
            until_kind=until_kind,
            until_value_column=until_value_column,
        )

    def per_policy_period_dates_expr(self) -> pl.Expr:
        """Return a variable-length List<Date> per row for a ``per_policy_grid``.

        Each policy's list runs from ``start_date`` to
        ``start_date + until_value_column`` (in ``until_kind`` units), inclusive
        of both endpoints — so a policy with horizon ``k`` periods gets ``k + 1``
        boundary dates. Built with vectorised ``pl.date_ranges`` (no Python
        per-row callbacks).
        """
        if self._kind != "per_policy_grid":
            msg = (
                "per_policy_period_dates_expr() is only valid for"
                " per_policy_grid schedules"
            )
            raise ValueError(msg)
        if self.start_date is None or self.until_value_column is None:
            msg = "per_policy_grid Schedule missing start_date/until_value_column"
            raise RuntimeError(msg)  # unreachable given constructor invariant

        start = pl.lit(self.start_date)
        unit = _UNTIL_KIND_TO_OFFSET_UNIT[self.until_kind or "term_months"]
        magnitude = pl.col(self.until_value_column).cast(pl.Int64)
        end = start.dt.offset_by(pl.concat_str([magnitude.cast(pl.Utf8), pl.lit(unit)]))
        interval = _SCHED_FREQ_TO_INTERVAL[self.frequency]
        return pl.date_ranges(start=start, end=end, interval=interval, closed="both")

    def per_policy_period_count_expr(self) -> pl.Expr:
        """Return each policy's period count (= boundaries - 1) for a jagged grid.

        Null-safe and non-negative: a null ``until_value`` yields a null date
        list and a negative one yields an empty list; both clamp to ``0``
        periods rather than underflowing the unsigned ``list.len()`` or
        propagating a null mask. Single source of truth for the per-policy
        length consumed by the in-force / boundary / year-fraction / anniversary
        expressions.
        """
        if self._kind != "per_policy_grid":
            msg = "per_policy_period_count_expr() is only valid for per_policy_grid"
            raise ValueError(msg)
        if self.until_value_column is None:
            msg = "per_policy_grid Schedule missing until_value_column"
            raise RuntimeError(msg)  # unreachable given constructor invariant
        # Arithmetic count — no date_ranges materialisation. The horizon is in
        # months (term_months) or years (term_years); per_policy_grid is only
        # built for month-aligned frequencies (1W/1D term_* are rejected at
        # set()). Null / negative terms clamp to 0 periods.
        months = pl.col(self.until_value_column).fill_null(0).cast(pl.Int64)
        if self.until_kind == "term_years":
            months = months * 12
        per_period = _SCHED_FREQ_MONTHS_PER_PERIOD[self.frequency]
        return (months // per_period).clip(lower_bound=0)

    def period_dates(self) -> list[date]:
        """Return the period boundary dates (length n_periods + 1).

        Only valid for ``from_calendar_grid`` schedules — per-policy grids
        produce a Polars expression, not a Python list (see
        :meth:`period_dates_expr`).
        """
        if self._kind != "from_calendar_grid":
            msg = (
                "period_dates() (a Python list) is only valid for "
                "from_calendar_grid schedules; use period_dates_expr() for "
                "from_inception, per_policy_period_dates_expr() for "
                "per_policy_grid (jagged), or the frame accessor "
                "af.projection.period_dates() which dispatches for any kind."
            )
            raise ValueError(msg)
        if self.start_date is None:
            msg = "from_calendar_grid Schedule has no start_date"
            raise RuntimeError(msg)  # unreachable given _kind invariant
        start = self.convention.adjust(self.start_date, self.calendar)
        out: list[date] = [start]
        d = start
        for _ in range(self.n_periods):
            d = _step_date(d, self.frequency, self.anchor)
            d = self.convention.adjust(d, self.calendar)
            out.append(d)
        return out

    def period_dates_expr(self) -> pl.Expr:
        """Return a Polars expression yielding a List<Date> per row.

        Each row's list has length ``n_periods + 1`` (boundaries inclusive of
        t=0 and t=n_periods).

        Fast path (UNADJUSTED + NullCalendar — the actuarial default):
            Uses vectorised ``pl.concat_list`` + ``dt.offset_by`` — pure Rust,
            no Python callbacks. This eliminates ``MAP_ELEMENTS_PERFORMANCE_ISSUE``
            warnings for the ~80% of life-insurance models that use the default.

        Slow path (real calendar OR non-UNADJUSTED convention):
            Falls back to ``map_elements`` with per-element business-day
            adjustment. BD adjustment is genuinely per-element and cannot be
            trivially vectorised within Polars expressions.
        """
        if self._kind != "from_inception":
            msg = (
                "period_dates_expr() is only valid for from_inception schedules;"
                " use period_dates() for from_calendar_grid, "
                "per_policy_period_dates_expr() for per_policy_grid (jagged), or "
                "the frame accessor af.projection.period_dates() for any kind."
            )
            raise ValueError(msg)
        if self.inception_column is None:
            msg = "from_inception Schedule has no inception_column"
            raise RuntimeError(msg)  # unreachable given _kind invariant

        if self.convention is BusinessDayConvention.UNADJUSTED and isinstance(
            self.calendar, NullCalendar
        ):
            # Fast path: vectorised offset_by + concat_list.
            # Each pl.col().dt.offset_by() is a native Rust pass; concat_list
            # assembles them into a List<Date> column. Zero Python per-row calls.
            return pl.concat_list(
                [
                    pl.col(self.inception_column).dt.offset_by(
                        _offset_str(self.frequency, i)
                    )
                    for i in range(self.n_periods + 1)
                ]
            )

        # Slow path: per-element BD adjustment via map_elements.
        # Business-day adjustment is genuinely row- and element-specific —
        # it cannot be expressed as a simple broadcast without materialising
        # each adjusted date individually.
        offsets = _build_period_offsets(self.frequency, self.n_periods)

        def _expand_row(d: date | None) -> list[date]:
            if d is None:
                return []
            out = [d + off for off in offsets]
            out = [self.convention.adjust(x, self.calendar) for x in out]
            return out

        return pl.col(self.inception_column).map_elements(
            _expand_row, return_dtype=pl.List(pl.Date)
        )

    def year_fractions(self) -> list[float]:
        """Return the per-period year-fraction series under this Schedule's day-count.

        Length: ``n_periods``. Only valid for ``from_calendar_grid`` schedules.
        """
        if self._kind != "from_calendar_grid":
            msg = (
                "year_fractions() is only valid for from_calendar_grid schedules;"
                " use year_fractions_expr() for from_inception"
            )
            raise ValueError(msg)
        boundaries = self.period_dates()
        return [
            self.day_count.year_fraction(boundaries[t], boundaries[t + 1])
            for t in range(self.n_periods)
        ]

    def year_fractions_expr(self) -> pl.Expr:
        """Return a Polars expression yielding a List<Float64> dt[t] series per row.

        Length per row: ``n_periods``. Only valid for ``from_inception`` schedules.

        Fast path (OneTwelfth day-count):
            ``OneTwelfth`` returns exactly ``1/12`` per period regardless of the
            actual dates, so the result is row-invariant. Returns a broadcast
            literal — zero Python per-row calls.

        Slow path (all other day-counts):
            Act/Act ISDA, Act/365F, Act/360, Thirty360, etc. all depend on the
            actual period boundary dates and are computed via ``map_elements``.
        """
        if self._kind not in ("from_inception", "per_policy_grid"):
            msg = (
                "year_fractions_expr() is only valid for from_inception or"
                " per_policy_grid schedules; use year_fractions() for"
                " from_calendar_grid"
            )
            raise ValueError(msg)

        if (
            isinstance(self.day_count, OneTwelfth)
            and self.frequency in _ONETWELFTH_PER_PERIOD
        ):
            # Fast path: OneTwelfth on a month-aligned frequency is per-period
            # constant (months_in_period / 12); 1W and 1D depend on boundary
            # dates and fall through to the slow path.
            per_period = _ONETWELFTH_PER_PERIOD[self.frequency]
            if self._kind == "per_policy_grid":
                # Per-policy length -> build the constant list per row.
                return pl.int_ranges(
                    0, self.per_policy_period_count_expr()
                ).list.eval(pl.lit(per_period))
            return pl.lit([per_period] * self.n_periods, dtype=pl.List(pl.Float64))

        # Slow path: day-count depends on actual boundary dates. The jagged grid
        # yields variable-length boundary lists; the map handles both.
        period_dates_e = (
            self.per_policy_period_dates_expr()
            if self._kind == "per_policy_grid"
            else self.period_dates_expr()
        )
        dc = self.day_count

        def _list_to_yfs(boundaries: list[date]) -> list[float]:
            return [
                dc.year_fraction(boundaries[t], boundaries[t + 1])
                for t in range(len(boundaries) - 1)
            ]

        return period_dates_e.map_elements(
            _list_to_yfs, return_dtype=pl.List(pl.Float64)
        )

    def cumulative_year_fractions(self) -> list[float]:
        """Return cumulative year fractions ``[0, yf[0], yf[0]+yf[1], ..., sum]``.

        Length: ``n_periods + 1``. Useful for feeding ``Curve.discount_factor(t)``
        where ``t`` is the year fraction from the schedule start to each period
        boundary.

        ``from_calendar_grid`` only — for per-policy schedules, accumulate over
        ``year_fractions_expr()`` within a Polars expression context.

        Returns:
            A list of length ``n_periods + 1`` where index 0 is always ``0.0``
            and index ``k`` is the cumulative year fraction from the schedule
            start through the end of period ``k``.

        Raises:
            ValueError: If called on a ``from_inception`` schedule.

        Example::

            >>> from datetime import date
            >>> sched = Schedule.from_calendar_grid(
            ...     start_date=date(2025, 1, 31), n_periods=3, frequency="1M"
            ... )
            >>> sched.cumulative_year_fractions()
            [0.0, 0.08333333333333333, 0.16666666666666666, 0.25]

        """
        if self._kind != "from_calendar_grid":
            msg = (
                "cumulative_year_fractions() is only valid for from_calendar_grid;"
                " for from_inception use accumulate over year_fractions_expr()"
            )
            raise ValueError(msg)
        yfs = self.year_fractions()
        out: list[float] = [0.0]
        running = 0.0
        for yf in yfs:
            running += yf
            out.append(running)
        return out

    def _anniversary_period_count(self) -> int:
        """Return how many periods constitute one contract anniversary (12 months).

        Raises ``AssertionError`` if ``self.frequency`` is not in
        :data:`_ANNIVERSARY_PERIODS` — which cannot happen for valid ``Schedule``
        instances because :meth:`from_calendar_grid` and :meth:`from_inception`
        both validate against ``_SUPPORTED_FREQUENCIES``.
        """
        count = _ANNIVERSARY_PERIODS.get(self.frequency)
        if count is None:
            msg = f"unhandled frequency {self.frequency!r}"
            raise AssertionError(msg)
        return count

    def anniversary_mask(self) -> list[bool]:
        """Return a boolean list marking end-of-period contract anniversaries.

        Index ``t`` is ``True`` when period ``t + 1`` closes a full 12-month
        anniversary from the schedule start date.

        ``from_calendar_grid`` only — for per-policy schedules use
        :meth:`anniversary_mask_expr`.

        Returns:
            A list of length ``n_periods`` where ``True`` marks anniversary
            periods.

        Raises:
            ValueError: If called on a ``from_inception`` schedule.

        Example::

            >>> from datetime import date
            >>> sched = Schedule.from_calendar_grid(
            ...     start_date=date(2025, 1, 31), n_periods=24, frequency="1M"
            ... )
            >>> mask = sched.anniversary_mask()
            >>> mask[11], mask[23]
            (True, True)
            >>> mask[0], mask[10]
            (False, False)

        """
        if self._kind != "from_calendar_grid":
            msg = (
                "anniversary_mask() is only valid for from_calendar_grid schedules;"
                " use anniversary_mask_expr() for from_inception"
            )
            raise ValueError(msg)
        step = self._anniversary_period_count()
        return [(t + 1) % step == 0 for t in range(self.n_periods)]

    def anniversary_mask_expr(self) -> pl.Expr:
        """Return a per-row boolean list expression marking contract anniversaries.

        The mask is purely structural — it depends only on ``n_periods`` and
        ``frequency``, not on each row's inception date — so the same list is
        broadcast to every row.

        ``from_inception`` only — for shared-grid schedules use
        :meth:`anniversary_mask`.

        Returns:
            A Polars expression of type ``List<Boolean>`` with length
            ``n_periods`` per row, where ``True`` marks anniversary periods.

        Raises:
            ValueError: If called on a ``from_calendar_grid`` schedule.

        """
        if self._kind == "per_policy_grid":
            step = self._anniversary_period_count()
            # Same structural rule (t+1) % step == 0, over each policy's own
            # variable-length period count.
            return pl.int_ranges(0, self.per_policy_period_count_expr()).list.eval(
                ((pl.element() + 1) % step) == 0
            )

        if self._kind != "from_inception":
            msg = (
                "anniversary_mask_expr() is only valid for from_inception schedules;"
                " use anniversary_mask() for from_calendar_grid"
            )
            raise ValueError(msg)
        if self.inception_column is None:
            msg = "from_inception Schedule has no inception_column"
            raise RuntimeError(msg)  # unreachable given _kind invariant
        step = self._anniversary_period_count()
        n = self.n_periods
        mask = [(t + 1) % step == 0 for t in range(n)]
        # The mask is purely structural — it depends only on n_periods and
        # frequency, not on each row's inception date. Broadcast as a literal
        # so every row receives the same list with zero Python per-row calls.
        return pl.lit(mask, dtype=pl.List(pl.Boolean))

    def next_anniversary_date(
        self,
        *,
        inception: date,
        valuation_date: date,
        n: int = 1,
    ) -> date:
        """Return the Nth contract anniversary on/after ``valuation_date``.

        Anchored on ``inception``. Anniversaries are calendar-month-day matches.
        Feb 29 inceptions in non-leap target years fall to Feb 28.

        Only valid for ``from_inception`` schedules — ``from_calendar_grid`` has
        no per-policy anchor.

        Args:
            inception: The contract inception date for one policy.
            valuation_date: The reference date; the returned anniversary is
                on or after this date.
            n: 1 = next anniversary on/after valuation; 2 = anniversary after
                that; etc. Must be >= 1.

        Returns:
            The anniversary date. May equal ``valuation_date`` if that day is
            itself an anniversary.

        Raises:
            ValueError: If ``n < 1`` or if the schedule is not ``from_inception``.

        Example::

            >>> from datetime import date
            >>> sched = Schedule.from_inception(
            ...     inception_column="policy_inception",
            ...     n_periods=120,
            ...     frequency="1M",
            ... )
            >>> sched.next_anniversary_date(
            ...     inception=date(2020, 6, 15),
            ...     valuation_date=date(2025, 1, 1),
            ...     n=1,
            ... )
            datetime.date(2025, 6, 15)

        """
        if self._kind != "from_inception":
            msg = "next_anniversary_date is only valid for from_inception schedules"
            raise ValueError(msg)
        if n < 1:
            msg = f"n must be >= 1, got {n}"
            raise ValueError(msg)

        # Find the most recent anniversary on/before valuation_date,
        # then add (n) full years on top.
        val_year = valuation_date.year
        incep_month = inception.month
        incep_day = inception.day

        # Candidate anniversary in val_year. If it's on/after valuation, that's
        # the "next" anniversary — add (n-1) more years; otherwise add n.
        candidate = _safe_anniversary(val_year, incep_month, incep_day)
        years_to_add = n - 1 if candidate >= valuation_date else n
        return _safe_anniversary(val_year + years_to_add, incep_month, incep_day)

    def is_in_force_expr(
        self,
        *,
        end_date_column: str | None = None,
    ) -> pl.Expr:
        """Return a per-row boolean list expression marking in-force periods.

        Length per row: ``n_periods``. ``True`` at index ``t`` means period ``t``
        is in force (the contract has not yet terminated).

        Args:
            end_date_column: For ``from_inception`` schedules, optional column
                name holding each policy's end date. If provided, periods whose
                end-of-period date falls strictly after this date are False.
                If a row's end date is null, that row is treated as still in
                force — all periods True. If omitted entirely, all periods are
                True for every row. Ignored for ``from_calendar_grid`` schedules
                (which have no per-policy boundary).

        Returns:
            A Polars expression of type ``List<Boolean>`` with length
            ``n_periods`` per row.

        """
        n = self.n_periods

        # Zero-period schedule: empty list regardless of branch. Avoids
        # pl.concat_list([]) crashing at collect time on the per-policy path.
        if n == 0:
            return pl.lit([], dtype=pl.List(pl.Boolean))

        if self._kind == "per_policy_grid":
            if end_date_column is not None:
                raise ValueError(_PER_POLICY_END_DATE_MSG)
            # Jagged: each policy projects only its own horizon, so every period
            # in its variable-length timeline is in force -> all-True of
            # per-policy length.
            return pl.int_ranges(0, self.per_policy_period_count_expr()).list.eval(
                pl.lit(True)  # noqa: FBT003
            )

        if self._kind == "from_calendar_grid":
            # No per-policy end — broadcast a uniform True mask
            mask = [True] * n
            return pl.lit(mask, dtype=pl.List(pl.Boolean))

        # from_inception path
        if end_date_column is None:
            # No end specified — uniform True mask
            mask = [True] * n
            return pl.lit(mask, dtype=pl.List(pl.Boolean))

        if self.inception_column is None:
            msg = "from_inception Schedule has no inception_column"
            raise RuntimeError(msg)  # unreachable given _kind invariant

        # Compute per-period end dates: incep + offset_str(frequency, t+1)
        # for t in 0..n-1, then compare each to the policy's end_date.
        incep_col = pl.col(self.inception_column)
        period_end_exprs = [
            incep_col.dt.offset_by(_offset_str(self.frequency, t + 1)) for t in range(n)
        ]
        end_col = pl.col(end_date_column)
        # For each period: True if its end-of-period date <= policy end_date.
        # A null end date means the contract is still in force (no termination
        # known) — coalesce to True so downstream rollforward boundary masks
        # are not silently corrupted by null elements.
        mask_exprs = [(pe <= end_col).fill_null(True) for pe in period_end_exprs]  # noqa: FBT003
        return pl.concat_list(mask_exprs)

    def contract_boundary_expr(
        self,
        *,
        end_date_column: str | None = None,
    ) -> pl.Expr:
        """Return a per-row boolean list expression marking termination (boundary).

        Length per row: ``n_periods``. ``True`` at index ``t`` means period ``t``
        is the contract-boundary period — the rollforward kernel zeroes this
        period and every later period.

        This is the **negation** of :meth:`is_in_force_expr`. The kernel uses
        boundary semantics (True = terminate); :meth:`is_in_force_expr` is
        natural for non-kernel code (True = active).

        Args:
            end_date_column: For ``from_inception`` schedules, optional column
                name holding each policy's end date. If provided, periods whose
                end-of-period date falls strictly after this date are True
                (terminated). If a row's end date is null, that row is treated
                as still in force — all False. If omitted entirely, all
                periods are False (no termination — feed unbounded projections).
                Ignored for ``from_calendar_grid`` schedules (which have no
                per-policy boundary).

        Returns:
            A Polars expression of type ``List<Boolean>`` with length
            ``n_periods`` per row.
        """
        n = self.n_periods

        if n == 0:
            return pl.lit([], dtype=pl.List(pl.Boolean))

        if self._kind == "per_policy_grid":
            if end_date_column is not None:
                raise ValueError(_PER_POLICY_END_DATE_MSG)
            # Jagged: the timeline already stops at each policy's horizon -> no
            # period is a contract boundary; all-False of per-policy length.
            return pl.int_ranges(0, self.per_policy_period_count_expr()).list.eval(
                pl.lit(False)  # noqa: FBT003
            )

        if self._kind == "from_calendar_grid":
            # No per-policy end — uniform False mask (no termination)
            mask = [False] * n
            return pl.lit(mask, dtype=pl.List(pl.Boolean))

        # from_inception path
        if end_date_column is None:
            # No end specified — uniform False mask
            mask = [False] * n
            return pl.lit(mask, dtype=pl.List(pl.Boolean))

        if self.inception_column is None:
            msg = "from_inception Schedule has no inception_column"
            raise RuntimeError(msg)  # unreachable given _kind invariant

        # period_end[t] = inception + offset_str(frequency, t+1)
        incep_col = pl.col(self.inception_column)
        end_col = pl.col(end_date_column)
        # Boundary fires at periods where end-of-period date > policy end date.
        # Null end_col → treat as still in force → False (no boundary).
        period_end_exprs = [
            incep_col.dt.offset_by(_offset_str(self.frequency, t + 1)) for t in range(n)
        ]
        mask_exprs = [(pe > end_col).fill_null(False) for pe in period_end_exprs]  # noqa: FBT003
        return pl.concat_list(mask_exprs)

    def canonical_form(self) -> dict[str, Any]:
        """Return the JSON-encodable canonical form of this Schedule.

        This is the structural recipe identity — two Schedules with the same
        canonical form produce the same per-row dt[t] series for any row data.

        Returns:
            A dict with string/int values encoding all schedule parameters.
            The ``kind`` key distinguishes ``from_calendar_grid`` (which also
            includes ``anchor`` and ``start_date``) from ``from_inception``
            (which includes ``inception_column``).

        Example::

            >>> from datetime import date
            >>> sched = Schedule.from_calendar_grid(
            ...     start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
            ... )
            >>> cf = sched.canonical_form()
            >>> cf["kind"]
            'from_calendar_grid'
            >>> cf["calendar"]
            'NullCalendar'

        """
        common: dict[str, Any] = {
            "kind": self._kind,
            "n_periods": self.n_periods,
            "frequency": self.frequency,
            "calendar": self.calendar.name(),
            "convention": self.convention.canonical_name(),
            "day_count": self.day_count.name(),
        }
        if self._kind == "per_policy_grid":
            if self.start_date is None or self.until_value_column is None:
                msg = "per_policy_grid Schedule missing start_date/until_value_column"
                raise RuntimeError(msg)  # unreachable given _kind invariant
            common["start_date"] = self.start_date.isoformat()
            common["until_kind"] = self.until_kind
            common["until_value_column"] = self.until_value_column
            return common
        if self._kind == "from_calendar_grid":
            if self.start_date is None:
                msg = "from_calendar_grid Schedule has no start_date"
                raise RuntimeError(msg)  # unreachable given _kind invariant
            common["anchor"] = self.anchor
            common["start_date"] = self.start_date.isoformat()
            return common
        # from_inception branch
        if self.inception_column is None:
            msg = "from_inception Schedule has no inception_column"
            raise RuntimeError(msg)  # unreachable given _kind invariant
        common["inception_column"] = self.inception_column
        return common

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        Used by :func:`action_key` (Sub-plan D) to fold typed-input identity
        into the run-identity envelope. Two schedules with the same
        :meth:`canonical_form` always produce the same sha; any parameter
        difference (including constructor kind) produces a different sha.

        Returns:
            A string of the form ``sha256:<64 hex chars>``.

        Example::

            >>> from datetime import date
            >>> sched = Schedule.from_calendar_grid(
            ...     start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
            ... )
            >>> sha = sched.source_sha()
            >>> sha.startswith("sha256:")
            True
            >>> len(sha) == len("sha256:") + 64
            True

        """
        digest = hashlib.sha256(canonical_bytes(self.canonical_form())).hexdigest()
        return f"sha256:{digest}"


__all__ = ["Schedule"]
