from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

# Type stubs for the wrapper functions exposed by vector.py

def fill_series(expr: pl.Expr, *, limit: int) -> pl.Expr:
    """Fill forward missing values in a series up to a limit."""
    ...

def floor(expr: pl.Expr, *, divisor: float = 1.0) -> pl.Expr:
    """Floor the values in a series by a divisor."""
    ...

def round(expr: pl.Expr, *, decimals: int = 0) -> pl.Expr:
    """Round the values in a series to a specified number of decimals."""
    ...

def round_to_int(expr: pl.Expr, *, strategy: str = "nearest") -> pl.Expr:
    """Round the values in a series to the nearest integer using a specified strategy."""
    ...
