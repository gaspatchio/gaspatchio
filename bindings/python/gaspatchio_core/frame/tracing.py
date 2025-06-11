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
                logger.debug(f"Running {func.__name__} in debug mode.")
                # Temporarily disable tracing to execute operations immediately
                original_tracing_state = frame_instance._tracing
                frame_instance._tracing = False
                try:
                    result = func(*args, **kwargs)
                    return frame_instance if result is None else result
                finally:
                    frame_instance._tracing = original_tracing_state

            if mode == "optimize":
                logger.debug(f"Tracing {func.__name__} in optimize mode.")
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

                    # Return the frame instance (state is unchanged wrt _df in optimize mode)
                    # If the original function returned something else, we might lose it here.
                    # The original implementation assumed the function modifies the frame inplace
                    # or returns None. Let's stick to that for now.
                    return frame_instance

                finally:
                    # Restore original tracing state and graph (if needed, though usually not)
                    frame_instance._tracing = original_tracing_state
                    # frame_instance._computation_graph = original_graph # Usually reset is fine

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
    # Stack depth 2: capture_source_context -> append_operation_to_graph -> user code
    metadata = capture_source_context(depth=2)

    # Create TracedOperation instead of tuple
    operation = TracedOperation(
        alias=name,
        expression=expr,
        metadata=metadata,
    )

    frame_instance._computation_graph.append(operation)
    logger.trace(
        f"Graph: Added '{name}' = {expr} at {metadata.display_filename}:{metadata.line_number}",
    )


# You might add more helper functions here if needed, e.g., for complex logic
# related to applying operations or optimizing the graph.
