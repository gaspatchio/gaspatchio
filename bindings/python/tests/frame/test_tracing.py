from unittest.mock import Mock, patch

import polars as pl
import pytest
from gaspatchio_core import ActuarialFrame, set_default_mode
from gaspatchio_core.util import set_default_verbose
from polars.testing import assert_frame_equal

# Sample data for testing
DATA = {"a": [1, 2, 3], "b": [4, 5, 6]}


@pytest.fixture
def base_frame():
    "Fixture to provide a basic ActuarialFrame."
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
    # Check that computation graph is empty
    assert base_frame._computation_graph == []


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

    # Check that operations were captured, not executed immediately on original _df
    original_df = pl.LazyFrame(DATA)
    assert_frame_equal(
        base_frame._df.collect(), original_df.collect()
    )  # _df should be updated *after* trace returns

    # Check computation graph content (simplified check)
    assert len(base_frame._computation_graph) == 2


def test_trace_optimize_mode_no_operations(base_frame):
    """Test trace in optimize mode when the function performs no frame ops."""
    set_default_mode("optimize")

    @base_frame.trace
    def no_op_func(f):
        print("Performing no frame operations")
        return 123  # Return a value other than None

    result = no_op_func(base_frame)

    # In optimize mode, the trace wrapper currently returns the frame instance
    assert result is base_frame
    assert base_frame._computation_graph == []
    # The internal df should not have changed
    assert_frame_equal(base_frame.collect(), pl.DataFrame(DATA))


@patch("gaspatchio_core.frame.tracing.log_query_plan")
def test_trace_log_query_plan_called(mock_log_plan, base_frame):
    """Test that log_query_plan is called in optimize mode with verbose=True."""
    set_default_mode("optimize")
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
    assert captured_ops[0][0] == "c"
    # Check the expression type approximately
    assert isinstance(captured_ops[0][1], pl.Expr)

    # Check that the df passed is the final one after applying ops
    expected_final_df = pl.LazyFrame(DATA)
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
