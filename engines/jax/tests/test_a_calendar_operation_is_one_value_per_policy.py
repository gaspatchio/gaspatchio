# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every 11.1.33 operation but excel.yearfrac is refused per period by name.

11.1.33 states its date operations over one value per policy; the reference
producer refuses each one written over a value per period where the line is
written, naming the operation and its move. This engine answered six of them
per period -- and failed ``date.date_ranges`` with an array error -- so the
engines parted on a model the specification does not state. Each now refuses
by name: from the record's declared shape where the operand is an input, and
in the lowering where it is a calculation that declares none.
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
    "d": {"dtype": "date", "values": ["2025-01-31"]},
    "e": {"dtype": "date", "values": ["2025-06-30"]},
    "s": {"dtype": "f64", "values": [45000.0]},
    "dl": {"dtype": "list[date]", "values": [["2025-01-31", "2025-03-31"]]},
    "el": {"dtype": "list[date]", "values": [["2025-06-30", "2025-07-31"]]},
    "sl": {"dtype": "list[f64]", "values": [[45000.0, 45001.0]]},
}

# Each operation, its per-policy operands, its attributes and what it answers.
OPERATIONS: dict[str, tuple[tuple[str, ...], dict[str, object], str]] = {
    "date.months_between": (("d", "e"), {}, "i64"),
    "excel.days": (("e", "d"), {}, "i64"),
    "date.to_period": (("d",), {"freq": "M"}, "date"),
    "date.offset_by": (("d",), {"duration": "1mo"}, "date"),
    "date.date_ranges": (("d", "e"), {"interval": "1mo", "closed": "both"}, "date"),
    "excel.from_excel_serial": (("s",), {"epoch": "1900"}, "date"),
}


def _nested(name: str) -> dict[str, Any]:
    """Return a calculation held per period standing for the operand ``name``."""
    if name in ("dl", "el"):
        return call(
            "date.date_ranges", col("d"), col("e"), interval="5mo", closed="both"
        )
    return {"op": "binop", "kind": "add", "left": col(name), "right": lit(0.0)}


def _cells() -> list[tuple[str, int, bool]]:
    return [
        (name, position, nested)
        for name, (operands, _attrs, _answers) in OPERATIONS.items()
        for position in range(len(operands))
        for nested in (False, True)
    ]


@pytest.mark.parametrize(("name", "position", "nested"), _cells())
def test_an_operand_held_per_period_is_refused_by_name(
    name: str, position: int, *, nested: bool
) -> None:
    operands, attrs, answers = OPERATIONS[name]
    args = [col(one) for one in operands]
    held = f"{operands[position]}l"
    args[position] = _nested(held) if nested else col(held)
    one = invocation(call(name, *args, **attrs), INPUTS, f"list[{answers}]")
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    rendered = " ".join(refused.value.report.render().split())
    assert f"{name} is written over one value per period" in rendered
    assert "11.1.33" in rendered


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_one_value_per_policy_still_answers(name: str) -> None:
    operands, attrs, answers = OPERATIONS[name]
    dtype = "list[date]" if name == "date.date_ranges" else answers
    one = invocation(call(name, *(col(o) for o in operands), **attrs), INPUTS, dtype)
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert result.columns["answer"].to_list()[0] is not None
