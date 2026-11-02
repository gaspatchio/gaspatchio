# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reference reader reads a stored flag in arithmetic as the 0 or 1 it indicates.

Section 11.1.25 reads a Boolean operand of arithmetic as 1 for true, 0 for
false and null for null, per policy and per period, on either side and
under every operator, answering ``f64``; a per-policy Boolean on both sides
is not admitted. The producer and the JAX engine answered ``af.b * 1.0``
as ``[1.0, 0.0]``, and the reader refused the record
(``numeric-operands-required``). A comparison already reached it as its
indicator; a stored Boolean column, a run of them, and a ``True`` written
into the formula did not.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)
sys.path.insert(0, str(_CONFORMANCE))
try:
    from reader.shared import Column, DomainRefusal
    from reference import Reader
finally:
    sys.path.remove(str(_CONFORMANCE))

_BOOK = {
    "b": Column("bool", [True, False]),
    "d": Column("bool", [None, True]),
    "x": Column("f64", [2.5, -1.0]),
    "k": Column("i64", [5, 1]),
    "runs": Column("list[bool]", [[True, False], None]),
    "amounts": Column("list[f64]", [[1.0, 2.0], [3.0, 4.0]]),
}


def _col(name: str) -> dict:
    return {"op": "col", "name": name}


def _lit(value: object) -> dict:
    return {"op": "lit", "value": value}


def _binop(kind: str, left: dict, right: dict) -> dict:
    return {"op": "binop", "kind": kind, "left": left, "right": right}


@pytest.mark.parametrize(
    ("tree", "dtype", "hand"),
    [
        (_binop("mul", _col("b"), _lit(1.0)), "f64", [1.0, 0.0]),
        (_binop("sub", _lit(1), _col("b")), "f64", [0.0, 1.0]),
        (_binop("add", _col("b"), _col("k")), "f64", [6.0, 1.0]),
        (_binop("floordiv", _lit(2), _col("b")), "f64", [2.0, math.inf]),
        (_binop("pow", _col("b"), _lit(2.0)), "f64", [1.0, 0.0]),
        (_binop("mul", _col("d"), _col("x")), "f64", [None, -1.0]),
        (_binop("mul", _col("x"), _lit(value=True)), "f64", [2.5, -1.0]),
        (_binop("mul", _col("runs"), _lit(2.0)), "list[f64]", [[2.0, 0.0], None]),
        (
            _binop("add", _col("runs"), _col("amounts")),
            "list[f64]",
            [[2.0, 2.0], None],
        ),
        (
            _binop("add", _col("b"), _col("amounts")),
            "list[f64]",
            [[2.0, 3.0], [3.0, 4.0]],
        ),
    ],
)
def test_a_stored_flag_reads_as_its_indicator(
    tree: dict, dtype: str, hand: list
) -> None:
    answer = Reader(_BOOK, [], {}).evaluate(tree)

    assert answer.dtype == dtype
    assert answer.values == hand


def test_two_per_policy_flags_in_one_operation_are_refused() -> None:
    with pytest.raises(DomainRefusal, match="boolean-on-both-sides"):
        Reader(_BOOK, [], {}).evaluate(_binop("sub", _col("b"), _col("d")))


def test_the_reader_answers_the_producers_record_alike() -> None:
    af = ActuarialFrame(pl.DataFrame({"b": [True, False], "x": [2.5, -1.0]}))
    af.r = af.b * 1.0 + af.x * af.b
    tree = next(
        node["expr"]
        for node in json.loads(GraphExporter(af).export(profile="executable"))["nodes"]
        if node.get("column") == "r" and "expr" in node
    )

    answer = Reader(_BOOK, [], {}).evaluate(tree)

    assert answer.values == [3.5, 0.0]
    assert af.collect()["r"].to_list() == [3.5, 0.0]
