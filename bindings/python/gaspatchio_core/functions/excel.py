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


def year_frac(start_date: IntoExprColumn, end_date: IntoExprColumn, basis: int = 1) -> pl.Expr:
    """Calculate the year fraction between two dates using Excel's YEARFRAC function.

    Args:
        start_date: The start date expression or column
        end_date: The end date expression or column
        basis: The day count basis (0-4):
            - 0: US (NASD) 30/360
            - 1: Actual/Actual (default)
            - 2: Actual/360
            - 3: Actual/365
            - 4: European 30/360

    Returns:
        A Polars expression representing the year fraction between the dates
    """
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(start_date, "name") and hasattr(start_date, "_parent"):
        # This is likely a ColumnProxy object
        start_date = pl.col(start_date.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(start_date, "_expr") and hasattr(start_date, "_parent"):
        # This is likely an ExpressionProxy object
        start_date = start_date._expr

    # Handle ColumnProxy objects by extracting the column name
    if hasattr(end_date, "name") and hasattr(end_date, "_parent"):
        # This is likely a ColumnProxy object
        end_date = pl.col(end_date.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(end_date, "_expr") and hasattr(end_date, "_parent"):
        # This is likely an ExpressionProxy object
        end_date = end_date._expr

    return register_plugin_function(
        args=[start_date, end_date],
        plugin_path=LIB,
        function_name="year_frac",
        is_elementwise=True,
        kwargs={"basis": basis},
    )