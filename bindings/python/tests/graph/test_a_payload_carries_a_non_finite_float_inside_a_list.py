# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An audit payload carries a NaN or an infinity inside a list.

Section 10 writes a non-finite ``f64`` as the string naming it -- ``"NaN"``,
``"Infinity"``, ``"-Infinity"`` -- wherever a value appears, and section 13
has a consumer read it back to the float before re-hashing. The producer
applied that to a scalar ``f64`` cell only: a join whose right side held a
``list[f64]`` with a non-finite element died exporting on the JSON writer's
backstop (``Out of range float values are not JSON compliant``), and
``gspio validate`` did not read the sentinel back inside a list either.

A table cannot hold a list column (its key and its answer are one value per
row), so its scalar cells are the control beside the join's.
"""

from __future__ import annotations

import itertools
import json
import math
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._identity import content_sha_of
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.frame.graph.validate import payload_frame, validate_artifact

_NAMES = itertools.count()
_NON_FINITE = {"NaN": math.nan, "+inf": math.inf, "-inf": -math.inf}
_SENTINEL = {"NaN": "NaN", "+inf": "Infinity", "-inf": "-Infinity"}


def _strict(text: str | bytes) -> dict[str, Any]:
    """Parse as a strict reader does: a bare NaN or Infinity token refuses."""

    def refuse(token: str) -> None:
        message = f"bare token {token} is not JSON"
        raise ValueError(message)

    return json.loads(text, parse_constant=refuse)  # type: ignore[no-any-return]


def _join_document(column: pl.Series) -> dict[str, Any]:
    right = pl.DataFrame({"k": [1, 2], "c": column})
    af = ActuarialFrame(pl.DataFrame({"pid": [1, 2], "k": [1, 2]})).join(right, on="k")
    af.out = af.k * 2
    exported = GraphExporter(af).export(
        af.collect(), profile="audit", include_source=False
    )
    return _strict(exported)  # type: ignore[arg-type]


def _table_document(value: float) -> dict[str, Any]:
    table = Table(
        name=f"m1_non_finite_{next(_NAMES)}",
        source=pl.DataFrame({"a": [1.0, 2.0], "v": [value, 0.5]}),
        dimensions={"a": "a"},
        value="v",
    )
    af = ActuarialFrame(pl.DataFrame({"pid": [1], "q": [2.0]}))
    af.r = table.lookup(a=af.q)
    exported = GraphExporter(af).export(
        af.collect(), profile="audit", include_source=False
    )
    return _strict(exported)  # type: ignore[arg-type]


def _entry(document: dict[str, Any], kind: str) -> dict[str, Any]:
    (entry,) = [one for one in document["assumptions"] if one["kind"] == kind]
    return entry


def _cells(entry: dict[str, Any], name: str = "c") -> list[Any]:
    names = [column["name"] for column in entry["payload"]["columns"]]
    at = names.index(name)
    return [row[at] for row in entry["payload"]["rows"]]


def _rehashes(entry: dict[str, Any]) -> None:
    rebuilt, unreadable = payload_frame(entry["payload"])
    assert unreadable is None
    assert rebuilt is not None
    assert content_sha_of(rebuilt) == entry["fingerprint"]


@pytest.mark.parametrize("what", list(_NON_FINITE))
def test_a_join_list_of_floats_carries_the_sentinel_and_rehashes(what: str) -> None:
    value = _NON_FINITE[what]
    entry = _entry(_join_document(pl.Series("c", [[value, 1.0], [2.0]])), "join")

    assert [_SENTINEL[what], 1.0] in _cells(entry)
    _rehashes(entry)


@pytest.mark.parametrize("what", list(_NON_FINITE))
def test_a_nested_list_of_floats_carries_the_sentinel_at_depth(what: str) -> None:
    value = _NON_FINITE[what]
    entry = _entry(_join_document(pl.Series("c", [[[value]], [[2.0], []]])), "join")

    assert [[_SENTINEL[what]]] in _cells(entry)
    _rehashes(entry)


@pytest.mark.parametrize("what", list(_NON_FINITE))
def test_validate_deep_reads_the_list_sentinel_back_and_finds_nothing(
    what: str,
) -> None:
    document = _join_document(pl.Series("c", [[_NON_FINITE[what], 1.0], [2.0]]))
    report = validate_artifact(document, deep=True)
    assert not [
        finding
        for finding in report.findings
        if finding.where.startswith("/assumptions") or finding.severity == "error"
    ]


def test_validate_flags_a_list_sentinel_that_names_another_number() -> None:
    document = _join_document(pl.Series("c", [[math.nan, 1.0], [2.0]]))
    entry = _entry(document, "join")
    at = [column["name"] for column in entry["payload"]["columns"]].index("c")
    for row in entry["payload"]["rows"]:
        if row[at] == ["NaN", 1.0]:
            row[at] = ["Infinity", 1.0]
    report = validate_artifact(document, deep=True)
    assert [f for f in report.findings if f.where.startswith("/assumptions")]


def test_a_list_of_text_holding_the_word_nan_stays_text() -> None:
    entry = _entry(_join_document(pl.Series("c", [["NaN", "x"], ["y"]])), "join")
    rebuilt, _ = payload_frame(entry["payload"])
    assert rebuilt is not None
    assert ["NaN", "x"] in rebuilt["c"].to_list()
    _rehashes(entry)


@pytest.mark.parametrize("what", list(_NON_FINITE))
def test_a_scalar_float_cell_still_carries_the_sentinel(what: str) -> None:
    value = _NON_FINITE[what]
    join = _entry(_join_document(pl.Series("c", [value, 1.0])), "join")
    table = _entry(_table_document(value), "table")

    for entry in (join, table):
        cells = [cell for row in entry["payload"]["rows"] for cell in row]
        assert _SENTINEL[what] in cells
        _rehashes(entry)
