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
    start_date = to_polars_expression(start_date)
    end_date = to_polars_expression(end_date)
    
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
            "actual/365": 3,
            "actual_365": 3,
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

    # Don't cast if already the right type (Date or List[Date])
    # The Rust function handles both scalar and list types
    start_date_expr = start_date
    end_date_expr = end_date

    return register_plugin_function(
        args=[start_date_expr, end_date_expr],
        plugin_path=LIB,
        function_name="yearfrac",
        is_elementwise=True,
        kwargs={"basis": basis_int},
    )


