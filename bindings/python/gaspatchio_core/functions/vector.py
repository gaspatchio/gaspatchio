from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

# Correct path to the compiled library relative to *this* file
# It should point to the directory containing the compiled dynamic library (e.g., .so, .dylib, .dll)
# Adjust this based on your actual build output location.
# Assuming a standard maturin build places it in the root of the bindings/python directory
LIB = (
    Path(__file__).parent.parent / "gaspatchio_core.so"
)  # Adjust extension as needed (.dylib, .dll)


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
