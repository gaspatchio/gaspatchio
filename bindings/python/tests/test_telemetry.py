# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for gaspatchio_core.telemetry.

Covers the PerformanceViolationError raise path (formerly sys.exit) and the
debug-mode warning path for map_elements.
"""

from __future__ import annotations

import polars as pl
import pytest

import gaspatchio_core
from gaspatchio_core.telemetry import PerformanceViolationError
from gaspatchio_core.util import get_default_mode


def _call_map_elements() -> pl.DataFrame:
    """Invoke pl.Expr.map_elements so the telemetry wrapper fires."""
    frame = pl.DataFrame({"x": [1, 2, 3]})
    return frame.select(
        pl.col("x").map_elements(lambda v: v + 1, return_dtype=pl.Int64)
    )


class TestMapElementsDebugMode:
    """map_elements in debug mode should warn and return a result."""

    def test_returns_result_in_debug_mode(self) -> None:
        """Confirm map_elements executes and returns correct values in debug mode."""
        with gaspatchio_core.execution_mode("debug"):
            result = _call_map_elements()
        assert result["x"].to_list() == [2, 3, 4]

    def test_mode_is_restored_after_context_exits(self) -> None:
        """execution_mode context manager restores the prior mode on exit."""
        prior = get_default_mode()
        with gaspatchio_core.execution_mode("debug"):
            pass
        assert get_default_mode() == prior


class TestMapElementsOptimizeMode:
    """map_elements in optimize mode raises PerformanceViolationError."""

    def test_raises_performance_violation_error(self) -> None:
        """map_elements in optimize mode raises PerformanceViolationError."""
        with gaspatchio_core.execution_mode("optimize"), pytest.raises(
            PerformanceViolationError
        ):
            _call_map_elements()

    def test_error_message_contains_location_context(self) -> None:
        """Error message includes location, function, and suggestion fields."""
        with gaspatchio_core.execution_mode("optimize"), pytest.raises(
            PerformanceViolationError
        ) as exc_info:
            _call_map_elements()
        message = str(exc_info.value)
        assert "map_elements" in message
        assert "Location:" in message
        assert "Function:" in message
        assert "SUGGESTION:" in message

    def test_error_message_contains_calling_filename(self) -> None:
        """The Location banner references the file that called map_elements."""
        with gaspatchio_core.execution_mode("optimize"), pytest.raises(
            PerformanceViolationError
        ) as exc_info:
            _call_map_elements()
        assert "test_telemetry.py" in str(exc_info.value)

    def test_mode_restored_after_exception(self) -> None:
        """execution_mode restores mode even when an exception escapes its body."""
        prior = get_default_mode()
        with (
            pytest.raises(PerformanceViolationError),
            gaspatchio_core.execution_mode("optimize"),
        ):
            _call_map_elements()
        assert get_default_mode() == prior

    def test_exception_is_catchable(self) -> None:
        """Callers can catch PerformanceViolationError — not a BaseException abort."""
        caught: list[PerformanceViolationError] = []
        with gaspatchio_core.execution_mode("optimize"):
            try:
                _call_map_elements()
            except PerformanceViolationError as exc:
                caught.append(exc)
        assert len(caught) == 1
        assert isinstance(caught[0], PerformanceViolationError)
