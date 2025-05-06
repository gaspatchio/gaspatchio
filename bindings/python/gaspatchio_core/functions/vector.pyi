from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    # Assuming IntoExprColumn resolves correctly or use pl.Expr directly
    from gaspatchio_core.typing import IntoExprColumn

# Type stubs for the wrapper functions exposed by vector.py

def fill_series(expr: IntoExprColumn, start: int = 0, increment: int = 1) -> pl.Expr:
    """Fill a series using a start value and increment for generated values."""
    ...

def floor(expr: IntoExprColumn, divisor: int = 1, default: int = 0) -> pl.Expr:
    """Floor the values in a series by a divisor, returning a default for errors."""
    ...

def round(expr: IntoExprColumn, decimal_places: int = 0) -> pl.Expr:
    """Round the values in a series to a specified number of decimal places."""
    ...

def round_to_int(expr: IntoExprColumn) -> pl.Expr:
    """Round the values in a series to the nearest integer."""
    ...
