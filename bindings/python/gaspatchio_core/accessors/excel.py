"""Accessors for Excel-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING, Dict, Literal, Union

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

# Map between Excel's numeric basis and string representation
BASIS_MAP: Dict[Union[int, str], str] = {
    0: "us_nasd_30_360",
    "0": "us_nasd_30_360",
    "us_nasd_30_360": "us_nasd_30_360",
    "30/360": "us_nasd_30_360",
    "30/360 US": "us_nasd_30_360",
    1: "act/act",
    "1": "act/act",
    "act/act": "act/act",
    "actual/actual": "act/act",
    2: "actual/360",
    "2": "actual/360",
    "actual/360": "actual/360",
    "act/360": "actual/360",
    3: "actual/365",
    "3": "actual/365",
    "actual/365": "actual/365",
    "act/365": "actual/365",
    4: "european_30_360",
    "4": "european_30_360",
    "european_30_360": "european_30_360",
    "30E/360": "european_30_360",
    "30/360 EU": "european_30_360",
}


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


def _normalize_basis(basis: BasisType) -> str:
    """Normalize basis to a standard string representation.
    
    Internal helper function that converts various basis representations
    (integer or string) to a standardized string format.
    """
    if basis in BASIS_MAP:
        return BASIS_MAP[basis]
    raise ValueError(
        f"Invalid basis '{basis}'. Valid values are: {', '.join(sorted(set(BASIS_MAP.values())))}"
    )


def _adjust_date_us_nasd_30_360(
    year: int, month: int, day: int, is_start: bool, other_day: int = None
) -> tuple[int, int, int]:
    """Apply US NASD 30/360 date adjustments to a date's components.
    
    Internal helper function that implements the US NASD 30/360 day count
    convention date adjustment rules.

    Args:
        year: Year component
        month: Month component (1-12)
        day: Day component (1-31)
        is_start: True if this is the start date, False if end date
        other_day: The other date's day value (start day if this is end date, or vice versa)
                  Used for certain adjustment rules

    Returns:
        Tuple of (adjusted_year, adjusted_month, adjusted_day)
    """
    # Make a copy of the inputs to avoid modifying the originals
    y, m, d = year, month, day

    # Check if date is the last day of February
    is_leap_year = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    days_in_month = (
        31
        if m in (1, 3, 5, 7, 8, 10, 12)
        else (30 if m != 2 else (29 if is_leap_year else 28))
    )
    is_last_day_of_month = d == days_in_month
    is_feb_last_day = m == 2 and is_last_day_of_month

    # End-of-February rule: If date is the last day of February, set day to 30
    if is_feb_last_day:
        d = 30

    # Start date end-of-month rule: If start date is the last day of any month, set day to 30
    if is_start and is_last_day_of_month:
        d = 30

    # End date end-of-month rules depend on start date's day
    if not is_start and is_last_day_of_month:
        # If we have the start day value and it's adjusted value is < 30,
        # Excel's behavior is complex. For consistency with the formula,
        # we just leave d = day (which is already the last day of the month)
        if other_day is not None and other_day < 30:
            # Excel might conceptually treat this as the 1st of next month,
            # but the formula handles it correctly without adjustment
            pass
        elif d == 31:  # Last day of a 31-day month
            d = 30

    # 31-day adjustment: After above rules, if day is still 31, set it to 30
    if d == 31:
        d = 30

    return y, m, d


# Helper function for the core yearfrac calculation logic
def _compute_yearfrac_value_exprs(
    start_date_e: pl.Expr, end_date_e: pl.Expr, basis_str: str
) -> pl.Expr:
    """Computes year fraction between two date expressions based on basis.
    
    Internal helper function that handles the core yearfrac calculation logic
    for different day count bases using Polars expressions.
    """
    # Ensure inputs are cast to Date, allowing Polars to attempt conversion
    # strict=False allows for attempted conversion of various date-like inputs.
    s_dt = start_date_e.cast(pl.Date, strict=False)
    e_dt = end_date_e.cast(pl.Date, strict=False)

    # Normalize the basis to a standard string
    basis_str = _normalize_basis(basis_str)

    if basis_str == "act/act":
        # Excel's Actual/Actual typically involves more complex leap year logic.
        # This is a simplified version using 365.25 days per year.
        days_diff = (e_dt - s_dt).dt.total_days()
        return days_diff / 365.25  # Simplified Act/Act

    elif basis_str == "us_nasd_30_360":
        # For US NASD 30/360 (Basis 0), we need to apply special date adjustments
        # Extract year, month, day components
        s_year = s_dt.dt.year()
        s_month = s_dt.dt.month()
        s_day = s_dt.dt.day()

        e_year = e_dt.dt.year()
        e_month = e_dt.dt.month()
        e_day = e_dt.dt.day()

        # Define a struct-based function to adjust dates according to NASD rules
        # We'll use map_elements with return_dtype to process both dates

        date_struct = pl.struct(
            [
                s_year.alias("s_year"),
                s_month.alias("s_month"),
                s_day.alias("s_day"),
                e_year.alias("e_year"),
                e_month.alias("e_month"),
                e_day.alias("e_day"),
            ]
        )

        return date_struct.map_elements(
            lambda x: _apply_us_nasd_30_360(
                x["s_year"],
                x["s_month"],
                x["s_day"],
                x["e_year"],
                x["e_month"],
                x["e_day"],
            ),
            return_dtype=pl.Float64,
        )

    # elif basis_str == "actual/360": # Basis 2
    #     days_diff = (e_dt - s_dt).dt.total_days()
    #     return days_diff / 360.0
    # elif basis_str == "actual/365": # Basis 3
    #     days_diff = (e_dt - s_dt).dt.total_days()
    #     return days_diff / 365.0
    # TODO: Implement other bases like "30E/360"
    else:
        raise NotImplementedError(
            f"Day count basis '{basis_str}' not yet implemented. Only 'act/act' (simplified) and 'us_nasd_30_360' are supported."
        )


def _apply_us_nasd_30_360(s_year, s_month, s_day, e_year, e_month, e_day):
    """
    Apply US NASD 30/360 calculation after adjusting the dates.

    This implements the formula:
    YEARFRAC = ((D2' + 30 × M2' + 360 × Y2') - (D1' + 30 × M1' + 360 × Y1')) / 360

    Where the primed values are the adjusted day, month, and year values.
    """
    # Skip calculation for None values
    if any(x is None for x in [s_year, s_month, s_day, e_year, e_month, e_day]):
        return None

    # Apply US NASD 30/360 adjustments to start date
    s_year, s_month, s_day = _adjust_date_us_nasd_30_360(s_year, s_month, s_day, True)

    # Apply US NASD 30/360 adjustments to end date (passing the adjusted start day)
    e_year, e_month, e_day = _adjust_date_us_nasd_30_360(
        e_year, e_month, e_day, False, s_day
    )

    # Calculate the 30/360 date difference as per the formula
    start_value = s_day + 30 * s_month + 360 * s_year
    end_value = e_day + 30 * e_month + 360 * e_year

    # Return the year fraction
    return (end_value - start_value) / 360.0


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
        and an end date. It uses a specified day count basis. The function can
        operate on individual dates (scalars or columns) and also handles scenarios
        where one of the date inputs is a list of dates within a column.

        !!! note "When to use"
            *   **Premium Proration**: Calculate the portion of an annual premium that corresponds to a partial policy term, for example, if a policy starts or ends mid-year.
            *   **Exposure Calculation**: Determine fractional exposure periods for reserving or IBNR (Incurred But Not Reported) calculations, especially when dealing with policies that are not in force for a full year.
            *   **Investment Analysis**: Compute fractional year periods for accrued interest calculations or for annualizing returns on investments held for parts of a year.
            *   **Performance Metrics**: Analyze time-based metrics such as time-to-claim or duration of an event, expressed as a fraction of a year.

        Parameters
        ----------
        end_date_expr : IntoExprColumn
            An expression or column representing the end dates. Can be a scalar date,
            a column of dates, or a column of `List[Date]` if the start date is a
            scalar/column of dates (and vice-versa).
        basis : int or str, optional
            The day count basis to use. Can be an integer (0-4) or a string name.
            Defaults to "act/act" (which is basis 1).

            Supported bases:
            - `0` or `'us_nasd_30_360'` (30/360 US NASD) - US (NASD) 30/360 convention
            - `1` or `'act/act'` (Actual/Actual) - Simplified version (uses 365.25 days)
            - `2` or `'actual_360'` (Actual/360) - Not Implemented
            - `3` or `'actual_365'` (Actual/365 fixed) - Not Implemented
            - `4` or `'european_30_360'` (30/360 European) - Not Implemented

        Returns
        -------
        ExpressionProxy
            An expression representing the calculated year fraction as a `Float64`.
            If one of the inputs was a `List[Date]`, the output will be a `List[Float64]`.

        Raises
        ------
        NotImplementedError
            If a `basis` other than the currently supported basis values is specified,
            or if both start and end date expressions resolve to `List[Date]` columns
            (which requires a more complex UDF or explode/aggregate pattern).
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

            # Calculate year fraction using 'act/act' (simplified)
            af_with_term = af["start_date"].excel.yearfrac(af["end_date"], basis="act/act")
            print(af_with_term.collect())
            ```

            ```
            shape: (3, 4)
            ┌───────────┬────────────┬────────────┬────────────┐
            │ policy_id ┆ start_date ┆ end_date   ┆ term_years │
            │ ---       ┆ ---        ┆ ---        ┆ ---        │
            │ str       ┆ date       ┆ date       ┆ f64        │
            ╞═══════════╪════════════╪════════════╪════════════╡
            │ P001      ┆ 2020-01-01 ┆ 2021-01-01 ┆ 1.002053   │
            │ P002      ┆ 2021-06-15 ┆ 2022-06-15 ┆ 0.999316   │
            │ P003      ┆ 2022-03-01 ┆ 2022-09-01 ┆ 0.503765   │
            └───────────┴────────────┴────────────┴────────────┘
            ```

        Fractional Exposure for Multiple Claim Events from a Single Policy Start (List Operation)::

            Scenario: A policy has a single start date, but multiple claim event dates.
            Calculate the time from policy start to each claim event as a year fraction.

            ```python
            import datetime
            import polars as pl
            from gaspatchio_core import ActuarialFrame

            data = {
                "policy_id": ["PolicyA", "PolicyB"],
                "policy_start_date": [datetime.date(2020, 1, 1), datetime.date(2021, 1, 1)],
                "claim_event_dates": [
                    [datetime.date(2020, 7, 1), datetime.date(2021, 3, 15)], # Events for PolicyA
                    [datetime.date(2021, 2, 1)],                            # Event for PolicyB
                ],
            }
            # Ensure claim_event_dates is typed as List[Date]
            af = ActuarialFrame(data, schema_overrides={"claim_event_dates": pl.List(pl.Date)})

            af_with_frac = af.with_columns(
                time_to_event_years = af["policy_start_date"].excel.yearfrac(af["claim_event_dates"])
            )
            print(af_with_frac.collect())
            ```

            ```
            shape: (2, 4)
            ┌───────────┬───────────────────┬───────────────────────────────────────────┬─────────────────────────────┐
            │ policy_id ┆ policy_start_date ┆ claim_event_dates                         ┆ time_to_event_years         │
            │ ---       ┆ ---               ┆ ---                                       ┆ ---                         │
            │ str       ┆ date              ┆ list[date]                                ┆ list[f64]                   │
            ╞═══════════╪═══════════════════╪═══════════════════════════════════════════╪═════════════════════════════╡
            │ PolicyA   ┆ 2020-01-01        ┆ [2020-07-01, 2021-03-15]                  ┆ [0.50016, 1.200046]         │
            │ PolicyB   ┆ 2021-01-01        ┆ [2021-02-01]                              ┆ [0.084873]                  │
            └───────────┴───────────────────┴───────────────────────────────────────────┴─────────────────────────────┘
            ```
        """
        parent_frame = self._get_parent_frame()
        start_expr_polars = self._get_polars_expr()
        end_expr_polars = parent_frame._convert_to_expr(end_date_expr)

        # Heuristic to check if inputs directly refer to list columns in the schema.
        # Use collect_schema() to avoid PerformanceWarning
        schema = parent_frame._df.collect_schema()

        start_is_list_col = False
        if hasattr(self._proxy, "name") and self._proxy.name in schema:
            col_dtype = schema[self._proxy.name]
            if isinstance(col_dtype, pl.List) and isinstance(col_dtype.inner, pl.Date):
                start_is_list_col = True

        end_is_list_col = False
        if end_expr_polars.meta.is_column():  # Check if it's a simple column expression
            end_col_name = end_expr_polars.meta.output_name()
            if end_col_name in schema:
                col_dtype = schema[end_col_name]
                if isinstance(col_dtype, pl.List) and isinstance(
                    col_dtype.inner, pl.Date
                ):
                    end_is_list_col = True

        # Normalize basis to a standard string representation
        try:
            normalized_basis = _normalize_basis(basis)
        except ValueError as e:
            raise ValueError(f"Invalid basis: {e}")

        final_year_frac_expr: pl.Expr

        if start_is_list_col and not end_is_list_col:
            # Start is List[Date], End is Date-like (scalar or column of dates)
            # For list columns with scalar values, we use map_elements which is more flexible
            if isinstance(end_date_expr, (datetime.date, datetime.datetime)):
                # For Python date/datetime objects, we can use a direct approach
                struct_expr = pl.struct([start_expr_polars.alias("start_list")])
                if normalized_basis == "us_nasd_30_360":
                    # Special handling for 30/360 basis
                    final_year_frac_expr = struct_expr.map_elements(
                        lambda x: [
                            None
                            if date is None
                            else _compute_30_360_yearfrac(
                                date.year,
                                date.month,
                                date.day,
                                end_date_expr.year,
                                end_date_expr.month,
                                end_date_expr.day,
                            )
                            for date in x["start_list"]
                        ],
                        return_dtype=pl.List(pl.Float64),
                    )
                else:
                    # Use the simple approach for act/act
                    final_year_frac_expr = struct_expr.map_elements(
                        lambda x: [
                            None
                            if date is None
                            else (end_date_expr - date).days / 365.25
                            for date in x["start_list"]
                        ],
                        return_dtype=pl.List(pl.Float64),
                    )
            else:
                # For column references or expressions, we need to use struct with both values
                struct_expr = pl.struct(
                    [
                        start_expr_polars.alias("start_list"),
                        end_expr_polars.alias("end_date"),
                    ]
                )
                if normalized_basis == "us_nasd_30_360":
                    # Special handling for 30/360 basis
                    final_year_frac_expr = struct_expr.map_elements(
                        lambda x: [
                            None
                            if date is None or x["end_date"] is None
                            else _compute_30_360_yearfrac(
                                date.year,
                                date.month,
                                date.day,
                                x["end_date"].year,
                                x["end_date"].month,
                                x["end_date"].day,
                            )
                            for date in x["start_list"]
                        ],
                        return_dtype=pl.List(pl.Float64),
                    )
                else:
                    # Use the simple approach for act/act
                    final_year_frac_expr = struct_expr.map_elements(
                        lambda x: [
                            None
                            if date is None or x["end_date"] is None
                            else (x["end_date"] - date).days / 365.25
                            for date in x["start_list"]
                        ],
                        return_dtype=pl.List(pl.Float64),
                    )
        elif not start_is_list_col and end_is_list_col:
            # Start is Date-like, End is List[Date]
            if isinstance(end_date_expr, (datetime.date, datetime.datetime)):
                # For Python date/datetime objects, we can use a direct approach
                struct_expr = pl.struct([end_expr_polars.alias("end_list")])

                # We need to get the date from the polars expression
                # We can't access .year/.month/.day on a Polars expression directly
                # Instead, we'll use map_elements where we have direct access to the actual dates

                if normalized_basis == "us_nasd_30_360":
                    # Special handling for 30/360 basis
                    # If start_expr_polars is a literal date, extract it
                    if hasattr(self._proxy, "_parent") and hasattr(self._proxy, "name"):
                        # Get the value from the actual column
                        start_col_name = self._proxy.name
                        start_date_val = parent_frame.collect()[start_col_name][0]

                        final_year_frac_expr = struct_expr.map_elements(
                            lambda x: [
                                None
                                if date is None
                                else _compute_30_360_yearfrac(
                                    start_date_val.year,
                                    start_date_val.month,
                                    start_date_val.day,
                                    date.year,
                                    date.month,
                                    date.day,
                                )
                                for date in x["end_list"]
                            ],
                            return_dtype=pl.List(pl.Float64),
                        )
                    else:
                        # Generic fallback
                        final_year_frac_expr = struct_expr.map_elements(
                            lambda x: [
                                None
                                if date is None
                                else 0.0  # This would need to be fixed
                                for date in x["end_list"]
                            ],
                            return_dtype=pl.List(pl.Float64),
                        )
                else:
                    # Use the simple approach for act/act with real dates
                    if hasattr(self._proxy, "_parent") and hasattr(self._proxy, "name"):
                        # Get the value from the actual column
                        start_col_name = self._proxy.name
                        start_date_val = parent_frame.collect()[start_col_name][0]

                        final_year_frac_expr = struct_expr.map_elements(
                            lambda x: [
                                None
                                if date is None
                                else (date - start_date_val).days / 365.25
                                for date in x["end_list"]
                            ],
                            return_dtype=pl.List(pl.Float64),
                        )
                    else:
                        # Generic fallback
                        final_year_frac_expr = struct_expr.map_elements(
                            lambda x: [
                                None
                                if date is None
                                else 0.0  # This would need to be fixed
                                for date in x["end_list"]
                            ],
                            return_dtype=pl.List(pl.Float64),
                        )
            else:
                # For column references or expressions, we need to use struct with both values
                struct_expr = pl.struct(
                    [
                        start_expr_polars.alias("start_date"),
                        end_expr_polars.alias("end_list"),
                    ]
                )
                if normalized_basis == "us_nasd_30_360":
                    # Special handling for 30/360 basis
                    final_year_frac_expr = struct_expr.map_elements(
                        lambda x: [
                            None
                            if date is None or x["start_date"] is None
                            else _compute_30_360_yearfrac(
                                x["start_date"].year,
                                x["start_date"].month,
                                x["start_date"].day,
                                date.year,
                                date.month,
                                date.day,
                            )
                            for date in x["end_list"]
                        ],
                        return_dtype=pl.List(pl.Float64),
                    )
                else:
                    # Use the simple approach for act/act
                    final_year_frac_expr = struct_expr.map_elements(
                        lambda x: [
                            None
                            if date is None or x["start_date"] is None
                            else (date - x["start_date"]).days / 365.25
                            for date in x["end_list"]
                        ],
                        return_dtype=pl.List(pl.Float64),
                    )
        elif start_is_list_col and end_is_list_col:
            # Both are List[Date] columns. This requires element-wise zipping of items within lists.
            raise NotImplementedError(
                "Calculating yearfrac where both start and end dates are list columns "
                "(requiring pairing elements from each list like a zip) is not directly supported "
                "by this accessor. Consider using `pl.struct().map_elements()` for such custom list operations."
            )
        else:
            # Default case: treat as scalar/simple column operations.
            # This handles Date vs Date. If an unhandled List vs List case (e.g., from complex expressions
            # not caught by the schema check) slips through, Polars will likely error during the
            # _compute_yearfrac_value_exprs call due to mismatched types/shapes.
            final_year_frac_expr = _compute_yearfrac_value_exprs(
                start_expr_polars, end_expr_polars, normalized_basis
            )

        from ..column.expression_proxy import ExpressionProxy

        # Do not apply a final cast here, as we need to preserve the List type for list operations
        # and only cast the inner type to Float64 if necessary.
        # We'll let Polars handle the casting based on the result structure.
        return ExpressionProxy(final_year_frac_expr, parent_frame)


def _compute_30_360_yearfrac(s_year, s_month, s_day, e_year, e_month, e_day):
    """
    Compute the 30/360 US NASD year fraction between two dates.

    This is a helper function that applies the US NASD 30/360 rules to date components
    and computes the resulting year fraction.

    Args:
        s_year: Start date year
        s_month: Start date month (1-12)
        s_day: Start date day (1-31)
        e_year: End date year
        e_month: End date month (1-12)
        e_day: End date day (1-31)

    Returns:
        The year fraction as a float, or None if any inputs are None
    """
    # Skip calculation for None values
    if any(x is None for x in [s_year, s_month, s_day, e_year, e_month, e_day]):
        return None

    # Apply US NASD 30/360 adjustments to start date
    s_year, s_month, s_day = _adjust_date_us_nasd_30_360(s_year, s_month, s_day, True)

    # Apply US NASD 30/360 adjustments to end date (passing the adjusted start day)
    e_year, e_month, e_day = _adjust_date_us_nasd_30_360(
        e_year, e_month, e_day, False, s_day
    )

    # Calculate the 30/360 date difference as per the formula
    start_value = s_day + 30 * s_month + 360 * s_year
    end_value = e_day + 30 * e_month + 360 * e_year

    # Return the year fraction
    return (end_value - start_value) / 360.0
