# ABOUTME: Tracing and computation graph utilities for ActuarialFrame
# ABOUTME: Handles debug mode operation capture and query plan logging
# ruff: noqa: SLF001, ANN401, C901, PLR0912, PLR0915, DTZ001
"""Tracing and computation graph utilities for ActuarialFrame."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from loguru import logger

from gaspatchio_core.errors.metadata import (
    TracedOperation,
    capture_source_context,
)
from gaspatchio_core.util import get_default_mode, get_default_verbose

if TYPE_CHECKING:
    from collections.abc import Callable

    import polars as pl

    from gaspatchio_core.frame.base import ActuarialFrame


def log_query_plan(operations: list[Any], frame_df: pl.LazyFrame) -> None:
    """Log the query plan if verbose mode is enabled."""
    if get_default_verbose():
        logger.trace("Computation Graph:")
        for i, operation in enumerate(operations):
            # Handle both old tuple format and new TracedOperation format
            if isinstance(operation, tuple):
                # Legacy format: (name, expr)
                name, expr = operation
                logger.trace(f"  Step {i + 1}: {name} = {expr}")
            else:
                # New format: TracedOperation
                logger.trace(
                    f"  Step {i + 1}: {operation.alias} = {operation.expression}",
                )
                if hasattr(operation, "metadata") and operation.metadata:
                    logger.trace(
                        f"    Source: "
                        f"{operation.metadata.display_filename}:"
                        f"{operation.metadata.line_number}",
                    )
        logger.trace("Optimized Query Plan:")
        try:
            logger.debug(frame_df.explain(optimized=True))
        except Exception:  # noqa: BLE001
            logger.warning("Could not explain query plan")


def build_trace_decorator(frame_instance: ActuarialFrame) -> Callable:  # type: ignore[type-arg]
    """Create trace decorator for a specific ActuarialFrame instance."""

    def decorator(func: Callable) -> Callable:  # type: ignore[type-arg]
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> ActuarialFrame | None:
            mode = get_default_mode()

            if mode == "debug":
                func_name = getattr(func, "__name__", "<unknown>")
                logger.debug(
                    f"Tracing {func_name} in debug mode for enhanced error handling."
                )
                original_tracing_state = frame_instance._tracing
                frame_instance._tracing = True
                frame_instance._computation_graph = []  # Reset for this trace

                try:
                    # Execute function - operations captured via __setitem__
                    result = func(*args, **kwargs)

                    # Operations captured, applied later (collect/profile)
                    captured_operations = frame_instance._computation_graph
                    if captured_operations:
                        logger.debug(
                            f"{len(captured_operations)} operations captured "
                            f"for later application.",
                        )
                        # Log the plan if verbose, but don't apply yet
                        if get_default_verbose() and frame_instance._df is not None:
                            log_query_plan(captured_operations, frame_instance._df)
                    else:
                        logger.debug("No operations captured during trace.")

                    # Return result if model created a new frame, otherwise original
                    return frame_instance if result is None else result

                finally:
                    # Restore original tracing state
                    frame_instance._tracing = original_tracing_state

            elif mode == "optimize":
                func_name = getattr(func, "__name__", "<unknown>")
                logger.debug(f"Running {func_name} in optimize mode.")
                # Disable tracing for immediate execution
                original_tracing_state = frame_instance._tracing
                frame_instance._tracing = False
                try:
                    result = func(*args, **kwargs)
                    return frame_instance if result is None else result
                finally:
                    frame_instance._tracing = original_tracing_state

            else:
                msg = f"Unknown execution mode: {mode}"
                raise ValueError(msg)

        return wrapper

    return decorator


def append_operation_to_graph(
    frame_instance: ActuarialFrame,
    name: str,
    expr: Any,
) -> None:
    """Append operation with metadata to computation graph if tracing enabled."""
    # Fast path: check tracing flag early to avoid overhead when disabled
    if not frame_instance._tracing:
        return

    # Capture source context from the calling code
    # Try different depths to find user's model code (not internal frame code)
    metadata = None
    for depth in range(2, 8):  # Try depths 2-7
        temp_metadata = capture_source_context(depth=depth)
        # Skip internal frame/column files
        if not any(
            internal in temp_metadata.file_name
            for internal in [
                "gaspatchio_core/frame/",
                "gaspatchio_core/column/",
                "gaspatchio_core/errors/",
                "<frozen",
                "site-packages/",
            ]
        ):
            # This looks like user code
            metadata = temp_metadata
            break

    # Fallback to depth 2 if we couldn't find user code
    if metadata is None:
        metadata = capture_source_context(depth=2)

    # Try to infer the expected type of this expression
    expected_dtype = _infer_expression_type(expr, frame_instance)

    # Extract dependencies from the expression
    from gaspatchio_core.frame.graph import extract_dependencies

    dependencies = extract_dependencies(expr)

    # Create TracedOperation
    operation = TracedOperation(
        alias=name,
        expression=expr,
        metadata=metadata,
        expected_dtype=expected_dtype,
        dependencies=dependencies,
    )

    frame_instance._computation_graph.append(operation)  # type: ignore[arg-type]
    logger.trace(
        f"Graph: Added '{name}' = {expr} (type={expected_dtype}, "
        f"deps={dependencies}) at {metadata.display_filename}:"
        f"{metadata.line_number}",
    )


def _infer_expression_type(expr: Any, frame_instance: ActuarialFrame) -> Any:
    """Infer the type that an expression will produce.

    Returns a Polars DataType or None if type cannot be inferred.
    """
    import polars as pl

    if not hasattr(frame_instance, "_computation_graph"):
        return None

    # Build a type map from previous operations in the computation graph
    type_map = {}
    for op in frame_instance._computation_graph:
        if hasattr(op, "alias") and hasattr(op, "expected_dtype") and op.expected_dtype:
            type_map[op.alias] = op.expected_dtype

    # Also add types from the existing schema if available
    try:
        if frame_instance._df is not None:
            schema = frame_instance._df.collect_schema()
            for col_name, dtype in schema.items():
                if col_name not in type_map:
                    type_map[col_name] = dtype
    except Exception as e:  # noqa: BLE001
        logger.trace(f"Could not collect schema for type inference: {e}")

    # Try to infer type using Polars' schema inference with minimal LazyFrame
    try:
        # Create a minimal schema with known types
        if type_map:
            # Create a LazyFrame with one row and the known schema
            dummy_data = {}
            for col_name, dtype in type_map.items():
                if isinstance(dtype, pl.List):
                    # For list types, create list with one dummy element
                    inner_type = dtype.inner if hasattr(dtype, "inner") else pl.Float64
                    # Create appropriate dummy value based on inner type
                    if inner_type == pl.Date:
                        import datetime

                        dummy_data[col_name] = [[datetime.date(2020, 1, 1)]]
                    elif inner_type in (pl.Float64, pl.Float32):
                        dummy_data[col_name] = [[0.0]]
                    elif inner_type in (
                        pl.Int64,
                        pl.Int32,
                        pl.Int16,
                        pl.Int8,
                        pl.UInt64,
                        pl.UInt32,
                        pl.UInt16,
                        pl.UInt8,
                    ):
                        dummy_data[col_name] = [[0]]
                    elif inner_type == pl.Utf8:
                        dummy_data[col_name] = [[""]]
                    elif inner_type == pl.Boolean:
                        dummy_data[col_name] = [[False]]
                    elif inner_type == pl.Datetime:
                        import datetime

                        dummy_data[col_name] = [[datetime.datetime(2020, 1, 1)]]
                    elif inner_type == pl.Time:
                        dummy_data[col_name] = [[pl.time(0, 0, 0)]]
                    elif inner_type == pl.Duration:
                        dummy_data[col_name] = [[pl.duration(days=0)]]
                    else:
                        # Default to empty list if we don't know the type
                        dummy_data[col_name] = [[]]
                # Numeric types
                elif dtype in (pl.Float64, pl.Float32):
                    dummy_data[col_name] = [0.0]
                elif dtype in (
                    pl.Int64,
                    pl.Int32,
                    pl.Int16,
                    pl.Int8,
                    pl.UInt64,
                    pl.UInt32,
                    pl.UInt16,
                    pl.UInt8,
                ):
                    dummy_data[col_name] = [0]
                # String type
                elif dtype == pl.Utf8:
                    dummy_data[col_name] = [""]
                # Boolean type
                elif dtype == pl.Boolean:
                    dummy_data[col_name] = [False]
                # Temporal types
                elif dtype == pl.Date:
                    import datetime

                    dummy_data[col_name] = [datetime.date(2020, 1, 1)]
                elif dtype == pl.Datetime:
                    import datetime

                    dummy_data[col_name] = [datetime.datetime(2020, 1, 1)]
                elif dtype == pl.Time:
                    dummy_data[col_name] = [pl.time(0, 0, 0)]
                elif dtype == pl.Duration:
                    dummy_data[col_name] = [pl.duration(days=0)]
                # Categorical type
                elif isinstance(dtype, pl.Categorical):
                    dummy_data[col_name] = ["category1"]
                # Null type
                elif dtype == pl.Null:
                    dummy_data[col_name] = [None]
                else:
                    # For any other types, let Polars infer from None
                    logger.trace(
                        f"Unknown dtype {dtype} for column {col_name}, using None"
                    )
                    dummy_data[col_name] = [None]

            dummy_df = pl.DataFrame(dummy_data).lazy()

            # Apply the expression and let Polars tell us the resulting type
            result_df = dummy_df.select(expr.alias("_test_col"))
            result_schema = result_df.collect_schema()
            inferred_type = result_schema.get("_test_col")

            logger.trace(f"Type inference for expression: {expr} -> {inferred_type}")
            return inferred_type
        # If we have no type map, try with the existing schema
        if frame_instance._df is not None:
            result_df = frame_instance._df.select(expr.alias("_test_col"))
            result_schema = result_df.collect_schema()
            return result_schema.get("_test_col")
    except Exception as e:  # noqa: BLE001
        # If type inference fails, log it and return None
        logger.trace(f"Type inference failed for expression: {expr}, error: {e}")

    return None
