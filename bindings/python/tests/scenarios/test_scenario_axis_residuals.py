# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: F9 residuals — sketch Period* and partitioned Period* on the
# ABOUTME: scenario axis reduce ACROSS scenarios; .of() rejects non-additive.

"""Scenario-axis residuals of the F9 cluster.

The shipped F9a fix made non-partitioned closed-form ``Period*`` aggregators
reduce ACROSS scenarios of each scenario's per-period portfolio total. This
suite covers the remaining paths:

- sketch-backed ``PeriodMedian``/``PeriodQuantile``/``PeriodCTE`` (previously
  a bare NotImplementedError at the first batch fold),
- partitioned ``Period*.over(dim)`` (previously reduced over policy x
  scenario cells — the factor-P error),
- ``.over("scenario_id")`` keeps per-scenario/across-policy semantics,
- ``run_aggregated`` rejects non-additive aggregators combined with ``.of()``
  (previously silently batch-count-dependent).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.scenarios import (
    Mean,
    PeriodCTE,
    PeriodMean,
    PeriodMedian,
    PeriodQuantile,
    Sum,
    for_each_scenario,
    run_aggregated,
)
from gaspatchio_core.scenarios._period_sketch import build_period_sketches


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


def _base_af() -> ActuarialFrame:
    """4 policies; per-scenario portfolio totals are [10*sid, 20*sid]."""
    return ActuarialFrame(
        {"value": [1.0, 2.0, 3.0, 4.0], "product": ["A", "A", "B", "B"]}
    )


# ---------------------------------------------------------------------------
# Sketch Period* on the scenario axis (two-stage)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("batch_size", [1, 3])
def test_period_median_reduces_across_scenarios(batch_size: int) -> None:
    """Median across per-scenario portfolio totals: [10,20,30] and [20,40,60]."""
    result = for_each_scenario(
        _base_af(),
        [1, 2, 3],
        model_fn=_period_scenario_model,
        aggregations=[PeriodMedian("cf").alias("med")],
        batch_size=batch_size,
    )
    med = np.asarray(result.aggregations["med"])
    assert med == pytest.approx([20.0, 40.0], rel=1e-3)


def test_period_quantile_and_cte_match_direct_sketch_of_totals() -> None:
    """Quantile/CTE via for_each equal the same sketch fed per-scenario totals.

    Uses the sketch machinery itself on hand-built per-scenario totals as the
    reference, so this pins the two-stage ROUTING (not the sketch math): six
    scenarios give totals 10*sid per period 0 and 20*sid per period 1.
    """
    scenarios = [1, 2, 3, 4, 5, 6]
    result = for_each_scenario(
        _base_af(),
        scenarios,
        model_fn=_period_scenario_model,
        aggregations=[
            PeriodQuantile("cf", levels=(0.5, 0.9)).alias("q"),
            PeriodCTE("cf", level=0.4, direction="upper").alias("cte"),
        ],
        batch_size=2,
    )

    totals = pl.DataFrame(
        {
            "cf": [[10.0 * s, 20.0 * s] for s in scenarios],
        }
    ).with_columns(pl.int_ranges(pl.col("cf").list.len()).alias("__p"))
    ref_sketches = build_period_sketches(
        totals, "__p", "cf", relative_accuracy=1e-4
    )

    q = result.aggregations["q"]
    for level in (0.5, 0.9):
        expected = [sk.quantile(level) for sk in ref_sketches]
        assert np.asarray(q[level]) == pytest.approx(expected, rel=1e-9)

    expected_cte = [sk.cte(level=0.4, direction="upper") for sk in ref_sketches]
    assert np.asarray(result.aggregations["cte"]) == pytest.approx(
        expected_cte, rel=1e-9
    )


def test_sketch_fold_is_batch_invariant() -> None:
    """Same PeriodMedian result whether scenarios run in 1 batch or 3."""
    runs = {
        bs: for_each_scenario(
            _base_af(),
            [1, 2, 3, 4, 5, 6],
            model_fn=_period_scenario_model,
            aggregations=[PeriodMedian("cf").alias("med")],
            batch_size=bs,
        )
        for bs in (2, 6)
    }
    a = np.asarray(runs[2].aggregations["med"])
    b = np.asarray(runs[6].aggregations["med"])
    assert a == pytest.approx(b, rel=1e-12)


# ---------------------------------------------------------------------------
# Partitioned Period*.over(dim) on the scenario axis (two-stage per partition)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("batch_size", [1, 3])
@pytest.mark.parametrize(
    ("agg", "expected"),
    [
        (PeriodMean("cf"), {"A": [6.0, 12.0], "B": [14.0, 28.0]}),
        (PeriodMedian("cf"), {"A": [6.0, 12.0], "B": [14.0, 28.0]}),
    ],
    ids=["mean", "median"],
)
def test_partitioned_period_reduces_across_scenarios(
    agg: object, expected: dict[str, list[float]], batch_size: int
) -> None:
    """Per (product, period): statistic ACROSS scenarios of per-scenario sums.

    Product A sums to 3*sid per period 0 (values 1+2), so across scenarios
    {1,2,3} the mean/median is 6; product B sums to 7*sid, giving 14.
    Policy x scenario cell semantics (the old bug) would give A a period-0
    mean of 2 (six cells {1,2,2,4,3,6}, mean 3) — distinguishable.
    """
    result = for_each_scenario(
        _base_af(),
        [1, 2, 3],
        model_fn=_period_scenario_model,
        aggregations=[agg.alias("stat").over("product")],
        batch_size=batch_size,
    )
    tidy = result.aggregations["stat"].sort(["product", "period"])
    for product, per_period in expected.items():
        rows = tidy.filter(pl.col("product") == product).sort("period")
        assert rows["stat"].to_list() == pytest.approx(per_period, rel=1e-3), product


def test_over_scenario_id_keeps_policy_cell_semantics() -> None:
    """.over("scenario_id") means per-scenario stats ACROSS POLICIES — unchanged.

    Mean of value*sid over policies {1,2,3,4} is 2.5*sid per period 0.
    """
    result = for_each_scenario(
        _base_af(),
        [1, 2],
        model_fn=_period_scenario_model,
        aggregations=[PeriodMean("cf").alias("m").over("scenario_id")],
        batch_size=1,
    )
    tidy = result.aggregations["m"].sort(["scenario_id", "period"])
    s1 = tidy.filter(pl.col("scenario_id") == 1).sort("period")
    s2 = tidy.filter(pl.col("scenario_id") == 2).sort("period")
    assert s1["m"].to_list() == pytest.approx([2.5, 5.0])
    assert s2["m"].to_list() == pytest.approx([5.0, 10.0])


# ---------------------------------------------------------------------------
# run_aggregated: .of() with non-additive aggregators is rejected
# ---------------------------------------------------------------------------


def _policy_model(af: ActuarialFrame) -> ActuarialFrame:
    return af.with_columns(pl.col("value").alias("x"))


@pytest.mark.parametrize(
    "agg",
    [
        Mean.of(pl.col("x").sum()),
        Sum.of(pl.col("x").mean()),
    ],
    ids=["mean-of-sum", "sum-of-mean"],
)
def test_of_rejected_on_policy_axis(agg: object) -> None:
    """.of() on run_aggregated is batch-size-dependent for ANY outer aggregator.

    No allowlist is sound: invariance would require the within-expression to
    be decomposable w.r.t. the outer fold (Min.of(col.sum()) and
    Sum.of(col.mean()) are both silently batch-dependent), which cannot be
    verified on an arbitrary Polars expression. The scenario axis
    (for_each_scenario) keeps .of() — each scenario is reduced whole there.
    """
    mp = pl.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]})
    with pytest.raises(ValueError, match="of\\(.*policy axis|not supported"):
        run_aggregated(
            _policy_model,
            mp,
            [agg.alias("m")],
        )
