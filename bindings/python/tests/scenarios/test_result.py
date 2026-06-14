# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test ScenarioResult dataclass."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gaspatchio_core.scenarios._result import ScenarioResult

if TYPE_CHECKING:
    from pathlib import Path


def test_result_construction() -> None:
    """ScenarioResult stores the aggregator outputs and runtime metadata."""
    r = ScenarioResult(
        aggregations={"scr": 1.234e6},
        plan_sha="sha256:abc",
        n_scenarios=500,
        batch_size=64,
        batch_size_resolution="auto_search",
        wall_time_s=12.34,
        peak_rss_mb=1500.0,
        n_batches=8,
        sink_dir=None,
    )
    assert r.aggregations == {"scr": 1.234e6}
    assert r.batch_size_resolution == "auto_search"
    assert r.sink_dir is None


def test_result_with_sink_dir(tmp_path: Path) -> None:
    """sink_dir is preserved when supplied."""
    sink = tmp_path / "foo"
    r = ScenarioResult(
        aggregations={},
        plan_sha="sha256:def",
        n_scenarios=100,
        batch_size=10,
        batch_size_resolution="manual",
        wall_time_s=5.0,
        peak_rss_mb=500.0,
        n_batches=8,
        sink_dir=sink,
    )
    assert r.sink_dir == sink


def test_result_is_frozen() -> None:
    """ScenarioResult is immutable; field assignment raises."""
    r = ScenarioResult(
        aggregations={},
        plan_sha="sha256:x",
        n_scenarios=1,
        batch_size=1,
        batch_size_resolution="manual",
        wall_time_s=0.1,
        peak_rss_mb=None,
        n_batches=8,
        sink_dir=None,
    )
    with pytest.raises((AttributeError, Exception)):  # FrozenInstanceError
        r.batch_size = 99  # type: ignore[misc]


def test_scenario_result_has_selection_and_new_resolution_literal() -> None:
    """ScenarioResult carries SelectionDecision and uses the new auto_search literal."""
    from gaspatchio_core.scenarios._result import (
        ProbeResult,
        ScenarioResult,
        SelectionDecision,
    )

    probe = ProbeResult(batch=4, engine="streaming", per_sc_s=0.04, peak_mb=300.0, fits=True)
    sel = SelectionDecision(
        engine="streaming", batch=4, reason="fastest_fitting", probed=[probe]
    )
    r = ScenarioResult(
        aggregations={},
        plan_sha="x",
        n_scenarios=10,
        batch_size=4,
        batch_size_resolution="auto_search",
        wall_time_s=1.0,
        peak_rss_mb=None,
        n_batches=8,
        sink_dir=None,
        selection=sel,
    )
    assert r.batch_size_resolution == "auto_search"
    assert r.selection.engine == "streaming"
    assert r.selection.probed[0].batch == 4
