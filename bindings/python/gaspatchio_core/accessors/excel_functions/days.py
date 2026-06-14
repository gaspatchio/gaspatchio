# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

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
    """Calculate the number of days between two dates, similar to Excel's DAYS.

    Returns the number of days between a start date and an end date as an integer.
    The result is positive if the end date is after the start date, and negative
    if the end date is before the start date.

    !!! note "When to use"
        * **Policy Duration Calculations:** Determine the exact number of days a policy has been in force for premium calculations or exposure analysis.
        * **Claim Processing Time:** Calculate the number of days between claim filing and settlement for service level tracking.
        * **Grace Period Tracking:** Measure the number of days in grace periods for lapsed policies or late premium payments.
        * **Interest Accrual:** Calculate the exact number of days for interest calculations on policy loans or reserves.
        * **Waiting Period Compliance:** Track waiting periods in days for specific benefits or coverage exclusions.
        * **Performance Metrics:** Measure time-to-issue, underwriting duration, or other process timelines in days.

    Parameters
    ----------
    end_date : IntoExprColumn
        The ending date of the period. Can be a scalar date, a column of dates,
        or a list column of dates.
    start_date : IntoExprColumn
        The starting date of the period. Can be a scalar date, a column of dates,
        or a list column of dates.

    Returns
    -------
    pl.Expr
        A Polars expression containing the number of days as Int64 (or List[Int64]
        for list columns). The result is end_date - start_date.

    Examples
    --------
    **Scalar Example: Policy Duration in Days**

    ```python
    import datetime
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "issue_date": [
            datetime.date(2023, 1, 15),
            datetime.date(2023, 3, 1),
            datetime.date(2023, 6, 10)
        ],
        "valuation_date": [
            datetime.date(2023, 12, 31),
            datetime.date(2023, 12, 31),
            datetime.date(2023, 12, 31)
        ],
    }
    af = ActuarialFrame(data)

    af.days_in_force = af.valuation_date.excel.days(af.issue_date)

    print(af.collect())
    ```

    ```text
    shape: (3, 4)
    ┌───────────┬────────────┬────────────────┬───────────────┐
    │ policy_id ┆ issue_date ┆ valuation_date ┆ days_in_force │
    │ ---       ┆ ---        ┆ ---            ┆ ---           │
    │ str       ┆ date       ┆ date           ┆ i64           │
    ╞═══════════╪════════════╪════════════════╪═══════════════╡
    │ P001      ┆ 2023-01-15 ┆ 2023-12-31     ┆ 350           │
    │ P002      ┆ 2023-03-01 ┆ 2023-12-31     ┆ 305           │
    │ P003      ┆ 2023-06-10 ┆ 2023-12-31     ┆ 204           │
    └───────────┴────────────┴────────────────┴───────────────┘
    ```

    **Vector Example: Monthly Projection Days**

    ```python
    import datetime
    import polars as pl
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.accessors.excel_functions.days import days

    data = {
        "policy_id": ["P001", "P002"],
        "projection_dates": [
            [datetime.date(2024, 1, 1), datetime.date(2024, 2, 1), datetime.date(2024, 3, 1)],
            [datetime.date(2024, 1, 15), datetime.date(2024, 2, 15), datetime.date(2024, 3, 15)]
        ],
        "issue_date": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 1)]
    }
    af = ActuarialFrame(data)

    af.days_from_issue = af.projection_dates.list.eval(
        days(pl.element(), pl.lit(datetime.date(2024, 1, 1)))
    )

    print(af.collect())
    ```

    ```text
    shape: (2, 4)
    ┌───────────┬──────────────────────────────────────┬────────────┬─────────────────┐
    │ policy_id ┆ projection_dates                     ┆ issue_date ┆ days_from_issue │
    │ ---       ┆ ---                                  ┆ ---        ┆ ---             │
    │ str       ┆ list[date]                           ┆ date       ┆ list[i64]       │
    ╞═══════════╪══════════════════════════════════════╪════════════╪═════════════════╡
    │ P001      ┆ [2024-01-01, 2024-02-01, 2024-03-01] ┆ 2024-01-01 ┆ [0, 31, 60]     │
    │ P002      ┆ [2024-01-15, 2024-02-15, 2024-03-15] ┆ 2024-01-01 ┆ [14, 45, 74]    │
    └───────────┴──────────────────────────────────────┴────────────┴─────────────────┘
    ```
    """
    end_date_expr = to_polars_expression(end_date)
    start_date_expr = to_polars_expression(start_date)
    
    # Simple scalar date handling
    # Cast to Date to ensure we're working with dates, not datetimes
    end_date_expr = end_date_expr.cast(pl.Date, strict=False)
    start_date_expr = start_date_expr.cast(pl.Date, strict=False)
    
    # Return the difference in days
    return (end_date_expr - start_date_expr).dt.total_days()