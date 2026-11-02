# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule typed primitive — period boundaries + day-count + calendar.

Named constructors:
  - ``from_calendar_grid`` — shared grid for all policies; useful for cohort
    aggregation and SII reporting. Mid-month starts normalise to month-end by
    default to match US/UK/EU production practice.
  - ``from_inception`` — per-policy grid anchored on a column of inception
    dates. Anniversary semantics intrinsic.
  - ``from_per_policy_grid`` — a shared start and each policy's own horizon.
  - ``fixed_step`` — ``n_periods`` steps of a fixed number of years, with no
    calendar under them: a teaching workbook, a numerical solution of
    Thiele's or Kolmogorov's equations.

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

When integrating with ``ActuarialFrame.projection.set(until_value=N)``, which
produces ``N + 1`` timeline steps, pass ``n_periods=N`` to
``Schedule.from_inception`` so that ``period_dates_expr`` returns ``N + 1``
boundaries that align with the timeline indices.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from gaspatchio._authoring import emit
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.lowering.artefacts import register_schedule
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.schedule._business_day import BusinessDayConvention
from gaspatchio.schedule._calendar import Calendar, NullCalendar
from gaspatchio.schedule._data import (
    _PER_POLICY_END_DATE_MSG,
    _SUPPORTED_FREQUENCIES,
    _UNTIL_KIND_TO_OFFSET_UNIT,
    FIXED_STEP,
    MAXIMUM_AGE,
    Anchor,
    Frequency,
    ScheduleData,
    _default_convention,
    _normalise_anchor,
    refuse_dates_on_a_fixed_step,
)
from gaspatchio.schedule._day_count import DayCount, OneTwelfth

if TYPE_CHECKING:
    from datetime import date

    import polars as pl


@dataclass(frozen=True)
class Schedule(ScheduleData):
    """Typed schedule — periods, day-count, calendar, BD convention.

    Construct via :meth:`from_calendar_grid` (shared grid),
    :meth:`from_inception` (per-policy column-anchored),
    :meth:`from_per_policy_grid` (shared start, per-policy horizon) or
    :meth:`fixed_step` (fixed steps in years, no calendar). Direct
    construction is intentionally awkward — use the classmethods.
    """

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
        portfolio-wide maximum. The grid states no ``n_periods``: each row's
        length comes from its column, so no other policy's horizon is part of
        the recipe or of any fingerprint that reads it. The longest horizon in
        a run is a fact of that run (``run_metadata.n_periods``).

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
            n_periods=None,
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

    @classmethod
    def _to_maximum_age(  # noqa: PLR0913 -- the shared start, the cadence, and the three forms of the age
        cls,
        *,
        start_date: date,
        frequency: Frequency,
        issue_age_column: str,
        maximum_age: int | None = None,
        until_value_column: str | None = None,
        until_value_expr: pl.Expr | None = None,
    ) -> Schedule:
        """Per-policy *jagged* grid running each policy to a maximum age.

        ``projection.set(until="maximum_age", ...)`` builds this. Every policy
        shares ``start_date`` and runs ``until_value - issue_age`` whole years
        -- the age given as a whole number, a column or an expression, exactly
        one of the three -- so a 70-year-old projected to age 100 carries 30
        years whichever other policies share its run. Like
        :meth:`from_per_policy_grid`, it states no ``n_periods``.
        """
        given = [
            value
            for value in (maximum_age, until_value_column, until_value_expr)
            if value is not None
        ]
        if len(given) != 1:  # pragma: no cover - projection.set passes one
            msg = "a maximum-age grid takes the age in exactly one form"
            raise ValueError(msg)
        return cls(
            n_periods=None,
            frequency=frequency,
            calendar=NullCalendar(),
            convention=_default_convention(NullCalendar()),
            day_count=OneTwelfth(),
            anchor="exact_date",  # placeholder — start_date IS the anchor
            start_date=start_date,
            inception_column=None,
            _kind="per_policy_grid",
            until_kind=MAXIMUM_AGE,
            until_value_column=until_value_column,
            issue_age_column=issue_age_column,
            maximum_age=maximum_age,
            until_value_expr=until_value_expr,
        )

    @classmethod
    def fixed_step(
        cls,
        *,
        n_periods: int,
        step_years: float | None = None,
        steps_per_year: int | None = None,
    ) -> Schedule:
        """Construct an axis of ``n_periods`` fixed steps in years, with no calendar.

        For a model whose time axis is *k steps of h years* rather than
        calendar months: a teaching workbook, a numerical solution of
        Thiele's or Kolmogorov's equations, a continuous-time product
        discretised for valuation. Give the step one of two ways, the way
        the workbook writes its time column:

        - ``step_years=0.1`` -- each step is 0.1 years, and the time at
          boundary ``k`` is ``k * 0.1`` (a sheet's ``x + A*h``);
        - ``steps_per_year=12`` -- twelve steps a year, and the time at
          boundary ``k`` is ``k / 12`` (a sheet's ``x + A/12``).

        The two differ in the last bits at a third of the boundaries, which
        is why the spelling is recorded rather than normalised. There are no
        dates, no day count and no business days on this axis; hand it to
        ``af.projection.set(schedule=...)``, or use the same arguments there
        directly.

        Args:
            n_periods: The number of steps ``T``; the axis has ``T + 1``
                boundaries, ``k = 0..T``.
            step_years: The length of one step in years, a finite positive
                number. Pass this or ``steps_per_year``, not both.
            steps_per_year: The whole number of steps one year makes.

        Returns:
            A ``fixed_step`` schedule.

        Raises:
            ValueError: If neither or both of ``step_years`` and
                ``steps_per_year`` are given, or a value is out of range.

        Example::

            >>> from gaspatchio import Schedule
            >>> Schedule.fixed_step(n_periods=3, step_years=0.1).canonical_form()
            {'kind': 'fixed_step', 'n_periods': 3, 'step_years': 0.1}
            >>> Schedule.fixed_step(n_periods=24, steps_per_year=12).year_fractions()[0]
            0.08333333333333333

        """
        _check_fixed_step(
            n_periods=n_periods, step_years=step_years, steps_per_year=steps_per_year
        )
        return cls(
            n_periods=n_periods,
            frequency=None,
            # Placeholders the recipe never states: a step axis has no
            # calendar, no business days and no day count.
            calendar=NullCalendar(),
            convention=BusinessDayConvention.UNADJUSTED,
            day_count=OneTwelfth(),
            anchor="exact_date",
            start_date=None,
            inception_column=None,
            _kind="fixed_step",
            step_years=None if step_years is None else float(step_years),
            steps_per_year=steps_per_year,
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
        return self._emit("schedule.per_policy_period_dates")

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
        return self._emit("schedule.per_policy_period_count")

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
        if self._kind == FIXED_STEP:
            refuse_dates_on_a_fixed_step("period_dates_expr()")
        if self._kind != "from_inception":
            msg = (
                "period_dates_expr() is only valid for from_inception schedules;"
                " use period_dates() for from_calendar_grid, "
                "per_policy_period_dates_expr() for per_policy_grid (jagged), or "
                "the frame accessor af.projection.period_dates() for any kind."
            )
            raise ValueError(msg)
        return self._emit("schedule.period_dates")

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
        _refuse_a_fixed_step_expr(self, "year_fractions")
        if self._kind not in ("from_inception", "per_policy_grid"):
            msg = (
                "year_fractions_expr() is only valid for from_inception or"
                " per_policy_grid schedules; use year_fractions() for"
                " from_calendar_grid"
            )
            raise ValueError(msg)
        return self._emit("schedule.year_fractions")

    def _emit(
        self,
        name: str,
        attrs: tuple[tuple[str, Any], ...] = (),
    ) -> pl.Expr:
        """Emit a schedule ``Call`` and hand back the expression it lowers to.

        The node carries this schedule's own ``source_sha`` rather than a
        transcription of its fields; the registered lowering in
        ``frame/lowering/rules/schedule.py`` resolves the schedule back and
        builds the expression.

        The result is a ``ProxyAwareExpr`` because ``pl.Expr`` raises on a
        ``ColumnProxy`` operand instead of returning ``NotImplemented``
        (gh#67), so a schedule expression combined with an ``af`` column
        worked in one operand order and not the other -- the same contract
        as ``Table.lookup``. It carries the node too, so an operand that
        meets it sees a schedule expression rather than an opaque one. The
        wrapping happens here rather than in a decorator on the ``*_expr``
        methods, because the node has to travel with the expression it
        lowered to and a decorator that only saw the finished expression
        could not carry it.

        A timeline anchored per policy genuinely reads columns off the
        frame -- each policy's inception date, its own horizon, its
        termination date -- so the node declares those as arguments
        alongside the configuration in ``attrs``. They are read back off
        the expression this call lowers to (see ``emit.column_args``), so
        what the node says it reads cannot drift from what runs: a
        structural mask that depends only on the cadence declares nothing,
        and a boundary test that compares two date columns declares both.
        """
        call_attrs = (("schedule", register_schedule(self)), *attrs)
        expr = lower_polars(emit.call_node(name, (), call_attrs))
        node = emit.call_node(name, emit.column_args(expr), call_attrs)
        return ProxyAwareExpr.wrap(expr, node=node)

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
        _refuse_a_fixed_step_expr(self, "anniversary_mask")
        if self._kind not in ("from_inception", "per_policy_grid"):
            msg = (
                "anniversary_mask_expr() is only valid for from_inception schedules;"
                " use anniversary_mask() for from_calendar_grid"
            )
            raise ValueError(msg)
        return self._emit("schedule.anniversary_mask")

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
        refuse_an_end_date(self, end_date_column)
        return self._emit(
            "schedule.is_in_force", (("end_date_column", end_date_column),)
        )

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
        refuse_an_end_date(self, end_date_column)
        return self._emit(
            "schedule.contract_boundary", (("end_date_column", end_date_column),)
        )


def _check_fixed_step(
    *, n_periods: int, step_years: float | None, steps_per_year: int | None
) -> None:
    """Refuse a fixed step that is not one whole, positive way of writing a step."""
    if (step_years is None) == (steps_per_year is None):
        given = "both" if step_years is not None else "neither"
        msg = (
            f"A fixed-step axis takes its step one way, and was given {given}: "
            "step_years=0.1 (each step 0.1 years, so the time at boundary k is "
            "k * 0.1) or steps_per_year=12 (twelve steps a year, so the time at "
            "boundary k is k / 12). Write the one the workbook's time column "
            "uses -- x + A*h is step_years, x + A/12 is steps_per_year."
        )
        raise ValueError(msg)
    if not isinstance(n_periods, int) or isinstance(n_periods, bool) or n_periods < 0:
        msg = (
            f"A fixed-step axis needs a whole number of steps, got n_periods="
            f"{n_periods!r}: n_periods=T lays T steps and T + 1 boundaries."
        )
        raise ValueError(msg)
    if steps_per_year is not None and (
        not isinstance(steps_per_year, int)
        or isinstance(steps_per_year, bool)
        or steps_per_year < 1
    ):
        msg = (
            f"steps_per_year={steps_per_year!r}: the steps one year makes is a "
            "whole number of at least one. For a step that is not a whole "
            "fraction of a year, write it in years: step_years=0.1."
        )
        raise ValueError(msg)
    if step_years is not None and (
        not isinstance(step_years, (int, float))
        or isinstance(step_years, bool)
        or not math.isfinite(step_years)
        or step_years <= 0
    ):
        msg = (
            f"step_years={step_years!r}: a step is a finite, positive number of "
            "years, such as step_years=0.1."
        )
        raise ValueError(msg)


def _refuse_a_fixed_step_expr(schedule: ScheduleData, reading: str) -> None:
    """Send a fixed-step schedule's per-row readings to the frame accessor."""
    if schedule._kind != FIXED_STEP:  # noqa: SLF001
        return
    msg = (
        f"{reading}_expr() is the per-policy reading of a calendar schedule, "
        "and a fixed-step schedule is one shared axis with no calendar under "
        "it. Project with it -- af.projection.set(schedule=...) -- and read "
        f"af.projection.{reading}()."
    )
    raise ValueError(msg)


def refuse_an_end_date(schedule: ScheduleData, end_date_column: str | None) -> None:
    """Refuse an end-date boundary on an axis that cannot compare one.

    A jagged per-policy grid already stops each policy at its own horizon,
    and a fixed-step axis has no dates for an end date to be compared with.

    Raises:
        ValueError: If ``end_date_column`` is given on either.

    """
    if end_date_column is None:
        return
    if schedule._kind == "per_policy_grid":  # noqa: SLF001
        raise ValueError(_PER_POLICY_END_DATE_MSG)
    if schedule._kind == FIXED_STEP:  # noqa: SLF001
        msg = (
            f"end_date_column={end_date_column!r} on a fixed-step axis: a step "
            "axis has no dates, so there is no period end to compare an end "
            "date with. Model termination with a decrement, or bound the "
            "projection with a per-period test on af.step or "
            "af.projection.t_years(); for a dated contract boundary, project on "
            'a calendar cadence: af.projection.set(..., frequency="monthly").'
        )
        raise ValueError(msg)


__all__ = ["Schedule"]
