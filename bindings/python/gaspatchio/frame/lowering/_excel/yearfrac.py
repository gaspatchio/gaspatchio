# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars implementation of the Excel-compatible yearfrac function."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from polars.plugins import register_plugin_function

from gaspatchio._internal import __file__ as native_path
from gaspatchio.frame.lowering._polars.expressions import to_polars_expression

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.typing import IntoExprColumn

LIB = Path(native_path)

# A day-count basis: 0-4, or one of the names (and aliases) the mapping in
# :func:`yearfrac` reads, in any case. Anything else is refused there by name.
# A ``Literal`` of the canonical spellings would leave out the aliases the
# function accepts, and one unioned with ``int | str`` constrains nothing.
BasisType = int | str


def yearfrac(
    start_date: IntoExprColumn,
    end_date: IntoExprColumn,
    basis: BasisType = 1,
) -> pl.Expr:
    """Calculate the year fraction between two dates, as Excel's YEARFRAC does.

    Calculates the fraction of a year represented by the number of whole days
    between two dates, using a specified day count basis. Essential for financial
    and actuarial calculations requiring precise time period measurements. As
    in Excel, the order of the two dates does not matter: the earlier is the
    start and the answer is never negative.

    !!! note "When to use"
        * **Premium Proration:** Calculate the portion of an annual premium for partial
          policy terms when policies start or end mid-year.
        * **Exposure Calculation:** Determine fractional exposure periods for reserving,
          pricing, or IBNR calculations for policies not in force for a full year.
        * **Investment Analysis:** Compute time-weighted returns or accrued interest for
          investments held for partial years.
        * **Policy Lapse Studies:** Measure policy duration in fractional years for
          lapse and persistency analysis.
        * **Benefit Accrual:** Calculate prorated benefits or reserves based on partial
          year periods.
        * **Regulatory Reporting:** Prepare time-based metrics using industry-standard
          day count conventions for regulatory compliance.

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
    from gaspatchio import ActuarialFrame

    data = {
        "policy_id": ["P001", "P002", "P003"],
        "policy_start": [
            datetime.date(2023, 1, 1),
            datetime.date(2023, 6, 15),
            datetime.date(2023, 9, 1),
        ],
        "policy_end": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 6, 15),
            datetime.date(2024, 3, 1),
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
    from gaspatchio import ActuarialFrame

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
    # Convert inputs to Polars expressions: a column name reads the column,
    # and a literal (a date, a Series) becomes pl.lit().
    start_date_expr = to_polars_expression(start_date)
    end_date_expr = to_polars_expression(end_date)

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
            msg = (
                f"Invalid basis '{basis}'. Valid values are: 0-4 or "
                f"{', '.join(sorted(set(basis_map.keys())))}"
            )
            raise ValueError(msg)
        basis_int = basis_map[basis_lower]
    else:
        basis_int = int(basis)
        if basis_int not in range(5):
            msg = f"Invalid basis {basis_int}. Must be an integer between 0 and 4."
            raise ValueError(msg)

    # The Rust side takes Date or List[Date] and does its own validation, so
    # the expressions are passed through as they were built. A cast here could
    # not serve both shapes: List[Date] cannot be cast to Date.
    start_date_final = start_date_expr
    end_date_final = end_date_expr

    return register_plugin_function(
        args=[start_date_final, end_date_final],
        plugin_path=LIB,
        function_name="yearfrac",
        is_elementwise=True,
        kwargs={"basis": basis_int},
    )
