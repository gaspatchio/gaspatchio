# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Internal helpers shared across the Polars lowering primitives.

Kept private (leading underscore) and small — anything that grows here
should justify its own module. Currently houses the proxy-unwrap helper
that plugins.py, operators.py, and masks.py all need.

This helper reads proxy attributes without importing their classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaspatchio.frame.lowering.columns import column_reference

if TYPE_CHECKING:
    import polars as pl


def _unwrap_proxy(expr: Any) -> pl.Expr | Any:  # noqa: ANN401
    """Unwrap ColumnProxy / ExpressionProxy to underlying pl.Expr.

    The plugin operand contract reads a column name before an expression.
    ``expressions.to_polars_expression`` retains the distinct conversion
    contract used by the Excel functions. Neither helper imports the proxy
    classes at module load time.
    """
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        return column_reference(expr.name)
    if hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        return expr._expr  # noqa: SLF001
    return expr
