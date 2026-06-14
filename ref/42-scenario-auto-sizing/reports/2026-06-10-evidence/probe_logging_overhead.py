# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Logging-overhead probe (ref/42). Every model_fn call (= every PASS) re-registers assumption
# tables and emits a burst of LOGURU DEBUG lines. Passes = scenarios / batch, so logging
# penalises SMALL batches (many passes) more than large ones -- which could artificially inflate
# the left side of the per-scenario-wall U-shape and bias the measured optimum batch LARGER than
# the truth. This quantifies the speed AND memory cost of logging, and whether the batch optimum
# shifts when logging is off.
#
# Each config in a fresh process (clean peak). logging OFF = logger.remove() before the run.
# Worker writes its RESULT to a file (NOT a RAM-buffered pipe -- that bug crashed the prior probe);
# worker DEBUG stderr -> a throwaway file on the root disk (realistic IO), stdout -> devnull.
#
# Run:
#   cd bindings/python
#   uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/probe_logging_overhead.py
# Worker (internal): <thisfile> --worker <n_pts> <n_scen> <batch> <log:on|off> <result_file>
from __future__ import annotations

import gc
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RESULTS = Path(__file__).resolve().parent / "probe_logging_overhead_results.jsonl"
SCRATCH = Path("/tmp/gsp_design_review")
SCRATCH.mkdir(exist_ok=True)


def _worker(n_pts: int, n_scen: int, batch: int, logging_on: bool, result_file: str) -> None:
    sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))
    import psutil  # noqa: PLC0415
    import polars as pl  # noqa: PLC0415
    from loguru import logger  # noqa: PLC0415

    if not logging_on:
        logger.remove()  # silence ALL handlers -> no formatting, no emission

    from scenario_lib import L5_DIR, generate_stochastic_returns, load_l5_model  # noqa: PLC0415
    import gaspatchio_core.scenarios._for_each as fe  # noqa: PLC0415, F401
    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415
    from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: PLC0415

    l5 = load_l5_model()
    returns = generate_stochastic_returns(n_scen, n_months=180, seed=12345)
    pts = L5_DIR / "model_points_1k.parquet" if n_pts <= 1000 else L5_DIR / "model_points_10k.parquet"
    mp = pl.read_parquet(pts).head(n_pts)

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
            stop.wait(0.01)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    t = time.perf_counter()
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
    out = dict(n_pts=n_pts, n_scen=n_scen, batch=batch, logging="on" if logging_on else "off",
               passes=(n_scen + batch - 1) // batch, wall=round(wall, 3),
               per_sc=round(wall / n_scen, 4),
               peak_mb=round((peak - baseline) / 1024**2, 1),
               resolved_batch=int(r.batch_size))
    Path(result_file).write_text(json.dumps(out))


def run_cfg(n_pts, n_scen, batch, logging_on):  # noqa: ANN001, ANN201
    rf = SCRATCH / f"logres_{n_pts}_{n_scen}_{batch}_{int(logging_on)}.json"
    rf.unlink(missing_ok=True)
    errsink = SCRATCH / "worker_debug.stderr"  # realistic IO sink for DEBUG (root disk), reused
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker",
           str(n_pts), str(n_scen), str(batch), "on" if logging_on else "off", str(rf)]
    with errsink.open("w") as ferr:
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=ferr, timeout=1800, check=False)  # noqa: S603
    if rf.exists():
        return json.loads(rf.read_text())
    return dict(n_pts=n_pts, n_scen=n_scen, batch=batch, logging="on" if logging_on else "off",
                error=f"NO_RESULT exit={p.returncode}")


def log(m: str) -> None:
    print(m, flush=True)


# 1K policies (fast, safe): full batch sweep x logging on/off -> does the optimum shift?
# + 10K x {1,16} to see if the effect scales with per-pass work.
CONFIGS = []
for b in [1, 4, 16, 64]:
    CONFIGS.append((1000, 100, b))
for b in [1, 16]:
    CONFIGS.append((10000, 100, b))

RESULTS.unlink(missing_ok=True)
log("logging-overhead probe: same config, logging ON vs OFF (fresh process each)")
rows = []
for n_pts, n_scen, batch in CONFIGS:
    on = run_cfg(n_pts, n_scen, batch, True)
    off = run_cfg(n_pts, n_scen, batch, False)
    rec = {"n_pts": n_pts, "n_scen": n_scen, "batch": batch,
           "passes": on.get("passes"), "on": on, "off": off}
    if on.get("wall") and off.get("wall"):
        rec["log_slowdown"] = round(on["wall"] / off["wall"], 3)
        rec["log_wall_cost_s"] = round(on["wall"] - off["wall"], 3)
        rec["per_pass_log_cost_ms"] = round(1000 * (on["wall"] - off["wall"]) / max(1, on["passes"]), 2)
        rec["peak_on_mb"] = on.get("peak_mb")
        rec["peak_off_mb"] = off.get("peak_mb")
    with RESULTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    log(f"  {n_pts}pts x{n_scen}sc b={batch:>2} ({on.get('passes')} passes): "
        f"ON {on.get('wall')}s / OFF {off.get('wall')}s -> {rec.get('log_slowdown')}x "
        f"(+{rec.get('log_wall_cost_s')}s, {rec.get('per_pass_log_cost_ms')}ms/pass) "
        f"| peak ON {on.get('peak_mb')}MB OFF {off.get('peak_mb')}MB")
    rows.append(rec)
log("DONE")
