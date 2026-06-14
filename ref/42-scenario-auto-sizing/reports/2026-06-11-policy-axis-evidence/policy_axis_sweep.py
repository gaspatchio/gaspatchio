# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Policy-axis batch-size sweep for ``run_aggregated``.

THE QUESTION this answers: is the per-run wall time of ``run_aggregated``
**monotonic** in batch size B (bigger batch -> fewer plan-builds + folds ->
faster, until memory caps it) or **U-shaped** (an interior optimum, the way
``for_each_scenario`` is because of its cross-join)?

* Monotonic  => "largest B that fits memory" is already speed-optimal; the policy
  axis needs no ladder search, only the hardcoded 384 MB working-set cap scrutinised
  and the single-seed extrapolation validated.
* U-shaped   => an interior optimum exists; a search (like the scenario axis) is
  warranted.

It also records, for each n: how much wall actually moves across the whole B range
(is sizing even a speed lever, or purely a memory-safety knob?), the peak-RSS range,
and where ``batch_size="auto"`` lands relative to the measured optimum.

Each (n, B) point runs in a FRESH SUBPROCESS so peak RSS is clean (process-global,
sticky). Points run SEQUENTIALLY; local scales are capped at 10K (push 100K to the
CI runner). Reuses the real L4 (reconciled-lifelib) model via ``aggregated_runner``.

Usage:
    uv run python ref/42-scenario-auto-sizing/reports/2026-06-11-policy-axis-evidence/policy_axis_sweep.py
    # restrict scales:
    uv run python .../policy_axis_sweep.py --scales 1000
    # single point (internal; used to spawn clean workers):
    uv run python .../policy_axis_sweep.py --worker 10000 2500
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
BENCH_DIR = REPO_ROOT / "evals" / "benchmarks"

# Within 5% of the fastest counts as "flat" (measurement noise floor).
_FLAT_TOL = 0.05


def _ladder(n: int) -> list[int]:
    """Batch sizes spanning full-batch -> many-small-batches, to expose the curve."""
    cands = {n, n // 2, n // 4, n // 8, n // 16, max(1, n // 40), max(1, n // 100)}
    return sorted(b for b in cands if b >= 1)


def _worker(n: int, b: str) -> None:
    """Run ONE (n, B) point in this process and print a single JSON line."""
    # Silence the loguru firehose so the captured stdout stays a single tiny line.
    from loguru import logger

    logger.remove()
    sys.path.insert(0, str(BENCH_DIR))
    import psutil
    from aggregated_runner import (
        l4_model_points,
        load_l4_model,
        make_model_fn,
        run_batched,
    )

    from gaspatchio_core.scenarios._auto_batch import (
        bounded_seed_size,
        memory_budget_bytes,
    )
    from gaspatchio_core.scenarios._memory import DEFAULTS

    model_fn = make_model_fn(load_l4_model())
    mp = l4_model_points(n)
    batch_size: int | str = "auto" if b == "auto" else int(b)
    # Record the budget + free RAM the sizer sees (mp already resident) so "peak is
    # ~0.4x of free" is a recorded fact, not reverse-engineered from the peak.
    budget_mb = memory_budget_bytes(DEFAULTS.target_memory_fraction) / 1024**2
    avail_mb = psutil.virtual_memory().available / 1024**2
    res = run_batched(model_fn, mp, batch_size=batch_size)
    n_batches = math.ceil(n / max(1, res.batch_size))
    print(
        json.dumps(
            {
                "n": n,
                "requested": b,
                "resolved_B": res.batch_size,
                "n_batches": n_batches,
                "wall_s": res.time_s,
                "peak_mb": res.peak_mb,
                "seed": bounded_seed_size(n),  # the bounded measurement sample
                "budget_mb": budget_mb,  # bytes/1024^2 the sizer may target
                "avail_mb": avail_mb,  # free RAM at sizing time
            }
        )
    )


def _run_point(n: int, b: str) -> dict[str, float] | None:
    """Spawn a clean worker for (n, B); parse its JSON line, or None on failure."""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(Path(__file__).resolve()), "--worker", str(n), str(b)],
        capture_output=True,  # worker prints ONE small line (loguru silenced) -> safe
        text=True,
        cwd=str(BENCH_DIR),
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        print(
            f"  ! point n={n} B={b} produced no result (rc={proc.returncode})\n"
            f"    stderr tail: {proc.stderr.strip()[-400:]}",
            file=sys.stderr,
        )
        return None
    return json.loads(lines[-1])


def _verdict(rows: list[dict[str, float]]) -> str:
    """Classify the wall-vs-B curve as monotonic, flat, or U-shaped."""
    by_b = sorted(rows, key=lambda r: r["resolved_B"])
    walls = [r["wall_s"] for r in by_b]
    fastest = min(walls)
    slowest = max(walls)
    argmin_b = by_b[walls.index(fastest)]["resolved_B"]
    largest_b = by_b[-1]["resolved_B"]
    spread = (slowest / fastest) if fastest else float("inf")

    # Is the largest-B point within the flat tolerance of the global fastest?
    largest_wall = by_b[-1]["wall_s"]
    largest_is_best = (largest_wall - fastest) <= _FLAT_TOL * fastest

    if spread <= 1 + _FLAT_TOL:
        shape = f"FLAT (wall varies only {spread:.2f}x across the whole B range)"
    elif largest_is_best:
        shape = (
            f"MONOTONIC — fastest at the LARGEST batch (B={largest_b}); "
            f"smallest-B is {spread:.2f}x slower"
        )
    else:
        shape = (
            f"U-SHAPED — interior optimum at B={argmin_b} "
            f"(largest B={largest_b} is {largest_wall / fastest:.2f}x slower; "
            f"slowest overall {spread:.2f}x)"
        )
    return shape


def _report(n: int, rows: list[dict[str, float]], auto: dict[str, float] | None) -> None:
    """Print the per-n table, the auto pick, and the shape verdict."""
    print(f"\n=== run_aggregated @ {n} policies — batch-size sweep ===")
    print(f"{'B (req)':>10}{'B (resolved)':>14}{'batches':>9}{'wall_s':>10}{'peak_MB':>10}")
    for r in sorted(rows, key=lambda r: r["resolved_B"]):
        print(
            f"{r['requested']!s:>10}{r['resolved_B']:>14}{r['n_batches']:>9}"
            f"{r['wall_s']:>10.3f}{r['peak_mb']:>10.1f}"
        )
    if auto is not None:
        print(
            f"{'auto':>10}{auto['resolved_B']:>14}{auto['n_batches']:>9}"
            f"{auto['wall_s']:>10.3f}{auto['peak_mb']:>10.1f}"
            f"   <- auto pick (seed={auto.get('seed', '?')})"
        )
    # Sizing relationship from the recorded budget — print even in auto-only mode
    # (before the empty-rows guard) so the budget/peak link is always visible.
    bud = (auto or {}).get("budget_mb")
    if bud:
        av = (auto or {}).get("avail_mb") or 0.0
        frac = (bud / av) if av else 0.0
        print(
            f"  budget ≈ {bud:.0f} MB (~{frac:.0%} of {av:.0f} MB free); "
            f"peak ceiling ≈ budget/1.3 ≈ {bud / 1.3:.0f} MB"
        )
    if not rows:
        if auto is None:
            print("  (no successful points)")
        return
    print(f"  VERDICT: {_verdict(rows)}")

    # Peak range — the memory cost of going bigger.
    by_b = sorted(rows, key=lambda r: r["resolved_B"])
    print(
        f"  peak grows {by_b[0]['peak_mb']:.0f} MB (B={by_b[0]['resolved_B']}) "
        f"-> {by_b[-1]['peak_mb']:.0f} MB (B={by_b[-1]['resolved_B']})"
    )
    if auto is not None:
        fastest = min(r["wall_s"] for r in rows)
        auto_pen = auto["wall_s"] / fastest if fastest else float("inf")
        print(
            f"  auto resolved B={auto['resolved_B']} "
            f"({auto['wall_s']:.3f}s = {auto_pen:.2f}x the measured fastest)"
        )


def main() -> None:
    """Sweep B for each requested scale and print the curve + verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", nargs=2, metavar=("N", "B"))
    parser.add_argument(
        "--scales",
        type=int,
        nargs="+",
        default=[1000, 10000],
        help="policy counts to sweep (default 1000 10000; keep <=10K locally)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write structured JSON results here (for CI artifacts)",
    )
    parser.add_argument(
        "--max-batch",
        type=int,
        default=None,
        help=(
            "cap the EXPLICIT ladder rungs at this batch size (skip larger ones that "
            "would exceed RAM at huge scale, e.g. the full-batch rung at 1M). 'auto' "
            "is self-safe (it sizes to the budget) and is always run."
        ),
    )
    parser.add_argument(
        "--auto-only-scales",
        type=int,
        nargs="*",
        default=[],
        help=(
            "scales for which ONLY 'auto' is measured (skip the explicit ladder). Use "
            "for huge scales (e.g. 10M) where the ladder rungs are too slow but 'auto' "
            "must still demonstrate it stays bounded."
        ),
    )
    args = parser.parse_args()

    if args.worker is not None:
        _worker(int(args.worker[0]), args.worker[1])
        return

    auto_only = set(args.auto_only_scales)
    summary: dict[str, dict[str, object]] = {}
    for n in args.scales:
        rows: list[dict[str, float]] = []
        rungs = (
            []
            if n in auto_only
            else [b for b in _ladder(n) if args.max_batch is None or b <= args.max_batch]
        )
        for b in rungs:
            point = _run_point(n, str(b))
            if point is not None:
                rows.append(point)
                print(
                    f"  n={n} B={point['resolved_B']:>6} "
                    f"wall={point['wall_s']:.3f}s peak={point['peak_mb']:.0f}MB",
                    file=sys.stderr,
                )
        auto = _run_point(n, "auto")
        _report(n, rows, auto)
        summary[str(n)] = {
            "points": rows,
            "auto": auto,
            "verdict": (
                _verdict(rows)
                if rows
                else ("auto-only" if auto else "no successful points")
            ),
        }

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2))
        print(f"\nwrote structured results to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
