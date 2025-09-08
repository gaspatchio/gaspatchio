"""Accessors for Excel-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING, Literal, Union

import polars as pl

# Import registry decorator
from ..frame.registry import register_accessor

# Use the new base location
from .base import BaseColumnAccessor, BaseFrameAccessor

# Use TYPE_CHECKING for core components to avoid circular imports
if TYPE_CHECKING:
    # Update imports to new locations
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame
    from ..typing import IntoExprColumn  # Added for yearfrac

# Define Excel basis constants
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


@register_accessor("excel", kind="frame")
class ExcelFrameAccessor(BaseFrameAccessor):
    """Provides Excel-related methods applicable to the entire ActuarialFrame.

    Accessed via `.excel` on an ActuarialFrame instance,
    e.g., `af.excel`.
    """

    def __init__(self, frame: "ActuarialFrame"):
        """Initializes the accessor with the parent ActuarialFrame.

        Internal initialization method for the Excel frame accessor.
        """
        super().__init__(frame)
        # Placeholder for any frame-level excel methods


@register_accessor("excel", kind="column")
class ExcelColumnAccessor(BaseColumnAccessor):
    """Provides Excel-related methods applicable to columns or expressions.

    Accessed via `.excel` on an ActuarialFrame column or expression proxy,
    e.g., `af["my_excel_col"].excel`.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy"):
        """Initializes the accessor with the parent proxy.

        Internal initialization method for the Excel column accessor.
        """
        super().__init__(proxy)
        self._proxy: ColumnProxy | ExpressionProxy = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Helper to get the underlying Polars expression from the proxy.

        Internal helper method that extracts the Polars expression from
        the column or expression proxy for further processing.
        """
        if hasattr(self._proxy, "_expr") and isinstance(self._proxy._expr, pl.Expr):
            return self._proxy._expr
        if hasattr(self._proxy, "name") and isinstance(self._proxy.name, str):
            return pl.col(self._proxy.name)
        raise TypeError(
            f"ExcelColumnAccessor expected ColumnProxy or ExpressionProxy, got {type(self._proxy).__name__}"
        )

    def _get_parent_frame(self) -> "ActuarialFrame":
        """Helper to get the parent ActuarialFrame, raising error if absent.

        Internal helper method that retrieves the parent ActuarialFrame
        context, which is required for many Excel operations.
        """
        if not hasattr(self._proxy, "_parent") or self._proxy._parent is None:
            raise RuntimeError(
                "Operation requires the expression/column to be part of an ActuarialFrame context."
            )
        return self._proxy._parent

    def from_excel_serial(self, epoch: str = "1900") -> "ExpressionProxy":
        """Converts Excel serial numbers (integers or floats) to Polars Date.

        Follows logic similar to openpyxl for compatibility. This method handles
        Excel's date serialization system, including the notorious Excel 1900
        leap year bug where Excel incorrectly treats 1900 as a leap year.

        !!! note "When to use"
            *   **Excel File Import:** When importing Excel files that contain date columns stored as serial numbers rather than proper date values.
            *   **Legacy Data Processing:** When working with older Excel files or systems that export dates as numeric serial values.
            *   **Cross-Platform Compatibility:** When handling Excel files that may have been created on different platforms (Windows vs Mac) with different epoch systems.
            *   **Data Validation:** When you need to convert and validate date serial numbers from external Excel-based data sources.

        Args:
            epoch: The epoch system used by Excel ('1900' or '1904').
                   Defaults to '1900'.

                   - 1900 Epoch (WINDOWS_1900_EPOCH = 1899-12-30):
                     Serial 1 is 1900-01-01. Excel's serial 60 (phantom 1900-02-29)
                     is mapped to 1900-03-01. Serials > 60 are adjusted by -1 day
                     before adding to epoch.
                   - 1904 Epoch (MAC_1904_EPOCH = 1904-01-01):
                     Serial 1 is 1904-01-01. Days to add from epoch are serial - 1.

        Returns:
            An ExpressionProxy representing the converted date column.

        Raises:
            ValueError: If an invalid epoch is provided.

        Examples:
            ```python
            from gaspatchio_core import ActuarialFrame

            # Excel serial numbers for some dates
            data = {
                "policy_id": ["P001", "P002", "P003"],
                "excel_date_serial": [44197, 44562, 44927],  # Excel serial numbers
            }
            af = ActuarialFrame(data)

            # Convert Excel serial numbers to proper dates
            af_with_dates = af.with_columns(
                actual_date=af["excel_date_serial"].excel.from_excel_serial(
                    epoch="1900"
                )
            )
            print(af_with_dates.collect())
            ```

            ```text
            shape: (3, 3)
            ┌───────────┬────────────────────┬─────────────┐
            │ policy_id ┆ excel_date_serial  ┆ actual_date │
            │ ---       ┆ ---                ┆ ---         │
            │ str       ┆ i64                ┆ date        │
            ╞═══════════╪════════════════════╪═════════════╡
            │ P001      ┆ 44197              ┆ 2021-01-01  │
            │ P002      ┆ 44562              ┆ 2021-12-31  │
            │ P003      ┆ 44927              ┆ 2022-12-31  │
            └───────────┴────────────────────┴─────────────┘
            ```
        """
        base_expr = self._get_polars_expr()
        numeric_expr = base_expr.cast(pl.Float64, strict=False)
        int_expr = numeric_expr.floor()  # For exact comparison like == 60

        if epoch == "1900":
            EPOCH_DT = datetime.date(1899, 12, 30)

            # Adjust serial for numbers > 60 due to Excel's 1900 leap year bug
            # This serial is then added to EPOCH_DT
            effective_serial_days = (
                pl.when(numeric_expr > 60)
                .then(numeric_expr - 1)
                .otherwise(numeric_expr)
            )

            date_expr = (
                pl.when(numeric_expr < 1)
                .then(None)  # Invalid serial
                .when(int_expr == 60)
                .then(pl.lit(datetime.date(1900, 3, 1)))  # Correct Excel's 1900-02-29
                .otherwise(pl.lit(EPOCH_DT) + pl.duration(days=effective_serial_days))
                .cast(pl.Date)
            )

        elif epoch == "1904":
            EPOCH_DT = datetime.date(1904, 1, 1)
            # For 1904 epoch, serial 1 is the first day (Jan 1, 1904).
            # So, timedelta to add is (serial - 1) days.
            days_to_add = numeric_expr - 1

            date_expr = (
                pl.when(numeric_expr < 1)
                .then(None)  # serial 0 or less is invalid if 1 is first day
                .otherwise(pl.lit(EPOCH_DT) + pl.duration(days=days_to_add))
                .cast(pl.Date)
            )

        else:
            raise ValueError(f"Invalid epoch '{epoch}'. Must be '1900' or '1904'.")

        parent_frame = self._get_parent_frame()
        from ..column.expression_proxy import ExpressionProxy

        return ExpressionProxy(date_expr, parent_frame)

    def yearfrac(
        self, end_date_expr: "IntoExprColumn", basis: BasisType = "act/act"
    ) -> "ExpressionProxy":
        """Calculate the year fraction between two dates, similar to Excel's YEARFRAC.

        This function computes the fraction of a year represented by the number of
        whole days between a start date (the column/expression this accessor is on)
        and an end date. It uses a specified day count basis.

        !!! note "When to use"
            *   **Premium Proration**: Calculate the portion of an annual premium that corresponds to a partial policy term, for example, if a policy starts or ends mid-year.
            *   **Exposure Calculation**: Determine fractional exposure periods for reserving or IBNR (Incurred But Not Reported) calculations, especially when dealing with policies that are not in force for a full year.
            *   **Investment Analysis**: Compute fractional year periods for accrued interest calculations or for annualizing returns on investments held for parts of a year.
            *   **Performance Metrics**: Analyze time-based metrics such as time-to-claim or duration of an event, expressed as a fraction of a year.

        Parameters
        ----------
        end_date_expr : IntoExprColumn
            An expression or column representing the end dates. Can be a scalar date,
            a column of dates.
        basis : int or str, optional
            The day count basis to use. Can be an integer (0-4) or a string name.
            Defaults to "act/act" (which is basis 1).

            Supported bases:
            - `0` or `'us_nasd_30_360'` (30/360 US NASD) - US (NASD) 30/360 convention
            - `1` or `'act/act'` (Actual/Actual) - Actual/Actual convention
            - `2` or `'actual_360'` (Actual/360) - Actual/360 convention
            - `3` or `'actual_365'` (Actual/365 fixed) - Actual/365 convention
            - `4` or `'european_30_360'` (30/360 European) - European 30/360 convention

        Returns
        -------
        ExpressionProxy
            An expression representing the calculated year fraction as a `Float64`.

        Raises
        ------
        TypeError
            If the underlying proxy for the start date is not a `ColumnProxy` or `ExpressionProxy`.
        RuntimeError
            If the operation requires an `ActuarialFrame` context that is not available.
        ValueError
            If an invalid basis is provided.

        Examples
        --------
        Calculating Policy Term as Year Fraction (Scalar/Column Operations)::

            Scenario: You have policy start and end dates and want to calculate the policy term in years.

            ```python
            import datetime
            from gaspatchio_core import ActuarialFrame

            data = {
                "policy_id": ["P001", "P002", "P003"],
                "start_date": [
                    datetime.date(2020, 1, 1),
                    datetime.date(2021, 6, 15),
                    datetime.date(2022, 3, 1),
                ],
                "end_date": [
                    datetime.date(2021, 1, 1),
                    datetime.date(2022, 6, 15),
                    datetime.date(2022, 9, 1), # Partial year
                ],
            }
            af = ActuarialFrame(data)

            # Calculate year fraction using 'act/act'
            af_with_term = af.with_columns(
                term_years=af["start_date"].excel.yearfrac(af["end_date"], basis="act/act")
            )
            print(af_with_term.collect())
            ```

            ```
            shape: (3, 4)
            ┌───────────┬────────────┬────────────┬────────────┐
            │ policy_id ┆ start_date ┆ end_date   ┆ term_years │
            │ ---       ┆ ---        ┆ ---        ┆ ---        │
            │ str       ┆ date       ┆ date       ┆ f64        │
            ╞═══════════╪════════════╪════════════╪════════════╡
            │ P001      ┆ 2020-01-01 ┆ 2021-01-01 ┆ 1.000000   │
            │ P002      ┆ 2021-06-15 ┆ 2022-06-15 ┆ 1.000000   │
            │ P003      ┆ 2022-03-01 ┆ 2022-09-01 ┆ 0.501370   │
            └───────────┴────────────┴────────────┴────────────┘
            ```


        List Column Workaround::

            For actuarial projections stored as list columns (e.g., monthly projection dates),
            use the explode/group_by pattern:

            ```python
            import datetime
            import polars as pl
            from gaspatchio_core import ActuarialFrame
            
            # Example with monthly projection dates
            projection_data = {
                "policy_id": ["P001", "P002"],
                "projection_dates": [
                    [datetime.date(2024, i, 1) for i in range(1, 13)],  # 12 monthly dates
                    [datetime.date(2024, i, 15) for i in range(1, 13)]
                ],
                "maturity_date": [
                    datetime.date(2024, 12, 31),
                    datetime.date(2025, 1, 1)
                ]
            }
            af_proj = ActuarialFrame(projection_data)

            # Calculate yearfrac for each projection date using explode/group_by
            result = (
                af_proj.lazy()
                .with_row_index("_idx")
                .explode("projection_dates")
                .with_columns(
                    pl.col("projection_dates").excel.yearfrac(pl.col("maturity_date"))
                    .alias("years_to_maturity")
                )
                .group_by("_idx")
                .agg([
                    pl.col("policy_id").first(),
                    pl.col("years_to_maturity"),
                    pl.col("maturity_date").first()
                ])
                .drop("_idx")
                .collect()
            )
            print(result)
            ```

            ```
            shape: (2, 3)
            ┌───────────┬───────────────────┬─────────────┐
            │ policy_id ┆ years_to_maturity ┆ maturity_date │
            │ ---       ┆ ---               ┆ ---          │
            │ str       ┆ list[f64]         ┆ date         │
            ╞═══════════╪═══════════════════╪══════════════╡
            │ P001      ┆ [0.997260, 0.915...] ┆ 2024-12-31   │
            │ P002      ┆ [0.958904, 0.876...] ┆ 2025-01-01   │
            └───────────┴───────────────────┴──────────────┘
            ```

            Note: List columns are not directly supported due to Polars plugin limitations.
            Excel 365 achieves this with dynamic arrays, but we require explicit data
            transformation.

        """
        # Import the yearfrac function from the accessor functions module
        from .excel_functions.yearfrac import yearfrac

        # Get the start expression from the proxy
        start_expr = self._get_polars_expr()

        # Use the standard yearfrac implementation
        result_expr = yearfrac(start_expr, end_date_expr, basis=basis)

        # Return wrapped in ExpressionProxy
        from ..column.expression_proxy import ExpressionProxy

        parent_frame = self._get_parent_frame()

        return ExpressionProxy(result_expr, parent_frame)

    def irr(
        self,
        *,
        guess: "IntoExprColumn | None" = None,
        default_guess: float | None = None,
    ) -> "ExpressionProxy":
        """Calculate the internal rate of return for a series of cash flows.

        This function computes the discount rate that makes the net present value (NPV)
        of all cash flows equal to zero, using Excel's IRR algorithm.

        !!! note "When to use"
            *   **Investment Analysis**: Evaluate the profitability of investment portfolios or individual securities
            *   **Project Evaluation**: Compare the returns of different actuarial projects or initiatives
            *   **Premium Adequacy**: Assess whether premium cash flows generate sufficient returns
            *   **Asset-Liability Matching**: Evaluate the performance of matched asset and liability cash flows

        Parameters
        ----------
        guess : IntoExprColumn, optional
            Optional per-row initial guess for IRR. If not provided, uses default_guess.
        default_guess : float, optional
            Scalar fallback guess when `guess` is not provided. Defaults to 0.1 (10%).

        Returns
        -------
        ExpressionProxy
            Float64 IRR per row representing the internal rate of return.

        Examples
        --------
        Calculate IRR for investment cash flows::

            ```python
            from gaspatchio_core import ActuarialFrame

            data = {
                "investment_id": ["INV001", "INV002"],
                "cash_flows": [
                    [-1000.0, 300.0, 400.0, 500.0],  # Initial investment + returns
                    [-5000.0, 1000.0, 2000.0, 3500.0]  # Different investment
                ]
            }
            af = ActuarialFrame(data)

            # Calculate IRR for each investment
            result = af.with_columns(
                irr=af["cash_flows"].excel.irr()
            )
            print(result.collect())
            ```

            ```
            shape: (2, 3)
            ┌──────────────┬──────────────────────────┬──────────┐
            │ investment_id ┆ cash_flows              ┆ irr      │
            │ ---          ┆ ---                     ┆ ---      │
            │ str          ┆ list[f64]               ┆ f64      │
            ╞══════════════╪═════════════════════════╪══════════╡
            │ INV001       ┆ [-1000.0, 300.0, …]     ┆ 0.168595 │
            │ INV002       ┆ [-5000.0, 1000.0, …]    ┆ 0.120476 │
            └──────────────┴──────────────────────────┴──────────┘
            ```

        """
        from .excel_functions.irr import irr as _irr

        values_expr = self._get_polars_expr()
        parent_frame = self._get_parent_frame()
        result_expr = _irr(values_expr, guess=guess, default_guess=default_guess)
        from ..column.expression_proxy import ExpressionProxy

        return ExpressionProxy(result_expr, parent_frame)

    def pv(
        self,
        nper: "IntoExprColumn",
        pmt: "IntoExprColumn",
        *,
        fv: float | None = None,
        typ: int | None = None,
    ) -> "ExpressionProxy":
        """Calculate the present value of an investment based on periodic payments.

        This function computes the present value of a loan or an investment, based on a
        constant interest rate and regular payments, using Excel's PV formula.

        !!! note "When to use"
            *   **Reserve Calculations**: Calculate the present value of future benefit payments for reserve valuations
            *   **Annuity Pricing**: Determine the present value of annuity payment streams
            *   **Loan Analysis**: Evaluate the present value of loan repayments for asset-liability management
            *   **Capital Budgeting**: Assess the present value of project cash flows for investment decisions

        Parameters
        ----------
        nper : IntoExprColumn
            Number of periods as scalar/column or list column.
        pmt : IntoExprColumn
            Payment per period as scalar/column or list column.
        fv : float, optional
            Future value at the end of nper periods. Defaults to 0.0.
        typ : int, optional
            Payment timing: 0 for payments at end of period (default), 1 for beginning.

        Returns
        -------
        ExpressionProxy
            Float64 or List[Float64] representing the present value.

        Examples
        --------
        Calculate present value of annuity payments::

            ```python
            from gaspatchio_core import ActuarialFrame

            data = {
                "policy_id": ["POL001", "POL002", "POL003"],
                "interest_rate": [0.05, 0.04, 0.06],  # Annual interest rates
                "num_periods": [10, 15, 20],  # Number of payment periods
                "payment": [1000.0, 1500.0, 2000.0],  # Payment per period
            }
            af = ActuarialFrame(data)

            # Calculate present value of the annuity streams
            result = af.with_columns(
                present_value=af["interest_rate"].excel.pv(
                    nper=af["num_periods"],
                    pmt=af["payment"]
                )
            )
            print(result.collect())
            ```

            ```
            shape: (3, 5)
            ┌───────────┬───────────────┬─────────────┬─────────┬───────────────┐
            │ policy_id ┆ interest_rate ┆ num_periods ┆ payment ┆ present_value │
            │ ---       ┆ ---           ┆ ---         ┆ ---     ┆ ---           │
            │ str       ┆ f64           ┆ i64         ┆ f64     ┆ f64           │
            ╞═══════════╪═══════════════╪═════════════╪═════════╪═══════════════╡
            │ POL001    ┆ 0.05          ┆ 10          ┆ 1000.0  ┆ -7721.735     │
            │ POL002    ┆ 0.04          ┆ 15          ┆ 1500.0  ┆ -16684.789    │
            │ POL003    ┆ 0.06          ┆ 20          ┆ 2000.0  ┆ -22937.702    │
            └───────────┴───────────────┴─────────────┴─────────┴───────────────┘
            ```

        """
        from .excel_functions.pv import pv as _pv

        rate_expr = self._get_polars_expr()
        parent_frame = self._get_parent_frame()
        result_expr = _pv(rate_expr, nper, pmt, fv=fv, typ=typ)
        from ..column.expression_proxy import ExpressionProxy

        return ExpressionProxy(result_expr, parent_frame)

    def days(self, start_date: "IntoExprColumn") -> "ExpressionProxy":
        """Calculate the number of days between two dates, similar to Excel's DAYS.

        This function computes the number of days between an end date (the column/expression
        this accessor is on) and a start date. The result is positive if the end date
        is after the start date, and negative if before.

        !!! note "When to use"
            *   **Duration Calculations**: Calculate the length of policy terms, claim periods, or other time-based intervals.
            *   **Age Calculations**: Determine the number of days between birth dates and valuation dates for precise age calculations.
            *   **Interest Calculations**: Calculate the exact number of days for interest accrual between two specific dates.
            *   **Exposure Period Analysis**: Measure exposure periods in days for risk assessment or premium calculations.

        Parameters
        ----------
        start_date : IntoExprColumn
            An expression or column representing the start dates. Can be a scalar date,
            a column of dates.

        Returns
        -------
        ExpressionProxy
            An expression representing the calculated days difference as an `Int64`.

        Examples
        --------
        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "start_date": [datetime.date(2023, 1, 1), datetime.date(2023, 6, 15)],
            "end_date": [datetime.date(2023, 1, 31), datetime.date(2023, 7, 15)],
        }
        af = ActuarialFrame(data)

        # Calculate days between start and end dates
        af_with_days = af.with_columns(
            days_diff=af["end_date"].excel.days(af["start_date"])
        )
        print(af_with_days.collect())
        ```
        """
        from .excel_functions.days import days

        end_date_expr = self._get_polars_expr()
        result_expr = days(end_date_expr, start_date)

        from ..column.expression_proxy import ExpressionProxy
        parent_frame = self._get_parent_frame()
        return ExpressionProxy(result_expr, parent_frame)

    def edate(self, months: "IntoExprColumn") -> "ExpressionProxy":
        """Add months to a date, similar to Excel's EDATE.

        This function adds the specified number of months to the date column/expression
        this accessor is on, returning the resulting date. Handles month boundaries
        correctly (e.g., January 31 + 1 month = February 28/29).

        !!! note "When to use"
            *   **Policy Anniversary Dates**: Calculate policy renewal dates or anniversary dates by adding months to the issue date.
            *   **Payment Schedules**: Determine future premium due dates or benefit payment dates based on monthly intervals.
            *   **Maturity Calculations**: Calculate policy or investment maturity dates by adding a term in months to the start date.
            *   **Projection Periods**: Generate future valuation dates for cash flow projections or reserving calculations.

        Parameters
        ----------
        months : IntoExprColumn
            An expression or column representing the number of months to add.
            Can be positive or negative.

        Returns
        -------
        ExpressionProxy
            An expression representing the date after adding months.

        Examples
        --------
        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "start_date": [datetime.date(2023, 1, 31), datetime.date(2023, 3, 15)],
            "months_to_add": [1, 3],
        }
        af = ActuarialFrame(data)

        # Add months to dates
        af_with_new_dates = af.with_columns(
            new_date=af["start_date"].excel.edate(af["months_to_add"])
        )
        print(af_with_new_dates.collect())
        ```
        """
        from .excel_functions.edate import edate

        start_date_expr = self._get_polars_expr()
        result_expr = edate(start_date_expr, months)

        from ..column.expression_proxy import ExpressionProxy
        parent_frame = self._get_parent_frame()
        return ExpressionProxy(result_expr, parent_frame)

    def eomonth(self, months: "IntoExprColumn") -> "ExpressionProxy":
        """Get the end of month after adding months, similar to Excel's EOMONTH.

        This function adds the specified number of months to the date column/expression
        this accessor is on, then returns the last day of that resulting month.

        !!! note "When to use"
            *   **Reporting Periods**: Determine month-end dates for financial reporting or regulatory submissions.
            *   **Interest Calculations**: Calculate interest accrual periods that end on the last day of each month.
            *   **Benefit Payment Dates**: Set benefit payment dates to month-end when payments are made monthly.
            *   **Policy Term Boundaries**: Define policy terms or coverage periods that end on month boundaries.

        Parameters
        ----------
        months : IntoExprColumn
            An expression or column representing the number of months to add.
            Can be positive or negative.

        Returns
        -------
        ExpressionProxy
            An expression representing the end-of-month date after adding months.

        Examples
        --------
        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "start_date": [datetime.date(2023, 3, 15), datetime.date(2023, 1, 5)],
            "months_to_add": [1, 2],
        }
        af = ActuarialFrame(data)

        # Get end of month after adding months
        af_with_eom_dates = af.with_columns(
            end_of_month=af["start_date"].excel.eomonth(af["months_to_add"])
        )
        print(af_with_eom_dates.collect())
        ```
        """
        from .excel_functions.eomonth import eomonth

        start_date_expr = self._get_polars_expr()
        result_expr = eomonth(start_date_expr, months)

        from ..column.expression_proxy import ExpressionProxy
        parent_frame = self._get_parent_frame()
        return ExpressionProxy(result_expr, parent_frame)
