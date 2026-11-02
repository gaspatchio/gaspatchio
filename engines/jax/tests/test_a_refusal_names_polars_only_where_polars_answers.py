# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A capability refusal sends a reader to Polars only where Polars answers.

Every tree refusal named one move -- "run this model on Polars, or keep the
column out of the artifact" -- including where the reference producer refuses
the same line: a fold over a per-policy value, a month move over a value per
period, a rate held per period in a scalar valuation, a flag widened to a
double. A registration now states, per declaration, the move a refusal names
where the producer refuses it too, and only the rest name Polars.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from gaspatchio_jax.lowerings import LOWERINGS, load
from tests.conftest import invocation
from tests.test_final_domains import call, col

if TYPE_CHECKING:
    from gaspatchio_jax.capability import Capability

ON_POLARS = "run this model on Polars"

INPUTS: dict[str, dict[str, object]] = {
    "d": {"dtype": "date", "values": ["2025-01-31"]},
    "e": {"dtype": "date", "values": ["2025-06-30"]},
    "ml": {"dtype": "list[i64]", "values": [[1, 2]]},
    "x": {"dtype": "f64", "values": [100.0]},
    "xl": {"dtype": "list[f64]", "values": [[100.0, 110.0]]},
    "r": {"dtype": "f64", "values": [0.05]},
    "rl": {"dtype": "list[f64]", "values": [[0.05, 0.05]]},
    "n": {"dtype": "f64", "values": [10.0]},
    "flag": {"dtype": "bool", "values": [True]},
}


def _rendered(expr: dict[str, Any], dtype: str) -> str:
    one = invocation(expr, INPUTS, dtype)
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    return " ".join(refused.value.report.render().split())


@pytest.mark.parametrize(
    ("expr", "dtype", "move"),
    [
        (call("excel.edate", col("d"), col("ml")), "list[date]", "per-policy count"),
        (call("sum", col("x")), "f64", "fold the per-period column"),
        (
            call("finance.discount", col("x"), col("rl"), col("n")),
            "f64",
            "prospective_value",
        ),
        (call("to_float", col("flag")), "f64", "when(flag).then(1.0)"),
        (
            call("excel.yearfrac", col("d"), col("e"), basis=9),
            "f64",
            "write basis as 0 to 4",
        ),
    ],
    ids=["edate", "sum", "discount", "to_float", "yearfrac"],
)
def test_a_form_the_producer_refuses_names_its_own_move(
    expr: dict[str, Any], dtype: str, move: str
) -> None:
    rendered = _rendered(expr, dtype)
    assert move in rendered
    assert ON_POLARS not in rendered


@pytest.mark.parametrize(
    ("expr", "dtype"),
    [(call("to_text", col("xl")), "list[str]")],
    ids=["to_text-per-period"],
)
def test_a_form_the_producer_answers_still_names_polars(
    expr: dict[str, Any], dtype: str
) -> None:
    assert ON_POLARS in _rendered(expr, dtype)


def _declared(capability: Capability, key: str) -> bool:
    """Return whether a ``refused_alike`` key names a declaration it makes."""
    kind, _, where = key.partition("@")
    if kind == "shape":
        shapes = capability.shapes or ()
        return int(where) < len(shapes) and len(shapes[int(where)]) == 1
    if kind == "carrier":
        return capability.carriers is not None and int(where) < len(capability.carriers)
    name = key.removeprefix("attr:")
    return key.startswith("attr:") and name in (capability.attrs or {})


def test_every_stated_move_names_a_declaration_the_registration_makes() -> None:
    load()
    stated = {
        (name, key)
        for name, (_lowering, capability) in LOWERINGS.items()
        for key in (capability.refused_alike or {})
    }
    assert stated, "no registration states a move"
    for name, key in sorted(stated):
        assert _declared(LOWERINGS[name][1], key), (name, key)
