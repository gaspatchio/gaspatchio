# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Text orders by code point, per policy and per period, as the producer orders it.

Section 11.1.26: "Scalar text uses lexicographic Unicode order", and "List-shaped
text compares period by period under the same rule -- exact equality, order by
code point". This engine held text as one run's interned codes and refused the
four orderings over them ("lt is written over text"), so a model the producer
ran -- a filter on ``plan >= "UL"``, a ``when(plan > "TERM")`` -- did not run
here. It now reads each code's rank among the run's strings sorted by code
point, so the answers are the producer's, and the codes themselves still mean
nothing beyond which string they stand for.
"""

from __future__ import annotations

import datetime
import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from gaspatchio import ActuarialFrame, when
from gaspatchio.engines.protocol import FrameSink
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.interning import Dictionary
from tests.conftest import invocation

if TYPE_CHECKING:
    from collections.abc import Callable

_ORDERINGS: dict[str, Callable[[str, str], bool]] = {
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "eq": operator.eq,
    "ne": operator.ne,
}
# Code-point order: "" < "B" < "a" < "ab" < "abc" < "b" < "é" < "😀". The
# capital before the small letter, a prefix before its extension, an accent
# after every ASCII letter and a character beyond the basic plane last.
_LEFT = ["a", "B", "ab", "", "é", "😀", "abc", "b"]
_RIGHT = ["ab", "a", "ab", "a", "z", "é", "ab", "B"]


def _col(name: str) -> dict:
    return {"op": "col", "name": name}


def _binop(kind: str, left: dict, right: dict) -> dict:
    return {"op": "binop", "kind": kind, "left": left, "right": right}


def _answer(expr: dict, inputs: dict, dtype: str) -> list:
    one = invocation(expr, inputs, dtype)
    return (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()
    )


@pytest.mark.parametrize("kind", sorted(_ORDERINGS))
def test_one_value_per_policy_orders_by_code_point(kind: str) -> None:
    got = _answer(
        _binop(kind, _col("a"), _col("b")),
        {
            "a": {"dtype": "str", "values": _LEFT},
            "b": {"dtype": "str", "values": _RIGHT},
        },
        "f64",
    )
    assert got == [
        float(_ORDERINGS[kind](x, y)) for x, y in zip(_LEFT, _RIGHT, strict=True)
    ]


def test_a_literal_on_either_side_orders_by_code_point() -> None:
    inputs = {"a": {"dtype": "str", "values": _LEFT}}
    right = _answer(
        _binop("lt", _col("a"), {"op": "lit", "value": "ab"}), inputs, "f64"
    )
    left = _answer(_binop("gt", {"op": "lit", "value": "b"}, _col("a")), inputs, "f64")
    assert right == [1.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    assert left == [1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0]


@pytest.mark.parametrize("kind", ["lt", "ge"])
def test_one_value_per_period_orders_period_by_period(kind: str) -> None:
    runs = [["a", "B", "é"], ["", "zz"]]
    others = [["b", "B", "e"], ["a", "z"]]
    got = _answer(
        _binop(kind, _col("r"), _col("s")),
        {
            "r": {"dtype": "list[str]", "values": runs},
            "s": {"dtype": "list[str]", "values": others},
        },
        "list[f64]",
    )
    hand = {"lt": [[1.0, 0.0, 0.0], [1.0, 0.0]], "ge": [[0.0, 1.0, 1.0], [0.0, 1.0]]}
    assert got == hand[kind]


def test_a_run_against_one_value_per_policy_and_a_literal() -> None:
    inputs = {
        "r": {"dtype": "list[str]", "values": [["a", "B", "é"], ["", "zz"]]},
        "p": {"dtype": "str", "values": ["B", "z"]},
    }
    assert _answer(_binop("lt", _col("r"), _col("p")), inputs, "list[f64]") == [
        [0.0, 0.0, 0.0],
        [1.0, 0.0],
    ]
    assert _answer(
        _binop("gt", {"op": "lit", "value": "b"}, _col("r")), inputs, "list[f64]"
    ) == [[1.0, 1.0, 0.0], [1.0, 0.0]]


def test_the_rank_is_read_from_the_strings_and_not_from_the_codes() -> None:
    """Interned in an order that is not the strings' order, ranked by the strings."""
    from gaspatchio_jax.lowerings.comparisons import code_point_ranks

    interned = Dictionary()
    for text in ("z", "B", "a", ""):
        interned.code_for(text)
    ranks = code_point_ranks(interned)
    # Slot 0 is the absent key's, below every string; then codes 0..3.
    assert ranks.tolist() == [-1, 3, 1, 2, 0]


def test_a_model_ordering_text_runs_through_the_frame_door_as_on_polars() -> None:
    """A filter, a when() and a stored indicator, over jagged timelines."""
    plans = ["TERM", "Whole", "annuity", "UL", "ÉPARGNE", "term"]
    book = pl.DataFrame(
        {
            "policy_id": [f"P{i:03d}" for i in range(40)],
            "plan": [plans[i % 6] for i in range(40)],
            "term_m": [12 * (1 + i % 7) for i in range(40)],
            "sa": [1000.0 * (i + 1) for i in range(40)],
        }
    )
    af = ActuarialFrame(book)
    af = af.filter(af.plan >= "UL")
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value="term_m",
        frequency="annual",
    )
    af.before_whole = af.plan < "Whole"
    af.amount = when(af.plan > "TERM").then(af.sa).otherwise(0.0)
    af.early = af.policy_id <= "P020"

    columns = ["policy_id", "plan", "before_whole", "amount", "early"]
    reference = af.collect().select(columns)
    engine = af.collect(engine="jax").select(columns)

    assert_frame_equal(engine, reference, check_exact=True)
    # By hand: "UL" < "Whole" < "annuity" < "term" < "ÉPARGNE", so "TERM" is
    # the one plan dropped, and only "UL" sorts before "Whole".
    assert sorted(set(engine["plan"])) == ["UL", "Whole", "annuity", "term", "ÉPARGNE"]
    assert set(engine.filter(pl.col("before_whole") == 1.0)["plan"]) == {"UL"}
