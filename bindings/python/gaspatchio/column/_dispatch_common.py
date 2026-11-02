# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Proxy conversions used by the explicit Polars-native escape."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio.frame.lowering.columns import column_reference

from .column_proxy import ColumnProxy
from .condition_expression import ConditionExpression
from .expression_proxy import ExpressionProxy

if TYPE_CHECKING:
    import polars as pl

    type ProxyType = ColumnProxy | ExpressionProxy


def _unwrap(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap ColumnProxy, ExpressionProxy, or ConditionExpression to Polars expr."""
    if isinstance(arg, ColumnProxy):
        return column_reference(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr  # noqa: SLF001
    if isinstance(arg, ConditionExpression):
        # Return raw boolean expression for methods like .filter()
        return arg._expr  # noqa: SLF001
    return arg


def _get_proxy_base_expr(proxy: ProxyType) -> pl.Expr:
    """Get the base expression from a proxy object."""
    if isinstance(proxy, ColumnProxy):
        return column_reference(proxy.name)
    if isinstance(proxy, ExpressionProxy):
        return proxy._expr  # noqa: SLF001
    msg = f"Unsupported proxy type: {type(proxy).__name__}"
    raise TypeError(msg)
