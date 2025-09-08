from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal, Union

import polars as pl
from polars.plugins import register_plugin_function

from gaspatchio_core import _internal
from gaspatchio_core.functions.utils import to_polars_expression

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(_internal.__file__)

BasisType = Union[
    Literal[
        0,
        1,
        2,
        3,
        4,
        "us_nasd_30_360",
        "act/act",
        "actual/360",
        "actual/365",
        "european_30_360",
    ],
    int,
    str,
]


def yearfrac(
    start_date: IntoExprColumn,
    end_date: IntoExprColumn,
    basis: BasisType = 1,
) -> pl.Expr:
    """Calculate the year fraction between two dates using Excel's YEARFRAC logic.
    
    This function provides Excel YEARFRAC functionality through a Rust implementation.
    It supports scalar dates, list columns of dates, and broadcasting between scalar
    and list columns (matching Excel 365's dynamic array behavior).
    
    Args:
        start_date: Start date expression or column (Date or List[Date])
        end_date: End date expression or column (Date or List[Date])
        basis: Day count basis (0-4 or string name)
        
    Returns:
        Polars expression with the year fraction calculation
    """
    # Convert inputs to Polars expressions, handling literals with pl.lit()
    def ensure_polars_expr(arg):
        """Convert input to Polars expression, handling literals."""
        expr_candidate = to_polars_expression(arg)
        # If it's still not a Polars expression, wrap it in pl.lit()
        if not isinstance(expr_candidate, pl.Expr):
            return pl.lit(expr_candidate)
        return expr_candidate
    
    start_date_expr = ensure_polars_expr(start_date)
    end_date_expr = ensure_polars_expr(end_date)
    
    # Convert basis to integer if it's a string
    if isinstance(basis, str):
        # Map string basis to integer
        basis_map = {
            "us_nasd_30_360": 0,
            "30/360": 0,
            "act/act": 1,
            "actual/actual": 1,
            "actual/360": 2,
            "actual_360": 2,
            "act/360": 2,  # Common alias
            "actual/365": 3,
            "actual_365": 3,
            "act/365": 3,  # Common alias
            "european_30_360": 4,
            "30e/360": 4,  # lowercase e for consistency
        }
        basis_lower = basis.lower()
        if basis_lower not in basis_map:
            raise ValueError(
                f"Invalid basis '{basis}'. Valid values are: 0-4 or "
                f"{', '.join(sorted(set(basis_map.keys())))}"
            )
        basis_int = basis_map[basis_lower]
    else:
        basis_int = int(basis)
        if basis_int not in range(5):
            raise ValueError(
                f"Invalid basis {basis_int}. Must be an integer between 0 and 4."
            )

    # The Rust function expects Date or List[Date] types
    # Apply type conversions to handle common cases:
    # 1. Datetime columns -> cast to Date
    # 2. String columns -> parse as dates
    # 3. List columns -> pass through (Rust handles List[Datetime] -> List[Date])
    
    def prepare_date_expr(expr: pl.Expr) -> pl.Expr:
        """Prepare date expression for yearfrac by handling type conversions."""
        # Try to cast to date - this handles:
        # - Date columns (no-op)
        # - Datetime columns (converts to date)
        # - String columns that look like dates
        # For list columns, this will fail but that's OK - we'll catch it
        try:
            # First try: assume it might be a datetime and extract date
            # This is a lazy operation, so it won't fail here
            return expr.dt.date()
        except:
            # If dt.date() doesn't work, try casting
            return expr.cast(pl.Date, strict=False)
    
    # Apply conversions - these are lazy operations
    # For scalar columns: cast datetime to date
    # For list columns: pass through unchanged (Rust handles list validation)
    # We can't cast List[Date] to Date, so we skip the cast for lists
    start_date_final = start_date_expr
    end_date_final = end_date_expr

    return register_plugin_function(
        args=[start_date_final, end_date_final],
        plugin_path=LIB,
        function_name="yearfrac",
        is_elementwise=True,
        kwargs={"basis": basis_int},
    )


