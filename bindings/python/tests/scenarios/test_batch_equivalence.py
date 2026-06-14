# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Locks the GSP-100 acceptance criterion: batch-size invariance.
# ABOUTME: Same plan run at batch_size=1 and >1 must produce equal output.
"""All v0.2 aggregators must be batch-equivalent across batch_size in {1, 4, 8}."""

from __future__ import annotations

import math
from typing import Any

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    CTE,
    ArgMax,
    ArgMin,
    Count,
    Max,
    Mean,
    Median,
    Min,
    Quantile,
    QuantileRank,
    Std,
    Sum,
    Variance,
    for_each_scenario,
)


@pytest.fixture
def af() -> ActuarialFrame:
    """Eight-policy frame; per-scenario sum varies enough to exercise reducers."""
    return ActuarialFrame({
        "policy_id": list(range(1, 9)),
        "premium": [100.0, 200.0, 150.0, 250.0, 300.0, 175.0, 225.0, 350.0],
    })


def _model_fn(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    return af.with_columns(pl.col("premium").alias("value"))


# Scalar-valued aggregators: (alias, instance, abs_tolerance).
# Tolerance 0 means bit-exact across all batch sizes; >0 means math.isclose(abs_tol=tol).
# Quantile returns dict[float, float] - tested separately below.
#
# Bit-exact across batch_size:
#   Sum:           Neumaier-compensated summation (value-magnitude-symmetric).
#   Count:         integer addition (exact).
#   Min/Max:       pick semantics (exact).
#   ArgMin/ArgMax: pick semantics carrying scenario_id (exact).
#   Median/CTE/Quantile/QuantileRank: DDSketch is integer-bucket counts;
#     bucket merge is commutative integer addition; final quantile is a
#     deterministic interpolation off bucket boundaries.
#
# Numerically stable but NOT bit-exact across batch_size:
#   Mean/Variance/Std: Welford-Chan. The merge formula divides by n_total,
#     which rounds differently when (n_a, n_b) split differently across
#     batches. Drift is O(eps * log N) -- well below any actuarially
#     meaningful threshold but not zero. Documented in
#     concepts/scenarios/performance.md.
SCALAR_AGGREGATORS: list[tuple[str, Any, float]] = [
    ("sum", Sum("value").alias("sum"), 0.0),
    ("count", Count("value").alias("count"), 0.0),
    ("min", Min("value").alias("min"), 0.0),
    ("max", Max("value").alias("max"), 0.0),
    # Welford-Chan: stable but not bit-exact. Tolerances are calibrated to the
    # fixture scale below (values ~100-350, mean ~225, variance ~6000).
    ("mean", Mean("value").alias("mean"), 1e-10),
    ("variance", Variance("value").alias("variance"), 1e-8),
    ("std", Std("value").alias("std"), 1e-9),
    # DDSketch-backed: bucket counts are integer-exact; the only fuzz is the
    # sketch's relative_accuracy=1e-4 (~5 units at the fixture scale, but
    # cross-batch_size drift inside the sketch is zero).
    ("median", Median("value").alias("median"), 0.0),
    ("cte", CTE("value", level=0.01, direction="upper").alias("cte"), 0.0),
    ("quantile_rank", QuantileRank("value", at=200.0).alias("quantile_rank"), 0.0),
    ("argmin", ArgMin("value").alias("argmin"), 0.0),
    ("argmax", ArgMax("value").alias("argmax"), 0.0),
]

# Batch sizes that exercise both small (within-batch growth) and large
# (cross-batch merge) reduction paths. With 64 scenarios, bs=1 yields 64
# batches and bs=64 yields a single batch -- every value of bs in between
# changes the merge tree shape.
BATCH_SIZES_TO_CHECK = (1, 2, 4, 16, 64)


@pytest.mark.parametrize(
    ("alias", "agg", "tol"),
    SCALAR_AGGREGATORS,
    ids=[a[0] for a in SCALAR_AGGREGATORS],
)
def test_scalar_batch_equivalence(
    af: ActuarialFrame,
    alias: str,
    agg: Any,  # noqa: ANN401
    tol: float,
) -> None:
    """Each scalar aggregator must yield equal results across batch sizes."""
    scenarios = [f"S{i:03d}" for i in range(64)]
    results: dict[int, Any] = {}
    for batch_size in BATCH_SIZES_TO_CHECK:
        r = for_each_scenario(
            af,
            scenarios=scenarios,
            model_fn=_model_fn,
            aggregations=(agg,),
            batch_size=batch_size,
        )
        results[batch_size] = r.aggregations[alias]

    base = results[1]
    for bs in BATCH_SIZES_TO_CHECK[1:]:
        other = results[bs]
        if isinstance(base, (int, float)) and isinstance(other, (int, float)):
            if tol == 0:
                assert other == base, (
                    f"{alias} drifted: batch_size=1 -> {base!r}, "
                    f"batch_size={bs} -> {other!r}"
                )
            else:
                assert math.isclose(other, base, abs_tol=tol), (
                    f"{alias} drifted beyond tol={tol}: "
                    f"batch_size=1 -> {base!r}, batch_size={bs} -> {other!r}"
                )
        else:
            assert other == base, f"{alias} mismatch: {base!r} vs {other!r}"


def test_quantile_batch_equivalence(af: ActuarialFrame) -> None:
    """Quantile (dict output) must be bit-exact across batch sizes.

    DDSketch buckets are integer-counter dicts -- their merge is commutative
    addition with no rounding. The quantile lookup at the end is a
    deterministic walk over bucket boundaries. So unlike Welford, this is
    bit-exact across batch_size, not just numerically stable.
    """
    scenarios = [f"S{i:03d}" for i in range(64)]
    agg = Quantile("value", levels=(0.25, 0.50, 0.75, 0.95)).alias("q")
    results: dict[int, dict[float, float]] = {}
    for batch_size in BATCH_SIZES_TO_CHECK:
        r = for_each_scenario(
            af,
            scenarios=scenarios,
            model_fn=_model_fn,
            aggregations=(agg,),
            batch_size=batch_size,
        )
        results[batch_size] = r.aggregations["q"]

    base = results[1]
    for bs in BATCH_SIZES_TO_CHECK[1:]:
        other = results[bs]
        for level, base_val in base.items():
            assert other[level] == base_val, (
                f"Quantile[{level}] drifted: batch_size=1 -> {base_val!r}, "
                f"batch_size={bs} -> {other[level]!r}"
            )


def test_sum_neumaier_adversarial_input() -> None:
    """Sum with magnitude-mixed inputs holds precision where naive folding fails.

    Classic Kahan-Neumaier benchmark: feeding [1e20, 1.0, -1e20, 1.0] in order
    through a plain ``s = s + x`` accumulator loses the small terms entirely
    (result: 0.0). Neumaier-compensated summation recovers them (result: 2.0).
    """
    agg = Sum("value").alias("s")
    state = agg.create_accumulator()
    for x in (1e20, 1.0, -1e20, 1.0):
        state = agg.add_input(state, x)
    assert agg.extract_output(state) == 2.0


def test_sum_neumaier_merge_adversarial() -> None:
    """Compensation must survive cross-batch merge, not just within-batch adds."""
    agg = Sum("value").alias("s")
    # Two partial states, each one contributing a magnitude-mixed pair.
    left = agg.create_accumulator()
    left = agg.add_input(left, 1e20)
    left = agg.add_input(left, 1.0)
    right = agg.create_accumulator()
    right = agg.add_input(right, -1e20)
    right = agg.add_input(right, 1.0)
    merged = agg.merge_accumulators(left, right)
    assert agg.extract_output(merged) == 2.0


def test_sum_batch_equivalence_at_cashflow_scale() -> None:
    """Realistic-scale Sum stress: drift was ~1 ULP @ ~1e8 in the prior demo.

    Constructs a per-scenario cashflow at actuarial scale (~1e7 each, 50
    scenarios -> sum ~5e8) and asserts bit-identical result across
    batch_sizes -- the regression that motivated this work.
    """
    af = ActuarialFrame({
        "policy_id": list(range(1, 21)),
        "premium": [float(1_000_000 + i * 137.91) for i in range(20)],
    })
    scenarios = [f"S{i:03d}" for i in range(50)]
    agg = Sum("value").alias("pv")
    results: dict[int, float] = {}
    for batch_size in (1, 2, 4, 16):
        r = for_each_scenario(
            af,
            scenarios=scenarios,
            model_fn=_model_fn,
            aggregations=(agg,),
            batch_size=batch_size,
        )
        results[batch_size] = r.aggregations["pv"]
    base = results[1]
    for bs in (2, 4, 16):
        assert results[bs] == base, (
            f"Sum drifted at cashflow scale: bs=1 -> {base!r}, "
            f"bs={bs} -> {results[bs]!r} (delta = {results[bs] - base})"
        )


def test_partitioned_batch_equivalence(af: ActuarialFrame) -> None:
    """Partitioned aggregators must also be batch-invariant."""

    def lob_model(
        af: ActuarialFrame,
        *,
        tables: dict | None = None,  # noqa: ARG001
        drivers: dict | None = None,  # noqa: ARG001
    ) -> ActuarialFrame:
        return af.with_columns(
            pl.when(pl.col("policy_id") % 2 == 0)
            .then(pl.lit("home"))
            .otherwise(pl.lit("motor"))
            .alias("lob"),
            pl.col("premium").alias("value"),
        )

    plan = (Sum("value").alias("by_lob").over("lob"),)
    scenarios = [f"S{i}" for i in range(1, 9)]
    results: dict[int, pl.DataFrame] = {}
    for batch_size in (1, 4):
        r = for_each_scenario(
            af,
            scenarios=scenarios,
            model_fn=lob_model,
            aggregations=plan,
            batch_size=batch_size,
        )
        results[batch_size] = r.aggregations["by_lob"].sort("lob")

    assert results[1].equals(results[4]), (
        f"Partitioned aggregator output drifted:\n"
        f"batch_size=1:\n{results[1]}\n"
        f"batch_size=4:\n{results[4]}"
    )
