# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Test tracing functionality for ActuarialFrame debug mode
# ABOUTME: Verifies operation capture, log_query_plan calls, and mode switching
# ruff: noqa: SLF001, ANN202, ARG001, T201
# type: ignore[attr-defined]

"""Tests for ActuarialFrame tracing functionality."""

from unittest.mock import Mock, patch

import polars as pl
from polars.testing import assert_frame_equal

from gaspatchio import ActuarialFrame
from gaspatchio.util import set_default_verbose

# Sample data for testing
DATA = {"a": [1, 2, 3], "b": [4, 5, 6]}


def test_trace_debug_mode():
    """Test that trace runs the function directly in debug mode."""
    base_frame = ActuarialFrame(DATA, mode="debug")

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
    # Debug mode routes the model function through the decorator, and that
    # is what marks the run as traced.
    assert base_frame._traced_run is True
    assert [record.column for record in base_frame._calculations] == ["c"]


def test_trace_optimize_mode_capture():
    """Test that trace captures operations in optimize mode."""
    base_frame = ActuarialFrame(DATA, mode="optimize")

    mock_func = Mock(return_value=None)

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + 1
        f["d"] = f["b"] * 2
        mock_func(f)  # Should be called, but operations are deferred

    # Before calling, nothing has been calculated
    assert base_frame._calculations == []

    result_frame = model_func(base_frame)

    mock_func.assert_called_once()
    assert result_frame is base_frame

    # In optimize mode, operations are executed within the trace decorator
    # So the frame should have the new columns
    expected_df = pl.DataFrame(
        {"a": [1, 2, 3], "b": [4, 5, 6], "c": [2, 3, 4], "d": [8, 10, 12]}
    )
    assert_frame_equal(base_frame.collect(), expected_df)

    # Both columns are recorded — the log does not depend on the mode —
    # but optimize mode never went through a traced run, so the verbose
    # diagnosis tier stays off.
    assert [record.column for record in base_frame._calculations] == ["c", "d"]
    assert base_frame._traced_run is False


def test_trace_optimize_mode_no_operations():
    """Test trace in optimize mode when the function performs no frame ops."""
    base_frame = ActuarialFrame(DATA, mode="optimize")

    @base_frame.trace
    def no_op_func(f):
        print("Performing no frame operations")
        return 123  # Return a value other than None

    result = no_op_func(base_frame)

    # The trace wrapper returns the function's return value
    assert result == 123
    assert base_frame._calculations == []
    # The internal df should not have changed
    assert_frame_equal(base_frame.collect(), pl.DataFrame(DATA))


@patch("gaspatchio.frame.tracing.log_query_plan")
def test_trace_log_query_plan_called(mock_log_plan):
    """Test that log_query_plan is called in debug mode with verbose=True."""
    base_frame = ActuarialFrame(DATA, mode="debug")
    set_default_verbose(True)

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + 1

    model_func(base_frame)

    mock_log_plan.assert_called_once()
    # Check the arguments passed to log_query_plan
    args, kwargs = mock_log_plan.call_args
    recorded = args[0]
    final_df = args[1]

    # One record per calculation, and it is the log's own record — there is
    # no second account of what the run did.
    assert len(recorded) == 1
    assert recorded == base_frame._calculations
    assert recorded[0].column == "c"
    assert isinstance(recorded[0].expr, pl.Expr)

    # Check that the df passed is the final one after applying ops
    expected_final_df = pl.LazyFrame({"a": [1, 2, 3], "b": [4, 5, 6], "c": [2, 3, 4]})
    assert_frame_equal(final_df.collect(), expected_final_df.collect())

    set_default_verbose(False)  # Reset for other tests


@patch("gaspatchio.frame.tracing.log_query_plan")
def test_trace_log_query_plan_not_called(mock_log_plan):
    """Test that log_query_plan is NOT called in optimize mode with verbose=False."""
    base_frame = ActuarialFrame(DATA, mode="optimize")
    set_default_verbose(False)

    @base_frame.trace
    def model_func(f):
        f["c"] = f["a"] + 1

    model_func(base_frame)

    mock_log_plan.assert_not_called()
