# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every exported artifact carries the identity that makes it comparable.

An artifact whose identity fields are all null is a file nobody can hold
against last quarter's. It says how each column was made and cannot say
whether it is the same model that was read three months ago, which is the
one question the format exists to answer. So there is no unstamped export
path and no flag that makes one: every node arrives carrying both its own
content hash and the hash of everything its answer rests on, and the
envelope carries one string standing for the whole model.

The propagation test below is the one worth naming. It recomputes each
node's inherited hash from the artifact alone -- no operation tree, no
model, nothing but the file -- because that is exactly what a consumer
holding the audit profile has. If the arithmetic could not be redone from
the file, the identity fields would be a claim rather than a check.
"""

from __future__ import annotations

import hashlib
import json
from importlib import import_module
from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio.frame import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.artifact import build_artifact
from gaspatchio.frame.graph.fingerprint import fingerprints_for
from gaspatchio.frame.graph.graph_builder import fold

if TYPE_CHECKING:
    import pytest

    from gaspatchio.frame.graph.fingerprint import NodeFingerprints
    from gaspatchio.frame.graph.graph_builder import CalcGraph
    from gaspatchio.frame.graph.graph_models import NodeId

# The scheme every content hash in the framework is written under. Spelled
# out here rather than imported, so that a change to the constant has to
# face a test that states the shape a consumer was promised.
_SHA256_PREFIX = "sha256:"


def _two_column_model() -> ActuarialFrame:
    """Return a model with two arriving columns and one calculation over them."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    return frame


def _artifact_for_a_two_column_model() -> dict[str, Any]:
    """Return that model's exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(_two_column_model()).export())
    return artifact


def _chained_model() -> ActuarialFrame:
    """Return a model deep enough that inheritance has somewhere to travel.

    Three calculations over three arriving columns, the last reading two of
    the earlier ones, so the propagation check walks a node whose reads are
    themselves computed rather than only leaves.
    """
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "sum_assured": [100_000.0, 250_000.0],
                "mortality_rate": [0.001_23, 0.002_04],
                "lapse_rate": [0.05, 0.07],
            }
        )
    )
    frame.death_claims = frame.sum_assured * frame.mortality_rate
    frame.policies_in_force = 1.0 - frame.lapse_rate
    frame.expected_claims = frame.death_claims * frame.policies_in_force
    return frame


def _artifact_for_a_chained_model() -> dict[str, Any]:
    """Return the chained model's exported artifact, parsed back from the wire."""
    artifact: dict[str, Any] = json.loads(GraphExporter(_chained_model()).export())
    return artifact


def _digest(stamped: str) -> bytes:
    """Return the raw digest a stamped ``"sha256:<hex>"`` string carries."""
    return bytes.fromhex(stamped.removeprefix(_SHA256_PREFIX))


# --- what every node carries ------------------------------------------------


def test_every_node_in_an_exported_artifact_is_stamped() -> None:
    """No unstamped export path: both hashes are on every node, always."""
    artifact = _artifact_for_a_two_column_model()

    assert artifact["nodes"], "the model has nodes to stamp"
    for node in artifact["nodes"]:
        assert node["local_fingerprint"].startswith(_SHA256_PREFIX), node["id"]
        assert node["fingerprint"].startswith(_SHA256_PREFIX), node["id"]


def test_a_leaf_is_stamped_as_readily_as_a_calculation() -> None:
    """An arriving column has no formula and still has an identity.

    Its values are what a downstream number rests on, so a reader comparing
    two quarters needs to know whether the model was handed the same column
    -- which is a question about the leaf, not about what reads it.
    """
    artifact = _artifact_for_a_two_column_model()

    leaves = [node for node in artifact["nodes"] if node["kind"] == "input"]
    assert leaves, "the model has arriving columns"
    for leaf in leaves:
        assert leaf["local_fingerprint"].startswith(_SHA256_PREFIX), leaf["id"]
        assert leaf["fingerprint"].startswith(_SHA256_PREFIX), leaf["id"]


# --- what the envelope carries ----------------------------------------------


def test_the_artifact_carries_one_string_standing_for_the_whole_model() -> None:
    """One identity for the model, so "nothing changed" is a thing to check."""
    artifact = _artifact_for_a_two_column_model()

    assert artifact["graph_fingerprint"].startswith(_SHA256_PREFIX)


def test_two_exports_of_one_model_agree() -> None:
    """Identity that moved between two exports of one model would be noise."""
    first = _artifact_for_a_two_column_model()
    second = _artifact_for_a_two_column_model()

    assert first["graph_fingerprint"] == second["graph_fingerprint"]


def test_the_model_identity_moves_when_a_calculation_does() -> None:
    """The other half of agreement: a changed formula is not the same model."""
    unchanged = _artifact_for_a_two_column_model()

    edited = _two_column_model()
    edited.death_claims = edited.sum_assured * edited.mortality_rate * 0.5
    artifact: dict[str, Any] = json.loads(GraphExporter(edited).export())

    assert artifact["graph_fingerprint"] != unchanged["graph_fingerprint"]


# --- what a consumer can check with nothing but the file --------------------


def test_propagation_is_recomputable_from_the_artifact_alone() -> None:
    """What an audit-profile consumer can check without the operation tree."""
    artifact = _artifact_for_a_two_column_model()
    by_id = {node["id"]: node for node in artifact["nodes"]}

    for node in artifact["nodes"]:
        expected = hashlib.sha256(
            _digest(node["local_fingerprint"])
            + b"".join(_digest(by_id[read]["fingerprint"]) for read in node["reads"])
        ).hexdigest()
        assert node["fingerprint"] == f"{_SHA256_PREFIX}{expected}", node["id"]


def test_propagation_is_recomputable_through_a_chain_of_calculations() -> None:
    """The same check where what a node reads is itself computed."""
    artifact = _artifact_for_a_chained_model()
    by_id = {node["id"]: node for node in artifact["nodes"]}

    inherited = [node for node in artifact["nodes"] if node["reads"]]
    assert inherited, "the chained model has nodes that read something"
    for node in inherited:
        expected = hashlib.sha256(
            _digest(node["local_fingerprint"])
            + b"".join(_digest(by_id[read]["fingerprint"]) for read in node["reads"])
        ).hexdigest()
        assert node["fingerprint"] == f"{_SHA256_PREFIX}{expected}", node["id"]


def test_everything_a_node_reads_is_in_the_file_it_arrived_in() -> None:
    """Propagation is checkable only if no read points outside the artifact."""
    artifact = _artifact_for_a_chained_model()
    ids = {node["id"] for node in artifact["nodes"]}

    for node in artifact["nodes"]:
        for read in node["reads"]:
            assert read in ids, f"{node['id']} reads {read!r}, which is not in the file"


# --- what the export pays for it --------------------------------------------


def test_one_export_hashes_the_model_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stamping is unconditional, so the export must not pay for it twice.

    The stamp on every node and the one string standing for the whole model
    are the same digests read twice. Taking them in two passes would hash
    every operation tree in the model a second time to reach an answer the
    first pass already had.
    """
    passes = 0

    def counted(graph: CalcGraph) -> dict[NodeId, NodeFingerprints]:
        nonlocal passes
        passes += 1
        return fingerprints_for(graph)

    # Imported by name rather than reached through the package: the graph
    # package re-exports a *function* called ``fingerprint``, so an attribute
    # walk to the module of that name hands back the function instead.
    hashing = import_module("gaspatchio.frame.graph.fingerprint")
    monkeypatch.setattr(hashing, "fingerprints_for", counted)
    build_artifact(fold(_chained_model()))

    assert passes == 1
