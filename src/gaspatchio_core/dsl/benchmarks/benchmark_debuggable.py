#!/usr/bin/env python
"""
Benchmark for the debuggable DSL.

This script compares the performance of the debug and optimize modes
of the debuggable DSL.
"""

import time

import numpy as np
import polars as pl
from loguru import logger

from gaspatchio_core.dsl.debuggable import (
    ActuarialFrame,
    run_model,
    set_default_mode,
)

# Configure logging
logger.remove()
logger.add(lambda msg: print(msg, flush=True), level="INFO")


def generate_synthetic_data(num_rows=10000):
    """Generate synthetic data for benchmarking."""
    np.random.seed(42)
    return pl.DataFrame(
        {
            "age": np.random.randint(20, 70, num_rows),
            "premium": np.random.uniform(100, 1000, num_rows),
            "sum_assured": np.random.uniform(10000, 100000, num_rows),
            "duration": np.random.randint(1, 20, num_rows),
            "gender": np.random.choice(["M", "F"], num_rows),
            "smoker": np.random.choice([True, False], num_rows),
        }
    )


def simple_model(df):
    """A simple actuarial model for benchmarking."""
    # Basic calculations
    df["age_squared"] = df["age"] * df["age"]
    df["premium_factor"] = df["premium"] / 100.0
    df["sum_assured_factor"] = df["sum_assured"] / 10000.0

    # Derived calculations
    df["risk_factor"] = df["age"] / 100.0
    df["mortality_cost"] = df["sum_assured"] * df["risk_factor"]
    df["expense"] = df["premium"] * 0.05

    # More calculations to stress test
    for i in range(5):
        df[f"premium_{i}"] = df["premium"] * (i + 1)
        df[f"sum_assured_{i}"] = df["sum_assured"] / (i + 1)
        df[f"combined_{i}"] = df[f"premium_{i}"] * df[f"sum_assured_{i}"]

    return df


def complex_model(df):
    """A more complex actuarial model for benchmarking."""
    # Basic calculations
    df["age_squared"] = df["age"] * df["age"]
    df["premium_factor"] = df["premium"] / 100.0
    df["sum_assured_factor"] = df["sum_assured"] / 10000.0

    # Risk factors
    df["age_factor"] = df["age"] / 100.0
    df["duration_factor"] = 1.0 - (0.02 * df["duration"])

    # Gender and smoker adjustments - convert to float
    df["gender_factor"] = df["gender"].apply(lambda x: 0.8 if x == "F" else 1.0)
    df["smoker_factor"] = df["smoker"].apply(lambda x: 1.5 if x else 1.0)

    # Combined risk factor
    df["risk_factor"] = (
        df["age_factor"]
        * df["duration_factor"]
        * df["gender_factor"]
        * df["smoker_factor"]
    )

    # Financial calculations
    df["mortality_cost"] = df["sum_assured"] * df["risk_factor"] / 1000.0
    df["expense"] = df["premium"] * 0.05
    df["commission"] = df["premium"] * 0.1 * (1.0 - 0.05 * df["duration"])
    df["profit_margin"] = (
        df["premium"] - df["mortality_cost"] - df["expense"] - df["commission"]
    )
    df["profit_ratio"] = df["profit_margin"] / df["premium"]

    # Conditional calculations - convert boolean to float
    df["high_risk"] = df["risk_factor"].apply(lambda x: 1.0 if x > 0.5 else 0.0)
    df["extra_premium"] = df["high_risk"] * 200.0
    df["total_premium"] = df["premium"] + df["extra_premium"]

    # More calculations to stress test
    for i in range(10):
        df[f"premium_{i}"] = df["premium"] * (i + 1) / 10.0
        df[f"sum_assured_{i}"] = df["sum_assured"] / (i + 1)
        df[f"combined_{i}"] = df[f"premium_{i}"] * df[f"sum_assured_{i}"]
        df[f"risk_{i}"] = df["risk_factor"] * (i + 1) / 10.0
        df[f"cost_{i}"] = df[f"sum_assured_{i}"] * df[f"risk_{i}"]

    return df


def run_benchmark(data, model_func, num_runs=5, name=""):
    """Run a benchmark for the given model function."""
    # Check if data has required columns
    required_columns = ["age", "premium", "sum_assured"]
    if not all(col in data.columns for col in required_columns):
        logger.error(
            f"Data is missing required columns ({', '.join(required_columns)})"
        )
        return None

    logger.info(f"\nRunning benchmark for {name} model:")

    # Run in debug mode
    debug_times = []
    for i in range(num_runs):
        logger.info(f"Debug mode - Run {i+1}/{num_runs}")
        df_debug = ActuarialFrame(data, mode="debug")
        start_time = time.time()
        result_debug = run_model(model_func, df_debug).collect()
        debug_time = time.time() - start_time
        debug_times.append(debug_time)
        logger.info(f"Debug mode - Run {i+1} completed in {debug_time:.4f} seconds")

    # Run in optimize mode
    optimize_times = []
    for i in range(num_runs):
        logger.info(f"Optimize mode - Run {i+1}/{num_runs}")
        df_optimize = ActuarialFrame(data, mode="optimize")
        start_time = time.time()
        result_optimize = run_model(model_func, df_optimize).collect()
        optimize_time = time.time() - start_time
        optimize_times.append(optimize_time)
        logger.info(
            f"Optimize mode - Run {i+1} completed in {optimize_time:.4f} seconds"
        )

    # Calculate average times
    avg_debug_time = sum(debug_times) / len(debug_times)
    avg_optimize_time = sum(optimize_times) / len(optimize_times)
    speedup = avg_debug_time / avg_optimize_time if avg_optimize_time > 0 else 0

    # Print results
    logger.info(f"\nBenchmark results for {name} model:")
    logger.info(f"Average debug mode time: {avg_debug_time:.4f} seconds")
    logger.info(f"Average optimize mode time: {avg_optimize_time:.4f} seconds")
    logger.info(f"Speedup: {speedup:.2f}x")

    return {
        "debug_times": debug_times,
        "optimize_times": optimize_times,
        "avg_debug_time": avg_debug_time,
        "avg_optimize_time": avg_optimize_time,
        "speedup": speedup,
    }


def main():
    """Run the benchmarks."""
    logger.info("Starting benchmarks...")

    # Set default mode to debug
    set_default_mode("debug")

    # Generate synthetic data with larger size
    logger.info("Generating synthetic data...")
    synthetic_df = generate_synthetic_data(num_rows=50000)

    # Run benchmark with simple model
    logger.info("Running benchmark with simple model...")
    simple_results = run_benchmark(
        synthetic_df, simple_model, num_runs=10, name="Simple"
    )

    # Run benchmark with complex model
    logger.info("Running benchmark with complex model...")
    complex_results = run_benchmark(
        synthetic_df, complex_model, num_runs=10, name="Complex"
    )

    # Print summary
    logger.info("\nBenchmark Summary:")
    logger.info(f"Simple model speedup: {simple_results['speedup']:.2f}x")
    logger.info(f"Complex model speedup: {complex_results['speedup']:.2f}x")

    logger.info("Benchmarks complete!")


if __name__ == "__main__":
    main()
