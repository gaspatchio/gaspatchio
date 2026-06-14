# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for error boundary detection using binary search."""

from dataclasses import dataclass
from unittest.mock import patch

import polars as pl
from polars.exceptions import ColumnNotFoundError

from gaspatchio_core.errors.boundary import ErrorBoundaryFinder
from gaspatchio_core.errors.metadata import OperationMetadata, TracedOperation


@dataclass
class MockActuarialFrame:
    """Mock ActuarialFrame for testing."""

    _df: pl.DataFrame
    _computation_graph: list
    _tracing: bool = True


class TestErrorBoundaryFinder:
    """Test ErrorBoundaryFinder class."""

    def test_init(self):
        """Test ErrorBoundaryFinder initialization."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        af = MockActuarialFrame(_df=df, _computation_graph=[])
        exception = ValueError("test error")

        finder = ErrorBoundaryFinder(af, exception)

        assert finder.af is af
        assert finder.exception is exception
        assert finder.original_df is df
        assert finder.exception_type is ValueError

    def test_empty_computation_graph(self):
        """Test with empty computation graph."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        af = MockActuarialFrame(_df=df, _computation_graph=[])
        exception = ValueError("test error")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == -1
        assert operation is None
        assert last_df is df

    def test_first_operation_fails_tuple_format(self):
        """Test when first operation fails using tuple format."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        # Create operation that will fail (column 'b' doesn't exist)
        failing_expr = pl.col("b") * 2
        operations = [("result", failing_expr)]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'b' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 0
        assert isinstance(operation, tuple)
        assert operation[0] == "result"  # Check alias
        assert last_df is df

    def test_first_operation_fails_traced_format(self):
        """Test when first operation fails using TracedOperation format."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        # Create operation that will fail
        failing_expr = pl.col("b") * 2
        metadata = OperationMetadata(
            file_name="test.py",
            line_number=10,
            source_line="af['result'] = af['b'] * 2",
        )
        operation = TracedOperation(
            alias="result",
            expression=failing_expr,
            metadata=metadata,
        )

        af = MockActuarialFrame(_df=df, _computation_graph=[operation])
        exception = ColumnNotFoundError("column 'b' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, found_op, last_df = finder.find_failing_operation()

        assert index == 0
        assert found_op is operation
        assert last_df is df

    def test_middle_operation_fails(self):
        """Test when middle operation fails."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("a") * 2),  # Should succeed: b = [2, 4, 6]
            ("c", pl.col("a") + 1),  # Should succeed: c = [2, 3, 4]
            ("d", pl.col("missing") * 3),  # Should fail: column 'missing' not found
            ("e", pl.col("a") / 2),  # Would succeed if reached
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 2
        assert isinstance(operation, tuple)
        assert operation[0] == "d"  # Check alias

        # Verify last_df contains the successful operations
        expected_cols = {"a", "b", "c"}
        assert set(last_df.columns) == expected_cols
        assert last_df["b"].to_list() == [2, 4, 6]
        assert last_df["c"].to_list() == [2, 3, 4]

    def test_last_operation_fails(self):
        """Test when last operation fails."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("a") * 2),
            ("c", pl.col("a") + 1),
            ("d", pl.col("missing") * 3),  # Last operation fails
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 2
        assert isinstance(operation, tuple)
        assert operation[0] == "d"  # Check alias

        # Verify last_df contains all successful operations
        expected_cols = {"a", "b", "c"}
        assert set(last_df.columns) == expected_cols

    def test_all_operations_succeed(self):
        """Test when all operations succeed (no failure to find)."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("a") * 2),
            ("c", pl.col("a") + 1),
            ("d", pl.col("a") / 2),
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ValueError("some other error")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == -1
        assert operation is None

        # Should return final DataFrame with all operations applied
        expected_cols = {"a", "b", "c", "d"}
        assert set(last_df.columns) == expected_cols

    def test_different_error_types(self):
        """Test handling of different error types."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("a") / pl.col("a")),  # Division that might cause issues
            ("c", pl.col("missing")),  # Column not found
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        # Look for column error, but other errors might occur
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 1  # Should find the column not found error
        assert isinstance(operation, tuple)
        assert operation[0] == "c"  # Check alias

    def test_mixed_operation_formats(self):
        """Test with mixed tuple and TracedOperation formats."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        # Mix of formats
        metadata = OperationMetadata(
            file_name="test.py",
            line_number=15,
            source_line="af['c'] = af['missing']",
        )
        traced_op = TracedOperation(
            alias="c",
            expression=pl.col("missing"),
            metadata=metadata,
        )

        operations = [
            ("b", pl.col("a") * 2),  # Tuple format
            traced_op,  # TracedOperation format
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 1
        assert operation is traced_op
        assert "b" in last_df.columns

    def test_large_graph_performance(self):
        """Test performance with large computation graph (100+ operations)."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        # Create 150 operations, with failure at position 75
        operations = []
        for i in range(150):
            if i == 75:
                # Insert failing operation
                operations.append((f"col_{i}", pl.col("missing")))
            else:
                # Valid operations
                operations.append((f"col_{i}", pl.col("a") + i))

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)

        # Time the operation (should be much faster than linear search)
        import time

        start_time = time.time()
        index, operation, last_df = finder.find_failing_operation()
        elapsed = time.time() - start_time

        assert index == 75
        assert isinstance(operation, tuple)
        assert operation[0] == "col_75"  # Check alias
        # Should find error in reasonable time (binary search advantage)
        assert elapsed < 1.0  # Should be much faster than 1 second

        # Verify we have operations 0-74 applied
        assert len(last_df.columns) == 76  # Original 'a' + 75 new columns

    def test_edge_case_single_operation(self):
        """Test edge case with single operation."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [("b", pl.col("missing"))]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 0
        assert isinstance(operation, tuple)
        assert operation[0] == "b"  # Check alias
        assert last_df is df

    def test_edge_case_two_operations_first_fails(self):
        """Test edge case with two operations where first fails."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("missing")),  # Fails
            ("c", pl.col("a") * 2),  # Would succeed
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 0
        assert isinstance(operation, tuple)
        assert operation[0] == "b"  # Check alias
        assert last_df is df

    def test_edge_case_two_operations_second_fails(self):
        """Test edge case with two operations where second fails."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("a") * 2),  # Succeeds
            ("c", pl.col("missing")),  # Fails
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 1
        assert isinstance(operation, tuple)
        assert operation[0] == "c"  # Check alias
        assert "b" in last_df.columns

    def test_apply_operations_up_to_negative_index(self):
        """Test _apply_operations_up_to with negative index."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        operations = [("b", pl.col("a") * 2)]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        finder = ErrorBoundaryFinder(af, ValueError())

        result = finder._apply_operations_up_to(-1)
        assert result is df

    def test_apply_operations_up_to_index_too_large(self):
        """Test _apply_operations_up_to with index larger than graph."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        operations = [("b", pl.col("a") * 2)]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        finder = ErrorBoundaryFinder(af, ValueError())

        result = finder._apply_operations_up_to(10)  # Much larger than graph size
        assert "b" in result.columns

    def test_get_operation_at_bounds_checking(self):
        """Test _get_operation_at with various indices."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        operations = [("b", pl.col("a") * 2), ("c", pl.col("a") + 1)]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        finder = ErrorBoundaryFinder(af, ValueError())

        # Valid indices
        op0 = finder._get_operation_at(0)
        op1 = finder._get_operation_at(1)
        assert isinstance(op0, tuple) and op0[0] == "b"
        assert isinstance(op1, tuple) and op1[0] == "c"

        # Invalid indices
        assert finder._get_operation_at(-1) is None
        assert finder._get_operation_at(2) is None
        assert finder._get_operation_at(100) is None

    def test_is_same_error_type(self):
        """Test _is_same_error_type method."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        af = MockActuarialFrame(_df=df, _computation_graph=[])

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
                "a": [1, 2, 3],
                "b": [4, 5, 6],
            },
        )

        # Complex sequence of operations
        operations = [
            ("sum_ab", pl.col("a") + pl.col("b")),  # Valid: [5, 7, 9]
            ("ratio", pl.col("a") / pl.col("b")),  # Valid: [0.25, 0.4, 0.5]
            ("product", pl.col("a") * pl.col("sum_ab")),  # Valid: uses previous result
            ("log_a", pl.col("a").log()),  # Valid but might have issues with 0
            ("bad_ref", pl.col("nonexistent") + 1),  # Invalid: column doesn't exist
            ("would_work", pl.col("a") - 1),  # Would work if reached
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'nonexistent' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 4  # The bad_ref operation
        assert isinstance(operation, tuple)
        assert operation[0] == "bad_ref"  # Check alias

        # Verify all previous operations were applied
        expected_cols = {"a", "b", "sum_ab", "ratio", "product", "log_a"}
        assert set(last_df.columns) == expected_cols

    @patch("gaspatchio_core.errors.boundary.logger")
    def test_logging_behavior(self, mock_logger):
        """Test that appropriate logging occurs during binary search."""
        df = pl.DataFrame({"a": [1, 2, 3]})

        operations = [
            ("b", pl.col("a") * 2),
            ("c", pl.col("missing")),  # Fails
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

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
                "a": list(range(1000)),
                "b": list(range(1000, 2000)),
            },
        )

        operations = [
            ("c", pl.col("a") + pl.col("b")),
            ("d", pl.col("a") * 2),
            ("e", pl.col("missing")),  # Fails
        ]

        af = MockActuarialFrame(_df=df, _computation_graph=operations)
        exception = ColumnNotFoundError("column 'missing' does not exist")

        finder = ErrorBoundaryFinder(af, exception)
        index, operation, last_df = finder.find_failing_operation()

        assert index == 2
        assert isinstance(operation, tuple)
        assert operation[0] == "e"  # Check alias

        # Verify the DataFrame operations worked correctly with larger data
        assert len(last_df) == 1000
        assert set(last_df.columns) == {"a", "b", "c", "d"}

    def test_operation_with_none_result(self):
        """Test handling when _get_operation_at returns None."""
        df = pl.DataFrame({"a": [1, 2, 3]})
        af = MockActuarialFrame(_df=df, _computation_graph=[])
        finder = ErrorBoundaryFinder(af, ValueError())

        # Mock _get_operation_at to return None
        with patch.object(finder, "_get_operation_at", return_value=None):
            result = finder._apply_operations_up_to(0)
            assert result is df  # Should return original DataFrame
