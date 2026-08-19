# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Frame-level projection accessor — set() unifies projection axis setup.
# ABOUTME: rollforward() reads schedule from frame; both go through this accessor.

"""Frame-level projection accessor for actuarial projection setup."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from gaspatchio_core.accessors.base import BaseFrameAccessor
from gaspatchio_core.frame.registry import register_accessor
from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gaspatchio_core.column.proxy_aware_expr import ProxyAwareExpr
    from gaspatchio_core.frame.base import ActuarialFrame
    from gaspatchio_core.rollforward._builder import ExprLike


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
    ).cast(pl.List(pl.Int32))


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


@register_accessor("projection", kind="frame")
class ProjectionFrameAccessor(BaseFrameAccessor):
    """Frame-level accessor for actuarial projection operations.

    Two verbs:
      - ``set(...)`` — declare the projection time axis on the frame
      - ``rollforward(...)`` — construct a state-machine rollforward
        builder that reads the projection from this frame
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
            "next_anniversary",
        ]
        | None = None,
        until_value: int | dt.date | str | pl.Expr | None = None,
        issue_age_column: str = "issue_age",
        inception_column: str = "policy_inception",
        # Kwargs path — synthetic
        start_date: dt.date | None = None,
        n_periods: int | None = None,
        # Common
        frequency: str | None = None,
        per_policy: bool | None = None,
    ) -> ActuarialFrame:
        """Declare the projection time axis on this frame.

        With a per-policy ``until_value`` column, each policy projects only as
        far as its own horizon — producing variable-length (jagged) list
        columns instead of one uniform grid sized to the longest-lived policy.
        This recovers the compute/memory of per-policy timelines while keeping
        the unified projection API.

        ``per_policy`` (default ``None`` = auto): jagged is the default whenever
        it applies (a column ``until_value`` with a ``term_*`` horizon); other
        cases fall back to a uniform grid. Pass ``per_policy=False`` to force a
        uniform (rectangular) grid — useful when combining fixed-width list
        columns or doing cross-policy shared-axis aggregation. Pass
        ``per_policy=True`` to require jagged (raises if it cannot apply).
        ``rollforward()`` works on both uniform and jagged timelines.

        Stamps ``projection_start_date``, ``projection_end_date``,
        ``num_proj_months``, and — at month-aligned frequencies on a
        projection-anchored axis — ``month``: elapsed whole months from the
        projection start, length ``n_periods + 1``, aligned with
        ``t_years()``. Derive a year label in the model with the convention
        you mean: ``af.month // 12`` (completed years / duration) or
        ``ceil(month / 12)`` ("year 1" ordinal). There is deliberately no
        ``proj_year`` or ``year`` column.

        Raises:
            ValueError: if the frame already carries a ``month`` column and
                has no in-session projection — rename your column, or drop it
                if it came from a previous run's output.

        See ref/38-projection-axis/specs for full semantics.

        """
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

        if schedule is None:
            schedule = self._build_schedule(
                valuation_date=valuation_date,
                until=until,
                until_value=until_value,
                issue_age_column=issue_age_column,
                inception_column=inception_column,
                start_date=start_date,
                n_periods=n_periods,
                frequency=frequency,
                per_policy=per_policy,
            )

        return self._stamp_eager_columns(schedule)

    def _build_schedule(  # noqa: PLR0913
        self,
        *,
        valuation_date: dt.date | None,
        until: str | None,
        until_value: Any,  # noqa: ANN401
        issue_age_column: str,
        inception_column: str,  # noqa: ARG002
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
                "OR valuation_date+until+until_value+frequency (policy-anchored)."
            )
            raise ValueError(msg)

        # A month/year horizon (term_months/term_years) with a sub-month cadence
        # (1W/1D) makes the period count ambiguous — the uniform and jagged
        # paths would disagree silently (e.g. a 12-month term gives ~12 periods
        # uniform but ~52 jagged at weekly). Require a month-aligned frequency.
        if (
            until in ("term_months", "term_years")
            and sched_freq not in _MONTHS_PER_PERIOD
        ):
            msg = (
                f"until={until!r} is a month/year horizon and requires a "
                f"month-aligned frequency (one of {sorted(_MONTHS_PER_PERIOD)}); "
                f"got a frequency resolving to {sched_freq!r}. Use a monthly / "
                "quarterly / semi-annual / annual frequency."
            )
            raise ValueError(msg)

        # Compute the portfolio-maximum n_periods (also the uniform-grid size).
        n_per = self._compute_n_periods(
            valuation_date=valuation_date,
            until=until,
            until_value=until_value,
            issue_age_column=issue_age_column,
            sched_freq=sched_freq,
        )

        # Resolve jagged-vs-uniform. ``per_policy=None`` (auto, the default)
        # prefers jagged whenever it applies — a column ``until_value`` with a
        # ``term_*`` horizon — and falls back to uniform otherwise. Explicit
        # ``True`` requires jagged (raises if inapplicable); explicit ``False``
        # forces uniform.
        jagged_applicable = isinstance(until_value, str) and until in (
            "term_months",
            "term_years",
        )
        use_per_policy = jagged_applicable if per_policy is None else per_policy

        # Per-policy (jagged) path: each policy projects only its own horizon.
        if use_per_policy:
            if not isinstance(until_value, str):
                msg = (
                    "per_policy=True requires until_value to be a column name "
                    "(str) giving each policy's horizon; got "
                    f"{type(until_value).__name__}."
                )
                raise ValueError(msg)
            if until not in ("term_months", "term_years"):
                msg = (
                    "per_policy=True currently supports until in "
                    "{'term_months', 'term_years'}; "
                    f"got until={until!r}. Use the uniform path (per_policy=False) "
                    "for other horizons."
                )
                raise ValueError(msg)
            return Schedule.from_per_policy_grid(
                start_date=valuation_date,
                n_periods=n_per,
                frequency=sched_freq,  # type: ignore[arg-type]
                until_kind=until,
                until_value_column=until_value,
            )

        # Uniform path (per_policy=False, or auto fell back). A per-policy
        # until_value (column / expr) is collapsed to the portfolio max here —
        # every policy carries the longest-lived policy's horizon.
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
        """Compute uniform n_periods from an `until` specification.

        Per-policy ``until_value`` (column name or ``pl.Expr``) is resolved
        as a max across the frame; per-policy boundaries are expressed via
        ``af.projection.is_in_force(...)``.
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
        if until == "next_anniversary":
            n_value = self._resolve_int_until_value(until_value)
            return n_value * _PERIODS_PER_YEAR[sched_freq]
        valid = [
            "maximum_age",
            "term_years",
            "term_months",
            "fixed_date",
            "next_anniversary",
        ]
        msg = f"invalid until={until!r}; expected one of {valid}"
        raise ValueError(msg)

    def _resolve_int_until_value(self, until_value: Any) -> int:  # noqa: ANN401
        """Resolve ``until_value`` to a single integer.

        - ``int`` is used directly.
        - ``str`` is interpreted as a column name; the max is taken.
        - ``pl.Expr`` is evaluated; the max is taken.
        """
        if isinstance(until_value, int):
            return until_value
        af_df = self._frame._df  # noqa: SLF001
        if isinstance(until_value, str):
            return int(af_df.select(pl.col(until_value).max()).collect()[0, 0])
        return int(af_df.select(until_value.max()).collect()[0, 0])

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
        af_df = self._frame._df  # noqa: SLF001
        if isinstance(until_value, int):
            # uniform max age — the shared grid must be long enough for the
            # YOUNGEST life, so size it from min(issue_age) (the most tail
            # years). Using max(issue_age) would give the fewest months and
            # truncate every younger cohort. This mirrors the str/expr
            # branches below, which take max(target - issue) over policies.
            min_issue = af_df.select(pl.col(issue_age_column).min()).collect()[0, 0]
            years = until_value - int(min_issue)
        elif isinstance(until_value, str):
            # per-policy max-age column — compute max(target - issue)
            expr = pl.col(until_value) - pl.col(issue_age_column)
            years = int(af_df.select(expr.max()).collect()[0, 0])
        else:  # pl.Expr
            expr = until_value - pl.col(issue_age_column)
            years = int(af_df.select(expr.max()).collect()[0, 0])
        return years * _PERIODS_PER_YEAR[sched_freq]

    def _reject_reserved_column_collisions(self) -> None:
        """Raise if the frame already carries a column projection.set() stamps.

        Overwriting silently is the failure class this release exists to
        remove — and a calendar ``year`` or a source ``month`` on the model
        points is exactly the sort of column a user would not expect to lose.

        This guards the *user's* columns, not ours. Re-projecting a frame that
        already has an in-session projection is supported, and there the index
        is ours to replace. A frame reconstructed from a previous run's output
        (parquet reload, ``ActuarialFrame(af.collect())``) carries ``month``
        without a live projection — we cannot tell that apart from a user's
        calendar column, so the error names both exits rather than guessing.
        """
        if self._frame._projection is not None:  # noqa: SLF001
            return

        frame_df = self._frame._df  # noqa: SLF001
        if frame_df is None:
            return

        if _MONTH_COLUMN in frame_df.collect_schema().names():
            msg = (
                f"projection.set() materialises {_MONTH_COLUMN!r} (elapsed whole "
                f"months from projection start), but the frame already has a "
                f"{_MONTH_COLUMN!r} column.\n"
                f"  • if it is your own (e.g. a calendar month), rename it: "
                f'mp.rename({{"{_MONTH_COLUMN}": "source_{_MONTH_COLUMN}"}})\n'
                f"  • if it came from a previous projection run's output, drop "
                f'it: mp.drop("{_MONTH_COLUMN}")'
            )
            raise ValueError(msg)

    def _stamp_eager_columns(self, schedule: Schedule) -> ActuarialFrame:
        """Stamp projection dates, num_proj_months, and the ``month`` index.

        ``month`` is the period index shipped examples already assume exists
        (#36): **elapsed whole months from the projection start**, one value
        per boundary (length ``n_periods + 1``, aligned with ``t_years()``).

        It is stamped only where the name is honest:

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
        stamp_month = (
            schedule.frequency in _MONTHS_PER_PERIOD
            and schedule._kind != "from_inception"  # noqa: SLF001
        )
        if stamp_month:
            # Only a schedule that will stamp `month` can collide with it —
            # weekly/daily/from_inception axes leave the user's column alone.
            self._reject_reserved_column_collisions()

        if schedule._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = schedule.period_dates()  # list[date], length n_periods+1
            start_date = boundaries[0]
            end_date = boundaries[-1]
            eager_columns: dict[str, pl.Expr] = {
                "projection_start_date": pl.lit(start_date),
                "projection_end_date": pl.lit(end_date),
                "num_proj_months": pl.lit(len(boundaries)),
            }
            if stamp_month:
                # Boundaries on a month-aligned grid share one anchor
                # convention, so the calendar-month difference is exact.
                months = [
                    (d.year - start_date.year) * 12 + (d.month - start_date.month)
                    for d in boundaries
                ]
                eager_columns[_MONTH_COLUMN] = pl.lit(months, dtype=pl.List(pl.Int32))
            stamped_df = self._frame._df.with_columns(**eager_columns)  # noqa: SLF001
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
                # Signed Int32 to match the uniform path's pl.lit(int): a bare
                # list.len() is UInt and `num_proj_months - k` would underflow.
                # fill_null(0) so a null until_value stamps 0 (matching the
                # clamped per_policy_period_count_expr) rather than null — else
                # the int_ranges(0, num_proj_months - 1) feeder builds a null
                # list and the rollforward kernel rejects it.
                "num_proj_months": (
                    period_dates_e.list.len().fill_null(0).cast(pl.Int32)
                ),
            }
            if stamp_month:
                # Elapsed whole months from each policy's own first boundary —
                # jagged with the timeline, not padded to the longest-lived
                # policy. Same null guard as num_proj_months: a null horizon
                # stamps an empty index, not a null one.
                eager_columns[_MONTH_COLUMN] = _elapsed_months_expr(
                    period_dates_e
                ).fill_null(pl.lit([], dtype=pl.List(pl.Int32)))
            stamped_df = self._frame._df.with_columns(**eager_columns)  # noqa: SLF001

        new_af = self._frame.__class__(stamped_df)
        new_af._projection = schedule  # noqa: SLF001
        new_af._mode = self._frame._mode  # noqa: SLF001
        new_af._verbose = self._frame._verbose  # noqa: SLF001
        new_af._threads = self._frame._threads  # noqa: SLF001
        return new_af

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
        if self._frame._projection is None:  # noqa: SLF001
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
        return RollforwardBuilder(
            states=states,
            schedule=self._frame._projection,  # noqa: SLF001
            points=points,
            track_increments=track_increments,
            lapse_when_all_non_positive=lapse_when_all_non_positive,
            contract_boundary=contract_boundary,
            batch_axes=batch_axes,
        )

    def _require_projection(self) -> Schedule:
        """Return the frame's Schedule or raise if absent."""
        proj = self._frame._projection  # noqa: SLF001
        if proj is None:
            msg = "This frame has no projection. Call af.projection.set(...) first."
            raise ValueError(msg)
        return proj

    def _wrap(self, expr: pl.Expr) -> ProxyAwareExpr:
        """Wrap an emitted expression for proxy-aware operator interop.

        These methods hand frame-independent expressions to users, and a
        bare ``pl.Expr`` raises on a proxy operand before the proxy's
        reflected method can run (gh#67) — so results worked in one
        operand order and not the other. ``ProxyAwareExpr`` fixes the
        operand-order trap while staying a real ``pl.Expr``, so raw
        Polars interop (``pl.concat_list([...])``, the tutorial idiom)
        is untouched. Same treatment as ``Table.lookup`` and the
        ``Schedule.*_expr`` family.
        """
        from gaspatchio_core.column.proxy_aware_expr import ProxyAwareExpr

        return ProxyAwareExpr.wrap(expr)

    def period_dates(self) -> ProxyAwareExpr:
        """Return per-row List<Date>.

        Uniform schedules give length ``n_periods+1`` for every row;
        ``per_policy_grid`` gives each policy its own (variable) length.
        """
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = sched.period_dates()
            return self._wrap(pl.lit(boundaries, dtype=pl.List(pl.Date)))
        if sched._kind == "per_policy_grid":  # noqa: SLF001
            return self._wrap(sched.per_policy_period_dates_expr())
        return self._wrap(sched.period_dates_expr())

    def year_fractions(self) -> ProxyAwareExpr:
        """Return per-row List<Float64> of length n_periods (per-period dt[t])."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            yfs = sched.year_fractions()
            return self._wrap(pl.lit(yfs, dtype=pl.List(pl.Float64)))
        return self._wrap(sched.year_fractions_expr())

    def t_years(self) -> ProxyAwareExpr:
        """Return per-row List<Float64> of cumulative year fractions from 0.

        Length is ``n_periods + 1``. Feeds ``Curve.discount_factor(t)`` directly.
        """
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            ty = sched.cumulative_year_fractions()
            return self._wrap(pl.lit(ty, dtype=pl.List(pl.Float64)))
        # from_inception / per_policy_grid: cumsum the year_fractions_expr with
        # a leading 0. (list.cum_sum() does not exist; eval cum_sum per sublist.)
        yfs_expr = sched.year_fractions_expr()
        zeros = pl.lit([0.0], dtype=pl.List(pl.Float64))
        return self._wrap(
            pl.concat_list([zeros, yfs_expr.list.eval(pl.element().cum_sum())])
        )

    def anniversary_mask(self) -> ProxyAwareExpr:
        """Return per-row List<Boolean> of length n_periods marking anniversaries."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            mask = sched.anniversary_mask()
            return self._wrap(pl.lit(mask, dtype=pl.List(pl.Boolean)))
        return self._wrap(sched.anniversary_mask_expr())

    def is_in_force(self, *, end_date_column: str | None = None) -> ProxyAwareExpr:
        """Return per-row List<Boolean> of length n_periods — boundary mask.

        Pass ``end_date_column`` for from_inception schedules where each
        policy has its own end date. Without it, the mask is uniform True
        for all periods.
        """
        sched = self._require_projection()
        return self._wrap(sched.is_in_force_expr(end_date_column=end_date_column))

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
        sched = self._require_projection()
        return self._wrap(sched.contract_boundary_expr(end_date_column=end_date_column))

    def canonical_form(self) -> dict[str, Any]:
        """Return the structural recipe — same shape as Schedule.canonical_form()."""
        sched = self._require_projection()
        return sched.canonical_form()

    def source_sha(self) -> str:
        """Return sha256:<hex> over the canonical form bytes (audit identifier)."""
        sched = self._require_projection()
        return sched.source_sha()
