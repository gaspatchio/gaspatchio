# ABOUTME: Excel DAYS function implementation for calculating days between dates
# ABOUTME: Provides Excel-compatible date difference calculations with proper null handling
from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn


def days(
    end_date: IntoExprColumn,
    start_date: IntoExprColumn,
) -> pl.Expr:
    """Calculate the number of days between two dates using Excel's DAYS logic.
    
    This function provides Excel DAYS functionality. It calculates the difference
    between an end date and start date, returning the result in days as an integer.
    
    Args:
        end_date: End date expression or column (Date or List[Date])
        start_date: Start date expression or column (Date or List[Date])
        
    Returns:
        Polars expression with the days difference calculation (Int64 or List[Int64])
    """
    end_date_expr = to_polars_expression(end_date)
    start_date_expr = to_polars_expression(start_date)
    
    # Simple scalar date handling
    # Cast to Date to ensure we're working with dates, not datetimes
    end_date_expr = end_date_expr.cast(pl.Date, strict=False)
    start_date_expr = start_date_expr.cast(pl.Date, strict=False)
    
    # Return the difference in days
    return (end_date_expr - start_date_expr).dt.total_days()