import time

import polars as pl
import typer
from gaspatchio_core import ActuarialFrame, fill_series, floor, run_model
from gaspatchio_core.utils import read_model_points
from loguru import logger
from typing_extensions import Annotated


def model_calculation(df):
    """
    Define the model calculation using the core DSL.
    """
    # Constants
    max_age = 100

    # Calculations
    df["num_proj_months"] = (max_age - df["age"]) * 12 + 1
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
    file_path = f"jobs/basic/model-points-{size}.parquet"

    start = time.time()
    logger.info("Starting model run with {} model points in {} mode...", size, mode)
    data = read_model_points(file_path)

    # Create ActuarialFrame with specified mode
    df = ActuarialFrame(data, mode=mode)
    result = run_model(model_calculation, df).collect()

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


def test_abs_i64():
    df = read_model_points("jobs/basic/model-points-smol.parquet")

    print(df)

    result = (
        df.with_columns(num_proj_months=(pl.lit(100).sub(pl.col("age")).mul(12).add(1)))
        .with_columns(proj_months=fill_series("num_proj_months"))
        .collect()
    )
    # result = result.with_columns(proj_months=fill_series("abs_proj_months"))
    print(result)


if __name__ == "__main__":
    app = typer.Typer()
    app.command()(main)
    app.command()(test_abs_i64)
    app()
