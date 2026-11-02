# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Collection and profiling leave one consistent, inspectable completion."""

from __future__ import annotations

import inspect
import pickle
import platform
from dataclasses import FrozenInstanceError
from importlib.metadata import version
from typing import Any

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio import ActuarialFrame, _internal
from gaspatchio.engines import EngineNotInstalledError, report
from gaspatchio.engines.report import RunReport, RunSummary


@pytest.mark.parametrize("profiled", [False, True])
def test_completion_preserves_values_for_reentry(*, profiled: bool) -> None:
    af = ActuarialFrame({"amount": [2.0, 3.0]})
    af.reserve = af.amount * 2
    assert af.graph.last_run is None

    values = af.profile()[0] if profiled else af.collect()
    summary = af.graph.last_run
    assert summary is not None
    assert (summary.engine, summary.profiled) == ("polars", profiled)
    assert summary.polars_mode == (None if profiled else "streaming")
    assert (summary.rows, summary.columns) == (2, 2)
    assert not summary.report.refused()
    assert summary.report.notes == ()

    returned = ActuarialFrame(values, continue_from=af)
    assert_frame_equal(returned.collect(), values)
    assert returned.graph.precedents("reserve") == af.graph.precedents("reserve")


@pytest.mark.parametrize("engine", ["streaming", "in-memory", "auto"])
def test_summary_names_the_requested_polars_mode(engine: str) -> None:
    af = ActuarialFrame({"amount": [1]})
    af.collect(engine=engine)
    assert af.graph.last_run is not None
    assert af.graph.last_run.polars_mode == engine


def test_summary_is_immutable_and_invalidated_when_plan_changes() -> None:
    af = ActuarialFrame({"amount": [1]})
    af.collect()
    summary = af.graph.last_run
    assert summary is not None
    with pytest.raises(FrozenInstanceError):
        summary.rows = 9  # type: ignore[misc]
    af.reserve = af.amount * 2
    assert af.graph.last_run is None
    assert summary.rows == 1


def test_materialize_invalidates_the_completed_plan_summary() -> None:
    af = ActuarialFrame({"amount": [1]})
    af.materialize()
    assert af.graph.last_run is None


def test_failed_attempt_does_not_leave_a_successful_summary() -> None:
    af = ActuarialFrame({"amount": [1]})
    af.collect()
    with pytest.raises(EngineNotInstalledError):
        af.collect(engine="absent-test-engine")
    assert af.graph.last_run is None


@pytest.mark.parametrize("profiled", [False, True])
def test_a_polars_run_states_the_versions_it_ran_on(*, profiled: bool) -> None:
    af = ActuarialFrame({"amount": [2.0, 3.0]})
    af.reserve = af.amount * 2
    if profiled:
        af.profile()
    else:
        af.collect()

    summary = af.graph.last_run
    assert summary is not None
    stated = summary.versions
    assert set(stated) == {
        "core_version",
        "extension_version",
        "polars_version",
        "platform",
        "python_version",
        "extension_sha256",
    }
    assert stated["core_version"] == version("gaspatchio")
    assert stated["extension_version"] == _internal.__version__
    assert stated["polars_version"] == pl.__version__
    assert stated["python_version"] == platform.python_version()
    assert stated["extension_sha256"].startswith("sha256:")


def test_the_versions_are_read_when_asked_for_and_not_during_the_collect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def counted() -> dict[str, str]:
        asked.append("versions")
        return {"core_version": "0.0.0-test"}

    monkeypatch.setattr(report, "versions_in_this_process", counted)
    af = ActuarialFrame({"amount": [1.0]})
    af.collect()
    assert asked == []

    summary = af.graph.last_run
    assert summary is not None
    assert summary.versions == {"core_version": "0.0.0-test"}
    assert asked == ["versions"]


def test_each_read_of_the_versions_hands_back_a_mapping_of_the_callers_own() -> None:
    af = ActuarialFrame({"amount": [1.0]})
    af.collect()
    summary = af.graph.last_run
    assert summary is not None

    mine = summary.versions
    mine["polars_version"] = "edited"

    assert summary.versions["polars_version"] == pl.__version__


def test_what_produced_a_run_is_no_constructor_argument() -> None:
    """A run states what produced it; a caller building a summary cannot."""
    assert list(inspect.signature(RunSummary).parameters) == [
        "engine",
        "polars_mode",
        "profiled",
        "rows",
        "columns",
        "report",
    ]
    told: dict[str, Any] = {
        "engine": "polars",
        "polars_mode": None,
        "profiled": False,
        "rows": 1,
        "columns": 1,
        "report": RunReport(refusals=()),
        "_stated": (("core_version", "0.0.0"),),
    }
    with pytest.raises(TypeError, match="_stated"):
        RunSummary(**told)


def test_a_pickled_summary_states_the_versions_of_the_process_that_ran_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    af = ActuarialFrame({"amount": [1.0]})
    af.reserve = af.amount * 2
    af.collect()
    summary = af.graph.last_run
    assert summary is not None

    monkeypatch.setattr(
        report, "versions_in_this_process", lambda: {"core_version": "ran-here"}
    )
    carried = pickle.dumps(summary)
    monkeypatch.setattr(
        report, "versions_in_this_process", lambda: {"core_version": "restored-here"}
    )
    restored = pickle.loads(carried)  # noqa: S301 -- a pickle this test just wrote

    assert restored.versions == {"core_version": "ran-here"}
    assert restored == summary
    assert hash(restored) == hash(summary)
    assert summary.versions == {"core_version": "restored-here"}


def test_profiling_keeps_a_defensive_snapshot() -> None:
    af = ActuarialFrame({"amount": [2.0, 3.0]})
    af.reserve = af.amount * 2
    values, _ = af.profile()
    values.replace_column(1, pl.Series("reserve", [99.0, 99.0]))
    returned = ActuarialFrame(values, continue_from=af)
    assert returned.graph.precedents("reserve") == ()
