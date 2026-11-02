# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Model runner utilities for actuarial model execution and profiling."""

import contextlib
import importlib.util
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import polars as pl
from loguru import logger
from pydantic import BaseModel, ConfigDict

from gaspatchio import ActuarialFrame
from gaspatchio import run_model as dsl_run_model
from gaspatchio._beside import importable_beside
from gaspatchio.errors.policy_locator import telling_the_policy_id_column
from gaspatchio.frame._across_rows import ReadAcrossRowsError, frame_is_not_the_book
from gaspatchio.util import read_model_points


class ModelRunConfig(BaseModel):
    """Configuration for running a GasPatchIO model."""

    directory: Path
    model_file: str = "model.py"
    model_points_file: str = "model-points.parquet"
    mode: Literal["debug", "optimize"] = "debug"
    model_function_name: str = "main"
    id_column_name: str | None = None


class RunMetrics(BaseModel):
    """Metrics collected during a model run."""

    total_time_s: float
    profile_info: Any
    tracked_column_order: list[str] | None = None


class ModelRunResult(BaseModel):
    """Result object containing outputs from a model run."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: Literal["success", "error"] = "success"
    result: pl.DataFrame | None = None
    metrics: RunMetrics | None = None
    errors: list[str] | None = None
    error_message: str | None = None
    # The frame the model finished on, beside the values it produced. The
    # values alone cannot answer a question about a node -- which definition
    # of a twice-written column a number belongs to, what a compiled
    # rollforward's balance was -- because those are facts about the
    # calculation log rather than about the columns. ``run-model
    # --every-node`` reads them off this.
    frame: ActuarialFrame | None = None
    # How a single-policy run reached its policy, where it did not run that
    # policy alone: the read across rows that sent it to the whole book, and
    # the book it ran -- "ran the 4-policy book and selected policy 1". None
    # where the policy ran alone, or for a run of the whole book.
    route: str | None = None


def load_model_from_path(
    model_path: Path | str, function_name: str = "life_model"
) -> Callable[..., Any]:
    """Dynamically load a model function from a Python file."""
    model_path = Path(model_path)
    if not model_path.exists():
        msg = f"Model file not found: {model_path}"
        raise FileNotFoundError(msg)

    spec = importlib.util.spec_from_file_location("model_module", model_path)
    if spec is None or spec.loader is None:
        msg = f"Could not load module spec from {model_path}"
        raise ImportError(msg)

    model_module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses, get_type_hints, and pickle resolve a
    # module's string annotations by looking its name up in sys.modules.
    sys.modules[spec.name] = model_module
    try:
        # With the model's own directory importable, as `python model.py`
        # has it: a helper beside the model is imported by its bare name.
        with importable_beside(model_path):
            spec.loader.exec_module(model_module)
    except BaseException:
        # Don't leave a half-executed module shadowing the next load.
        del sys.modules[spec.name]
        raise

    # Look specifically for the specified function name
    model_function = getattr(model_module, function_name, None)
    if callable(model_function):
        # Checked callable just above; getattr itself is typed Any.
        found: Callable[..., Any] = model_function
        return found

    msg = f"No function named '{function_name}' found in {model_path}"
    raise ValueError(msg)


def transpose_single_policy_result(result_df: pl.DataFrame) -> pl.DataFrame:
    """Transpose a single policy result for vector column display.

    Args:
        result_df: A DataFrame containing a single row with vector columns

    Returns:
        A transposed DataFrame with one row per element in the longest vector

    """
    if len(result_df) != 1:
        msg = "Transposition only works with a single policy result"
        raise ValueError(msg)

    # Detect List columns via DataFrame schema (more reliable than runtime checks)
    schema = result_df.schema
    vector_cols = [
        col_name for col_name, dtype in schema.items() if dtype.base_type() == pl.List
    ]
    scalar_cols = [
        col_name for col_name in result_df.columns if col_name not in vector_cols
    ]

    # Get the first (and only) row as a dictionary
    row = result_df.row(0, named=True)

    # Determine max length from vector columns
    max_length = 0
    for col_name in vector_cols:
        value = row[col_name]
        if value is not None:
            max_length = max(max_length, len(value))

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


def _model_failure_message(error: Exception, *, mode: str) -> str:
    """Return what to tell somebody whose model did not run.

    One wording, wherever a command runs a model and has to say why it
    stopped. A debug run is diagnosed first -- the source location is put on
    the exception itself, which is where the verbose panel and the message
    below both read it from -- and a suppressed failure to diagnose leaves
    the plain message rather than replacing one error with another.

    The missing-attribute case carries the contract that causes it. A model
    whose ``main()`` reads a column its ``if __name__`` block attached runs
    standalone and dies here, and the bare attribute error reads as a typo
    hint, which is the one thing it is not.
    """
    # Imported here rather than at module scope: the error path is the only
    # caller, and the diagnosis machinery is not worth a run that succeeds.
    from gaspatchio.errors.exception_utils import (  # noqa: PLC0415
        enhance_exception_with_location,
    )

    if mode == "debug":
        with contextlib.suppress(Exception):
            enhance_exception_with_location(error)

    message = str(error)
    if "'ActuarialFrame' object has no attribute" in message:
        message += (
            " Note: this command builds the frame from the model-points file"
            " and calls main() with only those columns — a column attached"
            " outside main() (for example in an `if __name__ == '__main__':`"
            " block) is not visible here. Create it inside main() or add it"
            " to the model points."
        )
    return message


def _execute_model_run(
    config: ModelRunConfig,
    data_lazy: pl.LazyFrame,
    model_func: Callable[..., Any],
    policy_id: str | None = None,
    *,
    across_rows_raises: bool = False,
) -> ModelRunResult:
    """Execute the model run logic.

    ``across_rows_raises`` lets a refusal of a read across rows
    (:class:`~gaspatchio.frame._across_rows.ReadAcrossRowsError`) leave this
    function as raised, rather than as an error result, so that a caller
    that ran one policy alone can run the whole book instead.
    """
    start_time = time.time()
    errors = []
    result_df = pl.DataFrame()
    profile_info = None
    run_description = (
        f"Single policy run (ID: {policy_id})" if policy_id else "Full model run"
    )

    # Check if data_lazy is empty *after* potential filtering
    # Note: head(1).collect() used instead of deprecated fetch(1)
    if data_lazy.head(1).collect().is_empty():
        error_suffix = f" for Policy ID '{policy_id}'" if policy_id else ""
        err_msg = f"No data found{error_suffix} after filtering."
        errors.append(err_msg)
        # Return error result instead of raising
        return ModelRunResult(
            status="error",
            result=None,
            metrics=None,
            errors=errors,
            error_message=err_msg,
        )

    # 5. Run the model using ActuarialFrame and dsl_run_model
    logger.debug("Setting up ActuarialFrame in {} mode...", config.mode)
    actuarial_frame = ActuarialFrame(data_lazy, mode=config.mode)

    logger.debug("Running model function...")
    try:
        # A list kernel's refusal names the policy by the column the run was
        # told, where it was told one (errors/policy_locator.py).
        with telling_the_policy_id_column(config.id_column_name):
            # Use returned frame - models may create new ActuarialFrame instances
            result_frame = dsl_run_model(model_func, actuarial_frame)

            # 6. Collect result - profile() in debug, collect() in optimize
            logger.info("Collecting results...")
            if config.mode == "debug":
                # Debug mode: Enable profiling for timing information
                result_df, profile_info = result_frame.profile()
            else:
                # Optimize mode: Fast collection without profiling
                result_df = result_frame.collect()
                # Create empty profile to maintain interface
                profile_info = pl.DataFrame(
                    {
                        "node": [],
                        "start": [],
                        "end": [],
                    }
                )
    except Exception as e:
        if across_rows_raises and _the_read_refused(e) is not None:
            raise
        error_message = _model_failure_message(e, mode=config.mode)

        # Log that model execution failed (without repeating the full error)
        logger.debug("Model execution failed with {}", type(e).__name__)

        # Return error result instead of raising
        return ModelRunResult(
            status="error",
            result=None,
            metrics=None,
            errors=[error_message],
            error_message=error_message,
        )

    # Capture the column order from the ActuarialFrame
    tracked_column_order = actuarial_frame.get_column_order()

    # Reorder the result DataFrame to match the tracked column order
    if tracked_column_order and not result_df.is_empty():
        # Only reorder columns that exist in both the tracked order and the result
        available_columns = result_df.columns
        ordered_columns = [
            col for col in tracked_column_order if col in available_columns
        ]
        # Add remaining columns not in tracked order (safety check)
        remaining_columns = [
            col for col in available_columns if col not in ordered_columns
        ]
        final_column_order = ordered_columns + remaining_columns

        if final_column_order != available_columns:
            logger.debug(
                f"Reordering columns from {available_columns} to {final_column_order}"
            )
            result_df = result_df.select(final_column_order)

    end_time = time.time()
    total_time = end_time - start_time
    record_count = len(result_df) if not result_df.is_empty() else 0
    logger.success(
        f"{run_description} finished in {total_time:.2f}s "
        f"producing {record_count} result records."
    )

    metrics = RunMetrics(
        total_time_s=total_time,
        profile_info=profile_info,
        tracked_column_order=tracked_column_order,
    )
    return ModelRunResult(
        status="success",
        result=result_df,
        frame=result_frame,
        metrics=metrics,
        errors=errors or None,
        error_message=None,
    )


def run_model(config: ModelRunConfig) -> ModelRunResult:
    """Run actuarial model for all policies and return results."""
    logger.info(f"Starting full model run with config: {config.model_dump()}\n")

    # 1. Construct full paths
    model_path = config.directory / config.model_file
    model_points_path = config.directory / config.model_points_file

    logger.debug(
        f"Constructed model_path in runner: {model_path=}, type: {type(model_path)}",
    )

    # 2. Load model function
    logger.info("Loading model from {}", model_path)
    model_func = load_model_from_path(model_path, config.model_function_name)

    # 3. Read model points (lazy)
    logger.info("Reading model points data from {}", model_points_path)
    data_lazy = read_model_points(model_points_path)

    # Delegate execution to helper - let enhanced error handling work
    return _execute_model_run(config, data_lazy, model_func)


class PolicyNotFoundError(ValueError):
    """The one policy a single-policy run was asked for cannot be found.

    Raised before the model runs -- no identifier column, a column the book
    does not carry, an id the column does not hold -- so a command can say
    so as a refusal of its command line rather than as a model that raised.
    """


def _cast_policy_id(policy_id: str, col_dtype: pl.DataType) -> int | str:
    """Cast policy ID string to match the column dtype.

    Args:
        policy_id: The policy ID as a string from CLI
        col_dtype: The Polars dtype of the policy ID column

    Returns:
        The policy ID cast to the appropriate type (int or str)

    Raises:
        PolicyNotFoundError: If policy_id cannot be converted to the required type

    """
    int_types = (
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    )
    if col_dtype in int_types:
        try:
            return int(policy_id)
        except ValueError as e:
            err_msg = (
                f"Policy ID '{policy_id}' cannot be converted to integer "
                f"to match column dtype {col_dtype}"
            )
            raise PolicyNotFoundError(err_msg) from e
    # For string/categorical/other types, keep as string
    return policy_id


# Common names for the policy-identifier column, tried in order when the caller
# does not name one explicitly. Matched case-insensitively against the data.
_ID_COLUMN_CANDIDATES = (
    "policy_id",
    "policy_number",
    "policy number",
    "policyid",
    "pol_id",
    "point_id",
    "id",
)


def _resolve_id_column(available: list[str], requested: str | None) -> str:
    """Resolve the policy-ID column, honouring an explicit name or auto-detecting.

    An explicit ``requested`` name must exist in the model points (matched
    case-insensitively); otherwise the refusal lists the available columns.
    When ``requested`` is ``None``, the first common id-column name present in the
    data is used (``policy_id``, ``policy_number``, ...). Only those names are
    read as an identity: a book keyed by some other column -- a workbook's
    ``scenario`` label, a ``variant_id`` -- is refused with the names looked
    for, the columns present and the flag, rather than having one of its
    columns guessed at.

    Args:
        available: Column names present in the model points.
        requested: The column the caller asked for, or None to auto-detect.

    Returns:
        The resolved column name, as it appears in the data.

    Raises:
        PolicyNotFoundError: If the requested column is absent, or none can be
            detected.

    """
    by_lower = {c.lower(): c for c in available}
    if requested is not None:
        if requested in available:
            return requested
        if requested.lower() in by_lower:
            return by_lower[requested.lower()]
        msg = (
            f"Policy ID column '{requested}' not found in the model points. "
            f"Available columns: {available}"
        )
        raise PolicyNotFoundError(msg)
    for candidate in _ID_COLUMN_CANDIDATES:
        if candidate in by_lower:
            return by_lower[candidate]
    msg = (
        "Could not auto-detect a policy ID column from the model points "
        f"(looked for {list(_ID_COLUMN_CANDIDATES)}). "
        f"Available columns: {available}. "
        "Only those names are read as a policy identifier, so a book keyed by "
        "another column -- a scenario or variant label -- needs it named: "
        "--policy-id-column <column>."
    )
    raise PolicyNotFoundError(msg)


def run_single_policy(config: ModelRunConfig, policy_id: str) -> ModelRunResult:
    """Run actuarial model for a single policy and return results."""
    logger.debug(
        f"Starting single policy run for ID: {policy_id} "
        f"with config: {config.model_dump()}\n"
    )

    # 1. Construct full paths
    model_path = config.directory / config.model_file
    model_points_path = config.directory / config.model_points_file

    logger.debug(
        f"Constructed model_path in runner: {model_path=}, type: {type(model_path)}",
    )

    # 2. Load model function
    logger.info("Loading model from {}", model_path)
    model_func = load_model_from_path(model_path, config.model_function_name)

    # 3. Read model points (lazy)
    logger.info("Reading model points data from {}", model_points_path)
    data_lazy = read_model_points(model_points_path)

    # 4. Resolve the policy-ID column (honour an explicit name, else auto-detect)
    schema = data_lazy.collect_schema()
    id_column = _resolve_id_column(list(schema.names()), config.id_column_name)

    # Cast the requested policy_id to match the column dtype
    col_dtype = schema[id_column]
    policy_id_typed = _cast_policy_id(policy_id, col_dtype)
    logger.debug(
        "Filtering for single policy with ID: {} (cast to {} from dtype {}) "
        "in column '{}'",
        policy_id_typed,
        type(policy_id_typed).__name__,
        col_dtype,
        id_column,
    )

    # Check if policy exists before filtering (on the full dataset)
    existing_ids = (
        data_lazy.select(id_column).unique().lazy().collect().get_column(id_column)
    )
    if policy_id_typed not in existing_ids:
        err_msg = (
            f"Policy ID '{policy_id}' not found in column '{id_column}'. "
            f"Available IDs preview: {existing_ids[:10].to_list()}"
        )
        raise PolicyNotFoundError(err_msg)

    filtered_data_lazy = data_lazy.filter(
        pl.col(id_column) == policy_id_typed,
    )
    book_rows = int(data_lazy.select(pl.len()).collect().item())

    # The policy runs alone, inside the guard a batch runner opens: a read
    # across rows answers from the rows in the frame, and here that is one
    # row of the book (spec section 13.2). A model that makes no such read runs as
    # it always did, over one row; a model that does is refused at the line
    # that reads, and the whole book runs instead, the policy selected from
    # it, so the number shown is the run's.
    alone = filtered_data_lazy.collect()
    try:
        with frame_is_not_the_book(
            on_a_scenario_axis=False,
            cut=(
                f"run-single-policy runs policy {policy_id} alone, one row of "
                f"the {book_rows}-policy book"
            ),
            batch=alone,
        ):
            # The row's own values, so the frame the model is handed is the
            # batch the guard judges a rebuilt frame against.
            return _execute_model_run(
                config,
                alone.lazy(),
                model_func,
                policy_id=policy_id,
                across_rows_raises=True,
            )
    except Exception as raised:
        refused = _the_read_refused(raised)
        if refused is None:
            raise
        where = _the_model_line(raised, model_path)

    return _run_the_book_and_select(
        config,
        data_lazy,
        model_func,
        _Selection(
            id_column=id_column,
            policy_id=policy_id,
            typed=policy_id_typed,
            book_rows=book_rows,
            read=refused.read or "a read across rows",
            line=where,
        ),
    )


class _Selection(BaseModel):
    """The policy a single-policy run selects from the book, and why it ran the book."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id_column: str
    policy_id: str
    typed: int | str
    book_rows: int
    read: str
    line: str | None


def _run_the_book_and_select(
    config: ModelRunConfig,
    data_lazy: pl.LazyFrame,
    model_func: Callable[..., Any],
    selection: _Selection,
) -> ModelRunResult:
    """Run the whole book and hand back the selected policy's rows, saying so.

    The second leg of a single-policy run: the model read across rows, so
    one row alone would answer a different calculation. The book runs as
    ``run-model`` runs it, and the policy's rows are selected from what it
    produced. The frame handed back is the book's, so a results file states
    the book that ran. A policy the model's own selection drops from the
    book is refused by name: there is no value of it to show.
    """
    at = "" if selection.line is None else f"{selection.line} "
    route = (
        f"{at}reads across rows ({selection.read}), so this ran the "
        f"{selection.book_rows}-policy book and selected policy "
        f"{selection.policy_id}"
    )
    logger.info(route)
    whole = _execute_model_run(config, data_lazy, model_func)
    if whole.status == "error" or whole.result is None:
        return whole
    values = whole.result
    if selection.id_column not in values.columns:
        message = (
            f"Policy {selection.policy_id} cannot be shown: {route}, but the "
            f"results do not carry {selection.id_column!r}, so the "
            "policy cannot be found among them. Keep the policy id column on "
            "the frame the model returns, or run gspio run-model."
        )
        return _refused_selection(message, whole)
    chosen = values.filter(pl.col(selection.id_column) == selection.typed)
    if chosen.is_empty():
        message = (
            f"Policy {selection.policy_id} is not valued by this model. "
            f"{selection.line or 'The model'} reads across rows "
            f"({selection.read}), so the {selection.book_rows}-policy book "
            "ran, and the model's own selection drops policy "
            f"{selection.policy_id} from it: there is no value of it to show. "
            "gspio run-model shows the policies the model values."
        )
        return _refused_selection(message, whole)
    return whole.model_copy(update={"result": chosen, "route": route})


def _refused_selection(message: str, whole: ModelRunResult) -> ModelRunResult:
    """Return a run of the book whose selected policy cannot be shown, as an error."""
    return ModelRunResult(
        status="error",
        result=None,
        metrics=whole.metrics,
        errors=[message],
        error_message=message,
    )


def _the_read_refused(raised: BaseException) -> ReadAcrossRowsError | None:
    """Return the refusal of a read across rows behind ``raised``, if one is.

    A column assignment re-raises a refusal under a message naming the
    column, keeping the original as its cause, so the chain is walked.
    """
    seen: set[int] = set()
    found: ReadAcrossRowsError | None = None
    current: BaseException | None = raised
    while current is not None and id(current) not in seen:
        if isinstance(current, ReadAcrossRowsError):
            # The re-raised copy carries the message; the original, further
            # down, carries the read it names.
            found = current if found is None or current.read is not None else found
            if current.read is not None:
                return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return found


def _the_model_line(raised: BaseException, model_path: Path) -> str | None:
    """Return ``file:line`` of the model line a refusal was raised from, if found.

    The innermost frame in the model file itself, else the innermost frame
    outside this library and Polars -- a helper beside the model.
    """
    library = Path(__file__).resolve().parent
    target = model_path.resolve()
    beside: str | None = None
    for frame in reversed(traceback.extract_tb(raised.__traceback__)):
        place = Path(frame.filename).resolve()
        if place == target:
            return f"{model_path.name}:{frame.lineno}"
        if beside is None and not (
            place.is_relative_to(library) or "polars" in place.parts
        ):
            beside = f"{place.name}:{frame.lineno}"
    return beside
