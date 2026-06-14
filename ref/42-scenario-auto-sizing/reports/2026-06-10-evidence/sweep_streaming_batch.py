# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Full streaming-batch sweep (ref/42). Maps the OPTIMUM-BATCH SURFACE under the streaming
# engine and the OOM CEILING that bounds it, across policies x scenarios x batch. Replaces the
# two-point A-vs-B grid as the basis for the reframed design ("stream + speed-optimal batch
# that fits"), after the decisive probe showed in-memory is dominated and the per-scenario
# wall is U-shaped in batch under streaming.
#
# METHODOLOGY: each config runs in its OWN fresh subprocess (clean cold baseline) so the peak
# RSS is trustworthy -- prior in-process runs retain arrow buffers and corrupt delta-over-
# baseline peaks (the earlier probes returned None / warm-baseline noise). A config the kernel
# OOM-kills shows up as a non-zero exit with no JSON line -> recorded as "OOM" (the ceiling).
#
# Run:
#   cd bindings/python
#   uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/sweep_streaming_batch.py
# Worker mode (internal): <thisfile> --worker <n_pts> <n_scen> <horizon> <batch|auto> <stream:0|1>
from __future__ import annotations

import gc
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RESULTS = Path(__file__).resolve().parent / "sweep_streaming_batch_results.jsonl"


# ----------------------------------------------------------------------------- worker
def _worker(n_pts: int, n_scen: int, horizon: int, batch, streaming: bool) -> None:  # noqa: ANN001
    sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))
    import psutil  # noqa: PLC0415
    import polars as pl  # noqa: PLC0415
    from scenario_lib import L5_DIR, generate_stochastic_returns, load_l5_model  # noqa: PLC0415

    import gaspatchio_core.scenarios._for_each as fe  # noqa: PLC0415
    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415
    from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: PLC0415

    l5 = load_l5_model()
    orig = fe._collect_with_peak
    if streaming:
        def patched(lazy, *, engine="streaming", _o=orig):  # noqa: ANN001, ANN202
            return _o(lazy, engine=engine)
        fe._collect_with_peak = patched

    def points_path(n: int) -> Path:
        if n <= 1000:
            return L5_DIR / "model_points_1k.parquet"
        if n <= 10000:
            return L5_DIR / "model_points_10k.parquet"
        return ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet"

    returns = generate_stochastic_returns(n_scen, n_months=max(180, horizon + 12), seed=12345)
    mp = pl.read_parquet(points_path(n_pts)).head(n_pts)

    def fn(af, *, tables=None, drivers=None, _r=returns):  # noqa: ANN001, ANN202, ARG001
        return l5.main(af, scenario_returns_override=_r, projection_months=horizon)

    proc = psutil.Process()
    gc.collect()
    baseline = proc.memory_info().rss
    peak = baseline
    stop = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not stop.is_set():
            try:
                rss = proc.memory_info().rss
            except Exception:  # noqa: BLE001
                rss = peak
            peak = max(peak, rss)
            stop.wait(0.01)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
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
        stop.set()
        sampler.join(timeout=1.0)
        out = dict(
            ok=True, wall=round(wall, 2), per_sc=round(wall / n_scen, 4),
            resolved_batch=int(r.batch_size), resolution=str(r.batch_size_resolution),
            peak_mb=round((peak - baseline) / 1024**2, 1),
            abs_peak_mb=round(peak / 1024**2, 1), baseline_mb=round(baseline / 1024**2, 1),
        )
    except Exception as e:  # noqa: BLE001
        stop.set()
        out = dict(ok=False, error=type(e).__name__ + ": " + str(e)[:120])
    print("RESULT " + json.dumps(out), flush=True)


# ------------------------------------------------------------------------- orchestrator
def _cfg(name, n_pts, n_scen, horizon, batches, with_inmem=True):  # noqa: ANN001, ANN201, PLR0913
    return dict(name=name, n_pts=n_pts, n_scen=n_scen, horizon=horizon,
                batches=batches, with_inmem=with_inmem)


# LEAN sweep: prove STRUCTURE + MECHANISM (not map L5's surface -- L5 is 1 of hundreds, don't
# overfit). Each cell demonstrates one structural fact; the optimum-batch numbers are NOT design
# inputs (the selector searches per-model at runtime). cheapest-first.
CELLS = [
    # U-shape + streaming dominance in the overhead regime; optimum is a BIG batch here:
    _cfg("1K x 100sc", 1000, 100, 82, [1, 4, 16, 64]),
    # same shape, longer horizon: does the optimum MOVE? (=> must measure, can't hardcode)
    _cfg("1K x 100sc x360mo", 1000, 100, 360, [1, 8, 32]),
    # more policies: optimum should shift SMALLER (compute-leaning):
    _cfg("10K x 100sc", 10000, 100, 82, [1, 4, 16]),
    # high policies: optimum = b1, and the feasibility/OOM ceiling (in-mem refuses):
    _cfg("100K x 10sc", 100000, 10, 82, [1, 2]),   # b4 known much slower; {1,2} shows trend + clean peak
    # more scenarios: optimum should shift BIGGER (overhead-leaning) -- clean-peak re-measure:
    _cfg("1K x 1000sc", 1000, 1000, 82, [4, 16, 64]),         # skip b1 (known ~492s)
]


def run_worker_subprocess(n_pts, n_scen, horizon, batch, streaming):  # noqa: ANN001, ANN201
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker",
           str(n_pts), str(n_scen), str(horizon), str(batch), "1" if streaming else "0"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, check=False)  # noqa: S603
    except subprocess.TimeoutExpired:
        return dict(ok=False, error="TIMEOUT(>3600s)")
    for line in p.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    # No RESULT line + non-zero exit -> almost certainly OOM-killed by the kernel.
    tail = (p.stderr or "")[-160:]
    return dict(ok=False, error=f"NO_RESULT exit={p.returncode} (likely OOM) {tail!r}")


def log(m: str) -> None:
    print(m, flush=True)


def orchestrate() -> None:
    RESULTS.unlink(missing_ok=True)
    total = sum(len(c["batches"]) + (1 if c["with_inmem"] else 0) for c in CELLS)
    log(f"streaming-batch sweep: {len(CELLS)} cells, {total} configs (fresh process each)")
    done = 0
    for c in CELLS:
        log(f"\n=== {c['name']} (horizon {c['horizon']}mo) ===")
        rec = {"cell": c["name"], "n_pts": c["n_pts"], "n_scen": c["n_scen"],
               "horizon": c["horizon"], "inmem": None, "stream": {}}
        if c["with_inmem"]:
            r = run_worker_subprocess(c["n_pts"], c["n_scen"], c["horizon"], "auto", False)
            rec["inmem"] = r
            done += 1
            log(f"  [{done}/{total}] in-mem @auto: {_fmt(r)}")
        for b in c["batches"]:
            r = run_worker_subprocess(c["n_pts"], c["n_scen"], c["horizon"], b, True)
            rec["stream"][str(b)] = r
            done += 1
            log(f"  [{done}/{total}] stream @b={b}: {_fmt(r)}")
        # crash-safe: write the cell as soon as it finishes
        with RESULTS.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        _summarise_cell(rec)
    log("\nDONE")


def _fmt(r) -> str:  # noqa: ANN001
    if not r.get("ok"):
        return f"FAIL {r.get('error')}"
    return f"{r['wall']}s ({r['per_sc']}s/sc) peak={r['peak_mb']}MB [b={r.get('resolved_batch')}]"


def _summarise_cell(rec) -> None:  # noqa: ANN001
    streams = {int(b): r for b, r in rec["stream"].items() if r.get("ok")}
    if not streams:
        return
    best_b = min(streams, key=lambda b: streams[b]["wall"])
    best = streams[best_b]
    inmem = rec["inmem"]
    line = f"  -> OPTIMUM stream @b={best_b}: {best['wall']}s ({best['per_sc']}s/sc), peak {best['peak_mb']}MB"
    if inmem and inmem.get("ok"):
        line += f"  | vs in-mem {inmem['wall']}s = {round(inmem['wall'] / best['wall'], 2)}x"
    elif inmem and not inmem.get("ok"):
        line += f"  | in-mem: {inmem.get('error', '?')[:40]}"
    log(line)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _, _, np_, ns_, hz_, b_, st_ = sys.argv
        _worker(int(np_), int(ns_), int(hz_), (b_ if b_ == "auto" else int(b_)), st_ == "1")
    else:
        orchestrate()
