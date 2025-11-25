# ABOUTME: Test tracing functionality for ActuarialFrame debug mode
# ABOUTME: Verifies operation capture, log_query_plan calls, and mode switching
# ruff: noqa: S101, PLR2004, ANN201, SLF001, ANN202, D100, INP001, ARG001, T201
# type: ignore[attr-defined]

"""Tests for ActuarialFrame tracing functionality."""

from unittest.mock import Mock, patch

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio_core import ActuarialFrame, set_default_mode
from gaspatchio_core.util import set_default_verbose

# Sample data for testing
DATA = {"a": [1, 2, 3], "b": [4, 5, 6]}


@pytest.fixture
def base_frame():
    """Fixture to provide a basic ActuarialFrame."""
    return ActuarialFrame(DATA)


def test_trace_debug_mode(base_frame):
    """Test that trace runs the function directly in debug mode."""
    set_default_mode("debug")

    mock_func = Mock(return_value=None)  # Function modifies frame implicitly

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + f["b"]
        mock_func(f)  # Call mock to track execution

    result_frame = model_func(base_frame)

    mock_func.assert_called_once()
    assert result_frame is base_frame
    # Check that the operation was executed immediately
    expected_df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [5, 7, 9]})
    assert_frame_equal(result_frame.collect(), expected_df)
    # In debug mode, operations are still tracked in the computation graph
    assert len(base_frame._computation_graph) == 1
    assert base_frame._computation_graph[0].alias == "c"


def test_trace_optimize_mode_capture(base_frame):
    """Test that trace captures operations in optimize mode."""
    set_default_mode("optimize")

    mock_func = Mock(return_value=None)

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + 1
        f["d"] = f["b"] * 2
        mock_func(f)  # Should be called, but operations are deferred

    # Before calling, graph should be empty
    assert base_frame._computation_graph == []

    result_frame = model_func(base_frame)

    mock_func.assert_called_once()
    assert result_frame is base_frame

    # In optimize mode, operations are executed within the trace decorator
    # So the frame should have the new columns
    expected_df = pl.DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": [2, 3, 4], "d": [8, 10, 12]}
    )
    assert_frame_equal(base_frame.collect(), expected_df)

    # Check computation graph - operations were applied so graph should be empty
    assert len(base_frame._computation_graph) == 0


def test_trace_optimize_mode_no_operations(base_frame):
    """Test trace in optimize mode when the function performs no frame ops."""
    set_default_mode("optimize")

    @base_frame.trace
    def no_op_func(f):
        print("Performing no frame operations")
        return 123  # Return a value other than None

    result = no_op_func(base_frame)

    # The trace wrapper returns the function's return value
    assert result == 123
    assert base_frame._computation_graph == []
    # The internal df should not have changed
    assert_frame_equal(base_frame.collect(), pl.DataFrame(DATA))


@patch("gaspatchio_core.frame.tracing.log_query_plan")
def test_trace_log_query_plan_called(mock_log_plan, base_frame):
    """Test that log_query_plan is called in debug mode with verbose=True."""
    set_default_mode("debug")
    set_default_verbose(True)

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + 1

    model_func(base_frame)

    mock_log_plan.assert_called_once()
    # Check the arguments passed to log_query_plan
    args, kwargs = mock_log_plan.call_args
    captured_ops = args[0]
    final_df = args[1]

    assert len(captured_ops) == 1
    # Handle both old tuple format and new TracedOperation format
    if hasattr(captured_ops[0], "alias"):
        # New TracedOperation format
        assert captured_ops[0].alias == "c"
        assert isinstance(captured_ops[0].expression, pl.Expr)
    else:
        # Old tuple format
        assert captured_ops[0][0] == "c"
        assert isinstance(captured_ops[0][1], pl.Expr)

    # Check that the df passed is the final one after applying ops
    expected_final_df = pl.LazyFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [2, 3, 4]})
    assert_frame_equal(final_df.collect(), expected_final_df.collect())

    set_default_verbose(False)  # Reset for other tests


@patch("gaspatchio_core.frame.tracing.log_query_plan")
def test_trace_log_query_plan_not_called(mock_log_plan, base_frame):
    """Test that log_query_plan is NOT called in optimize mode with verbose=False."""
    set_default_mode("optimize")
    set_default_verbose(False)

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + 1

    model_func(base_frame)

    mock_log_plan.assert_not_called()
