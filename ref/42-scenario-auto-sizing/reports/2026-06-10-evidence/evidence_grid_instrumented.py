# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Instrumented evidence grid for the shape-aware for_each_scenario driver (ref/42).
# Extends evidence_grid.py with TWO goals:
#   1. Refresh the full 14-cell A-vs-B grid (the committed evidence_results.jsonl was a
#      partial 10-cell run missing all three 1000sc A-wins + the 100K infeasibility cell).
#   2. INSTRUMENT B's per-pass wall via on_batch, to settle whether the per-scenario
#      comparator the selector would use is sound at high scenario counts.
#
# The decisive question (T0.2 in 2026-06-10-design-review-findings.md): B's per-scenario
# wall rose ~4x from 100sc (0.116s) to 1000sc (0.484s) at 1K policies. Is that:
#   (DRIFT)        early passes cheap, late passes expensive  -> a race timing pass #2
#                  under-predicts B and wrongly crowns it where A wins. MECHANISM HOLE.
#   (FLAT-BUT-HIGH) every pass ~equal including pass #2        -> race samples the right
#                  value; the between-run gap is a confound (e.g. thermal). T0.2 dissolves.
# We capture the per-pass wall timeseries for B and simulate the race's prediction
# (mean of early post-warmup passes x N) vs the actual total.
#
# Run (from the repo so uv resolves the maturin-built gaspatchio_core):
#   cd bindings/python
#   uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/evidence_grid_instrumented.py
# Sequential (timing integrity). Crash-safe: one JSON line per cell. Numbers are machine/RAM-
# dependent. Outputs (next to this script, overwritten each run):
#   evidence_results_v2.jsonl   -- per-cell A-vs-B summary (refresh candidate)
#   per_pass_timeseries.jsonl   -- per-pass walls for the timeseries cells (B and A)
from __future__ import annotations

import gc
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # .../gaspatchio-core
sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))

import polars as pl  # noqa: E402
from scenario_lib import L5_DIR, generate_stochastic_returns, load_l5_model  # noqa: E402

import gaspatchio_core.scenarios._for_each as fe  # noqa: E402
from gaspatchio_core import ActuarialFrame  # noqa: E402
from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "evidence_results_v2.jsonl"
TIMESERIES = Path(__file__).resolve().parent / "per_pass_timeseries.jsonl"
RESULTS.unlink(missing_ok=True)
TIMESERIES.unlink(missing_ok=True)

_L5 = load_l5_model()
_ORIG_CWP = fe._collect_with_peak


def force_streaming(on: bool) -> None:
    """Force (or restore) engine='streaming' on the per-batch projection collect."""
    if not on:
        fe._collect_with_peak = _ORIG_CWP
        return

    def patched(lazy, *, engine="streaming", _o=_ORIG_CWP):  # noqa: ANN001, ANN202
        return _o(lazy, engine=engine)

    fe._collect_with_peak = patched


ARCHETYPES = {
    "A1_short": dict(projection_months=60, n_months=72, heavy=False),
    "A2_base": dict(projection_months=82, n_months=180, heavy=False),
    "A3_long": dict(projection_months=360, n_months=372, heavy=False),
    "A4_heavy": dict(projection_months=82, n_months=180, heavy=True),
}


def make_model_fn(returns, projection_months, heavy):  # noqa: ANN001, ANN201
    def model_fn(af, *, tables=None, drivers=None):  # noqa: ANN001, ANN202, ARG001
        out = _L5.main(af, scenario_returns_override=returns, projection_months=projection_months)
        if heavy:
            for i in range(40):
                setattr(out, f"heavy_{i}", (out.pv_net_cf * (1.0 + i / 1000.0)) - (out.pv_claims * (i / 1000.0)))
        return out

    return model_fn


def points_path(n: int) -> Path:
    if n <= 1000:
        return L5_DIR / "model_points_1k.parquet"
    if n <= 10000:
        return L5_DIR / "model_points_10k.parquet"
    return ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet"


def checksum(result) -> float:  # noqa: ANN001
    agg = result.aggregations["total"]
    if isinstance(agg, pl.DataFrame):
        cols = [c for c, t in agg.schema.items() if t.is_numeric() and c != "scenario_id"]
        return round(sum(float(agg[c].sum()) for c in cols), 2)
    if isinstance(agg, dict):
        return round(sum(float(v) for v in agg.values()), 2)
    return round(float(agg), 2)


class PerPassTimer:
    """Captures wall between consecutive on_batch callbacks => per-pass (per-batch) wall.

    At batch_size=1 each batch is one scenario, so this IS the per-scenario wall timeseries.
    """

    def __init__(self) -> None:
        self.t_prev: float | None = None
        self.walls: list[float] = []
        self.scenarios_done: list[int] = []
        self.peaks: list[float | None] = []

    def start(self) -> None:
        self.t_prev = time.perf_counter()

    def __call__(self, snap) -> None:  # noqa: ANN001
        now = time.perf_counter()
        if self.t_prev is not None:
            self.walls.append(now - self.t_prev)
            self.scenarios_done.append(snap.scenarios_done)
            self.peaks.append(snap.peak_rss_mb)
        self.t_prev = now


def run_point(arch, n_scen, n_pts, *, batch_size, streaming, capture_timeseries=False):  # noqa: ANN001, ANN201, PLR0913
    cfg = ARCHETYPES[arch]
    returns = generate_stochastic_returns(n_scen, n_months=cfg["n_months"], seed=12345)
    mp = pl.read_parquet(points_path(n_pts)).head(n_pts)
    fn = make_model_fn(returns, cfg["projection_months"], cfg["heavy"])
    force_streaming(streaming)
    gc.collect()
    timer = PerPassTimer() if capture_timeseries else None
    t = time.perf_counter()
    try:
        if timer is not None:
            timer.start()
        r = for_each_scenario(
            ActuarialFrame(mp),
            scenarios=list(range(1, n_scen + 1)),
            model_fn=fn,
            aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
            batch_size=batch_size,
            on_batch=timer,
        )
        wall = time.perf_counter() - t
        peak = float(r.peak_rss_mb) if r.peak_rss_mb else -1.0
        out = dict(wall=round(wall, 3), peak_mb=round(peak, 1), batch=int(r.batch_size),
                   res=str(r.batch_size_resolution), check=checksum(r))
        if timer is not None:
            out["timer"] = timer
        return out
    except Exception as e:  # noqa: BLE001
        return dict(error=str(e)[:160])
    finally:
        force_streaming(False)


def simulate_race(walls: list[float], n_scen: int, actual_total: float, warmup=1, sample=5):  # noqa: ANN001, ANN201
    """Simulate what the drafted race would predict: mean of early post-warmup B passes x N.

    Returns the prediction, the prediction/actual ratio, and drift diagnostics
    (early vs late mean). prediction << actual => the race under-predicts B (mispick risk).
    """
    if len(walls) < warmup + sample + 5:
        return None
    early = walls[warmup : warmup + sample]
    early_mean = sum(early) / len(early)
    predicted_total = early_mean * n_scen
    last = walls[-sample:]
    late_mean = sum(last) / len(last)
    return dict(
        early_mean_s=round(early_mean, 4),
        late_mean_s=round(late_mean, 4),
        drift_late_over_early=round(late_mean / early_mean, 3) if early_mean > 0 else None,
        predicted_total_s=round(predicted_total, 2),
        actual_total_s=round(actual_total, 2),
        predicted_over_actual=round(predicted_total / actual_total, 3) if actual_total > 0 else None,
    )


# Full 14-cell grid (refreshes evidence). High-N / decisive cells flagged for per-pass capture.
CELLS = [
    ("A1_short", 10, 1000), ("A1_short", 100, 1000), ("A1_short", 1000, 1000),
    ("A2_base", 10, 1000), ("A2_base", 100, 1000), ("A2_base", 1000, 1000),
    ("A2_base", 10, 10000), ("A2_base", 10, 100000),
    ("A4_heavy", 10, 1000), ("A4_heavy", 100, 1000), ("A4_heavy", 1000, 1000),
    ("A3_long", 10, 1000), ("A3_long", 100, 1000), ("A3_long", 10, 10000),
]
# Capture B's per-pass timeseries on the cells where the comparator question lives:
# the 1000sc A-wins (decisive) + their 10/100sc siblings (to see the per-pass distribution
# shift across N at fixed policies/horizon).
TIMESERIES_CELLS = {
    ("A2_base", 10, 1000), ("A2_base", 100, 1000), ("A2_base", 1000, 1000),
    ("A1_short", 1000, 1000), ("A4_heavy", 1000, 1000),
}
CELLS.sort(key=lambda c: c[1] * c[2] * ARCHETYPES[c[0]]["projection_months"])


def log(msg: str) -> None:
    print(msg, flush=True)


log(f"instrumented grid: {len(CELLS)} cells x 2 points; {len(TIMESERIES_CELLS)} B-timeseries cells")
for idx, (arch, ns, npt) in enumerate(CELLS):
    cap = (arch, ns, npt) in TIMESERIES_CELLS
    rec = {"archetype": arch, "n_scen": ns, "n_pts": npt, "horizon": ARCHETYPES[arch]["projection_months"]}
    a = run_point(arch, ns, npt, batch_size="auto", streaming=False)
    b = run_point(arch, ns, npt, batch_size=1, streaming=True, capture_timeseries=cap)
    if "error" in a:
        rec["A_error"] = a["error"]
    else:
        rec.update(A_wall=a["wall"], A_peak_mb=a["peak_mb"], A_batch=a["batch"], A_res=a["res"], A_check=a["check"])
    if "error" in b:
        rec["B_error"] = b["error"]
    else:
        rec.update(B_wall=b["wall"], B_peak_mb=b["peak_mb"], B_check=b["check"])
    if "error" not in a and "error" not in b:
        rec["faster"] = "B" if b["wall"] < a["wall"] else "A"
        rec["speed_B_over_A"] = round(a["wall"] / b["wall"], 3) if b["wall"] > 0 else None
        rec["peak_ratio_B_over_A"] = round(b["peak_mb"] / a["peak_mb"], 3) if a["peak_mb"] > 0 else None
        rec["checksum_match"] = a["check"] == b["check"]
    elif "error" in a and "error" not in b:
        rec["faster"] = "B"
        rec["A_infeasible"] = True

    # Per-pass analysis: does the race's early-sample extrapolation predict B's actual total?
    if cap and "error" not in b and "timer" in b:
        timer = b["timer"]
        sim = simulate_race(timer.walls, ns, b["wall"])
        if sim is not None:
            rec["race_sim"] = sim
        with TIMESERIES.open("a") as f:
            f.write(json.dumps({
                "archetype": arch, "n_scen": ns, "n_pts": npt,
                "point": "B", "batch": 1,
                "per_pass_walls_s": [round(w, 5) for w in timer.walls],
                "scenarios_done": timer.scenarios_done,
                "peaks_mb": timer.peaks,
            }) + "\n")

    with RESULTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    extra = ""
    if "race_sim" in rec:
        rs = rec["race_sim"]
        extra = f" | race_sim pred/actual={rs['predicted_over_actual']} drift(late/early)={rs['drift_late_over_early']}"
    log(f"[{idx + 1}/{len(CELLS)}] {arch} {ns}sc x {npt}pts -> faster={rec.get('faster')} "
        f"A={a.get('wall', a.get('error', '?'))} B={b.get('wall', b.get('error', '?'))}{extra}")
log("DONE")
