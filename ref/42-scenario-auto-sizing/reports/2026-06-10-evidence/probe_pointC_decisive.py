# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# DECISIVE Point-C probe (ref/42). Two questions that determine whether the two-point design
# should become "stream + size the batch":
#   Q1. At 1000 scenarios (where in-memory A "won" the grid), does streaming-BIG-batch beat
#       in-memory A (~123s)? If yes, the A-win was an artifact of streaming-batch-1's 1000
#       plan-builds, not a real in-memory advantage.
#   Q2. At 100K policies, does streaming-batch>1 stay within the memory budget, or is batch=1
#       genuinely the only feasible streaming point there (the graceful-degradation floor)?
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))

import polars as pl  # noqa: E402
from scenario_lib import L5_DIR, generate_stochastic_returns, load_l5_model  # noqa: E402

import gaspatchio_core.scenarios._for_each as fe  # noqa: E402
from gaspatchio_core import ActuarialFrame  # noqa: E402
from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "probe_pointC_decisive_results.jsonl"
RESULTS.unlink(missing_ok=True)

_L5 = load_l5_model()
_ORIG_CWP = fe._collect_with_peak


def force_streaming(on: bool) -> None:
    if not on:
        fe._collect_with_peak = _ORIG_CWP
        return

    def patched(lazy, *, engine="streaming", _o=_ORIG_CWP):  # noqa: ANN001, ANN202
        return _o(lazy, engine=engine)

    fe._collect_with_peak = patched


def points_path(n: int) -> Path:
    if n <= 1000:
        return L5_DIR / "model_points_1k.parquet"
    if n <= 10000:
        return L5_DIR / "model_points_10k.parquet"
    return ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet"


def run(n_pts, n_scen, batch, streaming):  # noqa: ANN001, ANN201
    returns = generate_stochastic_returns(n_scen, n_months=180, seed=12345)
    mp = pl.read_parquet(points_path(n_pts)).head(n_pts)

    def fn(af, *, tables=None, drivers=None, _r=returns):  # noqa: ANN001, ANN202, ARG001
        return _L5.main(af, scenario_returns_override=_r, projection_months=82)

    force_streaming(streaming)
    gc.collect()
    t = time.perf_counter()
    try:
        r = for_each_scenario(
            ActuarialFrame(mp),
            scenarios=list(range(1, n_scen + 1)),
            model_fn=fn,
            aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
            batch_size=batch,
        )
        wall = time.perf_counter() - t
        peak = float(r.peak_rss_mb) if r.peak_rss_mb else None
        return dict(wall=round(wall, 2), per_sc=round(wall / n_scen, 4),
                    peak_mb=round(peak, 1) if peak else None, batch=int(r.batch_size))
    except Exception as e:  # noqa: BLE001
        return dict(error=str(e)[:140])
    finally:
        force_streaming(False)


def log(m: str) -> None:
    print(m, flush=True)


log("=== Q1: 1K x 1000sc — streaming-big-batch vs in-memory A ===")
a = run(1000, 1000, "auto", streaming=False)
log(f"  A in-mem @auto(b={a.get('batch')}): wall={a.get('wall')}s per_sc={a.get('per_sc')}s peak={a.get('peak_mb')}MB")
rec1 = {"cell": "1K x 1000sc", "A_inmem": a, "B_stream": {}}
for b in [1, 8, 32, 64]:
    s = run(1000, 1000, b, streaming=True)
    rec1["B_stream"][str(b)] = s
    spd = round(a["wall"] / s["wall"], 2) if (a.get("wall") and s.get("wall")) else None
    log(f"  stream @b={b}: wall={s.get('wall')}s per_sc={s.get('per_sc')}s peak={s.get('peak_mb')}MB | vs_A={spd}")
with RESULTS.open("a") as f:
    f.write(json.dumps(rec1) + "\n")

log("\n=== Q2: 100K x 10sc — does streaming-batch>1 stay feasible? ===")
rec2 = {"cell": "100K x 10sc", "B_stream": {}}
for b in [1, 2, 4]:
    s = run(100000, 10, b, streaming=True)
    rec2["B_stream"][str(b)] = s
    log(f"  stream @b={b}: wall={s.get('wall')}s per_sc={s.get('per_sc')}s peak={s.get('peak_mb')}MB err={s.get('error')}")
with RESULTS.open("a") as f:
    f.write(json.dumps(rec2) + "\n")
log("\nDONE")
