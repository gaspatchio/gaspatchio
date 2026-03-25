#!/usr/bin/env python3
# ruff: noqa: INP001, T201
"""Run the L4 model for benchmarking.

L4's model.py has no __main__ block. This script loads model points,
calls main(), and prints timing information.

Usage:
    uv run python tutorial/level-4-lifelib/base/run_benchmark.py
    uv run python tutorial/level-4-lifelib/base/run_benchmark.py --model-points model_points_1k.parquet
"""

import argparse
import time
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame

MODEL_DIR = Path(__file__).resolve().parent

# Import the model
import sys
sys.path.insert(0, str(MODEL_DIR))
import model  # noqa: E402


def main() -> None:
    """Run the L4 model and print timing."""
    parser = argparse.ArgumentParser(description="Run L4 model benchmark")
    parser.add_argument(
        "--model-points",
        default="model_points.parquet",
        help="Model points file (default: model_points.parquet)",
    )
    args = parser.parse_args()

    mp_path = MODEL_DIR / args.model_points
    print(f"Loading: {mp_path}")

    start = time.perf_counter()
    mp = pl.read_parquet(mp_path)
    load_time = time.perf_counter() - start
    print(f"  Model points: {len(mp)} rows ({load_time:.3f}s)")

    start = time.perf_counter()
    af = ActuarialFrame(mp)
    result_af = model.main(af)
    result = result_af.collect()
    run_time = time.perf_counter() - start

    print(f"  Run time: {run_time:.3f}s")
    print(f"  Output: {result.shape}")
    print(result.select(["point_id", "product_id", "pv_net_cf"]).head(5))


if __name__ == "__main__":
    main()
