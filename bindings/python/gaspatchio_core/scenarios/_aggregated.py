# bindings/python/gaspatchio_core/scenarios/_aggregated.py
# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: run_aggregated -- policy-axis aggregate driver (bounded memory).
# ABOUTME: Mirrors for_each_scenario's loop over policy row-slices; AggregatedResult.

"""Bounded-memory per-period aggregation for a single (non-scenario) run."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

import polars as pl

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios._aggregators import Count
from gaspatchio_core.scenarios._auto_batch import bounded_seed_size, size_to_budget
from gaspatchio_core.scenarios._for_each import _collect_with_peak
from gaspatchio_core.scenarios._metric import _Partitioned
from gaspatchio_core.scenarios._period_aggregators import _tidy_partitioned_vector

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from gaspatchio_core.scenarios._period_aggregators import VectorAggregator

_PERIOD = "__period"


@dataclass(frozen=True)
class AggregatedResult:
    """Typed output of :func:`run_aggregated`. Aliases are attribute-accessible."""

    aggregations: dict[str, Any]
    n_policies: int
    n_periods: int
    batch_size: int
    wall_time_s: float
    peak_rss_mb: float | None

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        # Only consulted when normal attribute lookup misses (i.e. for aliases).
        if name.startswith("__"):
            raise AttributeError(name)
        aggregations = object.__getattribute__(self, "aggregations")
        if name in aggregations:
            return aggregations[name]
        raise AttributeError(name)


def _alias_of(agg: Any) -> str:  # noqa: ANN401
    """Return the alias set on an aggregator (handles _Partitioned), else raise."""
    if isinstance(agg, _Partitioned):
        return agg.alias
    name: str | None = getattr(agg, "alias_", None)
    if not name:
        msg = f"Aggregator {type(agg).__name__} needs .alias(name) for run_aggregated."
        raise ValueError(msg)
    return name


def _reject_multi_level_over(aggregations: Sequence[Any]) -> None:
    """Reject ``PeriodQuantile.over()`` before any computation.

    ``PeriodQuantile`` produces a ``{level: array}`` dict per period — there is
    no single-column tidy form, so the tidy reshape used for all other vector
    ``.over()`` aggregators cannot represent it. Raise early with a clear message
    rather than crashing mid-run with an opaque Polars error.
    """
    for agg in aggregations:
        # Duck-type on ``levels`` (only PeriodQuantile carries it) rather than
        # isinstance(PeriodQuantile) — that would import _period_sketch and cycle.
        if isinstance(agg, _Partitioned) and hasattr(agg.inner, "levels"):
            msg = (
                "PeriodQuantile.over() is not yet supported on run_aggregated "
                "(its multi-level output has no tidy single-column form); "
                "use PeriodMedian/PeriodCTE with .over(), or PeriodQuantile "
                "without .over()."
            )
            raise NotImplementedError(msg)


def _reject_scenario_axis_only(aggregations: Sequence[Any]) -> None:
    """Reject aggregators only well-defined on the scenario axis.

    ``Count`` (counts scenarios) and ``ArgMin``/``ArgMax`` (need scenario identity)
    are inapplicable to the policy axis, with or without ``.over()``. ``.over()``
    partitioning itself IS supported (handled in _fold_batch).
    """
    for agg in aggregations:
        inner = agg.inner if isinstance(agg, _Partitioned) else agg
        if getattr(inner, "requires_scenario_id", False):
            msg = (
                f"{type(inner).__name__} needs a scenario axis (scenario_id) "
                "and is not applicable to run_aggregated; use for_each_scenario."
            )
            raise ValueError(msg)
        if isinstance(inner, Count):
            msg = (
                "Count counts scenarios and is not applicable to run_aggregated (the "
                "policy axis has no scenarios); use Sum/Period* aggregators instead."
            )
            raise ValueError(msg)  # noqa: TRY004 — usage error on the policy axis


def _max_period_len(frame: pl.DataFrame) -> int:
    """Longest List(Float64) length across all such columns (0 if none / all-null).

    Guards the n_periods scan against an all-null List(Float64) column, whose
    ``list.len().max()`` is None (which would crash ``int(None)``).
    """
    list_cols = [c for c, dt in frame.schema.items() if dt == pl.List(pl.Float64)]
    if not list_cols:
        return 0
    val = frame.select(
        pl.max_horizontal([pl.col(c).list.len() for c in list_cols]).max()
    ).item()
    return int(val) if val is not None else 0


def _fold_batch(
    proj: pl.DataFrame,
    aggregations: Sequence[Any],
    accumulators: dict[str, Any],
) -> None:
    """Fold one collected batch frame into every aggregator's accumulator."""
    list_col = next(
        (c for c, dt in proj.schema.items() if dt == pl.List(pl.Float64)),
        None,
    )
    # FIX A: guard against vector aggregators on a list-free frame.
    has_vector_agg = any(
        hasattr(a.inner if isinstance(a, _Partitioned) else a, "batch_reduce")
        for a in aggregations
    )
    if has_vector_agg and list_col is None:
        msg = (
            "run_aggregated: a Period* (vector) aggregator was supplied but the model "
            "produced no List(Float64) column to reduce over."
        )
        raise ValueError(msg)
    for agg in aggregations:
        alias = _alias_of(agg)
        if isinstance(agg, _Partitioned):
            by = agg.by
            if hasattr(agg.inner, "batch_reduce"):
                # vector .over(): {partition: partial} -> add_input per partition
                vec = cast("VectorAggregator", agg.inner)
                agg_col: str = vec.column
                proj_p = proj.with_columns(
                    pl.int_ranges(pl.col(agg_col).list.len()).alias(_PERIOD),
                )
                partials = vec.batch_reduce_over(proj_p, _PERIOD, by)
                for key, partial in partials.items():
                    accumulators[alias] = agg.add_input(
                        accumulators[alias], (key, partial)
                    )
            else:
                # scalar .over(): group_by(by), within_expr per group
                reduced = proj.group_by(by).agg(
                    agg.inner.within_expr().alias(alias)
                )
                key_pos = [reduced.columns.index(b) for b in by]
                val_pos = reduced.columns.index(alias)
                for row in reduced.iter_rows():
                    key = tuple(row[p] for p in key_pos)
                    accumulators[alias] = agg.add_input(
                        accumulators[alias], (key, row[val_pos])
                    )
            continue
        if hasattr(agg, "batch_reduce"):
            # Vector aggregator (PeriodSum, PeriodCount, etc.) — batch_reduce path.
            # Build the period index from THIS aggregator's column so that jagged
            # list columns (different lengths per column) each get the right index.
            agg_col2: str = agg.column
            proj_p2 = proj.with_columns(
                pl.int_ranges(pl.col(agg_col2).list.len()).alias(_PERIOD),
            )
            partial2 = agg.batch_reduce(proj_p2, _PERIOD)
            accumulators[alias] = agg.add_input(accumulators[alias], partial2)
        elif agg.within_expr_override is not None:
            # Custom within-reduction (.of): there is no per-policy column to
            # fold, so the override defines the batch's single contribution.
            value = proj.select(agg.within_expr().alias(alias)).item()
            accumulators[alias] = agg.add_input(accumulators[alias], value)
        else:
            # Scalar aggregator over the policy axis: every POLICY is a data
            # point. Fold each policy value into a per-batch partial accumulator,
            # then merge across batches. The old code collapsed the batch to one
            # within_expr value and add_input'd it, so non-additive aggregators
            # (Mean/Variance/Std/Median/CTE) divided by the BATCH count instead
            # of the policy count — batch-dependent, wrong. Additive aggregators
            # (Sum/Min/Max) are unaffected by the change.
            batch_acc = agg.create_accumulator()
            for value in proj.get_column(agg.column):
                batch_acc = agg.add_input(batch_acc, value)
            accumulators[alias] = agg.merge_accumulators(
                accumulators[alias], batch_acc
            )


def _check_period_origin(af: ActuarialFrame, align: str | None) -> None:
    """Reject inception-aligned (per-policy-origin) timelines unless align='duration'.

    Index-aligned summation is calendar-correct only when policies share a period
    origin (from_calendar_grid / per_policy_grid). from_inception's index is policy
    DURATION; summing across policies then mixes calendar periods.

    Args:
        af: The ActuarialFrame returned by the first batch of ``model_fn``.
        align: The ``align`` argument passed to :func:`run_aggregated`.

    Raises:
        ValueError: When the schedule kind is ``"from_inception"`` and
            ``align != "duration"``.

    """
    schedule = getattr(af, "_projection", None)
    kind = getattr(schedule, "_kind", None)
    if kind == "from_inception" and align != "duration":
        msg = (
            "Inception-aligned timeline: the period index is policy DURATION, not "
            "calendar time, so summing across policies mixes calendar periods. Pass "
            "align='duration' to aggregate by duration, or rebuild the projection with "
            "a shared valuation grid (per_policy=False) for calendar totals."
        )
        raise ValueError(msg)


def _resolve_auto(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
) -> tuple[int, ActuarialFrame, pl.DataFrame, int]:
    """Run one seed batch (~10 % of policies, ≥1), measure per-policy peak, return B.

    The seed batch is REAL work — its ActuarialFrame and collected DataFrame are
    returned to the caller to be folded exactly once (not re-run). ``B`` is the
    largest batch that fits the memory budget (:func:`size_to_budget`); there is no
    working-set cap — the policy axis is monotonic, so the budget alone governs.

    Args:
        model_fn: The same callable passed to :func:`run_aggregated`.
        model_points: Full policy table.

    Returns:
        ``(B, seed_af, seed_proj, seed_size)`` where ``B`` is the resolved batch
        size for the remainder, ``seed_af`` is the unreduced ``ActuarialFrame``
        (needed by the origin guard), ``seed_proj`` is the collected seed frame
        (ready to fold), and ``seed_size`` is the number of rows in the seed.

    """
    n_policies = model_points.height
    seed_size = bounded_seed_size(n_policies)
    seed_af = model_fn(ActuarialFrame(model_points.slice(0, seed_size)))
    seed_lazy = seed_af._df  # noqa: SLF001
    if seed_lazy is None:
        msg = "model_fn returned an ActuarialFrame with no underlying frame."
        raise ValueError(msg)
    seed_proj, seed_peak = _collect_with_peak(seed_lazy, engine="streaming")
    # per-cell cost: bytes per policy. Floor the measured peak with the materialised
    # frame size: a fast seed collect can complete between RSS samples (seed_peak==0),
    # which would otherwise collapse per_cell to 1 byte and size the WHOLE dataset
    # into one batch — defeating the bounded-memory guarantee.
    effective_peak = max(seed_peak, int(seed_proj.estimated_size()))
    per_cell = max(1, effective_peak // max(1, seed_size))
    return int(size_to_budget(per_cell, n_policies)), seed_af, seed_proj, seed_size


def run_aggregated(
    model_fn: Callable[[ActuarialFrame], ActuarialFrame],
    model_points: pl.DataFrame,
    aggregations: Sequence[Any],
    *,
    batch_size: int | Literal["auto"] = "auto",
    align: Literal["calendar", "duration"] | None = None,
) -> AggregatedResult:
    """Run ``model_fn`` over policy batches; fold each to per-period aggregates.

    ``aggregations`` is a list of aliased aggregators (same shape as
    ``for_each_scenario``); vector ``Period*`` aggregators yield per-period
    ndarrays, scalar aggregators (e.g. ``Sum``) yield portfolio scalars.

    Args:
        model_fn: Callable accepting an ``ActuarialFrame`` and returning one.
        model_points: Polars DataFrame of policy data; rows are sliced into batches.
        aggregations: Sequence of aliased aggregators (call ``.alias(name)``).
            An aggregator may be partitioned with ``agg.over(by)`` (one or more
            column names) to split results by a low-cardinality dimension: scalar
            aggregators yield a ``{*by, alias}`` DataFrame; ``Period*`` aggregators
            yield a tidy ``{*by, period, alias}`` DataFrame under that alias.
            ``Count``, ``ArgMin``, and ``ArgMax`` are not supported on the policy
            axis; ``PeriodQuantile.over()`` is not yet supported.
        batch_size: Number of policies per batch. ``"auto"`` sizes to the
            cgroup-aware memory budget via :func:`size_to_budget` — the largest
            policy batch whose predicted peak fits the budget (a bounded seed
            measures per-policy cost; the policy axis is monotonic, so the
            budget alone governs, with no working-set cap).
        align: Alignment mode guard. Pass ``"duration"`` for inception-aligned
            (per-policy-origin) timelines; otherwise a ``ValueError`` is raised
            when inception-aligned output is detected.

    Returns:
        :class:`AggregatedResult` with per-alias outputs plus metadata.

    """
    if model_points.height == 0:
        msg = "model_points is empty."
        raise ValueError(msg)

    _reject_scenario_axis_only(aggregations)
    _reject_multi_level_over(aggregations)
    aliases = [_alias_of(a) for a in aggregations]
    if len(set(aliases)) != len(aliases):
        msg = f"Aggregator aliases must be unique; got {aliases}."
        raise ValueError(msg)

    n_policies = model_points.height
    accumulators: dict[str, Any] = {
        a: agg.create_accumulator()
        for a, agg in zip(aliases, aggregations, strict=True)
    }

    started = time.perf_counter()
    n_periods = 0
    max_batch_peak = 0

    if batch_size == "auto":
        # --- auto path: run+measure the seed, fold it, then loop the remainder ---
        resolved, seed_af, seed_proj, seed_size = _resolve_auto(model_fn, model_points)
        # Origin guard runs on the seed ActuarialFrame (schedule lives on the frame).
        _check_period_origin(seed_af, align)
        # Account for seed's n_periods contribution.
        n_periods = max(n_periods, _max_period_len(seed_proj))
        # Fold the seed EXACTLY ONCE.
        _fold_batch(seed_proj, aggregations, accumulators)
        del seed_proj
        # Loop the REMAINDER (rows [seed_size, n_policies)) in steps of resolved.
        loop_start = seed_size
    else:
        # --- explicit-int path: unchanged, loop from 0 ---
        resolved = int(batch_size)
        loop_start = 0

    for start in range(loop_start, n_policies, resolved):
        batch = model_points.slice(start, resolved)
        out_af = model_fn(ActuarialFrame(batch))
        if batch_size != "auto" and start == 0:
            # explicit-int: guard on the first batch's frame
            _check_period_origin(out_af, align)
        lazy = out_af._df  # noqa: SLF001
        if lazy is None:
            msg = "model_fn returned an ActuarialFrame with no underlying frame."
            raise ValueError(msg)
        proj, batch_peak = _collect_with_peak(lazy, engine="streaming")
        max_batch_peak = max(max_batch_peak, batch_peak)
        # n_periods = max list length across ALL List(Float64) columns (all-null safe).
        n_periods = max(n_periods, _max_period_len(proj))
        _fold_batch(proj, aggregations, accumulators)
        del proj

    outputs: dict[str, Any] = {}
    for a, agg in zip(aliases, aggregations, strict=True):
        raw = agg.extract_output(accumulators[a])
        if isinstance(agg, _Partitioned) and hasattr(agg.inner, "batch_reduce"):
            raw = _tidy_partitioned_vector(raw, by=agg.by, alias=a)
        outputs[a] = raw
    return AggregatedResult(
        aggregations=outputs,
        n_policies=n_policies,
        n_periods=n_periods,
        batch_size=resolved,
        wall_time_s=time.perf_counter() - started,
        peak_rss_mb=(max_batch_peak / (1024 * 1024)) if max_batch_peak else None,
    )


__all__ = [
    "AggregatedResult",
    "run_aggregated",
]
