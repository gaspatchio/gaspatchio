# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison in arithmetic reads as its 0.0/1.0 indicator, in either order.

``af.loading * (af.age > 60)`` answered the loading where the test held and
nought where it did not, but ``(af.age > 60) * af.loading``, ``(af.age > 60)
* 1.0`` and ``-(af.age > 60)`` raised Python's own ``unsupported operand
type(s) ... 'ConditionExpression'``: the comparison's wrapper carried the
logical operators and none of the arithmetic ones, so the line worked only
with a column on the left. Section 11.1.25 reads a flag beside a number as
the 0 or 1 it indicates, under every operator and on either side, and a
comparison stored as a value is already that 0.0/1.0 double, so each
arithmetic operator on a comparison is now the declared one, per policy as
per period, and answers ``f64``. The reference reader answers the record of
each line the same.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import operator
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)

# Policy 0 is over 2, policy 1 is not: the indicator is [1.0, 0.0].
_BOOK = pl.DataFrame({"k": [5, 1], "x": [2.5, -4.0]})

# (operator, the other operand, the hand answer with the comparison first,
# the hand answer with it second)
_CASES: dict[str, tuple[Callable[[object, object], object], object, list, list]] = {
    "add 1": (operator.add, 1, [2.0, 1.0], [2.0, 1.0]),
    "sub 0.5": (operator.sub, 0.5, [0.5, -0.5], [-0.5, 0.5]),
    "mul 3.0": (operator.mul, 3.0, [3.0, 0.0], [3.0, 0.0]),
    "div 4": (operator.truediv, 4, [0.25, 0.0], [4.0, float("inf")]),
    "floordiv 2": (operator.floordiv, 2, [0.0, 0.0], [2.0, float("inf")]),
    "mod 2": (operator.mod, 2, [1.0, 0.0], [0.0, float("nan")]),
    "pow 3": (operator.pow, 3, [1.0, 0.0], [3.0, 1.0]),
}


def _same(got: list[float], hand: list[float]) -> bool:
    return all(
        (math.isnan(g) and math.isnan(h)) or g == h
        for g, h in zip(got, hand, strict=True)
    )


@pytest.mark.parametrize("case", sorted(_CASES))
@pytest.mark.parametrize(
    "first", [True, False], ids=["comparison-first", "other-first"]
)
def test_a_per_policy_comparison_in_arithmetic(case: str, *, first: bool) -> None:
    apply, other, hand_first, hand_second = _CASES[case]
    af = ActuarialFrame(_BOOK)
    af.r = apply(af.k > 2, other) if first else apply(other, af.k > 2)

    result = af.collect()["r"]

    assert result.dtype == pl.Float64
    assert _same(result.to_list(), hand_first if first else hand_second)


@pytest.mark.parametrize("case", sorted(_CASES))
def test_a_per_period_comparison_in_arithmetic(case: str) -> None:
    apply, other, hand_first, _ = _CASES[case]
    af = ActuarialFrame(_BOOK).projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=1, frequency="monthly"
    )
    # month >= 1 is [0.0, 1.0] on every policy; hand_first[1] is the false answer.
    af.r = apply(af.month >= 1, other)

    result = af.collect()["r"]

    assert result.dtype == pl.List(pl.Float64)
    for row in result.to_list():
        assert _same(row, [hand_first[1], hand_first[0]])


def test_a_comparison_beside_a_column_reads_alike_in_either_order() -> None:
    af = ActuarialFrame(_BOOK)
    af.left = (af.k > 2) * af.x
    af.right = af.x * (af.k > 2)

    out = af.collect()

    assert out["left"].to_list() == [2.5, -0.0]
    assert out["right"].to_list() == [2.5, -0.0]


def test_two_comparisons_combine_as_two_indicators() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = (af.k > 2) + (af.k > 0) - (af.x > 0)

    assert af.collect()["r"].to_list() == [1.0, 1.0]


def test_a_comparison_negated_is_its_indicator_negated() -> None:
    af = ActuarialFrame(_BOOK)
    af.r = -(af.k > 2)

    assert af.collect()["r"].to_list() == [-1.0, -0.0]


def test_the_reference_reader_answers_the_record_alike() -> None:
    sys.path.insert(0, str(_CONFORMANCE))
    try:
        from reader.shared import Column
        from reference import Reader
    finally:
        sys.path.remove(str(_CONFORMANCE))
    af = ActuarialFrame(_BOOK)
    af.r = (af.k > 2) * 1.0 - 0.5
    tree = next(
        node["expr"]
        for node in json.loads(GraphExporter(af).export(profile="executable"))["nodes"]
        if node.get("column") == "r" and "expr" in node
    )
    book = {"k": Column("i64", [5, 1]), "x": Column("f64", [2.5, -4.0])}

    answer = Reader(book, [], {}).evaluate(tree)

    assert answer.dtype == "f64"
    assert answer.values == [0.5, -0.5]
    assert af.collect()["r"].to_list() == [0.5, -0.5]
