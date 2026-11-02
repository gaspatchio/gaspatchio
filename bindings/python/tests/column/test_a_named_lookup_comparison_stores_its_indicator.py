# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A lookup's comparison named with ``.alias()`` stores its indicator at every door.

``af.r = table.lookup(k=af.k) > 60`` stores the 0.0 or 1.0 indicator section
11.1.26 states, as a column's comparison does. The batch doors take the same
test named on the Polars expression the lookup hands back --
``af.with_columns((table.lookup(k=af.k) > 60).alias("r"))`` and the same in
``select`` -- and there the name was lost: the test was rebuilt as the
comparison it is, which carries no name, so Polars named the indicator after
the lookup's key column and the frame refused the line for writing over
``k`` without saying so. The name is now kept, and every door stores the
indicator, typed ``f64`` in the record, with the reader agreeing.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reader.shared import Column  # noqa: E402
from reference import Reader  # noqa: E402

_BOOK = pl.DataFrame({"policy_id": [1, 2], "k": [1, 5]})
_TABLE = Table(
    name="a_named_lookup_comparison_stores_its_indicator",
    source=pl.DataFrame({"k": [1, 5], "rate": [135.021, 0.25]}),
    dimensions={"k": "k"},
    value="rate",
)

# By hand: the rates are 135.021 and 0.25, so "over 60" is 1.0 then 0.0.
_HAND = [1.0, 0.0]


def _with_columns(af: ActuarialFrame) -> ActuarialFrame:
    return af.with_columns((_TABLE.lookup(k=af.k) > 60).alias("r"))


def _select(af: ActuarialFrame) -> ActuarialFrame:
    return af.select("policy_id", "k", (_TABLE.lookup(k=af.k) > 60).alias("r"))


def _on_a_timeline(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=1,
        frequency="monthly",
    )
    return af.with_columns((_TABLE.lookup(k=af.k) > 60).alias("r"))


_DOORS: dict[str, Callable[[ActuarialFrame], ActuarialFrame]] = {
    "with_columns": _with_columns,
    "select": _select,
    "with_columns on a timeline": _on_a_timeline,
}


@pytest.mark.parametrize("door", list(_DOORS))
@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_the_named_test_stores_the_indicator(door: str, engine: str) -> None:
    af = _DOORS[door](ActuarialFrame(_BOOK))  # refused on the base

    out = af.collect(engine=engine)

    assert out.schema["r"] == pl.Float64
    assert out["r"].to_list() == _HAND


@pytest.mark.parametrize("door", list(_DOORS))
def test_the_record_names_the_indicator_and_the_reader_agrees(door: str) -> None:
    af = _DOORS[door](ActuarialFrame(_BOOK))
    doc = json.loads(GraphExporter(af).export(af.collect(), profile="executable"))
    node = next(n for n in doc["nodes"] if n.get("column") == "r")

    read = Reader(
        {"k": Column("i64", [1, 5])}, doc.get("assumptions", []), {}
    ).evaluate(node["expr"])

    assert node["dtype"] == "f64"
    assert (read.dtype, read.values) == ("f64", _HAND)


def test_assignment_stores_the_same_indicator() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = _TABLE.lookup(k=af.k) > 60

    assert af.collect()["r"].to_list() == _HAND
