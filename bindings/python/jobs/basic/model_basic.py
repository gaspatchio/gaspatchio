import time

import typer
from gaspatchio_core.dsl.core import ActuarialFrame, run_model
from gaspatchio_core.plugin import fill_series, floor
from gaspatchio_core.utils import read_model_points
from loguru import logger
from typing_extensions import Annotated


# Define a model function
def simple_model(df):
    """Simple model function that works with the actual model points columns"""
    # Add age squared calculation
    max_age = 100
    df["num_proj_months"] = (max_age - df["age"]) * 12 + 1

    # Using custom plugin functions
    df["proj_months"] = fill_series(df["num_proj_months"], 0, 1)
    df["proj_years"] = floor((df["proj_months"] - 1) / 12) + 1

    df["policy_duration"] = df["proj_months"] / 12
    df["policy_duration_start_month"] = floor((df["proj_months"] - 1) / 12, 0)
    df["policy_expiry_month"] = (max_age - df["age"]) * 12
    df["age_last"] = df["age"] + df["proj_years"] - 1

    return df


def main(
    size: Annotated[
        str,
        typer.Argument(
            show_choices=True,
            case_sensitive=False,
            help="Size of model run: 'smol' or 'milli'",
        ),
    ] = "smol",
    mode: Annotated[
        str,
        typer.Option(
            help="Execution mode: 'debug' or 'optimize'",
            case_sensitive=False,
        ),
    ] = "debug",
):
    logger.info("Reading model points data...")
    file_path = f"gaspatchio-core/jobs/basic/model-points-{size}.parquet"

    start = time.time()
    logger.info("Starting model run with {} model points in {} mode...", size, mode)
    data = read_model_points(file_path)

    # Create ActuarialFrame with specified mode
    df = ActuarialFrame(data, mode=mode)
    result = run_model(simple_model, df).collect()

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

    print(result)


def compare_modes(
    size: Annotated[
        str,
        typer.Argument(
            show_choices=True,
            case_sensitive=False,
            help="Size of model run: 'smol' or 'milli'",
        ),
    ] = "smol",
):
    """Compare debug and optimize modes using a dataset of specified size"""
    # Read data from parquet file
    file_path = f"gaspatchio-core/jobs/basic/model-points-{size}.parquet"
    print(f"Reading model points from {file_path}...")
    data = read_model_points(file_path)

    # Run in debug mode
    print("Running in debug mode...")
    df_debug = ActuarialFrame(data, mode="debug")

    debug_start = time.time()
    result_debug = run_model(simple_model, df_debug).collect()
    debug_end = time.time()
    debug_time = debug_end - debug_start

    records = len(result_debug)

    print(f"Debug mode completed in {debug_time:.4f} seconds")
    print(f"Debug mode: {debug_time / records * 1000:.4f} ms per record")
    print("Debug mode result:")
    print(result_debug)

    # Run in optimize mode
    print("\nRunning in optimize mode...")
    df_optimize = ActuarialFrame(data, mode="optimize")

    optimize_start = time.time()
    result_optimize = run_model(simple_model, df_optimize).collect()
    optimize_end = time.time()
    optimize_time = optimize_end - optimize_start

    print(f"Optimize mode completed in {optimize_time:.4f} seconds")
    print(f"Optimize mode: {optimize_time / records * 1000:.4f} ms per record")
    print("Optimize mode result:")
    print(result_optimize)

    # Verify results are identical
    print("\nResults are identical:", result_debug.equals(result_optimize))

    # Performance comparison
    speedup = debug_time / optimize_time if optimize_time > 0 else float("inf")
    print("\nPerformance comparison:")
    print(f"Debug mode: {debug_time:.4f} seconds")
    print(f"Optimize mode: {optimize_time:.4f} seconds")
    print(
        f"Speedup factor: {speedup:.2f}x (optimize is {speedup:.2f} times faster than debug)"
    )


if __name__ == "__main__":
    app = typer.Typer()
    app.command()(main)
    app.command()(compare_modes)
    app()
