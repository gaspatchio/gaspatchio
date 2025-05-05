from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable, List, Tuple

import polars as pl
from loguru import logger

from ..util import get_default_mode, get_default_verbose

if TYPE_CHECKING:
    from .base import ActuarialFrame  # noqa: F401 - Avoid circular import


def log_query_plan(operations: List[Tuple[str, Any]], frame_df: pl.LazyFrame) -> None:
    """Logs the query plan if verbose mode is enabled."""
    if get_default_verbose():
        logger.info("Computation Graph:")
        for i, (name, expr) in enumerate(operations):
            logger.info(f"  Step {i + 1}: {name} = {expr}")
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
                # Pass the frame instance itself if the function expects it
                # Assuming the decorated function might take the frame as first arg
                # or might operate implicitly on it. Adjust if needed.
                # If the function takes the frame explicitly:
                # result = func(frame_instance, *args, **kwargs)
                # If it operates implicitly:
                result = func(*args, **kwargs)
                return frame_instance if result is None else result

            elif mode == "optimize":
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

                    # Apply captured operations
                    captured_operations = frame_instance._computation_graph
                    if captured_operations:
                        logger.debug(
                            f"Applying {len(captured_operations)} captured operations."
                        )
                        # Create a dictionary of expressions for with_columns
                        exprs_dict = {name: expr for name, expr in captured_operations}
                        frame_instance._df = frame_instance._df.with_columns(
                            **exprs_dict
                        )
                        log_query_plan(captured_operations, frame_instance._df)
                    else:
                        logger.debug("No operations captured during trace.")

                    # Return the frame instance (potentially modified)
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
    frame_instance: ActuarialFrame, name: str, expr: Any
) -> None:
    """Appends an operation to the frame's computation graph if tracing is enabled."""
    if frame_instance._tracing:
        frame_instance._computation_graph.append((name, expr))
        logger.trace(f"Graph: Added '{name}' = {expr}")


# You might add more helper functions here if needed, e.g., for complex logic
# related to applying operations or optimizing the graph.
