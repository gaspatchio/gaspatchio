# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Rank-based per-period aggregators (PeriodQuantile/Median/CTE).
# ABOUTME: list[SignedSketch] state; vectorized histogram build, no per-value loop.

"""Per-period sketch-backed aggregators.

They follow the null rule of :mod:`gaspatchio.scenarios._period_aggregators`:
a null is skipped, never sketched, and a period whose sketch saw no value is
masked (``None``) in the answer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl

from gaspatchio.scenarios._aggregators import _refuse_a_tail_option, scenario_aggregator
from gaspatchio.scenarios._period_aggregators import VectorAggregator, _scenario_totals
from gaspatchio.scenarios._sketch import SignedSketch


def build_period_sketches(
    frame: pl.DataFrame, period: str, column: str, *, relative_accuracy: float
) -> list[SignedSketch]:
    """One :class:`SignedSketch` per period, built via a vectorized histogram.

    The DDSketch bin key is reproduced in Polars from ``gamma``; a real per-bin
    representative value (``first(|v|)``) is fed to ``from_binned`` so the
    library's own mapping assigns the bucket. Held bit-exact against per-value
    adds by ``tests/scenarios/test_period_sketch.py``, which builds both ways
    and compares quantiles.

    Args:
        frame: DataFrame with a list column ``column`` and a period column ``period``.
            The period column must contain integer period indices (one list per row,
            each element belonging to the period at that index within the list).
        period: Name of the column holding integer period indices.  Each row's list
            element at position ``i`` is assigned to period ``i``.
        column: Name of the list column holding numeric cashflow values.
        relative_accuracy: DDSketch relative-accuracy parameter shared across all
            per-period sketches.  Smaller values give tighter quantile bounds but
            consume more memory per sketch.

    Returns:
        A list of :class:`SignedSketch` objects, one per period (indexed 0 …
        ``n_periods - 1``).  The list length equals ``max(period) + 1`` across
        all rows after the explode.

    """
    exploded = (
        frame.lazy().select(pl.col(period), pl.col(column)).explode([period, column])
    )
    return _sketches_from_exploded(
        exploded, period, column, relative_accuracy=relative_accuracy
    )


def _sketches_from_exploded(
    exploded: pl.LazyFrame,
    period: str,
    column: str,
    *,
    relative_accuracy: float,
) -> list[SignedSketch]:
    """Vectorized histogram build over an already-exploded (period, value) frame.

    Core of :func:`build_period_sketches`; also fed directly with per-scenario
    stage-1 totals (one scalar row per (scenario, period)) by the two-stage
    scenario-axis reducers.

    The values are read as the doubles a sketch holds, as ``SignedSketch.add``
    reads each one, before any is binned. Binned in a whole-number column's
    own width, the least ``i64`` has no magnitude: its absolute value wrapped
    to itself, and three policies of -2**63 answered a median of +9.2e18.
    """
    gamma = (1.0 + relative_accuracy) / (1.0 - relative_accuracy)
    inv_log_gamma = 1.0 / math.log(gamma)
    exploded = exploded.with_columns(pl.col(column).cast(pl.Float64))

    zeros = (
        exploded.filter(pl.col(column) == 0)
        .group_by(period)
        .agg(pl.len().alias("z"))
        .collect()
    )
    # A NaN answers false to `== 0` and true to `!= 0`, so without this it
    # reached the binning below, where `log()` of it is NaN and the cast of that
    # to a bin index fails the whole collect. It has no bin to reach: it is not a
    # zero and it is in neither store. Counted per period instead, exactly as
    # `SignedSketch.add` counts it on the per-value path, so that the refusal in
    # `_probe_values` fires for the period that saw it and for no other. Null is
    # not NaN and is excluded from all three: `is_nan()` and `!= 0` both answer
    # null for it, and a null filter keeps nothing.
    nans = (
        exploded.filter(pl.col(column).is_nan())
        .group_by(period)
        .agg(pl.len().alias("k"))
        .collect()
    )
    binned = (
        exploded.filter((pl.col(column) != 0) & pl.col(column).is_not_nan())
        .with_columns(
            (pl.col(column) > 0).cast(pl.Int8).alias("__sign"),
            pl.col(column).abs().alias("__abs"),
        )
        .with_columns(
            (pl.col("__abs").log() * inv_log_gamma).ceil().cast(pl.Int64).alias("__bin")
        )
        .group_by([period, "__sign", "__bin"])
        .agg(pl.col("__abs").first().alias("__rep"), pl.len().alias("__cnt"))
        .collect()
    )

    # Horizon = max period index across ALL exploded rows, INCLUDING periods whose
    # values are entirely null (absent from zeros/binned, which filter by value). This
    # keeps the sketch vector the same length as PeriodSum/PeriodCount; a trailing
    # all-null period would otherwise be dropped. max() ignores null periods (the
    # empty-[]-list phantom).
    period_max = exploded.select(pl.col(period).max()).collect().item()
    n_periods = (int(period_max) + 1) if period_max is not None else 0

    pos: list[list[tuple[float, int]]] = [[] for _ in range(n_periods)]
    neg: list[list[tuple[float, int]]] = [[] for _ in range(n_periods)]
    zero_n = [0] * n_periods
    nan_n = [0] * n_periods
    for row in zeros.iter_rows(named=True):
        zero_n[row[period]] = row["z"]
    for row in nans.iter_rows(named=True):
        nan_n[row[period]] = row["k"]
    for row in binned.iter_rows(named=True):
        t = row[period]
        entry = (float(row["__rep"]), int(row["__cnt"]))
        (pos if row["__sign"] == 1 else neg)[t].append(entry)

    return [
        SignedSketch.from_binned(
            pos=pos[t],
            neg=neg[t],
            zero_n=zero_n[t],
            nan_n=nan_n[t],
            relative_accuracy=relative_accuracy,
        )
        for t in range(n_periods)
    ]


def build_period_sketches_over(
    frame: pl.DataFrame,
    period: str,
    column: str,
    by: tuple[str, ...],
    *,
    relative_accuracy: float,
) -> dict[tuple[Any, ...], list[SignedSketch]]:
    """Per-partition list[SignedSketch]: ``build_period_sketches`` grouped by ``by``."""
    parts: dict[tuple[Any, ...], list[SignedSketch]] = {}
    for key, sub in frame.partition_by(*by, as_dict=True, include_key=False).items():
        parts[key] = build_period_sketches(
            sub, period, column, relative_accuracy=relative_accuracy
        )
    return parts


def _merge_sketch_lists(
    a: list[SignedSketch], b: list[SignedSketch], relative_accuracy: float
) -> list[SignedSketch]:
    """Elementwise SignedSketch.merge; pad the shorter with empty sketches."""
    n = max(len(a), len(b))
    out: list[SignedSketch] = []
    for t in range(n):
        sa = a[t] if t < len(a) else SignedSketch(relative_accuracy=relative_accuracy)
        sb = b[t] if t < len(b) else SignedSketch(relative_accuracy=relative_accuracy)
        out.append(SignedSketch.merge(sa, sb))
    return out


@dataclass(frozen=True)
class _PeriodSketchAgg(VectorAggregator):
    """Shared list[SignedSketch] machinery for rank-based per-period aggregators."""

    relative_accuracy: float = 1e-4

    def create_accumulator(self) -> Any:  # noqa: ANN401
        return []

    def batch_reduce(self, frame: pl.DataFrame, period: str) -> Any:  # noqa: ANN401
        return build_period_sketches(
            frame, period, self.column, relative_accuracy=self.relative_accuracy
        )

    def batch_reduce_over(
        self, frame: pl.DataFrame, period: str, by: tuple[str, ...]
    ) -> dict[tuple[Any, ...], Any]:
        """Partitioned sketch reduce: ``{partition_tuple: list[SignedSketch]}``."""
        return build_period_sketches_over(
            frame, period, self.column, by, relative_accuracy=self.relative_accuracy
        )

    def batch_reduce_within(
        self, frame: pl.DataFrame, period: str, within_by: tuple[str, ...]
    ) -> Any:  # noqa: ANN401
        """Two-stage sketch reduce for the scenario axis.

        Stage 1 sums ``column`` within each ``within_by`` group (scenario) per
        period — exact, matching the closed-form aggregators' stage 1. Stage 2
        inserts each group's per-period total into the period sketches, so the
        rank statistic is taken ACROSS scenarios of per-scenario totals.
        ``within_by`` groups are disjoint across batches, so merging the
        per-batch sketches keeps the fold batch-invariant.
        """
        totals = self._stage1_totals(frame, period, (), within_by)
        return _sketches_from_exploded(
            totals.lazy().select(pl.col(period), pl.col(self.column)),
            period,
            self.column,
            relative_accuracy=self.relative_accuracy,
        )

    def batch_reduce_over_within(
        self,
        frame: pl.DataFrame,
        period: str,
        by: tuple[str, ...],
        within_by: tuple[str, ...],
    ) -> dict[tuple[Any, ...], Any]:
        """Partitioned two-stage sketch reduce (scenario axis), per ``by`` key."""
        totals = self._stage1_totals(frame, period, by, within_by)
        parts: dict[tuple[Any, ...], Any] = {}
        partitioned = totals.partition_by(*by, as_dict=True, include_key=False)
        for key, sub in partitioned.items():
            parts[key] = _sketches_from_exploded(
                sub.lazy().select(pl.col(period), pl.col(self.column)),
                period,
                self.column,
                relative_accuracy=self.relative_accuracy,
            )
        return parts

    def _stage1_totals(
        self,
        frame: pl.DataFrame,
        period: str,
        by: tuple[str, ...],
        within_by: tuple[str, ...],
    ) -> pl.DataFrame:
        """Sum ``column`` per (*by, *within_by, period) after exploding the lists.

        A group whose every value at a period is null totals null, which the
        sketch then skips as it skips any null. A scenario's total of whole
        numbers is exact, and refused by name past ``i64``.
        """
        group_cols = (*by, *within_by)
        cells = (
            frame.lazy()
            .select(
                *[pl.col(c) for c in group_cols],
                pl.col(period),
                pl.col(self.column),
            )
            .explode([period, self.column])
            .filter(pl.col(period).is_not_null())
        )
        return _scenario_totals(
            cells,
            [*group_cols, period],
            self.column,
            schema=frame.schema,
            period=period,
            within_by=within_by,
            within=self.within,
        ).collect()

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _merge_sketch_lists(state, value, self.relative_accuracy)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _merge_sketch_lists(a, b, self.relative_accuracy)


def _per_period(state: list[SignedSketch], read: Any) -> np.ma.MaskedArray:  # noqa: ANN401 — one reading of a sketch
    """Read each period's sketch, masked (NaN underneath) where it saw no value."""
    present = np.array([sk.n > 0 for sk in state], dtype=bool)
    values = np.array(
        [read(sk) if sk.n > 0 else np.nan for sk in state], dtype=np.float64
    )
    return np.ma.MaskedArray(values, mask=~present)


@scenario_aggregator("PeriodQuantile")
@dataclass(frozen=True)
class PeriodQuantile(_PeriodSketchAgg):
    """Per-period quantile(s) across the batched axis (DDSketch-backed).

    Nulls are skipped; at a period that saw nothing but nulls every level's
    vector is masked (``None``).
    """

    levels: tuple[float, ...] = (0.5,)

    def __post_init__(self) -> None:
        super().__post_init__()
        _refuse_a_tail_option("PeriodQuantile", levels=tuple(self.levels))

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return {
            level: _per_period(state, lambda sk, q=level: sk.quantile(q))
            for level in self.levels
        }

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical(
            {
                "kind": "PeriodQuantile",
                "column": self.column,
                "levels": list(self.levels),
                "relative_accuracy": self.relative_accuracy,
            }
        )


@scenario_aggregator("PeriodMedian")
@dataclass(frozen=True)
class PeriodMedian(_PeriodSketchAgg):
    """Per-period median across the batched axis.

    Nulls are skipped; a period that saw nothing but nulls is masked (``None``).
    """

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return _per_period(state, lambda sk: sk.quantile(0.5))

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical(
            {
                "kind": "PeriodMedian",
                "column": self.column,
                "relative_accuracy": self.relative_accuracy,
            }
        )


@scenario_aggregator("PeriodCTE")
@dataclass(frozen=True)
class PeriodCTE(_PeriodSketchAgg):
    """Per-period Conditional Tail Expectation across the batched axis.

    Nulls are skipped; a period that saw nothing but nulls is masked (``None``).
    """

    level: float = 0.005
    direction: Literal["upper", "lower"] = "upper"

    def __post_init__(self) -> None:
        super().__post_init__()
        _refuse_a_tail_option("PeriodCTE", level=self.level, direction=self.direction)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return _per_period(
            state, lambda sk: sk.cte(level=self.level, direction=self.direction)
        )

    def canonical_form(self) -> dict[str, Any]:
        return self._canonical(
            {
                "kind": "PeriodCTE",
                "column": self.column,
                "level": self.level,
                "direction": self.direction,
                "relative_accuracy": self.relative_accuracy,
            }
        )


__all__ = [
    "PeriodCTE",
    "PeriodMedian",
    "PeriodQuantile",
    "build_period_sketches",
    "build_period_sketches_over",
]
