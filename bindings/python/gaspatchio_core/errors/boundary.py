# ABOUTME: Error boundary detection using binary search replay
# ABOUTME: Finds the exact operation that causes compilation or runtime errors
"""Error boundary detection using binary search replay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame

    from .metadata import TracedOperation


class ErrorBoundaryFinder:
    """Efficiently find the failing operation using binary search."""

    def __init__(self, af: ActuarialFrame, exception: Exception) -> None:
        """Initialize the error boundary finder.

        Args:
            af: The ActuarialFrame with failed computation
            exception: The exception that was raised

        """
        self.af = af
        self.exception = exception
        # Convert LazyFrame to DataFrame for binary search operations
        if af._df is not None:  # noqa: SLF001
            if hasattr(af._df, "collect"):  # noqa: SLF001
                # It's a LazyFrame, collect it
                try:
                    self.original_df = af._df.collect()  # noqa: SLF001
                except Exception:  # noqa: BLE001
                    # If collection fails, try to reconstruct original data
                    # using the stored schema (before computation graph ops)
                    if hasattr(af, "_schema") and af._schema:  # noqa: SLF001
                        # Create empty DataFrame with original schema columns
                        self.original_df = pl.DataFrame(schema=af._schema)  # noqa: SLF001
                    else:
                        self.original_df = pl.DataFrame()
            else:
                # It's already a DataFrame
                self.original_df = af._df  # noqa: SLF001
        else:
            self.original_df = pl.DataFrame()
        self.exception_type = type(exception)

    def find_failing_operation(
        self,
    ) -> tuple[int, TracedOperation | None, pl.DataFrame]:
        """Find the first operation that fails using binary search.

        Returns:
            Tuple of (failing_index, failing_operation, last_good_dataframe)
            If no failing operation found, returns (-1, None, original_df)

        """
        operations = self.af._computation_graph  # noqa: SLF001

        # Handle empty graph
        if not operations:
            logger.debug("Empty computation graph, no operations to search")
            return -1, None, self.original_df

        # Early termination: check if first operation fails
        try:
            self._apply_operations_up_to(0)
        except Exception as e:  # noqa: BLE001
            if self._is_same_error_type(e):
                logger.debug("First operation fails, returning index 0")
                return 0, self._get_operation_at(0), self.original_df

        # Early termination: check if all operations succeed
        try:
            final_df = self._apply_operations_up_to(len(operations) - 1)
        except Exception as e:  # noqa: BLE001
            if not self._is_same_error_type(e):
                logger.debug(f"Different error type during full replay: {type(e)}")
                return -1, None, self.original_df
        else:
            logger.debug("All operations succeed, no failing operation found")
            return -1, None, final_df

        # Binary search for the failing operation
        return self._binary_search_failure()

    def _binary_search_failure(
        self,
    ) -> tuple[int, TracedOperation | None, pl.DataFrame]:
        """Perform binary search to find the first failing operation.

        Returns:
            Tuple of (failing_index, failing_operation, last_good_dataframe)

        """
        operations = self.af._computation_graph  # noqa: SLF001
        left, right = 0, len(operations) - 1
        last_good_df = self.original_df
        failing_index = -1

        logger.debug(f"Starting binary search on {len(operations)} operations")

        while left <= right:
            mid = (left + right) // 2
            logger.trace(
                f"Binary search: ops 0-{mid} (left={left}, right={right})",
            )

            try:
                test_df = self._apply_operations_up_to(mid)
                # This point succeeded, error is later
                last_good_df = test_df
                left = mid + 1
                logger.trace(f"Operations 0-{mid} succeeded, searching right half")
            except Exception as e:  # noqa: BLE001
                if self._is_same_error_type(e):
                    # Error at or before this point
                    failing_index = mid
                    right = mid - 1
                    logger.trace(
                        f"Ops 0-{mid} failed with same error, searching left",
                    )
                else:
                    # Different error type, continue searching right
                    last_good_df = (
                        self._apply_operations_up_to(mid - 1)
                        if mid > 0
                        else self.original_df
                    )
                    left = mid + 1
                    logger.trace(
                        f"Different error at ops 0-{mid}, searching right",
                    )

        # Refine to find exact failing operation
        if failing_index != -1:
            # Binary search found a range, now find exact operation
            exact_index = self._find_exact_failing_operation(
                failing_index,
                last_good_df,
            )
            failing_op = self._get_operation_at(exact_index)
            logger.debug(f"Found failing operation at index {exact_index}")
            return exact_index, failing_op, last_good_df

        logger.debug("Binary search completed, no failing operation found")
        return -1, None, last_good_df

    def _find_exact_failing_operation(
        self,
        start_index: int,
        last_good_df: pl.DataFrame,
    ) -> int:
        """Find the exact failing operation starting from a known failing range.

        Args:
            start_index: Index where we know failure occurs
            last_good_df: Last known good DataFrame

        Returns:
            Exact index of failing operation

        """
        operations = self.af._computation_graph  # noqa: SLF001
        current_df = last_good_df.lazy()  # Convert to LazyFrame for operations

        # Apply operations one by one from the last good state
        for i in range(max(0, start_index - 1), len(operations)):
            try:
                operation = self._get_operation_at(i)
                if operation is None:
                    continue

                # Apply this single operation
                if isinstance(operation, tuple):
                    alias, expr = operation
                else:
                    alias, expr = operation.alias, operation.expression

                current_df = current_df.with_columns(expr.alias(alias))
                # Test by collecting to see if it fails
                _ = current_df.collect()
                logger.trace(f"Operation {i} ({alias}) succeeded")

            except Exception as e:  # noqa: BLE001
                if self._is_same_error_type(e):
                    logger.debug(f"Exact failing operation found at index {i}")
                    return i
                logger.trace(f"Different error type at operation {i}, continuing")
                continue

        # Fallback to start_index if exact operation not found
        return start_index

    def _apply_operations_up_to(self, end_index: int) -> pl.DataFrame:
        """Apply operations from start to end_index (inclusive) efficiently.

        Args:
            end_index: Last operation index to apply (inclusive)

        Returns:
            Resulting DataFrame after applying operations

        Raises:
            Exception: If any operation in the range fails

        """
        if end_index < 0:
            return self.original_df

        operations = self.af._computation_graph  # noqa: SLF001
        if end_index >= len(operations):
            end_index = len(operations) - 1

        # Check if we have any valid operations to apply
        valid_operations = []
        for i in range(end_index + 1):
            operation = self._get_operation_at(i)
            if operation is not None:
                valid_operations.append((i, operation))

        # If no valid operations, return original DataFrame
        if not valid_operations:
            return self.original_df

        # Start with the original DataFrame (already converted from LazyFrame)
        current_df = self.original_df.lazy()  # Convert to LazyFrame for operations

        # Apply operations sequentially
        for _, operation in valid_operations:
            # Handle both tuple and TracedOperation formats
            if isinstance(operation, tuple):
                alias, expr = operation
            else:
                alias, expr = operation.alias, operation.expression

            # Apply the operation
            current_df = current_df.with_columns(expr.alias(alias))

        # Collect the result to DataFrame for return
        return current_df.collect()

    def _get_operation_at(self, index: int) -> tuple[str, Any] | TracedOperation | None:
        """Get operation at specified index with bounds checking.

        Args:
            index: Index of operation to retrieve

        Returns:
            Operation at index, or None if index is out of bounds

        """
        operations = self.af._computation_graph  # noqa: SLF001
        if 0 <= index < len(operations):
            return operations[index]
        return None

    def _is_same_error_type(self, exception: Exception) -> bool:
        """Check if the given exception is the same type as the original error.

        Args:
            exception: Exception to check

        Returns:
            True if exception types match

        """
        return isinstance(exception, self.exception_type)
