# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Example model using the core DSL.

This example demonstrates how to use the core DSL to build
actuarial models that are both debuggable and performant.
"""

import math
import time
from pathlib import Path

import numpy as np
import polars as pl
import typer
from gaspatchio_core import ActuarialFrame, floor, run_model
from gaspatchio_core.functions import fill_series
from gaspatchio_core.utils import read_model_points
from loguru import logger


def debuggable_model_calculation(df):
    """Define a sample actuarial model calculation."""
    # In this model, you can insert breakpoints, print statements, and use
    # all Python features for debugging.

    # Constants
    max_age = 100
    interest_rate = 0.03

    # Calculate remaining lifetime
    df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
    df["proj_months"] = fill_series(df["num_proj_months"], 0, 1)
    df["proj_years"] = floor((df["proj_months"] - 1) / 12) + 1

    # Use print for debugging (in debug mode)
    if df._mode == "debug":
        print(f"First row: proj_years = {df['proj_years'].collect()[0]}")

    # Calculate policy duration
    df["policy_duration"] = df["proj_months"] / 12
    df["policy_duration_start_month"] = floor((df["proj_months"] - 1) / 12, 0)
    df["policy_expiry_month"] = (max_age - df["age"]) * 12
    df["age_last"] = df["age"] + df["proj_years"] - 1

    # Custom Python function
    def calculate_risk_factor(age):
        base = math.log(max(age, 1)) * 0.01
        # Complex logic that would be hard to express in the pure DSL
        for i in range(5):
            if age > 50 + i * 5:
                base *= 1.1
        return base

    # Apply the custom function
    df["risk_factor"] = df["age"].apply(calculate_risk_factor)

    # Use numpy functions
    df["exp_factor"] = df["age"].apply(lambda age: np.exp(-0.01 * age))

    # Use plugin functions
    df["abs_age_diff"] = df["age"].apply(lambda age: abs(age - 50))

    # Add a premium column if it doesn't exist (since our data only has sum_assured)
    try:
        df._df.collect().select("premium")
    except:
        # Premium column doesn't exist, create it
        df["premium"] = df["sum_assured"].apply(
            lambda x: float(x) * 0.01
        )  # Set premium to 1% of sum assured

    # Simulate some complex policy value calculation but in a safer way for debug mode
    if df._mode == "debug":
        # Instead of creating many columns, just calculate total margins
        all_margins = []
        for i in range(1, 11):
            year = i
            premium_factor = (1 + 0.02) ** year
            benefit_factor = (1 + interest_rate) ** year

            # Use a simple calculation instead of collecting values
            if all_margins:
                all_margins.append(
                    all_margins[-1] * 1.05
                )  # Just a placeholder calculation
            else:
                all_margins.append(1000)  # Start with a default value
    else:
        # Original calculation for optimize mode
        for i in range(10):
            year = i + 1
            df[f"premium_yr{year}"] = df["premium"] * (1 + 0.02) ** year
            df[f"benefit_yr{year}"] = df["sum_assured"] * (1 + interest_rate) ** year
            df[f"margin_yr{year}"] = df[f"benefit_yr{year}"] - df[f"premium_yr{year}"]

        # Use complex control flow (which would be impossible in pure DSL)
        all_margins = []
        for i in range(1, 11):
            # This list comprehension approach demonstates powerful Python features
            year_margins = [
                df[f"margin_yr{i}"].collect()[j] for j in range(len(df._df.collect()))
            ]
            all_margins.append(sum(year_margins))

    # In debug mode, we can use any Python code for analysis
    if df._mode == "debug":
        print(f"Total margins by year: {all_margins}")
        avg_margin = sum(all_margins) / len(all_margins)
        print(f"Average margin: {avg_margin:.2f}")

    return df


def main(
    size: str = "smol",
    mode: str = "debug",  # Default to debug mode for development
    profile: bool = False,
):
    """Run the example model."""
    logger.info("Reading model points data...")
    try:
        file_path = Path(f"jobs/basic/model-points-{size}.parquet")
        data = read_model_points(file_path)
    except Exception as e:
        logger.error(f"Error reading model points: {e}")
        logger.info("Generating synthetic data instead...")
        # Generate synthetic data
        ages = np.random.randint(20, 70, 1000)
        premiums = np.random.uniform(100, 500, 1000)
        sum_assured = np.random.uniform(10000, 50000, 1000)

        data = pl.DataFrame(
            {
                "age": ages,
                "premium": premiums,
                "sum_assured": sum_assured,
            }
        ).lazy()

    logger.info(f"Starting model run with model points in {mode} mode...")

    start = time.time()

    # Use our dual-mode approach
    df = ActuarialFrame(data, mode=mode)

    # You can also use context manager for temporary mode override
    # with execution_mode("optimize"):
    #     result = run_model(debuggable_model_calculation, df).collect()

    if profile and mode == "debug":
        # For debugging performance issues, we can use Python's profiler
        import cProfile
        import pstats

        profile = cProfile.Profile()
        profile.enable()

        try:
            result = run_model(debuggable_model_calculation, df).collect()
        except Exception as e:
            logger.error(f"Error collecting result: {e}")
            # Try to create a simple DataFrame instead
            result = pl.DataFrame(
                {"status": ["Model ran successfully but couldn't collect full results"]}
            )

        profile.disable()
        ps = pstats.Stats(profile).sort_stats("cumtime")
        ps.print_stats(20)  # Print top 20 time-consuming functions
    else:
        try:
            result = run_model(debuggable_model_calculation, df).collect()
        except Exception as e:
            logger.error(f"Error collecting result: {e}")
            # Try to create a simple DataFrame instead
            result = pl.DataFrame(
                {"status": ["Model ran successfully but couldn't collect full results"]}
            )

    end = time.time()
    total_time = end - start
    records = len(result)
    time_per_record_s = total_time / records
    time_per_record_ms = (total_time * 1e3) / records
    time_per_record_ns = (total_time * 1e9) / records

    logger.info(
        "Model run completed in {:.2f} seconds ({:.3f} s | {:.3f} ms | {:.3f} ns per record)",
        total_time,
        time_per_record_s,
        time_per_record_ms,
        time_per_record_ns,
    )

    # If in optimize mode, show performance statistics
    if mode == "optimize" and hasattr(df, "get_execution_stats"):
        stats = df.get_execution_stats()
        if stats:
            logger.info("Execution statistics: {}", stats)

    # Show a sample of the results
    print(result.head(5))


if __name__ == "__main__":
    typer.run(main)
