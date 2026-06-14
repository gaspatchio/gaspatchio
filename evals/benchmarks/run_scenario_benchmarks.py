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
    result = for_each_scenario(
        ActuarialFrame(mp),
        scenarios=list(range(1, n_scenarios + 1)),
        model_fn=model_fn,
        aggregations=(Sum("pv_net_cf").alias("total").over("scenario_id"),),
        batch_size="auto",
    )
    m = read_result_metrics(result, n_scenarios, mp.height)
    m["n_scenarios"] = n_scenarios
    m["n_points"] = mp.height
    return m


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


def main() -> None:
    """Run the full grid and emit the github-action-benchmark JSON array to stdout."""
    rows: list[dict] = []
    for arm, n_scen, n_pts in GRID:
        path = _points_path(n_pts)
        if not path.exists():
            print(f"SKIP {arm} {n_scen}x{n_pts} -- {path} missing", file=sys.stderr)
            continue
        print(f"{arm} {n_scen}sc x {n_pts}pts ...", file=sys.stderr)
        cell = run_cell(n_scen, path)
        print(
            f"  wall={cell['wall_s']}s rss={cell['peak_rss_mb']}MB "
            f"batch={cell['batch_size']} ({cell['batch_size_resolution']})",
            file=sys.stderr,
        )
        rows.extend(cell_to_json_rows(arm, cell))
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
