# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201
"""Stochastic VA showcase: N scenarios -> distribution + CTE + percentile fan.

Emits DATA ONLY (scenario_showcase.json). Rendering is a separate step
(render_scenario_showcase.py) so the same data feeds both perf pages and docs.

Illustrative on tutorial data; not a certified reserve. CTE70 mirrors the
VM-21 statutory method; CTE95 mirrors the economic-capital tail.
"""

from __future__ import annotations

import sys
from pathlib import Path

# repo root, for evals.benchmarks.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json

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

N_SCENARIOS = 1_000
N_FAN = 100  # scenarios re-run with full grid retained for the per-month fan
OUT = Path(__file__).resolve().parent / "scenario_showcase.json"

_FAN_PCTS = [(0.05, "p05"), (0.25, "p25"), (0.5, "p50"), (0.75, "p75"), (0.95, "p95")]


def _fan_series(l5, mp: pl.DataFrame, returns: pl.DataFrame, n_fan: int) -> dict:
    """Per-month percentiles (5/25/50/75/95) of portfolio net_cf across scenarios.

    FOLLOW-UP (investigate — possible non-idiomatic pattern): this drops the
    per-policy list columns to long format via ``explode(["month", "net_cf"])``
    then ``group_by`` + ``quantile``. ``explode`` + ``group_by`` IS the documented
    Phase-4 fund-aggregation pattern (skills/model-building/references/
    aggregate-patterns.md), so it is not categorically wrong. BUT in the *scenario*
    context, exploding the scenarios x policies x months grid to long format is
    exactly what the bounded-memory ``for_each_scenario`` loop avoids elsewhere —
    so a more "gaspatchio" route likely exists: either the scenario Aggregator
    framework (``Quantile(...).over(...)`` partitioned per projection period) or a
    list-native portfolio sum (element-wise sum of the ``net_cf`` lists across
    policies within a scenario, then per-month cross-scenario percentiles) that
    stays in the list-column world. Bounded here by ``n_fan`` (subset), so it is
    safe at this scale. See ref/42-scenario-auto-sizing/FOLLOWUPS.md.
    """
    df = l5.main(
        with_scenarios(ActuarialFrame(mp), list(range(1, n_fan + 1))),
        scenario_returns_override=returns,
    ).collect()
    port = (
        df.select("scenario_id", "month", "net_cf")
        .explode(["month", "net_cf"])
        .group_by("scenario_id", "month")
        .agg(pl.col("net_cf").sum().alias("p"))
    )
    pct = (
        port.group_by("month")
        .agg([pl.col("p").quantile(q).alias(name) for q, name in _FAN_PCTS])
        .sort("month")
    )
    return pct.to_dict(as_series=False)


def main(n_scenarios: int = N_SCENARIOS) -> None:
    """Run the stochastic showcase and write scenario_showcase.json (data only)."""
    l5 = load_l5_model()
    mp = pl.read_parquet(L5_DIR / "model_points_1k.parquet")
    returns = generate_stochastic_returns(n_scenarios, n_months=180, seed=12345)

    # Panel A: per-scenario portfolio totals via the auto loop (the distribution).
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, n_scenarios + 1)),
        model_fn=make_stochastic_model_fn(l5, returns),
        aggregations=(Sum("pv_net_cf").alias("dist").over("scenario_id"),),
        batch_size="auto",
    )
    totals = np.array(result.aggregations["dist"].sort("scenario_id")["dist"].to_list())
    loss = -totals  # insurer loss
    cte70 = portfolio_cte(loss, 0.70)
    cte95 = portfolio_cte(loss, 0.95)

    # Panel B: per-month cross-scenario percentile fan (smaller subset, full grid).
    fan = _fan_series(l5, mp, returns, n_fan=min(n_scenarios, N_FAN))

    OUT.write_text(json.dumps({
        "meta": {"n_scenarios": n_scenarios, "n_points": mp.height,
                 "n_fan": min(n_scenarios, N_FAN),
                 "batch_size": int(result.batch_size),
                 "batch_size_resolution": str(result.batch_size_resolution),
                 "wall_s": round(float(result.wall_time_s), 3)},
        "distribution": {"per_scenario_loss": loss.tolist(),
                         "cte70": cte70, "cte95": cte95},
        "fan": fan,
    }, indent=2))
    print(f"Wrote {OUT}: {n_scenarios}-scenario CTE70={cte70:,.0f} CTE95={cte95:,.0f}")


if __name__ == "__main__":
    main()
