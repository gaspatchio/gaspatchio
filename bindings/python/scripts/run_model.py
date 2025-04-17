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

import importlib.util
import logging
import os
import sys
import time
from pathlib import Path

import polars as pl
import typer
from datacompy import PolarsCompare
from gaspatchio_core.dsl.core import (
    ActuarialFrame,
    run_model,
)
from gaspatchio_core.utils import read_model_points
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


def load_model_from_path(model_path, function_name="life_model"):
    """Dynamically load a model function from a Python file"""
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    spec = importlib.util.spec_from_file_location("model_module", model_path)
    model_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model_module)

    # Look specifically for the specified function name
    if hasattr(model_module, function_name) and callable(
        getattr(model_module, function_name)
    ):
        model_func = getattr(model_module, function_name)
        # Optional: Add a check for argument count if needed
        # if hasattr(model_func, '__code__') and model_func.__code__.co_argcount in [1, 2]:
        #     return model_func
        # else:
        #     raise ValueError(f"Function '{function_name}' found but has incorrect signature.")
        return model_func
    else:
        raise ValueError(f"No function named '{function_name}' found in {model_path}")


def transpose_single_policy_result(result_df):
    """
    Transpose a single policy result so that vector columns are displayed as rows.

    Args:
        result_df: A DataFrame containing a single row with vector columns

    Returns:
        A transposed DataFrame with one row per element in the longest vector
    """
    if len(result_df) != 1:
        raise ValueError("Transposition only works with a single policy result")

    # Get the first (and only) row as a dictionary
    row = result_df.row(0, named=True)

    # Find all list/vector columns and determine the max length
    max_length = 0
    vector_cols = []
    scalar_cols = []

    for col_name, value in row.items():
        if isinstance(value, (list, tuple)) or (
            hasattr(value, "__iter__") and not isinstance(value, (str, bytes))
        ):
            vector_cols.append(col_name)
            max_length = max(max_length, len(value))
        else:
            scalar_cols.append(col_name)

    if max_length == 0:
        logger.info("No vector columns found in result, displaying as-is")
        return result_df

    # Create a new dictionary to build the transposed DataFrame
    transposed_data = {}

    # Spread vector columns across rows
    for col_name in vector_cols:
        vector = row[col_name]
        # If the vector is shorter than max_length, pad with None
        padded_vector = list(vector) + [None] * (max_length - len(vector))
        transposed_data[col_name] = padded_vector

    # Repeat scalar values for each row
    for col_name in scalar_cols:
        transposed_data[col_name] = [row[col_name]] * max_length

    # Create the transposed DataFrame
    return pl.DataFrame(transposed_data)


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
    # Calculate absolute paths
    directory_path = Path(directory)
    model_path = directory_path / model_file
    model_points_path = directory_path / model_points_file

    logger.info("Loading model from {}", model_path)
    model_func = load_model_from_path(model_path, model_function_name)

    logger.info("Reading model points data from {}", model_points_path)
    start = time.time()
    data_lazy = read_model_points(model_points_path)  # Keep it lazy initially

    # Filter for specific policy if requested (still lazy)
    if policy_id:
        logger.info("Filtering for single policy with ID: {}", policy_id)
        try:
            policy_id_int = int(policy_id)
        except ValueError:
            logger.error("Policy ID must be an integer, got: {}", policy_id)
            raise ValueError(f"Policy ID must be an integer, got: {policy_id}")

        # Use the provided ID column name
        # Check if policy exists before filtering
        # Collect only the necessary column to check existence efficiently
        existing_ids = (
            data_lazy.select(id_column_name)
            .unique()
            .collect()
            .get_column(id_column_name)
        )
        if policy_id_int not in existing_ids:
            logger.error(
                "Policy ID '{}' not found in column '{}'. Available IDs preview: {}",
                policy_id,
                id_column_name,
                existing_ids[:10].to_list(),
            )
            raise ValueError(f"Policy ID '{policy_id}' not found in '{id_column_name}'")

        # Now filter the LazyFrame
        data_lazy = data_lazy.filter(pl.col(id_column_name) == policy_id_int)

        # No need to check for multiple policies here, ActuarialFrame handles it

    # Create ActuarialFrame with specified mode
    logger.info("Starting model run in {} mode...", mode)
    logger.info(f"polars thread size: {pl.thread_pool_size()}")

    # Pass the lazy data to ActuarialFrame
    df = ActuarialFrame(data_lazy, mode=mode)

    df.show_query_plan(True)

    # Run the model - this modifies df in place or returns the modified df
    run_model(model_func, df)

    # Collect the result *after* the model run logic is defined in df
    result, profile = df.profile()  # Get the collected DataFrame and profile info

    print(profile)

    end = time.time()
    total_time = end - start
    records = len(result)
    # Handle division by zero if records is 0
    time_per_record_s = total_time / records if records > 0 else 0
    time_per_record_ms = (total_time * 1e3) / records if records > 0 else 0
    time_per_record_ns = (total_time * 1e9) / records if records > 0 else 0
    logger.info(
        "Model run completed in {:.2f} seconds ({:.3f} s | {:.3f} ms | {:.3f} ns per record)",
        total_time,
        time_per_record_s,
        time_per_record_ms,
        time_per_record_ns,
    )

    # Get the tracked column order *from the ActuarialFrame instance*
    tracked_column_order = df.get_column_order()
    # Get columns actually present in the final materialized DataFrame
    final_result_columns = result.columns
    # Filter the tracked order to only include columns that exist in the result
    # This handles cases where columns were defined but not ultimately selected/output
    available_ordered_columns = [
        col for col in tracked_column_order if col in final_result_columns
    ]

    if output_file:
        output_path = Path(output_file)
        logger.info("Writing results to Parquet file: {}", output_path)
        # Select columns in the desired order before writing (optional but good practice)
        result.select(available_ordered_columns).write_parquet(output_path)
        logger.info("Results saved successfully.")
    else:
        saved_to_file = False
        if policy_id and len(result) == 1:
            logger.info("Transposing single policy result")
            # Transpose still operates on the collected 'result' DataFrame
            transposed_result = transpose_single_policy_result(result)
            logger.info("Transposed result has {} rows", len(transposed_result))

            # Determine output path and save if needed
            if output_csv:
                # User specified an output directory for the CSV
                if output_file:
                    logger.error(
                        "--output-file and --output-csv are mutually exclusive when using --policy-id"
                    )
                    raise typer.Exit(code=1)
                output_dir = Path(output_csv)
                output_filename = f"{policy_id}_gs_output.csv"
                output_path = output_dir / output_filename

                # Ensure the directory exists
                output_dir.mkdir(parents=True, exist_ok=True)

                logger.info(
                    "Writing transposed single policy result to specified directory as {}: {}",
                    output_filename,
                    output_path,
                )
                # Use transposed_result for writing
                transposed_result.write_csv(output_path)
                logger.info("Transposed result saved successfully to CSV.")
                saved_to_file = True

                # --- Reconciliation Step ---
                try:
                    source_data_filename = f"{policy_id}_data.csv"
                    source_data_path = output_dir / source_data_filename
                    logger.info(
                        "Attempting to read source data for reconciliation: {}",
                        source_data_path,
                    )

                    if not source_data_path.exists():
                        logger.warning(
                            "Source data file for reconciliation not found: {}. Skipping reconciliation.",
                            source_data_path,
                        )
                    else:
                        ss_df = pl.read_csv(
                            source_data_path
                        )  # Assuming source has a 'month' column
                        # Use transposed_result for reconciliation
                        model_df = transposed_result

                        # Ensure 'month' column exists in both dataframes
                        join_column = (
                            "month"  # <-- Make sure this is the correct column name
                        )
                        if (
                            join_column not in ss_df.columns
                            or join_column not in model_df.columns
                        ):
                            logger.warning(
                                f"Join column '{join_column}' not found in both source and model data. Skipping reconciliation."
                            )
                        else:
                            logger.info("Running reconciliation comparison...")
                            compare = PolarsCompare(
                                ss_df,
                                model_df,
                                join_columns=join_column,
                                abs_tol=0.00001,
                                rel_tol=0,
                                df1_name="source_data",
                                df2_name="model_output",
                            )

                            recon_report = compare.report()

                            recon_dir = output_dir
                            recon_dir.mkdir(parents=True, exist_ok=True)
                            recon_filename = f"{policy_id}_recon.md"
                            recon_path = recon_dir / recon_filename

                            logger.info(
                                "Saving reconciliation report to: {}", recon_path
                            )
                            with open(recon_path, "w") as f:
                                f.write(recon_report)
                            logger.info("Reconciliation report saved successfully.")

                except Exception as e:
                    logger.error(
                        "Error during reconciliation: {}. Reconciliation skipped.", e
                    )
                # --- End Reconciliation Step ---

            # Print transposed result to console if not saved
            if not saved_to_file:
                # Make sure all columns are displayed with good formatting
                pl.Config.set_tbl_width_chars(1500)
                pl.Config.set_fmt_str_lengths(30)  # Increased from 10
                pl.Config.set_tbl_cols(-1)  # Ensure all selected cols can be shown
                pl.Config.set_tbl_rows(rows)  # Use the rows parameter
                with pl.Config(
                    tbl_cols=-1, tbl_rows=rows
                ):  # Reiterate config for clarity/safety
                    print("Transposed Result (Selected Columns):")
                    # Apply first_n and last_n to the *columns* of the transposed result,
                    # using the original assignment order.
                    first_cols = available_ordered_columns[:first_n]
                    last_cols = available_ordered_columns[-last_n:]
                    # Combine first and last, ensuring uniqueness while preserving order
                    combined_unique_cols = first_cols + [
                        col for col in last_cols if col not in first_cols
                    ]
                    # Select the columns from the transposed result
                    print(transposed_result.select(combined_unique_cols))

        elif (
            not output_file
        ):  # Only print original result if not single policy and not saving to Parquet
            # Ensure all columns are displayed when printing to console
            # Print original (non-transposed) result using tracked order
            with pl.Config(
                tbl_cols=-1, tbl_rows=rows, tbl_width_chars=1500, fmt_str_lengths=30
            ):
                print("Result (Columns ordered by assignment):")
                # Use the available_ordered_columns for selection
                first_cols = available_ordered_columns[:first_n]
                last_cols = available_ordered_columns[-last_n:]
                # Combine first and last, ensuring uniqueness while preserving order
                combined_unique_cols = first_cols + [
                    col for col in last_cols if col not in first_cols
                ]
                # Select from the original 'result' DataFrame using the ordered subset
                print(result.select(combined_unique_cols))


def compare_modes(
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
    model_function_name: Annotated[
        str,
        typer.Option(
            "--model-function-name",
            help="Name of the model function to run within the model file",
        ),
    ] = "life_model",
):
    """Compare debug and optimize modes using a dataset from specified directory"""
    # Calculate absolute paths
    directory_path = Path(directory)
    model_path = directory_path / model_file
    model_points_path = directory_path / model_points_file

    logger.info("Loading model from {}", model_path)
    model_func = load_model_from_path(model_path, model_function_name)

    # Read data from parquet file
    print(f"Reading model points from {model_points_path}...")
    data = read_model_points(model_points_path)

    # Run in debug mode
    print("Running in debug mode...")
    df_debug = ActuarialFrame(data, mode="debug")

    debug_start = time.time()
    result_debug = run_model(model_func, df_debug).collect()
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
    result_optimize = run_model(model_func, df_optimize).collect()
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

    # Run if called directly
    try:
        import sys

        if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
            # Check if the first argument is a path (likely a directory)
            if os.path.exists(sys.argv[1]):
                # Call main directly
                policy_id_arg = None
                model_func_name_arg = "life_model"
                # Check if policy-id was provided in command line
                for i, arg in enumerate(sys.argv):
                    if arg in ["--policy-id", "-i"] and i + 1 < len(sys.argv):
                        policy_id_arg = sys.argv[i + 1]
                    # Check if model-function-name was provided
                    if arg == "--model-function-name" and i + 1 < len(sys.argv):
                        model_func_name_arg = sys.argv[i + 1]
                # No need to break, continue checking other args

                main(
                    directory=sys.argv[1],
                    model_file="model.py",
                    model_points_file="model-points.parquet",
                    mode="debug",
                    policy_id=policy_id_arg,
                    model_function_name=model_func_name_arg,
                )
                sys.exit(0)
    except Exception as e:
        logger.error(f"Error running direct mode: {e}")

    # Otherwise use the typer app
    app()
