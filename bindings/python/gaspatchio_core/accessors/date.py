"""Accessors for date-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING

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
    from ..typing import IntoExprColumn

# ADDED: More imports for moved logic
from typing import Literal, Union


# Add registration decorator
@register_accessor("date", kind="frame")
class DateFrameAccessor(BaseFrameAccessor):
    """Provides date-related methods applicable to the entire ActuarialFrame.

    Accessed via `.date` on an ActuarialFrame instance,
    e.g., `af.date`.
    """

    def __init__(self, frame: "ActuarialFrame"):
        """Initializes the accessor with the parent ActuarialFrame."""
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
        """
        # Eagerly validate projection_frequency
        valid_frequencies = ("monthly", "quarterly", "semi-annual", "annual")
        if projection_frequency not in valid_frequencies:
            raise ValueError(
                f"Invalid projection frequency: {projection_frequency}. "
                f"Must be one of {valid_frequencies}"
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
            if issue_age_column not in self._frame._df.columns:
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
            raise ValueError(f"Invalid projection end type: {projection_end_type}")

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
        self._frame._schema = self._frame._df.schema
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

        return self._frame  # Return the modified frame


# Add registration decorator
@register_accessor("date", kind="column")
class DateColumnAccessor(BaseColumnAccessor):
    """Provides date-related methods applicable to columns or expressions.

    Accessed via `.date` on an ActuarialFrame column or expression proxy,
    e.g., `af["my_date_col"].date`.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy"):
        """Initializes the accessor with the parent proxy."""
        super().__init__(proxy)
        # Refine type hint now that we expect specific proxy types
        self._proxy: "ColumnProxy | ExpressionProxy" = proxy

    def to_period(self, freq: str = "M") -> "ExpressionProxy":
        """Converts a date/datetime column to a period representation (e.g., year-month).

        Currently truncates the date to the beginning of the specified frequency.

        Args:
            freq: The frequency to truncate to ('Y', 'M', 'W', 'D').
                  More complex Polars frequencies might work but are less standard for periods.

        Returns:
            An ExpressionProxy representing the truncated date (start of the period).

        Raises:
            RuntimeError: If the proxy is not part of an ActuarialFrame context.
            pl.ComputeError: On truncation errors.
        """
        # Import from new location
        from ..column.expression_proxy import ExpressionProxy

        parent_frame = self._get_parent_frame()
        base_expr = self._get_polars_expr()

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
        period_expr = base_expr.dt.truncate(polars_freq)

        return ExpressionProxy(period_expr.cast(pl.Date), parent_frame)
