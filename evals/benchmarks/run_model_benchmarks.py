#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Run end-to-end model benchmarks at different scales.

Runs L4 and L5 tutorial models at 8/1K/10K/100K model points.
Measures wall-clock time. Outputs JSON for github-action-benchmark.

Usage:
    uv run python evals/benchmarks/run_model_benchmarks.py
    uv run python evals/benchmarks/run_model_benchmarks.py --skip-100k
"""

import argparse
import gc
import importlib.util
import json
import sys
import threading
import time
import traceback
from pathlib import Path
from types import ModuleType

import polars as pl

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from gaspatchio_core import ActuarialFrame


class CpuMonitor:
    """Sample per-core CPU usage in a background thread."""

    def __init__(self, interval: float = 0.1) -> None:
        self.interval = interval
        self.samples: list[list[float]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not HAS_PSUTIL:
            return
        self.samples.clear()
        self._stop.clear()
        # Prime psutil (first call returns 0)
        psutil.cpu_percent(percpu=True)
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        if not HAS_PSUTIL or self._thread is None:
            return {}
        self._stop.set()
        self._thread.join(timeout=2)
        self._thread = None
        return self._summarize()

    def _sample(self) -> None:
        while not self._stop.is_set():
            self.samples.append(psutil.cpu_percent(percpu=True))
            self._stop.wait(self.interval)

    def _summarize(self) -> dict:
        if not self.samples:
            return {}
        n_cores = len(self.samples[0])
        n_samples = len(self.samples)
        # Average utilization per core across all samples
        core_avgs = [
            sum(s[c] for s in self.samples) / n_samples for c in range(n_cores)
        ]
        avg_util = sum(core_avgs) / n_cores
        active_cores = sum(1 for a in core_avgs if a > 10.0)
        peak_core = max(core_avgs)
        return {
            "avg_cpu_pct": round(avg_util, 1),
            "active_cores": active_cores,
            "total_cores": n_cores,
            "peak_core_pct": round(peak_core, 1),
        }

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TUTORIAL_DIR = REPO_ROOT / "tutorial"
GENERATED_DIR = Path(__file__).resolve().parent / "model_points"


def _load_model_module(model_path: Path, module_name: str) -> ModuleType:
    """Load a model.py as a named module using importlib to avoid collisions.

    Both L4 and L5 have model.py — using sys.path + import would cause
    the second import to return the cached first module. This loads each
    with a unique module name.
    """
    # Add the model's directory to sys.path so its own imports work
    model_dir = str(model_path.parent)
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    spec = importlib.util.spec_from_file_location(module_name, model_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _get_model_points_path(level: str, gen_key: str, size: int) -> Path:
    """Find the model points file for a given level and size.

    Args:
        level: Tutorial level directory suffix (e.g. "4-lifelib", "5-scenarios")
        gen_key: Short key for generated files (e.g. "4", "5")
        size: Number of model points
    """
    base_dir = TUTORIAL_DIR / f"level-{level}" / "base"

    if size <= 10:
        return base_dir / "model_points.parquet"
    elif size <= 1_000:
        path = base_dir / "model_points_1k.parquet"
        if path.exists():
            return path
        return GENERATED_DIR / f"l{gen_key}_{size // 1000}k.parquet"
    elif size <= 10_000:
        path = base_dir / "model_points_10k.parquet"
        if path.exists():
            return path
        return GENERATED_DIR / f"l{gen_key}_{size // 1000}k.parquet"
    else:
        # 100K — always generated on-the-fly
        return GENERATED_DIR / f"l{gen_key}_{size // 1000}k.parquet"


# Load model modules once with unique names (avoids import collision)
_l4_model = _load_model_module(
    TUTORIAL_DIR / "level-4-lifelib" / "base" / "model.py", "l4_model"
)
_l5_model = _load_model_module(
    TUTORIAL_DIR / "level-5-scenarios" / "base" / "model.py", "l5_model"
)


def _measure_peak_rss_mb() -> float:
    """Get current process RSS in MB. Falls back to tracemalloc if psutil unavailable."""
    if HAS_PSUTIL:
        return psutil.Process().memory_info().rss / 1024 / 1024
    return 0.0


def _measure_data_mb(result_df: pl.DataFrame) -> float:
    """Measure actual list column data memory in MB.

    Counts total f64 elements across all List(Float64) columns.
    This is the "real" data footprint — independent of process overhead.
    """
    total_elements = 0
    for col in result_df.columns:
        dtype = result_df[col].dtype
        if dtype == pl.List(pl.Float64) or dtype == pl.List(pl.Int64):
            total_elements += result_df[col].list.len().sum()
        elif dtype == pl.List(pl.Date) or dtype == pl.List(pl.Datetime):
            total_elements += result_df[col].list.len().sum()
    return round(total_elements * 8 / 1024 / 1024, 1)


def bench_l4(mp_path: Path) -> dict:
    """Benchmark L4 model."""
    mp = pl.read_parquet(mp_path)

    cpu = CpuMonitor()
    gc.collect()
    rss_before = _measure_peak_rss_mb()
    cpu.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    result_af = _l4_model.main(af)
    result_df = result_af.collect()

    elapsed = time.perf_counter() - start
    rss_after = _measure_peak_rss_mb()
    cpu_stats = cpu.stop()
    data_mb = _measure_data_mb(result_df)

    return {"time_s": round(elapsed, 3), "peak_mb": round(rss_after - rss_before, 1), "rss_mb": round(rss_after, 1), "data_mb": data_mb, **cpu_stats}


def bench_l5(mp_path: Path) -> dict:
    """Benchmark L5 model (with 3 scenarios = 3x effective rows)."""
    from gaspatchio_core.scenarios import with_scenarios

    mp = pl.read_parquet(mp_path)
    scenarios = ["BASE", "UP", "DOWN"]

    cpu = CpuMonitor()
    gc.collect()
    rss_before = _measure_peak_rss_mb()
    cpu.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    af = with_scenarios(af, scenarios)
    result_af = _l5_model.main(af)
    result_df = result_af.collect()

    elapsed = time.perf_counter() - start
    rss_after = _measure_peak_rss_mb()
    cpu_stats = cpu.stop()
    data_mb = _measure_data_mb(result_df)

    return {"time_s": round(elapsed, 3), "peak_mb": round(rss_after - rss_before, 1), "rss_mb": round(rss_after, 1), "data_mb": data_mb, **cpu_stats}


BENCHMARKS = {
    "VA Model (GMDB/GMAB)": {"level": "4-lifelib", "gen_key": "4", "func": bench_l4},
    "VA + Scenarios (3x)": {"level": "5-scenarios", "gen_key": "5", "func": bench_l5},
}


def main() -> None:
    """Run all benchmarks and output JSON."""
    parser = argparse.ArgumentParser(description="Run model benchmarks")
    parser.add_argument("--skip-100k", action="store_true", help="Skip 100K benchmarks")
    args = parser.parse_args()

    sizes = [8, 1_000, 10_000]
    if not args.skip_100k:
        sizes.append(100_000)

    # Generate 100K if needed
    if 100_000 in sizes:
        for level_key in ["l4", "l5"]:
            out_path = GENERATED_DIR / f"{level_key}_100k.parquet"
            if not out_path.exists():
                print(f"Generating 100K points for {level_key}...", file=sys.stderr)
                from evals.benchmarks.generate_model_points import generate_model_points

                source_key = "4-lifelib" if level_key == "l4" else "5-scenarios"
                source_path = TUTORIAL_DIR / f"level-{source_key}" / "base" / "model_points.parquet"
                source_mp = pl.read_parquet(source_path)
                scaled = generate_model_points(source_mp, 100_000)
                GENERATED_DIR.mkdir(parents=True, exist_ok=True)
                scaled.write_parquet(out_path)
                print(f"  Written: {out_path}", file=sys.stderr)

    results = []

    for bench_name, config in BENCHMARKS.items():
        for size in sizes:
            mp_path = _get_model_points_path(config["level"], config["gen_key"], size)

            if not mp_path.exists():
                print(f"SKIP {bench_name}/{size} — {mp_path} not found", file=sys.stderr)
                continue

            size_label = f"{size // 1000}K" if size >= 1000 else str(size)
            print(f"{bench_name}/{size_label}: ", end="", flush=True, file=sys.stderr)

            try:
                metrics = config["func"](mp_path)
                throughput = round(size / metrics["time_s"], 1) if metrics["time_s"] > 0 else 0
                active = metrics.get("active_cores", "?")
                total = metrics.get("total_cores", "?")
                avg_cpu = metrics.get("avg_cpu_pct", "?")
                rss = metrics.get("rss_mb", "?")
                data = metrics.get("data_mb", "?")
                print(f"{metrics['time_s']}s, RSS={rss}MB, delta={metrics['peak_mb']}MB, data={data}MB, {throughput} pts/s, {active}/{total} cores ({avg_cpu}% avg)", file=sys.stderr)

                results.append({
                    "name": f"{bench_name}/{size_label}-points",
                    "unit": "seconds",
                    "value": metrics["time_s"],
                })
                results.append({
                    "name": f"{bench_name}/{size_label}-throughput",
                    "unit": "points/sec",
                    "value": throughput,
                })
                results.append({
                    "name": f"{bench_name}/{size_label}-memory",
                    "unit": "MB",
                    "value": metrics["peak_mb"],
                })
                if "data_mb" in metrics:
                    results.append({
                        "name": f"{bench_name}/{size_label}-data-mb",
                        "unit": "MB",
                        "value": metrics["data_mb"],
                    })
                if "rss_mb" in metrics:
                    results.append({
                        "name": f"{bench_name}/{size_label}-rss",
                        "unit": "MB",
                        "value": metrics["rss_mb"],
                    })
                if "active_cores" in metrics:
                    results.append({
                        "name": f"{bench_name}/{size_label}-cores",
                        "unit": "cores",
                        "value": metrics["active_cores"],
                    })
                    results.append({
                        "name": f"{bench_name}/{size_label}-cpu-avg",
                        "unit": "%",
                        "value": metrics["avg_cpu_pct"],
                    })
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
                results.append({
                    "name": f"{bench_name}/{size_label}-points",
                    "unit": "seconds",
                    "value": -1,
                })

    # Output JSON to stdout (clean, for CI piping via tee)
    output = json.dumps(results, indent=2)
    print(output)

    # Also write to file
    output_path = Path(__file__).resolve().parent / "model_points" / "benchmark-results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output)


if __name__ == "__main__":
    main()
