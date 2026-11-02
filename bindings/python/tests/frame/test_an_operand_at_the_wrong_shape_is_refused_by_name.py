# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An operand held at a shape its operation does not read is refused by name.

Each of these failed when the frame ran, in Polars' own words -- ``list.eval
operation not supported for dtype f64``, ```pow` operation not supported for
dtype list[f64]``, ``cannot cast List type``, ``expected leading integer in the
duration string`` -- naming neither the line nor a way through. A fold or a
period override over one value per policy, a broadcast onto a per-policy axis,
a guess, a rate, a period count or an initial value held per period, and a
period no interval names are now refused where the line is written, with the
clause and the move. The JAX engine and the kit's reader refuse the same forms.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.column import ExpressionProxy
from gaspatchio.frame.graph.op_json import op_node_from_json

if TYPE_CHECKING:
    from collections.abc import Callable

BOOK = pl.DataFrame(
    {
        "x": [2.0, 3.0],
        "xl": [[2.0, 3.0], [4.0, 5.0]],
        "ax": [3, 2],
        "axl": [[0, 1, 2], [0, 1]],
        "cf": [100.0, 200.0],
        "cfl": [[100.0, 100.0], [200.0, 200.0]],
        "r": [0.05, 0.04],
        "rl": [[0.05, 0.06], [0.04, 0.04]],
        "n": [2.0, 1.0],
        "nl": [[1.0, 2.0], [1.0, 2.0]],
        "irrcf": [[-100.0, 60.0, 60.0], [-100.0, 110.0]],
        "gl": [[0.1, 0.1, 0.1], [0.1, 0.1]],
        "i0": [100.0, 50.0],
        "i0l": [[100.0, 100.0], [50.0, 50.0]],
        "mu": [[1.01, 1.02], [1.0, 1.0]],
        "ad": [[1.0, 1.0], [2.0, 2.0]],
        "d": [datetime.date(2025, 5, 17), datetime.date(2025, 8, 2)],
    }
)


def _col(name: str) -> dict[str, str]:
    return {"op": "col", "name": name}


def _call(name: str, *args: str, **attrs: object) -> dict[str, object]:
    return {
        "op": "call",
        "name": name,
        "args": [_col(a) for a in args],
        "attrs": attrs,
    }


def _nested(name: str) -> dict[str, object]:
    return {
        "op": "binop",
        "kind": "add",
        "left": _col(name),
        "right": {"op": "lit", "value": 0.0},
    }


def _answer(expr: dict[str, object]) -> list[object]:
    frame = ActuarialFrame(BOOK)
    frame.answer = ExpressionProxy._from_node(op_node_from_json(expr), frame)  # noqa: SLF001
    return frame.collect()["answer"].to_list()


POLICY = "holds one value per policy, so the line is refused"
PERIOD = "holds one value per period, so the line is refused"

# (call, what the refusal says, the move it names)
REFUSED: dict[str, tuple[dict[str, object], str, str]] = {
    **{
        f"{op} over a per-policy value": (
            _call(op, "x", **attrs),
            (
                f"{op}() folds one policy's own periods ({clause}), and the "
                f"column 'x' {POLICY}"
            ),
            "Fold the per-period column the model means",
        )
        for op, clause, attrs in (
            ("sum", "11.1.14", {}),
            ("mean", "11.1.15", {}),
            ("min", "11.1.16", {}),
            ("max", "11.1.17", {}),
            ("cum_sum", "11.1.9", {"reverse": False}),
            ("cum_prod", "11.1.9", {"reverse": False}),
        )
    },
    "with_period over a per-policy value": (
        _call("projection.with_period", "x", period=0, value=9.0),
        f"(11.1.32), and the column 'x' {POLICY}",
        ".projection.broadcast_to_periods()",
    ),
    "broadcast onto a per-policy axis": (
        _call("projection.broadcast_to_periods", "x", "ax"),
        f"(11.1.32), and the column 'ax' {POLICY}",
        "like=af.month",
    ),
    "irr guess per period": (
        _call("excel.irr", "irrcf", "gl", default_guess=0.2),
        f"(11.1.36), and the column 'gl' {PERIOD}",
        "Write the guess once per policy.",
    ),
    **{
        f"{op} {what} per period": (
            _call(op, *args),
            (
                f"{op}() values one amount for each policy (11.1.29), and the "
                f"column {args[position]!r} {PERIOD}"
            ),
            "projection.prospective_value (11.1.21)",
        )
        for op in ("finance.discount", "finance.present_value")
        for what, args, position in (
            ("value", ("cfl", "r", "n"), 0),
            ("rate", ("cf", "rl", "n"), 1),
            ("period count", ("cf", "r", "nl"), 2),
        )
    },
    "accumulate initial per period": (
        _call("projection.accumulate", "i0l", "mu", "ad", reverse=False),
        f"(11.1.20), and the column 'i0l' {PERIOD}",
        "Write the initial value once per policy",
    ),
    "to_period with freq Q": (
        _call("date.to_period", "d", freq="Q"),
        "freq='Q' names none of them, so the line is refused",
        "Write freq as Y, M, W or D",
    ),
}


@pytest.mark.parametrize("case", REFUSED, ids=list(REFUSED))
def test_the_form_is_refused_where_the_line_is_written(case: str) -> None:
    expr, said, move = REFUSED[case]

    with pytest.raises(ValueError, match="so the line is refused") as refused:
        _answer(expr)

    message = str(refused.value)
    assert said in message
    assert move in message


def _nest_every_column(expr: dict[str, object]) -> dict[str, object]:
    args = expr["args"]
    assert isinstance(args, list)
    return {
        **expr,
        "args": [_nested(a["name"]) if a["name"] != "d" else a for a in args],
    }


@pytest.mark.parametrize(
    "case",
    [case for case in REFUSED if "freq" not in case],
    ids=[case for case in REFUSED if "freq" not in case],
)
def test_a_calculation_at_the_wrong_shape_is_refused_too(case: str) -> None:
    expr, _said, move = REFUSED[case]

    with pytest.raises(
        ValueError, match="an expression holds one value per"
    ) as refused:
        _answer(_nest_every_column(expr))
    assert move in str(refused.value)


ANSWERED: dict[str, tuple[dict[str, object], Callable[[list[object]], bool]]] = {
    "sum per period": (_call("sum", "xl"), lambda v: v == [5.0, 9.0]),
    "cum_sum per period": (
        _call("cum_sum", "xl", reverse=False),
        lambda v: v == [[2.0, 5.0], [4.0, 9.0]],
    ),
    "with_period per period": (
        _call("projection.with_period", "xl", period=0, value=9.0),
        lambda v: v == [[9.0, 3.0], [9.0, 5.0]],
    ),
    "broadcast onto a per-period axis": (
        _call("projection.broadcast_to_periods", "x", "axl"),
        lambda v: v == [[2.0, 2.0, 2.0], [3.0, 3.0]],
    ),
    "discount per policy": (
        _call("finance.discount", "cf", "r", "n"),
        lambda v: v == pytest.approx([100.0 / 1.05**2, 200.0 / 1.04]),
    ),
    "accumulate from a per-policy initial": (
        _call("projection.accumulate", "i0", "mu", "ad", reverse=False),
        lambda v: (
            [c for row in v for c in row] == pytest.approx([102.0, 105.04, 52.0, 54.0])
        ),
    ),
    "to_period with freq M": (
        _call("date.to_period", "d", freq="M"),
        lambda v: v == [datetime.date(2025, 5, 1), datetime.date(2025, 8, 1)],
    ),
    "to_period with an interval written with its count": (
        _call("date.to_period", "d", freq="1q"),
        lambda v: v == [datetime.date(2025, 4, 1), datetime.date(2025, 7, 1)],
    ),
}


@pytest.mark.parametrize("case", ANSWERED, ids=list(ANSWERED))
def test_the_stated_shape_answers_as_before(case: str) -> None:
    expr, holds = ANSWERED[case]

    assert holds(_answer(expr))
