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
    from gaspatchio_core.frame.base import ActuarialFrame


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
        if until in ("term_months", "term_years") and sched_freq not in _MONTHS_PER_PERIOD:
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

    def _stamp_eager_columns(self, schedule: Schedule) -> ActuarialFrame:
        """Stamp projection_start_date / projection_end_date / num_proj_months."""
        if schedule._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = schedule.period_dates()  # list[date], length n_periods+1
            start_date = boundaries[0]
            end_date = boundaries[-1]
            stamped_df = self._frame._df.with_columns(  # noqa: SLF001
                projection_start_date=pl.lit(start_date),
                projection_end_date=pl.lit(end_date),
                num_proj_months=pl.lit(len(boundaries)),
            )
        else:
            # from_inception / per_policy_grid: per-policy boundaries (jagged).
            period_dates_e = (
                schedule.per_policy_period_dates_expr()
                if schedule._kind == "per_policy_grid"  # noqa: SLF001
                else schedule.period_dates_expr()
            )
            stamped_df = self._frame._df.with_columns(  # noqa: SLF001
                projection_start_date=period_dates_e.list.first(),
                projection_end_date=period_dates_e.list.last(),
                # Signed Int32 to match the uniform path's pl.lit(int): a bare
                # list.len() is UInt and `num_proj_months - k` would underflow.
                # fill_null(0) so a null until_value stamps 0 (matching the
                # clamped per_policy_period_count_expr) rather than null — else
                # the int_ranges(0, num_proj_months - 1) feeder builds a null
                # list and the rollforward kernel rejects it.
                num_proj_months=period_dates_e.list.len().fill_null(0).cast(pl.Int32),
            )

        new_af = self._frame.__class__(stamped_df)
        new_af._projection = schedule  # noqa: SLF001
        new_af._mode = self._frame._mode  # noqa: SLF001
        new_af._verbose = self._frame._verbose  # noqa: SLF001
        new_af._threads = self._frame._threads  # noqa: SLF001
        return new_af

    def rollforward(self, **kwargs: Any) -> RollforwardBuilder:  # noqa: ANN401
        """Construct a :class:`RollforwardBuilder` that reads schedule from this frame.

        ``schedule=`` is no longer accepted on this method — call
        ``af.projection.set(...)`` first.
        """
        if "schedule" in kwargs:
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
        kwargs["schedule"] = self._frame._projection  # noqa: SLF001
        return RollforwardBuilder(**kwargs)

    def _require_projection(self) -> Schedule:
        """Return the frame's Schedule or raise if absent."""
        proj = self._frame._projection  # noqa: SLF001
        if proj is None:
            msg = "This frame has no projection. Call af.projection.set(...) first."
            raise ValueError(msg)
        return proj

    def period_dates(self) -> pl.Expr:
        """Return per-row List<Date>.

        Uniform schedules give length ``n_periods+1`` for every row;
        ``per_policy_grid`` gives each policy its own (variable) length.
        """
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            boundaries = sched.period_dates()
            return pl.lit(boundaries, dtype=pl.List(pl.Date))
        if sched._kind == "per_policy_grid":  # noqa: SLF001
            return sched.per_policy_period_dates_expr()
        return sched.period_dates_expr()

    def year_fractions(self) -> pl.Expr:
        """Return per-row List<Float64> of length n_periods (per-period dt[t])."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            yfs = sched.year_fractions()
            return pl.lit(yfs, dtype=pl.List(pl.Float64))
        return sched.year_fractions_expr()

    def t_years(self) -> pl.Expr:
        """Return per-row List<Float64> of cumulative year fractions from 0.

        Length is ``n_periods + 1``. Feeds ``Curve.discount_factor(t)`` directly.
        """
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            ty = sched.cumulative_year_fractions()
            return pl.lit(ty, dtype=pl.List(pl.Float64))
        # from_inception / per_policy_grid: cumsum the year_fractions_expr with
        # a leading 0. (list.cum_sum() does not exist; eval cum_sum per sublist.)
        yfs_expr = sched.year_fractions_expr()
        zeros = pl.lit([0.0], dtype=pl.List(pl.Float64))
        return pl.concat_list([zeros, yfs_expr.list.eval(pl.element().cum_sum())])

    def anniversary_mask(self) -> pl.Expr:
        """Return per-row List<Boolean> of length n_periods marking anniversaries."""
        sched = self._require_projection()
        if sched._kind == "from_calendar_grid":  # noqa: SLF001
            mask = sched.anniversary_mask()
            return pl.lit(mask, dtype=pl.List(pl.Boolean))
        return sched.anniversary_mask_expr()

    def is_in_force(self, *, end_date_column: str | None = None) -> pl.Expr:
        """Return per-row List<Boolean> of length n_periods — boundary mask.

        Pass ``end_date_column`` for from_inception schedules where each
        policy has its own end date. Without it, the mask is uniform True
        for all periods.
        """
        sched = self._require_projection()
        return sched.is_in_force_expr(end_date_column=end_date_column)

    def contract_boundary(self, *, end_date_column: str | None = None) -> pl.Expr:
        """Return per-row List<Boolean> of length n_periods — kernel termination mask.

        True at period t means the contract has terminated by period t. Pass to
        ``af.projection.rollforward(..., contract_boundary=...)`` to bound the
        projection at each policy's end date.

        This is the **negation** of :meth:`is_in_force` — the kernel uses
        boundary semantics (True = terminate); ``is_in_force()`` is natural
        for other uses (True = active).
        """
        sched = self._require_projection()
        return sched.contract_boundary_expr(end_date_column=end_date_column)

    def canonical_form(self) -> dict[str, Any]:
        """Return the structural recipe — same shape as Schedule.canonical_form()."""
        sched = self._require_projection()
        return sched.canonical_form()

    def source_sha(self) -> str:
        """Return sha256:<hex> over the canonical form bytes (audit identifier)."""
        sched = self._require_projection()
        return sched.source_sha()
