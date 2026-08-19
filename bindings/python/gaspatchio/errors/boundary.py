# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Error boundary detection using binary search replay
# ABOUTME: Finds the exact operation that causes compilation or runtime errors
"""Error boundary detection using binary search replay."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from gaspatchio.frame.base import ActuarialFrame

    from .metadata import TracedOperation


def is_plan_lowering_panic(exception: BaseException) -> bool:
    """Return True for pyo3 panics raised by plan lowering's schema derivation.

    A schema mismatch inside a ``when().then()`` branch fails during IR plan
    lowering, where polars panics ("no valid schema can be derived") instead
    of raising a typed error. pyo3 surfaces that as ``PanicException`` — a
    ``BaseException`` subclass that bypasses every ``except Exception``.
    Matched by type name rather than import: ``pyo3_runtime`` is a synthetic
    module and this predicate must be safe to call before/without it.

    Kept narrow deliberately (#54): only the schema-derivation panic is a
    data-shape failure that reproduces deterministically under replay. Any
    other panic — and any real interrupt — must pass through untouched.
    """
    return type(
        exception
    ).__name__ == "PanicException" and "no valid schema can be derived" in str(
        exception
    )


def _replayable(exception: BaseException) -> bool:
    """Return True when a replay probe may consume this exception.

    Probes catch ``BaseException`` so schema-derivation panics can be matched
    like any other failure, but anything that is neither an ``Exception`` nor
    such a panic (``KeyboardInterrupt``, ``SystemExit``, foreign panics) must
    propagate immediately.
    """
    return isinstance(exception, Exception) or is_plan_lowering_panic(exception)


class ErrorBoundaryFinder:
    """Efficiently find the failing operation using binary search."""

    def __init__(
        self,
        af: ActuarialFrame,
        exception: BaseException,
        max_rows: int | None = None,
    ) -> None:
        """Initialize the error boundary finder.

        Args:
            af: The ActuarialFrame with failed computation
            exception: The exception that was raised
            max_rows: Optional row cap applied to the replay baseline. Replay
                collects real data repeatedly; on a 100K-policy frame an
                uncapped replay multiplies the failed run's full cost on the
                error path. A capped baseline keeps diagnosis fast — an error
                that only manifests beyond the cap simply fails to reproduce,
                which callers treat as "no attribution".

        """
        self.af = af
        self.exception = exception
        # Replay must start from the PRE-OP baseline captured when the trace
        # sequence began: _df already contains every recorded operation, so
        # replaying the graph on top of it would re-apply self-referential
        # operations during diagnosis and misattribute the failing op.
        source = getattr(af, "_baseline_df", None)
        if source is None:
            source = af._df  # noqa: SLF001
        if source is not None and max_rows is not None:
            source = (
                source.limit(max_rows)
                if hasattr(source, "collect")
                else source.head(max_rows)
            )
        if source is not None:
            if hasattr(source, "collect"):
                # It's a LazyFrame, collect it
                try:
                    self.original_df = source.collect()
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
                self.original_df = source
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
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
            if self._is_same_error_type(e):
                logger.debug("First operation fails, returning index 0")
                return 0, self._get_operation_at(0), self.original_df

        # Early termination: check if all operations succeed
        try:
            final_df = self._apply_operations_up_to(len(operations) - 1)
        except BaseException as e:  # panic-aware probe, guarded below
            if not _replayable(e):
                raise
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
        last_good_index = -1
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
                last_good_index = mid
                left = mid + 1
                logger.trace(f"Operations 0-{mid} succeeded, searching right half")
            except BaseException as e:  # panic-aware probe, guarded below
                if not _replayable(e):
                    raise
                if self._is_same_error_type(e):
                    # Error at or before this point
                    failing_index = mid
                    right = mid - 1
                    logger.trace(
                        f"Ops 0-{mid} failed with same error, searching left",
                    )
                else:
                    # Different error type, continue searching right
                    if mid > 0:
                        try:
                            last_good_df = self._apply_operations_up_to(mid - 1)
                            last_good_index = mid - 1
                        except (
                            BaseException
                        ) as retry_error:  # panic-aware probe, guarded below
                            if not _replayable(retry_error):
                                raise
                            last_good_df = self.original_df
                            last_good_index = -1
                    else:
                        last_good_df = self.original_df
                        last_good_index = -1
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
                last_good_index,
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
        last_good_index: int = -1,
    ) -> int:
        """Find the exact failing operation from a known-good prefix.

        Args:
            start_index: Index at or before which failure is known to occur.
            last_good_df: DataFrame with ops ``0..last_good_index`` applied.
            last_good_index: Largest op index already contained in
                ``last_good_df`` (``-1`` when it is the pristine baseline).
                The scan applies ops strictly AFTER this index — re-applying
                an op already present double-applies it, and a valid
                self-referential dtype-changing assignment then raises on
                its second application and gets blamed for another
                column's error.

        Returns:
            Exact index of failing operation.

        """
        operations = self.af._computation_graph  # noqa: SLF001
        current_df = last_good_df.lazy()  # Convert to LazyFrame for operations

        for i in range(last_good_index + 1, len(operations)):
            operation = self._get_operation_at(i)
            if operation is None:
                continue

            if isinstance(operation, tuple):
                alias, expr = operation
            else:
                alias, expr = operation.alias, operation.expression

            current_df = current_df.with_columns(expr.alias(alias))
            try:
                # Test by collecting to see if it fails
                _ = current_df.collect()
                logger.trace(f"Operation {i} ({alias}) succeeded")
            except BaseException as e:  # panic-aware probe, guarded below
                if not _replayable(e):
                    raise
                if self._is_same_error_type(e):
                    logger.debug(f"Exact failing operation found at index {i}")
                    return i
                # The plan now carries a different failure; every later
                # prefix would just re-raise it, so stop refining.
                logger.trace(f"Different error type at operation {i}, stopping")
                break

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

    def _is_same_error_type(self, exception: BaseException) -> bool:
        """Check if the given exception is the same type as the original error.

        Args:
            exception: Exception to check

        Returns:
            True if exception types match

        """
        return isinstance(exception, self.exception_type)


# Error classes eligible for collect-time column attribution (#39). Kept
# narrow deliberately: these are data-shape failures that reproduce
# deterministically under replay. A wrong column name costs the user more
# than no column name, so anything outside this list passes through.
_ATTRIBUTABLE_ERRORS = (
    pl.exceptions.ShapeError,
    pl.exceptions.InvalidOperationError,
    pl.exceptions.SchemaError,
)

# Replay baseline row cap. Attribution re-collects real data several times;
# uncapped, a 100K-policy failure would multiply the failed run's full cost
# on the error path (the edit-run-refine loop principle). Shape failures
# overwhelmingly reproduce within the head; one that does not simply yields
# no attribution.
_REPLAY_MAX_ROWS = 10_000


class _AttributionReplayFinder(ErrorBoundaryFinder):
    """Stricter finder for default-mode collect attribution (#39).

    Class-only matching can pair column A's name with column B's message
    when two operations raise the same exception class. Attribution
    therefore also requires the first line of the replayed message to match
    the original's — a mismatch means "not certainly the same failure",
    which per the fallback contract yields no attribution rather than a
    self-contradictory one.
    """

    def _is_same_error_type(self, exception: BaseException) -> bool:
        if not isinstance(exception, self.exception_type):
            return False
        original = str(self.exception).split("\n", 1)[0]
        replayed = str(exception).split("\n", 1)[0]
        return original == replayed


def attribute_collect_failure(
    af: ActuarialFrame,
    exception: BaseException,
) -> tuple[str, str] | None:
    """Name the recorded assignment that reproduces a collect-time failure.

    Replays the frame's recorded assignments against the pristine baseline
    (row-capped, via :class:`_AttributionReplayFinder`) until one reproduces
    the same error class AND leading message. Returns
    ``(column_name, expression_string)`` for the first failing assignment,
    or ``None`` whenever attribution is not certain — unknown error class,
    empty or unsound graph, a replay that does not reproduce the error, or
    any failure inside the replay itself. Callers must treat ``None`` as
    "re-raise the original error untouched".

    Replay never mutates the live frame: the finder works on eager copies
    collected from the baseline plan.

    Args:
        af: The frame whose ``collect()``/``profile()`` raised.
        exception: The exception raised by the failed execution.

    Returns:
        ``(column_name, expression_string)`` or ``None``.

    """
    if not (
        isinstance(exception, _ATTRIBUTABLE_ERRORS) or is_plan_lowering_panic(exception)
    ):
        return None
    if not getattr(af, "_computation_graph", None):
        return None
    if getattr(af, "_attribution_unsound", False):
        # The live plan diverged from baseline + graph (an unrecorded
        # mutation on a graph that had to be kept) — replaying would risk
        # naming the wrong column.
        return None
    try:
        finder = _AttributionReplayFinder(af, exception, max_rows=_REPLAY_MAX_ROWS)
        _, failing_op, _ = finder.find_failing_operation()
    except BaseException as replay_error:  # never make the error worse
        if not _replayable(replay_error):
            raise
        logger.debug("Collect-error attribution replay failed; passing through")
        return None
    if failing_op is None:
        return None
    if isinstance(failing_op, tuple):
        alias, expr = failing_op
    else:
        alias, expr = failing_op.alias, failing_op.expression
    return alias, str(expr)
