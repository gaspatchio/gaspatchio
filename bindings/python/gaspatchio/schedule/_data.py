# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Read-only Schedule data and calculations shared by authoring and execution."""

from __future__ import annotations

import calendar as _stdlib_calendar
import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any, Final, Literal, NoReturn

from dateutil.relativedelta import relativedelta

from gaspatchio._identity import SHA256_PREFIX, canonical_bytes
from gaspatchio.schedule._business_day import BusinessDayConvention
from gaspatchio.schedule._calendar import Calendar, NullCalendar
from gaspatchio.schedule._day_count import OneTwelfth

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.schedule._day_count import DayCount

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

# The per-policy horizon measured in whole years from each policy's issue age
# to a maximum age: ``until_value - issue_age``, the age written as a number
# (``maximum_age``), read from a column (``until_value_column``) or computed
# by an expression (``until_value_expr``). Each policy runs to its own age, so
# its value never depends on which other policies share its run.
MAXIMUM_AGE: Final = "maximum_age"

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


# The cadences OneTwelfth cannot measure, in the words a refusal uses, and the
# constructor each schedule kind is rebuilt with.
_SUB_MONTH_CADENCE: dict[str, tuple[str, str]] = {
    "1W": ("weekly", "a week"),
    "1D": ("daily", "a day"),
}
_CONSTRUCTOR_OF_KIND: dict[str, str] = {
    "from_calendar_grid": "from_calendar_grid",
    "from_inception": "from_inception",
    "per_policy_grid": "from_per_policy_grid",
}

# The schedule kind with no calendar under it: ``n_periods`` steps of a fixed
# number of years, written as the step (``step_years``) or as the steps a year
# make (``steps_per_year``).
FIXED_STEP: Final = "fixed_step"

# Where a step is a whole number of calendar months -- 12, 6, 4, 3, 2 or 1 a
# year -- and a ``month`` index is therefore honest. 0.1 years is 1.2 months.
_WHOLE_MONTH_STEPS_PER_YEAR: Final[frozenset[int]] = frozenset({1, 2, 3, 4, 6, 12})
_MONTHS_IN_A_YEAR: Final = 12


def _fixed_step_spelling(schedule: ScheduleData) -> str:
    """Return the step as the model wrote it, for a refusal to quote."""
    if schedule.steps_per_year is not None:
        return f"steps_per_year={schedule.steps_per_year}"
    return f"step_years={schedule.step_years!r}"


def refuse_dates_on_a_fixed_step(what: str) -> NoReturn:
    """Refuse a calendar reading of an axis that has no calendar under it.

    Args:
        what: The reading asked for, as the model wrote it.

    Raises:
        ValueError: Always -- a fixed-step axis has no dates to give.

    """
    msg = (
        f"{what} on a fixed-step axis: a step axis has no calendar. Its "
        "boundaries are k steps of a fixed number of years, not dates, so "
        "there are no period dates, start or end date, or day count to give. "
        "For dated periods, project on a calendar cadence: "
        "af.projection.set(start_date=..., n_periods=..., "
        'frequency="monthly"). Time along a step axis is '
        "af.projection.t_years()."
    )
    raise ValueError(msg)


def fixed_step_boundary_years(schedule: ScheduleData) -> list[float]:
    """Return the time in years at each of a fixed-step axis's ``T + 1`` boundaries.

    ``k * step_years`` or ``k / steps_per_year``: one IEEE operation per
    boundary, never a running sum. The two spellings differ in the last bits
    -- ``k / 12`` and ``k * (1 / 12)`` part company in 324 of 976 boundaries,
    ``k * 0.1`` and ``k / 10`` in 1,002 of 2,948 -- and a workbook's time
    column is written one way or the other (``x + A/12``, ``x + A*h``), so the
    spelling the model chose is the one reproduced.
    """
    if schedule.steps_per_year is not None:
        per_year = schedule.steps_per_year
        count = schedule._shared_period_count()  # noqa: SLF001
        return [k / per_year for k in range(count + 1)]
    if schedule.step_years is None:  # pragma: no cover - constructor invariant
        msg = "fixed_step Schedule has neither step_years nor steps_per_year"
        raise RuntimeError(msg)
    step = schedule.step_years
    count = schedule._shared_period_count()  # noqa: SLF001
    return [k * step for k in range(count + 1)]


def fixed_step_year_fraction(schedule: ScheduleData) -> float:
    """Return the width of one step of a fixed-step axis, in years."""
    if schedule.steps_per_year is not None:
        return 1 / schedule.steps_per_year
    if schedule.step_years is None:  # pragma: no cover - constructor invariant
        msg = "fixed_step Schedule has neither step_years nor steps_per_year"
        raise RuntimeError(msg)
    return schedule.step_years


def fixed_step_months_per_step(schedule: ScheduleData) -> int | None:
    """Return the whole calendar months one step is, or None where it is not whole.

    Only a ``steps_per_year`` of 1, 2, 3, 4, 6 or 12 has one. A
    ``step_years`` axis never does, even where the decimal happens to be a
    twelfth's multiple: whether ``0.25`` years is meant as three months is a
    guess, and ``steps_per_year=4`` is how a model says so.
    """
    per_year = schedule.steps_per_year
    if per_year is None or per_year not in _WHOLE_MONTH_STEPS_PER_YEAR:
        return None
    return _MONTHS_IN_A_YEAR // per_year


def fixed_step_anniversary_steps(schedule: ScheduleData) -> int:
    """Return how many steps make one year, refusing where that is a guess.

    Raises:
        ValueError: On a ``step_years`` axis. Whether ten steps of ``0.1``
            make a year is floating-point arithmetic, not something the
            model said; ``steps_per_year=10`` is the form that says it.

    """
    if schedule.steps_per_year is not None:
        return schedule.steps_per_year
    msg = (
        "anniversary_mask() on a fixed-step axis written as "
        f"{_fixed_step_spelling(schedule)}: an anniversary is the step that "
        "closes a whole year, and whether a whole number of these steps makes "
        "a year is a guess the framework will not make. Say how many steps a "
        "year has instead -- af.projection.set(n_periods=..., "
        "steps_per_year=10) -- and anniversaries fall on every tenth step."
    )
    raise ValueError(msg)


def refuse_one_twelfth_off_whole_months(schedule: ScheduleData) -> None:
    """Refuse year fractions ``OneTwelfth`` has no answer for on this cadence.

    ``OneTwelfth`` counts one twelfth of a year for each whole calendar month
    a period spans. A weekly or daily period spans none, so the convention
    has no fraction to give it: counted anyway, the period that crosses a
    month end reads 1/12 and every other 0, and ``t_years`` stands still.
    Only year fractions consult the day count, so this is asked where they
    are taken; the axis's dates and masks are left alone.
    """
    if schedule.frequency is None:
        return
    cadence = _SUB_MONTH_CADENCE.get(schedule.frequency)
    if cadence is None or not isinstance(schedule.day_count, OneTwelfth):
        return
    name, period = cadence
    constructor = _CONSTRUCTOR_OF_KIND[schedule._kind]  # noqa: SLF001
    msg = (
        f"Year fractions on a {name} axis: the schedule's day count is "
        "OneTwelfth, the default day count, which counts one twelfth of a "
        "year for each whole calendar month a period spans, and "
        f"{period} spans no whole month. Counted anyway, the one period that "
        "crosses a month end would read 1/12 and every other 0, and time in "
        "years would stand still. "
        "Give the schedule a day count that counts days -- Actual365Fixed(), "
        "or ActualActualISDA() to count leap years exactly -- and hand it to "
        f"the frame: af.projection.set(schedule=Schedule.{constructor}(..., "
        f'frequency="{schedule.frequency}", day_count=Actual365Fixed())). '
        "OneTwelfth measures the monthly, quarterly, semi-annual and annual "
        "cadences, whose periods are whole months."
    )
    raise ValueError(msg)


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


def _period_offset(frequency: Frequency, periods: int = 1) -> relativedelta:
    """Return the offset that advances a date by ``periods`` whole periods.

    Built by name rather than by unpacking a kwargs dict: ``relativedelta``
    reads its first two positional parameters as dates, so a dict spread
    into it is only as safe as the keys happen to be.

    Raises ``ValueError`` for a frequency outside the supported set -- the
    same refusal ``_normalise_anchor`` gives an unsupported anchor. It cannot
    happen for a valid ``Schedule``, because :meth:`from_calendar_grid` and
    :meth:`from_inception` both validate against ``_SUPPORTED_FREQUENCIES``
    first.
    """
    if frequency == "1M":
        return relativedelta(months=periods)
    if frequency == "3M":
        return relativedelta(months=3 * periods)
    if frequency == "6M":
        return relativedelta(months=6 * periods)
    if frequency == "1Y":
        return relativedelta(years=periods)
    if frequency == "1D":
        return relativedelta(days=periods)
    if frequency == "1W":
        return relativedelta(weeks=periods)
    msg = f"unhandled frequency {frequency!r}"
    raise ValueError(msg)


def _step_date(d: date, frequency: Frequency, anchor: Anchor) -> date:
    """Advance ``d`` by one period under ``frequency``.

    ``relativedelta`` caps a day past the end of the target month (Mar 31 +
    1M = Apr 30) but never lifts one short of it (Feb 28 + 1M = Mar 28, and
    Feb 28 2027 + 1Y = Feb 28 2028, a day before that leap month's end). So a
    month-end anchor re-normalises to month-end after every step at each
    cadence measured in months -- annual included, or an annual grid would
    land on 28 February in a leap year -- and a year-end anchor to the year's
    end. A weekly or daily step is not a month apart, and is left as stepped.
    """
    next_d: date = d + _period_offset(frequency)
    if anchor == "month_end" and frequency in ("1M", "3M", "6M", "1Y"):
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
    return [_period_offset(frequency, t) for t in range(n_periods + 1)]


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
class ScheduleData:
    """Immutable values shared by lowering and audit, independent of authoring."""

    # The axis's one period count, ``T``, on every kind that shares one. None
    # on a ``per_policy_grid``: each policy runs to its own horizon, so the
    # grid has no count of its own, and the longest horizon in a book is a
    # fact of the run (``run_metadata.n_periods``), never of the recipe.
    n_periods: int | None
    # None on a fixed-step schedule, which has no calendar cadence.
    frequency: Frequency | None
    calendar: Calendar
    convention: BusinessDayConvention
    day_count: DayCount
    anchor: Anchor
    # One of the next two is set; the other is None depending on constructor.
    start_date: date | None
    inception_column: str | None
    # Internal flag — distinguishes "from_calendar_grid" vs "from_inception"
    # vs "per_policy_grid" in canonical form without inferring from None-ness.
    _kind: Literal[
        "from_calendar_grid", "from_inception", "per_policy_grid", "fixed_step"
    ] = field(default="from_calendar_grid")
    # ``per_policy_grid`` only: shared ``start_date`` + per-policy horizon read
    # from a column. ``until_kind`` is the ``term_months`` / ``term_years``
    # semantics; ``until_value_column`` names the per-policy magnitude column.
    until_kind: str | None = None
    until_value_column: str | None = None
    # ``per_policy_grid`` to a maximum age only: the column each policy's
    # issue age is read from, and the age as a whole number where the model
    # wrote one. Where it wrote an expression, the expression is held beside
    # the recipe -- its rendering is what the recipe states -- and is left out
    # of equality, since a Polars expression compares by building another.
    issue_age_column: str | None = None
    maximum_age: int | None = None
    until_value_expr: pl.Expr | None = field(default=None, compare=False)
    # ``fixed_step`` only, exactly one of the two: the step in years as the
    # model wrote it, or the whole number of steps a year makes.
    step_years: float | None = None
    steps_per_year: int | None = None

    def _shared_period_count(self) -> int:
        """Return the period count ``T`` every policy on this axis shares.

        A calendar grid, an inception grid and a fixed step each lay one
        count for the whole book. A per-policy grid lays none: each policy's
        count is its own horizon, read from the frame
        (:meth:`per_policy_period_count_expr`).

        Returns:
            The shared period count.

        Raises:
            ValueError: On a ``per_policy_grid``, which has no shared count.

        """
        if self.n_periods is None:
            msg = (
                "A per-policy grid has no shared period count: each policy runs "
                "to its own horizon, which the frame reads from "
                f"{self._horizon_named()}. Read each policy's count with "
                "per_policy_period_count_expr(), or the longest one in a run "
                "from the run's own record (run_metadata.n_periods)."
            )
            raise ValueError(msg)
        return self.n_periods

    def _horizon_named(self) -> str:
        """Name where a per-policy grid reads each policy's horizon, for a message."""
        if self.until_kind == MAXIMUM_AGE:
            return f"its issue-age column {self.issue_age_column!r}"
        return f"its column {self.until_value_column!r}"

    def _cadence(self) -> Frequency:
        """Return the calendar cadence of a schedule that has one.

        Raises:
            ValueError: On a fixed-step schedule, which steps a fixed number
                of years and has no calendar cadence.

        """
        if self.frequency is None:
            refuse_dates_on_a_fixed_step("A calendar cadence")
        return self.frequency

    def period_dates(self) -> list[date]:
        """Return the period boundary dates (length n_periods + 1).

        Only valid for ``from_calendar_grid`` schedules — per-policy grids
        produce a Polars expression, not a Python list (see
        :meth:`period_dates_expr`), and a fixed-step schedule has no dates.
        """
        if self._kind == FIXED_STEP:
            refuse_dates_on_a_fixed_step("period_dates()")
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
        for _ in range(self._shared_period_count()):
            d = _step_date(d, self._cadence(), self.anchor)
            d = self.convention.adjust(d, self.calendar)
            out.append(d)
        return out

    def year_fractions(self) -> list[float]:
        """Return the per-period year-fraction series under this Schedule's day-count.

        Length: ``n_periods``. Valid for ``from_calendar_grid`` schedules, and
        for ``fixed_step``, where every period is one step: ``step_years``, or
        ``1 / steps_per_year``.
        """
        if self._kind == FIXED_STEP:
            return [fixed_step_year_fraction(self)] * self._shared_period_count()
        if self._kind != "from_calendar_grid":
            msg = (
                "year_fractions() is only valid for from_calendar_grid schedules;"
                " use year_fractions_expr() for from_inception"
            )
            raise ValueError(msg)
        refuse_one_twelfth_off_whole_months(self)
        boundaries = self.period_dates()
        return [
            self.day_count.year_fraction(boundaries[t], boundaries[t + 1])
            for t in range(self._shared_period_count())
        ]

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

            >>> from gaspatchio import Schedule
            >>> from datetime import date
            >>> sched = Schedule.from_calendar_grid(
            ...     start_date=date(2025, 1, 31), n_periods=3, frequency="1M"
            ... )
            >>> sched.cumulative_year_fractions()
            [0.0, 0.08333333333333333, 0.16666666666666666, 0.25]

        """
        if self._kind == FIXED_STEP:
            msg = (
                "cumulative_year_fractions() on a fixed-step schedule: time along "
                "a step axis is k steps times the step, one rounding per "
                "boundary, and a running sum of the steps differs from it in the "
                "last bits. Project with the schedule and read "
                "af.projection.t_years(), which is that product."
            )
            raise ValueError(msg)
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
        if self._kind == FIXED_STEP:
            return fixed_step_anniversary_steps(self)
        count = _ANNIVERSARY_PERIODS.get(self._cadence())
        if count is None:
            msg = f"unhandled frequency {self.frequency!r}"
            raise AssertionError(msg)
        return count

    def anniversary_mask(self) -> list[bool]:
        """Return a boolean list marking end-of-period contract anniversaries.

        Index ``t`` is ``True`` when period ``t + 1`` closes a full 12-month
        anniversary from the schedule start date.

        ``from_calendar_grid``, and ``fixed_step`` written as
        ``steps_per_year`` (every that-many-th step), only — for per-policy
        schedules use :meth:`anniversary_mask_expr`. A ``step_years`` schedule
        refuses: whether a whole number of its steps makes a year is a guess.

        Returns:
            A list of length ``n_periods`` where ``True`` marks anniversary
            periods.

        Raises:
            ValueError: If called on a ``from_inception`` schedule.

        Example::

            >>> from gaspatchio import Schedule
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
        if self._kind not in ("from_calendar_grid", FIXED_STEP):
            msg = (
                "anniversary_mask() is only valid for from_calendar_grid schedules;"
                " use anniversary_mask_expr() for from_inception"
            )
            raise ValueError(msg)
        step = self._anniversary_period_count()
        return [(t + 1) % step == 0 for t in range(self._shared_period_count())]

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

            >>> from gaspatchio import Schedule
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

            >>> from gaspatchio import Schedule
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
        if self._kind == FIXED_STEP:
            # No calendar, business-day convention or day count: a step axis
            # has none, and a recipe stating one would be stating a default.
            step: dict[str, Any] = (
                {"steps_per_year": self.steps_per_year}
                if self.steps_per_year is not None
                else {"step_years": self.step_years}
            )
            return {"kind": FIXED_STEP, "n_periods": self.n_periods, **step}
        common: dict[str, Any] = {
            "kind": self._kind,
            "frequency": self.frequency,
            "calendar": self.calendar.name(),
            "convention": self.convention.canonical_name(),
            "day_count": self.day_count.name(),
        }
        if self._kind == "per_policy_grid":
            # No ``n_periods``: the grid's identity is its rule -- the shared
            # start, the cadence, the calendar and the column or age each
            # policy's horizon is read from -- and no other policy's horizon
            # moves it (spec 11.1.37).
            if self.start_date is None:
                msg = "per_policy_grid Schedule missing start_date"
                raise RuntimeError(msg)  # unreachable given _kind invariant
            common["start_date"] = self.start_date.isoformat()
            common["until_kind"] = self.until_kind
            if self.until_kind == MAXIMUM_AGE:
                return {**common, **self._maximum_age_recipe()}
            if self.until_value_column is None:
                msg = "per_policy_grid Schedule missing until_value_column"
                raise RuntimeError(msg)  # unreachable given _kind invariant
            common["until_value_column"] = self.until_value_column
            return common
        common["n_periods"] = self.n_periods
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

    def _maximum_age_recipe(self) -> dict[str, Any]:
        """Return what a per-policy grid to a maximum age states of its horizon.

        The issue-age column, and the age in the one form the model wrote:
        the whole number, the column it is read from, or the expression's
        rendering -- the same rendering ``projection.set`` records for an
        expression ``until_value``.
        """
        recipe: dict[str, Any] = {"issue_age_column": self.issue_age_column}
        if self.maximum_age is not None:
            recipe["maximum_age"] = self.maximum_age
        elif self.until_value_column is not None:
            recipe["until_value_column"] = self.until_value_column
        else:
            recipe["until_value_expr"] = str(self.until_value_expr)
        return recipe

    def source_sha(self) -> str:
        """Return ``sha256:<hex>`` over the canonical form bytes.

        Used by :func:`action_key` (Sub-plan D) to fold typed-input identity
        into the run-identity envelope. Two schedules with the same
        :meth:`canonical_form` always produce the same sha; any parameter
        difference (including constructor kind) produces a different sha.

        Returns:
            A string of the form ``sha256:<64 hex chars>``.

        Example::

            >>> from gaspatchio import Schedule
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
        return f"{SHA256_PREFIX}{digest}"
