# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Compilation error finder using schema validation and operation replay.

This module extends ErrorBoundaryFinder to handle compilation-specific errors
by using schema validation instead of execution to find failing operations.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

from .boundary import ErrorBoundaryFinder

if TYPE_CHECKING:
    from gaspatchio.frame.base import ActuarialFrame
    from gaspatchio.frame.calculations import CalculationRecord


class CompilationErrorFinder(ErrorBoundaryFinder):
    """
    Extends ErrorBoundaryFinder for compilation errors.

    Uses schema validation instead of execution to find failures.
    """

    def __init__(self, af: ActuarialFrame, exception: Exception) -> None:
        """
        Initialize the compilation error finder.

        Args:
            af: The ActuarialFrame with failed compilation
            exception: The compilation exception that was raised

        """
        super().__init__(af, exception)
        self.compilation_error_type = type(exception)
        logger.debug(
            f"CompilationErrorFinder initialized for {self.compilation_error_type}"
        )

    def find_failing_operation(
        self,
    ) -> tuple[int, CalculationRecord | None, pl.DataFrame]:
        """
        Find the failing operation using schema validation.

        Returns:
            Tuple of (failing_index, failing_calculation, last_good_dataframe)
            If no failing operation found, returns (-1, None, original_df)

        """
        if not self.groups:
            logger.debug("Empty attribution window, no operations to search")
            return -1, None, self.original_df

        # Use linear search for compilation errors to get accurate context
        return self._linear_search_with_schema()

    def _linear_search_with_schema(
        self,
    ) -> tuple[int, CalculationRecord | None, pl.DataFrame]:
        """
        Perform linear search using schema validation.

        Returns:
            Tuple of (failing_index, failing_calculation, last_good_dataframe)

        """
        last_good_df = self.original_df

        logger.debug(f"Starting linear schema search on {len(self.groups)} operations")

        for i in range(len(self.groups)):
            try:
                # Apply operations up to this point
                test_df = self._apply_single_operation(i, last_good_df)
                if test_df is not None:
                    last_good_df = test_df
                logger.trace(f"Operation {i} succeeded")
            # The replay runs the user's own expressions, and the error it is
            # looking for is whatever type their collect raised
            # (compilation_error_type), so it admits any; one that is not the
            # error sought is logged below and the search moves on.
            except Exception as e:  # noqa: BLE001 -- see above
                if self._is_same_compilation_error(e):
                    logger.debug(f"Found compilation error at operation {i}")
                    # Deliberate asymmetry, and it only bites a multi-column
                    # operation: this search selects the operation with the
                    # LOOSE compilation predicate, while `_blame_within_group`
                    # narrows to one of its columns with the base class's
                    # STRICT same-exception-type test. A group the loose
                    # predicate accepted can therefore have no column that
                    # satisfies the strict one, in which case narrowing
                    # returns None and the caller falls back to the basic
                    # column report. Lossy, never wrong — which is the side
                    # of the #39 fallback contract to be on. Routing
                    # narrowing through the loose predicate would attribute
                    # more, and is the change to make once there is a way to
                    # exercise it: the divergence needs a compilation error
                    # inside a traced multi-column `with_columns`, which
                    # nothing in the suite produces today.
                    return i, self._blame_within_group(i), last_good_df
                logger.trace(f"Different error type at operation {i}: {type(e)}")

        logger.debug("No failing operation found in linear search")
        return -1, None, last_good_df

    def _apply_single_operation(
        self, index: int, base_df: pl.DataFrame
    ) -> pl.DataFrame | None:
        """
        Apply a single operation and validate its schema.

        Args:
            index: Index of operation to apply
            base_df: Base DataFrame to apply operation to

        Returns:
            Resulting DataFrame or None if operation is invalid

        """
        operation = self._get_operation_at(index)
        if operation is None:
            return None

        # Start with lazy frame
        current_df = base_df.lazy() if not hasattr(base_df, "lazy") else base_df

        # Apply all operations up to and including this one, each as the
        # single with_columns call the frame itself applied it in.
        for i in range(index + 1):
            op = self._get_operation_at(i)
            if op is not None:
                current_df = current_df.with_columns(*self._group_exprs(op))

        # Try to validate schema. A schema error propagates to the caller,
        # which catches it.
        # First try schema collection (cheapest)
        _ = current_df.collect_schema()
        # If schema is valid, collect limited data for context
        return self._safe_collect(current_df)

    def _safe_collect(self, df: pl.LazyFrame | pl.DataFrame) -> pl.DataFrame:
        """
        Safely collect limited data for error context.

        The replay above hands over whichever of the two frames it was
        given: a LazyFrame when the failing frame was still lazy, an
        already-collected DataFrame otherwise. Only the lazy one has rows
        left to fetch, so only it is asked for a preview; the eager one
        falls through to the schema-shaped empty frame, which is what it
        answered with before -- ``DataFrame`` has no ``collect``, so the
        attempt raised and landed in the same branch.

        Args:
            df: The frame to take error context from

        Returns:
            Collected DataFrame with limited rows

        """
        if isinstance(df, pl.LazyFrame):
            # Try to collect just a few rows for context; the schema branch
            # below answers when that fails.
            with contextlib.suppress(Exception):
                return df.limit(10).collect()
        try:
            # If that fails, try empty collection with schema
            schema = df.collect_schema()
            return pl.DataFrame(schema=schema)
        except pl.exceptions.PolarsError:
            # A plan whose schema will not resolve: the frame the replay
            # started from is the last state known to be good
            return self.original_df

    def _is_same_compilation_error(self, exception: Exception) -> bool:
        """
        Check if exception is the same compilation error type.

        Args:
            exception: Exception to check

        Returns:
            True if it's the same compilation error

        """
        # Check exact type match
        if isinstance(exception, self.compilation_error_type):
            return True

        # Check for common compilation error types
        compilation_types: tuple[type[BaseException], ...] = (
            pl.exceptions.ComputeError,
            pl.exceptions.ColumnNotFoundError,
        )

        # SchemaError is not in every Polars version, so it joins the tuple
        # only when the installed one has it.
        if hasattr(pl.exceptions, "SchemaError"):
            compilation_types = (*compilation_types, pl.exceptions.SchemaError)

        return isinstance(
            exception, compilation_types
        ) and self._has_compilation_context(exception)

    def _has_compilation_context(self, exception: Exception) -> bool:
        """
        Check if exception has compilation context indicators.

        Args:
            exception: Exception to check

        Returns:
            True if exception appears to be compilation-related

        """
        error_str = str(exception)
        compilation_indicators = [
            "FAILED HERE RESOLVING",
            "query optimization",
            "type inference",
            "schema",
            "unable to determine output",
        ]

        return any(indicator in error_str for indicator in compilation_indicators)
