from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .base import ActuarialFrame


# Keep run_model for now, it might be moved later or stay as a top-level function
def run_model(model_func: Callable, df: "ActuarialFrame") -> "ActuarialFrame":
    """Run a model function on an ActuarialFrame"""
    # If we're in debug mode, just run the function directly
    if df._mode == "debug":
        result = model_func(df)
        return df if result is None else result

    # In optimize mode, use the tracer (Tracer logic needs integration)
    # This requires the tracing components to be fully integrated into ActuarialFrame first.
    if hasattr(df, "trace"):  # Check if trace method exists
        try:
            traced_func = df.trace(model_func)
            # The trace decorator itself should handle execution and returning the result/frame
            # Assuming the decorator returns the result or modified frame
            result_frame = traced_func(df)  # Pass df again, decorator might need it
            return result_frame
        except Exception as e:
            # Handle potential errors during tracing or execution
            print(f"Error during traced execution: {e}")
            # Fallback or re-raise depending on desired error handling
            raise
    else:
        # Fallback if trace is not available or tracing fails setup
        print(
            "Warning: optimize mode function execution without trace method."
            " Running directly."
        )
        result = model_func(df)
        return df if result is None else result
