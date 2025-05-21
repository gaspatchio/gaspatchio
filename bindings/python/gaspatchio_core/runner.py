import importlib.util
import time
from pathlib import Path
from typing import Any, List, Literal, Optional

import polars as pl
from loguru import logger
from pydantic import BaseModel, ConfigDict

from gaspatchio_core import ActuarialFrame
from gaspatchio_core import run_model as dsl_run_model
from gaspatchio_core.util import read_model_points


class ModelRunConfig(BaseModel):
    """Configuration for running a GasPatchIO model."""

    directory: Path
    model_file: str = "model.py"
    model_points_file: str = "model-points.parquet"
    mode: Literal["debug", "optimize"] = "debug"
    model_function_name: str = "life_model"
    id_column_name: str = "Policy number"


class RunMetrics(BaseModel):
    """Metrics collected during a model run."""

    total_time_s: float
    profile_info: Any


class ModelRunResult(BaseModel):
    """Result object containing outputs from a model run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    result: pl.DataFrame
    metrics: RunMetrics
    errors: Optional[List[str]] = None


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


def _execute_model_run(
    config: ModelRunConfig,
    data_lazy: pl.LazyFrame,
    model_func: callable,
    policy_id: Optional[str] = None,
) -> ModelRunResult:
    """Internal helper to execute the model run logic."""
    start_time = time.time()
    errors = []
    result_df = pl.DataFrame()
    profile_info = None
    run_description = (
        f"Single policy run (ID: {policy_id})" if policy_id else "Full model run"
    )

    # Check if data_lazy is empty *after* potential filtering
    if data_lazy.fetch(1).is_empty():
        error_suffix = f" for Policy ID '{policy_id}'" if policy_id else ""
        err_msg = f"No data found{error_suffix} after filtering."
        logger.error(err_msg)
        errors.append(err_msg)
        # Skip actual model execution if no data
        raise ValueError(err_msg)

    # 5. Run the model using ActuarialFrame and dsl_run_model
    logger.info("Setting up ActuarialFrame in {} mode...", config.mode)
    df = ActuarialFrame(data_lazy, mode=config.mode)
    # df.show_query_plan(True)

    logger.info("Running model function...")
    dsl_run_model(model_func, df)

    # 6. Collect the result and profile
    logger.info("Collecting results...")
    result_df, profile_info = df.profile()

    end_time = time.time()
    total_time = end_time - start_time
    record_count = len(result_df) if not result_df.is_empty() else 0
    logger.success(
        f"{run_description} finished in {total_time:.2f} seconds producing {record_count} result records."
    )

    metrics = RunMetrics(total_time_s=total_time, profile_info=profile_info)
    return ModelRunResult(
        result=result_df, metrics=metrics, errors=errors if errors else None
    )


def run_model(config: ModelRunConfig) -> ModelRunResult:
    """Loads model and points, runs the model for all policies, and returns the ModelRunResult."""
    logger.info(f"Starting full model run with config: {config.model_dump()}\n")
    try:
        # 1. Construct full paths
        model_path = config.directory / config.model_file
        model_points_path = config.directory / config.model_points_file

        logger.debug(
            f"Constructed model_path in runner: {model_path=}, type: {type(model_path)}"
        )

        # 2. Load model function
        logger.info("Loading model from {}", model_path)
        model_func = load_model_from_path(model_path, config.model_function_name)

        # 3. Read model points (lazy)
        logger.info("Reading model points data from {}", model_points_path)
        data_lazy = read_model_points(model_points_path)

        # Delegate execution to helper
        return _execute_model_run(config, data_lazy, model_func)

    except Exception as e:
        logger.opt(exception=True).error("Error during model setup")
        # Return an error result if setup fails
        metrics = RunMetrics(total_time_s=0.0, profile_info=None)
        return ModelRunResult(
            result=pl.DataFrame(), metrics=metrics, errors=[f"Setup Error: {str(e)}"]
        )


def run_single_policy(config: ModelRunConfig, policy_id: str) -> ModelRunResult:
    """Loads model and points, runs the model for a single policy, and returns the ModelRunResult."""
    logger.info(
        f"Starting single policy run for ID: {policy_id} with config: {config.model_dump()}\n"
    )
    errors = []  # Initialize errors list here for early exit checks

    try:
        # 1. Construct full paths
        model_path = config.directory / config.model_file
        model_points_path = config.directory / config.model_points_file

        logger.debug(
            f"Constructed model_path in runner: {model_path=}, type: {type(model_path)}"
        )

        # 2. Load model function
        logger.info("Loading model from {}", model_path)
        model_func = load_model_from_path(model_path, config.model_function_name)

        # 3. Read model points (lazy)
        logger.info("Reading model points data from {}", model_points_path)
        data_lazy = read_model_points(model_points_path)

        # 4. Filter model points for the specified policy_id (lazy)
        logger.info("Filtering for single policy with ID: {}", policy_id)
        try:
            policy_id_int = int(policy_id)
        except ValueError as e:
            err_msg = f"Policy ID must be an integer, got: {policy_id}"
            logger.error(err_msg)
            errors.append(err_msg)
            raise ValueError(err_msg) from e

        # Check if policy exists before filtering (on the full dataset)
        existing_ids = (
            data_lazy.select(config.id_column_name)
            .unique()
            .lazy()
            .collect()
            .get_column(config.id_column_name)
        )
        if policy_id_int not in existing_ids:
            err_msg = (
                f"Policy ID '{policy_id}' not found in column '{config.id_column_name}'. "
                f"Available IDs preview: {existing_ids[:10].to_list()}"
            )
            logger.error(err_msg)
            errors.append(err_msg)
            raise ValueError(err_msg)

        filtered_data_lazy = data_lazy.filter(
            pl.col(config.id_column_name) == policy_id_int
        )

        # Delegate execution to helper
        return _execute_model_run(
            config, filtered_data_lazy, model_func, policy_id=policy_id
        )

    except Exception as e:
        # Capture setup/filtering errors
        logger.error(
            f"Error during single policy setup/filtering (ID: {policy_id}): {e}"
        )
        # Add error if not already added by validation checks
        if not errors:
            errors.append(f"Setup/Filter Error (ID: {policy_id}): {str(e)}")
        # Return an error result
        metrics = RunMetrics(total_time_s=0.0, profile_info=None)
        return ModelRunResult(result=pl.DataFrame(), metrics=metrics, errors=errors)
