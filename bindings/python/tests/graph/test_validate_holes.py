# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The validator holds each hole to the shape its reason says it has.

Section 7.1 lists one entry per name the model cannot account for, carrying
the reason of the first node that stands for it, and the reason fixes that
node's shape: an overwritten hole is a definition a write past the
producer's interfaces made, versioned as a definition is, while an
unrecorded or a rebuilt hole stands for a column that arrived, unversioned
as an arrival is. A file whose section and nodes disagree tells a reader who
reads only the section one thing and a reader who walks the nodes another,
so the validator refuses it, as it refuses a gap in a column's ordinals.

What is not required is the line an overwritten hole carries: a producer
states it where it found the line, and a write made where no line can be
read back has none, as a definition written there has none.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, validate_artifact

_BOOK = pl.DataFrame({"policy_id": [1, 2], "premium": [100.0, 200.0]})


def _overwritten() -> dict[str, Any]:
    """Return an export holding one overwritten hole, ``commission@2``."""
    af = ActuarialFrame(_BOOK)
    af.commission = af.premium * 0.1
    af._df = af._df.with_columns(pl.lit(0.0).alias("commission"))  # noqa: SLF001
    af.net = af.premium - af.commission
    document: dict[str, Any] = json.loads(GraphExporter(af).export())
    return document


def _rebuilt() -> dict[str, Any]:
    """Return an export holding one rebuilt hole, ``reserve``."""
    af = ActuarialFrame(_BOOK)
    af.reserve = af.premium * 0.5
    wrapped = ActuarialFrame(af.collect())
    wrapped.total = wrapped.reserve + 1.0
    document: dict[str, Any] = json.loads(GraphExporter(wrapped).export())
    return document


def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in document["nodes"] if node["id"] == node_id)


def _errors(document: dict[str, Any]) -> list[str]:
    return [
        finding.message
        for finding in validate_artifact(document).findings
        if finding.severity == "error"
    ]


def test_an_export_holding_each_reason_validates() -> None:
    for document in (_overwritten(), _rebuilt()):
        assert _errors(document) == []


def test_an_overwritten_hole_without_its_line_still_validates() -> None:
    """A write made where no line can be read back has none to give."""
    document = _overwritten()
    _node(document, "commission@2")["source_location"] = None

    assert _errors(document) == []


@pytest.mark.parametrize(
    ("source", "column", "reason"),
    [
        (_overwritten, "commission", "rebuilt"),
        (_overwritten, "commission", "unrecorded"),
        (_rebuilt, "reserve", "overwritten"),
    ],
    ids=[
        "versioned-labelled-rebuilt",
        "versioned-labelled-unrecorded",
        "unversioned-labelled-overwritten",
    ],
)
def test_a_reason_the_hole_node_does_not_fit_is_refused(
    source: Any,  # noqa: ANN401 -- one of the two builders above
    column: str,
    reason: str,
) -> None:
    document = source()
    for entry in document["holes"]:
        if entry["column"] == column:
            entry["reason"] = reason

    errors = _errors(document)

    assert len(errors) == 1
    assert f"says {column!r}" in errors[0]
    assert "Export the model again" in errors[0]


def test_an_unversioned_unlocated_hole_relabelled_overwritten_is_refused() -> None:
    document = _rebuilt()
    _node(document, "reserve")["source_location"] = None
    document["holes"][0]["reason"] = "overwritten"

    (error,) = _errors(document)

    assert "carries no version" in error


def test_a_hole_the_section_leaves_out_is_refused() -> None:
    document = _overwritten()
    original = copy.deepcopy(document)
    document["holes"] = []

    errors = _errors(document)

    assert any("has no entry for it" in error for error in errors)
    assert _errors(original) == []


def test_an_entry_no_hole_stands_behind_is_refused() -> None:
    document = _overwritten()
    document["holes"].append(
        {**document["holes"][0], "column": "premium", "reason": "unrecorded"}
    )

    errors = _errors(document)

    assert any("no hole node in this file stands for" in error for error in errors)


def test_a_name_listed_twice_is_refused() -> None:
    document = _overwritten()
    document["holes"].append(dict(document["holes"][0]))

    errors = _errors(document)

    assert any("more than once" in error for error in errors)
