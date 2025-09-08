# ABOUTME: Excel EDATE function implementation for adding months to dates
# ABOUTME: Provides Excel-compatible month addition with proper boundary handling
from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn


def edate(
    start_date: IntoExprColumn,
    months: IntoExprColumn,
) -> pl.Expr:
    """Add months to a date using Excel's EDATE logic.
    
    This function provides Excel EDATE functionality. It takes a start date
    and adds the specified number of months to it, returning the resulting date.
    
    Args:
        start_date: Start date expression or column (Date or List[Date])
        months: Number of months to add (Int32/Int64 or List[Int])
        
    Returns:
        Polars expression with the date after adding months
    """
    start_date_expr = to_polars_expression(start_date)
    months_expr = to_polars_expression(months)
    
    # Cast to appropriate types
    start_date_expr = start_date_expr.cast(pl.Date, strict=False)
    months_expr = months_expr.cast(pl.Int64, strict=False)
    
    # Add months using Polars datetime arithmetic
    # Convert months to a duration string and use offset_by
    # This handles month boundaries correctly (e.g., Jan 31 + 1 month = Feb 28/29)
    return start_date_expr.dt.offset_by(months_expr.cast(pl.Utf8) + "mo")