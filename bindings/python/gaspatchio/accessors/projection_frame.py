# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Frame-level projection accessor — set() unifies projection axis setup.
# ABOUTME: rollforward() reads schedule from frame; both go through this accessor.

"""Frame-level projection accessor for actuarial projection setup."""

from __future__ import annotations

import datetime as dt
import decimal
import weakref
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from gaspatchio._authoring import emit
from gaspatchio._semantic.ir import Call
from gaspatchio.accessors.base import BaseFrameAccessor
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame._across_rows import refuse_a_grid_sized_from_the_rows
from gaspatchio.frame.calculations import CalculationRecord, with_columns_operation
from gaspatchio.frame.lowering.artefacts import register_schedule
from gaspatchio.frame.lowering.context import context_for
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.frame.registry import register_accessor
from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.schedule import Schedule
from gaspatchio.schedule._data import (
    FIXED_STEP,
    fixed_step_months_per_step,
    refuse_dates_on_a_fixed_step,
)
from gaspatchio.schedule._schedule import refuse_an_end_date

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gaspatchio._semantic.ir import AttrValue
    from gaspatchio.frame.base import ActuarialFrame
    from gaspatchio.rollforward._builder import ExprLike


# English-frequency -> Schedule frequency mapping.
_ENGLISH_TO_SCHED_FREQ: dict[str, str] = {
    "monthly": "1M",
    "quarterly": "3M",
    "semi-annual": "6M",
    "annual": "1Y",
    "weekly": "1W",
    "daily": "1D",
}
_VALID_SCHED_FREQ: frozenset[str] = frozenset({"1M", "3M", "6M", "1Y", "1W", "1D"})

# Periods-per-year by Schedule frequency. Used to convert "until_value"
# expressed in years/months/dates into Schedule n_periods.
_PERIODS_PER_YEAR: dict[str, int] = {
    "1M": 12,
    "3M": 4,
    "6M": 2,
    "1Y": 1,
    "1W": 52,
    "1D": 365,
}

# Months per period (only meaningful for monthly-aligned frequencies).
_MONTHS_PER_PERIOD: dict[str, int] = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}


# Columns projection.set() materialises. `year` is deliberately absent: model
# points routinely carry a calendar year, and Gotcha #7 already names
# `proj_year` vs `year` as a cause of silently-wrong stress scenarios.
_MONTH_COLUMN = "month"
# The boundary index a fixed-step axis stamps, 0..T: a workbook's step column.
_STEP_COLUMN = "step"
# What each reserved index means, and the kind of column of the model's own a
# collision is most likely to be, for the rename-or-drop refusal.
_RESERVED_MEANING: dict[str, tuple[str, str]] = {
    _MONTH_COLUMN: ("elapsed whole months from projection start", "a calendar month"),
    _STEP_COLUMN: (
        "the step index 0..T of a fixed-step axis",
        "a step index carried in the model points",
    ),
}


def _elapsed_months_expr(period_dates: pl.Expr) -> pl.Expr:
    """Return elapsed whole months from each row's first period boundary.

    A calendar-month difference, exact only when the boundaries sit on a
    month-aligned grid sharing one anchor convention — which is why the
    caller stamps ``month`` for 1M/3M/6M/1Y and never for 1W/1D, where the
    day component would make this over-count by up to a month.
    """
    return period_dates.list.eval(
        (pl.element().dt.year() - pl.element().first().dt.year()) * 12
        + (pl.element().dt.month() - pl.element().first().dt.month())
    ).cast(pl.List(pl.Int64))


def _until_value_attr(until_value: Any) -> AttrValue:  # noqa: ANN401 — mirrors set()'s own parameter
    """Render an ``until_value`` as one flat attribute value.

    A ``Call`` attribute is a flat typed value (see ``ir.AttrValue``), and
    the horizon arrives in four shapes. Each keeps the form that is true
    for it: a term of thirty years is the **integer** thirty, not the text
    ``"30"``; a fixed date is ISO text, the same encoding
    ``valuation_date`` gets; a per-policy horizon is the column name the
    caller passed; and a ``pl.Expr`` horizon is rendered as Polars renders
    it, since the op-tree cannot carry a live expression in an attribute.
    """
    if until_value is None or isinstance(until_value, (int, str)):
        return until_value
    if isinstance(until_value, dt.date):
        return until_value.isoformat()
    return str(until_value)


def _whole_count(name: str, value: Any) -> Any:  # noqa: ANN401 -- mirrors set()'s own parameter
    """Return a count given as a whole double or decimal as its integer, or refuse.

    ``n_periods`` and ``steps_per_year`` count periods and steps. ``True`` was
    read as 1 and ``3.0`` was refused in Python's words; a whole number of any
    numeric kind is now that number, one that is not whole is refused by
    value, and a flag or text is refused by kind.

    Raises:
        TypeError: ``value`` is a flag or text.
        ValueError: ``value`` is a number that is not whole.

    """
    if value is None or (isinstance(value, int) and not isinstance(value, bool)):
        return value
    if isinstance(value, (float, decimal.Decimal)):
        if value == int(value):
            return int(value)
        msg = (
            f"projection.set({name}={value!r}): {name} is a whole number of "
            f"{_COUNTED[name]}, and {value!r} is not one."
        )
        raise ValueError(msg)
    msg = (
        f"projection.set({name}={value!r}): {name} is a whole number of "
        f"{_COUNTED[name]}, and this is a {type(value).__name__}."
    )
    raise TypeError(msg)


# What each whole-number count of ``projection.set`` counts.
_COUNTED: dict[str, str] = {
    "n_periods": "periods (T periods lay T + 1 boundaries)",
    "steps_per_year": "steps a year",
}


# ``until="next_anniversary"`` read k whole years from the valuation date
# (``term_years``'s count) while its name promised each policy's own contract
# anniversary. It is refused by name, pointing at what each reading is
# written as.
_NEXT_ANNIVERSARY_REMOVED = (
    'projection.set(until="next_anniversary") is removed: it ran k whole years '
    "from the valuation date for every policy, not to each policy's own contract "
    "anniversary, which is what the name says. For k whole years write "
    'until="term_years", until_value=k (the same count). For a horizon on each '
    "policy's contract anniversaries, lay the axis with "
    'Schedule.from_inception(inception_column="policy_inception", ...) and read '
    "renewals with af.projection.anniversary_mask()."
)

# The ``until`` forms whose string ``until_value`` is a column name: the
# horizon is a count read per policy from that column.
_UNTIL_READS_A_COLUMN = frozenset({"term_months", "term_years"})

# The horizons that take a whole number, and what that number counts.
_WHOLE_HORIZONS: dict[str, str] = {
    "term_years": "years",
    "term_months": "months",
    "maximum_age": "years of age",
}
# The move a refusal of a horizon that is not whole names, per horizon.
_WHOLE_MOVE: dict[str, str] = {
    "term_years": (
        "For a term with months in it, write until='term_months' with the "
        "number of months, rounded in the model the way you mean."
    ),
    "term_months": (
        "Round the term in the model the way you mean (floor, ceil or "
        "round) before projection.set()."
    ),
    "maximum_age": (
        "State the attained age the projection stops at as a whole number."
    ),
}


def _projection_attrs(  # noqa: PLR0913 — mirrors set()'s own call-form parameters, one attribute source each
    *,
    frequency: str | None,
    until: str | None,
    until_value: Any,  # noqa: ANN401 — mirrors set()'s own parameter
    valuation_date: dt.date | None,
    start_date: dt.date | None,
    n_periods: int | None,
    schedule: Schedule | None,
    issue_age_column: str | None = None,
) -> tuple[tuple[str, AttrValue], ...]:
    """Return the timeline configuration a ``projection_set`` record carries.

    These are the arguments ``set()`` was called with, not properties
    re-derived from the Schedule it built -- except on the ``schedule=`` form,
    which passes no arguments of its own and so states what the object itself
    carries instead. ``set()`` has three call forms and they populate
    different amounts of this:

    - **policy-anchored** (``valuation_date`` / ``until`` / ``until_value`` /
      ``frequency``) -- all four populated.
    - **synthetic** (``start_date`` / ``n_periods`` / ``frequency``) --
      ``frequency``, plus ``start`` (ISO date text, the same encoding
      ``valuation_date`` gets) and ``n_periods`` (int) recording this form's
      own two parameters. ``until``/``until_value``/``valuation_date`` stay
      ``None`` -- this call form simply has no such arguments, the same way
      ``start``/``n_periods`` are absent from the other two forms' records.
    - **``schedule=``** -- ``frequency`` (a required field on every
      ``Schedule``, so always genuinely present) and, only for a per-policy
      (jagged) schedule, ``until`` (its ``until_kind``); ``start`` (ISO date
      text) whenever the schedule genuinely carries a ``start_date`` -- true
      for ``from_calendar_grid`` and ``per_policy_grid``, ``None`` only for
      ``from_inception``, whose axis is anchored per-policy on a column
      instead; plus ``schedule_source_sha``, the object's own
      ``source_sha()`` -- reused verbatim, never rehashed. ``until_value``
      and ``valuation_date`` stay ``None`` here regardless of schedule kind:
      a schedule's ``n_periods`` is a period count, not a term expressed in
      one of ``until_value``'s shapes, and ``valuation_date`` is the
      policy-anchored form's own argument name -- this form never received
      one, so the schedule's own start date (when it has one) is reported
      under ``start`` instead, the same name the synthetic form uses for the
      same concept, rather than borrowed under a name nobody here passed.

    A six-period and a six-hundred-period request are now distinguishable
    from the record alone on every call form: the synthetic form via
    ``n_periods`` directly, the ``schedule=`` form via
    ``schedule_source_sha`` (which changes whenever any canonical parameter
    -- including the period count -- does).

    A ``maximum_age`` horizon also states ``issue_age_column``, the column
    each policy's own horizon is measured from: ``until_value`` less that
    policy's issue age, in whole years. With the column the node reads, the
    record fixes every policy's boundary count.
    """
    if schedule is not None and schedule._kind == FIXED_STEP:  # noqa: SLF001
        return _fixed_step_attrs(schedule)
    if schedule is not None:
        return (
            ("frequency", schedule.frequency),
            ("until", schedule.until_kind),
            ("until_value", None),
            ("valuation_date", None),
            (
                "start",
                schedule.start_date.isoformat()
                if schedule.start_date is not None
                else None,
            ),
            ("schedule_source_sha", schedule.source_sha()),
        )

    attrs: tuple[tuple[str, AttrValue], ...] = (
        ("frequency", frequency),
        ("until", until),
        ("until_value", _until_value_attr(until_value)),
        (
            "valuation_date",
            valuation_date.isoformat() if valuation_date is not None else None,
        ),
    )
    if until == "maximum_age":
        attrs = (*attrs, ("issue_age_column", issue_age_column))
    if start_date is not None and n_periods is not None:
        attrs = (
            *attrs,
            ("start", start_date.isoformat()),
            ("n_periods", n_periods),
        )
    return attrs


def _fixed_step_attrs(schedule: Schedule) -> tuple[tuple[str, AttrValue], ...]:
    """Return the record of a fixed-step axis: its step count and its step.

    The same whichever door laid it -- ``set(n_periods=, step_years=)`` or
    ``set(schedule=Schedule.fixed_step(...))`` -- because the axis is wholly
    stated by these two numbers and no calendar stands behind either.
    ``frequency`` is null: a step axis has no calendar cadence. The step is
    the one the model wrote, ``step_years`` (the decimal as written) xor
    ``steps_per_year``, never converted into the other: the two spellings
    differ in the last bits.
    """
    step: tuple[str, AttrValue] = (
        ("steps_per_year", schedule.steps_per_year)
        if schedule.steps_per_year is not None
        else ("step_years", schedule.step_years)
    )
    return (
        ("frequency", None),
        ("until", None),
        ("until_value", None),
        ("valuation_date", None),
        ("n_periods", schedule.n_periods),
        step,
    )


def _refuse_a_calendar_argument_on_a_fixed_step(
    *,
    given: dict[str, Any],
    step: str,
) -> None:
    """Refuse a calendar or horizon argument passed beside a fixed step.

    Args:
        given: Every other ``set()`` argument the caller passed, by name.
        step: The step argument, as written (``step_years=0.1``).

    Raises:
        ValueError: If any calendar or horizon argument came with the step.

    """
    named = [name for name, value in given.items() if value is not None]
    if not named:
        return
    calendar = [n for n in named if n in ("start_date", "valuation_date", "frequency")]
    if calendar:
        msg = (
            f"projection.set() was given a fixed step ({step}) and a calendar "
            f"({', '.join(calendar)}). A fixed-step axis has no calendar under "
            "it: its boundaries are k steps of a fixed number of years, with no "
            "dates. Pass one form -- af.projection.set(n_periods=..., "
            f"{step}) for a step axis, or the calendar form "
            'af.projection.set(start_date=..., n_periods=..., frequency="monthly") '
            "for dated periods."
        )
        raise ValueError(msg)
    msg = (
        f"projection.set() was given a fixed step ({step}) and "
        f"{', '.join(named)}. A step axis is sized by n_periods alone: give the "
        "number of steps, af.projection.set(n_periods=..., "
        f"{step}). Horizons such as until= and per-policy timelines are the "
        "calendar form's."
    )
    raise ValueError(msg)


def _normalise_frequency(freq: str) -> str:
    """Map English vocab to Schedule shorthand, or pass shorthand through."""
    if freq in _ENGLISH_TO_SCHED_FREQ:
        return _ENGLISH_TO_SCHED_FREQ[freq]
    if freq in _VALID_SCHED_FREQ:
        return freq
    valid = sorted(set(_ENGLISH_TO_SCHED_FREQ) | _VALID_SCHED_FREQ)
    msg = f"unsupported frequency {freq!r}; expected one of {valid}"
    raise ValueError(msg)


def _months_to_periods(months: int, sched_freq: str) -> int:
    """Convert a month count into the number of Schedule periods."""
    if sched_freq in _MONTHS_PER_PERIOD:
        return months // _MONTHS_PER_PERIOD[sched_freq]
    # 1W / 1D — months-based until_value is not really meaningful for these,
    # but fall back to a simple month-aligned conversion via 1M.
    return months


def _refuse_a_year_horizon_below_a_month(until: str, sched_freq: str) -> None:
    """Refuse a horizon in months or years at a weekly or daily cadence.

    A month/year horizon (term_months/term_years) with a sub-month cadence
    (1W/1D) makes the period count ambiguous -- the uniform and jagged paths
    would disagree silently (a 12-month term gives ~12 periods uniform but ~52
    jagged at weekly). A maximum age is a horizon in whole years too, and N
    years is not a whole number of weeks or days (52N against the calendar's
    ~52.18N).
    """
    if (
        until not in ("term_months", "term_years", "maximum_age")
        or sched_freq in _MONTHS_PER_PERIOD
    ):
        return
    msg = (
        f"until={until!r} is a month/year horizon and requires a "
        f"month-aligned frequency (one of {sorted(_MONTHS_PER_PERIOD)}); "
        f"got a frequency resolving to {sched_freq!r}. Use a monthly / "
        "quarterly / semi-annual / annual frequency."
    )
    if until == "maximum_age":
        msg += (
            " A maximum age runs each policy a whole number of years, the age "
            "less its issue age, and a number of years is not a whole number "
            "of weeks or days."
        )
    raise ValueError(msg)


def _refuse_a_shared_grid_read_from_the_rows(
    frame: ActuarialFrame,
    *,
    until: str,
    until_value: Any,  # noqa: ANN401 — mirrors set()'s own parameter
    issue_age_column: str,
    per_policy: bool | None,
) -> None:
    """Refuse one shared grid sized from the rows where they are not the book."""
    if not _sized_from_the_rows(until, until_value):
        return
    refuse_a_grid_sized_from_the_rows(
        frame,
        grid=_the_shared_grid(
            until, until_value, issue_age_column, per_policy=per_policy
        ),
        route=_a_grid_of_its_own(until, until_value, issue_age_column),
    )


def _sized_from_the_rows(until: str | None, until_value: Any) -> bool:  # noqa: ANN401 — mirrors set()'s own parameter
    """Return whether a shared grid for this horizon takes its length from the rows.

    A maximum age is measured against the frame's issue ages in every form;
    a term or a number of years is read from the frame wherever it is a
    column or an expression rather than a number.
    """
    if until == "maximum_age":
        return True
    return until in ("term_months", "term_years") and not (isinstance(until_value, int))


def _the_shared_grid(
    until: str | None,
    until_value: Any,  # noqa: ANN401 — mirrors set()'s own parameter
    issue_age_column: str,
    *,
    per_policy: bool | None,
) -> str:
    """Name a shared grid sized from the rows, and what in the rows sizes it."""
    written = until_value if isinstance(until_value, (int, str)) else str(until_value)
    forced = ", per_policy=False" if per_policy is False else ""
    call = f"projection.set(until={until!r}, until_value={written!r}{forced})"
    if until == "maximum_age":
        return (
            f"{call} lays one shared grid, every policy's axis run to the "
            "youngest life in the frame: its length is read from the smallest "
            f"{issue_age_column!r} among the rows"
        )
    sized_by = (
        f"the largest {until_value!r}"
        if isinstance(until_value, str)
        else "the largest value of that expression"
    )
    return (
        f"{call} lays one shared grid, every policy's axis run to the longest "
        f"horizon in the frame: its length is read from {sized_by} among the rows"
    )


def _a_grid_of_its_own(
    until: str | None,
    until_value: Any,  # noqa: ANN401 — mirrors set()'s own parameter
    issue_age_column: str,
) -> str:
    """Say how to lay this axis without reading its length from the rows."""
    if until == "maximum_age":
        years = (
            f"{until_value} - int(model_points[{issue_age_column!r}].min())"
            if isinstance(until_value, int)
            else f"int((model_points[{until_value!r}] - "
            f"model_points[{issue_age_column!r}]).max())"
            if isinstance(until_value, str)
            else "the longest span over the book"
        )
        return (
            "Give each policy its own horizon -- leave per_policy at its "
            "default, which runs each life to the age -- or take the longest "
            "span over the book before the run and state the grid as a term "
            f"-- until='term_years', until_value={years}"
        )
    read = (
        f"int(model_points[{until_value!r}].max())"
        if isinstance(until_value, str)
        else "int(model_points.select(<the expression>.max()).item())"
    )
    own = (
        "Give each policy its own horizon -- leave per_policy at its default, "
        "which runs each policy to its own term -- or take"
        if until in ("term_months", "term_years") and isinstance(until_value, str)
        else "Take"
    )
    return (
        f"{own} the longest horizon over the book before the run and state it "
        f"as a number -- until_value={read}"
    )


@register_accessor("projection", kind="frame")
class ProjectionFrameAccessor(BaseFrameAccessor):
    """Frame-level accessor for actuarial projection operations.

    Two verbs:
      - ``set(...)`` — declare the projection time axis on the frame
      - ``rollforward(...)`` — construct a state-machine rollforward
        builder that reads the projection from this frame

    ``projection`` is a reserved attribute on the frame, as ``date``,
    ``excel``, ``finance`` and ``graph`` are. A model whose data really does
    carry a column called ``projection`` still has it -- reach it as
    ``af["projection"]`` -- but ``af.projection`` is always this accessor.
    """

    def __init__(self, frame: ActuarialFrame) -> None:
        """Bind this accessor to ``frame``."""
        super().__init__(frame)

    def set(  # noqa: PLR0913
        self,
        *,
        # Schedule path (mutually exclusive with the rest)
        schedule: Schedule | None = None,
        # Kwargs path — policy-anchored
        valuation_date: dt.date | None = None,
        until: Literal[
            "maximum_age",
            "term_years",
            "term_months",
            "fixed_date",
        ]
        | None = None,
        until_value: int | dt.date | str | pl.Expr | None = None,
        issue_age_column: str = "issue_age",
        # Kwargs path — synthetic
        start_date: dt.date | None = None,
        n_periods: int | None = None,
        # Common
        frequency: str | None = None,
        per_policy: bool | None = None,
        # Kwargs path — fixed step, no calendar
        step_years: float | None = None,
        steps_per_year: int | None = None,
    ) -> ActuarialFrame:
        """Declare the projection time axis on this frame.

        Four forms. **Policy-anchored** (``valuation_date``, ``until``,
        ``until_value``, ``frequency``) runs each policy from the valuation
        date to its own horizon; **synthetic** (``start_date``,
        ``n_periods``, ``frequency``) lays a calendar grid; **schedule=**
        hands over a :class:`Schedule`; and **fixed step**
        (``n_periods`` with ``step_years`` or ``steps_per_year``) lays
        ``n_periods`` steps of a fixed number of years with no calendar under
        them -- the axis of a teaching workbook or a numerical solution of
        Thiele's or Kolmogorov's equations:

        ```python
        af = af.projection.set(n_periods=2947, step_years=0.1)  # time k * 0.1
        af = af.projection.set(n_periods=240, steps_per_year=12)  # time k / 12
        af.x_t = af.issue_age + af.projection.t_years()
        ```

        A fixed-step axis stamps ``step`` (``0..T``, Int64, the workbook's
        step column), ``num_proj_months`` (the boundary count ``T + 1``) and,
        only where one step is a whole number of months (``steps_per_year``
        of 1, 2, 3, 4, 6 or 12), ``month`` (``k * 12 / steps_per_year``). It
        has no dates: ``period_dates()`` and ``end_date_column`` refuse, and
        so do ``start_date``, ``valuation_date``, ``frequency`` and ``until``
        passed beside the step. ``step`` is reserved like ``month``.

        With a per-policy ``until_value`` column, each policy projects only as
        far as its own horizon — producing variable-length (jagged) list
        columns instead of one uniform grid sized to the longest-lived policy.
        This recovers the compute/memory of per-policy timelines while keeping
        the unified projection API.

        ``until="maximum_age"`` runs each policy to its own horizon:
        ``until_value`` less its issue age (``issue_age_column``), in whole
        years at the schedule's frequency, so every life stops at attained age
        ``until_value`` whoever shares the run -- for a number, a column name
        or an expression ``until_value``, at a monthly, quarterly, semi-annual
        or annual frequency; a weekly or daily one is refused, as it is for a
        term. The record names ``issue_age_column``.

        ``per_policy`` (default ``None`` = auto): jagged is the default whenever
        it applies (a column ``until_value`` with a ``term_*`` horizon, or a
        ``maximum_age`` horizon at a month-aligned frequency); other cases fall
        back to a uniform grid. Pass ``per_policy=False`` to force a
        uniform (rectangular) grid — useful when combining fixed-width list
        columns or doing cross-policy shared-axis aggregation. Pass
        ``per_policy=True`` to require jagged (raises if it cannot apply).
        A shared grid whose length is read from the rows -- a maximum age, a
        term column or expression -- is a read
        across rows: it is refused in a batch runner cutting the book into
        batches and on a scenario axis, and stands where the frame is the
        whole book.
        ``rollforward()`` works on both uniform and jagged timelines.

        Stamps ``projection_start_date``, ``projection_end_date``,
        ``num_proj_months``, and — at month-aligned frequencies on a
        projection-anchored axis — ``month``: elapsed whole months from the
        projection start, length ``n_periods + 1``, aligned with
        ``t_years()``. Derive a year label in the model with the convention
        you mean: ``af.month // 12`` (completed years / duration) or
        ``ceil(month / 12)`` ("year 1" ordinal). There is deliberately no
        ``proj_year`` or ``year`` column.

        The synthetic form lays its grid on month-ends, as
        :meth:`Schedule.from_calendar_grid` does by default: whatever day of
        the month ``start_date`` falls on, the 1st included, the grid starts
        on that month's last day (``2025-01-01`` and ``2025-01-15`` both give
        ``projection_start_date`` ``2025-01-31``, at every frequency). The
        policy-anchored form starts there too wherever it lays one shared
        grid -- a whole-number ``until_value``, ``fixed_date``, or
        ``per_policy=False`` -- so ``valuation_date=2025-06-15`` opens the
        axis on ``2025-06-30`` (and ``fixed_date=2026-06-15`` closes it on
        ``2026-06-30``). A per-policy (jagged) grid -- a term column or
        ``maximum_age`` at the default ``per_policy`` -- starts on the
        ``valuation_date`` exactly as given (spec 11.1.1).
        ``num_proj_months`` is the number of period boundaries,
        ``n_periods + 1`` at every frequency (``4`` for three annual
        periods), not a count of months or periods.

        !!! warning "This modifies the frame you call it on"
            The timeline is stamped **in place** and the same frame is handed
            back, the way ``rename``, ``join`` and ``filter`` already work.
            That is what keeps a model's phase-one calculations answerable
            once the projection axis exists — a replacement frame would start
            with no history of them. It also means there is no "before"
            frame to keep:

            ```python
            af = af.projection.set(...)  # the idiom: rebind
            monthly = af.projection.set(...)  # NOT two independent
            annual = af.projection.set(...)  # timelines — the second
            # re-projects the first
            ```

            To project the same model points two ways, build two frames
            (``ActuarialFrame(model_points)`` twice) and set a timeline on
            each. Re-projecting a frame that already has a timeline is
            supported and replaces it, stamps included: a column the
            previous axis stamped that the new one does not mint is dropped
            (weekly after monthly keeps no ``month``, a calendar axis after a
            fixed step keeps no ``step``), so no index of the old length
            sits beside the new axis. Only the frame's own stamps go -- a
            column the model wrote over, or carried in under one of those
            names, is the model's, and a ``set()`` that would mint its name
            refuses it as the first ``set()`` would.

        Returns:
            This same frame, now carrying the projection axis.

        Raises:
            ValueError: if the frame already carries a ``month`` column (or,
                on a fixed-step axis, a ``step`` column) that is not this
                frame's own untouched stamp -- a model-point column, one the
                model wrote over, or one reloaded from a previous run's
                output with no in-session projection — rename your column, or
                drop it if it came from a previous run's output.
            ValueError: if a fixed step is given with a calendar or horizon
                argument, or both ``step_years`` and ``steps_per_year``.
            ValueError: if both kwargs forms are passed — the synthetic
                ``start_date``/``n_periods`` pair and any of the
                policy-anchored ``valuation_date``/``until``/``until_value``.
                They describe different axes, so pass one or the other.

        See ref/38-projection-axis/specs for full semantics.

        """
        self._frame._refuse_a_door_past_a_break("projection.set")  # noqa: SLF001
        if until == "next_anniversary":
            raise ValueError(_NEXT_ANNIVERSARY_REMOVED)
        n_periods = _whole_count("n_periods", n_periods)
        steps_per_year = _whole_count("steps_per_year", steps_per_year)
        if step_years is not None or steps_per_year is not None:
            return self._set_fixed_step(
                schedule=schedule,
                n_periods=n_periods,
                step_years=step_years,
                steps_per_year=steps_per_year,
                others={
                    "start_date": start_date,
                    "valuation_date": valuation_date,
                    "frequency": frequency,
                    "until": until,
                    "until_value": until_value,
                    "per_policy": per_policy,
                },
            )

        # Mutual exclusion check
        kwargs_provided = any(
            v is not None
            for v in (valuation_date, until, until_value, start_date, n_periods)
        )
        if schedule is not None and kwargs_provided:
            msg = (
                "schedule= cannot be combined with valuation_date / until / "
                "start_date / n_periods. Pass either a Schedule object OR "
                "construction kwargs, not both."
            )
            raise ValueError(msg)

        # The two kwargs forms are alternatives, not a blend. Given both,
        # _build_schedule() takes the synthetic branch first and never reads
        # the valuation date -- while the projection record echoes every
        # kwarg that was passed, so the axis reads as policy-anchored and
        # runs as a calendar grid. Refuse, naming both forms.
        synthetic = [
            name
            for name, value in (("start_date", start_date), ("n_periods", n_periods))
            if value is not None
        ]
        anchored = [
            name
            for name, value in (
                ("valuation_date", valuation_date),
                ("until", until),
                ("until_value", until_value),
            )
            if value is not None
        ]
        if synthetic and anchored:
            msg = (
                "projection.set() was given both the synthetic form "
                f"(start_date/n_periods: {', '.join(synthetic)}) and the "
                "policy-anchored form (valuation_date/until/until_value: "
                f"{', '.join(anchored)}). Pass one form: synthetic lays a "
                "calendar grid from a start date; policy-anchored runs each "
                "policy from the valuation date to its own horizon."
            )
            raise ValueError(msg)

        # A horizon is a whole number: a term, or an attained age. A whole
        # number held as a double reads as that number; one that is not whole,
        # text and a flag are refused here rather than truncated or read as 1.
        until_value = self._whole_horizon(until, until_value)

        # A string until_value names the column each policy's horizon is read
        # from. A name the frame does not carry is refused here, in the
        # model's words, rather than failing later inside the query plan.
        if isinstance(until_value, str) and until in _UNTIL_READS_A_COLUMN:
            columns = self._plan().collect_schema().names()
            if until_value not in columns:
                msg = (
                    f"projection.set(until={until!r}, until_value={until_value!r}) "
                    f"reads each policy's horizon from a column called "
                    f"{until_value!r}, but the frame has no column of that name. "
                    "Pass the name the frame uses, or rename the column first. "
                    f"Columns on the frame: {', '.join(columns)}."
                )
                raise ValueError(msg)

        if until == "maximum_age":
            self._refuse_an_issue_age_column_that_is_not_an_age(
                until_value, issue_age_column
            )

        # Captured before the possible rebuild below: `None` unless the
        # caller passed schedule= directly, which is exactly the case
        # _projection_attrs needs to distinguish "built from arguments"
        # from "handed over as an object".
        caller_schedule = schedule
        if schedule is None:
            schedule = self._build_schedule(
                valuation_date=valuation_date,
                until=until,
                until_value=until_value,
                issue_age_column=issue_age_column,
                start_date=start_date,
                n_periods=n_periods,
                frequency=frequency,
                per_policy=per_policy,
            )

        return self._stamp_eager_columns(
            schedule,
            _projection_attrs(
                frequency=frequency,
                until=until,
                until_value=until_value,
                valuation_date=valuation_date,
                start_date=start_date,
                n_periods=n_periods,
                schedule=caller_schedule,
                issue_age_column=issue_age_column,
            ),
        )

    def _set_fixed_step(
        self,
        *,
        schedule: Schedule | None,
        n_periods: int | None,
        step_years: float | None,
        steps_per_year: int | None,
        others: dict[str, Any],
    ) -> ActuarialFrame:
        """Lay a fixed-step axis from ``set()``'s step arguments."""
        step = (
            f"steps_per_year={steps_per_year!r}"
            if steps_per_year is not None
            else f"step_years={step_years!r}"
        )
        if schedule is not None:
            msg = (
                f"schedule= cannot be combined with {step}: a Schedule states its "
                "own axis. Pass Schedule.fixed_step(...) as schedule=, or the step "
                "arguments directly, not both."
            )
            raise ValueError(msg)
        _refuse_a_calendar_argument_on_a_fixed_step(given=others, step=step)
        if n_periods is None:
            msg = (
                f"projection.set({step}) needs the number of steps: "
                f"af.projection.set(n_periods=..., {step}) lays n_periods steps "
                "and n_periods + 1 boundaries."
            )
            raise ValueError(msg)
        fixed = Schedule.fixed_step(
            n_periods=n_periods, step_years=step_years, steps_per_year=steps_per_year
        )
        return self._stamp_eager_columns(fixed, _fixed_step_attrs(fixed))

    def _whole_horizon(self, until: str | None, until_value: Any) -> Any:  # noqa: ANN401 -- mirrors set()'s own parameter
        """Return ``until_value`` with a whole double read as its integer, or refuse.

        §11.1.1: ``term_months`` and ``term_years`` take a whole term and
        ``maximum_age`` a whole attained age. A double or decimal that is a
        whole number is that number; one that is not was truncated (a
        0.75-year term projected nowhere), text spelling a number was read as
        one, and ``True`` was read as 1. Each of those is refused, by value
        or by kind, naming the column and the move.

        Raises:
            ValueError: A literal or a column value is not a whole number.
            TypeError: A literal or a column holds text, flags or another
                kind that is not a number.

        """
        if until not in _WHOLE_HORIZONS or until_value is None:
            return until_value
        unit = _WHOLE_HORIZONS[until]
        said = f"projection.set(until={until!r})"
        if isinstance(until_value, bool):
            msg = (
                f"{said} was given until_value={until_value!r}, a flag; it takes "
                f"a whole number of {unit}."
            )
            raise TypeError(msg)
        if isinstance(until_value, (float, decimal.Decimal)):
            if until_value == int(until_value):
                return int(until_value)
            msg = (
                f"{said} takes a whole number of {unit}, and until_value="
                f"{until_value!r} is not one; it would be cut to "
                f"{int(until_value)}. {_WHOLE_MOVE[until]}"
            )
            raise ValueError(msg)
        if isinstance(until_value, str):
            if until_value not in self._plan().collect_schema().names():
                return until_value  # the refusal below names the missing column
            expr, named = pl.col(until_value), f"column {until_value!r}"
        elif isinstance(until_value, pl.Expr):
            expr, named = until_value, f"until_value={until_value!s}"
        else:
            return until_value
        self._refuse_a_horizon_that_is_not_whole(
            expr, named=named, said=said, unit=unit, until=until
        )
        return until_value

    def _refuse_an_issue_age_column_that_is_not_an_age(
        self, until_value: object, issue_age_column: str
    ) -> None:
        """Refuse an issue-age column a ``maximum_age`` horizon cannot read.

        Each policy runs ``until_value`` less its issue age (§11.1.1), read
        from ``issue_age_column``. A name the frame does not carry failed
        inside the query plan in Polars' words, text failed there as
        arithmetic on a string, and a flag was read as an issue age of 1.
        Each is refused here, naming the column and the move.

        Raises:
            ValueError: The frame has no column of that name.
            TypeError: The column holds text, flags or another kind that is
                not a number.

        """
        said = f"projection.set(until='maximum_age', until_value={until_value!r})"
        schema = self._plan().collect_schema()
        if issue_age_column not in schema.names():
            msg = (
                f"{said} runs each policy to that age from its issue age, read "
                f"from the column issue_age_column={issue_age_column!r}, but the "
                "frame has no column of that name. Pass issue_age_column= the "
                "name the frame uses, or rename the column first. Columns on "
                f"the frame: {', '.join(schema.names())}."
            )
            raise ValueError(msg)
        dtype = schema[issue_age_column]
        if dtype == pl.Null or (dtype.is_numeric() and dtype != pl.Boolean):
            return
        msg = (
            f"{said} reads each policy's issue age from column "
            f"{issue_age_column!r}, which holds {dtype} values; an issue age is "
            "a number. Read it as a number before projection.set(), for "
            "example pl.col(name).cast(pl.Int64) in the setup phase."
        )
        raise TypeError(msg)

    def _refuse_a_horizon_that_is_not_whole(
        self, expr: pl.Expr, *, named: str, said: str, unit: str, until: str
    ) -> None:
        """Refuse a horizon column of another kind, or holding a value not whole."""
        (dtype,) = self._plan().select(expr.alias("_horizon")).collect_schema().dtypes()
        if dtype.is_integer() or dtype == pl.Null:
            return
        if not (dtype.is_float() or dtype.is_decimal()):
            msg = (
                f"{said} reads each policy's horizon from {named}, which holds "
                f"{dtype} values; a horizon is a whole number of {unit}. Read it "
                "as a number before projection.set(), for example "
                "pl.col(name).cast(pl.Int64) in the setup phase."
            )
            raise TypeError(msg)
        value = expr.cast(pl.Float64)
        not_whole = value.is_not_null() & (value != value.floor())
        found = self._plan().select(expr.filter(not_whole).first()).collect().item()
        if found is None:
            return
        msg = (
            f"{said} takes a whole number of {unit}, and {named} holds "
            f"{found!r}, which is not one; it would be cut to {int(found)}. "
            f"{_WHOLE_MOVE[until]}"
        )
        raise ValueError(msg)

    def _build_schedule(  # noqa: PLR0913
        self,
        *,
        valuation_date: dt.date | None,
        until: str | None,
        until_value: Any,  # noqa: ANN401
        issue_age_column: str,
        start_date: dt.date | None,
        n_periods: int | None,
        frequency: str | None,
        per_policy: bool | None = None,
    ) -> Schedule:
        """Construct a Schedule from the kwargs path."""
        if frequency is None:
            msg = "frequency is required"
            raise ValueError(msg)
        sched_freq = _normalise_frequency(frequency)

        # Synthetic case: start_date + n_periods
        if start_date is not None and n_periods is not None:
            return Schedule.from_calendar_grid(
                start_date=start_date,
                n_periods=n_periods,
                frequency=sched_freq,  # type: ignore[arg-type]
            )

        # Policy-anchored case: valuation_date + until + until_value
        if valuation_date is None or until is None or until_value is None:
            msg = (
                "Either provide schedule=, "
                "OR start_date+n_periods+frequency (synthetic), "
                "OR valuation_date+until+until_value+frequency (policy-anchored), "
                "OR n_periods+step_years or n_periods+steps_per_year (fixed step, "
                "no calendar)."
            )
            raise ValueError(msg)

        _refuse_a_year_horizon_below_a_month(until, sched_freq)

        # Resolve jagged-vs-uniform. ``per_policy=None`` (auto, the default)
        # prefers jagged whenever it applies — a column ``until_value`` with a
        # ``term_*`` horizon, or a ``maximum_age`` horizon in any form at a
        # month-aligned cadence — and falls back to uniform otherwise.
        # Explicit ``True`` requires jagged (raises if inapplicable); explicit
        # ``False`` forces uniform.
        to_an_age = until == "maximum_age"
        jagged_applicable = to_an_age or (
            isinstance(until_value, str) and until in ("term_months", "term_years")
        )
        use_per_policy = jagged_applicable if per_policy is None else per_policy

        # A shared grid whose length is read from the rows -- the youngest
        # issue age, the longest term, the largest number of years -- is a
        # read across rows: in a batch it is the batch's, on a scenario axis
        # every scenario's together. It stands where the frame is the book.
        if not use_per_policy:
            _refuse_a_shared_grid_read_from_the_rows(
                self._frame,
                until=until,
                until_value=until_value,
                issue_age_column=issue_age_column,
                per_policy=per_policy,
            )

        # A maximum age is each policy's own horizon: ``until_value`` less its
        # issue age. One grid sized from the youngest life would project
        # every older life past the age asked for, and its value would then
        # depend on which other policies share the run.
        if use_per_policy and to_an_age:
            return Schedule._to_maximum_age(  # noqa: SLF001
                start_date=valuation_date,
                frequency=sched_freq,  # type: ignore[arg-type]
                issue_age_column=issue_age_column,
                maximum_age=until_value if isinstance(until_value, int) else None,
                until_value_column=(
                    until_value if isinstance(until_value, str) else None
                ),
                until_value_expr=(
                    until_value if isinstance(until_value, pl.Expr) else None
                ),
            )

        # Per-policy (jagged) path: each policy projects only its own horizon.
        if use_per_policy:
            if until not in ("term_months", "term_years"):
                msg = (
                    "per_policy=True currently supports until in "
                    "{'term_months', 'term_years', 'maximum_age'}, a maximum age "
                    "at a monthly, quarterly, semi-annual or annual frequency; "
                    f"got until={until!r} at {frequency!r}. Use the uniform path "
                    "(per_policy=False) for other horizons."
                )
                raise ValueError(msg)
            if not isinstance(until_value, str):
                msg = (
                    "per_policy=True requires until_value to be a column name "
                    "(str) giving each policy's horizon; got "
                    f"{type(until_value).__name__}."
                )
                raise ValueError(msg)
            return Schedule.from_per_policy_grid(
                start_date=valuation_date,
                frequency=sched_freq,  # type: ignore[arg-type]
                until_kind=until,
                until_value_column=until_value,
            )

        # Uniform path (per_policy=False, or auto fell back). A per-policy
        # until_value (column / expr) is collapsed to the portfolio max here —
        # every policy carries the longest-lived policy's horizon. Only this
        # path reads a count across the rows: a per-policy grid states none
        # (spec 11.1.37), each policy running to its own horizon.
        n_per = self._compute_n_periods(
            valuation_date=valuation_date,
            until=until,
            until_value=until_value,
            issue_age_column=issue_age_column,
            sched_freq=sched_freq,
        )
        return Schedule.from_calendar_grid(
            start_date=valuation_date,
            n_periods=n_per,
            frequency=sched_freq,  # type: ignore[arg-type]
        )

    def _compute_n_periods(
        self,
        *,
        valuation_date: dt.date,
        until: str,
        until_value: Any,  # noqa: ANN401
        issue_age_column: str,
        sched_freq: str,
    ) -> int:
        """Compute a shared grid's n_periods from an `until` specification.

        Per-policy ``until_value`` (column name or ``pl.Expr``) is resolved
        as a max across the frame; per-policy boundaries are expressed via
        ``af.projection.is_in_force(...)``. A per-policy grid never reaches
        here: it states no count of its own.
        """
        if until == "term_months":
            months = self._resolve_int_until_value(until_value)
            return _months_to_periods(months, sched_freq)
        if until == "term_years":
            years = self._resolve_int_until_value(until_value)
            return years * _PERIODS_PER_YEAR[sched_freq]
        if until == "fixed_date":
            return self._n_periods_for_fixed_date(
                valuation_date=valuation_date,
                until_value=until_value,
                sched_freq=sched_freq,
            )
        if until == "maximum_age":
            return self._n_periods_for_maximum_age(
                until_value=until_value,
                issue_age_column=issue_age_column,
                sched_freq=sched_freq,
            )
        valid = [
            "maximum_age",
            "term_years",
            "term_months",
            "fixed_date",
        ]
        msg = f"invalid until={until!r}; expected one of {valid}"
        raise ValueError(msg)

    def _resolve_int_until_value(
        self,
        until_value: Any,  # noqa: ANN401
    ) -> int:
        """Resolve ``until_value`` to a single integer.

        - ``int`` is used directly.
        - ``str`` is interpreted as a column name; the max is taken.
        - ``pl.Expr`` is evaluated; the max is taken.

        The max is over the frame's rows, which in a batched run are the
        batch's: a shared grid read from the rows is refused in a batched run
        before this is reached. A frame with no rows -- a filter that selects no
        policy, in the whole book or in one batch -- has no horizon to read
        and projects nothing, so its axis is zero periods long.
        """
        if isinstance(until_value, int):
            return until_value
        expr = pl.col(until_value) if isinstance(until_value, str) else until_value
        return self._largest_over_the_rows(expr, until_value)

    def _largest_over_the_rows(
        self,
        expr: pl.Expr,
        written: Any,  # noqa: ANN401 -- the until_value as the model wrote it
    ) -> int:
        """Return an expression's largest value over the frame's rows, or 0 over none.

        Raises:
            ValueError: If one shared grid is sized from rows that are null in
                every one of them, so no policy states the grid's length.

        """
        largest, rows = (
            self._plan().select(expr.max(), pl.len().alias("_rows")).collect().row(0)
        )
        if largest is not None:
            return int(largest)
        if rows == 0:
            return 0
        named = written if isinstance(written, str) else str(written)
        msg = (
            f"projection.set() lays one shared grid as long as the longest "
            f"horizon in {named!r}, and it is null in every one of the frame's "
            f"{rows} rows, so no policy states how long the grid runs. Fill the "
            "horizon for each policy, or filter out the rows that carry none "
            "before projection.set()."
        )
        raise ValueError(msg)

    @staticmethod
    def _n_periods_for_fixed_date(
        *,
        valuation_date: dt.date,
        until_value: Any,  # noqa: ANN401
        sched_freq: str,
    ) -> int:
        if not isinstance(until_value, dt.date):
            msg = "until_value must be datetime.date for until='fixed_date'"
            raise TypeError(msg)
        months = (until_value.year - valuation_date.year) * 12 + (
            until_value.month - valuation_date.month
        )
        return _months_to_periods(months, sched_freq)

    def _n_periods_for_maximum_age(
        self,
        *,
        until_value: Any,  # noqa: ANN401
        issue_age_column: str,
        sched_freq: str,
    ) -> int:
        # The longest of the policies' axes. A whole-number age reads the
        # youngest life, whose axis is longest: the age less the smallest
        # issue age, truncated. Using max(issue_age) would give the fewest
        # months and truncate every younger cohort. A column or an
        # expression takes max(target - issue) over the policies. A frame
        # with no rows projects nothing: zero periods.
        if isinstance(until_value, int):
            expr = pl.lit(until_value) - pl.col(issue_age_column).min().cast(pl.Int64)
            written: Any = issue_age_column
        else:
            target = (
                pl.col(until_value) if isinstance(until_value, str) else until_value
            )
            expr = target - pl.col(issue_age_column)
            written = until_value
        years = self._largest_over_the_rows(expr, written)
        return years * _PERIODS_PER_YEAR[sched_freq]

    def _reject_reserved_column_collisions(self, *reserved: str) -> None:
        """Raise if the frame already carries a column projection.set() stamps.

        Overwriting silently is the failure class this release exists to
        remove — and a calendar ``year`` or a source ``month`` on the model
        points is exactly the sort of column a user would not expect to lose.

        This guards the *user's* columns, not ours. Re-projecting a frame that
        already has an in-session projection is supported, and there an index
        the previous axis stamped is ours to replace -- but only that one
        (:meth:`_own_stamps`): a model point's ``month`` carried through a
        weekly axis, or a ``step`` through a calendar one, is still the
        user's, and a second ``set()`` that would mint the name refuses as
        the first would have. A frame reconstructed from a previous run's
        output (parquet reload, ``ActuarialFrame(af.collect())``) carries
        ``month`` without a live projection — we cannot tell that apart from
        a user's calendar column, so the error names both exits rather than
        guessing.
        """
        frame_df = self._frame._df  # noqa: SLF001
        if frame_df is None:
            return

        names = frame_df.collect_schema().names()
        own = self._own_stamps()
        for column in reserved:
            if column not in names or column in own:
                continue
            meaning, example = _RESERVED_MEANING[column]
            msg = (
                f"projection.set() materialises {column!r} ({meaning}), but the "
                f"frame already has a {column!r} column.\n"
                f"  • if it is your own (e.g. {example}), rename it: "
                f'mp.rename({{"{column}": "source_{column}"}})\n'
                f"  • if it came from a previous projection run's output, drop "
                f'it: mp.drop("{column}")'
            )
            raise ValueError(msg)

    def _own_stamps(self) -> frozenset[str]:
        """Return the columns this frame holds as its projection stamped them.

        The frame's calculation log is how it knows. ``projection.set()``
        records every column it stamps with origin ``"projection"``; a column
        whose latest entry in the log is still that record is the axis's own
        stamp, untouched since. A column the model wrote over afterwards
        (an assignment, a join, a rename onto the name, a write past the
        doors) has a later entry and is the model's; a model-point column
        that merely shares a stamp's name never had a projection record.
        Only columns the frame still holds count.
        """
        frame = self._frame
        plan = frame._df  # noqa: SLF001
        if plan is None or frame._projection is None:  # noqa: SLF001
            return frozenset()
        held = set(plan.collect_schema().names())
        return frozenset(
            column
            for column, entry in frame._live_entries().items()  # noqa: SLF001
            if column in held
            and isinstance(entry, CalculationRecord)
            and entry.origin == "projection"
        )

    def _stamp_eager_columns(
        self,
        schedule: Schedule,
        attrs: tuple[tuple[str, AttrValue], ...] = (),
    ) -> ActuarialFrame:
        """Stamp projection dates, num_proj_months, and the ``month`` index.

        ``month`` is the period index shipped examples already assume exists
        (#36): **elapsed whole months from the projection start**, one value
        per boundary (length ``n_periods + 1``, aligned with ``t_years()``).

        It is stamped only where the name is honest:

        - on a fixed-step axis, only where a step is whole months
          (``steps_per_year`` of 1, 2, 3, 4, 6 or 12), as ``k * 12 / n``; that
          axis stamps ``step`` and ``num_proj_months`` and no dates
          (:meth:`_fixed_step_columns`).
        - month-aligned frequencies only (1M/3M/6M/1Y). At 1W/1D a
          calendar-month difference over-counts by up to a month (Jan 31 +
          one day reads as month 1), so no index is fabricated there.
        - not on ``from_inception`` schedules, whose axis starts at each
          policy's own inception — elapsed months there are policy DURATION,
          not projection time, the exact conflation Gotcha #7 warns about
          (``scenarios/_aggregated.py`` already documents that axis as
          duration for the same reason).

        There is deliberately no ``proj_year``: a projection-year label
        depends on the model's timing convention. With end-of-period rows
        "year 1" is ``ceil(month / 12)``; with beginning-of-period rows it is
        ``month // 12 + 1``; the two disagree at every anniversary boundary.
        The framework cannot know which the model means, so the model states
        its own one-line formula (see AGENTS.md, Timing Conventions).
        """
        if schedule._kind == FIXED_STEP:  # noqa: SLF001
            eager_columns = self._fixed_step_columns(schedule)
            return self._record_stamp(schedule, eager_columns, attrs)

        stamp_month = (
            schedule.frequency in _MONTHS_PER_PERIOD
            and schedule._kind != "from_inception"  # noqa: SLF001
        )
        if stamp_month:
            # Only a schedule that will stamp `month` can collide with it —
            # weekly/daily/from_inception axes leave the user's column alone.
            self._reject_reserved_column_collisions(_MONTH_COLUMN)

        if schedule._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = schedule.period_dates()  # list[date], length n_periods+1
            start_date = boundaries[0]
            end_date = boundaries[-1]
            eager_columns: dict[str, pl.Expr] = {
                "projection_start_date": pl.lit(start_date),
                "projection_end_date": pl.lit(end_date),
                "num_proj_months": pl.lit(len(boundaries), dtype=pl.Int64),
            }
            if stamp_month:
                # Boundaries on a month-aligned grid share one anchor
                # convention, so the calendar-month difference is exact.
                months = [
                    (d.year - start_date.year) * 12 + (d.month - start_date.month)
                    for d in boundaries
                ]
                eager_columns[_MONTH_COLUMN] = pl.lit(months, dtype=pl.List(pl.Int64))
        else:
            # from_inception / per_policy_grid: per-policy boundaries (jagged).
            period_dates_e = (
                schedule.per_policy_period_dates_expr()
                if schedule._kind == "per_policy_grid"  # noqa: SLF001
                else schedule.period_dates_expr()
            )
            eager_columns = {
                "projection_start_date": period_dates_e.list.first(),
                "projection_end_date": period_dates_e.list.last(),
                # Signed Int64, the width every integer the frame stamps is
                # carried in: a bare list.len() is UInt and
                # `num_proj_months - k` would underflow.
                # fill_null(0) so a null until_value stamps 0 (matching the
                # clamped per_policy_period_count_expr) rather than null — else
                # the int_ranges(0, num_proj_months - 1) feeder builds a null
                # list and the rollforward kernel rejects it.
                "num_proj_months": (
                    period_dates_e.list.len().fill_null(0).cast(pl.Int64)
                ),
            }
            if stamp_month:
                # Elapsed whole months from each policy's own first boundary —
                # jagged with the timeline, not padded to the longest-lived
                # policy. Same null guard as num_proj_months: a null horizon
                # stamps an empty index, not a null one.
                eager_columns[_MONTH_COLUMN] = _elapsed_months_expr(
                    period_dates_e
                ).fill_null(pl.lit([], dtype=pl.List(pl.Int64)))

        return self._record_stamp(schedule, eager_columns, attrs)

    def _fixed_step_columns(self, schedule: Schedule) -> dict[str, pl.Expr]:
        """Return the columns a fixed-step axis stamps: no dates, a step index.

        ``num_proj_months`` is the boundary count ``T + 1``, as on every axis
        (the name is history; the value is a count of boundaries). ``step``
        is ``0..T``, the workbook's step column. ``month`` is stamped only
        where one step is a whole number of calendar months, ``k * 12 / n``
        for ``steps_per_year`` of 1, 2, 3, 4, 6 or 12; a step of 0.1 years is
        1.2 months, and an index of months there would be invented.
        """
        months_per_step = fixed_step_months_per_step(schedule)
        reserved = (
            (_STEP_COLUMN,)
            if months_per_step is None
            else (
                _STEP_COLUMN,
                _MONTH_COLUMN,
            )
        )
        self._reject_reserved_column_collisions(*reserved)
        boundaries = range(schedule._shared_period_count() + 1)  # noqa: SLF001
        columns: dict[str, pl.Expr] = {
            "num_proj_months": pl.lit(len(boundaries), dtype=pl.Int64),
            _STEP_COLUMN: pl.lit(list(boundaries), dtype=pl.List(pl.Int64)),
        }
        if months_per_step is not None:
            columns[_MONTH_COLUMN] = pl.lit(
                [k * months_per_step for k in boundaries], dtype=pl.List(pl.Int64)
            )
        return columns

    def _record_stamp(
        self,
        schedule: Schedule,
        eager_columns: dict[str, pl.Expr],
        attrs: tuple[tuple[str, AttrValue], ...],
    ) -> ActuarialFrame:
        """Stamp the axis columns onto this frame and record the declaration."""
        # A re-projection replaces the axis, so a column the previous axis
        # stamped that this one does not mint goes with it: weekly after
        # monthly mints no `month`, a calendar axis no `step`, a fixed step
        # no dates. Left behind, it is a per-period column of the old axis's
        # length beside the new one's -- a wrong number waiting for a read.
        # Only the frame's own untouched stamps are dropped, never a column
        # the model holds under the same name (see `_own_stamps`).
        own = self._own_stamps()
        stale = [
            column
            for column in self._plan().collect_schema().names()
            if column in own and column not in eager_columns
        ]
        if stale:
            self._frame.drop(*stale)
        # The stamp is one operation the sealed window keeps, so a
        # calculation named behind the timeline can be confirmed on the
        # plan it went on to hold.
        stamp = with_columns_operation("projection", **eager_columns)
        stamped_df = stamp.applied_to(self._plan())

        # The timeline is one step further on in the SAME model, so it is
        # stamped ON that model's frame -- through `_set_plan`, the way
        # rename/join/filter already work -- rather than onto a freshly
        # constructed one. A new frame would start with an empty calculation
        # log, restarted ordinals, and every phase-1 column re-labelled an
        # input: the model's whole history up to the projection axis, lost at
        # the line that declares the axis.
        af = self._frame
        af._set_plan(stamped_df)  # noqa: SLF001
        af._projection = schedule  # noqa: SLF001
        af._reset_attribution_window(stamp)  # noqa: SLF001
        af._schema = stamped_df.collect_schema()  # noqa: SLF001
        # Re-projecting an already-projected frame overwrites these columns
        # rather than adding them, so only the genuinely new names join the
        # column order -- but every stamped name is recorded either way, and
        # a second projection reads as that column's second assignment.
        af._column_order.extend(  # noqa: SLF001
            name
            for name in eager_columns
            if name not in af._column_order  # noqa: SLF001
        )
        af._refresh_attr_columns_set()  # noqa: SLF001
        # One record per stamped column, all sharing one operation id: the
        # dates, the period count and the `month` index all come from one
        # `projection.set(...)` call with one configuration, and none of them
        # is a formula the model wrote. The node names the call and carries
        # that configuration; the expression is the plain post-stamp
        # reference to the column, which is the only expression true of it
        # afterwards. `Call` is built directly rather than through
        # `emit.call_node` because "projection_set" has no registered
        # lowering and must never reach `lower_polars` -- these records sit
        # behind the attribution cursor precisely so nothing replays them.
        #
        # Its arguments are the columns the stamp genuinely read, taken
        # from the very expressions that produced the stamped values: a
        # shared calendar grid reads nothing (it is built from the
        # configuration alone), while a per-policy axis reads each policy's
        # own inception or horizon column. The post-stamp reference held as
        # the record's expression cannot answer that -- it names the
        # stamped column itself -- so the answer comes from `eager_columns`
        # before the plan swap erases the distinction.
        node = Call(
            "projection_set",
            args=emit.column_args(*eager_columns.values()),
            attrs=attrs,
        )
        af._record_minted_columns(  # noqa: SLF001
            {name: (node, pl.col(name)) for name in eager_columns},
            origin="projection",
        )
        return af

    def rollforward(  # noqa: PLR0913 — mirrors RollforwardBuilder; a config dict would lose call-site readability
        self,
        *,
        states: dict[str, ExprLike],
        points: Iterable[str] | None = None,
        track_increments: bool = False,
        lapse_when_all_non_positive: Iterable[str] = (),
        contract_boundary: ExprLike | None = None,
        batch_axes: tuple[str, ...] = ("policy",),
        schedule: None = None,
    ) -> RollforwardBuilder:
        """Construct a :class:`RollforwardBuilder` that reads schedule from this frame.

        ``schedule=`` is no longer accepted on this method — call
        ``af.projection.set(...)`` first. Every other keyword forwards to
        :class:`RollforwardBuilder` unchanged.
        """
        if schedule is not None:
            msg = (
                "schedule= is no longer accepted on rollforward(). "
                "Call af.projection.set(...) before rollforward(); the schedule "
                "is read from the frame."
            )
            raise TypeError(msg)
        projection = self._projection()
        if projection is None:
            msg = (
                "This frame has no projection. "
                "Call af.projection.set(...) before rollforward()."
            )
            raise ValueError(msg)
        # per_policy_grid (jagged) is supported: the rollforward kernel derives
        # each policy's period count from its own input-list offsets, so a
        # variable-length timeline projects each policy over only its own
        # horizon. ``n_periods`` from the schedule canonical form is passed to
        # the kernel as a portfolio-max capacity hint, not a per-row invariant.
        builder = RollforwardBuilder(
            states=states,
            schedule=projection,
            points=points,
            track_increments=track_increments,
            lapse_when_all_non_positive=lapse_when_all_non_positive,
            contract_boundary=contract_boundary,
            batch_axes=batch_axes,
        )
        # What the compiled rollforward's reads are bound to, so a method
        # chained on ``expr_for(...)`` means what it means on the column.
        builder._frame_ref = weakref.ref(self._frame)  # noqa: SLF001
        return builder

    def _require_projection(self) -> Schedule:
        """Return the frame's Schedule or raise if absent."""
        proj = self._projection()
        if proj is None:
            msg = "This frame has no projection. Call af.projection.set(...) first."
            raise ValueError(msg)
        return proj

    def _projection(self) -> Schedule | None:
        """Return the Schedule the frame keeps, or None before projection.set().

        Read with getattr: the frame's stub does not declare ``_projection``,
        so plain attribute access would resolve, for a type checker, through
        the frame's ``__getattr__`` to a column.
        """
        projection = getattr(self._frame, "_projection", None)
        return projection if isinstance(projection, Schedule) else None

    def _plan(self) -> pl.LazyFrame:
        """Return the frame's query plan, refusing a frame that has none."""
        plan = self._frame._df  # noqa: SLF001
        if plan is None:
            msg = "Cannot set a projection on an uninitialized ActuarialFrame."
            raise ValueError(msg)
        return plan

    def _emit(
        self,
        name: str,
        attrs: tuple[tuple[str, Any], ...] = (),
    ) -> ProxyAwareExpr:
        """Emit a timeline ``Call`` against this frame's own projection schedule.

        These methods hand frame-independent expressions to users, and a
        bare ``pl.Expr`` raises on a proxy operand before the proxy's
        reflected method can run (gh#67) — so results worked in one
        operand order and not the other. ``ProxyAwareExpr`` fixes the
        operand-order trap while staying a real ``pl.Expr``, so raw
        Polars interop (``pl.concat_list([...])``, the tutorial idiom)
        is untouched. It now carries the node as well, so an operand that
        meets one of these sees a timeline expression rather than an
        opaque one. Same treatment as ``Table.lookup`` and the
        ``Schedule.*_expr`` family -- and bound to this frame, because these
        are read *from* it: a method chained straight on
        (``year_fractions().cum_sum()``) means what it means on the column
        the timeline would be assigned to.

        The node also declares the columns the timeline genuinely reads --
        a per-policy axis is a function of each policy's own inception or
        horizon column -- taken from the expression this call lowers to
        (see ``emit.column_args``), so the declaration cannot drift from
        what actually runs.
        """
        sched = self._require_projection()
        call_attrs = (("schedule", register_schedule(sched)), *attrs)
        ctx = context_for(self._frame)
        expr = lower_polars(emit.call_node(name, (), call_attrs), ctx)
        node = emit.call_node(name, emit.column_args(expr), call_attrs)
        return ProxyAwareExpr.wrap(expr, node=node, parent=self._frame)

    def _reject_end_date_on_jagged(self, end_date_column: str | None) -> None:
        """Refuse a separate end date where the timeline cannot honour one.

        On a per-policy (jagged) timeline each policy's own horizon already
        bounds its projection, so a second boundary is both redundant and not
        honoured — a silent no-op is the worst of the three possible answers.
        On a fixed-step axis there are no dates to compare an end date with.
        """
        refuse_an_end_date(self._require_projection(), end_date_column)

    def period_dates(self) -> ProxyAwareExpr:
        """Return per-row List<Date>.

        Uniform schedules give length ``n_periods+1`` for every row;
        ``per_policy_grid`` gives each policy its own (variable) length. A
        fixed-step axis has no calendar and refuses, naming the calendar form.
        """
        if self._require_projection()._kind == FIXED_STEP:  # noqa: SLF001
            refuse_dates_on_a_fixed_step("period_dates()")
        return self._emit("projection_frame.period_dates")

    def year_fractions(self) -> ProxyAwareExpr:
        """Return per-row List<Float64> of length n_periods (per-period dt[t]).

        The year fraction of each period: how much of a year period ``t``
        spans, so that an annual rate applied over it is ``rate * dt[t]``.

        !!! note "When to use"
            * **Interest for the period:** Credit or accrue an annual rate
              over periods of unequal length -- a calendar month, a quarter,
              a short first period.
            * **Day-count conventions:** Read the period lengths a
              ``Schedule``'s day count gives (``OneTwelfth``,
              ``Actual365Fixed``, ``ActualActualISDA`` ...) rather than
              assuming ``1 / 12``.

        Measured on the schedule's day count. On a weekly or daily axis that
        must be one that counts days: ``OneTwelfth``, the default, counts
        whole months and refuses there. Project with
        ``af.projection.set(schedule=Schedule.from_calendar_grid(...,
        day_count=Actual365Fixed()))``.

        On a fixed-step axis every period is one step: ``step_years``, or
        ``1 / steps_per_year``. Summing these does not give ``t_years()`` in
        the last bits -- ``t_years()`` there is one product per boundary, and
        a running sum of ``0.1`` differs from ``k * 0.1`` at almost every
        boundary -- so read time from ``t_years()``, not from
        ``year_fractions().cum_sum()``.
        """
        return self._emit("projection_frame.year_fractions")

    def t_years(self) -> ProxyAwareExpr:
        """Return per-row List<Float64> of elapsed time in years from 0.

        Length is ``n_periods + 1``, one value per boundary. Feeds
        ``Curve.discount_factor(t)`` directly. It is defined two ways, by the
        kind of axis:

        - **On a calendar axis**, the running sum of ``year_fractions()``,
          measured on the schedule's day count (so a weekly or daily axis
          needs one that counts days). A monthly grid's ``t_years`` therefore
          differs from ``k / 12`` in the last bits at most boundaries (947 of
          975 from 31 January 2025): a model reconciling to a sheet written
          ``A/12`` should project on ``steps_per_year=12``. The calendar
          definition stays a running sum in 1.0.
        - **On a fixed-step axis**, ``k * step_years`` or
          ``k / steps_per_year`` -- one rounding per boundary, never a running
          sum -- so ``af.issue_age + af.projection.t_years()`` is a workbook's
          ``x + A*h`` or ``x + A/12`` bit for bit, in the spelling the model
          chose.
        """
        return self._emit("projection_frame.t_years")

    def anniversary_mask(self) -> ProxyAwareExpr:
        """Return per-row List<Boolean> of length n_periods marking anniversaries.

        On a fixed-step axis written as ``steps_per_year=n`` an anniversary is
        every ``n``-th step. Written as ``step_years``, it refuses: whether a
        whole number of steps makes a year is a guess, and
        ``steps_per_year`` is how a model says it does.
        """
        schedule = self._require_projection()
        if schedule._kind == FIXED_STEP:  # noqa: SLF001
            schedule._anniversary_period_count()  # noqa: SLF001 -- refuses step_years
        return self._emit("projection_frame.anniversary_mask")

    def is_in_force(self, *, end_date_column: str | None = None) -> ProxyAwareExpr:
        """Return per-row List<Boolean> of length n_periods — boundary mask.

        Pass ``end_date_column`` for from_inception schedules where each
        policy has its own end date. Without it, the mask is uniform True
        for all periods. A fixed-step axis has no dates and refuses
        ``end_date_column``.
        """
        self._reject_end_date_on_jagged(end_date_column)
        return self._emit(
            "schedule.is_in_force", (("end_date_column", end_date_column),)
        )

    def contract_boundary(
        self, *, end_date_column: str | None = None
    ) -> ProxyAwareExpr:
        """Return per-row List<Boolean> of length n_periods — kernel termination mask.

        True at period t means the contract has terminated by period t. Pass to
        ``af.projection.rollforward(..., contract_boundary=...)`` to bound the
        projection at each policy's end date.

        This is the **negation** of :meth:`is_in_force` — the kernel uses
        boundary semantics (True = terminate); ``is_in_force()`` is natural
        for other uses (True = active).
        """
        self._reject_end_date_on_jagged(end_date_column)
        return self._emit(
            "schedule.contract_boundary", (("end_date_column", end_date_column),)
        )

    def canonical_form(self) -> dict[str, Any]:
        """Return the structural recipe — same shape as Schedule.canonical_form()."""
        sched = self._require_projection()
        return sched.canonical_form()

    def source_sha(self) -> str:
        """Return sha256:<hex> over the canonical form bytes (audit identifier)."""
        sched = self._require_projection()
        return sched.source_sha()


# What the API reference documents from this module.
__all__ = ["ProjectionFrameAccessor"]
