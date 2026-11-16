# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``validate`` accepts an honest export of a column whose cells are lists (GSP-218).

A per-period column of ``list[list[f64]]`` holds a list in each period. Its
sample is therefore a list of lists, and a run of one period is ``[[1.0]]``:
the same shape as an array of one around ``list[f64]``, and a different
statement, which the node's ``dtype`` tells apart. The walk-through's last
line is that period's own value, so it is the inner list and not a rendering
of it.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter, document_digest_of, validate_artifact

_NESTED = {"policy_id": pl.Int64, "c": pl.List(pl.List(pl.Float64))}


def _exported(cells: list[list[float]]) -> dict[str, Any]:
    af = ActuarialFrame(pl.DataFrame({"policy_id": [1], "c": [cells]}, schema=_NESTED))
    af.d = af.c
    return json.loads(GraphExporter(af).export(af.collect()))


def _errors(document: dict[str, Any]) -> list[str]:
    report = validate_artifact(document, deep=True)
    return [f"{f.where}: {f.message}" for f in report.findings if f.severity == "error"]


def _resealed(document: dict[str, Any]) -> dict[str, Any]:
    unsealed = {
        key: value for key, value in document.items() if key != "document_digest"
    }
    unsealed["document_digest"] = document_digest_of(unsealed)
    return unsealed


@pytest.mark.parametrize(
    "cells",
    [
        pytest.param([[1.0]], id="one period of one value"),
        pytest.param([[1.0, 2.0]], id="one period of two values"),
        pytest.param([[1.0, 2.0], [3.0, 4.0]], id="two periods"),
        pytest.param([[float("inf")], [2.0]], id="an infinity"),
        pytest.param([[float("nan")]], id="one period of NaN"),
    ],
)
def test_an_honest_nested_column_has_nothing_to_answer_for(
    cells: list[list[float]],
) -> None:
    assert _errors(_exported(cells)) == []


def test_the_walk_through_ends_at_the_first_periods_own_list() -> None:
    document = _exported([[1.0, 2.0], [3.0, 4.0]])
    node = next(n for n in document["nodes"] if n["id"] == "d@1")

    assert node["trace"][-1]["result"] == [1.0, 2.0]


def test_a_nested_column_wrapped_in_an_array_of_one_is_still_refused() -> None:
    document = copy.deepcopy(_exported([[1.0]]))
    for node in document["nodes"]:
        if node["id"] == "c":
            node["value_sample"] = [node["value_sample"]]

    assert any(
        error.startswith("c: ") and "array of one" in error
        for error in _errors(_resealed(document))
    )


def test_a_plain_per_period_column_wrapped_in_an_array_of_one_is_still_refused() -> (
    None
):
    frame = pl.DataFrame({"policy_id": [1], "c": [[1.0, 2.0]]})
    af = ActuarialFrame(frame)
    af.d = af.c
    document = json.loads(GraphExporter(af).export(af.collect()))
    for node in document["nodes"]:
        if node["id"] == "c":
            node["value_sample"] = [node["value_sample"]]

    assert any(
        error.startswith("c: ") and "array of one" in error
        for error in _errors(_resealed(document))
    )
