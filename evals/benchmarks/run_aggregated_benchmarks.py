# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Benchmark the unified aggregation surface against the full-materialise baseline.

Runs the L4 model at 1K/10K/100K policies three ways (baseline full-materialise,
``run_aggregated`` batched, ``run_to_parquet`` spill) and emits flat JSON for
github-action-benchmark. The honest story this tracks:

* **memory-ratio** (baseline peak / aggregated peak) -- the robust win; grows with
  scale as the batched path caps peak RSS while the baseline holds the full grid.
* **speedup** (baseline wall / aggregated wall) -- *conditional*: <1 on a roomy
  machine (the batched path pays K plan-builds; L4 is plan-build-bound), >1 only
  once the baseline hits memory pressure it would otherwise swap/OOM on.
* **correct** -- 1.0 iff batched aggregates equal the full-materialise aggregates.

Usage:
    uv run python evals/benchmarks/run_aggregated_benchmarks.py
    uv run python evals/benchmarks/run_aggregated_benchmarks.py --skip-100k
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path
from typing import TYPE_CHECKING

# `evals` is not an importable package in this env; add our own dir for the sibling.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregated_runner import compare

if TYPE_CHECKING:
    from aggregated_runner import ScaleComparison

_BENCH = "L4 Aggregation"
_K = 1000
_OUT = Path(__file__).resolve().parent / "aggregated_results" / "benchmark-results.json"


def _scale_label(n: int) -> str:
    return f"{n // _K}K" if n >= _K else str(n)


def _throughput(n: int, secs: float) -> float:
    """Model points per second (the model-bench headline metric)."""
    return round(n / secs, 1) if secs else 0.0


def _rows(cmp: ScaleComparison) -> list[dict[str, object]]:
    """Flat github-action-benchmark rows for one scale."""
    s = _scale_label(cmp.n_policies)
    n = cmp.n_policies
    base_tput = _throughput(n, cmp.baseline.time_s)
    agg_tput = _throughput(n, cmp.aggregated.time_s)
    triples: list[tuple[str, str, float]] = [
        (f"{_BENCH}/{s}-baseline-wall", "seconds", cmp.baseline.time_s),
        (f"{_BENCH}/{s}-baseline-agg-wall", "seconds", cmp.baseline_agg_wall),
        (f"{_BENCH}/{s}-aggregated-wall", "seconds", cmp.aggregated.time_s),
        (f"{_BENCH}/{s}-baseline-throughput", "points/sec", base_tput),
        (f"{_BENCH}/{s}-aggregated-throughput", "points/sec", agg_tput),
        (f"{_BENCH}/{s}-baseline-peak", "MB", cmp.baseline.peak_mb),
        (
            f"{_BENCH}/{s}-baseline-data-mb",
            "MB",
            float(cmp.baseline.extra.get("data_mb", 0.0)),
        ),
        (f"{_BENCH}/{s}-aggregated-peak", "MB", cmp.aggregated.peak_mb),
        (f"{_BENCH}/{s}-memory-ratio", "x", cmp.memory_ratio),
        (f"{_BENCH}/{s}-speedup", "x", cmp.speedup),
        (f"{_BENCH}/{s}-correct", "bool", 1.0 if cmp.correct else 0.0),
    ]
    if cmp.spill is not None:
        spill_tput = _throughput(n, cmp.spill.time_s)
        triples.append((f"{_BENCH}/{s}-spill-wall", "seconds", cmp.spill.time_s))
        triples.append((f"{_BENCH}/{s}-spill-throughput", "points/sec", spill_tput))
        triples.append((f"{_BENCH}/{s}-spill-peak", "MB", cmp.spill.peak_mb))
    return [{"name": n, "unit": u, "value": v} for n, u, v in triples]


def main() -> None:
    """Run the aggregation benchmark across scales and write/print the JSON."""
    parser = argparse.ArgumentParser(description="Run run_aggregated benchmarks")
    parser.add_argument("--skip-100k", action="store_true", help="Skip the 100K scale")
    args = parser.parse_args()

    sizes = [1_000, 10_000]
    if not args.skip_100k:
        sizes.append(100_000)

    results: list[dict[str, object]] = []
    for size in sizes:
        label = _scale_label(size)
        try:
            cmp = compare(size)
        except Exception as exc:  # noqa: BLE001 — record the failure, keep going
            print(f"{_BENCH}/{label}: ERROR {exc}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            results.append(
                {
                    "name": f"{_BENCH}/{label}-baseline-wall",
                    "unit": "seconds",
                    "value": -1,
                }
            )
            continue
        verdict = "PASS" if cmp.correct else "FAIL"
        print(
            f"{_BENCH}/{label}: correctness={verdict} "
            f"vs materialise-then-aggregate ({cmp.baseline_agg_wall}s): "
            f"speed={cmp.speedup}x, mem={cmp.memory_ratio}x lighter "
            f"[pure projection {cmp.baseline.time_s}s; "
            f"aggregated {cmp.aggregated.time_s}s/{cmp.aggregated.peak_mb}MB]",
            file=sys.stderr,
        )
        results.extend(_rows(cmp))

    output = json.dumps(results, indent=2)
    print(output)  # stdout for CI `tee`
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(output)


if __name__ == "__main__":
    main()
