# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A tree as deep as a long line writes is lowered or refused by name, no traceback.

A model line summing a few hundred per-rider terms, a ``when`` nested a few
hundred times in its ``otherwise``, or a long conjunction of conditions
exports a tree that deep, and the producer writes such trees to about 245
levels. This engine lowered one operation inside the next, five Python frames
a level, so ``run-artifact`` ran out of Python's call depth at about 190 and
printed a ``RecursionError`` traceback. The operators a line chains are now
lowered from one stack (``gaspatchio_jax.lowerings``, *in steps*); any other
operation nested past the call depth is refused naming the node and its
depth.
"""

from __future__ import annotations

from typing import Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from tests.conftest import invocation

# Deeper than this engine reached before (about 190 levels) and than the
# producer writes (about 245), and inside what the core's reader parses.
DEPTH = 300


def _col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def _lit(value: float) -> dict[str, Any]:
    return {"op": "lit", "value": value}


def _answers(expr: dict[str, Any], values: list[float]) -> list[Any]:
    """Return what this engine answers for one tree over one double column."""
    one = invocation(expr, {"a": {"dtype": "f64", "values": values}}, "f64")
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    return result.columns["answer"].to_list()


def test_a_sum_of_three_hundred_terms_is_lowered() -> None:
    """``a + a + ... + a``, 301 terms: 301 times each policy's ``a``."""
    tree = _col("a")
    for _ in range(DEPTH):
        tree = {"op": "binop", "kind": "add", "left": tree, "right": _col("a")}
    assert _answers(tree, [1.0, 2.5]) == [301.0, 752.5]


def test_a_when_nested_three_hundred_times_in_its_otherwise_is_lowered() -> None:
    """when(a == 0) then 0, otherwise when(a == 1) then 10, ... otherwise -1."""
    tree = _lit(-1.0)
    for band in reversed(range(DEPTH)):
        tree = {
            "op": "when_then",
            "cond": {
                "op": "binop",
                "kind": "eq",
                "left": _col("a"),
                "right": _lit(float(band)),
            },
            "then": _lit(band * 10.0),
            "otherwise": tree,
        }
    assert _answers(tree, [5.0, 250.0, 400.0]) == [50.0, 2500.0, -1.0]


def test_a_conjunction_of_three_hundred_conditions_is_lowered() -> None:
    """(a > 0) and (a > 1) and ... (a > 299): only a policy past 299 holds."""
    tree: dict[str, Any] = {
        "op": "binop",
        "kind": "gt",
        "left": _col("a"),
        "right": _lit(0.0),
    }
    for level in range(1, DEPTH):
        condition = {
            "op": "binop",
            "kind": "gt",
            "left": _col("a"),
            "right": _lit(float(level)),
        }
        tree = {"op": "binop", "kind": "and", "left": tree, "right": condition}
    held = {"op": "when_then", "cond": tree, "then": _lit(1.0), "otherwise": _lit(0.0)}
    assert _answers(held, [250.0, 400.0]) == [0.0, 1.0]


def test_another_operation_nested_past_the_call_depth_is_refused_by_name() -> None:
    """abs(abs(...abs(a))), 300 deep, is not lowered in steps and is refused."""
    tree = _col("a")
    for _ in range(DEPTH):
        tree = {"op": "call", "name": "abs", "args": [tree], "attrs": {}}
    one = invocation(tree, {"a": {"dtype": "f64", "values": [-1.0]}}, "f64")

    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())

    (refusal,) = refused.value.report.refusals
    assert refusal.where == "answer@1"
    assert refusal.clause == "11.1"
    assert f"nests {DEPTH + 1} operations deep" in refusal.what
    assert "named intermediate columns" in refusal.move


def test_a_crafted_sum_past_the_host_s_operand_checks_is_refused_by_name() -> None:
    """400 terms, past any line the producer writes: refused at the operand checks.

    The host checks each call's arriving operands before anything is compiled,
    reading their types one level inside the next; a crafted tree past the
    call depth there is refused in the lowering's own sentence, not raised.
    """
    tree = _col("a")
    for _ in range(400):
        tree = {"op": "binop", "kind": "add", "left": tree, "right": _col("a")}
    one = invocation(tree, {"a": {"dtype": "f64", "values": [1.0]}}, "f64")

    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())

    (refusal,) = refused.value.report.refusals
    assert refusal.where == "answer@1"
    assert "nests 401 operations deep" in refusal.what
