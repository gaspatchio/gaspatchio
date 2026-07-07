# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0
"""CI scenario perf benchmark -- L-shaped grid, batch_size='auto', new dashboard page.

Emits a flat JSON array of {name, unit, value} for github-action-benchmark, on a
new dev/scenario-bench page. Tracks the DEFAULT (auto) scenario path over time.
Uses the validated for_each_scenario(auto) + integer-ID + stochastic-returns
mechanism (see ref/42-scenario-auto-sizing/reports/2026-05-30-scenario-testdrive.md).
"""
# ruff: noqa: T201

from __future__ import annotations

import json
import sys
from pathlib import Path

# repo root, for evals.benchmarks.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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
from gaspatchio_core.scenarios._auto_batch import memory_budget_bytes
from gaspatchio_core.scenarios._memory import DEFAULTS, IrreducibleCellError

# Point-file thresholds: the largest model-point parquet whose row count is <= the key.
_POINTS_8 = 8
_POINTS_1K = 1_000
_POINTS_10K = 10_000

# (arm, n_scenarios, n_points). Calibrated from the A.2 test-drive: portfolio arm
# capped at 10 scenarios so the first CI dry-run fits the 120-min budget. 1000x100K
# remains deliberately excluded (~10 hr). See the test-drive report for the math.
GRID = [
    ("scen-scaling", 10, 1_000),
    ("scen-scaling", 100, 1_000),
    ("scen-scaling", 1_000, 1_000),
    ("port-scaling", 10, 10_000),
    ("port-scaling", 10, 100_000),
]


def _points_path(n_points: int) -> Path:
    if n_points <= _POINTS_8:
        return L5_DIR / "model_points.parquet"
    if n_points <= _POINTS_1K:
        return L5_DIR / "model_points_1k.parquet"
    if n_points <= _POINTS_10K:
        return L5_DIR / "model_points_10k.parquet"
    return Path(__file__).resolve().parent / "model_points" / "l5_100k.parquet"


def run_cell(n_scenarios: int, points_path: Path) -> dict:
    """Run one (scenarios x points) cell via for_each_scenario(auto); return metrics."""
    l5 = load_l5_model()
    returns = generate_stochastic_returns(n_scenarios, n_months=180, seed=12345)
    mp = pl.read_parquet(points_path)
    model_fn = make_stochastic_model_fn(l5, returns)
    budget_mb = memory_budget_bytes(DEFAULTS.target_memory_fraction) / 1024**2
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, n_scenarios + 1)),
        model_fn=model_fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    _print_probe_ladder(result.selection, budget_mb)
    m = read_result_metrics(result, n_scenarios, mp.height)
    m["n_scenarios"] = n_scenarios
    m["n_points"] = mp.height
    return m


def _print_probe_ladder(selection: object, budget_mb: float) -> None:
    """Print the search's measured rungs to stderr — the memory story per cell.

    One line per cell makes gating decisions auditable from the CI log alone
    (which probe ran, what it peaked at, what fit) — the exact evidence that
    was missing when the ungated-probe OOM had to be reconstructed forensically.
    """
    probed = getattr(selection, "probed", None) or []
    rungs = "; ".join(
        f"b{p.batch}/{p.engine}="
        + (f"{p.peak_mb:.0f}MB" if p.peak_mb is not None else "?")
        + ("+fits" if p.fits else "!fits")
        for p in probed
    )
    print(f"  probes: [{rungs}] budget={budget_mb:.0f}MB", file=sys.stderr)


def _pts_label(n: int) -> str:
    return f"{n // _POINTS_1K}K" if n >= _POINTS_1K else str(n)


def cell_to_json_rows(arm: str, cell: dict) -> list[dict]:
    """One cell -> four github-action-benchmark rows (zero-padded scen for ordering)."""
    stub = f"{arm}/{_pts_label(cell['n_points'])}pts-{cell['n_scenarios']:04d}sc"
    return [
        {"name": f"{stub}-wall", "unit": "seconds", "value": cell["wall_s"]},
        {"name": f"{stub}-rss", "unit": "MB", "value": cell["peak_rss_mb"]},
        {
            "name": f"{stub}-throughput",
            "unit": "scenario-points/sec",
            "value": cell["throughput"],
        },
        {"name": f"{stub}-batch", "unit": "count", "value": cell["batch_size"]},
    ]


def _cell_worker(n_scenarios: int, n_points: int) -> None:
    """Child-process entry: run ONE cell, print ``CELL {json}`` (or ``CELLSKIP``) to stdout.

    Each cell runs in a fresh interpreter so it gets a clean allocator baseline
    and the full memory budget. In a shared process, earlier cells leave
    retained allocator pools behind: later probes are served from those pools
    (RSS never grows, so measured peaks read ~0 and the search's gate is blind)
    and the budget shrinks because base RSS includes the pools. Observed live:
    ``probes: [b1/streaming=0MB+fits]`` and a budget collapsing 7148->3094 MB
    across cells. Same pattern as scenario_batch_search_bench's floor workers.
    """
    try:
        cell = run_cell(n_scenarios, _points_path(n_points))
    except IrreducibleCellError as e:
        # The sizer refusing a cell that does not fit this box is the library
        # working as designed (free runners are smaller than the perf runner).
        print(f"CELLSKIP irreducible on this box: {e}", flush=True)
        return
    print("CELL " + json.dumps(cell), flush=True)


# Per-cell wall clock cap: the heaviest legitimate cell runs ~6 min on CI, so a
# cell still going at 30 min is wedged. Bounding it keeps one hung cell from
# eating the whole job timeout and losing every OTHER cell's output with it.
_CELL_TIMEOUT_S = 1800


def _run_cell_in_subprocess(arm: str, n_scen: int, n_pts: int) -> dict | None:
    """Spawn one fresh-process cell; return its metrics, or None for a tolerated loss.

    stderr is inherited so the child's probe-ladder lines stream straight into
    the CI log. Failure handling is deliberately asymmetric:

    * signal kill (negative returncode, e.g. kernel OOM-kill) or timeout -- the
      isolation working as intended: lose that one cell, keep the run;
    * clean nonzero exit with no result -- a real error (import failure, bug;
      its traceback already streamed on inherited stderr): raise, so CI fails
      instead of publishing an incomplete benchmark as green.
    """
    import subprocess  # noqa: PLC0415

    cmd = [sys.executable, str(Path(__file__).resolve()), "--cell", str(n_scen), str(n_pts)]
    try:
        p = subprocess.run(  # noqa: S603
            cmd, stdout=subprocess.PIPE, text=True, check=False, timeout=_CELL_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        print(
            f"SKIP {arm} {n_scen}x{n_pts} -- cell exceeded {_CELL_TIMEOUT_S}s and was killed",
            file=sys.stderr,
        )
        return None
    for ln in p.stdout.splitlines():
        if ln.startswith("CELLSKIP "):
            print(f"SKIP {arm} {n_scen}x{n_pts} -- {ln[len('CELLSKIP '):]}", file=sys.stderr)
            return None
        if ln.startswith("CELL "):
            return json.loads(ln[len("CELL "):])
    if p.returncode < 0:
        print(
            f"SKIP {arm} {n_scen}x{n_pts} -- cell process killed by signal "
            f"{-p.returncode} (likely OOM)",
            file=sys.stderr,
        )
        return None
    msg = (
        f"cell {arm} {n_scen}x{n_pts} exited {p.returncode} without a result -- "
        "a real error, not a memory kill; see its traceback on stderr above"
    )
    raise RuntimeError(msg)


def main() -> None:
    """Run the full grid and emit the github-action-benchmark JSON array to stdout."""
    rows: list[dict] = []
    for arm, n_scen, n_pts in GRID:
        path = _points_path(n_pts)
        if not path.exists():
            print(f"SKIP {arm} {n_scen}x{n_pts} -- {path} missing", file=sys.stderr)
            continue
        print(f"{arm} {n_scen}sc x {n_pts}pts ...", file=sys.stderr)
        cell = _run_cell_in_subprocess(arm, n_scen, n_pts)
        if cell is None:
            continue
        print(
            f"  wall={cell['wall_s']}s rss={cell['peak_rss_mb']}MB "
            f"batch={cell['batch_size']} ({cell['batch_size_resolution']})",
            file=sys.stderr,
        )
        rows.extend(cell_to_json_rows(arm, cell))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cell":
        _cell_worker(int(sys.argv[2]), int(sys.argv[3]))
    else:
        main()
