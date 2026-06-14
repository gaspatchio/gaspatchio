# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""Showcase aggregation correctness vs a numpy reference."""

from __future__ import annotations

import numpy as np
import polars as pl
from evals.benchmarks.scenario_lib import (
    L5_DIR,
    generate_stochastic_returns,
    load_l5_model,
    make_stochastic_model_fn,
    portfolio_cte,
)

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario, with_scenarios

N = 20


def _reference_totals() -> list[float]:
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(N, n_months=180, seed=555)
    df = l5.main(
        with_scenarios(ActuarialFrame(mp), list(range(1, N + 1))),
        scenario_returns_override=returns,
    ).collect()
    return (
        df.group_by("scenario_id")
        .agg(pl.col("pv_net_cf").sum().alias("t"))
        .sort("scenario_id")["t"]
        .to_list()
    )


def test_portfolio_cte_formula() -> None:
    """CTE_p = mean of losses >= the p-quantile of losses (TVaR)."""
    losses = np.arange(1.0, 11.0)  # 1..10
    # 70th pct (linear) = 7.3 -> losses >= 7.3 -> {8,9,10} -> mean 9.0
    assert portfolio_cte(losses, 0.70) == 9.0
    # 95th pct = 9.55 -> {10} -> mean 10.0
    assert portfolio_cte(losses, 0.95) == 10.0


def test_distribution_matches_numpy_reference() -> None:
    """for_each_scenario(auto) per-scenario totals reproduce the manual reference."""
    ref = np.array(_reference_totals())
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points.parquet")
    returns = generate_stochastic_returns(N, n_months=180, seed=555)
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, N + 1)),
        model_fn=make_stochastic_model_fn(l5, returns),
        aggregations=(Sum("pv_net_cf").alias("dist").over("scenario_id"),),
        batch_size="auto",
    )
    got = np.array(result.aggregations["dist"].sort("scenario_id")["dist"].to_list())
    assert np.allclose(got, ref, rtol=1e-6, atol=1e-6)
    # CTE on the loss tail is finite and ordered (CTE95 >= CTE70 for losses).
    loss = -ref
    assert np.isfinite(portfolio_cte(loss, 0.70))
    assert portfolio_cte(loss, 0.95) >= portfolio_cte(loss, 0.70)
