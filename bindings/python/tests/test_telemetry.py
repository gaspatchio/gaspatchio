# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for gaspatchio.telemetry.

Covers the PerformanceViolationError raise path (formerly sys.exit) and the
debug-mode warning path for map_elements.
"""

from __future__ import annotations

import importlib
import linecache
import sys
import warnings
from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

import gaspatchio
from gaspatchio.telemetry import PerformanceViolationError
from gaspatchio.util import get_default_mode

if TYPE_CHECKING:
    from pathlib import Path


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
        with gaspatchio.execution_mode("debug"):
            result = _call_map_elements()
        assert result["x"].to_list() == [2, 3, 4]

    def test_mode_is_restored_after_context_exits(self) -> None:
        """execution_mode context manager restores the prior mode on exit."""
        prior = get_default_mode()
        with gaspatchio.execution_mode("debug"):
            pass
        assert get_default_mode() == prior


class TestMapElementsOptimizeMode:
    """map_elements in optimize mode raises PerformanceViolationError."""

    def test_raises_performance_violation_error(self) -> None:
        """map_elements in optimize mode raises PerformanceViolationError."""
        with (
            gaspatchio.execution_mode("optimize"),
            pytest.raises(PerformanceViolationError),
        ):
            _call_map_elements()

    def test_error_message_contains_location_context(self) -> None:
        """Error message includes location, function, and suggestion fields."""
        with (
            gaspatchio.execution_mode("optimize"),
            pytest.raises(PerformanceViolationError) as exc_info,
        ):
            _call_map_elements()
        message = str(exc_info.value)
        assert "map_elements" in message
        assert "Location:" in message
        assert "Function:" in message
        assert "SUGGESTION:" in message

    def test_error_message_contains_calling_filename(self) -> None:
        """The Location banner references the file that called map_elements."""
        with (
            gaspatchio.execution_mode("optimize"),
            pytest.raises(PerformanceViolationError) as exc_info,
        ):
            _call_map_elements()
        assert "test_telemetry.py" in str(exc_info.value)

    def test_mode_restored_after_exception(self) -> None:
        """execution_mode restores mode even when an exception escapes its body."""
        prior = get_default_mode()
        with (
            pytest.raises(PerformanceViolationError),
            gaspatchio.execution_mode("optimize"),
        ):
            _call_map_elements()
        assert get_default_mode() == prior

    def test_exception_is_catchable(self) -> None:
        """Callers can catch PerformanceViolationError — not a BaseException abort."""
        caught: list[PerformanceViolationError] = []
        with gaspatchio.execution_mode("optimize"):
            try:
                _call_map_elements()
            except PerformanceViolationError as exc:
                caught.append(exc)
        assert len(caught) == 1
        assert isinstance(caught[0], PerformanceViolationError)


# --- who is told about a slow call, and through which channel ----------------
#
# The user's own call is raised as a PerformanceWarning at their line, and is
# not logged. The framework's own call -- its lowering takes the slow path
# where nothing faster exists -- is logged, and the user is not warned about
# code they did not write. One channel for each call, whichever it is.


def _logged_warnings() -> tuple[list[str], int]:
    """Add a loguru WARNING sink and return (messages, sink_id)."""
    from loguru import logger

    messages: list[str] = []
    return messages, logger.add(
        lambda message: messages.append(message.record["message"]), level="WARNING"
    )


def _stop(sink_id: int) -> None:
    from loguru import logger

    logger.remove(sink_id)


def _the_line_named(warning: warnings.WarningMessage) -> str:
    """Return the source line a warning names."""
    return linecache.getline(warning.filename, warning.lineno)


def test_the_users_own_map_elements_is_a_performance_warning_at_their_line() -> None:
    """Named at the line that called it, and said once, by warning only."""
    from gaspatchio import GaspatchioWarning, PerformanceWarning

    slow = pl.col("x")
    logged, sink = _logged_warnings()
    try:
        with (
            gaspatchio.execution_mode("debug"),
            pytest.warns(PerformanceWarning, match="map_elements") as heard,
        ):
            slow.map_elements(lambda v: v + 1, return_dtype=pl.Int64)
    finally:
        _stop(sink)

    (ours,) = [w for w in heard if issubclass(w.category, PerformanceWarning)]
    assert issubclass(ours.category, GaspatchioWarning)
    assert ours.filename == __file__
    assert "slow.map_elements(" in _the_line_named(ours)
    assert [m for m in logged if "MAP_ELEMENTS" in m] == []


def test_a_call_through_a_proxy_is_still_the_users_call() -> None:
    """af.x.map_elements() hands the user's request on; their line is named."""
    from gaspatchio import ActuarialFrame, PerformanceWarning

    af = ActuarialFrame(pl.DataFrame({"x": [1, 2, 3]}))
    with (
        gaspatchio.execution_mode("debug"),
        pytest.warns(PerformanceWarning, match="map_elements") as heard,
    ):
        af.y = af.x.map_elements(lambda v: v * 2, return_dtype=pl.Int64)

    (ours,) = [w for w in heard if issubclass(w.category, PerformanceWarning)]
    assert ours.filename == __file__
    assert "af.x.map_elements(" in _the_line_named(ours)


def test_map_batches_without_a_return_dtype_is_a_performance_warning() -> None:
    """The second pattern the notice covers, said the same way."""
    from gaspatchio import PerformanceWarning

    frame = pl.DataFrame({"x": [1, 2, 3]})
    with pytest.warns(PerformanceWarning, match="no return_dtype"):
        frame.select(pl.col("x").map_batches(lambda s: s * 2))


def test_the_frameworks_own_slow_path_is_logged_and_not_warned_about() -> None:
    """A day count over real boundary dates is the framework's map_elements call.

    The user did not write it and cannot rewrite it, so it is not raised at
    their line. It stays a log record, shown where the logs are on.
    """
    from gaspatchio import GaspatchioWarning
    from gaspatchio.schedule._day_count import Actual365Fixed
    from gaspatchio.schedule._schedule import Schedule

    frame = pl.DataFrame({"contract_inception": [date(2024, 3, 15)]})
    schedule = Schedule.from_inception(
        inception_column="contract_inception",
        n_periods=2,
        frequency="1M",
        day_count=Actual365Fixed(),
    )
    logged, sink = _logged_warnings()
    try:
        with (
            gaspatchio.execution_mode("debug"),
            warnings.catch_warnings(record=True) as heard,
        ):
            warnings.simplefilter("always")
            frame.with_columns(yfs=schedule.year_fractions_expr())
    finally:
        _stop(sink)

    assert [w for w in heard if issubclass(w.category, GaspatchioWarning)] == []
    assert any(m.startswith("MAP_ELEMENTS_PERFORMANCE_ISSUE") for m in logged)


# --- only the user's own call is theirs to hear about ------------------------


def test_map_elements_without_a_dtype_warns_once_not_twice() -> None:
    """Polars' map_elements calls map_batches itself; that call is not the user's."""
    from gaspatchio import PerformanceWarning

    slow = pl.col("x")
    with warnings.catch_warnings(record=True) as heard:
        warnings.simplefilter("always")
        pl.DataFrame({"x": [1, 2]}).select(slow.map_elements(lambda v: v + 1))

    ours = [w for w in heard if issubclass(w.category, PerformanceWarning)]
    assert len(ours) == 1, [str(w.message) for w in ours]
    assert ours[0].filename == __file__
    assert "map_elements()" in str(ours[0].message)


def test_a_librarys_own_call_is_not_the_users(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A third-party package's map_elements is logged, not raised at its line."""
    from gaspatchio import GaspatchioWarning

    library = tmp_path / "lib" / "python3.13" / "site-packages" / "slowlib"
    library.mkdir(parents=True)
    (library / "__init__.py").write_text(
        "import polars as pl\n"
        "\n"
        "\n"
        "def prep(frame):\n"
        '    return frame.select(pl.col("x").map_elements(lambda v: v + 1, '
        "return_dtype=pl.Int64))\n"
    )
    monkeypatch.syspath_prepend(str(library.parent))
    monkeypatch.delitem(sys.modules, "slowlib", raising=False)
    slowlib = importlib.import_module("slowlib")
    logged, sink = _logged_warnings()
    try:
        with warnings.catch_warnings(record=True) as heard:
            warnings.simplefilter("always")
            slowlib.prep(pl.DataFrame({"x": [1, 2]}))
    finally:
        _stop(sink)

    assert [w for w in heard if issubclass(w.category, GaspatchioWarning)] == []
    assert any(m.startswith("MAP_ELEMENTS_PERFORMANCE_ISSUE") for m in logged)


def test_the_notice_names_the_switch_that_refuses_the_call() -> None:
    """--mode optimize does not refuse it; GASPATCHIO_MODE=optimize does."""
    from gaspatchio import PerformanceWarning

    slow = pl.col("x")
    with pytest.warns(PerformanceWarning, match="GASPATCHIO_MODE=optimize"):
        slow.map_elements(lambda v: v + 1, return_dtype=pl.Int64)


def test_optimize_mode_refuses_only_the_users_call() -> None:
    """The framework's own Schedule slow path runs under optimize mode."""
    from gaspatchio.schedule._day_count import Actual365Fixed
    from gaspatchio.schedule._schedule import Schedule

    frame = pl.DataFrame({"contract_inception": [date(2024, 3, 15)]})
    schedule = Schedule.from_inception(
        inception_column="contract_inception",
        n_periods=2,
        frequency="1M",
        day_count=Actual365Fixed(),
    )
    with gaspatchio.execution_mode("optimize"):
        out = frame.with_columns(yfs=schedule.year_fractions_expr())

    assert out.get_column("yfs").to_list()[0] == pytest.approx([31 / 365, 30 / 365])
