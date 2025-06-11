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
        logger.info("Computation Graph:")
        for i, operation in enumerate(operations):
            # Handle both old tuple format and new TracedOperation format
            if isinstance(operation, tuple):
                # Legacy format: (name, expr)
                name, expr = operation
                logger.info(f"  Step {i + 1}: {name} = {expr}")
            else:
                # New format: TracedOperation
                logger.info(
                    f"  Step {i + 1}: {operation.alias} = {operation.expression}",
                )
                if hasattr(operation, "metadata") and operation.metadata:
                    logger.info(
                        f"    Source: {operation.metadata.display_filename}:{operation.metadata.line_number}",
                    )
        logger.info("Optimized Query Plan:")
        try:
            logger.info(frame_df.explain(optimized=True))
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
                logger.debug(f"Tracing {func.__name__} in debug mode for enhanced error handling.")
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
    import polars as pl

    # Capture source context from the calling code
    # Stack depth 2: capture_source_context -> append_operation_to_graph -> user code
    metadata = capture_source_context(depth=2)
    
    # Try to infer the expected type of this expression
    expected_dtype = _infer_expression_type(expr, frame_instance)

    # Create TracedOperation instead of tuple
    operation = TracedOperation(
        alias=name,
        expression=expr,
        metadata=metadata,
        expected_dtype=expected_dtype,
    )

    frame_instance._computation_graph.append(operation)
    logger.trace(
        f"Graph: Added '{name}' = {expr} (type={expected_dtype}) at {metadata.display_filename}:{metadata.line_number}",
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
                    # For list types, create an empty list of the right type
                    inner_type = dtype.inner if hasattr(dtype, 'inner') else pl.Float64
                    dummy_data[col_name] = [[]]
                # Numeric types
                elif dtype == pl.Float64:
                    dummy_data[col_name] = [0.0]
                elif dtype == pl.Float32:
                    dummy_data[col_name] = [0.0]
                elif dtype == pl.Int64:
                    dummy_data[col_name] = [0]
                elif dtype == pl.Int32:
                    dummy_data[col_name] = [0]
                elif dtype == pl.Int16:
                    dummy_data[col_name] = [0]
                elif dtype == pl.Int8:
                    dummy_data[col_name] = [0]
                elif dtype == pl.UInt64:
                    dummy_data[col_name] = [0]
                elif dtype == pl.UInt32:
                    dummy_data[col_name] = [0]
                elif dtype == pl.UInt16:
                    dummy_data[col_name] = [0]
                elif dtype == pl.UInt8:
                    dummy_data[col_name] = [0]
                # String type
                elif dtype == pl.Utf8:
                    dummy_data[col_name] = [""]
                # Boolean type
                elif dtype == pl.Boolean:
                    dummy_data[col_name] = [False]
                # Temporal types
                elif dtype == pl.Date:
                    dummy_data[col_name] = [pl.date(2020, 1, 1)]
                elif dtype == pl.Datetime:
                    dummy_data[col_name] = [pl.datetime(2020, 1, 1)]
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
                    logger.trace(f"Unknown dtype {dtype} for column {col_name}, using None")
                    dummy_data[col_name] = [None]
            
            dummy_df = pl.DataFrame(dummy_data).lazy()
            
            # Apply the expression and let Polars tell us the resulting type
            result_df = dummy_df.select(expr.alias("_test_col"))
            result_schema = result_df.collect_schema()
            inferred_type = result_schema.get("_test_col")
            
            logger.trace(f"Type inference for expression: {expr} -> {inferred_type}")
            return inferred_type
        else:
            # If we have no type map, try with the existing schema
            result_df = frame_instance._df.select(expr.alias("_test_col"))
            result_schema = result_df.collect_schema()
            return result_schema.get("_test_col")
    except Exception as e:
        # If type inference fails, log it and return None
        logger.trace(f"Type inference failed for expression: {expr}, error: {e}")
        pass
    
    return None
