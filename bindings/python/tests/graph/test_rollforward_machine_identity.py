# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The machine a file runs is the one its identity names (spec 12.1).

An executable artifact carries a compiled rollforward's state machine in the
``gaspatchio_rollforward_ir`` facet, keyed by the compiled fingerprint. That
fingerprint is the section 12.3 recipe-grammar hash of the body exactly as
published, less its ``schedule`` member, so a reader holding the file
recomputes it. Before this, the identity was taken over engine renderings the
file does not hold: a floor edited to a billion, or a charge read as a growth,
resealed, kept every identity, passed ``validate --deep`` and replayed a
different number.

The model is the shipped single-state fund pattern: grow by 1%, charge 0.1%,
floor at nought. Its first period is ``100,000 x 1.01 x 0.999 = 100,899.0``;
the charge read as a growth would be 101,101.0 and the floor of a billion
1,000,000,000.0.
"""

from __future__ import annotations

import copy
import datetime
import hashlib
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, compile_rollforward
from gaspatchio._identity import canonical_bytes
from gaspatchio.frame.graph import GraphExporter, validate_artifact
from gaspatchio.frame.graph.artifact import document_digest_of
from gaspatchio.frame.graph.execution import inspect_execution
from gaspatchio.frame.graph.rollforward_ir import FACET_NAME

_BOOK = pl.DataFrame(
    {
        "policy_id": ["VA-0001"],
        "av_init": [100_000.0],
        "fund_return": [[0.01] * 3],
        "me_charge": [[0.001] * 3],
    }
)


def _fund(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    (
        b["av"]
        .grow(af["fund_return"], label="fund_return")
        .charge(af["me_charge"], label="me_charge")
        .floor(value=0.0)
    )
    af.av = compile_rollforward(b).expr_for("av")
    return af


def _document(profile: str = "executable") -> dict[str, Any]:
    af = _fund(ActuarialFrame(_BOOK))
    assert af.collect()["av"][0][0] == pytest.approx(100_899.0, rel=1e-15)
    document: dict[str, Any] = json.loads(
        GraphExporter(af, data_columns=_BOOK.columns).export(profile=profile)
    )
    return document


def _the_compilation(document: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    ((fingerprint, body),) = document["facets"][FACET_NAME]["compilations"].items()
    return fingerprint, body


def _the_node(document: dict[str, Any]) -> dict[str, Any]:
    (node,) = [n for n in document["nodes"] if n["id"].startswith("rollforward:")]
    return node


def _resealed(document: dict[str, Any]) -> dict[str, Any]:
    document.pop("document_digest", None)
    document["document_digest"] = document_digest_of(document)
    return document


def _errors(document: dict[str, Any]) -> list[str]:
    report = validate_artifact(document, deep=True)
    return [f.where for f in report.findings if f.severity == "error"]


def test_the_identity_is_the_recipe_hash_of_the_published_body() -> None:
    """A reader recomputes the compiled fingerprint from the file alone."""
    document = _document()
    fingerprint, body = _the_compilation(document)
    without_schedule = {k: v for k, v in body.items() if k != "schedule"}
    taken = "sha256:" + hashlib.sha256(canonical_bytes(without_schedule)).hexdigest()
    assert taken == fingerprint
    assert _the_node(document)["id"] == "rollforward:" + fingerprint[7:19]
    assert validate_artifact(document, deep=True).ok
    assert _errors(document) == []


@pytest.mark.parametrize(
    "edit",
    ["floor of a billion", "charge read as a growth", "opening value re-pointed"],
)
def test_an_edited_machine_is_refused_by_validate_and_by_the_run(edit: str) -> None:
    """Every identity stays as it was, the body moves, and both readers refuse."""
    document = _document()
    fingerprint, body = _the_compilation(document)
    increments = body["increments"]
    if edit == "floor of a billion":
        increments[2]["settings"]["value"] = 1e9
    elif edit == "charge read as a growth":
        increments[1]["operation"] = "Grow"
    else:
        body["states"][0]["init"] = {"op": "col", "name": "fund_return"}
    document = _resealed(document)

    where = f"/facets/{FACET_NAME}/compilations/{fingerprint}"
    assert where in _errors(document)
    assert not validate_artifact(document, deep=True).ok

    # ``run-artifact`` reads through the execution inspection, which validates
    # deeply first and inspects nothing a failed reading leaves standing.
    inspection = inspect_execution(document)
    assert not inspection.validation.ok
    assert where in [f.where for f in inspection.validation.findings]


def test_a_summary_that_disagrees_with_the_body_is_refused() -> None:
    """The node's movement summary is held to the machine it restates."""
    document = _document()
    fingerprint, _ = _the_compilation(document)
    _the_node(document)["increments"][1]["operation"] = "Grow"
    document = _resealed(document)

    where = f"/facets/{FACET_NAME}/compilations/{fingerprint}/increments/1"
    assert where in _errors(document)
    assert not inspect_execution(document).validation.ok


def test_a_compilation_the_file_does_not_carry_is_named_as_read_on_trust() -> None:
    """The audit profile carries no machine: its identity is read as published."""
    document = _document(profile="audit")
    assert FACET_NAME not in document.get("facets", {})
    node_id = _the_node(document)["id"]
    report = validate_artifact(document, deep=True)
    assert report.ok
    (warning,) = [f for f in report.findings if f.where == node_id]
    assert warning.severity == "warning"
    assert "read as published" in warning.message


def test_an_unedited_copy_of_the_machine_passes_untouched() -> None:
    """Reordering nothing and resealing moves nothing: the check is not a seal check."""
    document = _resealed(copy.deepcopy(_document()))
    assert _errors(document) == []
