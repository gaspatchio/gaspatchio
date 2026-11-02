# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An integer raised to a written exponent past 11.1.25's integer promise is a double.

Two integers keep an integer power only for an exponent in ``[0, 2**32 - 1]``,
and ``af.a ** -1`` is ``1 / a``. On an integer column it failed when the frame
ran, inside Polars -- ``conversion from `i32` to `u32` failed in column
'literal'`` -- while the record called the line ``i64``. A literal exponent is
in the record, so its type is decided where the line is written: ``f64``.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter


def _frame() -> ActuarialFrame:
    return ActuarialFrame(pl.DataFrame({"a": [2, 4, 3], "k": [1, 2, 3]}))


def _record_dtype(af: ActuarialFrame, column: str) -> str:
    document = json.loads(GraphExporter(af).export(profile="executable"))
    return next(
        node["dtype"] for node in document["nodes"] if node["id"].startswith(column)
    )


@pytest.mark.parametrize(
    ("exponent", "expected"),
    [
        (-1, [0.5, 0.25, 1 / 3]),
        (-2, [0.25, 0.0625, 1 / 9]),
    ],
)
def test_a_written_exponent_past_the_promise_answers_a_double(
    exponent: int, expected: list[float]
) -> None:
    af = _frame()
    af.r = af.a**exponent

    answered = af.collect()["r"]

    assert answered.dtype == pl.Float64
    assert answered.to_list() == expected
    assert _record_dtype(af, "r") == "f64"


def test_the_method_spelling_and_a_line_built_on_it_answer_doubles() -> None:
    af = _frame()
    af.r = af.a.pow(-3)
    af.s = (af.a**-1) + af.k

    out = af.collect()

    assert out["r"].to_list() == [0.125, 0.015625, 1 / 27]
    assert out["s"].to_list() == [1.5, 2.25, 1 / 3 + 3]
    assert _record_dtype(af, "s") == "f64"


def test_an_exponent_inside_the_promise_keeps_the_integer() -> None:
    af = _frame()
    af.r = af.a**2
    af.z = af.a**0

    out = af.collect()

    assert out["r"].dtype == pl.Int64
    assert out["r"].to_list() == [4, 16, 9]
    assert out["z"].to_list() == [1, 1, 1]
    assert _record_dtype(af, "r") == "i64"


def test_a_decimal_base_under_a_negative_exponent_is_unchanged() -> None:
    af = ActuarialFrame(pl.DataFrame({"x": [2.0, 0.5]}))
    af.r = af.x**-1

    assert af.collect()["r"].to_list() == [0.5, 2.0]
