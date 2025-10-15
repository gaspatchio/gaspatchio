from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

from ..util import get_default_mode, get_default_verbose

if TYPE_CHECKING:
    from .base import ActuarialFrame


def log_query_plan(operations: list[Any], frame_df: pl.LazyFrame) -> None:
    """Logs the query plan if verbose mode is enabled."""
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
                        f"    Source: {operation.metadata.display_filename}:{operation.metadata.line_number}",
                    )
        logger.trace("Optimized Query Plan:")
        try:
            logger.debug(frame_df.explain(optimized=True))
        except Exception as e:
            logger.warning(f"Could not explain query plan: {e}")


def build_trace_decorator(frame_instance: ActuarialFrame) -> Callable:
    """
    Factory function to create the trace decorator for a specific ActuarialFrame instance.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> ActuarialFrame | None:
            mode = get_default_mode()

            if mode == "debug":
                logger.debug(
                    f"Tracing {func.__name__} in debug mode for enhanced error handling."
                )
                original_tracing_state = frame_instance._tracing
                original_graph = frame_instance._computation_graph[:]  # Shallow copy
                frame_instance._tracing = True
                frame_instance._computation_graph = []  # Reset for this trace

                try:
                    # Execute the function - operations will be captured via __setitem__
                    # Pass the frame instance if the function expects it as first arg
                    # result = func(frame_instance, *args, **kwargs)
                    result = func(*args, **kwargs)  # Assuming implicit operation

                    # Operations are captured, but not applied immediately by the decorator.
                    # Application should happen later (e.g., during collect/profile).
                    captured_operations = frame_instance._computation_graph
                    if captured_operations:
                        logger.debug(
                            f"{len(captured_operations)} operations captured for later application.",
                        )
                        # Log the plan if verbose, but don't apply yet
                        if get_default_verbose():
                            log_query_plan(captured_operations, frame_instance._df)
                    else:
                        logger.debug("No operations captured during trace.")

                    # Return the frame instance (state is unchanged wrt _df in debug mode)
                    # If the original function returned something else, we might lose it here.
                    # The original implementation assumed the function modifies the frame inplace
                    # or returns None. Let's stick to that for now.
                    return frame_instance

                finally:
                    # Restore original tracing state and graph (if needed, though usually not)
                    frame_instance._tracing = original_tracing_state
                    # frame_instance._computation_graph = original_graph # Usually reset is fine

            if mode == "optimize":
                logger.debug(f"Running {func.__name__} in optimize mode.")
                # Temporarily disable tracing to execute operations immediately for performance
                original_tracing_state = frame_instance._tracing
                frame_instance._tracing = False
                try:
                    result = func(*args, **kwargs)
                    return frame_instance if result is None else result
                finally:
                    frame_instance._tracing = original_tracing_state

            else:
                raise ValueError(f"Unknown execution mode: {mode}")

        return wrapper

    return decorator


def append_operation_to_graph(
    frame_instance: ActuarialFrame,
    name: str,
    expr: Any,
) -> None:
    """Appends an operation with metadata to the frame's computation graph if tracing is enabled."""
    # Fast path: check tracing flag early to avoid any overhead when disabled
    if not frame_instance._tracing:
        return

    # Import locally to avoid circular dependencies and cache for performance

    from ..errors.metadata import TracedOperation, capture_source_context

    # Capture source context from the calling code
    # Try different depths to find the user's model code (not internal frame code)
    metadata = None
    for depth in range(2, 8):  # Try depths 2-7
        temp_metadata = capture_source_context(depth=depth)
        # Skip internal frame/column files
        if not any(internal in temp_metadata.file_name for internal in [
            "gaspatchio_core/frame/", 
            "gaspatchio_core/column/",
            "gaspatchio_core/errors/",
            "<frozen",
            "site-packages/"
        ]):
            # This looks like user code
            metadata = temp_metadata
            break
    
    # Fallback to depth 2 if we couldn't find user code
    if metadata is None:
        metadata = capture_source_context(depth=2)

    # Try to infer the expected type of this expression
    expected_dtype = _infer_expression_type(expr, frame_instance)

    # Extract dependencies from the expression
    from .graph import extract_dependencies
    dependencies = extract_dependencies(expr)

    # Create TracedOperation instead of tuple
    operation = TracedOperation(
        alias=name,
        expression=expr,
        metadata=metadata,
        expected_dtype=expected_dtype,
        dependencies=dependencies,
    )

    frame_instance._computation_graph.append(operation)
    logger.trace(
        f"Graph: Added '{name}' = {expr} (type={expected_dtype}, deps={dependencies}) at {metadata.display_filename}:{metadata.line_number}",
    )


def _infer_expression_type(expr: Any, frame_instance: ActuarialFrame) -> Any:
    """
    Try to infer the type that an expression will produce.

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
        schema = frame_instance._df.collect_schema()
        for col_name, dtype in schema.items():
            if col_name not in type_map:
                type_map[col_name] = dtype
    except Exception:
        pass

    # Try to infer type using Polars' schema inference with a minimal LazyFrame
    try:
        # Create a minimal schema with known types
        if type_map:
            # Create a LazyFrame with one row and the known schema
            dummy_data = {}
            for col_name, dtype in type_map.items():
                if isinstance(dtype, pl.List):
                    # For list types, create a list with one dummy element of the right type
                    inner_type = dtype.inner if hasattr(dtype, "inner") else pl.Float64
                    # Create appropriate dummy value based on inner type
                    if inner_type == pl.Date:
                        import datetime
                        dummy_data[col_name] = [[datetime.date(2020, 1, 1)]]
                    elif inner_type == pl.Float64 or inner_type == pl.Float32:
                        dummy_data[col_name] = [[0.0]]
                    elif inner_type in [pl.Int64, pl.Int32, pl.Int16, pl.Int8, 
                                        pl.UInt64, pl.UInt32, pl.UInt16, pl.UInt8]:
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
                elif dtype == pl.Float64 or dtype == pl.Float32:
                    dummy_data[col_name] = [0.0]
                elif (
                    dtype == pl.Int64
                    or dtype == pl.Int32
                    or dtype == pl.Int16
                    or dtype == pl.Int8
                    or dtype == pl.UInt64
                    or dtype == pl.UInt32
                    or dtype == pl.UInt16
                    or dtype == pl.UInt8
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
        result_df = frame_instance._df.select(expr.alias("_test_col"))
        result_schema = result_df.collect_schema()
        return result_schema.get("_test_col")
    except Exception as e:
        # If type inference fails, log it and return None
        logger.trace(f"Type inference failed for expression: {expr}, error: {e}")

    return None
