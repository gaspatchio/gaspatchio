# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Accessors for date-related operations on ActuarialFrame columns/expressions."""

import datetime
from typing import TYPE_CHECKING, Union

import polars as pl

from gaspatchio._authoring import emit
from gaspatchio.frame.calculation_log import _refuse_reserved_column_names
from gaspatchio.frame.calculations import StructuralOperation, with_columns_operation
from gaspatchio.frame.lowering.context import context_for
from gaspatchio.frame.lowering.polars import lower_polars
from gaspatchio.frame.registry import register_accessor

# Use the new base location
from .base import (
    BaseColumnAccessor,
    BaseFrameAccessor,
    column_node,
    refuse_bare_string_operand,
)

# Use TYPE_CHECKING for core components to avoid circular imports
if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.column.column_proxy import ColumnProxy
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame


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

    **Frame-level methods name columns by string.** ``af.date.add_duration(
    "issue_date", "1y")`` reads the way ``rename``, ``drop`` and
    ``projection.set(issue_age_column=...)`` already read: the string is the
    name of a column on this frame, and a name the frame does not carry is
    refused rather than quietly becoming the literal text. Column-*level*
    operands are the opposite -- ``af.issue_date.excel.edate("months")`` is
    ambiguous between a column and a value, so it is refused too.

    **Both verbs here stamp the frame in place** and hand the same frame
    back, the way ``projection.set``, ``rename`` and ``join`` already do.
    ``create_timeline`` changes the row count as well; there is no "before"
    frame kept behind it.

    ``date`` is a reserved attribute on the frame, as ``excel``, ``finance``,
    ``graph`` and ``projection`` are. A model whose data really does carry a
    column called ``date`` still has it -- reach it as ``af["date"]`` -- but
    ``af.date`` is always this accessor.
    """

    def __init__(self, frame: "ActuarialFrame") -> None:
        """Initialize the accessor with the parent ActuarialFrame.

        This is typically called internally when accessing `af.date`.
        """
        super().__init__(frame)

    def _stamp_in_place(
        self,
        stamp: StructuralOperation,
        column: str,
        node: "OpNode",
    ) -> "ActuarialFrame":
        """Run this accessor's own frame through ``stamp`` and record ``column``.

        The frame after a date verb is the SAME model one step further on,
        not a new one: every column it carries was calculated on the frame
        the verb was called on. Stamping in place is what keeps that true --
        a replacement frame would start with an empty calculation log,
        restarted ordinals, and every earlier column re-labelled a field the
        model points supplied.

        The date column goes over as the calculation it is -- a range or an
        offset over the columns it was given -- rather than as data that
        arrived from nowhere. The expression held is the plain post-stamp
        reference to it, which is the only one true of it afterwards. The
        stamp itself is the operation the sealed window keeps, so that a
        calculation named behind the verb can be confirmed on the plan the
        verb went on to make.
        """
        _refuse_reserved_column_names((column,), door="new_col_name")
        frame = self._frame
        plan = frame._df  # noqa: SLF001 -- its own frame
        if plan is None:
            msg = "Cannot add a date column to an uninitialized ActuarialFrame."
            raise ValueError(msg)
        new_df = stamp.applied_to(plan)
        frame._set_plan(new_df)  # noqa: SLF001 -- its own frame
        frame._reset_attribution_window(stamp)  # noqa: SLF001 -- its own frame
        frame._schema = new_df.collect_schema()  # noqa: SLF001 -- its own frame
        if column not in frame._column_order:  # noqa: SLF001 -- its own frame
            frame._column_order.append(column)  # noqa: SLF001 -- its own frame
        frame._refresh_attr_columns_set()  # noqa: SLF001 -- its own frame
        frame._record_minted_columns(  # noqa: SLF001 -- its own frame
            {column: (node, pl.col(column))},
            origin="date",
        )
        return frame

    def create_timeline(
        self,
        start_col: "str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series",
        end_col: "str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series",
        freq: str = "1d",
        new_col_name: str = "timeline_date",
        closed: str = "left",
    ) -> "ActuarialFrame":  # Return type is ActuarialFrame
        """Create timeline columns based on start and end dates.

        Generates a list of dates for each row based on its start and end date,
        using the specified frequency. The result is exploded to create
        a longer DataFrame where each original row is repeated for each date
        in its timeline.

        !!! note "When to use"
            *   **Period-to-Event Transformation:** This method is useful when you need
                to transform row-per-period data (where each row has a start and end
                date) into row-per-event data (where each row represents a specific
                point in time, like a month-end). For example, to calculate monthly
                exposures from policy start/end dates.

        !!! warning "This modifies the frame you call it on"
            The timeline is stamped **in place** and the same frame is handed
            back, the way ``projection.set``, ``rename`` and ``join`` already
            work. That is what keeps the calculations made before the call
            answerable afterwards — a replacement frame would start with no
            history of them. The row count changes with it, so there is no
            "before" frame to keep: `af.date.create_timeline(...)` and
            `af = af.date.create_timeline(...)` do the same thing, and to
            build two timelines over the same model points, build two frames.

        Args:
            start_col: The start date of the interval. A **string is the name
                       of a column on this frame** (refused if the frame does
                       not carry it); a column, expression or Series is used
                       as given.
            end_col: The end date of the interval, named the same two ways.
            freq: The frequency of the timeline (e.g., "1M", "1Y", "1d").
                  Passed to `pl.date_ranges`.
            new_col_name: Name for the new column containing the generated timeline
                          dates. Defaults to "timeline_date". Must not already be a
                          column on the frame — the timeline is a new column, not a
                          replacement for one.
            closed: Which side of the interval is closed ("left", "right", "both",
                    "none"). Passed to `pl.date_ranges`.

        Returns:
            This same frame, now one row per period with the timeline column
            on it.

        Raises:
            pl.exceptions.ColumnNotFoundError: If `start_col` or `end_col` names
                             a column the frame does not carry.
            ValueError: If `new_col_name` is already a column on the frame.
            pl.ComputeError: If date range generation fails (e.g., invalid freq,
                             incompatible date types).

        Examples:
            **Naming the two date columns by string**

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "policy_id": [1, 2],
                "start_date": [datetime.date(2023, 1, 1), datetime.date(2023, 2, 15)],
                "end_date": [datetime.date(2023, 3, 1), datetime.date(2023, 4, 15)],
            }
            af = ActuarialFrame(data)

            af.date.create_timeline(
                "start_date", "end_date", freq="1mo", new_col_name="month_end"
            )

            print(af.collect())
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
        # --- Input Validation and Operand Resolution --- #
        # A string here is a column NAME, checked against the frame: this is
        # the frame level, where naming a column by string is the idiom. It
        # resolves to the column REFERENCE the range's own tree records --
        # `date.date_ranges` is an operation the format names, and a name
        # lowered to an engine fragment first made it read as an escape.
        start_node = column_node(self._frame, start_col, parameter="start_col")
        end_node = column_node(self._frame, end_col, parameter="end_col")

        # The timeline is built under a temporary name and renamed into place,
        # so a name the frame already holds would land a SECOND column under
        # it -- legal to build, fatal at collect, and by then this frame is
        # the only one the caller has. Refused at the call instead.
        if new_col_name in self._frame.columns:
            msg = (
                f"new_col_name={new_col_name!r} is already a column on this "
                "frame, and the timeline is a new column rather than a "
                "replacement for one. Pick a name the frame does not hold, or "
                f"drop {new_col_name!r} first."
            )
            raise ValueError(msg)

        # --- Core Logic: Generate and Explode Date Ranges --- #
        # 1. Create the date ranges as a list column
        ranges_node = emit.call_node(
            "date.date_ranges",
            (start_node, end_node),
            (("interval", freq), ("closed", closed)),
        )
        date_ranges_expr = lower_polars(ranges_node, context_for(self._frame)).alias(
            new_col_name
        )

        # 2. Add the list column to the DataFrame
        # Use a temporary name to avoid conflicts if new_col_name exists
        temp_col_name = f"__{new_col_name}_ranges__"

        def _timeline(plan: pl.LazyFrame) -> pl.LazyFrame:
            # 3. Explode the list column
            # Keep other columns, replace the list col with the exploded dates.
            # `empty_as_null=True` is stated rather than left to the default,
            # which Polars 2.0 flips. It is the behaviour this method has
            # always had, and the one a timeline wants: a policy whose interval
            # is empty -- expired before it started, or a term of zero under
            # `closed="left"` -- keeps ONE row carrying a null date, so it stays
            # in the frame and is visible as a policy with no periods. Dropping
            # to no rows would remove that policy from the model without
            # saying so.
            return (
                plan.with_columns(date_ranges_expr.alias(temp_col_name))
                .explode(temp_col_name, empty_as_null=True)
                .rename({temp_col_name: new_col_name})
            )

        # --- Stamp the exploded plan onto this same frame --- #
        return self._stamp_in_place(
            StructuralOperation("date", _timeline), new_col_name, ranges_node
        )

    def add_duration(
        self,
        date_col: "str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series",
        duration_str: str,
        new_col_name: str | None = None,
    ) -> "ActuarialFrame":
        """Add a duration string (e.g., '1Y', '3M', '-7d') to a date column.

        This function leverages Polars' powerful duration arithmetic to efficiently
        modify dates within the ActuarialFrame. It can create a new column with
        the resulting dates or overwrite the original column if `new_col_name` is
        not provided and `date_col` is a string name.

        !!! note "When to use"
            *   **Date Arithmetic:** Use this method to shift dates by a fixed duration,
                such as calculating a policy anniversary, determining a future maturity
                date, or finding a past event date. It's particularly useful for batch
                operations on an entire column of dates.

        !!! warning "This modifies the frame you call it on"
            The offset column is stamped **in place** and the same frame is
            handed back, the way ``projection.set``, ``rename`` and ``join``
            already work — the calculations made before the call stay
            answerable afterwards. There is no "before" frame to keep.

        Args:
            date_col: The dates to add the duration to. A **string is the name
                      of a column on this frame** (refused if the frame does
                      not carry it); a column, expression or Series is used as
                      given.
            duration_str: The duration string in Polars format (e.g., "1Y6M", "-3d12h").
            new_col_name: The name for the new column containing the resulting dates.
                          If None, overwrites the named column (which requires
                          `date_col` to be a string name).

        Returns:
            This same frame, now carrying the added or overwritten column.

        Raises:
            pl.exceptions.ColumnNotFoundError: If `date_col` names a column the
                      frame does not carry.
            ValueError: If `new_col_name` is omitted and `date_col` is not a
                      string name, so there is no column to overwrite.
            pl.ComputeError: If the duration addition fails (e.g., invalid duration
                             string, incompatible date types).

        Examples:
            **Overwriting the named column in place**

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "event_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
                "term_months": [6, 12],
            }
            af = ActuarialFrame(data)

            af.date.add_duration("event_date", "1y")

            print(af.collect())
            ```

            ```text
            shape: (2, 2)
            ┌────────────┬─────────────┐
            │ event_date ┆ term_months │
            │ ---        ┆ ---         │
            │ date       ┆ i64         │
            ╞════════════╪═════════════╡
            │ 2024-01-15 ┆ 6           │
            │ 2024-06-30 ┆ 12          │
            └────────────┴─────────────┘
            ```

            **Adding the offset alongside, under a new name**

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "event_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
                "term_months": [6, 12],
            }
            af = ActuarialFrame(data)

            af.date.add_duration(af.event_date, "1y", new_col_name="event_plus_1y")

            print(af.collect())
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

            **A negative duration walks the dates backwards**

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "event_date": [datetime.date(2023, 1, 15), datetime.date(2023, 6, 30)],
                "term_months": [6, 12],
            }
            af = ActuarialFrame(data)

            af.date.add_duration("event_date", "-3mo", new_col_name="event_minus_3m")

            print(af.collect())
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
        # A string here is a column NAME, checked against the frame -- the
        # in-place form this method's own docstring advertises. It resolves
        # to the column REFERENCE the offset's own tree records, so that
        # `date.offset_by` -- an operation the format's vocabulary names --
        # is recorded under that name rather than as an engine escape over
        # the framework's own rendering of the name it was given.
        date_node = column_node(self._frame, date_col, parameter="date_col")

        node = emit.call_node(
            "date.offset_by", (date_node,), (("duration", duration_str),)
        )
        result_expr = lower_polars(node, context_for(self._frame))

        # Determine the target column name
        target_col_name: str
        if new_col_name:
            target_col_name = new_col_name
        elif isinstance(date_col, str):
            target_col_name = date_col  # Overwrite the column that was named
        else:
            msg = "new_col_name must be provided if date_col is not a string"
            raise ValueError(msg)

        stamp = with_columns_operation("date", result_expr.alias(target_col_name))
        return self._stamp_in_place(stamp, target_col_name, node)


# Add registration decorator
@register_accessor("date", kind="column")
class DateColumnAccessor(BaseColumnAccessor):
    """Provides date-related methods for `ColumnProxy` or `ExpressionProxy` objects.

    Accessed via `.date` on a column or expression,
    e.g., `af["my_date_col"].date`.

    This accessor offers convenient methods to manipulate and extract
    information from date/datetime columns within Polars expressions.

    **A bare string operand is refused here: write the operand as
    ``af.column`` or ``af["column"]``.** That rule holds on every column
    accessor, and is stated once in
    ``gaspatchio.accessors.base.refuse_bare_string_operand`` -- along with
    the frame-level methods, ``DateFrameAccessor``'s among them, that *do*
    name a column by string.
    """

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None:
        """Initialize the accessor with the parent proxy object.

        This is typically called internally when accessing `.date` on a
        column/expression.
        """
        super().__init__(proxy)
        # Refine type hint now that we expect specific proxy types
        self._proxy: ColumnProxy | ExpressionProxy = proxy

    def to_period(self, freq: str = "M") -> "ExpressionProxy":
        """Convert a date/datetime column to a period representation (e.g., year-month).

        This is useful for grouping or aggregating data by specific time periods
        like month, quarter, or year. It truncates the date to the beginning
        of the specified period.

        !!! note "When to use"
            *   **Period Aggregation:** Use this to aggregate daily or weekly data into
                monthly, quarterly, or annual summaries.
            *   **Time Series Features:** For creating features for time series models
                based on periods.
            *   **Date Alignment:** When you need to align dates to a common period
                start (e.g., all dates in January 2023 become 2023-01-01 if `freq="M"`).

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
            **Claims aggregated into the month they occurred**

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "claim_date": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),
                    datetime.datetime(2023, 1, 20, 14, 0, 0),
                    datetime.datetime(2023, 2, 5, 8, 0, 0),
                ]
            }
            af = ActuarialFrame(data)

            af.claim_month = af.claim_date.date.to_period("M")

            print(af.collect())
            ```

            ```text
            shape: (3, 2)
            ┌─────────────────────┬─────────────┐
            │ claim_date          ┆ claim_month │
            │ ---                 ┆ ---         │
            │ datetime[μs]        ┆ date        │
            ╞═════════════════════╪═════════════╡
            │ 2023-01-15 10:30:00 ┆ 2023-01-01  │
            │ 2023-01-20 14:00:00 ┆ 2023-01-01  │
            │ 2023-02-05 08:00:00 ┆ 2023-02-01  │
            └─────────────────────┴─────────────┘
            ```

            **The same dates snapped to their issue year**

            ```python
            import datetime
            from gaspatchio import ActuarialFrame

            data = {
                "claim_date": [
                    datetime.datetime(2023, 1, 15, 10, 30, 0),
                    datetime.datetime(2023, 1, 20, 14, 0, 0),
                    datetime.datetime(2023, 2, 5, 8, 0, 0),
                ]
            }
            af = ActuarialFrame(data)

            af.claim_year = af.claim_date.date.to_period("Y")

            print(af.collect())
            ```

            ```text
            shape: (3, 2)
            ┌─────────────────────┬────────────┐
            │ claim_date          ┆ claim_year │
            │ ---                 ┆ ---        │
            │ datetime[μs]        ┆ date       │
            ╞═════════════════════╪════════════╡
            │ 2023-01-15 10:30:00 ┆ 2023-01-01 │
            │ 2023-01-20 14:00:00 ┆ 2023-01-01 │
            │ 2023-02-05 08:00:00 ┆ 2023-01-01 │
            └─────────────────────┴────────────┘
            ```
        """
        return emit.call(
            "date.to_period",
            (self._proxy._node,),  # noqa: SLF001
            self._proxy._parent,  # noqa: SLF001
            (("freq", freq),),
        )

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
            (single valuation date for the entire portfolio). A bare string
            is refused — pass ``af["valuation_date"]`` for the column.

        Returns
        -------
        ExpressionProxy
            Integer number of whole months between the dates.

        Examples
        --------
        **Duration from issue date to a fixed valuation date**

        ```python
        import datetime
        from gaspatchio import ActuarialFrame

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
        # `gaspatchio.column` reaches `frame.base`, which imports back from
        # `gaspatchio.column`, so a module-level import of either proxy from
        # an accessor fails on a partially initialised package.
        from gaspatchio.column.column_proxy import (  # noqa: PLC0415 — import cycle
            ColumnProxy,
        )
        from gaspatchio.column.expression_proxy import (  # noqa: PLC0415 — import cycle
            ExpressionProxy,
        )

        # Before the generic type check below, because a string is the one
        # wrong operand with a specific fix to point at.
        refuse_bare_string_operand(other, parameter="other")
        if not isinstance(self._proxy, (ColumnProxy, ExpressionProxy)):
            msg = (
                f"Expected ColumnProxy or ExpressionProxy, got "
                f"{type(self._proxy).__name__}"
            )
            raise TypeError(msg)
        if not isinstance(other, (ColumnProxy, ExpressionProxy, datetime.date)):
            msg = (
                f"other must be ColumnProxy, ExpressionProxy, or datetime.date, "
                f"got {type(other).__name__}"
            )
            raise TypeError(msg)

        return emit.call(
            "date.months_between",
            (self._proxy._node, other),  # noqa: SLF001
            self._proxy._parent,  # noqa: SLF001
        )


# What the API reference documents from this module.
__all__ = ["DateColumnAccessor", "DateFrameAccessor"]
