# ABOUTME: Tracing and computation graph utilities for ActuarialFrame
# ABOUTME: Handles debug mode operation capture and query plan logging
"""Tracing and computation graph utilities for ActuarialFrame."""

from __future__ import annotations

import datetime
import functools
from typing import TYPE_CHECKING, Any

import polars as pl  # Used at runtime for dtype comparison in type inference
from loguru import logger

from gaspatchio_core.errors.metadata import (
    TracedOperation,
    capture_source_context,
)
from gaspatchio_core.util import get_default_mode, get_default_verbose

if TYPE_CHECKING:
    from collections.abc import Callable

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
        def wrapper(*args: Any, **kwargs: Any) -> ActuarialFrame | None:  # noqa: ANN401
            mode = get_default_mode()

            if mode == "debug":
                func_name = getattr(func, "__name__", "<unknown>")
                logger.debug(
                    f"Tracing {func_name} in debug mode for enhanced error handling."
                )
                original_tracing_state = frame_instance._tracing  # noqa: SLF001
                frame_instance._tracing = True  # noqa: SLF001
                frame_instance._computation_graph = []  # noqa: SLF001  # Reset for this trace

                try:
                    # Execute function - operations captured via __setitem__
                    result = func(*args, **kwargs)

                    # Operations captured, applied later (collect/profile)
                    captured_operations = frame_instance._computation_graph  # noqa: SLF001
                    if captured_operations:
                        logger.debug(
                            f"{len(captured_operations)} operations captured "
                            f"for later application.",
                        )
                        # Log the plan if verbose, but don't apply yet
                        if get_default_verbose() and frame_instance._df is not None:  # noqa: SLF001
                            log_query_plan(captured_operations, frame_instance._df)  # noqa: SLF001
                    else:
                        logger.debug("No operations captured during trace.")

                    # Return result if model created a new frame, otherwise original
                    return frame_instance if result is None else result

                finally:
                    # Restore original tracing state
                    frame_instance._tracing = original_tracing_state  # noqa: SLF001

            elif mode == "optimize":
                func_name = getattr(func, "__name__", "<unknown>")
                logger.debug(f"Running {func_name} in optimize mode.")
                # Disable tracing for immediate execution
                original_tracing_state = frame_instance._tracing  # noqa: SLF001
                frame_instance._tracing = False  # noqa: SLF001
                try:
                    result = func(*args, **kwargs)
                    return frame_instance if result is None else result
                finally:
                    frame_instance._tracing = original_tracing_state  # noqa: SLF001

            else:
                msg = f"Unknown execution mode: {mode}"
                raise ValueError(msg)

        return wrapper

    return decorator


def append_operation_to_graph(
    frame_instance: ActuarialFrame,
    name: str,
    expr: pl.Expr,
) -> None:
    """Append operation with metadata to computation graph if tracing enabled."""
    # Fast path: check tracing flag early to avoid overhead when disabled
    if not frame_instance._tracing:  # noqa: SLF001
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

    # Extract dependencies from the expression (local import avoids circular dependency)
    from gaspatchio_core.frame.graph import extract_dependencies  # noqa: PLC0415

    dependencies = extract_dependencies(expr)

    # Create TracedOperation
    operation = TracedOperation(
        alias=name,
        expression=expr,
        metadata=metadata,
        expected_dtype=expected_dtype,
        dependencies=dependencies,
    )

    frame_instance._computation_graph.append(operation)  # type: ignore[arg-type]  # noqa: SLF001
    logger.trace(
        f"Graph: Added '{name}' = {expr} (type={expected_dtype}, "
        f"deps={dependencies}) at {metadata.display_filename}:"
        f"{metadata.line_number}",
    )


def _temporal_dummy_value(dtype: pl.DataType) -> object:
    """Create a dummy temporal value for schema inference."""
    if dtype == pl.Date:
        return datetime.date(2020, 1, 1)
    if dtype == pl.Datetime:
        return datetime.datetime(2020, 1, 1)  # noqa: DTZ001  # Naive datetime matches Polars schema
    if dtype == pl.Time:
        return pl.time(0, 0, 0)
    if dtype == pl.Duration:
        return pl.duration(days=0)
    return None


def _scalar_dummy_value(dtype: pl.DataType) -> object:
    """Create a single dummy scalar value for the given Polars DataType.

    Used to build minimal DataFrames for expression type inference.
    Returns None for unrecognized types.
    """
    # Numeric types
    if dtype.is_float():
        return 0.0
    if dtype.is_integer():
        return 0
    # Temporal types
    if dtype.is_temporal():
        return _temporal_dummy_value(dtype)
    # String-like and categorical types
    if dtype in (pl.Utf8, pl.String) or isinstance(dtype, pl.Categorical):
        return "category1" if isinstance(dtype, pl.Categorical) else ""
    # Boolean type
    if dtype == pl.Boolean:
        return False
    # Null and unknown types
    if dtype != pl.Null:
        logger.trace(f"Unknown dtype {dtype}, using None for dummy value")
    return None


def _create_dummy_column_value(dtype: pl.DataType) -> list[object]:
    """Create a single-row dummy column value for the given Polars DataType.

    Returns a list with one element suitable for constructing a pl.DataFrame.
    For List types, wraps the inner dummy value in a nested list.
    """
    if isinstance(dtype, pl.List):
        # For list types, create list with one dummy element of the inner type
        inner_type: pl.DataType = (  # type: ignore[assignment]  # Polars stubs return DataTypeClass | DataType
            dtype.inner if hasattr(dtype, "inner") else pl.Float64()
        )
        inner_val = _scalar_dummy_value(inner_type)
        # Default to empty list if we don't know the inner type
        return [[inner_val]] if inner_val is not None else [[]]
    return [_scalar_dummy_value(dtype)]


def _build_type_map(frame_instance: ActuarialFrame) -> dict[str, pl.DataType]:
    """Build a type map from the computation graph and existing schema.

    Collects known column types from previously traced operations and
    the underlying DataFrame schema for use in expression type inference.
    """
    type_map: dict[str, pl.DataType] = {}
    for op in frame_instance._computation_graph:  # noqa: SLF001
        if isinstance(op, TracedOperation) and op.expected_dtype is not None:
            type_map[op.alias] = op.expected_dtype

    # Also add types from the existing schema if available
    try:
        if frame_instance._df is not None:  # noqa: SLF001
            schema = frame_instance._df.collect_schema()  # noqa: SLF001
            for col_name, dtype in schema.items():
                if col_name not in type_map:
                    type_map[col_name] = dtype
    except Exception as e:  # noqa: BLE001
        logger.trace(f"Could not collect schema for type inference: {e}")

    return type_map


def _infer_expression_type(
    expr: pl.Expr,
    frame_instance: ActuarialFrame,
) -> pl.DataType | None:
    """Infer the type that an expression will produce.

    Returns a Polars DataType or None if type cannot be inferred.
    """
    if not hasattr(frame_instance, "_computation_graph"):
        return None

    type_map = _build_type_map(frame_instance)

    # Try to infer type using Polars' schema inference with minimal LazyFrame
    try:
        # Create a minimal schema with known types
        if type_map:
            # Create a LazyFrame with one row and the known schema
            dummy_data = {
                col_name: _create_dummy_column_value(dtype)
                for col_name, dtype in type_map.items()
            }

            dummy_df = pl.DataFrame(dummy_data).lazy()

            # Apply the expression and let Polars tell us the resulting type
            result_df = dummy_df.select(expr.alias("_test_col"))
            result_schema = result_df.collect_schema()
            inferred_type = result_schema.get("_test_col")

            logger.trace(f"Type inference for expression: {expr} -> {inferred_type}")
            return inferred_type
        # If we have no type map, try with the existing schema
        if frame_instance._df is not None:  # noqa: SLF001
            result_df = frame_instance._df.select(expr.alias("_test_col"))  # noqa: SLF001
            result_schema = result_df.collect_schema()
            return result_schema.get("_test_col")
    except Exception as e:  # noqa: BLE001
        # If type inference fails, log it and return None
        logger.trace(f"Type inference failed for expression: {expr}, error: {e}")

    return None
