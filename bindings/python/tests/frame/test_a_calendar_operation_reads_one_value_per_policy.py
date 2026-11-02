# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every 11.1.33 operation but ``excel.yearfrac`` reads one value per policy.

Section 11.1.33 states its date operations over scalar operands, and
``excel.yearfrac`` alone (11.1.34) over a date in every period. A date, a
serial or a count of months held per period failed when the frame ran, in
Polars' words (```year` operation not supported``, ``cannot cast List
type``), naming neither the line nor a way through, while the JAX engine and
the kit's reader answered it. It is refused by name where the line is written,
with the operation's own move, and the JAX engine and the reader refuse it too.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Any

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame
from gaspatchio.column import ExpressionProxy
from gaspatchio.frame.graph.op_json import op_node_from_json

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)
sys.path.insert(0, str(_CONFORMANCE))
try:
    from reader.shared import Column, DomainRefusal
    from reference import Reader
finally:
    sys.path.remove(str(_CONFORMANCE))

START, END = dt.date(2025, 1, 31), dt.date(2025, 6, 30)

# Each operation, its operands (the per-policy column names) and attributes.
OPERATIONS: dict[str, tuple[tuple[str, ...], dict[str, Any]]] = {
    "date.months_between": (("d", "e"), {}),
    "excel.days": (("e", "d"), {}),
    "date.to_period": (("d",), {"freq": "M"}),
    "date.offset_by": (("d",), {"duration": "1mo"}),
    "excel.edate": (("d", "m"), {}),
    "excel.eomonth": (("d", "m"), {}),
    "date.date_ranges": (("d", "e"), {"interval": "1mo", "closed": "both"}),
    "excel.from_excel_serial": (("s",), {"epoch": "1900"}),
}


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "d": [START],
                "e": [END],
                "m": [1],
                "s": [45000.0],
                "d_per_period": [[START, dt.date(2025, 3, 31)]],
                "e_per_period": [[END, dt.date(2025, 7, 31)]],
                "m_per_period": [[1, 2]],
                "s_per_period": [[45000.0, 45001.0]],
            }
        )
    )


def _col(name: str) -> dict[str, Any]:
    return {"op": "col", "name": name}


def _tree(name: str, args: list[dict[str, Any]]) -> dict[str, Any]:
    return {"op": "call", "name": name, "args": args, "attrs": OPERATIONS[name][1]}


def _cells() -> list[tuple[str, int]]:
    return [
        (name, position)
        for name, (operands, _attrs) in OPERATIONS.items()
        for position in range(len(operands))
    ]


@pytest.mark.parametrize(("name", "position"), _cells())
def test_an_operand_held_per_period_is_refused_where_the_line_is_written(
    name: str, position: int
) -> None:
    operands = list(OPERATIONS[name][0])
    held = f"{operands[position]}_per_period"
    operands[position] = held
    frame = _frame()
    tree = _tree(name, [_col(one) for one in operands])
    with pytest.raises(
        ValueError,
        match=rf"{name}\(\) .* for each policy \(11\.1\.33\), and the column "
        rf"'{held}' holds one value per period, so the line is refused\. \S",
    ):
        frame.answer = ExpressionProxy._from_node(op_node_from_json(tree), frame)  # noqa: SLF001


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_a_calculation_held_per_period_is_refused_too(name: str) -> None:
    """A calculation declares its shape as a column does, and is refused alike."""
    operands = OPERATIONS[name][0]
    first = operands[0]
    per_period = {
        "op": "binop",
        "kind": "add",
        "left": _col(f"{first}_per_period"),
        "right": {"op": "lit", "value": 0.0},
    }
    if first in ("d", "e"):
        per_period = {
            "op": "call",
            "name": "date.date_ranges",
            "args": [_col("d"), _col("e")],
            "attrs": {"interval": "5mo", "closed": "both"},
        }
    frame = _frame()
    tree = _tree(name, [per_period, *(_col(one) for one in operands[1:])])
    with pytest.raises(ValueError, match="an expression holds one value per period"):
        frame.answer = ExpressionProxy._from_node(op_node_from_json(tree), frame)  # noqa: SLF001


@pytest.mark.parametrize("name", list(OPERATIONS))
def test_one_value_per_policy_still_answers(name: str) -> None:
    frame = _frame()
    tree = _tree(name, [_col(one) for one in OPERATIONS[name][0]])
    frame.answer = ExpressionProxy._from_node(op_node_from_json(tree), frame)  # noqa: SLF001
    assert frame.collect()["answer"].to_list()[0] is not None


def test_yearfrac_still_reads_a_date_in_every_period() -> None:
    af = _frame()
    af.answer = af.d.excel.yearfrac(af.e_per_period, basis=3)
    assert af.collect()["answer"].to_list() == [[150 / 365, 181 / 365]]


@pytest.mark.parametrize(("name", "position"), _cells())
def test_the_reader_refuses_an_operand_held_per_period(
    name: str, position: int
) -> None:
    kinds = {"d": "date", "e": "date", "m": "i64", "s": "f64"}
    values = {"d": "2025-01-31", "e": "2025-06-30", "m": 1, "s": 45000.0}
    operands = OPERATIONS[name][0]
    book = {
        one: (
            Column(f"list[{kinds[one]}]", [[values[one], values[one]]])
            if at == position
            else Column(kinds[one], [values[one]])
        )
        for at, one in enumerate(operands)
    }
    with pytest.raises(DomainRefusal) as refused:
        Reader(book, [], {}).evaluate(_tree(name, [_col(one) for one in operands]))
    assert str(refused.value) == "calendar-operand-per-period"
