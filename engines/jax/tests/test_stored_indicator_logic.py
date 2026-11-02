# SPDX-FileCopyrightText: 2026 Opio Inc.
# SPDX-License-Identifier: Apache-2.0

"""Section 11.1.27's stored indicator: a 0/1 f64 column as a logical operand.

A direct reference to a stored ``f64`` or ``list[f64]`` column is read under
11.1.18's checked rule, as a ``when_then`` condition is; a floating-point
operand that is not a column reference -- a literal, an arithmetic result --
is a number and still refuses.
"""

from __future__ import annotations

from typing import Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from tests.conftest import invocation


def col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def both(kind: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {"op": "binop", "kind": kind, "left": left, "right": right}


def negated(operand: dict[str, Any]) -> dict[str, Any]:
    return {"op": "call", "name": "not_", "args": [operand], "attrs": {}}


def _answer(expr: dict[str, Any], inputs: dict[str, Any], dtype: str) -> list[Any]:
    one = invocation(expr, inputs, dtype)
    return (
        JaxEngine()
        .run(one.document, one.inputs, FrameSink())
        .columns["answer"]
        .to_list()
    )


def test_a_stored_flag_per_policy_reads_as_its_boolean() -> None:
    flags = {"a": {"dtype": "f64", "values": [1.0, 0.0, -0.0]}}
    truths = {"b": {"dtype": "bool", "values": [True, True, False]}}
    inputs = {**flags, **truths}
    assert _answer(both("and", col("a"), col("b")), inputs, "bool") == [
        True,
        False,
        False,
    ]
    assert _answer(both("or", col("b"), col("a")), inputs, "bool") == [
        True,
        True,
        False,
    ]
    assert _answer(negated(col("a")), flags, "bool") == [False, True, True]


def test_a_stored_flag_per_period_is_its_own_zero_one_run() -> None:
    inputs = {
        "a": {"dtype": "list[f64]", "values": [[1.0, 0.0, 1.0], [0.0, -0.0]]},
        "b": {"dtype": "list[bool]", "values": [[True, True, False], [True, False]]},
    }
    assert _answer(both("and", col("a"), col("b")), inputs, "list[f64]") == [
        [1.0, 0.0, 0.0],
        [0.0, 0.0],
    ]
    assert _answer(negated(col("a")), inputs, "list[f64]") == [
        [0.0, 1.0, 0.0],
        [1.0, 1.0],
    ]


@pytest.mark.parametrize("bad", [2.0, 0.5, -1.0])
@pytest.mark.parametrize("shape", ["scalar", "list"])
def test_a_flag_holding_another_number_refuses_by_the_stored_predicate_check(
    bad: float, shape: str
) -> None:
    values = [1.0, bad] if shape == "scalar" else [[1.0, bad]]
    dtype = "f64" if shape == "scalar" else "list[f64]"
    one = invocation(
        negated(col("a")),
        {"a": {"dtype": dtype, "values": values}},
        "bool" if shape == "scalar" else "list[f64]",
    )
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    assert "predicate.stored_f64" in str(caught.value)


@pytest.mark.parametrize(
    "operand",
    [
        {"op": "lit", "value": 1.0},
        both("add", col("a"), {"op": "lit", "value": 0.0}),
    ],
    ids=["literal", "arithmetic"],
)
def test_a_number_that_is_not_a_column_reference_is_not_a_stored_flag(
    operand: dict[str, Any],
) -> None:
    one = invocation(
        both("and", col("b"), operand),
        {
            "a": {"dtype": "f64", "values": [1.0]},
            "b": {"dtype": "bool", "values": [True]},
        },
        "bool",
    )
    with pytest.raises(EngineRefusal) as caught:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    assert any(item.clause == "11.1.27" for item in caught.value.report.refusals)
