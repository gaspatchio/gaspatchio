"""Accessors for date-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING, Literal, Union

import polars as pl

# Import registry decorator
from ..frame.registry import register_accessor
# Import validation error handling
from ..errors.validation import capture_validation_context, raise_validation_error

# Use the new base location
from .base import BaseColumnAccessor, BaseFrameAccessor

# Use TYPE_CHECKING for core components to avoid circular imports
if TYPE_CHECKING:
    # Update imports to new locations
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame
    from ..typing import IntoExprColumn

# ADDED: More imports for moved logic
from typing import Literal, Union


# Add registration decorator
@register_accessor("date", kind="frame")
class DateFrameAccessor(BaseFrameAccessor):
    """Provides date-related methods applicable to the entire ActuarialFrame.

    Accessed via `.date` on an ActuarialFrame instance,
    e.g., `af.date`.

    This accessor allows for complex date manipulations at the frame level,
    such as generating timelines for projections or adding durations to multiple
    date columns simultaneously. It integrates with Polars expressions for
    optimized performance.
    """

    def __init__(self, frame: "ActuarialFrame"):
        """Initializes the accessor with the parent ActuarialFrame.

        This is typically called internally when accessing `af.date`.
        """
        super().__init__(frame)

    def create_timeline(
        self,
        start_col: "IntoExprColumn",
        end_col: "IntoExprColumn",
        freq: str = "1d",
        new_col_name: str = "timeline_date",
        closed: str = "left",
    ) -> "ActuarialFrame":  # Return type is ActuarialFrame
        """Creates timeline columns based on start and end dates.

        Generates a list of dates for each row based on its start and end date,
        using the specified frequency. The result is exploded to create
        a longer DataFrame where each original row is repeated for each date
        in its timeline.

        !!! note "When to use"
            *   **Period-to-Event Transformation:** This method is useful when you need to transform row-per-period data
                (where each row has a start and end date) into row-per-event data
                (where each row represents a specific point in time, like a month-end).
                For example, to calculate monthly exposures from policy start/end dates.

        Args:
            start_col: Column or expression for the start date of the interval.
            end_col: Column or expression for the end date of the interval.
            freq: The frequency of the timeline (e.g., "1M", "1Y", "1d").
                  Passed to `pl.date_ranges`.
            new_col_name: Name for the new column containing the generated timeline dates.
                          Defaults to "timeline_date".
            closed: Which side of the interval is closed ("left", "right", "both", "none").
                    Passed to `pl.date_ranges`.

        Returns:
            A new ActuarialFrame instance with the original data expanded
            by the generated timeline dates.

        Raises:
            pl.ColumnNotFoundError: If start_col or end_col cannot be resolved.
            pl.ComputeError: If date range generation fails (e.g., invalid freq,
                             incompatible date types).

        Examples:
            ```python
            import datetime
            from gaspatchio_core import ActuarialFrame
            data = {
                "policy_id": [1, 2],
                "start_date": [datetime.date(2023, 1, 1), datetime.date(2023, 2, 15)],
                "end_date": [datetime.date(2023, 3, 1), datetime.date(2023, 4, 15)],
            }
            af = ActuarialFrame(data)
            # Create a monthly timeline
            timeline_af = af.date.create_timeline("start_date", "end_date", freq="1mo", new_col_name="month_end")
            print(timeline_af.collect())
            ```
            
            ```text
            shape: (5, 4)
            ┌───────────┬────────────┬────────────┬────────────┐
            │ policy_id ┆ start_date ┆ end_date   ┆ month_end  │
            │ ---       ┆ ---        ┆ ---        ┆ ---        │
            │ i64       ┆ date       ┆ date       ┆ date       │
            ╞═══════════╪════════════╪════════════╪════════════╡
            │ 1         ┆ 2023-01-01 ┆ 2023-03-01 ┆ 2023-01-01 │
            │ 1         ┆ 2023-01-01 ┆ 2023-03-01 ┆ 2023-02-01 │
            │ 2         ┆ 2023-02-15 ┆ 2023-04-15 ┆ 2023-02-15 │
            │ 2         ┆ 2023-02-15 ┆ 2023-04-15 ┆ 2023-03-15 │
            │ 2         ┆ 2023-02-15 ┆ 2023-04-15 ┆ 2023-04-15 │
            └───────────┴────────────┴────────────┴────────────┘
            ```
        """
        # --- Input Validation and Expression Conversion --- #
        try:
            start_expr = self._frame._convert_to_expr(start_col)
            end_expr = self._frame._convert_to_expr(end_col)
        except Exception as e:
            # Re-raise potential errors from _convert_to_expr (e.g., invalid input)
            raise ValueError(f"Invalid start_col or end_col provided: {e}") from e

        # --- Core Logic: Generate and Explode Date Ranges --- #
        # 1. Create the date ranges as a list column
        date_ranges_expr = pl.date_ranges(
            start=start_expr,
            end=end_expr,
            interval=freq,
            closed=closed,
            eager=False,  # Important for LazyFrame
        ).alias(new_col_name)

        # 2. Add the list column to the DataFrame
        # Use a temporary name to avoid conflicts if new_col_name exists
        temp_col_name = f"__{new_col_name}_ranges__"
        df_with_ranges = self._frame._df.with_columns(
            date_ranges_expr.alias(temp_col_name)
        )

        # 3. Explode the list column
        # Keep other columns, replace the list col with the exploded dates
        df_exploded = df_with_ranges.explode(temp_col_name).rename(
            {temp_col_name: new_col_name}
        )

        # --- Return New ActuarialFrame --- #
        # Import from new location
        from ..frame.base import ActuarialFrame

        # Create a new ActuarialFrame instance wrapping the modified LazyFrame
        return ActuarialFrame(df_exploded)

    def add_duration(
        self,
        date_col: "IntoExprColumn",
        duration_str: str,
        new_col_name: str | None = None,
    ) -> "ActuarialFrame":
        """Adds a duration string (e.g., '1Y', '3M', '-7d') to a date column.

        This function leverages Polars' powerful duration arithmetic to efficiently
        modify dates within the ActuarialFrame. It can create a new column with
        the resulting dates or modify an existing column if `new_col_name` is not
        provided and `date_col` is a string name.

        !!! note "When to use"
            *   **Date Arithmetic:** Use this method to shift dates by a fixed duration, such as calculating
                a policy anniversary, determining a future maturity date, or finding a
                past event date. It's particularly useful for batch operations on an
                entire column of dates.

        Args:
            date_col: The column containing the dates to add the duration to.
            duration_str: The duration string in Polars format (e.g., "1Y6M", "-3d12h").
            new_col_name: The name for the new column containing the resulting dates.
                          If None, modifies the original column (if it's a string name).

        Returns:
            A new ActuarialFrame with the added/modified column.

        Raises:
            ValueError: If date_col is not a valid column/expression or if modification
                      is attempted without providing a string name for date_col.
            pl.ComputeError: If the duration addition fails (e.g., invalid duration string,
                             incompatible date types).

        Examples:
            ```python
            import datetime
            from gaspatchio_core import ActuarialFrame
            data = {
                "event_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
                "term_months": [6, 12]
            }
            af = ActuarialFrame(data)
            # Add 1 year to event_date
            af_plus_1y = af.date.add_duration("event_date", "1Y", new_col_name="event_plus_1y")
            print(af_plus_1y.collect())
            ```
            
            ```text
            shape: (2, 3)
            ┌────────────┬─────────────┬─────────────────┐
            │ event_date ┆ term_months ┆ event_plus_1y   │
            │ ---        ┆ ---         ┆ ---             │
            │ date       ┆ i64         ┆ date            │
            ╞════════════╪═════════════╪═════════════════╡
            │ 2023-01-15 ┆ 6           ┆ 2024-01-15      │
            │ 2023-06-30 ┆ 12          ┆ 2024-06-30      │
            └────────────┴─────────────┴─────────────────┘
            ```
            
            ```python
            # Example with new column for clarity (using same data as above):
            import datetime
            from gaspatchio_core import ActuarialFrame
            data = {
                "event_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
                "term_months": [6, 12]
            }
            af = ActuarialFrame(data)
            af_minus_3m_new_col = af.date.add_duration("event_date", "-3MO", new_col_name="event_minus_3m")
            print(af_minus_3m_new_col.collect())
            ```
            
            ```text
            shape: (2, 3)
            ┌────────────┬─────────────┬────────────────┐
            │ event_date ┆ term_months ┆ event_minus_3m │
            │ ---        ┆ ---         ┆ ---            │
            │ date       ┆ i64         ┆ date           │
            ╞════════════╪═════════════╪════════════════╡
            │ 2023-01-15 ┆ 6           ┆ 2022-10-15     │
            │ 2023-06-30 ┆ 12          ┆ 2023-03-30     │
            └────────────┴─────────────┴────────────────┘
            ```
        """
        # Import from new location
        from ..frame.base import ActuarialFrame

        try:
            date_expr = self._frame._convert_to_expr(date_col)
        except Exception as e:
            raise ValueError(f"Invalid date_col provided: {e}") from e

        result_expr = date_expr.dt.offset_by(duration_str)

        # Determine the target column name
        target_col_name: str
        if new_col_name:
            target_col_name = new_col_name
        elif isinstance(date_col, str):
            target_col_name = date_col  # Modify in-place (by replacing)
        else:
            raise ValueError(
                "new_col_name must be provided if date_col is not a string"
            )

        df_updated = self._frame._df.with_columns(result_expr.alias(target_col_name))
        return ActuarialFrame(df_updated)

    # MOVED & ADAPTED: create_projection_timeline from dates.py
    @capture_validation_context
    def create_projection_timeline(
        self,
        valuation_date: datetime.date,
        projection_end_type: Literal[
            "maximum_age", "term_years", "term_months", "fixed_date"
        ] = "maximum_age",
        projection_end_value: Union[int, datetime.date] = 100,
        issue_age_column: str = "issue_age",
        projection_frequency: Literal[
            "monthly", "quarterly", "semi-annual", "annual"
        ] = "monthly",
        projection_start_offset_months: int = 0,
        store_start_date: bool = True,
        store_end_date: bool = True,
        output_column: str = "proj_dates",
    ) -> "ActuarialFrame":
        """
        Creates a projection timeline for actuarial calculations within the frame.

        This powerful method generates a series of projection dates for each row
        in the ActuarialFrame based on various actuarial projection methodologies.
        It can handle projections to a maximum age, for a fixed term (in years or
        months), or until a specific fixed date. The resulting timeline is added
        as a new list column to the frame, which can then be exploded for
        detailed cashflow modeling or analysis.

        !!! note "When to use"
            *   **Actuarial Projections:** This is a cornerstone function for actuarial modeling. Use it to:
                - Generate monthly, quarterly, semi-annual, or annual projection dates.
                - Model policies projecting to a maximum age (e.g., whole life insurance).
                - Model policies with fixed terms (e.g., term life insurance, annuities certain).
                - Align projections to specific calendar dates.
                - Prepare data for per-period calculations like reserves, premiums, or benefits.

        Args:
            valuation_date: The valuation date from which to project
            projection_end_type: How to determine the end of the projection:
                - "maximum_age": Project until the policyholder reaches the maximum age
                - "term_years": Project for a fixed number of years
                - "term_months": Project for a fixed number of months
                - "fixed_date": Project until a specific calendar date
            projection_end_value: The value corresponding to the projection_end_type:
                - For "maximum_age": The maximum age (e.g., 100)
                - For "term_years": The number of years to project
                - For "term_months": The number of months to project
                - For "fixed_date": A datetime.date object
            issue_age_column: The column containing the issue age (needed for "maximum_age")
            projection_frequency: The frequency of projection points
            projection_start_offset_months: Months to offset the start date from valuation
            store_start_date: Whether to store the projection start date
            store_end_date: Whether to store the projection end date
            output_column: The name of the column to store the projection dates

        Returns:
            The updated ActuarialFrame instance (`self._frame`).

        Examples:
            ```python no_output_check
            import datetime
            from gaspatchio_core import ActuarialFrame
            data = {
                "policy_id": ["A1", "B2"],
                "issue_age": [30, 45], # Needed for maximum_age projection
                "policy_term_years": [0, 10] # Example, not directly used by max_age
            }
            af = ActuarialFrame(data)
            val_date = datetime.date(2024, 1, 1)
            
            # Example 1: Project to maximum age of 65, monthly
            af_max_age = af.date.create_projection_timeline(
                valuation_date=val_date,
                projection_end_type="maximum_age",
                projection_end_value=32, # Max age of 32 for policy A1 (30+2), 47 for B2 (45+2)
                issue_age_column="issue_age",
                projection_frequency="annual", # Simplified for example
                output_column="projection_dates_max_age"
            )
            
            # Example 2: Project for a fixed term of 2 years, quarterly
            af_fixed_term = af.date.create_projection_timeline(
                valuation_date=val_date,
                projection_end_type="term_years",
                projection_end_value=2,
                projection_frequency="quarterly",
                output_column="projection_dates_fixed_term"
            )
            
            # Example 3: Project to a fixed date, annually
            fixed_end_date = datetime.date(2025, 12, 31)
            af_fixed_date = af.date.create_projection_timeline(
                valuation_date=val_date,
                projection_end_type="fixed_date",
                projection_end_value=fixed_end_date,
                projection_frequency="annual",
                output_column="projection_dates_fixed_date"
            )
            ```
        """
        # Eagerly validate projection_frequency
        valid_frequencies = ["monthly", "quarterly", "semi-annual", "annual"]
        if projection_frequency not in valid_frequencies:
            raise_validation_error(
                f"Invalid projection frequency: {projection_frequency}",
                valid_options=valid_frequencies,
                provided_value=projection_frequency,
                parameter_name="projection_frequency"
            )

        # Convert valuation_date to a Polars expression
        valuation_date_expr = pl.lit(valuation_date)

        # Calculate the projection start date based on offset
        start_date_expr = valuation_date_expr
        if projection_start_offset_months != 0:
            start_date_expr = valuation_date_expr.dt.offset_by(
                f"{projection_start_offset_months}mo"
            )

        # Calculate the projection end date based on the end type
        if projection_end_type == "maximum_age":
            if not isinstance(projection_end_value, int):
                raise TypeError(
                    "projection_end_value must be an integer for 'maximum_age'"
                )
            max_age = projection_end_value
            # Ensure issue_age_column exists or handle error
            if issue_age_column not in self._frame._df.collect_schema().names():
                raise pl.ColumnNotFoundError(
                    f"Required column '{issue_age_column}' not found for 'maximum_age' projection."
                )
            years_to_project_expr = (pl.lit(max_age) - pl.col(issue_age_column)).cast(
                pl.Int64
            )
            end_date_expr = start_date_expr.dt.offset_by(
                pl.concat_str(years_to_project_expr.cast(pl.Utf8), pl.lit("y"))
            )
        elif projection_end_type == "term_years":
            if not isinstance(projection_end_value, int):
                raise TypeError(
                    "projection_end_value must be an integer for 'term_years'"
                )
            end_date_expr = start_date_expr.dt.offset_by(f"{projection_end_value}y")
        elif projection_end_type == "term_months":
            if not isinstance(projection_end_value, int):
                raise TypeError(
                    "projection_end_value must be an integer for 'term_months'"
                )
            end_date_expr = start_date_expr.dt.offset_by(f"{projection_end_value}mo")
        elif projection_end_type == "fixed_date":
            if not isinstance(projection_end_value, datetime.date):
                raise TypeError(
                    "projection_end_value must be a datetime.date for 'fixed_date'"
                )
            end_date_expr = pl.lit(projection_end_value)
        else:
            valid_end_types = ["maximum_age", "term_years", "term_months", "fixed_date"]
            raise_validation_error(
                f"Invalid projection end type: {projection_end_type}",
                valid_options=valid_end_types,
                provided_value=projection_end_type,
                parameter_name="projection_end_type"
            )

        # --- Apply to frame ---
        updates = {}
        if store_start_date:
            updates["projection_start_date"] = start_date_expr
        if store_end_date:
            updates["projection_end_date"] = end_date_expr

        # Apply the updates first to ensure columns exist for timeline generation
        # Use the calculated expressions directly
        df_with_dates = self._frame._df.with_columns(**updates)

        # Map frequency string to Polars interval string
        freq_map = {
            "monthly": "1mo",
            "quarterly": "3mo",
            "semi-annual": "6mo",
            "annual": "1y",
        }
        polars_interval = freq_map[projection_frequency]  # Already validated

        # Use the correct start/end expressions for date_ranges
        # If dates were stored, use those columns. Otherwise, use the expressions.
        start_col_ref = (
            pl.col("projection_start_date") if store_start_date else start_date_expr
        )
        end_col_ref = pl.col("projection_end_date") if store_end_date else end_date_expr

        # Generate the projection dates using pl.date_ranges
        # Use closed='both' to include start and end dates, matching the old logic.
        timeline_expr = pl.date_ranges(
            start=start_col_ref,
            end=end_col_ref,
            interval=polars_interval,
            closed="both",  # Include both start and end if they align with frequency
            eager=False,  # Keep it lazy
        ).alias(output_column)

        # Add the final timeline column
        # Operate on the DataFrame that already has start/end dates added
        self._frame._df = df_with_dates.with_columns(timeline_expr)

        # No temporary columns were created in this approach, so no dropping needed

        # Update frame's internal state (schema, column order might need refresh)
        self._frame._schema = self._frame._df.collect_schema()
        # Be careful modifying column order directly, might be better to recalculate
        # For now, just add new columns if they weren't already tracked
        if (
            store_start_date
            and "projection_start_date" not in self._frame._column_order
        ):
            self._frame._column_order.append("projection_start_date")
        if store_end_date and "projection_end_date" not in self._frame._column_order:
            self._frame._column_order.append("projection_end_date")
        if output_column not in self._frame._column_order:
            self._frame._column_order.append(output_column)

        # Ensure attribute-eligible columns set is refreshed for attribute access
        try:
            self._frame._refresh_attr_columns_set()
        except Exception:
            # Safe to ignore; attribute access will still work via bracket notation
            pass

        return self._frame  # Return the modified frame


# Add registration decorator
@register_accessor("date", kind="column")
class DateColumnAccessor(BaseColumnAccessor):
    """Provides date-related methods for `ColumnProxy` or `ExpressionProxy` objects.

    Accessed via `.date` on a column or expression,
    e.g., `af["my_date_col"].date`.

    This accessor offers convenient methods to manipulate and extract
    information from date/datetime columns within Polars expressions.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy"):
        """Initializes the accessor with the parent proxy object.

        This is typically called internally when accessing `.date` on a column/expression.
        """
        super().__init__(proxy)
        # Refine type hint now that we expect specific proxy types
        self._proxy: "ColumnProxy | ExpressionProxy" = proxy

    def to_period(self, freq: str = "M") -> "ExpressionProxy":
        """Converts a date/datetime column to a period representation (e.g., year-month).

        This is useful for grouping or aggregating data by specific time periods
        like month, quarter, or year. It truncates the date to the beginning
        of the specified period.

        !!! note "When to use"
            *   **Period Aggregation:** Use this to aggregate daily or weekly data into monthly, quarterly, or annual summaries.
            *   **Time Series Features:** For creating features for time series models based on periods.
            *   **Date Alignment:** When you need to align dates to a common period start (e.g., all dates in January
                2023 become 2023-01-01 if `freq="M"`).

        Args:
            freq: The frequency string for period conversion (e.g., "M", "Q", "Y").
                  See Polars documentation for `truncate` for available frequencies.
                  Commonly: "1mo" (month), "1q" (quarter), "1y" (year).
                  Note: "M", "Q", "Y" are often aliases in Polars but prefer explicit
                  "1mo", "1q", "1y" for clarity with `dt.truncate`.

        Returns:
            An `ExpressionProxy` representing the date column truncated to the
            specified period.

        Examples:
            ```python
            import datetime
            from gaspatchio_core import ActuarialFrame
            data = {
                "event_timestamp": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),
                    datetime.datetime(2023, 1, 20, 14, 0, 0),
                    datetime.datetime(2023, 2, 5, 8, 0, 0),
                ]
            }
            af = ActuarialFrame(data)
            # Convert to Year-Month
            af_month = af.with_columns(
                month=af["event_timestamp"].date.to_period(freq="1mo")
            )
            print(af_month.collect())
            ```
            
            ```text
            shape: (3, 2)
            ┌─────────────────────┬────────────┐
            │ event_timestamp     ┆ month      │
            │ ---                 ┆ ---        │
            │ datetime[μs]        ┆ date       │
            ╞═════════════════════╪════════════╡
            │ 2023-01-15 10:30:00 ┆ 2023-01-01 │
            │ 2023-01-20 14:00:00 ┆ 2023-01-01 │
            │ 2023-02-05 08:00:00 ┆ 2023-02-01 │
            └─────────────────────┴────────────┘
            ```
            
            ```python
            # Convert to Year (using same data as previous example)
            import datetime
            from gaspatchio_core import ActuarialFrame
            data = {
                "event_timestamp": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),
                    datetime.datetime(2023, 1, 20, 14, 0, 0),
                    datetime.datetime(2023, 2, 5, 8, 0, 0),
                ]
            }
            af = ActuarialFrame(data)
            af_year = af.with_columns(
                year=af["event_timestamp"].date.to_period(freq="1y")
            )
            print(af_year.collect())
            ```
            
            ```text
            shape: (3, 2)
            ┌─────────────────────┬────────────┐
            │ event_timestamp     ┆ year       │
            │ ---                 ┆ ---        │
            │ datetime[μs]        ┆ date       │
            ╞═════════════════════╪════════════╡
            │ 2023-01-15 10:30:00 ┆ 2023-01-01 │
            │ 2023-01-20 14:00:00 ┆ 2023-01-01 │
            │ 2023-02-05 08:00:00 ┆ 2023-01-01 │
            └─────────────────────┴────────────┘
            ```
        """
        # Ensure the underlying proxy is an expression
        expr = self._proxy._ensure_expr()

        # Polars interval string mapping (simplified)
        polars_freq_map = {
            "Y": "1y",
            "M": "1mo",  # Use 'mo' for month end
            "W": "1w",
            "D": "1d",
        }
        polars_freq = polars_freq_map.get(
            freq.upper(), freq
        )  # Default to input if not found

        # Use dt.truncate for period start
        period_expr = expr.dt.truncate(polars_freq)

        # Import ExpressionProxy from new location
        from ..column.expression_proxy import ExpressionProxy
        
        return ExpressionProxy(period_expr.cast(pl.Date), self._proxy._parent_frame)
