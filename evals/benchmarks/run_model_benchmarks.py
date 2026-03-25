#!/usr/bin/env python3
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
import time
import traceback
import tracemalloc
from pathlib import Path
from types import ModuleType

import polars as pl

from gaspatchio_core import ActuarialFrame

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


def bench_l4(mp_path: Path) -> dict:
    """Benchmark L4 model."""
    mp = pl.read_parquet(mp_path)

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    result_af = _l4_model.main(af)
    _ = result_af.collect()

    elapsed = time.perf_counter() - start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {"time_s": round(elapsed, 3), "peak_mb": round(peak_mem / 1024 / 1024, 1)}


def bench_l5(mp_path: Path) -> dict:
    """Benchmark L5 model (with 3 scenarios = 3x effective rows)."""
    from gaspatchio_core.scenarios import with_scenarios

    mp = pl.read_parquet(mp_path)
    scenarios = ["BASE", "UP", "DOWN"]

    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()

    af = ActuarialFrame(mp)
    af = with_scenarios(af, scenarios)
    result_af = _l5_model.main(af)
    _ = result_af.collect()

    elapsed = time.perf_counter() - start
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {"time_s": round(elapsed, 3), "peak_mb": round(peak_mem / 1024 / 1024, 1)}


BENCHMARKS = {
    "L4-base": {"level": "4-lifelib", "gen_key": "4", "func": bench_l4},
    "L5-base": {"level": "5-scenarios", "gen_key": "5", "func": bench_l5},
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
                print(f"{metrics['time_s']}s, {metrics['peak_mb']}MB", file=sys.stderr)

                results.append({
                    "name": f"{bench_name}/{size_label}-points",
                    "unit": "seconds",
                    "value": metrics["time_s"],
                })
                results.append({
                    "name": f"{bench_name}/{size_label}-memory",
                    "unit": "MB",
                    "value": metrics["peak_mb"],
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
