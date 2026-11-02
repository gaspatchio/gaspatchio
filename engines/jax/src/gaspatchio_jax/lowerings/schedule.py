# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The projection axis itself, and the columns a schedule mints along it.

``projection_set`` is the declaration of a model's time axis, and everything
else here reads a schedule recipe out of the document's own directory and
answers one of its columns. Between them they are the **generator** class: the
answer's length is not an operand's, it is the axis's, and what they emit is
emitted to the bucket and cut back to each policy's own count on the way out.

**A boundary count and a period count are one apart, and the difference is
where models go wrong.** An axis of ``n`` periods has ``n + 1`` boundaries.
``period_dates`` and ``t_years`` answer boundaries; ``year_fractions``, the
masks and ``is_in_force`` answer periods. 11.1.37 says so per row of its own
table and this module keeps the two apart per operation rather than once.

**A shared grid and a per-policy one anchor differently, and both are here.**
A shared calendar grid steps from the previous boundary and re-clamps at each
step, so a quarterly grid from 31 January runs 30 April then 30 July; a
per-policy or inception grid offsets every boundary from the **original**
start, so the same dates run 30 April then 31 July. Neither silently
re-anchors to month end, and an engine that used one rule for both would be
wrong on exactly the policies whose issue day is the 29th, 30th or 31st.

**A fixed-step axis has no calendar, and is the simplest axis here.** 11.1.1's
fourth form steps ``T`` times a fixed number of years: the time at boundary
``k`` is ``k * step_years`` or ``k / steps_per_year``, one IEEE operation per
boundary, so ``iota(T + 1)`` times or over the step is the reference
producer's own number to the bit. It has no dates at all, so the readings that
answer dates refuse it by name rather than inventing a calendar under it.

**What the record does not determine, this engine does not lay.** 11.1.1 is
explicit that a horizon the attributes do not fix -- a ``maximum_age`` or a
column-named horizon collapsed onto one shared grid -- is sized from the model
points and that the sizing is nowhere on the record. Two runs of one
configuration over two books carry the same attributes, the same empty
``reads`` and the same node identity, and lay axes of different lengths. So
this engine refuses those by name rather than laying an axis from the
attributes as though they fixed it.

**A maximum age measured per policy is on the record, and is laid.** Where
the axis runs each policy to ``until_value`` less its own issue age, the node
names the issue-age column and reads it -- and reads the age's own column
where the age is one -- so every policy's count follows from the record:
``T_i = max(0, (age - issue_age) * p)``. An age the model computed with an
expression is on the record only as its rendering, and is refused by name.
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Final

import jax
import jax.numpy as jnp
from jax import lax

from gaspatchio_jax.capability import DATE, NUMERIC, PER_POLICY, Capability
from gaspatchio_jax.horizon import Horizon
from gaspatchio_jax.ieee import divided
from gaspatchio_jax.lowerings import register, register_sizing
from gaspatchio_jax.lowerings.dates import civil_from_days, moved_by_months
from gaspatchio_jax.lowerings.reduction import running
from gaspatchio_jax.typed import JNP_OF, DomainRefused, Value, require_carrier

if TYPE_CHECKING:
    import datetime

    from gaspatchio.engines.format import Call
    from gaspatchio_jax.lowerings import Lowering
    from gaspatchio_jax.plan import LoweringContext

_AXIS: Final = "11.1.1"
_SCHEDULES: Final = "11.1.37"

# Read off the producer, and stated in the specification beside it.
# The six cadences 11.1.1 names, each in the producer's English spelling and
# in the shorthand a schedule recipe carries, and the months a period of each
# is -- which only the four month-aligned ones have.
FREQUENCY_TOKENS: Final[dict[str, str]] = {
    "monthly": "1M",
    "quarterly": "3M",
    "semi-annual": "6M",
    "annual": "1Y",
    "weekly": "1W",
    "daily": "1D",
}
MONTHS_PER_PERIOD: Final[dict[str, int]] = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}

# The cadences this engine lays boundaries at, in both spellings: the four
# month-aligned ones. Stated on the registration so the published claim is
# the claim, rather than *lowered* with a refusal waiting at run time.
_ANSWERED_CADENCES: Final[tuple[str, ...]] = (
    "monthly",
    "quarterly",
    "semi-annual",
    "annual",
    "1M",
    "3M",
    "6M",
    "1Y",
)
PERIODS_PER_YEAR: Final[dict[str, int]] = {"1M": 12, "3M": 4, "6M": 2, "1Y": 1}

# The four schedule kinds, and 11.1.1's four declaration forms.
_CALENDAR_GRID: Final = "from_calendar_grid"
_INCEPTION: Final = "from_inception"
_PER_POLICY: Final = "per_policy_grid"
_FIXED_STEP: Final = "fixed_step"

# A fixed step, written either way: the step in years, or the steps a year.
_STEP_YEARS: Final = "step_years"
_STEPS_PER_YEAR: Final = "steps_per_year"

# The steps a year that make a step a whole number of calendar months, where
# 11.1.1 stamps ``month`` on a fixed-step axis; at any other the index is absent.
_WHOLE_MONTH_STEPS: Final[frozenset[int]] = frozenset({1, 2, 3, 4, 6, 12})

# The horizon kinds whose period count the attributes fix on their own.
_TERM_MONTHS: Final = "term_months"
_TERM_YEARS: Final = "term_years"
_FIXED_DATE: Final = "fixed_date"
_MAXIMUM_AGE: Final = "maximum_age"

# The four columns ``projection_set`` mints, and what each one is.
_START_DATE: Final = "projection_start_date"
_END_DATE: Final = "projection_end_date"
_BOUNDARY_COUNT: Final = "num_proj_months"
_MONTH_INDEX: Final = "month"
# The step index a fixed-step axis mints, ``0..T``, in place of the dates.
_STEP_INDEX: Final = "step"

# The one anchor 11.1.37 states boundary dates for, and the three recipe
# values it admits beside it. These are recipe values, not defaults a consumer
# is free to fill in: a business-day adjustment or a holiday calendar moves
# boundaries, and this family must not approximate one it cannot apply.
_EXACT_DATE: Final = "exact_date"
_ADMITTED_RECIPE: Final[dict[str, str]] = {
    "calendar": "NullCalendar",
    "convention": "Unadjusted",
    "day_count": "OneTwelfth",
}

# A year, in months, for the anniversary rule.
_MONTHS_IN_A_YEAR: Final = 12


def months_of(frequency: str, clause: str = _AXIS) -> int:
    """Return how many calendar months one period of a cadence is.

    Raises:
        DomainRefused: If the cadence is not one of the four month-aligned
            ones. A weekly or daily cadence has no whole number of months in
            a period, and the boundary-date rules in both clauses are stated
            in months.

    """
    token = FREQUENCY_TOKENS.get(str(frequency).lower(), str(frequency).upper())
    months = MONTHS_PER_PERIOD.get(token)
    if months is None:
        raise DomainRefused(
            what=(
                f"this axis runs at a cadence of {frequency!r}, and this "
                "engine lays boundaries at the four month-aligned cadences"
            ),
            move=(
                "run this model on Polars: a weekly or daily period has no "
                "whole number of months, and this clause states its "
                "boundaries in months"
            ),
            clause=clause,
        )
    return months


def _epoch_days(written: str) -> int:
    """Return one ISO calendar day from a recipe as a count of days."""
    import datetime  # noqa: PLC0415 -- one parse, on the host

    day: datetime.date = datetime.date.fromisoformat(str(written))
    return (day - datetime.date(1970, 1, 1)).days


# Compiled, with the cadence and the width fixed per compilation. A batch
# settles its axis on the host before its program runs, and there the calendar
# arithmetic below -- some forty integer operations over a batch-by-bucket
# rectangle -- ran one dispatch at a time, each a pass over the whole
# rectangle: at a million policies that was twice the projection's own time.
# Compiled, it is one call per batch shape; inside a program's trace it
# inlines exactly as the plain function did. Integer arithmetic, so the days
# are the same days.
@partial(jax.jit, static_argnums=(1, 2))
def boundaries_from_original(start: jax.Array, months: int, bucket: int) -> jax.Array:
    """Return boundary ``k`` as the original start plus ``k`` periods of months.

    The inception and per-policy rule: every boundary is offset from the day
    the policy actually started, so a clamped February boundary does not drag
    the boundary after it back to the 29th.
    """
    steps = jnp.arange(bucket, dtype=JNP_OF["i64"])[None, :] * months
    return moved_by_months(
        jnp.broadcast_to(start[:, None], (start.shape[0], bucket)), steps
    )


def boundaries_stepwise(start: jax.Array, months: int, bucket: int) -> jax.Array:
    """Return each boundary as the previous one advanced and re-clamped.

    The shared calendar grid's rule, and the one that makes a quarterly grid
    from 31 January run 30 April and then 30 July rather than 31 July.
    """

    def step(carry: jax.Array, _position: jax.Array) -> tuple[jax.Array, jax.Array]:
        return moved_by_months(carry, jnp.asarray(months)), carry

    _last, kept = lax.scan(step, start, jnp.arange(bucket))
    return kept.T


def _payload(call: Call, ctx: LoweringContext) -> dict[str, Any]:
    """Return the schedule recipe one call names, by its whole digest."""
    return ctx.assumption("schedule", None, str(dict(call.attrs)["schedule"]))


def _period_counts(
    payload: dict[str, Any], call: Call, ctx: LoweringContext, rows: int
) -> tuple[jax.Array, int]:
    """Return each policy's own period count and the months one period is.

    Raises:
        DomainRefused: If the recipe is outside the bounded domain -- an
            anchor other than an exact date, or a per-policy grid whose term
            operand the call does not carry.

    """
    if str(payload["kind"]) == _FIXED_STEP:
        # Every policy steps the recipe's own count; no month stands behind a
        # step, so the second answer is nought and nothing here reads it.
        return jnp.full((rows,), _fixed_count(payload), dtype=JNP_OF["i64"]), 0
    _outside_the_recipe(payload)
    months = months_of(str(payload["frequency"]), _SCHEDULES)
    kind = str(payload["kind"])
    stated = int(payload.get("n_periods") or 0)
    if kind == _CALENDAR_GRID:
        anchor = str(payload.get("anchor") or _EXACT_DATE)
        if anchor != _EXACT_DATE:
            raise DomainRefused(
                what=(
                    f"this schedule is anchored on {anchor!r}, and this "
                    "entry states boundary dates for an exact date"
                ),
                move="run this model on Polars until the anchor lands here",
                clause=_SCHEDULES,
            )
        return jnp.full((rows,), stated, dtype=JNP_OF["i64"]), months
    if kind == _INCEPTION:
        return jnp.full((rows,), stated, dtype=JNP_OF["i64"]), months
    per_year = PERIODS_PER_YEAR[
        FREQUENCY_TOKENS.get(
            str(payload["frequency"]).lower(), str(payload["frequency"]).upper()
        )
    ]
    if str(payload.get("until_kind")) == _MAXIMUM_AGE:
        years = _years_to_the_age(
            call,
            ctx,
            issue_age_column=payload.get("issue_age_column"),
            age=payload.get("maximum_age"),
            age_column=payload.get("until_value_column")
            or payload.get("until_value_expr"),
            clause=_SCHEDULES,
        )
        if years is None:
            raise DomainRefused(
                what=(
                    "this per-policy schedule runs each policy to a maximum age "
                    "measured from its issue age, and the call reads no operand "
                    f"carrying {payload.get('issue_age_column')!r}"
                ),
                move=(
                    "export the artifact again from the run that laid the axis, "
                    "so each policy's own horizon travels with the record"
                ),
                clause=_SCHEDULES,
            )
        return jnp.maximum(years * per_year, 0), months
    term = _term_operand(call, ctx, payload)
    whole = (
        term * per_year
        if str(payload.get("until_kind")) == _TERM_YEARS
        else jnp.floor_divide(term, months)
    )
    return jnp.maximum(whole, 0), months


def _operand_named(
    call: Call, ctx: LoweringContext, named: object, clause: str
) -> jax.Array | None:
    """Return the whole-number operand a call reads under ``named``, or None."""
    if not isinstance(named, str):
        return None
    for argument in call.args:
        if getattr(argument, "name", None) == named:
            return require_carrier(
                ctx.lower(argument), frozenset({"i64"}), call.name, clause
            ).array
    return None


def _years_to_the_age(  # noqa: PLR0913 -- the call, the run, and the three parts of the age
    call: Call,
    ctx: LoweringContext,
    *,
    issue_age_column: object,
    age: object,
    age_column: object,
    clause: str,
) -> jax.Array | None:
    """Return each policy's whole years from its issue age to the age, or None.

    The age is the whole number the record states, or the column it names
    and the call reads. None where the call reads no issue-age operand: the
    count is then nowhere on the record, and the caller refuses it.

    Raises:
        DomainRefused: If the call reads the issue age but the age is neither
            a whole number nor a column the call reads -- an age the model
            computed with an expression, which the record states only as its
            rendering.

    """
    issue = _operand_named(call, ctx, issue_age_column, clause)
    if issue is None:
        return None
    if isinstance(age, int) and not isinstance(age, bool):
        return age - issue
    target = _operand_named(call, ctx, age_column, clause)
    if target is None:
        raise DomainRefused(
            what=(
                "this axis runs each policy to a maximum age the record states "
                f"as {age_column!r}, and the call reads no column of that name: "
                "an age the model computed with an expression is on the record "
                "only as its rendering, which this engine does not evaluate"
            ),
            move=(
                "run this model on Polars, or put the age in a column of the "
                "model points and pass the column's name as until_value"
            ),
            clause=clause,
        )
    return target - issue


def _outside_the_recipe(payload: dict[str, Any]) -> None:
    """Refuse a calendar, a convention or a day count this family does not state.

    Raises:
        DomainRefused: If any of the three is outside 11.1.37's bounded
            domain. Approximating a business-day adjustment with none of one
            would answer boundaries the model never had, under the recipe's
            own digest.

    """
    for name, admitted in _ADMITTED_RECIPE.items():
        written = payload.get(name)
        if written is not None and str(written) != admitted:
            raise DomainRefused(
                what=(
                    f"this schedule states {name}={written!r}, and this "
                    f"bounded family admits {admitted}"
                ),
                move=(
                    "run this model on Polars: a reader must report this "
                    "capability limit rather than approximate the calendar "
                    "it cannot apply"
                ),
                clause=_SCHEDULES,
            )


def _term_operand(
    call: Call, ctx: LoweringContext, payload: dict[str, Any]
) -> jax.Array:
    """Return the per-policy term a per-policy grid is sized from.

    Raises:
        DomainRefused: If the call names no operand for it. 11.1.37 sizes a
            per-policy grid from a column, and a call that does not read one
            leaves the count nowhere on the record.

    """
    if not call.args:
        raise DomainRefused(
            what=(
                "this per-policy schedule is sized from the column "
                f"{payload.get('until_value_column')!r} and the call reads no "
                "operand carrying it"
            ),
            move=(
                "export the artifact again from the run that laid the axis, "
                "so each policy's own horizon travels with the record"
            ),
            clause=_SCHEDULES,
        )
    return require_carrier(
        ctx.lower(call.args[0]), frozenset({"i64"}), "schedule", _SCHEDULES
    ).array


def _start_of(
    payload: dict[str, Any], call: Call, ctx: LoweringContext, rows: int
) -> tuple[jax.Array, bool]:
    """Return each policy's boundary zero, and whether the grid steps or offsets."""
    kind = str(payload["kind"])
    if kind == _INCEPTION:
        named = str(payload["inception_column"])
        arrived = next(
            (
                ctx.lower(argument)
                for argument in call.args
                if getattr(argument, "name", None) == named
            ),
            None,
        )
        if arrived is None:
            arrived = ctx.key_column(named, role="its inception date")
        return require_carrier(arrived, DATE, "schedule", _SCHEDULES).array, False
    opened = _epoch_days(str(payload["start_date"]))
    return jnp.full((rows,), opened, dtype=JNP_OF["i64"]), kind == _CALENDAR_GRID


def _axis_of(
    call: Call, ctx: LoweringContext
) -> tuple[jax.Array, jax.Array, int, Horizon]:
    """Return the boundary days, each policy's period count, the months, and the axis.

    The axis is the boundary sequence's -- ``n + 1`` cells for ``n`` periods
    -- laid from the count the host already holds for this call where it
    holds one (:meth:`~gaspatchio_jax.plan.LoweringContext.cells_of`). A batch
    is settled while the card may still be computing the one before it, and
    a count read back off the device would wait for that computation to end.
    """
    payload = _payload(call, ctx)
    counts, months = _period_counts(payload, call, ctx, ctx.rows)
    start, stepwise = _start_of(payload, call, ctx, ctx.rows)
    boundary = Horizon.over(counts + 1, host=ctx.cells_of(call))
    boundaries = (
        boundaries_stepwise(start, months, boundary.bucket)
        if stepwise
        else boundaries_from_original(start, months, boundary.bucket)
    )
    return boundaries, counts, months, boundary


def _period_value(
    counts: jax.Array, boundary: Horizon, cells: jax.Array, carrier: str, dtype: str
) -> Value:
    """Return one per-period answer over each policy's own count of periods.

    One cell fewer than the boundaries, policy by policy, and counted on the
    host from the boundaries' own counts rather than read back.
    """
    periods = Horizon.over(counts, bucket=boundary.bucket, host=boundary.lengths - 1)
    return Value(cells, carrier, "list", dtype, periods)  # type: ignore[arg-type]


def _fixed_count(payload: dict[str, Any]) -> int:
    """Return a fixed-step recipe's step count ``T``.

    Raises:
        DomainRefused: If the count is not a whole number of nought or more.

    """
    count = payload.get("n_periods")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise DomainRefused(
            what=(
                f"this fixed-step axis states n_periods={count!r}, and a step "
                "count is a whole number of nought or more"
            ),
            move="export the artifact again from the run that laid the axis",
            clause=_AXIS,
        )
    return count


def _fixed_step(stated: dict[str, Any]) -> tuple[str, float | int]:
    """Return which spelling a fixed step is written in, and its value.

    Raises:
        DomainRefused: If both spellings, or neither, are stated, or the value
            is not a positive number of its kind.

    """
    years = stated.get(_STEP_YEARS)
    per_year = stated.get(_STEPS_PER_YEAR)
    if (years is None) == (per_year is None):
        raise DomainRefused(
            what=(
                "this fixed-step axis states "
                f"{'both' if years is not None else 'neither'} of step_years and "
                "steps_per_year, and 11.1.1 states exactly one"
            ),
            move="export the artifact again from the run that laid the axis",
            clause=_AXIS,
        )
    if per_year is not None:
        if not isinstance(per_year, int) or isinstance(per_year, bool) or per_year < 1:
            raise DomainRefused(
                what=(
                    f"this fixed-step axis states steps_per_year={per_year!r}, "
                    "and that is a whole number of one or more"
                ),
                move="export the artifact again from the run that laid the axis",
                clause=_AXIS,
            )
        return _STEPS_PER_YEAR, per_year
    if not isinstance(years, (int, float)) or isinstance(years, bool) or years <= 0:
        raise DomainRefused(
            what=(
                f"this fixed-step axis states step_years={years!r}, and a step "
                "is a positive number of years"
            ),
            move="export the artifact again from the run that laid the axis",
            clause=_AXIS,
        )
    return _STEP_YEARS, float(years)


def _boundary_years(stated: dict[str, Any], bucket: int) -> jax.Array:
    """Return the time in years at each boundary of a fixed-step axis.

    ``k * step_years`` or ``k / steps_per_year``: one IEEE operation per
    boundary, and never a running sum, so the cells are the reference
    producer's own doubles -- the division taken as written, never as a
    product by a rounded reciprocal (:func:`~gaspatchio_jax.ieee.divided`).
    """
    spelling, step = _fixed_step(stated)
    steps = jnp.arange(bucket, dtype=JNP_OF["f64"])[None, :]
    if spelling == _STEPS_PER_YEAR:
        return divided(steps, float(step))
    return steps * step


def _step_width(stated: dict[str, Any]) -> float:
    """Return one fixed step's width in years, as the producer computes it."""
    spelling, step = _fixed_step(stated)
    return 1 / step if spelling == _STEPS_PER_YEAR else float(step)


def _no_calendar(name: str) -> DomainRefused:
    """Return the refusal for a dated reading of an axis with no calendar."""
    return DomainRefused(
        what=(
            f"{name} reads dates, and this fixed-step axis has no calendar: its "
            "boundaries are steps of a fixed number of years"
        ),
        move=(
            "read time along this axis with projection_frame.t_years, or lay a "
            "calendar axis where dated periods are meant"
        ),
        clause=_SCHEDULES,
    )


def _fixed_step_reading(
    name: str, payload: dict[str, Any], call: Call, ctx: LoweringContext
) -> Value:
    """Return one schedule-family reading of a fixed-step axis.

    11.1.37 for the fourth kind: ``T + 1`` boundary times, ``T`` step widths,
    an anniversary at every ``n``-th step where the recipe states
    ``steps_per_year=n``, every period in force, and no dates.

    Raises:
        DomainRefused: For a reading that answers dates, an anniversary on an
            axis written as ``step_years``, an end-date boundary, or a
            per-policy count this kind does not have.

    """
    counts = jnp.full((ctx.rows,), _fixed_count(payload), dtype=JNP_OF["i64"])
    boundary = Horizon.over(counts + 1, host=ctx.cells_of(call))
    shape = (ctx.rows, boundary.bucket)
    if name == "projection_frame.t_years":
        cells = jnp.broadcast_to(_boundary_years(payload, boundary.bucket), shape)
        return Value(cells, "f64", "list", "list[f64]", boundary)
    if name in ("projection_frame.year_fractions", "schedule.year_fractions"):
        cells = jnp.full(shape, _step_width(payload), dtype=JNP_OF["f64"])
        return _period_value(counts, boundary, cells, "f64", "list[f64]")
    if name in ("projection_frame.anniversary_mask", "schedule.anniversary_mask"):
        spelling, step = _fixed_step(payload)
        if spelling != _STEPS_PER_YEAR:
            raise DomainRefused(
                what=(
                    "this fixed-step axis is written as step_years, and whether "
                    "a whole number of its steps makes a year is not stated"
                ),
                move="lay the axis as steps_per_year, which states it",
                clause=_SCHEDULES,
            )
        steps = jnp.arange(boundary.bucket, dtype=JNP_OF["i64"])[None, :] + 1
        cells = jnp.broadcast_to(steps % int(step) == 0, shape)
        return _period_value(counts, boundary, cells, "bool", "list[bool]")
    if name in ("schedule.is_in_force", "schedule.contract_boundary"):
        if isinstance(dict(call.attrs).get("end_date_column"), str):
            reading = f"{name} with an end date"
            raise _no_calendar(reading)
        in_force = name == "schedule.is_in_force"
        cells = jnp.full(shape, in_force, dtype=bool)
        return _period_value(counts, boundary, cells, "bool", "list[bool]")
    if name == "schedule.per_policy_period_count":
        raise DomainRefused(
            what="this fixed-step axis has one shared count and no per-policy grid",
            move="read the boundary count from num_proj_months",
            clause=_SCHEDULES,
        )
    raise _no_calendar(name)


def _schedule_reading(name: str) -> Lowering:
    """Return the lowering for one of the schedule family's readings."""

    def lowering(call: Call, ctx: LoweringContext) -> Value:
        payload = _payload(call, ctx)
        if str(payload["kind"]) == _FIXED_STEP:
            return _fixed_step_reading(name, payload, call, ctx)
        return calendar_reading(call, ctx)

    def calendar_reading(call: Call, ctx: LoweringContext) -> Value:
        boundaries, counts, months, boundary = _axis_of(call, ctx)
        bucket = boundary.bucket
        fraction = months / _MONTHS_IN_A_YEAR
        if name in (
            "projection_frame.period_dates",
            "schedule.period_dates",
            "schedule.per_policy_period_dates",
        ):
            return Value(
                boundaries.astype(JNP_OF["date"]),
                "date",
                "list",
                "list[date]",
                boundary,
            )
        if name in ("projection_frame.year_fractions", "schedule.year_fractions"):
            cells = jnp.full(boundaries.shape, fraction, dtype=JNP_OF["f64"])
            return _period_value(counts, boundary, cells, "f64", "list[f64]")
        if name == "projection_frame.t_years":
            # The reference producer's own sum: nought, then each period's
            # year fraction added to the one before, one addition at a time.
            # ``k * fraction`` is one rounding where the running sum is k of
            # them, and the two part company in the last place: monthly, six
            # times 1/12 is not 1/12 added six times, nor are ten or eleven.
            steps = jnp.full((1, bucket), fraction, dtype=JNP_OF["f64"])
            steps = steps.at[:, 0].set(0.0)
            _last, elapsed = running(
                steps, jnp.zeros((1,), dtype=JNP_OF["f64"]), jnp.add
            )
            cells = jnp.broadcast_to(elapsed, boundaries.shape)
            return Value(cells, "f64", "list", "list[f64]", boundary)
        if name in (
            "projection_frame.anniversary_mask",
            "schedule.anniversary_mask",
        ):
            steps = jnp.arange(bucket, dtype=JNP_OF["i64"])[None, :] + 1
            cells = jnp.broadcast_to(
                (steps * months) % _MONTHS_IN_A_YEAR == 0, boundaries.shape
            )
            return _period_value(counts, boundary, cells, "bool", "list[bool]")
        if name == "schedule.per_policy_period_count":
            return Value(counts.astype(JNP_OF["i64"]), "i64", "scalar", "i64")
        in_force = _in_force(call, ctx, boundaries)
        cells = in_force if name == "schedule.is_in_force" else ~in_force
        return _period_value(counts, boundary, cells, "bool", "list[bool]")

    lowering.__name__ = name.replace(".", "_")
    return lowering


def _in_force(call: Call, ctx: LoweringContext, boundaries: jax.Array) -> jax.Array:
    """Return which periods close at or before the end date, where there is one.

    11.1.37: the test is on the period's **end** boundary, which is boundary
    ``t + 1``. Without an end-date column every period is in force, and a null
    end date means no known termination, which is also in force -- but a null
    is a value this engine states no answer over, so a column carrying one
    refuses at the door rather than reaching here.
    """
    named = dict(call.attrs).get("end_date_column")
    if not isinstance(named, str):
        return jnp.ones(boundaries.shape, dtype=bool)
    ends = require_carrier(
        ctx.key_column(named, role="its end date"),
        DATE,
        "schedule.is_in_force",
        _SCHEDULES,
    ).array
    closing = jnp.concatenate([boundaries[:, 1:], boundaries[:, -1:]], axis=1)
    return closing <= ends[:, None]


_ANSWERS: Final[dict[str, str]] = {
    "projection_frame.period_dates": "list",
    "projection_frame.year_fractions": "list",
    "projection_frame.t_years": "list",
    "projection_frame.anniversary_mask": "list",
    "schedule.period_dates": "list",
    "schedule.per_policy_period_dates": "list",
    "schedule.per_policy_period_count": "scalar",
    "schedule.year_fractions": "list",
    "schedule.anniversary_mask": "list",
    "schedule.is_in_force": "list",
    "schedule.contract_boundary": "list",
}

for _name, _answer in _ANSWERS.items():
    register(
        Capability(
            identifier=_name,
            # The operand a schedule reading takes is the column its own kind
            # is sized or anchored from, and a kind that needs none takes no
            # operand at all -- so the count is the recipe's rather than this
            # registration's.
            carriers=(NUMERIC | DATE,),
            shapes=(PER_POLICY,),
            answers=_answer,
            attrs_required=("schedule",),
            horizon="generator",
            sizes_its_own_axis=True,
            clause=_SCHEDULES,
            note=(
                "boundary sequences carry T+1 cells and period values T; the "
                "recipe is resolved by its whole digest"
            ),
        )
    )(_schedule_reading(_name))


def _schedule_cells(call: Call, ctx: LoweringContext) -> jax.Array:
    """Return the boundary count one schedule reading lays down per policy."""
    payload = _payload(call, ctx)
    counts, _months = _period_counts(payload, call, ctx, ctx.rows)
    return counts + 1


for _sized in _ANSWERS:
    register_sizing(_sized)(_schedule_cells)


@register_sizing("projection_set")
def _projection_cells(call: Call, ctx: LoweringContext) -> jax.Array:
    """Return the boundary count one projection declaration lays down per policy."""
    attrs = dict(call.attrs)
    if _declares_a_fixed_step(attrs):
        return jnp.full((ctx.rows,), _fixed_count(attrs) + 1, dtype=JNP_OF["i64"])
    return _declared_periods(call, ctx, attrs, _cadence_months(attrs)) + 1


def _declares_a_fixed_step(attrs: dict[str, Any]) -> bool:
    """Return whether a ``projection_set`` declaration is 11.1.1's fixed-step form."""
    return attrs.get(_STEP_YEARS) is not None or attrs.get(_STEPS_PER_YEAR) is not None


def _cadence_months(attrs: dict[str, Any]) -> int:
    """Return the months a calendar declaration's period is, or refuse its absence.

    Raises:
        DomainRefused: If the declaration states no cadence and no fixed step,
            which leaves the axis it lays nowhere on the record.

    """
    frequency = attrs.get("frequency")
    if frequency is None:
        raise DomainRefused(
            what=(
                "this projection axis states neither a frequency nor a fixed "
                "step, so the record does not say what one period is"
            ),
            move="export the artifact again from the run that laid the axis",
            clause=_AXIS,
        )
    return months_of(str(frequency))


@register(
    Capability(
        identifier="projection_set",
        carriers=(NUMERIC,),
        shapes=(PER_POLICY,),
        # The four month-aligned cadences, in both the spellings 11.1.1 and
        # 11.1.37 use. A weekly or daily axis has no whole number of months in
        # a period and both clauses state their boundaries in months, so this
        # engine answers neither -- and the published claim says so rather
        # than reading *lowered* and refusing at run time.
        # The fixed-step form states no frequency and one of these two in its
        # place; a declaration that states neither is refused by name.
        attrs={"frequency": _ANSWERED_CADENCES},
        attrs_folded=("frequency",),
        attr_bounds={_STEPS_PER_YEAR: (1, None)},
        attrs_numeric=(_STEP_YEARS,),
        horizon="generator",
        sizes_its_own_axis=True,
        clause=_AXIS,
        note=(
            "the boundary count follows from the attributes where the horizon "
            "is a whole term, a fixed date or a number of years, or the axis is "
            "a fixed step of step_years or steps_per_year, which mints step, "
            "num_proj_months and, where a step is whole months, month; a "
            "horizon the attributes do not fix, and a declaration stating "
            "neither a frequency nor a step, are refused by name"
        ),
    )
)
def _projection_set(call: Call, ctx: LoweringContext) -> Value:
    """Return one of the four columns this declaration mints.

    Which one is the node's own column: 11.1.1 makes this node the account of
    each of the four, so the same call stands behind ``month`` and behind
    ``num_proj_months`` and the record says which account is being asked for.
    """
    attrs = dict(call.attrs)
    if _declares_a_fixed_step(attrs):
        return _fixed_step_axis(call, ctx, attrs)
    months = _cadence_months(attrs)
    counts = _declared_periods(call, ctx, attrs, months)
    opened = _valuation_day(attrs)
    start = jnp.full((ctx.rows,), opened, dtype=JNP_OF["i64"])
    column = ctx.node.column or ""
    if column == _START_DATE:
        return Value(start.astype(JNP_OF["date"]), "date", "scalar", "date")
    if column == _BOUNDARY_COUNT:
        return Value((counts + 1).astype(JNP_OF["i64"]), "i64", "scalar", "i64")
    # The two columns that read the boundaries are the only ones that lay
    # them, over the count the host already holds for this call: a settlement
    # that read it back would wait for whatever the card is still computing.
    boundary = Horizon.over(counts + 1, host=ctx.cells_of(call))
    boundaries = boundaries_from_original(start, months, boundary.bucket)
    if column == _END_DATE:
        last = jnp.take_along_axis(boundaries, counts[:, None], axis=1)[:, 0]
        return Value(last.astype(JNP_OF["date"]), "date", "scalar", "date")
    if column == _MONTH_INDEX:
        elapsed = _elapsed_months(boundaries, start)
        return Value(
            elapsed.astype(JNP_OF["i64"]), "i64", "list", "list[i64]", boundary
        )
    raise DomainRefused(
        what=(
            f"this projection axis stands as the account of {column!r}, and "
            "this clause mints projection_start_date, projection_end_date, "
            "num_proj_months and month"
        ),
        move="export the artifact again from the run that laid the axis",
        clause=_AXIS,
    )


def _fixed_step_axis(call: Call, ctx: LoweringContext, attrs: dict[str, Any]) -> Value:
    """Return one of the columns a fixed-step declaration mints.

    ``num_proj_months`` is the boundary count ``T + 1``; ``step`` is
    ``0..T``; ``month`` is ``k * 12 / n`` where ``steps_per_year=n`` makes a
    step a whole number of months, and is not minted otherwise. There is no
    start or end date: the axis has no calendar.

    Raises:
        DomainRefused: For a dated column, a ``month`` the form does not
            mint, or a column the declaration is not the account of.

    """
    spelling, step = _fixed_step(attrs)
    count = _fixed_count(attrs)
    counts = jnp.full((ctx.rows,), count, dtype=JNP_OF["i64"])
    column = ctx.node.column or ""
    if column == _BOUNDARY_COUNT:
        return Value(counts + 1, "i64", "scalar", "i64")
    boundary = Horizon.over(counts + 1, host=ctx.cells_of(call))
    steps = jnp.broadcast_to(
        jnp.arange(boundary.bucket, dtype=JNP_OF["i64"])[None, :],
        (ctx.rows, boundary.bucket),
    )
    if column == _STEP_INDEX:
        return Value(steps, "i64", "list", "list[i64]", boundary)
    if (
        column == _MONTH_INDEX
        and spelling == _STEPS_PER_YEAR
        and int(step) in _WHOLE_MONTH_STEPS
    ):
        months = _MONTHS_IN_A_YEAR // int(step)
        return Value(steps * months, "i64", "list", "list[i64]", boundary)
    raise DomainRefused(
        what=(
            f"this fixed-step axis stands as the account of {column!r}, and "
            "this form mints step, num_proj_months and, where a step is whole "
            "months, month -- it has no calendar and no dates"
        ),
        move="export the artifact again from the run that laid the axis",
        clause=_AXIS,
    )


@jax.jit
def _elapsed_months(boundaries: jax.Array, start: jax.Array) -> jax.Array:
    """Return whole calendar months from each policy's start to each boundary.

    Compiled for the reason :func:`boundaries_from_original` is: it runs on
    the host at settle time as well as inside the trace.
    """
    year, month, _ = civil_from_days(boundaries)
    opened_year, opened_month, _ = civil_from_days(start)
    return 12 * (year - opened_year[:, None]) + (month - opened_month[:, None])


def _valuation_day(attrs: dict[str, Any]) -> int:
    """Return boundary zero of the axis, as the declaration states it."""
    written = attrs.get("valuation_date") or attrs.get("start")
    if not isinstance(written, str):
        raise DomainRefused(
            what=(
                "this projection axis states neither a valuation date nor a "
                "start, so it has no boundary zero"
            ),
            move="export the artifact again from the run that laid the axis",
            clause=_AXIS,
        )
    return _epoch_days(written)


def _declared_periods(
    call: Call, ctx: LoweringContext, attrs: dict[str, Any], months: int
) -> jax.Array:
    """Return each policy's own period count, or refuse an axis the record leaves open.

    **The count, as the document states it.** A synthetic axis states its count
    outright. A policy-anchored one states a horizon kind and a value, and where that
    value is a whole term, a fixed date or a number of years the count follows
    from the attributes and the cadence. Where the horizon is named by a
    column, the call reads that column and the count is that policy's own.
    Where it is ``maximum_age`` and the call reads the issue-age column the
    attributes name, the count is that policy's own too: the age less its
    issue age, in years. Where it is ``maximum_age`` with no such read, or a
    column-named horizon the call does not read, the count was measured
    against the portfolio and is nowhere on the record -- and an axis laid
    from the attributes there would be a wrong reading rather than an
    ill-formed one.

    Raises:
        DomainRefused: If the record does not determine the count.

    """
    stated = _stated_per_policy(call, ctx, attrs, months)
    if stated is not None:
        return stated
    until = str(attrs.get("until") or "")
    value = attrs.get("until_value")
    per_year = _MONTHS_IN_A_YEAR // months
    if call.args:
        horizon = require_carrier(
            ctx.lower(call.args[0]),
            frozenset({"i64"}),
            "projection_set",
            _AXIS,
        ).array
        if until == _TERM_YEARS:
            return jnp.maximum(horizon * per_year, 0)
        if until == _TERM_MONTHS:
            return jnp.maximum(jnp.floor_divide(horizon, months), 0)
    elif isinstance(value, int) and not isinstance(value, bool):
        if until == _TERM_MONTHS:
            return jnp.full((ctx.rows,), value // months, dtype=JNP_OF["i64"])
        if until == _TERM_YEARS:
            return jnp.full((ctx.rows,), value * per_year, dtype=JNP_OF["i64"])
    elif isinstance(value, str) and until == _FIXED_DATE:
        elapsed = _epoch_months(value) - _epoch_months(str(attrs["valuation_date"]))
        return jnp.full((ctx.rows,), elapsed // months, dtype=JNP_OF["i64"])
    raise DomainRefused(
        what=(
            f"this projection axis runs until {until!r} and its length is not "
            "on the record: a horizon the attributes do not fix is measured "
            "against the whole portfolio, and two books lay two different "
            "axes under one node identity"
        ),
        move=(
            "run this model on Polars, or lay the axis on a horizon the "
            "record carries -- a whole term, a fixed date, or a column each "
            "policy's own horizon stands in"
        ),
        clause=_AXIS,
    )


def _stated_per_policy(
    call: Call, ctx: LoweringContext, attrs: dict[str, Any], months: int
) -> jax.Array | None:
    """Return a count the declaration states without a horizon kind's arithmetic.

    A synthetic axis states its count outright. A ``maximum_age`` axis whose
    call reads the issue-age column the attributes name states each
    policy's: the age less that policy's issue age, in years, at the cadence.
    None for every other declaration, and for a ``maximum_age`` with no such
    read, which :func:`_declared_periods` refuses.
    """
    synthetic = attrs.get("n_periods")
    if isinstance(synthetic, int) and not isinstance(synthetic, bool):
        return jnp.full((ctx.rows,), synthetic, dtype=JNP_OF["i64"])
    if str(attrs.get("until") or "") != _MAXIMUM_AGE:
        return None
    value = attrs.get("until_value")
    years = _years_to_the_age(
        call,
        ctx,
        issue_age_column=attrs.get("issue_age_column"),
        age=value,
        age_column=value,
        clause=_AXIS,
    )
    if years is None:
        return None
    return jnp.maximum(years * (_MONTHS_IN_A_YEAR // months), 0)


def _epoch_months(written: str) -> int:
    """Return one ISO calendar day as a count of months from year zero."""
    import datetime  # noqa: PLC0415 -- one parse, on the host

    day: datetime.date = datetime.date.fromisoformat(written)
    return day.year * 12 + (day.month - 1)
