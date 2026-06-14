# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# In-memory-floor probe (ref/42). Does in-memory@b1 stay LIGHTER than streaming@b1 at 100K
# policies as scenario count scales (10 -> 100 -> 1000), and does peak stay FLAT over many
# folds (the bounded-memory guarantee) or CREEP? If the gap persists, in-mem@b1 earns its place
# as the bottom rung of the memory ladder. If peak is per-scenario-bounded, 1000 folds == 10
# folds in peak (only wall scales).
#
# Each config runs in its OWN fresh process (clean cold-baseline peak). Per-pass ABSOLUTE RSS is
# captured via on_batch to reveal flatness/creep across folds. Cheapest-first, crash-safe
# (one JSON line per config) -- the 10/100sc gap lands in ~35 min; the 1000sc pair is the long
# pole (~5h combined) and can be killed once the trend is clear.
#
# Run:
#   cd bindings/python
#   uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/probe_inmem_floor.py
# Worker (internal): <thisfile> --worker <n_scen> <engine:inmem|stream>
from __future__ import annotations

import gc
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RESULTS = Path(__file__).resolve().parent / "probe_inmem_floor_results.jsonl"
N_PTS = 100_000


def _worker(n_scen: int, engine: str) -> None:
    sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))
    import psutil  # noqa: PLC0415
    import polars as pl  # noqa: PLC0415
    from scenario_lib import generate_stochastic_returns, load_l5_model  # noqa: PLC0415

    import gaspatchio_core.scenarios._for_each as fe  # noqa: PLC0415
    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415
    from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: PLC0415

    l5 = load_l5_model()
    orig = fe._collect_with_peak
    if engine == "stream":
        def patched(lazy, *, eng="streaming", _o=orig):  # noqa: ANN001, ANN202
            return _o(lazy, engine=eng)
        fe._collect_with_peak = patched

    returns = generate_stochastic_returns(n_scen, n_months=180, seed=12345)
    mp = pl.read_parquet(ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet").head(N_PTS)

    def fn(af, *, tables=None, drivers=None, _r=returns):  # noqa: ANN001, ANN202, ARG001
        return l5.main(af, scenario_returns_override=_r, projection_months=82)

    proc = psutil.Process()
    gc.collect()
    baseline = proc.memory_info().rss
    peak = baseline
    stop = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not stop.is_set():
            try:
                peak = max(peak, proc.memory_info().rss)
            except Exception:  # noqa: BLE001
                pass
            stop.wait(0.02)

    # per-pass absolute RSS (creep detector): sampled at each fold boundary
    pass_rss: list[float] = []

    def on_batch(_snap) -> None:  # noqa: ANN001
        try:
            pass_rss.append(round(proc.memory_info().rss / 1024**2, 1))
        except Exception:  # noqa: BLE001
            pass

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    t = time.perf_counter()
    try:
        r = for_each_scenario(
            ActuarialFrame(mp),
            scenarios=list(range(1, n_scen + 1)),
            model_fn=fn,
            aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
            batch_size=1,
            on_batch=on_batch,
        )
        wall = time.perf_counter() - t
        stop.set()
        sampler.join(timeout=1.0)
        # creep = last-decile mean RSS / first-decile mean RSS over the folds
        creep = None
        if len(pass_rss) >= 20:
            d = max(1, len(pass_rss) // 10)
            creep = round((sum(pass_rss[-d:]) / d) / (sum(pass_rss[:d]) / d), 3)
        out = dict(
            ok=True, n_scen=n_scen, engine=engine, wall=round(wall, 2),
            per_sc=round(wall / n_scen, 4),
            peak_working_mb=round((peak - baseline) / 1024**2, 1),
            abs_peak_mb=round(peak / 1024**2, 1), baseline_mb=round(baseline / 1024**2, 1),
            resolved_batch=int(r.batch_size), folds=len(pass_rss),
            pass_rss_first5=pass_rss[:5], pass_rss_last5=pass_rss[-5:], creep=creep,
        )
    except Exception as e:  # noqa: BLE001
        stop.set()
        out = dict(ok=False, n_scen=n_scen, engine=engine, error=type(e).__name__ + ": " + str(e)[:120])
    print("RESULT " + json.dumps(out), flush=True)


def run_cfg(n_scen, engine):  # noqa: ANN001, ANN201
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", str(n_scen), engine]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20000, check=False)  # noqa: S603
    except subprocess.TimeoutExpired:
        return dict(ok=False, n_scen=n_scen, engine=engine, error="TIMEOUT")
    for line in p.stdout.splitlines():
        if line.startswith("RESULT "):
            return json.loads(line[len("RESULT "):])
    return dict(ok=False, n_scen=n_scen, engine=engine,
                error=f"NO_RESULT exit={p.returncode} (likely OOM) {p.stderr[-120:]!r}")


def log(m: str) -> None:
    print(m, flush=True)


# cheapest-first: 10sc & 100sc gaps land first (~35 min); 1000sc pair is the ~5h long pole.
CONFIGS = [
    (10, "inmem"), (10, "stream"),
    (100, "inmem"), (100, "stream"),
    (1000, "stream"), (1000, "inmem"),   # long pole last; kill after if satisfied
]

RESULTS.unlink(missing_ok=True)
log("in-mem-floor probe @100K policies, batch=1 (in-mem vs stream), fresh process each")
gap = {}
for n_scen, engine in CONFIGS:
    r = run_cfg(n_scen, engine)
    with RESULTS.open("a") as f:
        f.write(json.dumps(r) + "\n")
    if r.get("ok"):
        log(f"  {n_scen:>4}sc {engine:>6}@b1: wall={r['wall']}s ({r['per_sc']}s/sc) "
            f"peak={r['peak_working_mb']}MB (abs {r['abs_peak_mb']}MB) folds={r['folds']} creep={r['creep']}")
        gap.setdefault(n_scen, {})[engine] = r
        if "inmem" in gap[n_scen] and "stream" in gap[n_scen]:
            im, st = gap[n_scen]["inmem"], gap[n_scen]["stream"]
            lighter = round(st["peak_working_mb"] / im["peak_working_mb"], 2) if im["peak_working_mb"] else None
            faster = round(im["wall"] / st["wall"], 2) if st["wall"] else None
            log(f"   => {n_scen}sc GAP: in-mem {im['peak_working_mb']}MB vs stream {st['peak_working_mb']}MB "
                f"(stream {lighter}x heavier) | stream {faster}x faster")
    else:
        log(f"  {n_scen:>4}sc {engine:>6}@b1: FAIL {r.get('error')}")
log("DONE")
