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
"""

import importlib.util
import logging
import os
import sys
import time
from pathlib import Path

import polars as pl
import typer
from loguru import logger

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
from gaspatchio_core.dsl.core import ActuarialFrame, run_model
from gaspatchio_core.utils import read_model_points
from typing_extensions import Annotated


def load_model_from_path(model_path):
    """Dynamically load a model function from a Python file"""
    model_path = Path(model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    spec = importlib.util.spec_from_file_location("model_module", model_path)
    model_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model_module)

    # Try to find a model function in the module
    model_functions = []
    for attr_name in dir(model_module):
        if attr_name.startswith("__"):
            continue
        attr = getattr(model_module, attr_name)
        if (
            callable(attr)
            and hasattr(attr, "__code__")
            and attr.__code__.co_argcount in [1, 2]
        ):
            model_functions.append(attr)

    if not model_functions:
        raise ValueError(f"No suitable model function found in {model_path}")

    # Use the first model function found
    return model_functions[0]


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
):
    # Calculate absolute paths
    directory_path = Path(directory)
    model_path = directory_path / model_file
    model_points_path = directory_path / model_points_file

    logger.info("Loading model from {}", model_path)
    model_func = load_model_from_path(model_path)

    logger.info("Reading model points data from {}", model_points_path)
    start = time.time()
    data = read_model_points(model_points_path)

    # Filter for specific policy if requested
    if policy_id:
        logger.info("Filtering for single policy with ID: {}", policy_id)
        # Convert policy_id to integer for comparison
        try:
            policy_id_int = int(policy_id)
        except ValueError:
            logger.error("Policy ID must be an integer, got: {}", policy_id)
            raise ValueError(f"Policy ID must be an integer, got: {policy_id}")

        # Use policyholder_nr as the ID column
        id_col = "policyholder_nr"
        filtered_data = data.filter(pl.col(id_col) == policy_id_int)

        # Collect the LazyFrame to get its actual length
        filtered_data_collected = filtered_data.collect()

        if len(filtered_data_collected) == 0:
            available_ids = data.select(id_col).unique().collect()
            logger.error(
                "Policy ID '{}' not found. Available IDs: {}", policy_id, available_ids
            )
            raise ValueError(f"Policy ID '{policy_id}' not found")

        if len(filtered_data_collected) > 1:
            logger.warning(
                "Multiple policies match ID '{}', using the first one", policy_id
            )
            filtered_data = filtered_data.slice(0, 1)

        data = filtered_data

    # Create ActuarialFrame with specified mode
    logger.info("Starting model run in {} mode...", mode)
    df = ActuarialFrame(data, mode=mode)
    # traced_function = df.trace(model_func)

    # result = run_model(traced_function, df).collect()

    result = run_model(model_func, df).collect()
    # View the complete operation log
    operation_log = df.get_operation_log()
    for op in operation_log:
        print(op)

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

    # Transpose the result if a single policy was requested
    if policy_id and len(result) == 1:
        logger.info("Transposing single policy result for better visualization")
        result = transpose_single_policy_result(result)
        logger.info("Transposed result has {} rows", len(result))

        # Make sure all columns are displayed with good formatting
        # Using Polars' built-in configuration to show all columns
        pl.Config.set_tbl_width_chars(
            1500
        )  # Wide enough for all columns but not excessive
        pl.Config.set_fmt_str_lengths(30)  # Reasonable string display length
        pl.Config.set_tbl_cols(-1)  # Show all columns (-1 means no limit)
        pl.Config.set_tbl_rows(15)  # Show more rows for better visibility

    print(result)


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
):
    """Compare debug and optimize modes using a dataset from specified directory"""
    # Calculate absolute paths
    directory_path = Path(directory)
    model_path = directory_path / model_file
    model_points_path = directory_path / model_points_file

    logger.info("Loading model from {}", model_path)
    model_func = load_model_from_path(model_path)

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
                # Check if policy-id was provided in command line
                for i, arg in enumerate(sys.argv):
                    if arg in ["--policy-id", "-i"] and i + 1 < len(sys.argv):
                        policy_id_arg = sys.argv[i + 1]
                        break

                main(
                    directory=sys.argv[1],
                    model_file="model.py",
                    model_points_file="model-points.parquet",
                    mode="debug",
                    policy_id=policy_id_arg,
                )
                sys.exit(0)
    except Exception as e:
        logger.error(f"Error running direct mode: {e}")

    # Otherwise use the typer app
    app()
