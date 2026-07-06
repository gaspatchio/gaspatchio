# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for the for_each_scenario bounded-memory loop primitive.
# ABOUTME: Phase 1 covers the list[ScenarioID] shape only (no shocks / drivers).
"""Test for_each_scenario core loop (Phase 1: list[ID] shape)."""

from __future__ import annotations

import warnings

import numpy as np
import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    Mean,
    PeriodCount,
    PeriodMax,
    PeriodMean,
    PeriodMin,
    PeriodStd,
    PeriodSum,
    PeriodVariance,
    Sum,
    for_each_scenario,
)


@pytest.fixture
def af() -> ActuarialFrame:
    """Three-policy ActuarialFrame used across the suite."""
    return ActuarialFrame({"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]})


def _identity_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Add a ``value`` column equal to ``premium`` (per-scenario, identical)."""
    return af.with_columns(pl.col("premium").alias("value"))


def test_list_of_ids_sum_one_batch(af: ActuarialFrame) -> None:
    """Sum aggregator over per-scenario sums: 3 scenarios x 600 = 1800."""
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C"],
        model_fn=_identity_model,
        aggregations=(Sum("value").alias("total"),),
        batch_size=1,
    )
    assert result.aggregations["total"] == pytest.approx(1800.0)
    assert result.n_scenarios == 3
    assert result.batch_size == 1
    assert result.batch_size_resolution == "manual"


def test_list_of_ids_batched(af: ActuarialFrame) -> None:
    """Mean aggregator with batch_size=2 over 5 scenarios stays bit-equivalent."""
    result = for_each_scenario(
        af,
        scenarios=["A", "B", "C", "D", "E"],
        model_fn=_identity_model,
        aggregations=(Mean("value").alias("avg"),),
        batch_size=2,
    )
    assert result.aggregations["avg"] == pytest.approx(600.0)
    assert result.batch_size == 2


def test_empty_scenarios_raises(af: ActuarialFrame) -> None:
    """Empty scenario list is rejected with the shared validator message."""
    with pytest.raises(ValueError, match="at least one"):
        for_each_scenario(
            af,
            scenarios=[],
            model_fn=_identity_model,
            aggregations=(Sum("value").alias("total"),),
        )


def test_auto_search_does_not_warn(af: ActuarialFrame) -> None:
    """The measured streaming-batch search resolves silently (no spurious warnings)."""
    scenarios = [f"S{i}" for i in range(8)]
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # any UserWarning would fail
        result = for_each_scenario(
            af,
            scenarios=scenarios,
            model_fn=_identity_model,
            aggregations=(Sum("value").alias("total"),),
            batch_size="auto",
        )
    assert result.batch_size_resolution == "auto_search"


def test_fold_batch_helper_exists() -> None:
    from gaspatchio_core.scenarios import _for_each

    assert hasattr(_for_each, "_fold_batch")


# ---------------------------------------------------------------------------
# F9a: Period* aggregators reduce ACROSS scenarios per period (two-stage),
#      not over policy x scenario cells. Full hand-computed derivation lives in
#      the docstring of test_period_reduces_across_scenarios_per_period below.
# ---------------------------------------------------------------------------

_F9A_EXPECTED: dict[str, list[float]] = {
    "sum": [60.0, 120.0],  # control (additive; unchanged by the bug)
    "mean": [20.0, 40.0],
    "count": [3.0, 3.0],
    "min": [10.0, 20.0],
    "max": [30.0, 60.0],
    "var": [100.0, 400.0],
    "std": [10.0, 20.0],
}


def _period_scenario_model(
    af: ActuarialFrame,
    *,
    tables: dict | None = None,  # noqa: ARG001
    drivers: dict | None = None,  # noqa: ARG001
) -> ActuarialFrame:
    """Per-scenario cf = [value*sid, value*sid*2] (reads the scenario_id column)."""
    return af.with_columns(
        pl.concat_list(
            [
                pl.col("value") * pl.col("scenario_id"),
                pl.col("value") * pl.col("scenario_id") * 2,
            ]
        ).alias("cf")
    )


def _run_f9a(batch_size: int) -> dict[str, list[float]]:
    base = ActuarialFrame({"value": [1.0, 2.0, 3.0, 4.0]})  # 4 policies
    result = for_each_scenario(
        base,
        [1, 2, 3],  # 3 scenarios
        model_fn=_period_scenario_model,
        aggregations=[
            PeriodSum("cf").alias("sum"),
            PeriodMean("cf").alias("mean"),
            PeriodCount("cf").alias("count"),
            PeriodMin("cf").alias("min"),
            PeriodMax("cf").alias("max"),
            PeriodVariance("cf").alias("var"),
            PeriodStd("cf").alias("std"),
        ],
        batch_size=batch_size,
    )
    return {k: np.asarray(v).tolist() for k, v in result.aggregations.items()}


@pytest.mark.parametrize("batch_size", [1, 3])
@pytest.mark.parametrize("alias", list(_F9A_EXPECTED))
def test_period_reduces_across_scenarios_per_period(
    alias: str, batch_size: int
) -> None:
    """Each Period* aggregator computes its statistic ACROSS scenarios per period.

    Hand-computed reference (4 policies x 3 scenarios x 2 periods). The model sets
    cf = [value*sid, value*sid*2]; value = [1,2,3,4] so sum(value) = 10; sid in
    {1,2,3}.

    Stage 1 (WITHIN each scenario, sum across the 4 policies per period) gives each
    scenario's per-period total T[sid] = (sid*10, sid*20):
        sid=1 -> (10, 20), sid=2 -> (20, 40), sid=3 -> (30, 60).

    Stage 2 (the statistic ACROSS the 3 scenario totals, per period):
        sum   -> (10+20+30, 20+40+60)          = (60, 120)  [additive control]
        mean  -> (60/3, 120/3)                 = (20, 40)
        count -> (3 scenarios, 3)              = (3, 3)
        min   -> (min(10,20,30), min(20,40,60))= (10, 20)
        max   -> (max(10,20,30), max(20,40,60))= (30, 60)
        var   -> (var([10,20,30]), var([20,40,60]), ddof=1) = (100, 400)
        std   -> (sqrt(100), sqrt(400))        = (10, 20)

    The pre-fix code reduced over all 4x3=12 policy x scenario cells, giving
    count=(12,12) and mean=(5,10) (off by the policy count P=4); sum is additive
    and stays (60,120), so it is the control.

    batch_size=1 folds one scenario per batch (proves cross-batch composition);
    batch_size=3 folds all scenarios in a single batch. Both must match.
    """
    got = _run_f9a(batch_size)[alias]
    assert got == pytest.approx(_F9A_EXPECTED[alias]), (
        f"{alias}: got {got}, want {_F9A_EXPECTED[alias]}"
    )


def test_period_count_is_num_scenarios_not_cells() -> None:
    """Regression guard: PeriodCount is the scenario count (3), not P*S (12)."""
    got = _run_f9a(batch_size=1)["count"]
    assert got == [3.0, 3.0]  # NOT [12.0, 12.0]


def test_period_mean_is_mean_of_scenario_totals_not_cells() -> None:
    """Regression guard: PeriodMean means per-scenario totals, not cell values."""
    got = _run_f9a(batch_size=1)["mean"]
    assert got == pytest.approx([20.0, 40.0])  # NOT [5.0, 10.0]
