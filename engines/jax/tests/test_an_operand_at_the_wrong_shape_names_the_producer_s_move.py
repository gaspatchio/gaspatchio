# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A guess, an initial value or a broadcast value held per period is refused by name.

The declaration refused each of these where the operand is an input. Where it
is a calculation, which declares no shape, the lowering read it anyway: a guess
held per period was answered as if it were one per policy, an initial value
held per period failed with an array error, and a broadcast of a per-period
value answered a list of the wrong numbers. Each is refused there too now,
naming the reference producer's own move -- which refuses the first two by
name -- and a ``freq`` no interval names names the move the producer names
rather than sending a reader to Polars, which refuses it as well.
"""

from __future__ import annotations

from typing import Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from tests.conftest import invocation
from tests.test_final_domains import call, col, lit

INPUTS: dict[str, dict[str, object]] = {
    "cf": {"dtype": "list[f64]", "values": [[-100.0, 60.0, 60.0]]},
    "g": {"dtype": "f64", "values": [0.1]},
    "gl": {"dtype": "list[f64]", "values": [[0.1, 0.1, 0.1]]},
    "i0": {"dtype": "f64", "values": [100.0]},
    "i0l": {"dtype": "list[f64]", "values": [[100.0, 100.0]]},
    "mu": {"dtype": "list[f64]", "values": [[1.01, 1.02]]},
    "ad": {"dtype": "list[f64]", "values": [[1.0, 1.0]]},
    "x": {"dtype": "f64", "values": [2.0]},
    "r": {"dtype": "f64", "values": [0.05]},
    "n": {"dtype": "f64", "values": [2.0]},
    "p": {"dtype": "f64", "values": [10.0]},
    "xl": {"dtype": "list[f64]", "values": [[2.0, 3.0]]},
    "axl": {"dtype": "list[i64]", "values": [[0, 1, 2]]},
    "d": {"dtype": "date", "values": ["2025-05-17"]},
}


def _nested(name: str) -> dict[str, Any]:
    return {"op": "binop", "kind": "add", "left": col(name), "right": lit(0.0)}


# The call over a per-period calculation, what it answers, and what the
# refusal must say.
REFUSED: dict[str, tuple[dict[str, Any], str, tuple[str, ...]]] = {
    "a guess per period": (
        call("excel.irr", col("cf"), _nested("gl"), default_guess=0.2),
        "f64",
        ("excel.irr is written over one value per period", "write the guess once"),
    ),
    "an initial value per period": (
        call(
            "projection.accumulate", _nested("i0l"), col("mu"), col("ad"), reverse=False
        ),
        "list[f64]",
        (
            "projection.accumulate is written over one value per period",
            "write the initial value once per policy",
        ),
    ),
    "a broadcast of a per-period value": (
        call("projection.broadcast_to_periods", _nested("xl"), col("axl")),
        "list[f64]",
        ("broadcast_to_periods is written over one value per period",),
    ),
}


@pytest.mark.parametrize("case", REFUSED, ids=list(REFUSED))
def test_a_calculation_at_the_wrong_shape_is_refused_by_name(case: str) -> None:
    expr, answers, said = REFUSED[case]
    one = invocation(expr, INPUTS, answers)
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    rendered = " ".join(refused.value.report.render().split())
    for words in said:
        assert words in rendered


def test_a_freq_no_interval_names_names_the_producer_s_move() -> None:
    one = invocation(call("date.to_period", col("d"), freq="Q"), INPUTS, "date")
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    rendered = " ".join(refused.value.report.render().split())
    assert "write freq as Y, M, W or D" in rendered
    assert "run this model on Polars, or keep" not in rendered


@pytest.mark.parametrize(
    ("expr", "answers"),
    [
        (call("excel.irr", col("cf"), _nested("g"), default_guess=0.2), "f64"),
        (
            call(
                "projection.accumulate",
                _nested("i0"),
                col("mu"),
                col("ad"),
                reverse=False,
            ),
            "list[f64]",
        ),
        (
            call("projection.broadcast_to_periods", _nested("x"), col("axl")),
            "list[f64]",
        ),
    ],
    ids=["guess", "initial", "broadcast"],
)
def test_one_value_per_policy_still_answers(expr: dict[str, Any], answers: str) -> None:
    one = invocation(expr, INPUTS, answers)
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert result.columns["answer"].to_list()[0] is not None


def test_a_per_period_excel_pv_calculation_answers_the_per_policy_cells() -> None:
    """11.1.35 states excel.pv per period; a calculation held per period is one.

    A per-period operand that is itself a calculation declares no shape, and
    reached the annuity as an array error and then as a refusal naming
    Polars. Each period now answers what the same three operands answer per
    policy -- the per-policy figure at period 0, the next at period 1.
    """
    expr = call("excel.pv", _nested("xl"), col("n"), col("p"), fv=50.0, typ=None)
    listed = invocation(expr, INPUTS, "list[f64]")
    per_period = JaxEngine().run(listed.document, listed.inputs, FrameSink())
    each = {
        "r": {"dtype": "f64", "values": [2.0, 3.0]},
        "n": {"dtype": "f64", "values": [2.0, 2.0]},
        "p": {"dtype": "f64", "values": [10.0, 10.0]},
    }
    flat = call("excel.pv", _nested("r"), col("n"), col("p"), fv=50.0, typ=None)
    one = invocation(flat, each, "f64")
    per_policy = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert per_period.columns["answer"].to_list() == [
        per_policy.columns["answer"].to_list()
    ]
