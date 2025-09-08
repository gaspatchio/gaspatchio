# ABOUTME: Excel EOMONTH function implementation for getting end-of-month dates
# ABOUTME: Provides Excel-compatible end-of-month calculations after adding months
from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn


def eomonth(
    start_date: IntoExprColumn,
    months: IntoExprColumn,
) -> pl.Expr:
    """Get the end of month date after adding months using Excel's EOMONTH logic.
    
    This function provides Excel EOMONTH functionality. It takes a start date,
    adds the specified number of months, and returns the last day of that month.
    
    Args:
        start_date: Start date expression or column (Date or List[Date])
        months: Number of months to add (Int32/Int64 or List[Int])
        
    Returns:
        Polars expression with the end-of-month date after adding months
    """
    start_date_expr = to_polars_expression(start_date)
    months_expr = to_polars_expression(months)
    
    # Cast to appropriate types
    start_date_expr = start_date_expr.cast(pl.Date, strict=False)
    months_expr = months_expr.cast(pl.Int64, strict=False)
    
    # Add months using Polars datetime arithmetic, then get end of month
    # First add the months
    new_date = start_date_expr.dt.offset_by(months_expr.cast(pl.Utf8) + "mo")
    
    # Get the end of the month by getting the first day of the next month and subtracting 1 day
    # Get year and month components
    year = new_date.dt.year()
    month = new_date.dt.month()
    
    # Create first day of next month, then subtract 1 day
    next_month_first = pl.date(
        year + (month == 12).cast(pl.Int32),  # Increment year if December
        ((month % 12) + 1).cast(pl.Int8),     # Next month (1 if December)
        pl.lit(1, dtype=pl.Int8)              # First day
    )
    
    # Return last day of current month
    return next_month_first - pl.duration(days=1)