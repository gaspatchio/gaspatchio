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
    """Add months to a date, similar to Excel's EDATE.

    Returns the date that is the indicated number of months before or after
    a specified start date. Handles month boundaries correctly (e.g., January 31
    plus 1 month becomes February 28 or 29).

    !!! note "When to use"
        * **Policy Anniversary Dates:** Calculate policy renewal dates or anniversary dates by adding months to the issue date.
        * **Payment Schedules:** Determine future premium due dates or benefit payment dates based on monthly intervals.
        * **Maturity Calculations:** Calculate policy or investment maturity dates by adding a term in months to the start date.
        * **Projection Periods:** Generate future valuation dates for cash flow projections or reserving calculations.
        * **Grace Period Tracking:** Calculate expiration dates for grace periods or reinstatement windows.
        * **Regulatory Deadlines:** Determine regulatory filing or compliance deadlines that are specified in months.

    Parameters
    ----------
    start_date : IntoExprColumn
        The starting date. Can be a scalar date, a column of dates,
        or a list column of dates.
    months : IntoExprColumn
        Number of months to add. Can be positive (future dates) or negative
        (past dates). Non-integer values are truncated. Can be a scalar,
        a column, or a list column.

    Returns
    -------
    pl.Expr
        A Polars expression containing the resulting date (or List[Date]
        for list columns) after adding the specified months.

    Examples
    --------
    **Scalar Example: Policy Renewal Dates**

    ```python
    import datetime
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "issue_date": [
            datetime.date(2023, 1, 31),
            datetime.date(2023, 3, 15),
            datetime.date(2023, 5, 30)
        ],
        "term_months": [12, 24, 6],
    }
    af = ActuarialFrame(data)

    af.renewal_date = af.issue_date.excel.edate(af.term_months)

    print(af.collect())
    ```

    ```text
    shape: (3, 4)
    ┌───────────┬────────────┬─────────────┬──────────────┐
    │ policy_id ┆ issue_date ┆ term_months ┆ renewal_date │
    │ ---       ┆ ---        ┆ ---         ┆ ---          │
    │ str       ┆ date       ┆ i64         ┆ date         │
    ╞═══════════╪════════════╪═════════════╪══════════════╡
    │ P001      ┆ 2023-01-31 ┆ 12          ┆ 2024-01-31   │
    │ P002      ┆ 2023-03-15 ┆ 24          ┆ 2025-03-15   │
    │ P003      ┆ 2023-05-30 ┆ 6           ┆ 2023-11-30   │
    └───────────┴────────────┴─────────────┴──────────────┘
    ```

    **Vector Example: Monthly Projection Dates**

    ```python
    import datetime
    import polars as pl
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.accessors.excel_functions.edate import edate

    data = {
        "policy_id": ["P001", "P002"],
        "issue_date": [datetime.date(2024, 1, 31), datetime.date(2024, 3, 15)],
        "projection_months": [[0, 1, 2, 3], [0, 6, 12, 18]]
    }
    af = ActuarialFrame(data)

    af.projection_dates = af.projection_months.list.eval(
        edate(pl.lit(datetime.date(2024, 1, 31)), pl.element())
    )

    print(af.collect())
    ```

    ```text
    shape: (2, 4)
    ┌───────────┬────────────┬───────────────────┬────────────────────────────────────────┐
    │ policy_id ┆ issue_date ┆ projection_months ┆ projection_dates                       │
    │ ---       ┆ ---        ┆ ---               ┆ ---                                    │
    │ str       ┆ date       ┆ list[i64]         ┆ list[date]                             │
    ╞═══════════╪════════════╪═══════════════════╪════════════════════════════════════════╡
    │ P001      ┆ 2024-01-31 ┆ [0, 1, … 3]       ┆ [2024-01-31, 2024-02-29, … 2024-04-30] │
    │ P002      ┆ 2024-03-15 ┆ [0, 6, … 18]      ┆ [2024-01-31, 2024-07-31, … 2025-07-31] │
    └───────────┴────────────┴───────────────────┴────────────────────────────────────────┘
    ```
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