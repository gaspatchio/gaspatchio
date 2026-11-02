# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for error boundary detection using binary search.

The finder searches a frame's attribution window -- the calculations
recorded since the last known-good point -- grouped into the operations
that produced them. One setter assignment is one operation of one column; a
multi-column ``with_columns`` is one operation of several, and replay has to
apply it whole because that is how Polars evaluated it.
"""

from dataclasses import dataclass
from unittest.mock import patch

import polars as pl
from polars.exceptions import ColumnNotFoundError

from gaspatchio._semantic.ir import Col
from gaspatchio.errors.boundary import ErrorBoundaryFinder, group_by_operation
from gaspatchio.frame.calculations import CalculationRecord


@dataclass
class MockActuarialFrame:
    """Stand-in for the attribution surface a finder consumes.

    Two things and no more: the window of recorded calculations, and the
    plan they replay from. ``_baseline_df`` is deliberately absent so the
    finder falls back to ``_df``, which is the pristine input here.
    """

    _df: pl.DataFrame
    _window: list[CalculationRecord]
    _traced_run: bool = True

    def _attribution_ops(self) -> list[CalculationRecord]:
        return self._window


def _calculation(
    column: str,
    expr: pl.Expr,
    operation_id: int,
    ordinal: int = 1,
) -> CalculationRecord:
    """Build one recorded calculation, as the frame's log would hold it."""
    return CalculationRecord(
        column=column,
        ordinal=ordinal,
        operation_id=operation_id,
        node=Col(column),
        expr=expr,
        dtype=None,
        source=None,
        origin="assignment",
    )


def _window(*definitions: tuple[str, pl.Expr]) -> list[CalculationRecord]:
    """Build a window of single-column assignments, one operation each."""
    return [
        _calculation(column, expr, operation_id)
        for operation_id, (column, expr) in enumerate(definitions)
    ]


def _batch(
    operation_id: int,
    *definitions: tuple[str, pl.Expr],
) -> list[CalculationRecord]:
    """Build the records one multi-column ``with_columns`` would produce."""
    return [_calculation(column, expr, operation_id) for column, expr in definitions]


def _policy_data() -> pl.DataFrame:
    """Three policies carrying the one input column these tests calculate from."""
    return pl.DataFrame({"sum_assured": [1, 2, 3]})


class TestGroupByOperation:
    """Records are grouped by the call that produced them, never by adjacency."""

    def test_consecutive_assignments_are_separate_operations(self):
        """Two setter assignments are two operations of one column each."""
        window = _window(
            ("death_claims", pl.col("sum_assured") * 2),
            ("expenses", pl.col("sum_assured") + 1),
        )

        groups = group_by_operation(window)

        assert [[record.column for record in group] for group in groups] == [
            ["death_claims"],
            ["expenses"],
        ]

    def test_a_shared_operation_id_makes_one_group(self):
        """Every column a single with_columns defined replays together."""
        window = _batch(
            0,
            ("death_claims", pl.col("sum_assured") * 2),
            ("expenses", pl.col("sum_assured") + 1),
        )

        groups = group_by_operation(window)

        assert len(groups) == 1
        assert [record.column for record in groups[0]] == ["death_claims", "expenses"]

    def test_an_empty_window_has_no_operations(self):
        """Nothing recorded, nothing to replay."""
        assert group_by_operation([]) == []


class TestErrorBoundaryFinder:
    """Test ErrorBoundaryFinder class."""

    def test_init(self):
        """Test ErrorBoundaryFinder initialization."""
        df = _policy_data()
        af = MockActuarialFrame(_df=df, _window=[])
        exception = ValueError("test error")

        finder = ErrorBoundaryFinder(af, exception)

        assert finder.af is af
        assert finder.exception is exception
        assert finder.original_df is df
        assert finder.exception_type is ValueError

    def test_empty_attribution_window(self):
        """Test with an empty attribution window."""
        df = _policy_data()
        af = MockActuarialFrame(_df=df, _window=[])
        exception = ValueError("test error")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == -1
        assert operation is None
        assert last_df is df

    def test_first_operation_fails(self):
        """Test when the first recorded calculation fails."""
        df = _policy_data()

        # Reads a column no policy carries
        window = _window(("death_claims", pl.col("mortality_rate") * 2))

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 0
        assert operation is window[0]
        assert operation.column == "death_claims"
        assert last_df is df

    def test_the_named_record_carries_its_own_source_and_ordinal(self):
        """Replay lands on a record, not merely on a column name."""
        df = _policy_data()

        window = _window(("death_claims", pl.col("mortality_rate") * 2))
        window[0].ordinal = 3

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        _, operation, _ = ErrorBoundaryFinder(af, exception).find_failing_operation()

        assert operation.ordinal == 3

    def test_middle_operation_fails(self):
        """Test when middle operation fails."""
        df = _policy_data()

        window = _window(
            # Succeeds, giving 2, 4 and 6
            ("death_claims", pl.col("sum_assured") * 2),
            # Succeeds, giving 2, 3 and 4
            ("expenses", pl.col("sum_assured") + 1),
            # Fails: column 'mortality_rate' not found
            ("reserves", pl.col("mortality_rate") * 3),
            # Would succeed if reached
            ("surrender_value", pl.col("sum_assured") / 2),
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 2
        assert operation.column == "reserves"

        # Verify last_df contains the successful operations
        expected_cols = {"sum_assured", "death_claims", "expenses"}
        assert set(last_df.columns) == expected_cols
        assert last_df["death_claims"].to_list() == [2, 4, 6]
        assert last_df["expenses"].to_list() == [2, 3, 4]

    def test_last_operation_fails(self):
        """Test when last operation fails."""
        df = _policy_data()

        window = _window(
            ("death_claims", pl.col("sum_assured") * 2),
            ("expenses", pl.col("sum_assured") + 1),
            ("reserves", pl.col("mortality_rate") * 3),  # Last operation fails
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 2
        assert operation.column == "reserves"

        # Verify last_df contains all successful operations
        expected_cols = {"sum_assured", "death_claims", "expenses"}
        assert set(last_df.columns) == expected_cols

    def test_all_operations_succeed(self):
        """Test when all operations succeed (no failure to find)."""
        df = _policy_data()

        window = _window(
            ("death_claims", pl.col("sum_assured") * 2),
            ("expenses", pl.col("sum_assured") + 1),
            ("surrender_value", pl.col("sum_assured") / 2),
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ValueError("some other error")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == -1
        assert operation is None

        # Should return final DataFrame with all operations applied
        expected_cols = {
            "sum_assured",
            "death_claims",
            "expenses",
            "surrender_value",
        }
        assert set(last_df.columns) == expected_cols

    def test_different_error_types(self):
        """Test handling of different error types."""
        df = _policy_data()

        window = _window(
            # Division that might cause issues
            ("loss_ratio", pl.col("sum_assured") / pl.col("sum_assured")),
            ("reserves", pl.col("mortality_rate")),  # Column not found
        )

        af = MockActuarialFrame(_df=df, _window=window)
        # Look for column error, but other errors might occur
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 1  # Should find the column not found error
        assert operation.column == "reserves"

    def test_large_window_performance(self):
        """Test performance with a large attribution window (100+ operations)."""
        df = _policy_data()

        # Create 150 operations, with failure at position 75
        definitions = [
            ("reserves", pl.col("mortality_rate"))
            if i == 75
            else (f"cashflow_month_{i}", pl.col("sum_assured") + i)
            for i in range(150)
        ]
        window = _window(*definitions)

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)

        # Time the operation (should be much faster than linear search)
        import time

        start_time = time.time()
        index, operation, last_df = finder.find_failing_operation()
        elapsed = time.time() - start_time

        assert index == 75
        assert operation.column == "reserves"
        # Should find error in reasonable time (binary search advantage)
        assert elapsed < 1.0  # Should be much faster than 1 second

        # Verify operations 0-74 applied
        assert len(last_df.columns) == 76  # sum_assured + 75 new columns

    def test_edge_case_single_operation(self):
        """Test edge case with single operation."""
        df = _policy_data()

        window = _window(("death_claims", pl.col("mortality_rate")))

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 0
        assert operation.column == "death_claims"
        assert last_df is df

    def test_edge_case_two_operations_first_fails(self):
        """Test edge case with two operations where first fails."""
        df = _policy_data()

        window = _window(
            ("death_claims", pl.col("mortality_rate")),  # Fails
            ("expenses", pl.col("sum_assured") * 2),  # Would succeed
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 0
        assert operation.column == "death_claims"
        assert last_df is df

    def test_edge_case_two_operations_second_fails(self):
        """Test edge case with two operations where second fails."""
        df = _policy_data()

        window = _window(
            ("death_claims", pl.col("sum_assured") * 2),  # Succeeds
            ("reserves", pl.col("mortality_rate")),  # Fails
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 1
        assert operation.column == "reserves"
        assert "death_claims" in last_df.columns

    def test_apply_operations_up_to_negative_index(self):
        """Test _apply_operations_up_to with negative index."""
        df = _policy_data()
        window = _window(("death_claims", pl.col("sum_assured") * 2))

        af = MockActuarialFrame(_df=df, _window=window)
        finder = ErrorBoundaryFinder(af, ValueError())

        result = finder._apply_operations_up_to(-1)
        assert result is df

    def test_apply_operations_up_to_index_too_large(self):
        """Test _apply_operations_up_to with index larger than the window."""
        df = _policy_data()
        window = _window(("death_claims", pl.col("sum_assured") * 2))

        af = MockActuarialFrame(_df=df, _window=window)
        finder = ErrorBoundaryFinder(af, ValueError())

        result = finder._apply_operations_up_to(10)  # Much larger than the window
        assert "death_claims" in result.columns

    def test_get_operation_at_bounds_checking(self):
        """Test _get_operation_at with various indices."""
        df = _policy_data()
        window = _window(
            ("death_claims", pl.col("sum_assured") * 2),
            ("expenses", pl.col("sum_assured") + 1),
        )

        af = MockActuarialFrame(_df=df, _window=window)
        finder = ErrorBoundaryFinder(af, ValueError())

        # Valid indices
        assert [record.column for record in finder._get_operation_at(0)] == [
            "death_claims",
        ]
        assert [record.column for record in finder._get_operation_at(1)] == ["expenses"]

        # Invalid indices
        assert finder._get_operation_at(-1) is None
        assert finder._get_operation_at(2) is None
        assert finder._get_operation_at(100) is None

    def test_is_same_error_type(self):
        """Test _is_same_error_type method."""
        df = _policy_data()
        af = MockActuarialFrame(_df=df, _window=[])

        original_error = ValueError("original")
        finder = ErrorBoundaryFinder(af, original_error)

        # Same type
        assert finder._is_same_error_type(ValueError("different message"))

        # Different types
        assert not finder._is_same_error_type(TypeError("different type"))
        assert not finder._is_same_error_type(ColumnNotFoundError("polars error"))

    def test_complex_error_scenario(self):
        """Test complex scenario with multiple operations and edge cases."""
        df = pl.DataFrame(
            {
                "sum_assured": [1, 2, 3],
                "annual_premium": [4, 5, 6],
            },
        )

        # Complex sequence of operations
        window = _window(
            # Valid, giving 5, 7 and 9
            ("total_exposure", pl.col("sum_assured") + pl.col("annual_premium")),
            # Valid, giving 0.25, 0.4 and 0.5
            ("premium_ratio", pl.col("sum_assured") / pl.col("annual_premium")),
            # Valid: uses a previous result
            ("weighted_exposure", pl.col("sum_assured") * pl.col("total_exposure")),
            # Valid but might have issues with 0
            ("log_exposure", pl.col("sum_assured").log()),
            # Invalid: column doesn't exist
            ("reserves", pl.col("mortality_rate") + 1),
            # Would work if reached
            ("net_cashflow", pl.col("sum_assured") - 1),
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 4  # The reserves operation
        assert operation.column == "reserves"

        # Verify all previous operations were applied
        expected_cols = {
            "sum_assured",
            "annual_premium",
            "total_exposure",
            "premium_ratio",
            "weighted_exposure",
            "log_exposure",
        }
        assert set(last_df.columns) == expected_cols

    @patch("gaspatchio.errors.boundary.logger")
    def test_logging_behavior(self, mock_logger):
        """Test that appropriate logging occurs during binary search."""
        df = _policy_data()

        window = _window(
            ("death_claims", pl.col("sum_assured") * 2),
            ("reserves", pl.col("mortality_rate")),  # Fails
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        finder.find_failing_operation()

        # Verify debug logging occurred
        mock_logger.debug.assert_called()

        # Check that binary search start was logged
        debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
        assert any("Starting binary search" in call for call in debug_calls)

    def test_memory_efficiency(self):
        """Test that DataFrame copies are handled efficiently."""
        # Create a larger DataFrame to test memory handling
        df = pl.DataFrame(
            {
                "sum_assured": list(range(1000)),
                "annual_premium": list(range(1000, 2000)),
            },
        )

        window = _window(
            ("total_exposure", pl.col("sum_assured") + pl.col("annual_premium")),
            ("death_claims", pl.col("sum_assured") * 2),
            ("reserves", pl.col("mortality_rate")),  # Fails
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = ColumnNotFoundError("column 'mortality_rate' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 2
        assert operation.column == "reserves"

        # Verify the DataFrame operations worked correctly with larger data
        assert len(last_df) == 1000
        assert set(last_df.columns) == {
            "sum_assured",
            "annual_premium",
            "total_exposure",
            "death_claims",
        }

    def test_operation_with_none_result(self):
        """Test handling when _get_operation_at returns None."""
        df = _policy_data()
        af = MockActuarialFrame(_df=df, _window=[])
        finder = ErrorBoundaryFinder(af, ValueError())

        # Mock _get_operation_at to return None
        with patch.object(finder, "_get_operation_at", return_value=None):
            result = finder._apply_operations_up_to(0)
            assert result is df  # Should return original DataFrame


class TestMultiColumnOperations:
    """A ``with_columns`` batch replays whole, then narrows to one column."""

    def _ragged_frame(self) -> pl.DataFrame:
        """One policy whose projection columns differ in length on purpose."""
        return pl.DataFrame(
            {
                "policy_id": [1],
                "six_periods": [[1.0] * 6],
                "three_periods": [[1.0] * 3],
                "accumulator": [[9.0] * 3],
            },
        )

    def test_a_batch_replays_as_one_with_columns(self):
        """A sibling reading a batch-mate's OLD value is never blamed.

        ``accumulator`` widens to six periods and ``surrender_value`` reads
        it -- but in one ``with_columns`` every expression sees the frame as
        it stood before the call, so ``surrender_value`` gets the old
        three-period ``accumulator`` and is healthy. Replaying the two
        sequentially would hand it the new six-period value, reproduce a
        length mismatch, and blame it.
        """
        df = self._ragged_frame()
        window = [
            *_batch(
                0,
                ("accumulator", pl.col("six_periods")),
                (
                    "surrender_value",
                    pl.col("accumulator") - pl.col("three_periods"),
                ),
            ),
            *_window(
                ("death_claims", pl.col("six_periods") - pl.col("three_periods")),
            ),
        ]
        # _window numbers from zero; the trailing assignment is its own call.
        window[-1].operation_id = 1

        af = MockActuarialFrame(_df=df, _window=window)
        exception = pl.exceptions.ShapeError("lengths differed")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, _ = finder.find_failing_operation()

        assert index == 1
        assert operation.column == "death_claims"

    def test_the_failing_column_of_a_batch_is_named_alone(self):
        """Narrowing inside a batch still applies one ``with_columns``."""
        df = self._ragged_frame()
        window = _batch(
            0,
            ("healthy_reserve", pl.col("six_periods") * 2.0),
            ("death_claims", pl.col("six_periods") - pl.col("three_periods")),
        )

        af = MockActuarialFrame(_df=df, _window=window)
        exception = pl.exceptions.ShapeError("lengths differed")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, _ = finder.find_failing_operation()

        assert index == 0
        assert operation.column == "death_claims"

    def test_two_consecutive_single_expression_batches_replay_in_order(self):
        """Separate calls replay separately: the second sees the first's output."""
        df = self._ragged_frame()
        window = [
            *_batch(0, ("accumulator", pl.col("six_periods"))),
            *_batch(
                1,
                ("death_claims", pl.col("accumulator") - pl.col("three_periods")),
            ),
        ]

        af = MockActuarialFrame(_df=df, _window=window)
        exception = pl.exceptions.ShapeError("lengths differed")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, _ = finder.find_failing_operation()

        # The second call reads the widened accumulator, so it genuinely
        # fails -- unlike the same two expressions inside ONE call.
        assert index == 1
        assert operation.column == "death_claims"
