# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# "Point C" probe (ref/42): is streaming at a SMALL batch (2/4/8) faster than streaming at
# batch=1 (Point B), and what does it cost in peak? The two-point design pins B at batch=1
# because streaming a cross-join inflates peak at batch>1 (#20786). This measures the actual
# speed gain (fixed-overhead amortisation) vs the peak inflation, to confirm B=1 or reveal a
# middle operating point.
#
# Compares, per cell: in-memory@k (Point A ref) and streaming@{1,2,4,8}. Sequential.
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

RESULTS = Path(__file__).resolve().parent / "probe_pointC_results.jsonl"
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
    return L5_DIR / "model_points_10k.parquet"


def run(n_pts, n_scen, batch, streaming):  # noqa: ANN001, ANN201
    returns = generate_stochastic_returns(n_scen, n_months=180, seed=12345)
    mp = pl.read_parquet(points_path(n_pts)).head(n_pts)

    def fn(af, *, tables=None, drivers=None, _r=returns):  # noqa: ANN001, ANN202, ARG001
        return _L5.main(af, scenario_returns_override=_r, projection_months=82)

    force_streaming(streaming)
    gc.collect()
    t = time.perf_counter()
    r = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, n_scen + 1)),
        model_fn=fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
        batch_size=batch,
    )
    wall = time.perf_counter() - t
    force_streaming(False)
    peak = float(r.peak_rss_mb) if r.peak_rss_mb else None
    return dict(wall=round(wall, 3), per_sc=round(wall / n_scen, 4),
                peak_mb=round(peak, 1) if peak else None, batch=int(r.batch_size))


def log(m: str) -> None:
    print(m, flush=True)


# Regime where Point C would most plausibly help: compute-bound (B wins big) but per-pass
# fixed overhead is a non-trivial fraction. 10K policies and 1K x100sc.
CELLS = [
    ("10K x 10sc", 10000, 10),
    ("1K x 100sc", 1000, 100),
]
log("Point C probe: streaming@{1,2,4,8} vs in-memory@auto, per cell")
for name, npt, nsc in CELLS:
    log(f"\n=== {name} ===")
    # in-memory reference (Point A: biggest-in-memory)
    a = run(npt, nsc, "auto", streaming=False)
    log(f"  A in-mem  @auto(b={a['batch']}): wall={a['wall']}s per_sc={a['per_sc']}s peak={a['peak_mb']}MB")
    rows = {"cell": name, "n_pts": npt, "n_scen": nsc,
            "A_inmem": a}
    stream = {}
    for b in [1, 2, 4, 8]:
        s = run(npt, nsc, b, streaming=True)
        stream[str(b)] = s
        vs_b1 = round(stream["1"]["wall"] / s["wall"], 3) if "1" in stream else None
        pk_vs_b1 = round(s["peak_mb"] / stream["1"]["peak_mb"], 3) if (stream.get("1", {}).get("peak_mb") and s["peak_mb"]) else None
        log(f"  B stream  @b={b}: wall={s['wall']}s per_sc={s['per_sc']}s peak={s['peak_mb']}MB"
            f"  | speedup_vs_b1={vs_b1} peak_vs_b1={pk_vs_b1}")
    rows["B_stream"] = stream
    with RESULTS.open("a") as f:
        f.write(json.dumps(rows) + "\n")
log("\nDONE")
