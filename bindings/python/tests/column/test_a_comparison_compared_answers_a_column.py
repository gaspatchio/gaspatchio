# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A comparison compared answers a column, never Python's own ``False``.

``af.r = (af.k > 2) == 1`` stored a column of ``False`` on every policy and
raised nothing: the comparison's wrapper had no comparison operators, so
``==`` and ``!=`` fell through to Python's identity test and answered a
Python ``bool``, which the frame stored as a literal. ``<``, ``<=``, ``>``
and ``>=`` raised Python's own TypeError, and per period a comparison beside
a column failed when the frame ran, in Polars' words. Each comparison on a
comparison is now the declared one: it records one comparison over the
other, and answers as a stored flag compared does -- per policy by its truth
value, per period by its 0.0/1.0 indicator (section 11.1.26).
"""

from __future__ import annotations

import datetime as dt
import json
import operator
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import BinOp, Lit
from gaspatchio.assumptions import Table
from gaspatchio.column.condition_expression import ConditionExpression
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)

# k > 2 holds for policy 0 and not policy 1, so its indicator is [1.0, 0.0];
# k > 4 is the same; b is a stored flag, [True, False]; x is a decimal.
_BOOK = pl.DataFrame({"k": [5, 1], "x": [2.5, -1.0], "b": [True, False]})
_TEST = [1.0, 0.0]

_COMPARISONS: dict[str, Callable[[object, object], object]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}

# Each other operand: how to write it, and its value at each policy by hand.
_OTHERS: dict[str, tuple[Callable[[ActuarialFrame], object], list[float]]] = {
    "1": (lambda _: 1, [1.0, 1.0]),
    "0.5": (lambda _: 0.5, [0.5, 0.5]),
    "True": (lambda _: True, [1.0, 1.0]),
    "another comparison": (lambda af: af.k > 4, [1.0, 0.0]),
    "a decimal column": (lambda af: af.x, [2.5, -1.0]),
    "a stored flag": (lambda af: af.b, [1.0, 0.0]),
}


def _hand(op: str, left: list[float], right: list[float]) -> list[float]:
    return [float(_COMPARISONS[op](a, b)) for a, b in zip(left, right, strict=True)]


@pytest.mark.parametrize("other", sorted(_OTHERS))
@pytest.mark.parametrize("op", sorted(_COMPARISONS))
@pytest.mark.parametrize(
    "first", [True, False], ids=["comparison-first", "other-first"]
)
def test_a_per_policy_comparison_compared(op: str, other: str, *, first: bool) -> None:
    write, values = _OTHERS[other]
    af = ActuarialFrame(_BOOK)
    compare = _COMPARISONS[op]
    value = compare(af.k > 2, write(af)) if first else compare(write(af), af.k > 2)

    assert not isinstance(value, bool)
    af.r = value
    result = af.collect()["r"]

    assert result.dtype == pl.Float64
    hand = _hand(op, _TEST, values) if first else _hand(op, values, _TEST)
    assert result.to_list() == hand


@pytest.mark.parametrize("other", sorted(_OTHERS))
@pytest.mark.parametrize("op", sorted(_COMPARISONS))
def test_a_per_period_comparison_compared(op: str, other: str) -> None:
    write, values = _OTHERS[other]
    af = ActuarialFrame(_BOOK).projection.set(
        start_date=dt.date(2025, 1, 1), n_periods=2, frequency="monthly"
    )
    af.r = _COMPARISONS[op](af.month >= 1, write(af))

    result = af.collect()["r"]

    assert result.dtype == pl.List(pl.Float64)
    # month >= 1 is [0.0, 1.0, 1.0] on every policy.
    for row, value in zip(result.to_list(), values, strict=True):
        assert row == _hand(op, [0.0, 1.0, 1.0], [value] * 3)


def test_the_line_the_defect_was_found_on() -> None:
    af = ActuarialFrame(_BOOK)
    condition = (af.k > 2) == 1
    af.r = condition

    assert isinstance(condition, ConditionExpression)
    assert af.collect()["r"].to_list() == [1.0, 0.0]


def test_the_record_holds_one_comparison_over_the_other() -> None:
    af = ActuarialFrame(_BOOK)
    node = ((af.k > 2) != 1)._node  # noqa: SLF001

    assert isinstance(node, BinOp)
    assert node.op == "ne"
    assert isinstance(node.left, BinOp)
    assert node.left.op == "gt"
    assert node.right == Lit(1)


@pytest.mark.parametrize("periods", [False, True], ids=["per-policy", "per-period"])
def test_a_comparison_compared_is_a_when_condition(*, periods: bool) -> None:
    af = ActuarialFrame(_BOOK)
    if periods:
        af = af.projection.set(
            start_date=dt.date(2025, 1, 1), n_periods=1, frequency="monthly"
        )
        # The two tests agree where the month is 1 on policy 0 (both true)
        # and at month 0 on policy 1 (both false).
        af.r = when((af.month >= 1) == (af.x > 0)).then(10.0).otherwise(-1.0)
        assert af.collect()["r"].to_list() == [[-1.0, 10.0], [10.0, -1.0]]
        return
    # k > 2 and x > 0 agree on both policies.
    af.r = when((af.k > 2) == (af.x > 0)).then(10.0).otherwise(-1.0)
    assert af.collect()["r"].to_list() == [10.0, 10.0]


def test_a_lookup_compared_with_a_comparison() -> None:
    table = Table(
        name="comparison_compared_rates",
        source=pl.DataFrame({"k": [1, 5], "rate": [0.0, 1.0]}),
        dimensions={"k": "k"},
        value="rate",
    )
    af = ActuarialFrame(_BOOK)
    # The rate is 1.0 for k = 5 and 0.0 for k = 1: the test's own indicator.
    af.same = table.lookup(k=af.k) == (af.k > 2)
    af.other_way = (af.k > 2) != table.lookup(k=af.k)

    out = af.collect()

    assert out["same"].to_list() == [1.0, 1.0]
    assert out["other_way"].to_list() == [0.0, 0.0]


def test_the_reference_reader_answers_the_record_alike() -> None:
    sys.path.insert(0, str(_CONFORMANCE))
    try:
        from reader.shared import Column
        from reference import Reader
    finally:
        sys.path.remove(str(_CONFORMANCE))
    af = ActuarialFrame(_BOOK)
    af.r = (af.k > 2) >= (af.x > 0)
    tree = next(
        node["expr"]
        for node in json.loads(GraphExporter(af).export(profile="executable"))["nodes"]
        if node.get("column") == "r" and "expr" in node
    )
    book = {
        "k": Column("i64", [5, 1]),
        "x": Column("f64", [2.5, -1.0]),
        "b": Column("bool", [True, False]),
    }

    answer = Reader(book, [], {}).evaluate(tree)

    assert answer.values == [1.0, 1.0]
    assert af.collect()["r"].to_list() == [1.0, 1.0]
