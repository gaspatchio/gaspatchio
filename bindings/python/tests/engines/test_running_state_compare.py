# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Compare fresh running-state exports without rewriting their unknown metadata."""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines.compare import compare_results
from gaspatchio.engines.reference import polars_reference
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.rollforward._compile import compile_rollforward

if TYPE_CHECKING:
    from gaspatchio.engines.protocol import ResultManifest


def specimen() -> tuple[dict[str, Any], pl.DataFrame, ResultManifest]:
    """Use the actual producer, not a hand-normalized artifact fixture."""
    frame = ActuarialFrame(
        pl.DataFrame({"opening": [100.0], "returns": [[0.1, -0.05]]})
    )
    frame = frame.projection.set(
        start_date=date(2024, 1, 31), n_periods=2, frequency="monthly"
    )
    builder = frame.projection.rollforward(states={"fund": frame.opening})
    builder["fund"].grow(frame.returns)
    frame.fund = compile_rollforward(builder).expr_for("fund")
    reference, manifest = polars_reference(frame, every_node=True)
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    state = next(node for node in artifact["nodes"] if node["kind"] == "state")
    assert state["dtype"] == "unknown"
    assert state["shape"] == "unknown"
    return artifact, reference, manifest


def test_fresh_running_state_compares_without_restamping_the_artifact() -> None:
    artifact, reference, manifest = specimen()
    original = json.dumps(artifact, sort_keys=True)
    report = compare_results(
        artifact,
        reference,
        reference,
        before_manifest=manifest,
        after_manifest=manifest,
    )
    assert report.verdict == "agree"
    assert not report.missing
    assert "state:fund@eop" in {line.node_id for line in report.lines}
    assert json.dumps(artifact, sort_keys=True) == original


def test_running_state_values_are_still_compared() -> None:
    artifact, reference, manifest = specimen()
    changed = reference.with_columns(pl.Series("state:fund@eop", [[110.0, 105.5]]))
    report = compare_results(
        artifact, reference, changed, before_manifest=manifest, after_manifest=manifest
    )
    assert report.verdict == "disagree"


def test_unknown_state_does_not_admit_a_wrong_physical_carrier() -> None:
    artifact, reference, manifest = specimen()
    changed = reference.with_columns(
        pl.Series("state:fund@eop", [[110, 104]], dtype=pl.List(pl.Int64))
    )
    with pytest.raises(
        ValueError, match=r"physical column.*state:fund@eop.*list\[i64\]"
    ):
        compare_results(
            artifact,
            reference,
            changed,
            before_manifest=manifest,
            after_manifest=manifest,
        )


def test_unknown_state_needs_a_proven_portable_declaration() -> None:
    artifact, reference, manifest = specimen()
    facet = artifact["facets"]["gaspatchio_rollforward_ir"]
    body = next(iter(facet["compilations"].values()))
    body["increments"][0]["operation"] = "GrowCapped"
    with pytest.raises(ValueError, match=r"state:fund@eop.*unknown"):
        compare_results(
            artifact,
            reference,
            reference,
            before_manifest=manifest,
            after_manifest=manifest,
        )
