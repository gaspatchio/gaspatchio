# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A compiled machine carries its schedule without a separate date calculation."""

from __future__ import annotations

import datetime
import json
from typing import Any, Literal

import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.lowering import artefacts
from gaspatchio.rollforward import RollforwardBuilder, compile_rollforward
from gaspatchio.schedule import OneTwelfth, Schedule


def _model(monkeypatch: pytest.MonkeyPatch) -> tuple[ActuarialFrame, Schedule]:
    """Build two distinct machines on one schedule, with no projection accessor."""
    monkeypatch.setattr(artefacts, "_SCHEDULES", {})
    monkeypatch.setattr(artefacts, "_ROLLFORWARDS", {})
    frame = ActuarialFrame({"initial": [100.0], "rate": [[0.1, 0.1, 0.1]]})
    schedule = Schedule.from_calendar_grid(
        start_date=datetime.date(2025, 1, 31),
        n_periods=3,
        frequency="1M",
        day_count=OneTwelfth(),
    )
    for state in ("fund", "benefit"):
        builder = RollforwardBuilder(states={state: frame.initial}, schedule=schedule)
        builder[state].grow(frame.rate, label="interest")
        compiled = compile_rollforward(builder)
        setattr(frame, state, compiled.expr_for(state))
    return frame, schedule


def _export(
    frame: ActuarialFrame, profile: Literal["audit", "executable"] = "executable"
) -> dict[str, Any]:
    """Read the exported document and require its deep integrity checks to pass."""
    artifact: dict[str, Any] = json.loads(GraphExporter(frame).export(profile=profile))
    report = validate_artifact(artifact, deep=True)
    assert report.ok, report.findings
    return artifact


@pytest.mark.parametrize("profile", ["audit", "executable"])
def test_compiled_schedules_are_discovered_and_shared(
    monkeypatch: pytest.MonkeyPatch, profile: Literal["audit", "executable"]
) -> None:
    """Two machines identify one complete basis and each names it as a read."""
    frame, schedule = _model(monkeypatch)
    fingerprint = frame.graph.fingerprint()
    artifact = _export(frame, profile)
    (entry,) = artifact["assumptions"]
    assert entry["kind"] == "schedule"
    assert entry["fingerprint"] == schedule.source_sha()
    assert entry["payload"] == schedule.canonical_form()
    machines = [node for node in artifact["nodes"] if node["kind"] == "rollforward"]
    assert len(machines) == 2
    assert all(node["reads_assumptions"] == [entry["name"]] for node in machines)
    assert artifact["graph_fingerprint"] == fingerprint
    values = frame.collect()
    assert values["fund"].to_list()[0] == pytest.approx([110.0, 121.0, 133.1])
    assert values["benefit"].to_list() == values["fund"].to_list()


def test_a_known_schedule_with_unavailable_values_remains_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing the schedule registry does not erase the machine's basis identity."""
    frame, schedule = _model(monkeypatch)
    monkeypatch.setattr(artefacts, "_SCHEDULES", {})
    artifact = _export(frame)
    (entry,) = artifact["assumptions"]
    assert entry["fingerprint"] == schedule.source_sha()
    assert entry["payload"] == {"omitted": "unavailable"}


def test_an_unavailable_compilation_still_names_the_schedule_its_node_carries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The node states its schedule beside the machine, so losing the machine keeps it.

    The compiled fingerprint is the machine alone, and the schedule it runs
    on is an attribute of the compilation's own call. A process that cannot
    reach the compiled artefact loses the machine -- no IR facet -- and
    still names the basis the node says it ran on, with its payload where
    the schedule itself is in reach.
    """
    frame, schedule = _model(monkeypatch)
    monkeypatch.setattr(artefacts, "_ROLLFORWARDS", {})
    artifact = _export(frame)
    (entry,) = artifact["assumptions"]
    assert entry["fingerprint"] == schedule.source_sha()
    assert entry["payload"] == schedule.canonical_form()
    assert "gaspatchio_rollforward_ir" not in artifact["facets"]


def test_unread_compilations_do_not_add_assumptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discovery follows the model's reads, rather than all registered objects."""
    _model(monkeypatch)
    frame = ActuarialFrame({"initial": [100.0]})
    frame.total = frame.initial * 2.0
    assert _export(frame)["assumptions"] == []
