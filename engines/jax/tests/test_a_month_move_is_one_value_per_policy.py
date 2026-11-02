# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A month move over a per-period operand is refused by name (11.1.33).

11.1.33 states one date and one count of months for each policy, and the
reference producer refuses either held per period by name where the line is
written. This engine answered both per period, so the engines parted on a
model the specification does not state. It now refuses by name too: from the
record's declared shape where the operand is an input, and in the lowering
where it is a calculation that declares none.
"""

from __future__ import annotations

from typing import Any

import pytest

from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio_jax.engine import JaxEngine
from tests.conftest import invocation
from tests.test_final_domains import call, col, lit

START = "2025-01-31"
INPUTS: dict[str, dict[str, object]] = {
    "d": {"dtype": "date", "values": [START]},
    "e": {"dtype": "date", "values": ["2025-03-31"]},
    "m": {"dtype": "i64", "values": [1]},
    "dl": {"dtype": "list[date]", "values": [[START, "2025-03-31"]]},
    "ml": {"dtype": "list[i64]", "values": [[1, 2]]},
    "mf": {"dtype": "list[f64]", "values": [[1.0, 2.0]]},
}


def _nested(operand: dict[str, Any]) -> dict[str, Any]:
    if operand["name"] == "d":
        return call("date.offset_by", operand, duration="0d")
    if operand["name"] == "dl":
        # A run of dates is a calculation held per period; a date move over
        # one would itself be refused per period (11.1.33).
        return call(
            "date.date_ranges", col("d"), col("e"), interval="2mo", closed="both"
        )
    return {"op": "binop", "kind": "add", "left": operand, "right": lit(0)}


@pytest.mark.parametrize("name", ["excel.edate", "excel.eomonth"])
@pytest.mark.parametrize(
    ("start", "months"), [("d", "ml"), ("d", "mf"), ("dl", "m"), ("dl", "ml")]
)
@pytest.mark.parametrize("nested", [False, True])
def test_a_per_period_date_or_months_is_refused_by_name(
    name: str, start: str, months: str, *, nested: bool
) -> None:
    operands = [col(start), col(months)]
    if nested:
        operands = [_nested(one) for one in operands]
    one = invocation(call(name, *operands), INPUTS, "list[date]")
    with pytest.raises(EngineRefusal) as refused:
        JaxEngine().run(one.document, one.inputs, FrameSink())
    rendered = " ".join(refused.value.report.render().split())
    assert f"{name} is written over one value per period" in rendered


@pytest.mark.parametrize("name", ["excel.edate", "excel.eomonth"])
def test_one_date_and_one_count_per_policy_still_answer(name: str) -> None:
    one = invocation(call(name, col("d"), col("m")), INPUTS, "date")
    result = JaxEngine().run(one.document, one.inputs, FrameSink())
    assert [str(day) for day in result.columns["answer"].to_list()] == ["2025-02-28"]
