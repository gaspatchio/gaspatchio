# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for proxy dispatch internals.

This module contains the small bits of glue that are needed by all three
dispatch concerns:
- namespace proxying
- method execution / routing
- autopatch / delegation
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame

    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    ProxyType = ColumnProxy | ExpressionProxy


def _unwrap(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap ColumnProxy, ExpressionProxy, or ConditionExpression to Polars expr."""
    from .column_proxy import ColumnProxy
    from .condition_expression import ConditionExpression
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr  # noqa: SLF001
    if isinstance(arg, ConditionExpression):
        # Return raw boolean expression for methods like .filter()
        return arg._expr  # noqa: SLF001
    return arg


def _unwrap_for_arithmetic(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap for arithmetic, converting ConditionExpression to boolean float."""
    from .condition_expression import ConditionExpression

    if isinstance(arg, ConditionExpression):
        # For arithmetic ops, convert to boolean float (0.0/1.0).
        return arg._to_boolean_expr()  # noqa: SLF001
    return _unwrap(arg)


def _wrap(
    parent: Optional["ActuarialFrame"],
    result: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Wrap Polars Expressions into ExpressionProxy."""
    from .expression_proxy import ExpressionProxy

    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
    return result


def _ensure_polars_expr_or_literal(
    arg: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Convert argument to Polars expression or literal if needed."""
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return _unwrap(arg) if hasattr(arg, "_expr") or hasattr(arg, "name") else arg


def _get_proxy_base_expr(proxy: "ProxyType") -> pl.Expr:
    """Get the base expression from a proxy object."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    if isinstance(proxy, ColumnProxy):
        return pl.col(proxy.name)
    if isinstance(proxy, ExpressionProxy):
        return proxy._expr  # noqa: SLF001
    msg = f"Unsupported proxy type: {type(proxy).__name__}"
    raise TypeError(msg)
