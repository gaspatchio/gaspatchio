# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reader answers a selection case's column as it answers any value case.

A ``selection-value`` case applies section 7.6's steps to the book and
publishes its ``expr`` over the kept rows. The reader evaluated that ``expr``
with its internal evaluator, which reads a comparison as a ``bool`` rather
than its ``f64`` indicator and carries 11.1.26's unknown as a NaN inside a
``bool`` -- not the column a producer stores (11.1.27: a per-policy ``&``
over a test a NaN left unknown is a null). Every published selection case
publishes a bare column, so none reached it; a case over a comparison or a
logical combination would have failed a conforming producer. The column is
now answered as a value case's is.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reference import verify  # noqa: E402

NAN = {"nonfinite": "nan"}
_BOOK = {
    "status": {"dtype": "str", "values": ["IF", "IF", "LAPSED", "IF", "IF"]},
    "flag": {"dtype": "bool", "values": [False, True, True, True, None]},
    "x": {"dtype": "f64", "values": [NAN, NAN, 2.0, 2.0, NAN]},
}
_IN_FORCE = [
    {
        "kind": "filter",
        "expr": {
            "op": "binop",
            "kind": "eq",
            "left": {"op": "col", "name": "status"},
            "right": {"op": "lit", "value": "IF"},
        },
    }
]
_GT = {
    "op": "binop",
    "kind": "gt",
    "left": {"op": "col", "name": "x"},
    "right": {"op": "lit", "value": 1.0},
}


def _case(expr: dict, expected: dict) -> dict:
    return {
        "id": "selection-over-a-test",
        "covers": ["gt"],
        "inputs": _BOOK,
        "selection": _IN_FORCE,
        "expr": expr,
        "case_kind": "selection-value",
        "expected": expected,
        "comparison": {"atol": 0.0, "rtol": 0.0},
    }


def _producer(line: object) -> pl.Series:
    """Return the producer's stored column over the rows the filter keeps."""
    kept = pl.DataFrame(
        {
            "flag": [False, True, True, None],
            "x": [float("nan"), float("nan"), 2.0, float("nan")],
        },
        schema={"flag": pl.Boolean, "x": pl.Float64},
    )
    af = ActuarialFrame(kept)
    af.r = line(af)  # type: ignore[operator]
    return af.collect().get_column("r")


def test_a_combination_a_nan_left_unknown_publishes_a_null() -> None:
    expr = {
        "op": "binop",
        "kind": "and",
        "left": {"op": "col", "name": "flag"},
        "right": _GT,
    }
    # Kept rows: F & unknown, T & unknown, T & T, null & unknown.
    want = [None, None, True, None]
    assert _producer(lambda af: af.flag & (af.x > 1.0)).to_list() == want
    assert verify(_case(expr, {"dtype": "bool", "values": want})) == []


def test_a_comparison_publishes_its_indicator() -> None:
    want = [NAN, NAN, 1.0, NAN]
    stored = _producer(lambda af: af.x > 1.0)
    assert stored.dtype == pl.Float64
    assert verify(_case(_GT, {"dtype": "f64", "values": want})) == []
