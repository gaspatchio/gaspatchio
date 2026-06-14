# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Method execution and list-routing internals for proxy dispatch."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

import polars as pl
from loguru import logger

from gaspatchio_core.polars_backend.list_eval import unwrap_for_list_eval

from ._dispatch_common import (
    _get_proxy_base_expr,
    _unwrap,
    _unwrap_for_arithmetic,
    _wrap,
)

# Import capture_source_context at module level for testability
try:
    from gaspatchio_core.errors.metadata import (
        capture_source_context as _capture_source_context,
    )
except ImportError:
    _capture_source_context = None  # type: ignore[assignment]

capture_source_context = _capture_source_context

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame

    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    ProxyType = ColumnProxy | ExpressionProxy


# Operations that are unary (no arguments) and should use list shimming
_NUMERIC_UNARY: set[str] = {
    "abs",
    "sign",
    "floor",
    "ceil",
    "round",
    "round_sig_figs",
    "exp",
    "log",
    "log1p",
    "ln",
    "log10",
    "sqrt",
    "cbrt",
    "gamma",
    "is_nan",
    "is_finite",
    "is_infinite",
    "is_not_nan",
    "is_null",
    "is_not_null",
}

# Operations that may have arguments and should use list shimming
_NUMERIC_ELEMENTWISE: set[str] = {
    "clip",
    "clip_min",
    "clip_max",
    "add",
    "sub",
    "mul",
    "truediv",
    "floordiv",
    "pow",
    "mod",
    "round",
    "cast",
    "cum_prod",
    "cum_sum",
    "cum_min",
    "cum_max",
    "diff",
    "shift",
    "fill_null",
    "fill_nan",
    "interpolate",
}

# Operations that route to polars_backend for list-aware execution.
_BACKEND_LIST_OPS: set[str] = {"pow", "clip"}

# Arithmetic operations that should coerce ConditionExpression to boolean (0.0/1.0)
_ARITHMETIC_OPS: set[str] = {"add", "sub", "mul", "truediv", "floordiv", "mod", "pow"}


def _create_method_wrapper(
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: pl.Expr,
) -> Callable:
    """Create a wrapper for a Polars method."""

    def method_wrapper(
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        return _method_caller(
            name=name,
            polars_attr=polars_attr,
            self_proxy=self_proxy,
            parent_af=parent_af,
            base_expr=base_expr,
            a=args,
            kw=kwargs,
        )

    try:
        method_wrapper.__doc__ = getattr(
            polars_attr, "__doc__", f"Proxied Polars method: {name}"
        )
    except AttributeError:
        method_wrapper.__doc__ = f"Proxied Polars method: {name}"

    return method_wrapper


def _should_use_list_shim(
    name: str,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: pl.Expr,  # noqa: ARG001
) -> bool:
    """Determine if list shimming should be used for the operation."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    if name not in _NUMERIC_UNARY and name not in _NUMERIC_ELEMENTWISE:
        return False

    if not parent_af:
        return False

    if isinstance(self_proxy, (ColumnProxy, ExpressionProxy)):
        return self_proxy.shape == "list"
    return False


def _execute_list_shim(
    name: str,
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
    *,
    is_unary: bool,
) -> pl.Expr:
    """Execute a method using list.eval for element-wise operations."""
    element_method = getattr(pl.element(), name)

    if is_unary:
        return base_expr.list.eval(element_method())

    unwrapped_args = [unwrap_for_list_eval(arg) for arg in args]
    unwrapped_kwargs = {k: unwrap_for_list_eval(v) for k, v in kwargs.items()}
    return base_expr.list.eval(element_method(*unwrapped_args, **unwrapped_kwargs))


def _execute_regular(polars_attr: Callable, args: tuple, kwargs: dict) -> Any:  # noqa: ANN401
    """Execute a regular Polars method."""
    unwrapped_args = [_unwrap(arg) for arg in args]
    unwrapped_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
    return polars_attr(*unwrapped_args, **unwrapped_kwargs)


class ErrorEnhancer:
    """Centralized error handling and enhancement."""

    def __init__(self, self_proxy: "ProxyType") -> None:
        self.proxy = self_proxy
        self.parent_af = getattr(self_proxy, "_parent", None)
        tracing = getattr(self.parent_af, "_tracing", False)
        self.is_tracing = bool(self.parent_af and tracing)

    def enhance_method_error(
        self, e: Exception, method_name: str, context_depth: int = 3
    ) -> Exception:
        """Enhance an error with proxy context information."""
        error_msg = f"Error calling proxied Polars method '{method_name}': {e}"

        if self.is_tracing and capture_source_context is not None:
            try:
                context = capture_source_context(depth=context_depth)
                error_msg += (
                    f"\n  Called from: {context.display_filename}:{context.line_number}"
                )
                error_msg += f"\n  Source: {context.source_line}"
            except AttributeError:
                logger.trace("Failed to capture source context for error")

        new_error = type(e)(error_msg)
        proxy_info = {
            "proxy_type": type(self.proxy).__name__,
            "method": method_name,
            "column": getattr(self.proxy, "name", None),
        }
        setattr(new_error, "proxy_info", proxy_info)  # noqa: B010
        setattr(new_error, "_dispatch_enhanced", True)  # noqa: B010
        return new_error


def _has_column_operands(args: tuple, kwargs: dict) -> bool:
    """Check if any argument is a column reference or expression with named columns."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    for arg in args:
        if isinstance(arg, (ColumnProxy, ExpressionProxy)):
            return True
        if isinstance(arg, pl.Expr) and 'col("' in str(arg):
            return True
    for val in kwargs.values():
        if isinstance(val, (ColumnProxy, ExpressionProxy)):
            return True
        if isinstance(val, pl.Expr) and 'col("' in str(val):
            return True
    return False


def _method_caller(  # noqa: PLR0913
    *,
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: Any,  # noqa: ANN401
    a: tuple,
    kw: dict,
) -> Any:  # noqa: ANN401
    """Execute the delegated method with proper list-type handling."""
    pow_arg_is_list = False
    if name == "pow" and a and parent_af:
        from .column_proxy import ColumnProxy
        from .expression_proxy import ExpressionProxy

        for arg in a:
            if (
                isinstance(arg, (ColumnProxy, ExpressionProxy))
                and arg.shape == "list"
            ):
                pow_arg_is_list = True
                logger.trace(f"Pow argument {arg!r} is list-shaped")
                break

    if name in _ARITHMETIC_OPS:
        a = tuple(_unwrap_for_arithmetic(arg) for arg in a)
        kw = {k: _unwrap_for_arithmetic(v) for k, v in kw.items()}

    should_use_list_shim = _should_use_list_shim(name, self_proxy, parent_af, base_expr)
    pow_base_is_list = should_use_list_shim

    if not should_use_list_shim and pow_arg_is_list:
        should_use_list_shim = True
        pow_base_is_list = False
        logger.trace("Pow argument is list — enabling list shim with scalar base")

    is_unary = name in _NUMERIC_UNARY and not a and not kw

    logger.trace(
        f"Method caller for {name}: list_shim={should_use_list_shim}, unary={is_unary}"
    )

    error_enhancer = ErrorEnhancer(self_proxy)

    try:
        if should_use_list_shim:
            if name == "pow" and a and name in _BACKEND_LIST_OPS:
                from gaspatchio_core.polars_backend.operators import dispatch_list_op

                logger.trace(
                    f"Routing pow to polars_backend (base_is_list={pow_base_is_list})"
                )
                result = dispatch_list_op(
                    name, base_expr, a, kw, base_is_list=pow_base_is_list
                )
            else:
                try:
                    logger.trace(f"Executing list shim for {name}")
                    result = _execute_list_shim(name, base_expr, a, kw, is_unary=is_unary)
                except (TypeError, ValueError) as list_error:
                    logger.trace(f"List shim failed for {name}: {list_error}")

                    if (
                        name == "clip"
                        and name in _BACKEND_LIST_OPS
                        and _has_column_operands(a, kw)
                    ):
                        from gaspatchio_core.polars_backend.operators import (
                            dispatch_list_op,
                        )

                        logger.trace("Routing clip to polars_backend dispatch_list_op")
                        result = dispatch_list_op(name, base_expr, a, kw)
                    else:
                        result = _execute_regular(polars_attr, a, kw)
        else:
            result = _execute_regular(polars_attr, a, kw)
    except Exception as e:
        raise error_enhancer.enhance_method_error(e, name) from e

    return _wrap(parent_af, result)


__all__ = [
    "_BACKEND_LIST_OPS",
    "_NUMERIC_ELEMENTWISE",
    "_NUMERIC_UNARY",
    "_create_method_wrapper",
    "_get_proxy_base_expr",
    "_method_caller",
]
