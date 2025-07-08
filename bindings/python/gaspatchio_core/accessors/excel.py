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
    int,
    str,
    Literal[0, 1, 2, 3, 4],
    Literal["us_nasd_30_360", "act/act", "actual/360", "actual/365", "european_30_360"],
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
        self._proxy: "ColumnProxy | ExpressionProxy" = proxy

    def _get_polars_expr(self) -> pl.Expr:
        """Helper to get the underlying Polars expression from the proxy.
        
        Internal helper method that extracts the Polars expression from
        the column or expression proxy for further processing.
        """
        if hasattr(self._proxy, "_expr") and isinstance(self._proxy._expr, pl.Expr):
            return self._proxy._expr
        elif hasattr(self._proxy, "name") and isinstance(self._proxy.name, str):
            return pl.col(self._proxy.name)
        else:
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
                actual_date=af["excel_date_serial"].excel.from_excel_serial(epoch="1900")
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
        """
        parent_frame = self._get_parent_frame()
        start_expr = self._get_polars_expr()
        end_expr = parent_frame._convert_to_expr(end_date_expr)

        # Check if we're dealing with list columns
        schema = parent_frame._df.collect_schema()
        
        start_is_list = False
        if hasattr(self._proxy, "name") and self._proxy.name in schema:
            col_dtype = schema[self._proxy.name]
            if isinstance(col_dtype, pl.List) and isinstance(col_dtype.inner, pl.Date):
                start_is_list = True

        end_is_list = False
        if end_expr.meta.is_column():
            end_col_name = end_expr.meta.output_name()
            if end_col_name in schema:
                col_dtype = schema[end_col_name]
                if isinstance(col_dtype, pl.List) and isinstance(col_dtype.inner, pl.Date):
                    end_is_list = True

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
                "30E/360": 4,
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

        # Handle list operations - for now, not supported
        if start_is_list or end_is_list:
            raise NotImplementedError(
                "yearfrac with list columns is not yet supported. "
                "As a workaround, consider using explode() to flatten the list, "
                "calculate yearfrac, then group_by().agg() to re-create the list structure."
            )

        # Import the year_frac function from the functions module
        from ..functions.excel import year_frac

        # Ensure both expressions are cast to Date type for the Rust function
        start_date_expr = start_expr.cast(pl.Date, strict=False)
        end_date_expr = end_expr.cast(pl.Date, strict=False)

        # Call the Rust implementation via the plugin
        result_expr = year_frac(start_date_expr, end_date_expr, basis=basis_int)

        from ..column.expression_proxy import ExpressionProxy

        return ExpressionProxy(result_expr, parent_frame)


