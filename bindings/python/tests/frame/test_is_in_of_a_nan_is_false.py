# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``is_in`` of a NaN answers false, per policy and per period (11.1.26).

Membership is equality (11.1.5), and under IEEE 754 a NaN equals nothing,
itself included -- so a NaN is a member of no set: false, not the unknown a
comparison with a NaN stores, and not null, which stays the answer for a null
value. Polars and the reader answered so over a set written into the formula;
over a set read from a column that held a NaN, Polars hashed one NaN equal to
another and answered true.
"""

from __future__ import annotations

import sys
from pathlib import Path

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)
sys.path.insert(0, str(_CONFORMANCE))
try:
    from reader.shared import Column
    from reference import Reader
finally:
    sys.path.remove(str(_CONFORMANCE))

NAN = float("nan")
ENGINES = ["in-memory", "streaming"]


def _frame() -> ActuarialFrame:
    # 0/0 is the NaN (11.1.25); a null stands beside it.
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "a0": [0.0, 1.0, 3.0, None],
                "b0": [0.0, 1.0, 1.0, 1.0],
                "a": [[0.0, 1.0, 3.0]] * 4,
                "b": [[0.0, 1.0, 1.0]] * 4,
            }
        )
    )
    af.r0 = af.a0 / af.b0
    af.r = af.a / af.b
    return af


@pytest.mark.parametrize("engine", ENGINES)
def test_a_nan_is_a_member_of_no_written_set(engine: str) -> None:
    af = _frame()
    af.m0 = af.r0.is_in([1.0, 2.0])
    af.m = af.r.is_in([1.0, 2.0])
    out = af.collect(engine=engine)
    assert out["m0"].to_list() == [False, True, False, None]
    assert out["m"].to_list() == [[False, True, False]] * 4


@pytest.mark.parametrize("engine", ENGINES)
def test_a_nan_is_not_a_member_of_a_set_holding_a_nan(engine: str) -> None:
    af = _frame()
    af.held = af.a / af.a  # [NaN, 1.0, 1.0]: a set read from a column
    af.m0 = af.r0.is_in(af.held)
    out = af.collect(engine=engine)
    assert out["m0"].to_list() == [False, True, False, None]


def test_the_reader_answers_false_for_a_nan() -> None:
    book = {
        "x": Column("f64", [NAN, 1.0, None]),
        "r": Column("list[f64]", [[NAN, 1.0], [2.0, NAN], None]),
    }
    for nulls_equal, null_answer in ((False, None), (True, False)):
        tree = {
            "op": "call",
            "name": "is_in",
            "args": [{"op": "col", "name": "x"}, {"op": "lit", "values": [1.0, 2.0]}],
            "attrs": {"nulls_equal": nulls_equal},
        }
        assert Reader(book, [], {}).evaluate(tree).values == [
            False,
            True,
            null_answer,
        ]
        tree["args"][0] = {"op": "col", "name": "r"}
        assert Reader(book, [], {}).evaluate(tree).values == [
            [False, True],
            [True, False],
            None,
        ]


@pytest.mark.parametrize(
    ("receiver", "members"),
    [("a0", [1.0, NAN]), ("a0", (NAN,)), ("a", [1.0, NAN])],
)
def test_a_nan_written_into_the_set_is_refused_by_name(
    receiver: str, members: object
) -> None:
    # A NaN member matches nothing, so the set cannot hold one; the refusal
    # says so and names is_nan, not a signature the call already matches.
    af = _frame()
    with pytest.raises(TypeError) as caught:
        af.m = af[receiver].is_in(members)
    message = str(caught.value)
    assert "is_in's set holds a NaN" in message
    assert "af.<column>.is_nan()" in message
    assert "do not match" not in message


@pytest.mark.parametrize(("value", "sign"), [(float("inf"), ">"), (-float("inf"), "<")])
def test_an_infinity_written_into_the_set_is_refused_by_name(
    value: float, sign: str
) -> None:
    af = _frame()
    with pytest.raises(TypeError) as caught:
        af.m = af.a0.is_in([1.0, value])
    message = str(caught.value)
    assert f"is_in's set holds {value!r}" in message
    assert f"(af.<column> {sign} 0)" in message
    assert "do not match" not in message


def test_the_moves_the_refusals_name_answer() -> None:
    af = ActuarialFrame(
        pl.DataFrame({"x": [NAN, float("inf"), -float("inf"), 1.0, 3.0]})
    )
    af.with_nan = af.x.is_in([1.0]) | af.x.is_nan()
    af.with_inf = af.x.is_in([1.0]) | (af.x.is_infinite() & (af.x > 0))
    out = af.collect()
    assert out["with_nan"].to_list() == [True, False, False, True, False]
    # A comparison with a NaN is unknown (11.1.26), so the NaN row's
    # infinity test is null, as any ordering of a NaN is.
    assert out["with_inf"].to_list() == [None, True, False, True, False]


def test_a_non_finite_argument_elsewhere_is_named_not_mismatched() -> None:
    af = _frame()
    with pytest.raises(TypeError) as caught:
        af.m = af.a0.fill_null(NAN)
    assert "nan is not finite in fill_null()" in str(caught.value)
