# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Accessors for date-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING, Union

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

            timeline_af = af.date.create_timeline(
                af.start_date, af.end_date, freq="1mo", new_col_name="month_end"
            )

            print(timeline_af.collect())
            ```

            ```text
            shape: (4, 4)
            ┌───────────┬────────────┬────────────┬────────────┐
            │ policy_id ┆ start_date ┆ end_date   ┆ month_end  │
            │ ---       ┆ ---        ┆ ---        ┆ ---        │
            │ i64       ┆ date       ┆ date       ┆ date       │
            ╞═══════════╪════════════╪════════════╪════════════╡
            │ 1         ┆ 2023-01-01 ┆ 2023-03-01 ┆ 2023-01-01 │
            │ 1         ┆ 2023-01-01 ┆ 2023-03-01 ┆ 2023-02-01 │
            │ 2         ┆ 2023-02-15 ┆ 2023-04-15 ┆ 2023-02-15 │
            │ 2         ┆ 2023-02-15 ┆ 2023-04-15 ┆ 2023-03-15 │
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
                "term_months": [6, 12],
            }
            af = ActuarialFrame(data)

            af_plus_1y = af.date.add_duration(
                af.event_date, "1y", new_col_name="event_plus_1y"
            )

            print(af_plus_1y.collect())
            ```

            ```text
            shape: (2, 3)
            ┌────────────┬─────────────┬───────────────┐
            │ event_date ┆ term_months ┆ event_plus_1y │
            │ ---        ┆ ---         ┆ ---           │
            │ date       ┆ i64         ┆ date          │
            ╞════════════╪═════════════╪═══════════════╡
            │ 2023-01-15 ┆ 6           ┆ 2024-01-15    │
            │ 2023-06-30 ┆ 12          ┆ 2024-06-30    │
            └────────────┴─────────────┴───────────────┘
            ```

            ```python
            import datetime
            from gaspatchio_core import ActuarialFrame

            data = {
                "event_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
                "term_months": [6, 12]
            }
            af = ActuarialFrame(data)

            af_minus_3m = af.date.add_duration(af.event_date, "-3mo", new_col_name="event_minus_3m")

            print(af_minus_3m.collect())
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
            import polars as pl
            from gaspatchio_core import ActuarialFrame

            data = {
                "event_timestamp": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),
                    datetime.datetime(2023, 1, 20, 14, 0, 0),
                    datetime.datetime(2023, 2, 5, 8, 0, 0),
                ]
            }
            af = ActuarialFrame(data)

            af.month = af.event_timestamp.dt.truncate("1mo").cast(pl.Date)

            print(af.collect())
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
            import datetime
            import polars as pl
            from gaspatchio_core import ActuarialFrame

            data = {
                "event_timestamp": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),
                    datetime.datetime(2023, 1, 20, 14, 0, 0),
                    datetime.datetime(2023, 2, 5, 8, 0, 0),
                ]
            }
            af = ActuarialFrame(data)

            af.year = af.event_timestamp.dt.truncate("1y").cast(pl.Date)

            print(af.collect())
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

    def months_between(
        self,
        other: Union["ColumnProxy", "ExpressionProxy", datetime.date],
    ) -> "ExpressionProxy":
        """Calculate the number of whole months between two dates.

        Computes ``(year2 - year1) * 12 + (month2 - month1)`` where
        ``self`` is the start date and ``other`` is the end date.
        Returns a positive integer when ``other`` is after ``self``.

        This is the standard actuarial duration calculation used for
        policy duration in months, time-to-maturity, and assumption
        table key derivation.

        !!! note "When to use"
            * **Policy Duration:** Calculate months since issue for use as
                an assumption lookup key (mortality select period, surrender
                charge schedule, commission clawback period).
            * **Time to Maturity:** Compute remaining term in months for
                each policy to determine the projection horizon or the
                ``in_boundary`` mask for IFRS 17 contract boundary.
            * **Cohort Assignment:** Derive issue quarter or issue year-month
                for grouping policies into measurement cohorts.

        Parameters
        ----------
        other : ColumnProxy | ExpressionProxy | datetime.date
            The end date. Can be a column reference (per-policy valuation
            dates), an expression, or a fixed ``datetime.date`` literal
            (single valuation date for the entire portfolio).

        Returns
        -------
        ExpressionProxy
            Integer number of whole months between the dates.

        Examples
        --------
        **Duration from issue date to a fixed valuation date**

        ```python
        import datetime
        from gaspatchio_core import ActuarialFrame

        af = ActuarialFrame(
            {
                "policy_id": ["P001", "P002", "P003"],
                "issue_date": [
                    datetime.date(2020, 3, 15),
                    datetime.date(2018, 11, 1),
                    datetime.date(2023, 7, 20),
                ],
            }
        )

        af.duration_months = af.issue_date.date.months_between(
            datetime.date(2025, 1, 1)
        )

        print(af.collect())
        ```

        ```text
        shape: (3, 3)
        ┌───────────┬────────────┬─────────────────┐
        │ policy_id ┆ issue_date ┆ duration_months │
        │ ---       ┆ ---        ┆ ---             │
        │ str       ┆ date       ┆ i32             │
        ╞═══════════╪════════════╪═════════════════╡
        │ P001      ┆ 2020-03-15 ┆ 58              │
        │ P002      ┆ 2018-11-01 ┆ 74              │
        │ P003      ┆ 2023-07-20 ┆ 18              │
        └───────────┴────────────┴─────────────────┘
        ```

        Notes
        -----
        - Counts whole calendar months, ignoring the day component.
          A policy issued on March 31 and valued on April 1 gives 1 month.
        - Negative values indicate ``other`` is before ``self``.
        - For sub-monthly precision, use ``date.year_frac()`` instead.

        See Also
        --------
        to_period : Truncate dates to period boundaries (month, quarter, year)

        """
        from ..column.column_proxy import ColumnProxy
        from ..column.expression_proxy import ExpressionProxy

        # Get the start date expression (self)
        if isinstance(self._proxy, ExpressionProxy):
            start_expr = self._proxy._expr  # noqa: SLF001
        elif isinstance(self._proxy, ColumnProxy):
            start_expr = pl.col(self._proxy.name)
        else:
            msg = f"Expected ColumnProxy or ExpressionProxy, got {type(self._proxy).__name__}"
            raise TypeError(msg)

        parent = self._proxy._parent  # noqa: SLF001

        # Get the end date expression
        if isinstance(other, datetime.date):
            end_year = pl.lit(other.year)
            end_month = pl.lit(other.month)
        elif isinstance(other, ColumnProxy):
            end_expr = pl.col(other.name)
            end_year = end_expr.dt.year()
            end_month = end_expr.dt.month()
        elif isinstance(other, ExpressionProxy):
            end_expr = other._expr  # noqa: SLF001
            end_year = end_expr.dt.year()
            end_month = end_expr.dt.month()
        else:
            msg = f"other must be ColumnProxy, ExpressionProxy, or datetime.date, got {type(other).__name__}"
            raise TypeError(msg)

        result_expr = (end_year - start_expr.dt.year()) * 12 + (
            end_month - start_expr.dt.month()
        )

        return ExpressionProxy(result_expr, parent)
