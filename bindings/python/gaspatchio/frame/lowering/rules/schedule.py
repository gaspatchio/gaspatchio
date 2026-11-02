# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowerings for the projection timeline a ``Schedule`` describes.

``af.projection.t_years()`` and ``Schedule.period_dates_expr()`` build
``Call`` nodes; the date arithmetic, the day-count year fractions, the
anniversary and in-force masks, and the four quite different shapes a
timeline can take -- a uniform calendar grid, one anchored on each
policy's inception, a jagged per-policy grid, and a fixed-step axis with no
calendar under it -- all live here.

Unlike an accessor method, a schedule expression is a function of a whole
value object rather than of a column plus a couple of settings. The node
therefore carries the schedule's ``source_sha`` and the rule looks the
schedule itself back up (see ``frame/lowering/artefacts.py`` for why a
published content identity is a safe key). The bodies are the schedule's
own, moved: ``self`` became ``schedule``, and nothing else changed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio.frame.lowering.artefacts import schedule_for
from gaspatchio.frame.lowering.polars import register_lowering
from gaspatchio.schedule._data import (
    FIXED_STEP,
    fixed_step_boundary_years,
    fixed_step_year_fraction,
    refuse_dates_on_a_fixed_step,
)

if TYPE_CHECKING:
    from datetime import date

    from gaspatchio._semantic.ir import AttrValue, Call
    from gaspatchio.frame.lowering.context import LoweringContext
    from gaspatchio.schedule._data import ScheduleData


def _attrs(node: Call) -> dict[str, AttrValue]:
    """Read a call's typed configuration back as a dict."""
    return dict(node.attrs)


def _schedule(node: Call) -> ScheduleData:
    """Resolve the schedule this call was emitted against."""
    sha = _attrs(node)["schedule"]
    if not isinstance(sha, str):  # pragma: no cover - emission always sets it
        msg = f"{node.name}: 'schedule' must be a source SHA, got {sha!r}"
        raise TypeError(msg)
    return schedule_for(sha)


def _end_date_column(node: Call) -> str | None:
    """Read the optional per-policy end-date column name off the call."""
    value = _attrs(node).get("end_date_column")
    if value is None:
        return None
    if not isinstance(value, str):  # pragma: no cover - emission validates
        msg = f"{node.name}: 'end_date_column' must be a column name, got {value!r}"
        raise TypeError(msg)
    return value


# --- per-policy (jagged) grid ------------------------------------------------


@register_lowering("schedule.per_policy_period_dates")
def _lower_per_policy_period_dates(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """One list of period boundary dates per policy, each its own length."""
    from gaspatchio.schedule._data import (  # noqa: PLC0415
        _SCHED_FREQ_TO_INTERVAL,
    )

    schedule = _schedule(node)
    if schedule.start_date is None:
        msg = "per_policy_grid Schedule missing start_date"
        raise RuntimeError(msg)  # unreachable given constructor invariant

    start = pl.lit(schedule.start_date)
    magnitude, unit = _per_policy_horizon(schedule)
    end = start.dt.offset_by(pl.concat_str([magnitude.cast(pl.Utf8), pl.lit(unit)]))
    interval = _SCHED_FREQ_TO_INTERVAL[schedule._cadence()]  # noqa: SLF001
    return pl.date_ranges(start=start, end=end, interval=interval, closed="both")


@register_lowering("schedule.per_policy_period_count")
def _lower_per_policy_period_count(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Count how many periods each policy projects for."""
    return _per_policy_period_count(_schedule(node))


def _per_policy_period_count(schedule: ScheduleData) -> pl.Expr:
    """Count each policy's own periods, for rules that build on top of it.

    Arithmetic count -- no ``date_ranges`` materialisation. The horizon is
    in months (``term_months``) or years (``term_years``);
    ``per_policy_grid`` is only built for month-aligned frequencies (1W/1D
    ``term_*`` are rejected at ``set()``). Null or negative terms clamp to
    zero periods.
    """
    from gaspatchio.schedule._data import (  # noqa: PLC0415
        _SCHED_FREQ_MONTHS_PER_PERIOD,
    )

    magnitude, unit = _per_policy_horizon(schedule)
    months = magnitude.fill_null(0)
    if unit == "y":
        months = months * 12
    per_period = _SCHED_FREQ_MONTHS_PER_PERIOD[schedule._cadence()]  # noqa: SLF001
    return (months // per_period).clip(lower_bound=0)


def _per_policy_horizon(schedule: ScheduleData) -> tuple[pl.Expr, str]:
    """Return each policy's own horizon as a whole number, and its unit.

    A term is read from its column in months (``term_months``) or years
    (``term_years``). A maximum age is ``until_value`` less the policy's
    issue age, in whole years toward zero: the age as the model wrote it --
    a whole number, a column or an expression -- less the issue-age column.
    """
    from gaspatchio.schedule._data import (  # noqa: PLC0415
        _UNTIL_KIND_TO_OFFSET_UNIT,
        MAXIMUM_AGE,
    )

    if schedule.until_kind == MAXIMUM_AGE:
        if schedule.issue_age_column is None:
            msg = "maximum-age per_policy_grid Schedule missing issue_age_column"
            raise RuntimeError(msg)  # unreachable given constructor invariant
        if schedule.maximum_age is not None:
            age: pl.Expr = pl.lit(schedule.maximum_age, dtype=pl.Int64)
        elif schedule.until_value_column is not None:
            age = pl.col(schedule.until_value_column)
        elif schedule.until_value_expr is not None:
            age = schedule.until_value_expr
        else:  # pragma: no cover - the constructor takes exactly one form
            msg = "maximum-age per_policy_grid Schedule states no age"
            raise RuntimeError(msg)
        years = (age - pl.col(schedule.issue_age_column)).cast(pl.Int64)
        return years, "y"
    if schedule.until_value_column is None:
        msg = "per_policy_grid Schedule missing until_value_column"
        raise RuntimeError(msg)  # unreachable given constructor invariant
    unit = _UNTIL_KIND_TO_OFFSET_UNIT[schedule.until_kind or "term_months"]
    return pl.col(schedule.until_value_column).cast(pl.Int64), unit


# --- inception-anchored grid -------------------------------------------------


@register_lowering("schedule.period_dates")
def _lower_period_dates(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """One list of period boundary dates per policy, anchored on its inception."""
    from gaspatchio.schedule._data import (  # noqa: PLC0415
        _build_period_offsets,
        _offset_str,
    )

    schedule = _schedule(node)
    if schedule.inception_column is None:
        msg = "from_inception Schedule has no inception_column"
        raise RuntimeError(msg)  # unreachable given _kind invariant

    from gaspatchio.schedule._business_day import (  # noqa: PLC0415
        BusinessDayConvention,
    )
    from gaspatchio.schedule._calendar import NullCalendar  # noqa: PLC0415

    if schedule.convention == BusinessDayConvention.UNADJUSTED and isinstance(
        schedule.calendar, NullCalendar
    ):
        # Fast path: vectorised offset_by + concat_list. Each
        # pl.col().dt.offset_by() is a native Rust pass; concat_list
        # assembles them into a List<Date> column. Zero Python per-row calls.
        return pl.concat_list(
            [
                pl.col(schedule.inception_column).dt.offset_by(
                    _offset_str(schedule._cadence(), i)  # noqa: SLF001
                )
                for i in range(schedule._shared_period_count() + 1)  # noqa: SLF001
            ]
        )

    # Slow path: per-element business-day adjustment. Adjustment is
    # genuinely row- and element-specific -- it cannot be expressed as a
    # broadcast without materialising each adjusted date individually.
    offsets = _build_period_offsets(
        schedule._cadence(),  # noqa: SLF001
        schedule._shared_period_count(),  # noqa: SLF001
    )
    convention = schedule.convention
    calendar = schedule.calendar

    def _expand_row(day: date | None) -> list[date]:
        if day is None:
            return []
        out = [day + off for off in offsets]
        return [convention.adjust(x, calendar) for x in out]

    return pl.col(schedule.inception_column).map_elements(
        _expand_row, return_dtype=pl.List(pl.Date)
    )


def _period_dates_for(schedule: ScheduleData) -> pl.Expr:
    """Period boundary dates for whichever of the two per-row kinds this is."""
    from gaspatchio.frame.lowering.artefacts import register_schedule  # noqa: PLC0415
    from gaspatchio.frame.lowering.polars import lower_polars  # noqa: PLC0415
    from gaspatchio.frame.lowering.rules import _call  # noqa: PLC0415

    sha = register_schedule(schedule)
    name = (
        "schedule.per_policy_period_dates"
        if schedule._kind == "per_policy_grid"  # noqa: SLF001
        else "schedule.period_dates"
    )
    return lower_polars(_call(name, (("schedule", sha),)))


@register_lowering("schedule.year_fractions")
def _lower_year_fractions(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Measure the year fraction each projection period spans, on this day count.

    ``OneTwelfth`` on a month-aligned frequency is per-period constant
    (months in period / 12) and needs no boundary dates at all. On 1W and
    1D it has no fraction to give -- a week or a day spans no whole month --
    and is refused, naming the day counts that count days; every other day
    count depends on the actual boundaries and takes the slow path.
    """
    from gaspatchio.schedule._data import (  # noqa: PLC0415
        _ONETWELFTH_PER_PERIOD,
        refuse_one_twelfth_off_whole_months,
    )
    from gaspatchio.schedule._day_count import OneTwelfth  # noqa: PLC0415

    schedule = _schedule(node)
    if schedule._kind == FIXED_STEP:  # noqa: SLF001
        return _fixed_step_year_fractions(schedule)
    refuse_one_twelfth_off_whole_months(schedule)
    is_per_policy = schedule._kind == "per_policy_grid"  # noqa: SLF001

    if (
        isinstance(schedule.day_count, OneTwelfth)
        and schedule.frequency is not None
        and schedule.frequency in _ONETWELFTH_PER_PERIOD
    ):
        per_period = _ONETWELFTH_PER_PERIOD[schedule.frequency]
        if is_per_policy:
            # Per-policy length -> build the constant list per row.
            return pl.int_ranges(0, _per_policy_period_count(schedule)).list.eval(
                pl.lit(per_period)
            )
        count = schedule._shared_period_count()  # noqa: SLF001
        return pl.lit([per_period] * count, dtype=pl.List(pl.Float64))

    # Slow path: the day count depends on actual boundary dates. The jagged
    # grid yields variable-length boundary lists; the map handles both.
    period_dates_expr = _period_dates_for(schedule)
    day_count = schedule.day_count

    def _list_to_year_fractions(boundaries: list[date]) -> list[float]:
        return [
            day_count.year_fraction(boundaries[t], boundaries[t + 1])
            for t in range(len(boundaries) - 1)
        ]

    return period_dates_expr.map_elements(
        _list_to_year_fractions, return_dtype=pl.List(pl.Float64)
    )


@register_lowering("schedule.anniversary_mask")
def _lower_anniversary_mask(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Mark the periods that close a contract anniversary.

    Purely structural -- it depends only on the period count and the
    frequency, not on each policy's inception date -- so the uniform kinds
    broadcast one literal list to every row with zero Python per-row calls.
    """
    schedule = _schedule(node)
    step = schedule._anniversary_period_count()  # noqa: SLF001

    if schedule._kind == FIXED_STEP:  # noqa: SLF001
        return pl.lit(schedule.anniversary_mask(), dtype=pl.List(pl.Boolean))

    if schedule._kind == "per_policy_grid":  # noqa: SLF001
        # Same structural rule (t+1) % step == 0, over each policy's own
        # variable-length period count.
        return pl.int_ranges(0, _per_policy_period_count(schedule)).list.eval(
            ((pl.element() + 1) % step) == 0
        )

    if schedule.inception_column is None:
        msg = "from_inception Schedule has no inception_column"
        raise RuntimeError(msg)  # unreachable given _kind invariant
    count = schedule._shared_period_count()  # noqa: SLF001
    mask = [(t + 1) % step == 0 for t in range(count)]
    return pl.lit(mask, dtype=pl.List(pl.Boolean))


def _fixed_step_year_fractions(schedule: ScheduleData) -> pl.Expr:
    """One step's width in years for each of a fixed-step axis's periods."""
    return pl.lit(
        [fixed_step_year_fraction(schedule)] * schedule._shared_period_count(),  # noqa: SLF001
        dtype=pl.List(pl.Float64),
    )


def _uniform_mask(n_periods: int, *, value: bool) -> pl.Expr:
    """Build a constant mask of the schedule's own length, for every row."""
    return pl.lit([value] * n_periods, dtype=pl.List(pl.Boolean))


def _per_period_end_dates(schedule: ScheduleData) -> list[pl.Expr]:
    """Each period's end date, as inception plus that period's offset."""
    from gaspatchio.schedule._data import _offset_str  # noqa: PLC0415

    if schedule.inception_column is None:  # pragma: no cover - invariant
        msg = "from_inception Schedule has no inception_column"
        raise RuntimeError(msg)
    inception = pl.col(schedule.inception_column)
    return [
        inception.dt.offset_by(_offset_str(schedule._cadence(), t + 1))  # noqa: SLF001
        for t in range(schedule._shared_period_count())  # noqa: SLF001
    ]


@register_lowering("schedule.is_in_force")
def _lower_is_in_force(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Mark each period the contract is still active in.

    A null end date means no termination is known, so the contract is
    still in force -- coalesced to True rather than left null, which would
    silently corrupt a downstream rollforward boundary mask.
    """
    schedule = _schedule(node)
    end_date_column = _end_date_column(node)

    # The per-policy branch comes first: a per-policy grid states no shared
    # count (spec 11.1.37), and each policy's in-force run is its own horizon.
    if schedule._kind == "per_policy_grid":  # noqa: SLF001
        # Jagged: each policy projects only its own horizon, so every
        # period in its variable-length timeline is in force.
        return pl.int_ranges(0, _per_policy_period_count(schedule)).list.eval(
            pl.lit(value=True)
        )

    # Zero-period shared axis: an empty list whichever branch would apply.
    # Avoids pl.concat_list([]) failing at collect on the inception path.
    n_periods = schedule._shared_period_count()  # noqa: SLF001
    if n_periods == 0:
        return pl.lit([], dtype=pl.List(pl.Boolean))

    if (
        schedule._kind in ("from_calendar_grid", FIXED_STEP)  # noqa: SLF001
        or end_date_column is None
    ):
        return _uniform_mask(n_periods, value=True)

    end_col = pl.col(end_date_column)
    return pl.concat_list(
        [
            (period_end <= end_col).fill_null(value=True)
            for period_end in _per_period_end_dates(schedule)
        ]
    )


@register_lowering("schedule.contract_boundary")
def _lower_contract_boundary(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Mark each period the contract has terminated by.

    The negation of ``is_in_force``: the rollforward kernel uses boundary
    semantics (True = stop), while ``is_in_force`` reads naturally
    everywhere else (True = active).
    """
    schedule = _schedule(node)
    end_date_column = _end_date_column(node)

    # The per-policy branch first, as for is_in_force.
    if schedule._kind == "per_policy_grid":  # noqa: SLF001
        # Jagged: the timeline already stops at each policy's horizon, so
        # no period is a contract boundary.
        return pl.int_ranges(0, _per_policy_period_count(schedule)).list.eval(
            pl.lit(value=False)
        )

    n_periods = schedule._shared_period_count()  # noqa: SLF001
    if n_periods == 0:
        return pl.lit([], dtype=pl.List(pl.Boolean))

    if (
        schedule._kind in ("from_calendar_grid", FIXED_STEP)  # noqa: SLF001
        or end_date_column is None
    ):
        return _uniform_mask(n_periods, value=False)

    end_col = pl.col(end_date_column)
    return pl.concat_list(
        [
            (period_end > end_col).fill_null(value=False)
            for period_end in _per_period_end_dates(schedule)
        ]
    )


# --- the frame accessor's six ------------------------------------------------


@register_lowering("projection_frame.period_dates")
def _lower_frame_period_dates(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Period boundary dates for whichever kind of timeline the frame carries."""
    schedule = _schedule(node)
    if schedule._kind == FIXED_STEP:  # noqa: SLF001
        refuse_dates_on_a_fixed_step("period_dates()")
    if schedule._kind == "from_calendar_grid":  # noqa: SLF001
        return pl.lit(schedule.period_dates(), dtype=pl.List(pl.Date))
    return _period_dates_for(schedule)


@register_lowering("projection_frame.year_fractions")
def _lower_frame_year_fractions(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Per-period year fractions for whichever kind of timeline the frame carries."""
    schedule = _schedule(node)
    if schedule._kind == FIXED_STEP:  # noqa: SLF001
        return _fixed_step_year_fractions(schedule)
    if schedule._kind == "from_calendar_grid":  # noqa: SLF001
        return pl.lit(schedule.year_fractions(), dtype=pl.List(pl.Float64))
    return _year_fractions_for(schedule)


def _year_fractions_for(schedule: ScheduleData) -> pl.Expr:
    """Year fractions for a per-row schedule kind, via the registered rule."""
    from gaspatchio.frame.lowering.artefacts import register_schedule  # noqa: PLC0415
    from gaspatchio.frame.lowering.polars import lower_polars  # noqa: PLC0415
    from gaspatchio.frame.lowering.rules import _call  # noqa: PLC0415

    sha = register_schedule(schedule)
    return lower_polars(_call("schedule.year_fractions", (("schedule", sha),)))


@register_lowering("projection_frame.t_years")
def _lower_frame_t_years(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Elapsed time in years at each period boundary, counting from zero.

    Length is one more than the period count, which is what
    ``Curve.discount_factor(t)`` expects. On a fixed-step axis it is one
    product (or quotient) per boundary, ``k * step_years`` or
    ``k / steps_per_year``, and never the running sum a calendar grid takes.
    """
    schedule = _schedule(node)
    if schedule._kind == FIXED_STEP:  # noqa: SLF001
        return pl.lit(fixed_step_boundary_years(schedule), dtype=pl.List(pl.Float64))
    if schedule._kind == "from_calendar_grid":  # noqa: SLF001
        return pl.lit(schedule.cumulative_year_fractions(), dtype=pl.List(pl.Float64))
    # from_inception / per_policy_grid: cumulate the per-period year
    # fractions with a leading zero. (There is no list.cum_sum(); eval
    # cum_sum per sublist.)
    zeros = pl.lit([0.0], dtype=pl.List(pl.Float64))
    return pl.concat_list(
        [zeros, _year_fractions_for(schedule).list.eval(pl.element().cum_sum())]
    )


@register_lowering("projection_frame.anniversary_mask")
def _lower_frame_anniversary_mask(node: Call, ctx: LoweringContext | None) -> pl.Expr:  # noqa: ARG001
    """Anniversary mask for whichever kind of timeline the frame carries."""
    schedule = _schedule(node)
    if schedule._kind in ("from_calendar_grid", FIXED_STEP):  # noqa: SLF001
        return pl.lit(schedule.anniversary_mask(), dtype=pl.List(pl.Boolean))
    return _lower_anniversary_mask(node, None)
