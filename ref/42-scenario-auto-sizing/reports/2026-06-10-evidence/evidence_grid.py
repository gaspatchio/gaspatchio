# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# Evidence grid for the shape-aware for_each_scenario driver (ref/42; report 2026-06-10).
# Two operating points per cell:
#   Point A: batch_size="auto"        (in-memory, biggest-B-that-fits)  -- today's default
#   Point B: batch_size=1 + streaming (compute-dominated lever)
# Across model archetypes (intrinsic graph/horizon) x shapes (scenarios x policies).
#
# Sequential (timing integrity -- NEVER parallelise timed runs). Crash-safe: one JSON line
# per cell. Point A and Point B are measured INDEPENDENTLY so an A budget-refusal still
# captures B (that is the 100K feasibility cell).
#
# Run (from the repo so `uv` resolves the maturin-built gaspatchio_core):
#   cd bindings/python
#   uv run python ../../ref/42-scenario-auto-sizing/reports/2026-06-10-evidence/evidence_grid.py
# Re-running OVERWRITES ./evidence_results.jsonl next to this script. Numbers are machine/RAM-
# dependent (esp. the 100K Point-A budget refusal). See the report's Reproduce section.
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

RESULTS = Path(__file__).resolve().parent / "evidence_results.jsonl"
RESULTS.unlink(missing_ok=True)

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
    "A1_short": dict(projection_months=60, n_months=72, heavy=False),   # overhead-leaning
    "A2_base": dict(projection_months=82, n_months=180, heavy=False),   # balanced (L5 default)
    "A3_long": dict(projection_months=360, n_months=372, heavy=False),  # compute-leaning
    "A4_heavy": dict(projection_months=82, n_months=180, heavy=True),   # plan-build-leaning
}


def make_model_fn(returns, projection_months, heavy):  # noqa: ANN001, ANN201
    def model_fn(af, *, tables=None, drivers=None):  # noqa: ANN001, ANN202, ARG001
        out = _L5.main(af, scenario_returns_override=returns, projection_months=projection_months)
        if heavy:  # +40 graph nodes; pv_net_cf (the aggregated col) untouched
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


def run_point(arch, n_scen, n_pts, *, batch_size, streaming):  # noqa: ANN001, ANN201
    cfg = ARCHETYPES[arch]
    returns = generate_stochastic_returns(n_scen, n_months=cfg["n_months"], seed=12345)
    mp = pl.read_parquet(points_path(n_pts)).head(n_pts)
    fn = make_model_fn(returns, cfg["projection_months"], cfg["heavy"])
    force_streaming(streaming)
    gc.collect()
    t = time.perf_counter()
    try:
        r = for_each_scenario(
            ActuarialFrame(mp),
            scenarios=list(range(1, n_scen + 1)),
            model_fn=fn,
            aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
            batch_size=batch_size,
        )
        wall = time.perf_counter() - t
        peak = float(r.peak_rss_mb) if r.peak_rss_mb else -1.0
        return dict(wall=round(wall, 3), peak_mb=round(peak, 1), batch=int(r.batch_size),
                    res=str(r.batch_size_resolution), check=checksum(r))
    except Exception as e:  # noqa: BLE001  -- a budget refusal on A must not drop B
        return dict(error=str(e)[:160])
    finally:
        force_streaming(False)


# (archetype, n_scen, n_pts). Lean, laptop-safe grid: scenario axis @1K for all 4 archetypes,
# compute axis @10sc for base + long. A3_long capped (no 1000sc / 100K -- too heavy for 16 GB).
CELLS = [
    ("A1_short", 10, 1000), ("A1_short", 100, 1000), ("A1_short", 1000, 1000),
    ("A2_base", 10, 1000), ("A2_base", 100, 1000), ("A2_base", 1000, 1000),
    ("A2_base", 10, 10000), ("A2_base", 10, 100000),
    ("A4_heavy", 10, 1000), ("A4_heavy", 100, 1000), ("A4_heavy", 1000, 1000),
    ("A3_long", 10, 1000), ("A3_long", 100, 1000), ("A3_long", 10, 10000),
]
CELLS.sort(key=lambda c: c[1] * c[2] * ARCHETYPES[c[0]]["projection_months"])  # cheapest first


def log(msg: str) -> None:
    print(msg, flush=True)


log(f"evidence grid: {len(CELLS)} cells x 2 points (A measured independently of B)")
for idx, (arch, ns, npt) in enumerate(CELLS):
    rec = {"archetype": arch, "n_scen": ns, "n_pts": npt, "horizon": ARCHETYPES[arch]["projection_months"]}
    a = run_point(arch, ns, npt, batch_size="auto", streaming=False)
    b = run_point(arch, ns, npt, batch_size=1, streaming=True)
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
        rec["faster"] = "B"  # A infeasible -> B is the only feasible point
        rec["A_infeasible"] = True
    with RESULTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    log(f"[{idx + 1}/{len(CELLS)}] {arch} {ns}sc x {npt}pts -> faster={rec.get('faster')} "
        f"A={a.get('wall', a.get('error', '?'))} B={b.get('wall', b.get('error', '?'))}")
log("DONE")
