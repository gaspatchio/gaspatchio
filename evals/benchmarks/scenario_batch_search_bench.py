# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
# ABOUTME: Time-series benchmark for the shape-aware for_each_scenario streaming-batch search.
# ABOUTME: Emits customSmallerIsBetter JSON (github-action-benchmark) -> gh-pages dev/batch-bench.

"""Streaming-batch-search benchmark (ref/42 shape-aware driver).

Tracks, over commits, how ``batch_size="auto"`` performs once it became a measured
streaming-batch search. Emits flat github-action-benchmark JSON to **stdout** (human log to
**stderr**), matching ``run_aggregated_benchmarks.py``. Two families of metric:

* **throughput** (1K/10K/[100K] policies): the auto-search wall + peak per shape. If a change
  makes the selector pick a worse batch, ``*-auto-wall`` regresses and the dashboard shows it.
  Correctness (checksum identity vs a manual batch) is asserted — a mismatch FAILS the job.
* **in-mem floor** (100K policies, runner-only): ``stream@b1`` peak vs ``in-mem@b1`` peak — the
  Polars cross-join inflation (#20786) that makes ``in-mem@b1`` the memory floor. Each engine
  runs in a FRESH subprocess for a clean cold-baseline peak. NEVER run the 100K cells on a 16 GB
  laptop (they saturate swap); they belong on the perf runner (``ubuntu-latest-m``).

Usage:
    # CI (perf runner): full grid incl. 100K + floor
    uv run python evals/benchmarks/scenario_batch_search_bench.py
    # local / laptop-safe: 1K + 10K only, no floor
    uv run python evals/benchmarks/scenario_batch_search_bench.py --skip-heavy
    # internal: one fresh-process 100K floor pass
    uv run python evals/benchmarks/scenario_batch_search_bench.py --floor-worker <n_scen> <inmem|stream>
"""

from __future__ import annotations

import argparse
import gc
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../gaspatchio-core
sys.path.insert(0, str(ROOT / "evals" / "benchmarks"))

_BENCH = "Batch Search"
_OUT = Path(__file__).resolve().parent / "batch_search_results" / "benchmark-results.json"

# (n_policies, n_scenarios) throughput cells. 100K is heavy (perf runner only).
_LIGHT_CELLS = ((1_000, 100), (1_000, 1_000), (10_000, 100))
_HEAVY_CELLS = ((100_000, 10),)
# (n_scenarios,) for the 100K in-mem floor confirmation (perf runner only; >100sc is multi-hour).
_FLOOR_SCEN = (10, 100)


def _err(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _points_path(n_pts: int) -> Path:
    from scenario_lib import L5_DIR  # noqa: PLC0415

    if n_pts <= 1000:
        return L5_DIR / "model_points_1k.parquet"
    if n_pts <= 10000:
        return L5_DIR / "model_points_10k.parquet"
    return ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet"


def _checksum(result) -> float:  # noqa: ANN001
    agg = result.aggregations["total"]
    cols = [c for c, t in agg.schema.items() if t.is_numeric() and c != "scenario_id"]
    return round(sum(float(agg[c].sum()) for c in cols), 2)


# --------------------------------------------------------------------------- throughput cells
def _run_cell(n_pts: int, n_scen: int, *, verify: bool) -> dict[str, object]:
    """Run one auto-search cell; on ``verify`` also assert checksum identity vs a manual batch.

    Checksum identity is cell-independent (and covered exhaustively by the unit tests), so the
    bench only spot-checks it at the cheapest cell -- a manual ``batch_size=1`` baseline at the
    heavy cells would be ~2 min of pure in-memory passes for no extra signal.
    """
    import polars as pl  # noqa: PLC0415
    from scenario_lib import generate_stochastic_returns, load_l5_model  # noqa: PLC0415

    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415
    from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: PLC0415

    l5 = load_l5_model()
    returns = generate_stochastic_returns(n_scen, n_months=180, seed=12345)
    mp = pl.read_parquet(_points_path(n_pts)).head(n_pts)

    def fn(af, *, tables=None, drivers=None, _r=returns):  # noqa: ANN001, ANN202, ARG001
        return l5.main(af, scenario_returns_override=_r, projection_months=82)

    agg = (Sum("pv_net_cf").alias("total").over("scenario_id"),)
    gc.collect()
    auto = for_each_scenario(
        ActuarialFrame(mp), scenarios=list(range(1, n_scen + 1)),
        model_fn=fn, aggregations=agg, batch_size="auto",
    )
    checksum_ok: bool | None = None
    if verify:
        manual = for_each_scenario(
            ActuarialFrame(mp), scenarios=list(range(1, n_scen + 1)),
            model_fn=fn, aggregations=agg, batch_size=8,
        )
        checksum_ok = _checksum(auto) == _checksum(manual)
        if not checksum_ok:
            msg = (
                f"checksum mismatch at {n_pts}pts x{n_scen}sc: "
                f"{_checksum(auto)} != {_checksum(manual)}"
            )
            raise AssertionError(msg)
    sel = auto.selection
    return {
        "wall": round(auto.wall_time_s, 3),
        "peak_mb": round(auto.peak_rss_mb, 1) if auto.peak_rss_mb else -1.0,
        "batch": auto.batch_size,
        "engine": sel.engine if sel else "?",
        "checksum_ok": checksum_ok,
    }


def _cell_label(n_pts: int, n_scen: int) -> str:
    pts = f"{n_pts // 1000}K" if n_pts >= 1000 else str(n_pts)
    return f"{pts}-{n_scen}sc"


def _throughput_rows(n_pts: int, n_scen: int, m: dict[str, object]) -> list[dict[str, object]]:
    lbl = _cell_label(n_pts, n_scen)
    ck = m["checksum_ok"]
    _err(
        f"{_BENCH}/{lbl}: auto batch={m['batch']} engine={m['engine']} "
        f"wall={m['wall']}s peak={m['peak_mb']}MB "
        f"checksum={'OK' if ck else ('FAIL' if ck is False else 'n/a')}"
    )
    rows = [
        {"name": f"{_BENCH}/{lbl}-auto-wall", "unit": "seconds", "value": m["wall"]},
        {"name": f"{_BENCH}/{lbl}-auto-peak", "unit": "MB", "value": m["peak_mb"]},
    ]
    if ck is not None:  # only the spot-checked cell emits a checksum series
        rows.append({"name": f"{_BENCH}/{lbl}-checksum", "unit": "bool", "value": 1.0 if ck else 0.0})
    return rows


# --------------------------------------------------------------------------- in-mem floor
def _floor_worker(n_scen: int, engine: str) -> None:
    """One fresh-process 100K x N run at batch_size=1; print (wall, clean peak) JSON to stdout."""
    import psutil  # noqa: PLC0415
    import polars as pl  # noqa: PLC0415
    from loguru import logger  # noqa: PLC0415

    logger.remove()  # silence the DEBUG firehose (RAM-buffering it crashed an early probe)
    from scenario_lib import generate_stochastic_returns, load_l5_model  # noqa: PLC0415

    import gaspatchio_core.scenarios._for_each as fe  # noqa: PLC0415
    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415
    from gaspatchio_core.scenarios import Sum, for_each_scenario  # noqa: PLC0415

    l5 = load_l5_model()
    orig = fe._collect_with_peak  # noqa: SLF001
    if engine == "stream":

        def patched(lazy, *, eng="streaming", _o=orig):  # noqa: ANN001, ANN202
            return _o(lazy, engine=eng)

        fe._collect_with_peak = patched  # noqa: SLF001

    returns = generate_stochastic_returns(n_scen, n_months=180, seed=12345)
    mp = pl.read_parquet(
        ROOT / "evals" / "benchmarks" / "model_points" / "l5_100k.parquet"
    ).head(100_000)

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

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    t = time.perf_counter()
    for_each_scenario(
        ActuarialFrame(mp), scenarios=list(range(1, n_scen + 1)), model_fn=fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),), batch_size=1,
    )
    wall = time.perf_counter() - t
    stop.set()
    sampler.join(timeout=1.0)
    print("FLOOR " + json.dumps({
        "n_scen": n_scen, "engine": engine, "wall_s": round(wall, 2),
        "peak_mb": round((peak - baseline) / 1024**2, 1),
    }), flush=True)


def _floor_rows(n_scen: int) -> list[dict[str, object]]:
    """Spawn fresh-process in-mem@b1 vs stream@b1 at 100K; assert floor; return metrics."""
    import subprocess  # noqa: PLC0415

    peaks: dict[str, float] = {}
    walls: dict[str, float] = {}
    for engine in ("inmem", "stream"):
        cmd = [sys.executable, str(Path(__file__).resolve()), "--floor-worker", str(n_scen), engine]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20000, check=False)  # noqa: S603
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith("FLOOR ")), None)
        if line is None:
            _err(f"{_BENCH}/100K-{n_scen}sc {engine}: NO RESULT exit={p.returncode} (likely OOM)")
            continue
        rec = json.loads(line[len("FLOOR ") :])
        peaks[engine] = rec["peak_mb"]
        walls[engine] = rec["wall_s"]
    if "inmem" not in peaks or "stream" not in peaks:
        return []
    ratio = round(peaks["stream"] / peaks["inmem"], 3) if peaks["inmem"] else 0.0
    holds = peaks["inmem"] < peaks["stream"]
    _err(
        f"{_BENCH}/100K-{n_scen}sc floor: in-mem {peaks['inmem']}MB vs stream {peaks['stream']}MB "
        f"(ratio {ratio}x) {'HOLDS' if holds else 'VIOLATED'}"
    )
    if not holds:
        msg = f"in-mem floor violated at 100K x{n_scen}sc: in-mem {peaks['inmem']} >= stream {peaks['stream']}"
        raise AssertionError(msg)
    return [
        {"name": f"{_BENCH}/100K-{n_scen}sc-inmem-peak", "unit": "MB", "value": peaks["inmem"]},
        {"name": f"{_BENCH}/100K-{n_scen}sc-stream-peak", "unit": "MB", "value": peaks["stream"]},
        {"name": f"{_BENCH}/100K-{n_scen}sc-stream-wall", "unit": "seconds", "value": walls["stream"]},
        {"name": f"{_BENCH}/100K-{n_scen}sc-floor-ratio", "unit": "x", "value": ratio},
    ]


# --------------------------------------------------------------------------- main
def main() -> None:
    """Run the cells, assert correctness/floor, emit github-action-benchmark JSON."""
    parser = argparse.ArgumentParser(description="streaming-batch-search benchmark")
    parser.add_argument("--skip-heavy", action="store_true", help="1K/10K only; no 100K + no floor")
    args = parser.parse_args()

    from gaspatchio_core.scenarios._memory import IrreducibleCellError  # noqa: PLC0415

    rows: list[dict[str, object]] = []
    cells = list(_LIGHT_CELLS) + ([] if args.skip_heavy else list(_HEAVY_CELLS))
    # Spot-check checksum identity only at the cheapest cell (cell-independent property).
    verify_cell = min(cells, key=lambda c: c[0] * c[1])
    for n_pts, n_scen in cells:
        try:
            m = _run_cell(n_pts, n_scen, verify=(n_pts, n_scen) == verify_cell)
        except IrreducibleCellError as e:
            # The sizer refusing a cell that does not fit this box is the library
            # working as designed (free runners are smaller than the perf runner).
            # Skip the cell's rows but keep the run -- and the emitted JSON -- valid.
            _err(f"{_BENCH}/{_cell_label(n_pts, n_scen)}: SKIPPED (irreducible on this box: {e})")
            continue
        rows.extend(_throughput_rows(n_pts, n_scen, m))
    if not args.skip_heavy:
        for n_scen in _FLOOR_SCEN:
            rows.extend(_floor_rows(n_scen))

    output = json.dumps(rows, indent=2)
    print(output)  # stdout for CI `tee`
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(output)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--floor-worker":
        _floor_worker(int(sys.argv[2]), sys.argv[3])
    else:
        main()
