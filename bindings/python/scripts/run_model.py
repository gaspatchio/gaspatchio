# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Run an actuarial model from a directory.

This script allows running actuarial models directly from a directory containing:
- model.py: Python file with a model function
- model-points.parquet: Parquet file with model points data

Usage:
    python -m gaspatchio-core.scripts.run_model <directory>

    # Specify model file or model-points file
    python -m gaspatchio-core.scripts.run_model <directory> --model-file custom_model.py --model-points-file custom_points.parquet

    # Compare debug and optimize modes
    python -m gaspatchio-core.scripts.run_model compare-modes <directory>

    # Run model for a single policy
    python -m gaspatchio-core.scripts.run_model <directory> --policy-id POLICY123

    # Run model for a single policy and save transposed result to CSV
    python -m gaspatchio-core.scripts.run_model <directory> --policy-id POLICY123 --output-csv result.csv
"""

import logging
import os
import sys
from pathlib import Path

import polars as pl
import typer
from gaspatchio_core.runner import (
    ModelRunConfig,
    ModelRunResult,
    transpose_single_policy_result,
)
from gaspatchio_core.runner import (
    run_model as execute_runner_run_model,
)
from loguru import logger
from typing_extensions import Annotated

# Set the RUST_LOG environment variable before importing any modules
os.environ["RUST_LOG"] = "debug"  # or "info" if you only want info logs
os.environ["GASPATCHIO_RUST_LOG"] = "debug"  # This is checked in the Rust code

# Configure loguru to intercept standard logging messages
# this is important for catching logs from the Rust code using pyo3-log
logger.remove()  # Remove the default handler
logger.add(sys.stderr, level="TRACE")  # Add a handler that outputs all levels


# Configure loguru as an interceptor for the standard logging module
class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


# Configure the standard logging to use our interceptor - set lowest possible level (0)
logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

# Configure default root logger as a last resort catch-all
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.handlers = [InterceptHandler()]

# Also set all other loggers to DEBUG level just to be sure
for name in logging.root.manager.loggerDict:
    logging_logger = logging.getLogger(name)
    logging_logger.setLevel(logging.DEBUG)
    for handler in list(logging_logger.handlers):
        logging_logger.removeHandler(handler)
    logging_logger.addHandler(InterceptHandler())

logger.info("Configured all loggers to DEBUG level")

# Configure specific loggers for Rust code
for logger_name in ["gaspatchio_core", "gaspatchio_core.lookup"]:
    rust_logger = logging.getLogger(logger_name)
    rust_logger.setLevel(logging.DEBUG)


# Now import the modules that might use Rust logging


# Define Typer app globally
app = typer.Typer(
    help="Run GasPatchIO actuarial models from a directory.",
    context_settings={"help_option_names": ["-h", "--help"]},
)


@app.command()
def main(
    directory: Annotated[
        str,
        typer.Argument(
            help="Directory containing model.py and model-points.parquet",
        ),
    ],
    model_file: Annotated[
        str,
        typer.Option(
            "--model-file",
            "-m",
            help="Model file (if not 'model.py')",
        ),
    ] = "model.py",
    model_points_file: Annotated[
        str,
        typer.Option(
            "--model-points-file",
            "-p",
            help="Model points file (if not 'model-points.parquet')",
        ),
    ] = "model-points.parquet",
    mode: Annotated[
        str,
        typer.Option(
            help="Execution mode: 'debug' or 'optimize'",
            case_sensitive=False,
        ),
    ] = "debug",
    policy_id: Annotated[
        str,
        typer.Option(
            "--policy-id",
            "-i",
            help="Run model for a single policy with the specified ID",
        ),
    ] = None,
    output_file: Annotated[
        str,
        typer.Option(
            "--output-file",
            "-o",
            help="Output Parquet file path (optional)",
        ),
    ] = None,
    output_csv: Annotated[
        str | None,  # Allow None
        typer.Option(
            "--output-csv",
            "-c",
            help="Output *directory* for single policy CSV (transposed). Saves as '{policy_id}_gs_output.csv' inside this directory. If --policy-id is used and this is not set, defaults to current directory. Mutually exclusive with --output-file when using --policy-id.",
        ),
    ] = None,
    model_function_name: Annotated[
        str,
        typer.Option(
            "--model-function-name",
            help="Name of the model function to run within the model file",
        ),
    ] = "life_model",
    first_n: Annotated[
        int,
        typer.Option(
            "--first-n",
            "-f",
            help="Number of first columns to display",
        ),
    ] = 5,
    last_n: Annotated[
        int,
        typer.Option(
            "--last-n",
            "-l",
            help="Number of last columns to display",
        ),
    ] = 10,
    rows: Annotated[
        int,
        typer.Option(
            "--rows",
            "-r",
            help="Number of rows to display",
        ),
    ] = 15,
    id_column_name: Annotated[
        str,
        typer.Option(
            "--id-column-name",
            "--id-col",
            help="Name of the column used for policy identification",
        ),
    ] = "Policy number",
):
    # Create configuration object
    config = ModelRunConfig(
        directory=Path(directory),
        model_file=model_file,
        model_points_file=model_points_file,
        mode=mode,
        model_function_name=model_function_name,
        id_column_name=id_column_name,
    )

    # Execute the model run using the runner function
    try:
        logger.debug(f"Runner Config: {config=}")
        # Get the ModelRunResult object
        run_result: ModelRunResult = execute_runner_run_model(config)
    except (FileNotFoundError, ValueError, Exception) as e:
        logger.error("Model execution failed: {}", e)
        raise typer.Exit(code=1)

    # Check for errors reported by the runner
    if run_result.errors:
        logger.error("Runner reported errors:")
        for err in run_result.errors:
            logger.error(f"- {err}")
        raise typer.Exit(code=1)

    # Extract results from the result object
    result_df = run_result.result
    profile_info = run_result.metrics.profile_info
    total_time = run_result.metrics.total_time_s

    # --- Add filtering based on policy_id if provided ---
    if policy_id:
        logger.info(
            f"Filtering results for policy ID: {policy_id} using column: {id_column_name}"
        )
        try:
            # Ensure the ID column exists
            if id_column_name not in result_df.columns:
                logger.error(
                    f"ID column '{id_column_name}' not found in results. Available columns: {result_df.columns}"
                )
                raise typer.Exit(code=1)

            # Attempt to cast policy_id to the dtype of the ID column for safe comparison
            id_col_dtype = result_df[id_column_name].dtype
            try:
                typed_policy_id = pl.Series([policy_id]).cast(id_col_dtype)[0]
                logger.debug(
                    f"Comparing with typed policy ID: {typed_policy_id} (type: {type(typed_policy_id)}) against column type {id_col_dtype}"
                )
            except Exception as cast_error:
                logger.warning(
                    f"Could not cast provided policy_id '{policy_id}' to column type {id_col_dtype}. Attempting direct comparison. Error: {cast_error}"
                )
                typed_policy_id = policy_id  # Fallback to original string

            result_df = result_df.filter(pl.col(id_column_name) == typed_policy_id)
            logger.info(
                f"Found {len(result_df)} row(s) after filtering for policy ID {policy_id}"
            )
            if len(result_df) == 0:
                logger.warning(f"Policy ID {policy_id} not found in the results.")
            elif len(result_df) > 1:
                logger.warning(
                    f"Multiple rows found for policy ID {policy_id}. Check your ID column and data."
                )

        except Exception as filter_error:
            logger.error(
                f"Error filtering results for policy ID {policy_id}: {filter_error}"
            )
            raise typer.Exit(code=1)
    # --- End filtering ---

    # Display profile info
    print("\n--- Profile Info ---")
    print(profile_info)
    print("--------------------\n")

    # Calculate and log timing
    records = len(result_df)
    time_per_record_s = total_time / records if records > 0 else 0
    time_per_record_ms = (total_time * 1e3) / records if records > 0 else 0
    time_per_record_ns = (total_time * 1e9) / records if records > 0 else 0
    logger.info(
        "(From CLI) Model run completed in {:.2f} seconds ({:.3f} s | {:.3f} ms | {:.3f} ns per record)",
        total_time,
        time_per_record_s,
        time_per_record_ms,
        time_per_record_ns,
    )

    # Handle output file/display logic
    if output_file:
        output_path = output_file
        logger.info("Writing results to Parquet file: {}", output_path)
        # Use original full column order if available, otherwise just use available columns
        cols_to_write = (
            getattr(run_result.metrics, "tracked_column_order", None)
            or result_df.columns
        )
        result_df.select(cols_to_write).write_parquet(output_path)
        logger.info("Results saved successfully.")
    else:
        # Determine column order - use tracked order from metrics if available, using getattr
        tracked_column_order = (
            getattr(run_result.metrics, "tracked_column_order", None) or []
        )
        final_result_columns = (
            result_df.columns
        )  # Columns in the (potentially filtered) df
        # Use tracked order, but only columns that actually exist in the final df
        available_ordered_columns = [
            col for col in tracked_column_order if col in final_result_columns
        ]
        # Add any columns present in final df but not in tracked_order
        available_ordered_columns.extend(
            [
                col
                for col in final_result_columns
                if col not in available_ordered_columns
            ]
        )

        # Calculate columns to print based on -f and -l BEFORE checking for policy_id
        first_cols = available_ordered_columns[:first_n]
        last_cols = available_ordered_columns[-last_n:]
        # Ensure columns are unique if first_n + last_n > total columns
        combined_unique_cols_set = set(first_cols)
        combined_unique_cols = first_cols + [
            col for col in last_cols if col not in combined_unique_cols_set
        ]

        # Ensure selected columns actually exist before deciding what to print
        # Handle case where there are fewer columns than first_n + last_n
        if not combined_unique_cols:
            final_cols_to_print = available_ordered_columns
        else:
            final_cols_to_print = [
                col for col in combined_unique_cols if col in result_df.columns
            ]

        saved_to_file = False
        # Check policy_id again - now len(result_df) should be 1 if filtering was successful and ID was unique
        if policy_id and len(result_df) == 1:
            logger.info("Transposing single policy result")
            # Ensure transpose function gets the correctly filtered (single row) df
            transposed_result = transpose_single_policy_result(result_df)
            logger.info("Transposed result has {} rows", len(transposed_result))

            # Determine columns to print for transposed result
            transposed_columns = transposed_result.columns
            first_transposed_cols = transposed_columns[:first_n]
            last_transposed_cols = transposed_columns[-last_n:]
            combined_transposed_set = set(first_transposed_cols)
            final_transposed_cols_to_print = first_transposed_cols + [
                col
                for col in last_transposed_cols
                if col not in combined_transposed_set
            ]

            logger.debug(
                f"Selected columns for transposed print (-f {first_n}, -l {last_n}): {final_transposed_cols_to_print}"
            )

            # Check if --output-csv was specified
            if output_csv is not None:
                csv_dir = Path(output_csv) or Path(
                    "."
                )  # Default to current dir if empty string
                csv_dir.mkdir(parents=True, exist_ok=True)
                csv_path = csv_dir / f"{policy_id}_gs_output.csv"
                logger.info(f"Writing transposed result to CSV: {csv_path}")
                # Write only the selected columns
                transposed_result.select(final_transposed_cols_to_print).write_csv(
                    csv_path
                )
                saved_to_file = True  # Flag that we saved
            else:
                saved_to_file = False  # Ensure flag is false if not saving CSV

            if not saved_to_file:
                pl.Config.set_tbl_width_chars(1500)
                pl.Config.set_fmt_str_lengths(30)
                pl.Config.set_tbl_cols(-1)  # Let Polars decide column wrapping
                pl.Config.set_tbl_rows(
                    rows
                )  # Use the --rows param for transposed output
                with pl.Config(tbl_cols=-1, tbl_rows=rows):
                    print("\nTransposed Result (Columns filtered by -f/-l):")
                    # --- CORRECTED: Select columns before printing ---
                    print(transposed_result.select(final_transposed_cols_to_print))

            else:
                logger.info("Transposed results saved to CSV, skipping print.")
        else:
            # Print the (potentially ID-filtered but not transposed) results
            if len(result_df) == 0 and policy_id:
                logger.info("No data to display for the specified policy ID.")
            elif len(result_df) > 0:
                # Use the column selection calculated before the policy_id check for non-transposed output
                with pl.Config(
                    tbl_cols=-1,  # Show all columns initially to select from
                    tbl_rows=rows,
                    tbl_width_chars=1500,
                    fmt_str_lengths=30,
                ):
                    print(
                        "\nResult (Columns ordered by assignment - best effort, filtered by -f/-l):"
                    )
                    if not final_cols_to_print:
                        logger.warning(
                            "No columns selected or available to display based on -f/-l settings."
                        )
                        print(
                            result_df
                        )  # Print dataframe with default columns if selection fails
                    else:
                        print(result_df.select(final_cols_to_print))
            else:
                logger.info("No results to display.")


# Run the Typer app
if __name__ == "__main__":
    app()
