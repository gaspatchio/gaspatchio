# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reference reader answers each line in the type the producer's record names.

The reader is the conformance kit's witness, and its ``verify`` compares a
result's type label with the case's before it compares a value, so a label
that contradicts the record fails a conforming producer. It kept a whole
number's ``i64`` label under ``sqrt``, ``exp`` and the logarithms, and under
``list.mean``, while it held doubles; ``fill_null`` of a whole number with a
double kept ``i64`` where section 11.1.13 says ``f64``; and several calls held
a whole number under an ``f64`` label, or a flag under an ``i64`` one, which a
comparison of values alone cannot see because 2 equals 2.0.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reader import shared  # noqa: E402
from reader.shared import Column  # noqa: E402
from reference import Reader, verify  # noqa: E402

_BOOK = pl.DataFrame(
    [
        pl.Series("n", [4, 9, None], dtype=pl.Int64),
        pl.Series("i", [4, -7, None], dtype=pl.Int64),
        pl.Series("f", [2.5, -1.25, None], dtype=pl.Float64),
        pl.Series("b", [True, False, None]),
        pl.Series(
            "L", [[2, 9, 3], [5, 1, 1], [100, 101, 101]], dtype=pl.List(pl.Int64)
        ),
        pl.Series(
            "Ln", [[2, None, 3], [5, 1, 1], [None, 2, 3]], dtype=pl.List(pl.Int64)
        ),
        pl.Series("Lf", [[0.5, None, 3.5], [1.0, 0.25, 4.0], [-3.5, 2.0, 2.0]]),
        pl.Series("Lq", [[0.1, 0.2, 0.3], [0.0, 0.5, 0.5], [0.25, 0.0, 0.0]]),
        pl.Series(
            "Lb", [[True, False, True], [False, False, True], [True, True, True]]
        ),
    ]
)
_COLUMNS = {
    "n": Column("i64", [4, 9, None]),
    "i": Column("i64", [4, -7, None]),
    "f": Column("f64", [2.5, -1.25, None]),
    "b": Column("bool", [True, False, None]),
    "L": Column("list[i64]", [[2, 9, 3], [5, 1, 1], [100, 101, 101]]),
    "Ln": Column("list[i64]", [[2, None, 3], [5, 1, 1], [None, 2, 3]]),
    "Lf": Column("list[f64]", [[0.5, None, 3.5], [1.0, 0.25, 4.0], [-3.5, 2.0, 2.0]]),
    "Lq": Column("list[f64]", [[0.1, 0.2, 0.3], [0.0, 0.5, 0.5], [0.25, 0.0, 0.0]]),
    "Lb": Column(
        "list[bool]", [[True, False, True], [False, False, True], [True, True, True]]
    ),
}
_E, _LN = math.exp, math.log

# Each line, the type its record names, and its answer by hand.
_LINES: dict[str, tuple[Callable[[ActuarialFrame], object], str, list]] = {
    "sqrt of a whole number": (lambda af: af.n.sqrt(), "f64", [2.0, 3.0, None]),
    "cbrt of a whole number": (
        lambda af: af.n.cbrt(),
        "f64",
        [4 ** (1 / 3), 9 ** (1 / 3), None],
    ),
    "exp of a whole number": (lambda af: af.n.exp(), "f64", [_E(4), _E(9), None]),
    "log of a whole number": (lambda af: af.n.log(), "f64", [_LN(4), _LN(9), None]),
    "log10 of a whole number": (
        lambda af: af.n.log10(),
        "f64",
        [math.log10(4), math.log10(9), None],
    ),
    "log1p of a whole number": (
        lambda af: af.n.log1p(),
        "f64",
        [_LN(5), _LN(10), None],
    ),
    "sqrt of a run of whole numbers": (
        lambda af: af.L.sqrt(),
        "list[f64]",
        [[2**0.5, 3.0, 3**0.5], [5**0.5, 1.0, 1.0], [10.0, 101**0.5, 101**0.5]],
    ),
    "abs of a whole number": (lambda af: af.i.abs(), "i64", [4, 7, None]),
    "sign of a whole number": (lambda af: af.i.sign(), "i64", [1, -1, None]),
    "floor of a whole number": (lambda af: af.i.floor(), "i64", [4, -7, None]),
    "ceil of a run of whole numbers": (
        lambda af: af.L.ceil(),
        "list[i64]",
        [[2, 9, 3], [5, 1, 1], [100, 101, 101]],
    ),
    "mean of a run of whole numbers": (
        lambda af: af.L.list.mean(),
        "f64",
        [14 / 3, 7 / 3, 302 / 3],
    ),
    "mean of a run of flags": (
        lambda af: af.Lb.list.mean(),
        "f64",
        [2 / 3, 1 / 3, 1.0],
    ),
    "sum of a run of whole numbers": (lambda af: af.L.list.sum(), "i64", [14, 7, 302]),
    "running sum of a run of flags": (
        lambda af: af.Lb.cum_sum(reverse=False),
        "list[i64]",
        [[1, 1, 2], [0, 0, 1], [1, 2, 3]],
    ),
    "running product of a run of flags": (
        lambda af: af.Lb.cum_prod(reverse=False),
        "list[i64]",
        [[1, 0, 0], [0, 0, 0], [1, 1, 1]],
    ),
    "remaining sum of a run of flags": (
        lambda af: af.Lb.projection.remaining_sum(),
        "list[i64]",
        [[2, 1, 1], [1, 1, 1], [3, 2, 1]],
    ),
    "a whole number filled with a double": (
        lambda af: af.i.fill_null(7.5),
        "f64",
        [4.0, -7.0, 7.5],
    ),
    "a whole number filled with a column of doubles": (
        lambda af: af.i.fill_null(af.f),
        "f64",
        [4.0, -7.0, None],
    ),
    "a whole number filled with a flag": (
        lambda af: af.i.fill_null(True),  # noqa: FBT003
        "i64",
        [4, -7, 1],
    ),
    "a double filled with a whole number": (
        lambda af: af.f.fill_null(7),
        "f64",
        [2.5, -1.25, 7.0],
    ),
    "a double filled with a flag": (
        lambda af: af.f.fill_null(True),  # noqa: FBT003
        "f64",
        [2.5, -1.25, 1.0],
    ),
    "a run of whole numbers filled with a double": (
        lambda af: af.Ln.fill_null(0.5),
        "list[f64]",
        [[2.0, 0.5, 3.0], [5.0, 1.0, 1.0], [0.5, 2.0, 3.0]],
    ),
    "a run of doubles filled with a whole number": (
        lambda af: af.Lf.fill_null(1),
        "list[f64]",
        [[0.5, 1.0, 3.5], [1.0, 0.25, 4.0], [-3.5, 2.0, 2.0]],
    ),
    "a double clipped by whole-number bounds": (
        lambda af: af.f.clip(0, 5),
        "f64",
        [2.5, 0.0, None],
    ),
    "a whole number put into a run of whole numbers": (
        lambda af: af.L.projection.with_period(1, 7),
        "list[i64]",
        [[2, 7, 3], [5, 7, 1], [100, 7, 101]],
    ),
    "a double put into a run of whole numbers": (
        lambda af: af.L.projection.with_period(1, 7.5),
        "list[f64]",
        [[2.0, 7.5, 3.0], [5.0, 7.5, 1.0], [100.0, 7.5, 101.0]],
    ),
    "a spreadsheet's round of a whole number": (
        lambda af: (af.i * 0).excel.round(0),
        "f64",
        [0.0, 0.0, None],
    ),
    "a spreadsheet's present value at a whole-number future value": (
        lambda af: (af.n * 0).excel.pv(af.n * 0 + 1, af.n, fv=1),
        "f64",
        [-5.0, -10.0, None],
    ),
    "survival opened at a whole number": (
        lambda af: af.Lq.projection.cumulative_survival(start_at=1),
        "list[f64]",
        [[1.0, 0.9, 0.9 * 0.8], [1.0, 1.0, 0.5], [1.0, 0.75, 0.75]],
    ),
}


def _held(values: list) -> list:
    return [_held(v) if isinstance(v, list) else type(v).__name__ for v in values]


def _close(actual: object, hand: object) -> bool:
    if isinstance(hand, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(hand)
            and all(map(_close, actual, hand))
        )
    if hand is None or actual is None:
        return actual is hand
    if type(actual) is not type(hand):
        return False
    return actual == hand or math.isclose(actual, hand, rel_tol=1e-12)


@pytest.mark.parametrize("line", sorted(_LINES))
def test_the_reader_answers_the_type_the_record_names(line: str) -> None:
    write, dtype, hand = _LINES[line]
    af = ActuarialFrame(_BOOK)
    af.r = write(af)
    document = json.loads(GraphExporter(af).export(profile="executable"))
    node = next(n for n in document["nodes"] if n.get("column") == "r")

    answer = Reader(_COLUMNS, document.get("assumptions", []), {}).evaluate(
        node["expr"]
    )

    assert node["dtype"] == dtype
    assert answer.dtype == dtype
    assert not shared.contradicts(answer), _held(answer.values)
    assert _close(answer.values, hand), answer.values
    assert _close(answer.values, af.collect()["r"].to_list())


@pytest.mark.parametrize(
    "column",
    [
        Column("i64", [2.0]),
        Column("i64", [True]),
        Column("f64", [2]),
        Column("list[f64]", [[1.0, 2]]),
        Column("list[i64]", [[1, 2.0]]),
        Column("bool", [1]),
    ],
)
def test_a_value_held_as_another_type_than_its_label_is_seen(column: Column) -> None:
    assert shared.contradicts(column)


@pytest.mark.parametrize(
    "column",
    [
        Column("i64", [2, None, -7]),
        Column("f64", [2.0, None]),
        Column("list[f64]", [[1.0, None], None, []]),
        Column("str", ["a", None]),
    ],
)
def test_a_value_held_as_its_label_is_not_flagged(column: Column) -> None:
    assert not shared.contradicts(column)


_A_FILL_CASE = {
    "id": "a-fill-held-whole",
    "case_kind": "value",
    "inputs": {"x": {"dtype": "f64", "values": [None, 2.5]}},
    "expr": {
        "op": "call",
        "name": "fill_null",
        "args": [{"op": "col", "name": "x"}, {"op": "lit", "value": 7}],
        "attrs": {},
    },
    "expected": {"dtype": "f64", "values": [7.0, 2.5]},
    "comparison": {"atol": 0.0, "rtol": 0.0},
}


def test_a_whole_number_fill_is_held_as_the_double_its_label_names() -> None:
    # The fill is the literal 7, so an answer that kept it whole under the
    # f64 label equalled the expected 7.0 value for value and passed.
    answer = Reader({"x": Column("f64", [None, 2.5])}, [], {}).evaluate(
        _A_FILL_CASE["expr"]
    )

    assert verify(_A_FILL_CASE) == []
    assert _held(answer.values) == ["float", "float"]


def test_verify_fails_an_answer_held_as_another_type_than_its_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def whole(*_arguments: object, **_keywords: object) -> Column:
        return Column("f64", [7, 2.5])

    monkeypatch.setattr(Reader, "evaluate", whole)

    assert verify(_A_FILL_CASE) == ["values: held as another type than f64"]


def test_every_published_case_is_held_as_its_label() -> None:
    vectors = _CONFORMANCE.parents[2] / "bindings/python/gaspatchio/schemas/vectors"
    checked = 0
    for bundle in sorted(vectors.glob("*.json")):
        for case in json.loads(bundle.read_text())["cases"]:
            assert verify(case) == [], case["id"]
            checked += 1
    assert checked > 0
