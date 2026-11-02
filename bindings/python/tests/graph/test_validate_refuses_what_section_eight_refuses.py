# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``validate`` refuses the documents the format says do not conform, and the
Python export writes none of them.

Section 7: no absolute path appears anywhere in an artifact. The export a
skill teaches -- ``GraphExporter(af).export()``, no model identity -- wrote
each node's location, each source entry and each selection step as the
exporting machine's absolute path, and ``validate`` passed it. Section 8: a
one-policy document writes each field as the value itself, and a consumer
meeting an array of one has met a document that does not conform. Section
7.3: one source entry per distinct path, ordered by path.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, document_digest_of, validate_artifact


def _exported() -> dict[str, Any]:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "sa": [1.0]}))
    af.prem = af.sa * 0.5
    af = af.filter(af.sa > 0.5)
    return json.loads(GraphExporter(af).export(af.collect()))


def _resealed(document: dict[str, Any]) -> dict[str, Any]:
    unsealed = {
        key: value for key, value in document.items() if key != "document_digest"
    }
    unsealed["document_digest"] = document_digest_of(unsealed)
    return unsealed


def _refused_at(document: dict[str, Any]) -> list[str]:
    report = validate_artifact(_resealed(document), deep=True)
    return [finding.where for finding in report.findings if finding.severity == "error"]


def _strings(held: object) -> list[str]:
    if isinstance(held, dict):
        return [text for value in held.values() for text in _strings(value)]
    if isinstance(held, list):
        return [text for value in held for text in _strings(value)]
    return [held] if isinstance(held, str) else []


def test_the_python_export_writes_no_absolute_path() -> None:
    document = _exported()

    assert not [text for text in _strings(document) if text.startswith("/")]
    assert document["sources"][0]["path"].endswith(
        "test_validate_refuses_what_section_eight_refuses.py"
    )
    assert validate_artifact(document, deep=True).ok


def test_an_absolute_location_is_refused() -> None:
    document = copy.deepcopy(_exported())
    document["nodes"][-1]["source_location"] = "/home/someone/model.py:3"

    assert _refused_at(document) == [
        f"/nodes/{len(document['nodes']) - 1}/source_location"
    ]


def test_an_absolute_model_path_or_drive_is_refused() -> None:
    document = copy.deepcopy(_exported())
    document["model"]["source_path"] = "C:\\models\\model.py"

    assert "/model/source_path" in _refused_at(document)


def test_a_value_wrapped_in_an_array_of_one_is_refused() -> None:
    document = copy.deepcopy(_exported())
    for node in document["nodes"]:
        if node.get("shape") == "scalar" and "value_sample" in node:
            node["value_sample"] = [node["value_sample"]]

    refused = _refused_at(document)

    assert "prem@1" in refused
    assert "sa" in refused


def test_a_source_entry_written_twice_is_refused() -> None:
    document = copy.deepcopy(_exported())
    document["sources"] = [*document["sources"], document["sources"][0]]

    assert _refused_at(document) == ["/sources/1"]
