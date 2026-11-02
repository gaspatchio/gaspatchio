# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``&``, ``|`` and ``~`` read a stored numeric predicate as the flag it is.

A stored ``f64``/``list[f64]`` column holding exactly 0.0 or 1.0 is a valid
``when()`` condition (spec section 11.1.18), and the logical operators used to
refuse it: ``af.flag & x`` and ``~af.flag`` raised while ``when(af.flag)`` ran,
and four independent builds hit that. Section 11.1.27 now has the operators take the
same stored column under the same exact contract: -0.0 is 0.0, and a null,
NaN, infinity or any other number refuses at evaluation, naming the column and
the comparison that fixes it. The stored column keeps its Float64 storage, and
an integer column, a literal number and an arithmetic result are still not
predicates and still refuse while the formula is written.

The matrix below crosses every operand form the operators meet -- stored
Float64 (input, computed, Float32 storage), stored Boolean, inline comparison,
each per policy and per period -- and checks each answer against truth values
worked out from the data by hand, in ``when()`` and as a stored column.
"""

from __future__ import annotations

import json
import math
from itertools import combinations_with_replacement
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio._semantic.ir import BinOp, Call, Col
from gaspatchio.frame.graph import GraphExporter, validate_artifact

if TYPE_CHECKING:
    from collections.abc import Callable

    from gaspatchio.column import ExpressionProxy

# Two policies; per-period columns have three periods each.
_PER_POLICY: dict[str, list[bool]] = {
    "sf": [True, False],  # stored Float64 input
    "sf32": [False, True],  # stored Float32 input
    "sfc": [False, True],  # computed earlier: af.sfc = af.age > 40
    "sb": [True, False],  # stored Boolean input
    "cmp_s": [False, True],  # inline comparison: af.age > 40
}
_PER_PERIOD: dict[str, list[list[bool]]] = {
    "lf": [[True, False, True], [False, False, True]],
    "lf32": [[False, True, True], [True, False, False]],
    "lfc": [[False, True, True], [False, True, True]],  # af.lfc = af.dur > 1
    "lb": [[True, False, True], [False, False, True]],
    "lbc": [[False, True, True], [False, True, True]],  # U7b: a Boolean conditional
    "cmp_l": [[False, True, True], [False, True, True]],  # af.dur > 1
}
_OPERANDS = (*_PER_POLICY, *_PER_PERIOD)


def _frame() -> ActuarialFrame:
    """Return the two-policy frame every operand form below is read from."""
    frame = ActuarialFrame(
        pl.DataFrame(
            {
                "age": [30.0, 50.0],
                "sf": pl.Series([1.0, 0.0], dtype=pl.Float64),
                "sf32": pl.Series([0.0, 1.0], dtype=pl.Float32),
                "sb": [True, False],
                "lf": pl.Series(
                    [[1.0, 0.0, 1.0], [0.0, 0.0, 1.0]], dtype=pl.List(pl.Float64)
                ),
                "lf32": pl.Series(
                    [[0.0, 1.0, 1.0], [1.0, -0.0, 0.0]], dtype=pl.List(pl.Float32)
                ),
                "lb": [[True, False, True], [False, False, True]],
                "dur": [[1, 2, 3], [1, 2, 3]],
            }
        )
    )
    frame.sfc = frame.age > 40
    frame.lfc = frame.dur > 1
    frame.lbc = when(frame.dur > 1).then(True).otherwise(False)  # noqa: FBT003
    return frame


def _operand(frame: ActuarialFrame, name: str) -> object:
    """Return the operand ``name`` stands for, read off ``frame``."""
    if name == "cmp_s":
        return frame.age > 40
    if name == "cmp_l":
        return frame.dur > 1
    return frame[name]


def _truth(name: str) -> list[bool] | list[list[bool]]:
    return _PER_POLICY[name] if name in _PER_POLICY else _PER_PERIOD[name]


def _combine(
    left: str, right: str, rule: Callable[[bool, bool], bool]
) -> tuple[bool, list[object]]:
    """Return (per_period, expected truth per policy) for ``left`` op ``right``."""
    per_period = left in _PER_PERIOD or right in _PER_PERIOD
    answers: list[object] = []
    for row in range(2):
        a, b = _truth(left)[row], _truth(right)[row]
        if not per_period:
            answers.append(rule(a, b))  # type: ignore[arg-type]
            continue
        periods = 3
        a_run = a if isinstance(a, list) else [a] * periods
        b_run = b if isinstance(b, list) else [b] * periods
        answers.append([rule(x, y) for x, y in zip(a_run, b_run, strict=True)])
    return per_period, answers


def _assert_answers(
    frame: ActuarialFrame, built: object, *, per_period: bool, truth: list[object]
) -> None:
    """Check ``built`` stored and used as a condition against ``truth``."""
    frame.stored = built
    frame.selected = when(built).then(10.0).otherwise(20.0)
    result = frame.collect()
    if per_period:
        assert result.schema["stored"] == pl.List(pl.Float64)
        assert result["stored"].to_list() == [
            [1.0 if cell else 0.0 for cell in row]  # type: ignore[attr-defined]
            for row in truth
        ]
        assert result["selected"].to_list() == [
            [10.0 if cell else 20.0 for cell in row]  # type: ignore[attr-defined]
            for row in truth
        ]
    else:
        assert result.schema["stored"] == pl.Boolean
        assert result["stored"].to_list() == truth
        assert result["selected"].to_list() == [10.0 if t else 20.0 for t in truth]
    # The stored flags keep the storage they arrived in or were computed to;
    # a single-precision flag arrives as the double the record names.
    assert result.schema["sf"] == pl.Float64
    assert result.schema["sf32"] == pl.Float64
    assert result.schema["sfc"] == pl.Float64
    assert result.schema["lf"] == pl.List(pl.Float64)
    assert result.schema["lfc"] == pl.List(pl.Float64)


@pytest.mark.parametrize("operator", ["and", "or"])
@pytest.mark.parametrize(
    ("left", "right"),
    list(combinations_with_replacement(_OPERANDS, 2)),
    ids=str,
)
def test_every_operand_pair_combines_to_its_hand_worked_truth(
    operator: str, left: str, right: str
) -> None:
    frame = _frame()
    a, b = _operand(frame, left), _operand(frame, right)
    if operator == "and":
        built = a & b  # type: ignore[operator]
        per_period, truth = _combine(left, right, lambda x, y: x and y)
    else:
        built = a | b  # type: ignore[operator]
        per_period, truth = _combine(left, right, lambda x, y: x or y)
    _assert_answers(frame, built, per_period=per_period, truth=truth)


@pytest.mark.parametrize("name", _OPERANDS)
def test_every_operand_negates_to_its_hand_worked_truth(name: str) -> None:
    frame = _frame()
    built = ~_operand(frame, name)  # type: ignore[operator]
    if name in _PER_POLICY:
        truth: list[object] = [not t for t in _PER_POLICY[name]]
        per_period = False
    else:
        truth = [[not t for t in row] for row in _PER_PERIOD[name]]
        per_period = True
    _assert_answers(frame, built, per_period=per_period, truth=truth)


@pytest.mark.parametrize("literal", [True, False])
def test_a_python_boolean_meets_a_stored_flag_on_either_side(*, literal: bool) -> None:
    frame = _frame()
    frame.left = literal & frame.sf
    frame.right = frame.sf | literal
    result = frame.collect()
    assert result["left"].to_list() == [literal, False]
    assert result["right"].to_list() == [True, literal]


def test_a_stored_logical_result_is_itself_a_stored_predicate() -> None:
    """The answer can be stored, then combined and selected on again."""
    frame = _frame()
    frame.eligible = frame.sf & frame.lf  # per-period, stored List(Float64)
    frame.either = frame.eligible | ~frame.lfc
    frame.picked = when(frame.eligible).then(1.0).otherwise(0.0)
    result = frame.collect()
    assert result.schema["eligible"] == pl.List(pl.Float64)
    assert result["eligible"].to_list() == [[1.0, 0.0, 1.0], [0.0, 0.0, 0.0]]
    assert result["either"].to_list() == [[1.0, 0.0, 1.0], [1.0, 0.0, 0.0]]
    assert result["picked"].to_list() == result["eligible"].to_list()


# --- the exact contract: anything but 0.0 / 1.0 refuses ---------------------


def _one_bad_value(bad: float | None, *, per_period: bool) -> ActuarialFrame:
    values: list[object] = [[1.0, bad]] if per_period else [1.0, bad]
    dtype = pl.List(pl.Float64) if per_period else pl.Float64
    return ActuarialFrame(
        pl.DataFrame(
            {
                "flag": pl.Series(values, dtype=dtype),
                "other": [True] if per_period else [True, False],
            }
        )
    )


_BUILDERS: dict[str, Callable[[ActuarialFrame], ExpressionProxy]] = {
    "and": lambda frame: frame.flag & frame.other,
    "or": lambda frame: frame.other | frame.flag,
    "not": lambda frame: ~frame.flag,
}


@pytest.mark.parametrize("per_period", [False, True], ids=["policy", "period"])
@pytest.mark.parametrize("operator", list(_BUILDERS))
@pytest.mark.parametrize(
    "bad", [2.0, 0.5, -1.0, None, math.nan, math.inf, -math.inf], ids=str
)
def test_a_flag_holding_anything_but_zero_or_one_refuses_and_names_the_comparison(
    bad: float | None, operator: str, *, per_period: bool
) -> None:
    frame = _one_bad_value(bad, per_period=per_period)
    frame.answer = _BUILDERS[operator](frame)
    with pytest.raises(pl.exceptions.PolarsError) as caught:
        frame.collect()
    message = str(caught.value)
    assert message.splitlines()[0] == (
        "Column 'flag' is used as a condition but holds a value that is "
        "neither 0.0 nor 1.0."
    )
    assert "(af.flag == 1.0)" in message


@pytest.mark.parametrize("per_period", [False, True], ids=["policy", "period"])
def test_negative_zero_is_zero(*, per_period: bool) -> None:
    frame = _one_bad_value(-0.0, per_period=per_period)
    frame.both = frame.flag & frame.other
    frame.negated = ~frame.flag
    result = frame.collect()
    if per_period:
        assert result["both"].to_list() == [[1.0, 0.0]]
        assert result["negated"].to_list() == [[0.0, 1.0]]
    else:
        assert result["both"].to_list() == [True, False]
        assert result["negated"].to_list() == [False, True]


def test_the_check_reaches_an_unused_side_of_or() -> None:
    """True OR anything is true, and the 2.0 in the other operand still refuses."""
    frame = ActuarialFrame({"flag": [2.0], "yes": [True]})
    frame.answer = frame.yes | frame.flag
    with pytest.raises(pl.exceptions.PolarsError, match="stored numeric predicate"):
        frame.collect()


def test_empty_periods_and_an_empty_book_answer_vacuously() -> None:
    empty_periods = ActuarialFrame(
        pl.DataFrame(
            {
                "flag": pl.Series([[]], dtype=pl.List(pl.Float64)),
                "other": pl.Series([[]], dtype=pl.List(pl.Boolean)),
            }
        )
    )
    empty_periods.both = empty_periods.flag & empty_periods.other
    assert empty_periods.collect()["both"].to_list() == [[]]

    no_policies = ActuarialFrame(
        pl.DataFrame(
            {
                "flag": pl.Series([], dtype=pl.Float64),
                "other": pl.Series([], dtype=pl.Boolean),
            }
        )
    )
    no_policies.both = no_policies.flag & no_policies.other
    no_policies.negated = ~no_policies.flag
    result = no_policies.collect()
    assert result.height == 0
    assert result.schema["both"] == pl.Boolean


# --- what is still not a predicate -----------------------------------------


@pytest.mark.parametrize(
    "build",
    [
        lambda frame: frame.units & frame.yes,
        lambda frame: ~frame.units,
        lambda frame: frame.yes | frame.counts,
        lambda frame: frame.flag & 1.0,
        lambda frame: (frame.flag * 1.0) & frame.yes,
        lambda frame: ~(frame.flag + 0.0),
    ],
    ids=[
        "integer-column",
        "negated-integer",
        "integer-periods",
        "literal-number",
        "arithmetic",
        "negated-arithmetic",
    ],
)
def test_a_number_that_is_not_a_stored_flag_still_refuses_naming_equals_one(
    build: Callable[[ActuarialFrame], object],
) -> None:
    frame = ActuarialFrame(
        {
            "units": [1, 0],
            "counts": [[1, 0], [0]],
            "flag": [1.0, 0.0],
            "yes": [True, False],
        }
    )
    with pytest.raises(
        TypeError, match=r"Compare numeric flags explicitly \(af\.flag == 1\)"
    ):
        build(frame)


def test_integer_bit_operations_stay_on_the_native_escape() -> None:
    frame = ActuarialFrame({"bits": [1, 2, 3]})
    frame.masked = frame.bits.polars_native().and_(2)
    assert frame.collect()["masked"].to_list() == [0, 2, 2]


# --- the record: the same operation tree, and an artifact that validates ---


def test_the_operation_tree_is_the_ordinary_logical_one() -> None:
    frame = _frame()
    both = frame.sf & frame.lf
    negated = ~frame.sf
    assert both._node == BinOp("and", Col("sf"), Col("lf"))  # noqa: SLF001
    assert negated._node == Call("not_", (Col("sf"),))  # noqa: SLF001


def test_an_exported_model_records_the_flag_read_and_validates() -> None:
    frame = ActuarialFrame(
        {"flag": [1.0, 0.0], "yes": [True, True], "rate": [0.01, 0.02]}
    )
    frame.eligible = frame.flag & frame.yes
    frame.charge = when(~frame.flag).then(frame.rate).otherwise(0.0)
    artifact = GraphExporter(frame).export(profile="executable")
    assert validate_artifact(artifact, deep=True).ok
    nodes = {node["column"]: node for node in json.loads(artifact)["nodes"]}
    assert nodes["eligible"]["expr"] == {
        "op": "binop",
        "kind": "and",
        "left": {"op": "col", "name": "flag"},
        "right": {"op": "col", "name": "yes"},
    }
    assert nodes["eligible"]["dtype"] == "bool"
    assert nodes["flag"]["dtype"] == "f64"
