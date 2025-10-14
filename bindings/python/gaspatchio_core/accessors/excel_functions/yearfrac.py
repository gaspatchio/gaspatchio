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
    """Calculate the year fraction between two dates, similar to Excel's YEARFRAC.

    Calculates the fraction of a year represented by the number of whole days
    between two dates, using a specified day count basis. Essential for financial
    and actuarial calculations requiring precise time period measurements.

    !!! note "When to use"
        * **Premium Proration:** Calculate the portion of an annual premium for partial policy terms when policies start or end mid-year.
        * **Exposure Calculation:** Determine fractional exposure periods for reserving, pricing, or IBNR calculations for policies not in force for a full year.
        * **Investment Analysis:** Compute time-weighted returns or accrued interest for investments held for partial years.
        * **Policy Lapse Studies:** Measure policy duration in fractional years for lapse and persistency analysis.
        * **Benefit Accrual:** Calculate prorated benefits or reserves based on partial year periods.
        * **Regulatory Reporting:** Prepare time-based metrics using industry-standard day count conventions for regulatory compliance.

    Parameters
    ----------
    start_date : IntoExprColumn
        The starting date of the period. Can be a scalar date, a column of dates,
        or a list column of dates.
    end_date : IntoExprColumn
        The ending date of the period. Can be a scalar date, a column of dates,
        or a list column of dates.
    basis : int or str, optional
        The day count basis to use. Defaults to 1 (Actual/Actual). Can be:

        - `0` or `'us_nasd_30_360'`: US (NASD) 30/360 convention
        - `1` or `'act/act'`: Actual/Actual convention (default)
        - `2` or `'actual/360'`: Actual/360 convention
        - `3` or `'actual/365'`: Actual/365 convention
        - `4` or `'european_30_360'`: European 30/360 convention

    Returns
    -------
    pl.Expr
        A Polars expression containing the year fraction as Float64 (or List[Float64]
        for list columns).

    Examples
    --------
    **Scalar Example: Premium Proration**

    ```python
    import datetime
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "policy_start": [
            datetime.date(2023, 1, 1),
            datetime.date(2023, 6, 15),
            datetime.date(2023, 9, 1)
        ],
        "policy_end": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 6, 15),
            datetime.date(2024, 3, 1)
        ],
        "annual_premium": [1200.0, 2400.0, 1800.0],
    }
    af = ActuarialFrame(data)

    af.term_fraction = af.policy_start.excel.yearfrac(af.policy_end, basis="act/act")
    af.prorated_premium = af.annual_premium * af.term_fraction

    print(af.collect())
    ```

    ```text
    shape: (3, 6)
    ┌───────────┬──────────────┬────────────┬────────────────┬───────────────┬──────────────────┐
    │ policy_id ┆ policy_start ┆ policy_end ┆ annual_premium ┆ term_fraction ┆ prorated_premium │
    │ ---       ┆ ---          ┆ ---        ┆ ---            ┆ ---           ┆ ---              │
    │ str       ┆ date         ┆ date       ┆ f64            ┆ f64           ┆ f64              │
    ╞═══════════╪══════════════╪════════════╪════════════════╪═══════════════╪══════════════════╡
    │ P001      ┆ 2023-01-01   ┆ 2024-01-01 ┆ 1200.0         ┆ 1.0           ┆ 1200.0           │
    │ P002      ┆ 2023-06-15   ┆ 2024-06-15 ┆ 2400.0         ┆ 1.0           ┆ 2400.0           │
    │ P003      ┆ 2023-09-01   ┆ 2024-03-01 ┆ 1800.0         ┆ 0.497268      ┆ 895.081967       │
    └───────────┴──────────────┴────────────┴────────────────┴───────────────┴──────────────────┘
    ```

    **Vector Example: Monthly Exposure Calculation**

    ```python
    import datetime
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001"],
        "valuation_dates": [[
            datetime.date(2024, 1, 1),
            datetime.date(2024, 2, 1),
            datetime.date(2024, 3, 1)
        ]],
        "issue_date": [datetime.date(2024, 1, 1)]
    }
    af = ActuarialFrame(data)

    af.time_in_force = af.issue_date.excel.yearfrac(af.valuation_dates, basis=1)

    print(af.collect())
    ```

    ```text
    shape: (1, 4)
    ┌───────────┬──────────────────────────────────────┬────────────┬───────────────────────────┐
    │ policy_id ┆ valuation_dates                      ┆ issue_date ┆ time_in_force             │
    │ ---       ┆ ---                                  ┆ ---        ┆ ---                       │
    │ str       ┆ list[date]                           ┆ date       ┆ list[f64]                 │
    ╞═══════════╪══════════════════════════════════════╪════════════╪═══════════════════════════╡
    │ P001      ┆ [2024-01-01, 2024-02-01, 2024-03-01] ┆ 2024-01-01 ┆ [0.0, 0.084699, 0.163934] │
    └───────────┴──────────────────────────────────────┴────────────┴───────────────────────────┘
    ```
    """
    # Convert inputs to Polars expressions, handling literals with pl.lit()
    def ensure_polars_expr(arg):
        # Convert input to Polars expression, handling literals
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
        # Prepare date expression for yearfrac by handling type conversions
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


