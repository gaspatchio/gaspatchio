# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison on a per-policy table lookup stores the 0.0 or 1.0 indicator.

``af.r = af.age > 60`` stores the Float64 indicator section 11.1.26 states,
and the record names ``f64``. The same test over a lookup -- ``af.r =
table.lookup(k=af.k) > 1`` -- stored ``True``/``False``, the record named
``bool`` and the JAX engine agreed with it, while the reference reader,
which reads a stored comparison as its indicator, answered ``1.0``/``0.0``
against a record that said otherwise. The lookup's comparison is now stored
as the column's is: on the frame, in the record and in the reader alike.
A logical over such tests (``&``, ``|``, ``~``) stays a flag, as it does
over columns.
"""

from __future__ import annotations

import json
import operator
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

_BOOK = pl.DataFrame({"k": [1, 5], "q": [135.021, 0.25], "x": [2.0, 0.5]})
_TABLE = Table(
    name="a_lookup_comparison_stores_its_indicator",
    source=pl.DataFrame({"k": [1, 5], "rate": [135.021, 0.25]}),
    dimensions={"k": "k"},
    value="rate",
)

# Each test, and its indicator by hand for rates 135.021 and 0.25.
_TESTS: dict[str, tuple[Callable[[object, object], object], float, list[float]]] = {
    "lookup > 1": (operator.gt, 1.0, [1.0, 0.0]),
    "lookup >= 1": (operator.ge, 1.0, [1.0, 0.0]),
    "lookup < 1": (operator.lt, 1.0, [0.0, 1.0]),
    "lookup <= 1": (operator.le, 1.0, [0.0, 1.0]),
    "lookup == 0.25": (operator.eq, 0.25, [0.0, 1.0]),
    "lookup != 0.25": (operator.ne, 0.25, [1.0, 0.0]),
}


def _stored(af: ActuarialFrame) -> tuple[pl.DataFrame, dict]:
    out = af.collect()
    doc = json.loads(GraphExporter(af).export(out, profile="executable"))
    node = next(n for n in doc["nodes"] if n.get("column") == "r")
    return out, {"node": node, "assumptions": doc.get("assumptions", [])}


@pytest.mark.parametrize("line", list(_TESTS))
@pytest.mark.parametrize("engine", ["streaming", "in-memory"])
def test_a_lookup_s_comparison_stores_the_column_s_indicator(
    line: str, engine: str
) -> None:
    compare, bound, hand = _TESTS[line]
    af = ActuarialFrame(_BOOK)
    af.r = compare(_TABLE.lookup(k=af.k), bound)
    af.s = compare(af.q, bound)

    out = af.collect(engine=engine)

    assert out.schema["r"] == pl.Float64 == out.schema["s"]
    assert out["r"].to_list() == hand == out["s"].to_list()


def test_the_record_names_the_indicator_and_the_reader_agrees() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = _TABLE.lookup(k=af.k) > 1

    out, stored = _stored(af)
    inputs = {"k": Column("i64", [1, 5]), "q": Column("f64", [135.021, 0.25])}
    read = Reader(inputs, stored["assumptions"], {}).evaluate(stored["node"]["expr"])

    assert stored["node"]["dtype"] == "f64"
    assert (read.dtype, read.values) == ("f64", [1.0, 0.0])
    assert out["r"].to_list() == [1.0, 0.0]


def test_a_logical_over_a_lookup_s_comparisons_stays_a_flag() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = (_TABLE.lookup(k=af.k) > 1) & (af.x > 1)
    af.s = (af.q > 1) & (af.x > 1)

    out, stored = _stored(af)

    assert out.schema["r"] == pl.Boolean == out.schema["s"]
    assert out["r"].to_list() == [True, False] == out["s"].to_list()
    assert stored["node"]["dtype"] == "bool"


def test_the_comparison_read_as_a_test_is_unchanged() -> None:
    af = ActuarialFrame(_BOOK)
    test = _TABLE.lookup(k=af.k) > 1

    assert test.kind == "comparison"
    assert _BOOK.select(test.alias("t"))["t"].to_list() == [True, False]
