# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Telemetry and performance monitoring for Gaspatchio.

This module contains utilities for tracking and logging performance issues,
providing insights to help optimize code.
"""

from __future__ import annotations

import inspect
import sys
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

from gaspatchio._source import PACKAGE_DIRECTORIES, is_framework_or_interpreter_file
from gaspatchio._warning import warn
from gaspatchio.util import get_default_mode

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType

    from gaspatchio.typing import PolarsDataType

    # What Expr.map_elements and Expr.map_batches accept as return_dtype.
    type _ReturnDtype = PolarsDataType | pl.DataTypeExpr | None

# The two Polars methods watched here, as the proxies' own methods are named.
# A proxy's map_elements() or map_batches() hands the user's request straight
# on, so a call from one of them is the user's call and not the framework's.
_PASS_THROUGHS = frozenset({"map_elements", "map_batches"})


def _users_frame(caller: FrameType | None) -> FrameType | None:
    """Return the user's frame that made this call, or ``None`` if it is not theirs.

    Whose call it is follows the rule every frame walk follows,
    ``is_framework_or_interpreter_file``. The framework's lowering calls
    map_elements() where nothing faster exists -- a business-day
    adjustment, a day count over real boundary dates -- Polars' own
    map_elements() calls map_batches(), and an installed library makes calls
    of its own. None of those is the user's to rewrite, so none is theirs to
    hear about. A proxy's same-named method hands the user's request
    straight on, so it is passed over to its caller.
    """
    frame = caller
    while (
        frame is not None
        and frame.f_code.co_name in _PASS_THROUGHS
        and frame.f_code.co_filename.startswith(PACKAGE_DIRECTORIES)
    ):
        frame = frame.f_back
    if frame is None or is_framework_or_interpreter_file(frame.f_code.co_filename):
        return None
    return frame


def _notice(
    users_frame: FrameType | None,
    *,
    said: str,
    logged: tuple[tuple[str, dict[str, object]], ...],
) -> None:
    """Tell the user about their own slow call, or log anyone else's, once.

    One channel for each call: a ``PerformanceWarning`` located at the
    user's line where the call is theirs, the log records where it is not.
    """
    if users_frame is None:
        for template, fields in logged:
            logger.warning(template, **fields)
        return
    # Imported here: the error package imports the frame, which is not yet
    # loaded when this module is, as the first thing the package imports.
    from gaspatchio.errors.formatting_errors import (  # noqa: PLC0415
        PerformanceWarning,
    )

    warn(said, PerformanceWarning)


# Custom exception for performance violations
class PerformanceViolationError(Exception):
    """Raised when a performance-critical violation occurs in optimize mode."""


# Store the original map_elements function
original_map_elements = pl.Expr.map_elements
# Store the original map_batches function
original_map_batches = pl.Expr.map_batches


def _suggestion_for(return_dtype: object) -> str:
    """Return the faster form to suggest for map_elements(), by the type it returns."""
    dtype = str(return_dtype) if return_dtype else ""
    if "List" in dtype:
        return (
            "Consider using expressions with pl.col().list operations for better "
            "performance."
        )
    if "Date" in dtype:
        return "Consider using pl.col().dt functions for date operations."
    if "Float" in dtype or "Int" in dtype:
        return (
            "Consider using arithmetic expressions or pl.when/then/otherwise for "
            "conditional logic."
        )
    return "Consider using native Polars expressions for better performance."


def _get_mode() -> str:
    """
    Get the current execution mode from ``gaspatchio.util``.

    Returns:
        Current execution mode ("debug" or "optimize")

    """
    return get_default_mode()


# This is the core logic, wrapped to look like the original
@wraps(original_map_elements)  # This wraps _map_with_warning_impl
def _map_with_warning_impl(
    expr_instance: pl.Expr,  # This will be the 'self' for the original method
    function: Callable[..., Any],
    return_dtype: _ReturnDtype = None,
    *,
    mapping_method: str,  # This comes from the wrapper that calls this
    **kwargs: Any,  # noqa: ANN401 - passed through to the original method
) -> pl.Expr:
    """
    Core implementation for map_elements and map_batches warnings.

    This function is NOT directly assigned; it's called by wrappers.
    """
    # Two frames up, past this function and the wrapper, is the wrapper's
    # caller. inspect.currentframe() reads the same frames but is typed to
    # allow None, for interpreters that keep none; CPython always does.
    frame = sys._getframe(2)  # noqa: SLF001 - documented CPython API
    # Whose call this is decides everything below: only the user's own call
    # is refused in optimize mode or raised as a warning, and it is reported
    # at the user's line rather than at a proxy's.
    users_frame = _users_frame(frame)
    info = inspect.getframeinfo(users_frame or frame)
    filename = Path(info.filename).name
    func_name = getattr(function, "__name__", "<lambda>")
    code_snippet = info.code_context[0].strip() if info.code_context else "Unknown"
    # The function the call sits in: what getframeinfo reports as `function`.
    caller = frame.f_back
    context_function = caller.f_code.co_name if caller is not None else "Unknown"
    call_site_id = f"{filename}:{info.lineno}:{func_name}:{mapping_method}"

    current_mode = _get_mode()

    if mapping_method == "map_elements":
        suggestion = _suggestion_for(return_dtype)
        if current_mode == "optimize" and users_frame is not None:
            error_message = (
                f"\n\n{'=' * 80}\n"
                "FATAL PERFORMANCE VIOLATION: map_elements() detected in optimize "
                "mode\n"
                f"{'=' * 80}\n\n"
                f"Location: {info.filename}:{info.lineno}\n"
                f"Function: {func_name}\n"
                f"Context: {context_function}\n"
                f"Return type: {return_dtype}\n\n"
                f"Code: {code_snippet}\n\n"
                f"SUGGESTION: {suggestion}\n\n"
                "map_elements() is NOT ALLOWED in optimize mode as it causes "
                "significant\n"
                "performance degradation. Please refactor to use native Polars "
                "expressions.\n"
                f"{'=' * 80}\n"
            )
            raise PerformanceViolationError(error_message)
        _notice(
            users_frame,
            said=(
                f"map_elements() runs {func_name} once for every value, in "
                f"Python, where Polars cannot vectorise it. {suggestion} With "
                "GASPATCHIO_MODE=optimize set, this call is refused."
            ),
            logged=(
                (
                    (
                        "MAP_ELEMENTS_PERFORMANCE_ISSUE | {issue_type} | {file}:{line}"
                        " | {func} | {dtype} | ID:{call_id}"
                    ),
                    {
                        "issue_type": "SLOW_OPERATION",
                        "file": filename,
                        "line": info.lineno,
                        "func": func_name,
                        "dtype": return_dtype,
                        "call_id": call_site_id,
                    },
                ),
                (
                    (
                        "MAP_ELEMENTS_CODE_CONTEXT | ID:{call_id} | {context_func}"
                        " | CODE: {snippet} | SUGGESTION: {suggestion}"
                    ),
                    {
                        "call_id": call_site_id,
                        "context_func": context_function,
                        "snippet": code_snippet,
                        "suggestion": suggestion,
                    },
                ),
            ),
        )
        return original_map_elements(
            expr_instance, function, return_dtype=return_dtype, **kwargs
        )

    if mapping_method == "map_batches":
        if return_dtype is None:
            _notice(
                users_frame,
                said=(
                    f"map_batches() was given no return_dtype for {func_name}, "
                    "so Polars infers the result's type from the values it "
                    "returns. Pass return_dtype= to map_batches()."
                ),
                logged=(
                    (
                        (
                            "MAP_BATCHES_PERFORMANCE_ISSUE | {issue_type}"
                            " | {file}:{line} | {func} | ID:{call_id}"
                        ),
                        {
                            "issue_type": "MISSING_RETURN_DTYPE",
                            "file": filename,
                            "line": info.lineno,
                            "func": func_name,
                            "call_id": call_site_id,
                        },
                    ),
                    (
                        (
                            "MAP_BATCHES_CODE_CONTEXT | ID:{call_id} | {context_func}"
                            " | CODE: {snippet} | SUGGESTION: {suggestion}"
                        ),
                        {
                            "call_id": call_site_id,
                            "context_func": context_function,
                            "snippet": code_snippet,
                            "suggestion": (
                                "Providing 'return_dtype' to map_batches "
                                "significantly improves performance by "
                                "avoiding schema inference."
                            ),
                        },
                    ),
                ),
            )
        return original_map_batches(
            expr_instance, function, return_dtype=return_dtype, **kwargs
        )
    msg = f"Invalid mapping_method: {mapping_method}"
    raise ValueError(msg)


def _set_expr_mapping_methods(
    map_elements: Callable[..., pl.Expr], map_batches: Callable[..., pl.Expr]
) -> None:
    """Point pl.Expr's map_elements and map_batches at the given functions.

    Replacing a class's methods at run time is what this module does, and
    setattr says so: the type checkers refuse a method assignment written out.
    """
    for name, method in (("map_elements", map_elements), ("map_batches", map_batches)):
        setattr(pl.Expr, name, method)


def install_performance_monitors() -> None:
    """Install performance monitoring hooks."""

    # Define the wrapper methods that will replace the originals on pl.Expr,
    # carrying the originals' metadata (name, docstring, signature).
    @wraps(original_map_elements)
    def _map_elements_wrapper(
        self: pl.Expr,
        function: Callable[..., Any],
        return_dtype: _ReturnDtype = None,
        **kwargs: Any,  # noqa: ANN401 - passed through to the original method
    ) -> pl.Expr:
        return _map_with_warning_impl(
            self, function, return_dtype, mapping_method="map_elements", **kwargs
        )

    @wraps(original_map_batches)
    def _map_batches_wrapper(
        self: pl.Expr,
        function: Callable[..., Any],
        return_dtype: _ReturnDtype = None,
        **kwargs: Any,  # noqa: ANN401 - passed through to the original method
    ) -> pl.Expr:
        return _map_with_warning_impl(
            self, function, return_dtype, mapping_method="map_batches", **kwargs
        )

    _set_expr_mapping_methods(_map_elements_wrapper, _map_batches_wrapper)

    logger.trace("Performance monitoring enabled for map_elements and map_batches")


def configure_telemetry(enable: bool = True) -> None:  # noqa: FBT001 - public positional form
    """
    Configure telemetry settings.

    Args:
        enable: Whether to enable telemetry

    """
    if enable:
        install_performance_monitors()
    else:
        # Restore original functions when disabling
        _set_expr_mapping_methods(original_map_elements, original_map_batches)
        logger.trace("Performance monitoring disabled")
