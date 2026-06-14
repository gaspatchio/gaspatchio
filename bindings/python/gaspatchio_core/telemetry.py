# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Telemetry and performance monitoring for Gaspatchio

This module contains utilities for tracking and logging performance issues,
providing insights to help optimize code.
"""

import inspect
import os
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
# Store the original map_batches function
original_map_batches = pl.Expr.map_batches


def _get_mode() -> str:
    """
    Get the current execution mode from core.py.

    This uses a dynamic import to avoid circular imports.

    Returns:
        Current execution mode ("debug" or "optimize")
    """
    # Use dynamic import to avoid circular imports
    from gaspatchio_core import get_default_mode

    return get_default_mode()


# This is the core logic, wrapped to look like the original
@wraps(original_map_elements)  # This wraps _map_with_warning_impl
def _map_with_warning_impl(
    expr_instance,  # This will be the 'self' for the original method
    function,
    return_dtype=None,
    *,
    mapping_method: str,  # This comes from the wrapper that calls this
    **kwargs,
):
    """
    Core implementation for map_elements and map_batches warnings.
    This function is NOT directly assigned; it's called by wrappers.
    """
    frame = (
        inspect.currentframe().f_back.f_back
    )  # Go back two frames to get caller of the wrapper
    info = inspect.getframeinfo(frame)
    filename = os.path.basename(info.filename)
    func_name = getattr(function, "__name__", "<lambda>")
    code_snippet = info.code_context[0].strip() if info.code_context else "Unknown"
    try:
        context_function = inspect.getframeinfo(frame.f_back).function
    except:
        context_function = "Unknown"
    call_site_id = f"{filename}:{info.lineno}:{func_name}:{mapping_method}"

    current_mode = _get_mode()

    if mapping_method == "map_elements":
        suggestion = "Consider using native Polars expressions for better performance."
        if return_dtype:
            dtype_str = str(return_dtype)
            if "List" in dtype_str:
                suggestion = "Consider using expressions with pl.col().list operations for better performance."
            elif "Date" in dtype_str or "Datetime" in dtype_str:
                suggestion = "Consider using pl.col().dt functions for date operations."
            elif "Float" in dtype_str or "Int" in dtype_str:
                suggestion = "Consider using arithmetic expressions or pl.when/then/otherwise for conditional logic."

        if current_mode == "optimize":
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
                f"{'=' * 80}\n"
            )
            raise PerformanceViolationError(error_message)
        else:  # debug mode
            logger.warning(
                "MAP_ELEMENTS_PERFORMANCE_ISSUE | {issue_type} | {file}:{line} | {func} | {dtype} | ID:{call_id}",
                issue_type="SLOW_OPERATION",
                file=filename,
                line=info.lineno,
                func=func_name,
                dtype=return_dtype,
                call_id=call_site_id,
            )
            logger.warning(
                "MAP_ELEMENTS_CODE_CONTEXT | ID:{call_id} | {context_func} | CODE: {snippet} | SUGGESTION: {suggestion}",
                call_id=call_site_id,
                context_func=context_function,
                snippet=code_snippet,
                suggestion=suggestion,
            )
        return original_map_elements(
            expr_instance, function, return_dtype=return_dtype, **kwargs
        )

    elif mapping_method == "map_batches":
        if return_dtype is None:
            logger.warning(
                "MAP_BATCHES_PERFORMANCE_ISSUE | {issue_type} | {file}:{line} | {func} | ID:{call_id}",
                issue_type="MISSING_RETURN_DTYPE",
                file=filename,
                line=info.lineno,
                func=func_name,
                call_id=call_site_id,
            )
            logger.warning(
                "MAP_BATCHES_CODE_CONTEXT | ID:{call_id} | {context_func} | CODE: {snippet} | SUGGESTION: {suggestion}",
                call_id=call_site_id,
                context_func=context_function,
                snippet=code_snippet,
                suggestion="Providing 'return_dtype' to map_batches significantly improves performance by avoiding schema inference.",
            )
        return original_map_batches(
            expr_instance, function, return_dtype=return_dtype, **kwargs
        )
    else:
        raise ValueError(f"Invalid mapping_method: {mapping_method}")


def install_performance_monitors():
    """
    Install performance monitoring hooks
    """

    # Define the wrapper methods that will replace the originals on pl.Expr
    def map_elements_wrapper(self, function, return_dtype=None, **kwargs):
        return _map_with_warning_impl(
            self, function, return_dtype, mapping_method="map_elements", **kwargs
        )

    def map_batches_wrapper(self, function, return_dtype=None, **kwargs):
        return _map_with_warning_impl(
            self, function, return_dtype, mapping_method="map_batches", **kwargs
        )

    # Ensure the wrappers have the correct metadata by copying from originals
    # (though @wraps on _map_with_warning_impl already does much of this for _map_with_warning_impl itself)
    map_elements_wrapper = wraps(original_map_elements)(map_elements_wrapper)
    map_batches_wrapper = wraps(original_map_batches)(map_batches_wrapper)

    pl.Expr.map_elements = map_elements_wrapper
    pl.Expr.map_batches = map_batches_wrapper

    logger.trace("Performance monitoring enabled for map_elements and map_batches")


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
        pl.Expr.map_batches = original_map_batches
        logger.trace("Performance monitoring disabled")
