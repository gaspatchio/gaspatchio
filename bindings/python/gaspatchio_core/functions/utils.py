"""ABOUTME: Utility functions for Excel and other function implementations.
ABOUTME: Provides proxy unwrapping and common patterns for plugin functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn


def to_polars_expression(arg: "IntoExprColumn") -> pl.Expr:
    """Convert any proxy or expression to a Polars expression.

    This function handles the common pattern of unwrapping proxy objects
    to get the underlying Polars expressions that plugin functions expect.

    Args:
        arg: Can be a ColumnProxy, ExpressionProxy, or pl.Expr

    Returns:
        A Polars expression ready for use in plugin functions

    Examples:
        ```python
        # With ColumnProxy
        expr = to_polars_expression(af["column_name"])
        
        # With ExpressionProxy  
        expr = to_polars_expression(af["col"].cast(pl.Date))
        
        # With raw Polars expression
        expr = to_polars_expression(pl.col("column_name"))
        ```
    """
    # Handle ExpressionProxy objects first (they have both _expr and _parent)
    if hasattr(arg, "_expr") and hasattr(arg, "_parent"):
        # This is likely an ExpressionProxy object
        return arg._expr
    
    # Handle ColumnProxy objects by extracting the column name
    elif hasattr(arg, "name") and hasattr(arg, "_parent") and isinstance(arg.name, str):
        # This is likely a ColumnProxy object (name must be a string)
        return pl.col(arg.name)
    
    # Return pl.Expr objects as-is, or pass through other types
    # (which may cause errors downstream if not compatible)
    return arg