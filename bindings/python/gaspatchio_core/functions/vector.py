from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

# Import the internal module to get its path
try:
    from gaspatchio_core import _internal
except ImportError as e:
    raise ImportError(
        "Failed to import the gaspatchio_core native extension (_internal). "
        "Ensure the project is built and installed correctly (e.g., using 'maturin develop -uv')."
    ) from e

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

# Get the path to the compiled extension from the imported module
LIB = Path(_internal.__file__)


def fill_series(expr: IntoExprColumn, start: int = 0, increment: int = 1) -> pl.Expr:
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        # This is likely a ColumnProxy object
        expr = pl.col(expr.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        # This is likely an ExpressionProxy object
        expr = expr._expr

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="fill_series",
        is_elementwise=True,
        kwargs={"start": start, "increment": increment},
    )


def floor(expr: IntoExprColumn, divisor: int = 1, default: int = 0) -> pl.Expr:
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        # This is likely a ColumnProxy object
        expr = pl.col(expr.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        # This is likely an ExpressionProxy object
        expr = expr._expr

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="floor",
        is_elementwise=True,
        kwargs={"divisor": divisor, "default": default},
    )


def round(expr: IntoExprColumn, decimal_places: int = 0) -> pl.Expr:
    # Handle ColumnProxy and ExpressionProxy
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        expr = pl.col(expr.name)
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        expr = expr._expr

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="round",
        is_elementwise=True,
        kwargs={"decimal_places": decimal_places},
    )


def round_to_int(expr: IntoExprColumn) -> pl.Expr:
    # Handle ColumnProxy and ExpressionProxy
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        expr = pl.col(expr.name)
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        expr = expr._expr

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="round_to_int",
        is_elementwise=True,
    )
