# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

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
    """Get the end of month after adding months, similar to Excel's EOMONTH.

    Returns the last day of the month that is the indicated number of months
    before or after the start date. Useful for calculating maturity dates, due
    dates, or any calculations requiring month-end boundaries.

    !!! note "When to use"
        * **Reporting Periods:** Determine month-end dates for financial reporting or regulatory submissions.
        * **Interest Calculations:** Calculate interest accrual periods that end on the last day of each month.
        * **Benefit Payment Dates:** Set benefit payment dates to month-end when payments are made monthly.
        * **Policy Term Boundaries:** Define policy terms or coverage periods that end on month boundaries.
        * **Maturity Dates:** Calculate investment or policy maturity dates that fall on the last day of a month.
        * **Regulatory Deadlines:** Determine month-end regulatory filing or compliance deadlines.

    Parameters
    ----------
    start_date : IntoExprColumn
        The starting date. Can be a scalar date, a column of dates,
        or a list column of dates.
    months : IntoExprColumn
        Number of months to add before getting the end of month. Can be positive
        (future dates) or negative (past dates). Non-integer values are truncated.
        Can be a scalar, a column, or a list column.

    Returns
    -------
    pl.Expr
        A Polars expression containing the end-of-month date (or List[Date]
        for list columns) for the calculated month.

    Examples
    --------
    **Scalar Example: Policy Maturity End-of-Month Dates**

    ```python
    import datetime
    from gaspatchio_core import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "issue_date": [
            datetime.date(2023, 1, 15),
            datetime.date(2023, 3, 5),
            datetime.date(2023, 5, 20)
        ],
        "term_months": [12, 24, 6],
    }
    af = ActuarialFrame(data)

    af.maturity_eom = af.issue_date.excel.eomonth(af.term_months)

    print(af.collect())
    ```

    ```text
    shape: (3, 4)
    ┌───────────┬────────────┬─────────────┬──────────────┐
    │ policy_id ┆ issue_date ┆ term_months ┆ maturity_eom │
    │ ---       ┆ ---        ┆ ---         ┆ ---          │
    │ str       ┆ date       ┆ i64         ┆ date         │
    ╞═══════════╪════════════╪═════════════╪══════════════╡
    │ P001      ┆ 2023-01-15 ┆ 12          ┆ 2024-01-31   │
    │ P002      ┆ 2023-03-05 ┆ 24          ┆ 2025-03-31   │
    │ P003      ┆ 2023-05-20 ┆ 6           ┆ 2023-11-30   │
    └───────────┴────────────┴─────────────┴──────────────┘
    ```

    **Vector Example: Monthly Reporting Period Ends**

    ```python
    import datetime
    import polars as pl
    from gaspatchio_core import ActuarialFrame
    from gaspatchio_core.accessors.excel_functions.eomonth import eomonth

    data = {
        "policy_id": ["P001", "P002"],
        "valuation_date": [datetime.date(2024, 1, 15), datetime.date(2024, 3, 10)],
        "projection_months": [[0, 1, 2, 3], [0, 3, 6, 12]]
    }
    af = ActuarialFrame(data)

    af.period_ends = af.projection_months.list.eval(
        eomonth(pl.lit(datetime.date(2024, 1, 15)), pl.element())
    )

    print(af.collect())
    ```

    ```text
    shape: (2, 4)
    ┌───────────┬────────────────┬───────────────────┬────────────────────────────────────────┐
    │ policy_id ┆ valuation_date ┆ projection_months ┆ period_ends                            │
    │ ---       ┆ ---            ┆ ---               ┆ ---                                    │
    │ str       ┆ date           ┆ list[i64]         ┆ list[date]                             │
    ╞═══════════╪════════════════╪═══════════════════╪════════════════════════════════════════╡
    │ P001      ┆ 2024-01-15     ┆ [0, 1, … 3]       ┆ [2024-01-31, 2024-02-29, … 2024-04-30] │
    │ P002      ┆ 2024-03-10     ┆ [0, 3, … 12]      ┆ [2024-01-31, 2024-04-30, … 2025-01-31] │
    └───────────┴────────────────┴───────────────────┴────────────────────────────────────────┘
    ```
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