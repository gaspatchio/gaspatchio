"""
Telemetry and performance monitoring for Gaspatchio

This module contains utilities for tracking and logging performance issues,
providing insights to help optimize code.
"""

import inspect
import os
import sys
from functools import wraps

import polars as pl
from loguru import logger


# Custom exception for performance violations
class PerformanceViolationError(Exception):
    """
    Exception raised when a performance-critical violation occurs in optimize mode.
    """

    pass


# Store the original map_elements function
original_map_elements = pl.Expr.map_elements


def _get_mode() -> str:
    """
    Get the current execution mode from core.py.

    This uses a dynamic import to avoid circular imports.

    Returns:
        Current execution mode ("debug" or "optimize")
    """
    # Use dynamic import to avoid circular imports
    from gaspatchio_core.dsl.core import get_default_mode

    return get_default_mode()


@wraps(original_map_elements)
def map_elements_with_warning(self, function, return_dtype=None, **kwargs):
    """
    Wrapper for map_elements that logs performance warnings or raises errors

    This is a monkey patch for the Polars map_elements function that adds
    performance warnings and suggestions when map_elements is used.

    When in optimize mode, this terminates program execution completely.
    """
    # Get call stack info
    frame = inspect.currentframe().f_back
    info = inspect.getframeinfo(frame)

    # Extract just the filename without the full path
    filename = os.path.basename(info.filename)

    # Extract function name or use '<lambda>' if it's a lambda
    func_name = getattr(function, "__name__", "<lambda>")

    # Get code context (the line of code and a few lines before/after)
    context_lines = info.code_context
    if context_lines:
        code_snippet = context_lines[0].strip()
    else:
        code_snippet = "Unknown"

    # Attempt to determine function or method context
    try:
        parent_frame = frame.f_back
        if parent_frame:
            parent_info = inspect.getframeinfo(parent_frame)
            context_function = parent_info.function
        else:
            context_function = "Unknown"
    except:
        context_function = "Unknown"

    # Attempt to suggest an alternative based on return type
    suggestion = "Consider using native Polars expressions for better performance."
    if return_dtype:
        dtype_str = str(return_dtype)
        if "List" in dtype_str:
            suggestion = "Consider using expressions with pl.col().list operations for better performance."
        elif "Date" in dtype_str or "Datetime" in dtype_str:
            suggestion = "Consider using pl.col().dt functions for date operations."
        elif "Float" in dtype_str or "Int" in dtype_str:
            suggestion = "Consider using arithmetic expressions or pl.when/then/otherwise for conditional logic."

    # Generate a tracking ID for this specific call site
    call_site_id = f"{filename}:{info.lineno}:{func_name}"

    # Check if we're in optimize mode
    current_mode = _get_mode()

    if current_mode == "optimize":
        # In optimize mode, completely terminate execution
        error_message = (
            f"\n\n{'=' * 80}\n"
            f"FATAL PERFORMANCE VIOLATION: map_elements() detected in optimize mode\n"
            f"{'=' * 80}\n\n"
            f"Location: {info.filename}:{info.lineno}\n"
            f"Function: {func_name}\n"
            f"Context: {context_function}\n"
            f"Return type: {return_dtype}\n\n"
            f"Code: {code_snippet}\n\n"
            f"SUGGESTION: {suggestion}\n\n"
            f"map_elements() is NOT ALLOWED in optimize mode as it causes significant\n"
            f"performance degradation. Please refactor to use native Polars expressions.\n"
            f"{'=' * 80}\n\n"
            f"PROGRAM EXECUTION TERMINATED\n"
            f"{'=' * 80}\n"
        )

        # Print error to stderr and terminate program
        logger.error(error_message)
        sys.stderr.write(error_message)
        sys.stderr.flush()

        # Exit with non-zero status code to indicate error
        sys.exit(1)
    else:
        # In debug mode, log warnings as before
        # Log first structured warning with basic information
        logger.warning(
            "MAP_ELEMENTS_PERFORMANCE_ISSUE | {issue_type} | {file}:{line} | {func} | {dtype} | ID:{call_id}",
            issue_type="SLOW_OPERATION",
            file=filename,
            line=info.lineno,
            func=func_name,
            dtype=return_dtype,
            call_id=call_site_id,
        )

        # Log second message with code snippet and suggestions
        logger.warning(
            "MAP_ELEMENTS_CODE_CONTEXT | ID:{call_id} | {context_func} | CODE: {snippet} | SUGGESTION: {suggestion}",
            call_id=call_site_id,
            context_func=context_function,
            snippet=code_snippet,
            suggestion=suggestion,
        )

    # Call the original function
    return original_map_elements(self, function, return_dtype, **kwargs)


def install_performance_monitors():
    """
    Install performance monitoring hooks

    This function applies monkey patches to various library functions to
    add performance monitoring and telemetry.
    """
    # Apply the map_elements monkey patch
    pl.Expr.map_elements = map_elements_with_warning

    # Additional performance monitors can be added here in the future
    # For example, monitoring other slow operations

    logger.debug("Performance monitoring enabled")


def configure_telemetry(enable=True):
    """
    Configure telemetry settings

    Args:
        enable: Whether to enable telemetry
    """
    if enable:
        install_performance_monitors()
    else:
        # Restore original functions when disabling
        pl.Expr.map_elements = original_map_elements
        logger.debug("Performance monitoring disabled")
