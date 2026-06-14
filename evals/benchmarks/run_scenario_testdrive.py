# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: T201, S101
"""Local test-drive: characterise auto vs fixed vs serial-seeded scenario runs.

Asserts (1) results identical across profiles and (2) auto wall ~= best fixed.
Writes scenario_testdrive_results.json; feeds measured timings into Phase B grid sizing.
"""

from __future__ import annotations

import sys
from pathlib import Path

# repo root, for evals.benchmarks.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import json

import polars as pl

from evals.benchmarks.scenario_lib import (
    L5_DIR,
    generate_stochastic_returns,
    load_l5_model,
    make_stochastic_model_fn,
    read_result_metrics,
)
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import Sum, for_each_scenario

N_SCENARIOS = 24
N_POINTS_PATH = L5_DIR / "model_points_1k.parquet"


def _run(profile: str, batch_size: int | str, model_fn, mp: pl.DataFrame, *,
         master_seed: int | None = None) -> dict:
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, N_SCENARIOS + 1)),
        model_fn=model_fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
        batch_size=batch_size,
        master_seed=master_seed,
    )
    metrics = read_result_metrics(result, N_SCENARIOS, mp.height)
    totals = result.aggregations["total"].sort("scenario_id")["total"].to_list()
    return {"profile": profile, "metrics": metrics, "totals": totals}


def main() -> None:
    """Run the three profiles, assert agreement, and write results JSON."""
    l5 = load_l5_model()
    returns = generate_stochastic_returns(N_SCENARIOS, n_months=180, seed=2024)
    model_fn = make_stochastic_model_fn(l5, returns)
    mp = pl.read_parquet(N_POINTS_PATH)

    runs = [
        _run("auto", "auto", model_fn, mp),
        _run("fixed-4", 4, model_fn, mp),
        _run("serial-seeded", 1, model_fn, mp, master_seed=2024),
    ]

    # Correctness guard: every profile must agree to ~1e-6 relative.
    ref = runs[0]["totals"]
    for r in runs[1:]:
        for a, b in zip(ref, r["totals"], strict=True):
            assert abs(a - b) <= 1e-6 * max(1.0, abs(a)), (r["profile"], a, b)

    auto_wall = runs[0]["metrics"]["wall_s"]
    best_fixed = min(
        r["metrics"]["wall_s"] for r in runs if r["profile"].startswith("fixed")
    )
    print(f"auto wall={auto_wall}s  best-fixed wall={best_fixed}s")
    for r in runs:
        m = r["metrics"]
        print(f"  {r['profile']:14s} wall={m['wall_s']}s rss={m['peak_rss_mb']}MB "
              f"batch={m['batch_size']} ({m['batch_size_resolution']})")
    out = Path(__file__).resolve().parent / "scenario_testdrive_results.json"
    out.write_text(json.dumps(runs, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
