# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
DataFrame filtering logic for calculation graphs.

This module handles filtering DataFrames based on expressions, with optimizations
for common patterns like year filtering.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Final

import polars as pl
from loguru import logger

from gaspatchio._warning import warn

if TYPE_CHECKING:
    from polars import DataFrame

# Where the pre-run cut counts the rows it keeps. In the reserved namespace
# the export's own scaffolding lives in, so a book carrying every name a
# model might write still leaves this one free.
_KEPT: Final[str] = "__gaspatchio_kept_row__"


def rows_the_filter_keeps(
    frame: DataFrame, filter_expr: str | None
) -> tuple[int, ...] | None:
    """Return the positions of ``frame`` a filter keeps, or None if it cannot say.

    **Read before the model runs, so that a selection is made inside the cut
    it was asked for.** ``--filter`` has always narrowed the rows an export's
    values come off; what it did not do was reach the selector, so
    ``--policies 7 --filter 'scenario_id == "BASE"'`` refused policy 7 as
    carried by three rows and then recommended the filter that leaves one of
    them.

    None is the honest answer for a cut this frame cannot be asked about --
    ``col('year') == 5`` against the model points, where ``year`` is a column
    the model has not computed yet. The expression is not wrong; it is about
    the finished frame, where it is applied as it always was, and the
    selection is then made over every row, which is what it always was.

    Args:
        frame: The rows the model will run over.
        filter_expr: The cut, as the caller wrote it, or None.

    Returns:
        The kept positions in the frame's own order, or None where there is
        no cut or the cut cannot be taken over this frame.

    """
    if not filter_expr:
        return None
    try:
        kept = (
            frame.with_row_index(_KEPT)
            .filter(eval(filter_expr, {"pl": pl, "col": pl.col}, {}))  # noqa: S307 -- the expression door :meth:`DataFrameFilter.apply_filter` already opens, on the same trust boundary and the same input
            .get_column(_KEPT)
            .to_list()
        )
    except Exception as failure:  # noqa: BLE001 -- a cut this frame cannot answer is not an error
        logger.debug(
            f"The filter {filter_expr!r} cannot be taken over the rows the "
            f"model will run ({failure}), so the selection is made over all "
            "of them and the filter narrows the finished frame as before."
        )
        return None
    return tuple(int(row) for row in kept)


class DataFrameFilter:
    """Handles filtering of DataFrames with expression evaluation."""

    # Common time-based columns that might be lists
    TIME_COLUMNS: ClassVar[tuple[str, ...]] = (
        "year",
        "month",
        "date",
        "year_frac",
        "quarter",
        "period",
    )

    def __init__(self, df: DataFrame) -> None:
        """
        Initialize the filter with a DataFrame.

        Args:
            df: The DataFrame to filter

        """
        self.df = df
        self._list_columns = self._identify_list_columns()

    def _identify_list_columns(self) -> list[str]:
        """Identify columns with List data type."""
        list_cols = []
        for col in self.TIME_COLUMNS:
            if col in self.df.columns:
                dtype = self.df[col].dtype
                if isinstance(dtype, pl.List):
                    list_cols.append(col)
        return list_cols

    def apply_filter(self, filter_expr: str) -> DataFrame:
        """
        Apply a filter expression to the DataFrame.

        Args:
            filter_expr: Polars filter expression as a string

        Returns:
            Filtered DataFrame

        """
        if not filter_expr:
            return self.df

        try:
            logger.debug(f"Applying filter expression: {filter_expr}")

            # Check for optimizable year filter
            if self._is_simple_year_filter(filter_expr):
                return self._apply_optimized_year_filter(filter_expr)

            # Apply general filter
            return self._apply_general_filter(filter_expr)

        except Exception as e:  # noqa: BLE001 -- eval of the caller's filter text can raise anything (SyntaxError, NameError, a Polars error); the documented answer is to keep every row and say so as a GaspatchioWarning naming the error (test_a_filter_that_cannot_be_applied_says_every_row_is_kept)
            warn(
                f"The filter {filter_expr!r} could not be applied, so every "
                f"row is kept: {e}. Write it as a Polars expression over the "
                f"result's columns, such as \"pl.col('year') == 2025\"."
            )
            return self.df

    def _is_simple_year_filter(self, filter_expr: str) -> bool:
        """Check if this is a simple year equality filter."""
        pattern = r"col\(['\"]year['\"]\)\s*==\s*\d+"
        return bool(re.match(pattern, filter_expr.strip())) and bool(self._list_columns)

    def _apply_optimized_year_filter(self, filter_expr: str) -> DataFrame:
        """Apply optimized year filtering without exploding lists."""
        match = re.match(r"col\(['\"]year['\"]\)\s*==\s*(\d+)", filter_expr.strip())
        if not match:
            return self._apply_general_filter(filter_expr)

        target_year = int(match.group(1))
        year_index = target_year - 1  # Convert to 0-based index

        logger.debug(
            f"Using optimized year filter for year {target_year} (index {year_index})"
        )

        # Add year index as a column for value extraction
        return self.df.with_columns(pl.lit(year_index).alias("__filter_year_index__"))

    def _apply_general_filter(self, filter_expr: str) -> DataFrame:
        """Apply a general filter expression."""
        # Check if we need to explode list columns
        if self._needs_list_explosion(filter_expr):
            df = self._explode_list_columns()
        else:
            df = self.df

        # Evaluate the filter expression
        filter_result = eval(filter_expr, {"pl": pl, "col": pl.col}, {})  # noqa: S307 -- filter_expr is the --filter text of the gspio export that also runs the caller's model.py as Python, or a GraphExportConfig the caller built in Python; eval grants nothing the caller does not already run
        filtered_df = df.filter(filter_result)

        logger.debug(f"Filter reduced rows from {len(df)} to {len(filtered_df)}")
        return filtered_df

    def _needs_list_explosion(self, filter_expr: str) -> bool:
        """Check if filter expression requires list column explosion."""
        if not self._list_columns:
            return False
        return any(col in filter_expr for col in self._list_columns)

    def _explode_list_columns(self) -> DataFrame:
        """Explode all list columns to create multiple rows."""
        logger.debug(f"Exploding list columns: {self._list_columns}")
        df = self.df

        for col in self.df.columns:
            if isinstance(df[col].dtype, pl.List):
                df = df.explode(col)

        logger.debug(f"After exploding: {len(df)} rows")
        return df
