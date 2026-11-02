# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A Boolean in arithmetic reads as its 0.0 or 1.0, per policy and per period.

Section 11.1.25: "A Boolean operand reads as the 0 or 1 it indicates", and the
answer is ``f64`` whatever the other operand is -- which is what the reference
producer answers for ``af.smoker + 1``, ``2 // af.smoker`` and
``af.in_force * 1.0``. This engine refused every such line by capability
("add is written over a Boolean at operand 0"), so a model the producer ran
did not run here. It now answers each line as the producer does, exactly, and
still refuses the one form the clause excludes: a per-policy flag on both
sides of one operation.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio import ActuarialFrame
from tests.conftest import answered, invocation

if TYPE_CHECKING:
    from collections.abc import Callable

_OPERATORS: dict[str, Callable[[object, object], object]] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "div": operator.truediv,
    "floordiv": operator.floordiv,
    "mod": operator.mod,
    "pow": operator.pow,
}
_OTHERS: dict[str, Callable[[ActuarialFrame], object]] = {
    "2": lambda _: 2,
    "2.0": lambda _: 2.0,
    "an i64 column": lambda af: af.n,
    "an f64 column": lambda af: af.x,
}
_BOOK = pl.DataFrame(
    {"smoker": [True, False], "n": [2, 3], "x": [0.5, 0.5]},
)


def _both(af: ActuarialFrame, column: str) -> tuple[pl.Series, pl.Series]:
    return af.collect()[column], af.collect(engine="jax")[column]


@pytest.mark.parametrize("op", sorted(_OPERATORS))
@pytest.mark.parametrize("other", sorted(_OTHERS))
@pytest.mark.parametrize("flag_first", [True, False], ids=["flag op", "op flag"])
def test_a_per_policy_flag_answers_as_the_producer_does(
    op: str, other: str, *, flag_first: bool
) -> None:
    af = ActuarialFrame(_BOOK)
    apply, beside = _OPERATORS[op], _OTHERS[other](af)
    af.r = apply(af.smoker, beside) if flag_first else apply(beside, af.smoker)

    reference, engine = _both(af, "r")

    assert engine.dtype == pl.Float64
    assert_series_equal(engine, reference, check_exact=True)


def test_hand_values_per_policy() -> None:
    af = ActuarialFrame(_BOOK)
    af.b = af.smoker + 1
    af.d = 2 // af.smoker
    af.e = 2.0**af.smoker

    out = af.collect(engine="jax")

    assert out["b"].to_list() == [2.0, 1.0]
    assert out["d"].to_list() == [2.0, float("inf")]
    assert out["e"].to_list() == [2.0, 1.0]


@pytest.mark.parametrize("op", sorted(_OPERATORS))
def test_a_per_period_flag_answers_as_the_producer_does(op: str) -> None:
    af = ActuarialFrame(
        pl.DataFrame({"flags": [[True, False], [False, True]], "x": [0.5, 2.0]})
    )
    af.r = _OPERATORS[op](af.flags, af.x)

    reference, engine = _both(af, "r")

    assert engine.dtype == pl.List(pl.Float64)
    assert_series_equal(engine, reference, check_exact=True)


def test_a_comparison_beside_a_flag_is_a_number_and_answers() -> None:
    """11.1.26's indicator is a number, so one flag and one comparison is one flag."""
    af = ActuarialFrame(_BOOK)
    af.r = (af.n > 2) + af.smoker

    reference, engine = _both(af, "r")

    assert engine.to_list() == [1.0, 1.0]
    assert_series_equal(engine, reference, check_exact=True)


def test_two_per_policy_flags_in_one_operation_are_refused() -> None:
    """The one Boolean form 11.1.25 excludes, in a document no producer writes."""
    outcome = answered(
        invocation(
            {
                "op": "binop",
                "kind": "add",
                "left": {"op": "col", "name": "smoker"},
                "right": {"op": "col", "name": "rider"},
            },
            {
                "smoker": {"dtype": "bool", "values": [True, False]},
                "rider": {"dtype": "bool", "values": [True, True]},
            },
            "f64",
        )
    )

    assert outcome.value is None
    assert "one value per policy each, and only one side of it may be" in (
        outcome.report
    )


def test_a_flag_beside_a_nested_flag_is_refused_where_the_lowering_meets_it() -> None:
    """The record states no type for ``smoker & rider``; the lowering refuses it."""
    outcome = answered(
        invocation(
            {
                "op": "binop",
                "kind": "mul",
                "left": {
                    "op": "binop",
                    "kind": "and",
                    "left": {"op": "col", "name": "smoker"},
                    "right": {"op": "col", "name": "rider"},
                },
                "right": {"op": "col", "name": "smoker"},
            },
            {
                "smoker": {"dtype": "bool", "values": [True, False]},
                "rider": {"dtype": "bool", "values": [True, True]},
            },
            "f64",
        )
    )

    assert outcome.value is None
    assert "arithmetic between two per-policy flags is not admitted" in outcome.report
