# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# 100K-policy scaling probe (ref/42). Question: at 100K model points (where Point A is
# infeasible and the design runs Point B = batch_size=1 streamed), is B's per-scenario wall
# FLAT across scenario count, or does it CLIMB with N (as it did at 1K policies: 0.08 -> 0.11
# -> 0.51 s as N went 10 -> 100 -> 1000)? The answer firms up the 1K/10K-scenario time estimate.
#
# Point B only (A refuses at 100K). Sequential (timing integrity). Captures per-pass walls via
# on_batch to separate within-run flatness from the between-N level.
#
# Run:
#   cd bindings/python
#   uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/probe_100k_scaling.py
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))

import polars as pl  # noqa: E402
from scenario_lib import generate_stochastic_returns, load_l5_model  # noqa: E402

import gaspatchio_core.scenarios._for_each as fe  # noqa: E402
from gaspatchio_core import ActuarialFrame  # noqa: E402
from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "probe_100k_results.jsonl"
RESULTS.unlink(missing_ok=True)

_L5 = load_l5_model()
_ORIG_CWP = fe._collect_with_peak

# A2_base archetype (the measured 100K cell): 82mo projection, 180mo returns table.
PROJECTION_MONTHS = 82
N_MONTHS = 180
POINTS = ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet"
N_VALUES = [10, 30, 100]


def patched(lazy, *, engine="streaming", _o=_ORIG_CWP):  # noqa: ANN001, ANN202
    return _o(lazy, engine=engine)


class PerPass:
    def __init__(self) -> None:
        self.t_prev: float | None = None
        self.walls: list[float] = []
        self.peaks: list[float | None] = []

    def start(self) -> None:
        self.t_prev = time.perf_counter()

    def __call__(self, snap) -> None:  # noqa: ANN001
        now = time.perf_counter()
        if self.t_prev is not None:
            self.walls.append(now - self.t_prev)
            self.peaks.append(snap.peak_rss_mb)
        self.t_prev = now


def log(m: str) -> None:
    print(m, flush=True)


mp = pl.read_parquet(POINTS).head(100_000)
log(f"100K scaling probe: {mp.height} policies, Point B (b=1 streamed), N in {N_VALUES}")

for n_scen in N_VALUES:
    returns = generate_stochastic_returns(n_scen, n_months=N_MONTHS, seed=12345)

    def fn(af, *, tables=None, drivers=None, _r=returns):  # noqa: ANN001, ANN202, ARG001
        return _L5.main(af, scenario_returns_override=_r, projection_months=PROJECTION_MONTHS)

    timer = PerPass()
    fe._collect_with_peak = patched
    gc.collect()
    t = time.perf_counter()
    timer.start()
    r = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, n_scen + 1)),
        model_fn=fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
        batch_size=1,
        on_batch=timer,
    )
    wall = time.perf_counter() - t
    fe._collect_with_peak = _ORIG_CWP

    walls = timer.walls
    # steady-state per-scenario wall = mean excluding the first 2 passes (warmup)
    steady = walls[2:] if len(walls) > 2 else walls
    steady_mean = sum(steady) / len(steady) if steady else None
    first = walls[0] if walls else None
    last_mean = sum(walls[-3:]) / 3 if len(walls) >= 3 else None
    peak = float(r.peak_rss_mb) if r.peak_rss_mb else None

    rec = {
        "n_scen": n_scen,
        "n_pts": 100_000,
        "total_wall_s": round(wall, 2),
        "per_sc_total_s": round(wall / n_scen, 4),
        "steady_per_sc_s": round(steady_mean, 4) if steady_mean else None,
        "first_pass_s": round(first, 4) if first else None,
        "last3_mean_s": round(last_mean, 4) if last_mean else None,
        "drift_last_over_steady": round(last_mean / steady_mean, 3)
        if (last_mean and steady_mean)
        else None,
        "peak_mb": round(peak, 1) if peak else None,
        "per_pass_walls_s": [round(w, 4) for w in walls],
    }
    with RESULTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    log(
        f"N={n_scen:>4}: total={rec['total_wall_s']}s per_sc={rec['per_sc_total_s']}s "
        f"steady={rec['steady_per_sc_s']}s drift={rec['drift_last_over_steady']} peak={rec['peak_mb']}MB"
    )

log("DONE")
