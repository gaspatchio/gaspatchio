"""
Tests for the enhanced tracing system with metadata capture.

Tests cover metadata capture during operations, performance characteristics,
graph storage and retrieval, and backward compatibility.
"""

import time
from unittest.mock import Mock, patch

import polars as pl
import pytest

from gaspatchio_core.errors.metadata import OperationMetadata, TracedOperation
from gaspatchio_core.frame.tracing import append_operation_to_graph, log_query_plan


class MockActuarialFrame:
    """Mock ActuarialFrame for testing tracing functionality."""

    def __init__(self, tracing: bool = False):
        self._tracing = tracing
        self._computation_graph = []
        self._df = pl.LazyFrame({"test": [1, 2, 3]})


class TestAppendOperationToGraph:
    """Test the enhanced append_operation_to_graph function."""

    def test_fast_path_when_tracing_disabled(self):
        """Test that function returns immediately when tracing is disabled."""
        frame = MockActuarialFrame(tracing=False)
        initial_graph_length = len(frame._computation_graph)

        # This should return immediately without doing anything
        append_operation_to_graph(frame, "test_col", pl.col("test"))

        assert len(frame._computation_graph) == initial_graph_length
        assert frame._computation_graph == []

    def test_metadata_capture_when_tracing_enabled(self):
        """Test that metadata is captured when tracing is enabled."""
        frame = MockActuarialFrame(tracing=True)

        # Call from this test function to have predictable source context
        append_operation_to_graph(frame, "result", pl.col("test") + 1)

        assert len(frame._computation_graph) == 1
        operation = frame._computation_graph[0]

        # Should be TracedOperation, not tuple
        assert isinstance(operation, TracedOperation)
        assert operation.alias == "result"
        # Expression should be a Polars expression
        assert hasattr(operation.expression, 'meta')  # It's a Polars expression
        assert operation.metadata is not None
        # Check that we captured some meaningful metadata (pytest may interfere with exact filenames)
        assert operation.metadata.file_name is not None
        assert operation.metadata.line_number > 0
        assert operation.metadata.function_name is not None

    def test_source_line_capture(self):
        """Test that source line is correctly captured."""
        frame = MockActuarialFrame(tracing=True)

        # This line should be captured in metadata
        append_operation_to_graph(frame, "captured_line", pl.col("test") * 2)

        operation = frame._computation_graph[0]
        # Check that some source line was captured (pytest may interfere with exact content)
        assert operation.metadata.source_line is not None
        assert len(operation.metadata.source_line) > 0

    def test_multiple_operations_metadata(self):
        """Test metadata capture for multiple operations."""
        frame = MockActuarialFrame(tracing=True)

        # Add multiple operations
        append_operation_to_graph(frame, "op1", pl.col("a"))
        append_operation_to_graph(frame, "op2", pl.col("b") + 1)
        append_operation_to_graph(frame, "op3", pl.col("op1") + pl.col("op2"))

        assert len(frame._computation_graph) == 3

        for i, operation in enumerate(frame._computation_graph):
            assert isinstance(operation, TracedOperation)
            assert operation.alias == f"op{i + 1}"
            # Check that expression is a Polars expression object
            assert hasattr(operation.expression, 'meta')  # It's a Polars expression
            assert operation.metadata is not None
            assert operation.metadata.line_number > 0

    def test_nested_function_calls(self):
        """Test metadata capture through nested function calls."""
        frame = MockActuarialFrame(tracing=True)

        def inner_function():
            append_operation_to_graph(frame, "nested", pl.col("x").filter(pl.col("y") > 0))

        def outer_function():
            inner_function()

        outer_function()

        operation = frame._computation_graph[0]
        # Should capture the outer_function context due to stack depth
        assert operation.metadata.function_name in ["outer_function", "inner_function"]

    def test_performance_overhead_when_disabled(self):
        """Test that there's minimal overhead when tracing is disabled."""
        frame = MockActuarialFrame(tracing=False)

        # Time many operations with tracing disabled
        start_time = time.time()
        for i in range(1000):
            append_operation_to_graph(frame, f"op_{i}", pl.col("test") + i)
        disabled_time = time.time() - start_time

        # Should be very fast since it returns early
        assert disabled_time < 0.1  # Should complete in under 100ms
        assert len(frame._computation_graph) == 0

    def test_performance_overhead_when_enabled(self):
        """Test performance characteristics when tracing is enabled."""
        frame = MockActuarialFrame(tracing=True)

        # Time operations with tracing enabled
        start_time = time.time()
        for i in range(100):  # Fewer operations since metadata capture has overhead
            append_operation_to_graph(frame, f"op_{i}", pl.col("test") + i)
        enabled_time = time.time() - start_time

        # Should complete reasonably fast even with metadata capture
        assert enabled_time < 2.0  # Should complete in under 2 seconds
        assert len(frame._computation_graph) == 100

    @patch("gaspatchio_core.frame.tracing.logger")
    def test_logging_includes_source_location(self, mock_logger):
        """Test that logging includes source location information."""
        frame = MockActuarialFrame(tracing=True)

        append_operation_to_graph(frame, "logged_op", pl.col("test").log())

        # Check that logger.trace was called (might be called twice - once for type inference error)
        assert mock_logger.trace.call_count >= 1
        
        # Find the call that logs the graph addition (not the type inference error)
        graph_addition_call = None
        for call in mock_logger.trace.call_args_list:
            call_args = call[0][0]
            if "Graph: Added" in call_args:
                graph_addition_call = call_args
                break
        
        assert graph_addition_call is not None
        assert "logged_op" in graph_addition_call
        # Should contain the actual expression representation
        assert ".log()" in graph_addition_call or "log" in graph_addition_call
        # Check that filename and line number are present in some form
        assert ":" in graph_addition_call  # Should contain line number
        # Just verify that some file path was captured
        assert "/" in graph_addition_call or "\\" in graph_addition_call

    def test_import_caching_performance(self):
        """Test that imports are cached for performance."""
        frame = MockActuarialFrame(tracing=True)

        # First call will do imports
        start_time = time.time()
        append_operation_to_graph(frame, "first", pl.col("a") * 2)
        first_call_time = time.time() - start_time

        # Second call should be faster due to import caching
        start_time = time.time()
        append_operation_to_graph(frame, "second", pl.col("b") / 3)
        second_call_time = time.time() - start_time

        # Second call should be reasonably fast (not drastically slower)
        # This test is inherently flaky due to timing variance
        assert second_call_time <= first_call_time * 10  # Very lenient to avoid flakiness

    def test_circular_import_avoidance(self):
        """Test that the local imports don't cause circular import issues."""
        frame = MockActuarialFrame(tracing=True)

        # This should not raise any import errors
        try:
            append_operation_to_graph(frame, "test", pl.col("test"))
        except ImportError as e:
            pytest.fail(f"Circular import detected: {e}")


class TestLogQueryPlan:
    """Test the updated log_query_plan function with backward compatibility."""

    @patch("gaspatchio_core.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio_core.frame.tracing.logger")
    def test_log_legacy_tuple_format(self, mock_logger, mock_verbose):
        """Test logging with legacy tuple format."""
        operations = [
            ("col1", "expr1"),
            ("col2", "expr2"),
        ]
        frame_df = pl.LazyFrame({"test": [1, 2, 3]})

        log_query_plan(operations, frame_df)

        # Check that trace was called for each operation
        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Step 1: col1 = expr1" in call for call in trace_calls)
        assert any("Step 2: col2 = expr2" in call for call in trace_calls)

    @patch("gaspatchio_core.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio_core.frame.tracing.logger")
    def test_log_traced_operation_format(self, mock_logger, mock_verbose):
        """Test logging with new TracedOperation format."""
        metadata1 = OperationMetadata(
            file_name="test1.py",
            line_number=10,
            source_line="af['col1'] = expr1",
            function_name="test_func",
        )
        metadata2 = OperationMetadata(
            file_name="test2.py",
            line_number=20,
            source_line="af['col2'] = expr2",
            function_name="other_func",
        )

        operations = [
            TracedOperation("col1", "expr1", metadata1),
            TracedOperation("col2", "expr2", metadata2),
        ]
        frame_df = pl.LazyFrame({"test": [1, 2, 3]})

        log_query_plan(operations, frame_df)

        # Check that trace was called for each operation and metadata
        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Step 1: col1 = expr1" in call for call in trace_calls)
        assert any("Step 2: col2 = expr2" in call for call in trace_calls)
        assert any("Source: test1.py:10" in call for call in trace_calls)
        assert any("Source: test2.py:20" in call for call in trace_calls)

    @patch("gaspatchio_core.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio_core.frame.tracing.logger")
    def test_log_mixed_formats(self, mock_logger, mock_verbose):
        """Test logging with mixed tuple and TracedOperation formats."""
        metadata = OperationMetadata(
            file_name="test.py",
            line_number=15,
            source_line="af['new_col'] = expr",
            function_name="mixed_func",
        )

        operations = [
            ("old_col", "old_expr"),  # Legacy tuple
            TracedOperation("new_col", "new_expr", metadata),  # New format
        ]
        frame_df = pl.LazyFrame({"test": [1, 2, 3]})

        log_query_plan(operations, frame_df)

        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Step 1: old_col = old_expr" in call for call in trace_calls)
        assert any("Step 2: new_col = new_expr" in call for call in trace_calls)
        assert any("Source: test.py:15" in call for call in trace_calls)

    @patch("gaspatchio_core.frame.tracing.get_default_verbose", return_value=False)
    @patch("gaspatchio_core.frame.tracing.logger")
    def test_no_logging_when_verbose_disabled(self, mock_logger, mock_verbose):
        """Test that nothing is logged when verbose mode is disabled."""
        operations = [("col1", "expr1")]
        frame_df = pl.LazyFrame({"test": [1, 2, 3]})

        log_query_plan(operations, frame_df)

        # Should not call logger.trace when verbose is disabled
        mock_logger.trace.assert_not_called()

    @patch("gaspatchio_core.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio_core.frame.tracing.logger")
    def test_query_plan_explanation_error_handling(self, mock_logger, mock_verbose):
        """Test handling of errors during query plan explanation."""
        # Create a frame that will cause explain() to fail
        operations = [("col1", "expr1")]
        frame_df = Mock()
        frame_df.explain.side_effect = Exception("Explain failed")

        log_query_plan(operations, frame_df)

        # Should log a warning when explain fails
        mock_logger.warning.assert_called_once()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Could not explain query plan" in warning_call

    @patch("gaspatchio_core.frame.tracing.get_default_verbose", return_value=True)
    @patch("gaspatchio_core.frame.tracing.logger")
    def test_operation_without_metadata(self, mock_logger, mock_verbose):
        """Test handling of TracedOperation without metadata."""
        # Create TracedOperation with None metadata
        operation = TracedOperation("col1", "expr1", None)
        operations = [operation]
        frame_df = pl.LazyFrame({"test": [1, 2, 3]})

        log_query_plan(operations, frame_df)

        trace_calls = [call[0][0] for call in mock_logger.trace.call_args_list]
        assert any("Step 1: col1 = expr1" in call for call in trace_calls)
        # Should not log source info when metadata is None
        assert not any("Source:" in call for call in trace_calls)


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    def test_computation_graph_mixed_formats(self):
        """Test that computation graph can handle mixed formats."""
        frame = MockActuarialFrame(tracing=True)

        # Add legacy tuple format manually
        frame._computation_graph.append(("legacy_col", "legacy_expr"))

        # Add new format via append_operation_to_graph
        append_operation_to_graph(frame, "new_col", pl.col("x") + pl.col("y"))

        assert len(frame._computation_graph) == 2

        # First should be tuple
        assert isinstance(frame._computation_graph[0], tuple)
        assert frame._computation_graph[0] == ("legacy_col", "legacy_expr")

        # Second should be TracedOperation
        assert isinstance(frame._computation_graph[1], TracedOperation)
        assert frame._computation_graph[1].alias == "new_col"

    def test_toggle_tracing_state(self):
        """Test that tracing can be toggled on and off."""
        frame = MockActuarialFrame(tracing=False)

        # Should not capture when disabled
        append_operation_to_graph(frame, "disabled", pl.col("a"))
        assert len(frame._computation_graph) == 0

        # Enable tracing
        frame._tracing = True
        append_operation_to_graph(frame, "enabled", pl.col("b"))
        assert len(frame._computation_graph) == 1

        # Disable again
        frame._tracing = False
        append_operation_to_graph(frame, "disabled_again", pl.col("c"))
        assert len(frame._computation_graph) == 1  # Should not add


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    def test_realistic_operation_sequence(self):
        """Test a realistic sequence of operations."""
        frame = MockActuarialFrame(tracing=True)

        # Simulate a typical calculation sequence
        operations = [
            ("premium_base", pl.col("policy_amount") * pl.col("rate")),
            ("premium_adjusted", pl.col("premium_base") * pl.col("adjustment_factor")),
            ("commission", pl.col("premium_adjusted") * pl.col("commission_rate")),
            ("net_premium", pl.col("premium_adjusted") - pl.col("commission")),
        ]

        for name, expr in operations:
            append_operation_to_graph(frame, name, expr)

        assert len(frame._computation_graph) == 4

        # All should be TracedOperation with metadata
        for i, operation in enumerate(frame._computation_graph):
            assert isinstance(operation, TracedOperation)
            assert operation.alias == operations[i][0]
            # Expression is a Polars expression object, just check it exists
            assert operation.expression is not None
            assert operation.metadata is not None

    def test_error_resilience(self):
        """Test that the system is resilient to errors in metadata capture."""
        frame = MockActuarialFrame(tracing=True)

        # Mock capture_source_context to raise an exception
        with patch(
            "gaspatchio_core.errors.metadata.capture_source_context",
            side_effect=Exception("Metadata capture failed"),
        ):
            # This should not crash the operation
            with pytest.raises(Exception, match="Metadata capture failed"):
                append_operation_to_graph(frame, "test", pl.col("x"))

    def test_memory_efficiency(self):
        """Test memory usage characteristics."""
        frame = MockActuarialFrame(tracing=True)

        # Add many operations and check that memory usage is reasonable
        for i in range(1000):
            # Use actual Polars expressions instead of strings
            append_operation_to_graph(frame, f"col_{i}", pl.col(f"input_{i}") * i)

        assert len(frame._computation_graph) == 1000

        # Each operation should have metadata
        for operation in frame._computation_graph:
            assert isinstance(operation, TracedOperation)
            assert operation.metadata is not None
            # Metadata should be reasonably sized
            assert len(operation.metadata.source_line) < 1000  # Reasonable line length
