# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Rank-based per-period aggregators (PeriodQuantile/Median/CTE).
# ABOUTME: list[SignedSketch] state; vectorized histogram build, no per-value loop.

"""Per-period sketch-backed aggregators."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import polars as pl

from gaspatchio_core.scenarios._aggregators import scenario_aggregator
from gaspatchio_core.scenarios._period_aggregators import VectorAggregator
from gaspatchio_core.scenarios._sketch import SignedSketch


def build_period_sketches(
    frame: pl.DataFrame, period: str, column: str, *, relative_accuracy: float
) -> list[SignedSketch]:
    """One :class:`SignedSketch` per period, built via a vectorized histogram.

    The DDSketch bin key is reproduced in Polars from ``gamma``; a real per-bin
    representative value (``first(|v|)``) is fed to ``from_binned`` so the
    library's own mapping assigns the bucket. Validated against per-value adds by
    the dual-build gate (Task 1 + the run_aggregated gate in Task 5).

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
    gamma = (1.0 + relative_accuracy) / (1.0 - relative_accuracy)
    inv_log_gamma = 1.0 / math.log(gamma)
    exploded = (
        frame.lazy().select(pl.col(period), pl.col(column)).explode([period, column])
    )

    zeros = (
        exploded.filter(pl.col(column) == 0)
        .group_by(period)
        .agg(pl.len().alias("z"))
        .collect()
    )
    binned = (
        exploded.filter(pl.col(column) != 0)
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
    for row in zeros.iter_rows(named=True):
        zero_n[row[period]] = row["z"]
    for row in binned.iter_rows(named=True):
        t = row[period]
        entry = (float(row["__rep"]), int(row["__cnt"]))
        (pos if row["__sign"] == 1 else neg)[t].append(entry)

    return [
        SignedSketch.from_binned(
            pos=pos[t],
            neg=neg[t],
            zero_n=zero_n[t],
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

    def add_input(self, state: Any, value: Any) -> Any:  # noqa: ANN401
        return _merge_sketch_lists(state, value, self.relative_accuracy)

    def merge_accumulators(self, a: Any, b: Any) -> Any:  # noqa: ANN401
        return _merge_sketch_lists(a, b, self.relative_accuracy)


@scenario_aggregator("PeriodQuantile")
@dataclass(frozen=True)
class PeriodQuantile(_PeriodSketchAgg):
    """Per-period quantile(s) across the batched axis (DDSketch-backed)."""

    levels: tuple[float, ...] = (0.5,)

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return {
            level: np.array([sk.quantile(level) for sk in state], dtype=np.float64)
            for level in self.levels
        }

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "PeriodQuantile",
            "column": self.column,
            "levels": list(self.levels),
            "relative_accuracy": self.relative_accuracy,
        }


@scenario_aggregator("PeriodMedian")
@dataclass(frozen=True)
class PeriodMedian(_PeriodSketchAgg):
    """Per-period median across the batched axis."""

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return np.array([sk.quantile(0.5) for sk in state], dtype=np.float64)

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "PeriodMedian",
            "column": self.column,
            "relative_accuracy": self.relative_accuracy,
        }


@scenario_aggregator("PeriodCTE")
@dataclass(frozen=True)
class PeriodCTE(_PeriodSketchAgg):
    """Per-period Conditional Tail Expectation across the batched axis."""

    level: float = 0.005
    direction: Literal["upper", "lower"] = "upper"

    def extract_output(self, state: Any) -> Any:  # noqa: ANN401
        return np.array(
            [sk.cte(level=self.level, direction=self.direction) for sk in state],
            dtype=np.float64,
        )

    def canonical_form(self) -> dict[str, Any]:
        return {
            "kind": "PeriodCTE",
            "column": self.column,
            "level": self.level,
            "direction": self.direction,
            "relative_accuracy": self.relative_accuracy,
        }


__all__ = [
    "PeriodCTE",
    "PeriodMedian",
    "PeriodQuantile",
    "build_period_sketches",
    "build_period_sketches_over",
]
