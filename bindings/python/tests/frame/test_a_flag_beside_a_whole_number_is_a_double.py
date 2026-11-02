# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A flag beside a whole number in a conditional answers a double, on both routes.

``when(af.x > 2).then(True).otherwise(af.n)`` answered ``Int64`` per policy,
where Polars reads the flag as 0 or 1, and ``list[f64]`` per period, where
the selection kernel works in doubles. Section 11.1.25 reads a flag beside a
number as its 0.0/1.0 indicator, so the pair now answers ``f64`` on both
routes, and the record says so; the reference reader types it so too, and a
flag beside a fixed-point decimal answers a double as well. Hand values are
the doubles a reader writes.
"""

from __future__ import annotations

import importlib
import json
import math
import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable


def _frame(**columns: pl.Series) -> ActuarialFrame:
    """Two policies: the first takes otherwise per policy, month 0 per period."""
    book = pl.DataFrame(
        {
            "pid": [1, 2],
            "x": [1.5, 3.5],
            "m": pl.Series([[0, 1, 2], [0, 1, 2]], dtype=pl.List(pl.Int64)),
            **columns,
        }
    )
    return ActuarialFrame(book)


def _answer(af: ActuarialFrame, line: Callable[[Any], Any]) -> pl.Series:
    af.r = line(af)
    return af.collect()["r"]


def _record_dtype(af: ActuarialFrame) -> str:
    document = json.loads(GraphExporter(af).export(profile="executable"))
    return next(node["dtype"] for node in document["nodes"] if node["column"] == "r")


_FLAG_LINES: list[tuple[str, Callable[[Any], Any], pl.DataType, list[Any]]] = [
    (
        "a flag literal beside a whole-number column",
        lambda af: when(af.x > 2).then(True).otherwise(af.n),  # noqa: FBT003
        pl.Float64(),
        [7.0, 1.0],
    ),
    (
        "a whole-number column beside a flag literal",
        lambda af: when(af.x > 2).then(af.n).otherwise(False),  # noqa: FBT003
        pl.Float64(),
        [0.0, -3.0],
    ),
    (
        "a flag column beside a whole-number literal",
        lambda af: when(af.x > 2).then(af.b).otherwise(5),
        pl.Float64(),
        [5.0, 0.0],
    ),
    (
        "a flag in a chain of whole numbers",
        lambda af: when(af.x > 3).then(af.n).when(af.x > 2).then(True).otherwise(4),  # noqa: FBT003
        pl.Float64(),
        [4.0, -3.0],
    ),
    (
        "per period, a flag beside a whole-number run",
        lambda af: when(af.m > 0).then(af.b).otherwise(af.k),
        pl.List(pl.Float64),
        [[10.0, 1.0, 1.0], [20.0, 0.0, 0.0]],
    ),
    (
        "per period, a flag run beside one whole number per policy",
        lambda af: when(af.x > 2).then(af.f).otherwise(af.n),
        pl.List(pl.Float64),
        [[7.0, 7.0, 7.0], [0.0, 1.0, 0.0]],
    ),
]


def _flag_frame() -> ActuarialFrame:
    return _frame(
        n=pl.Series([7, -3], dtype=pl.Int64),
        b=[True, False],
        k=pl.Series([[10, 11, 12], [20, 21, 22]], dtype=pl.List(pl.Int64)),
        f=pl.Series(
            [[True, False, True], [False, True, False]], dtype=pl.List(pl.Boolean)
        ),
    )


@pytest.mark.parametrize(
    ("line", "dtype", "hand"),
    [line[1:] for line in _FLAG_LINES],
    ids=[line[0] for line in _FLAG_LINES],
)
def test_a_flag_beside_a_whole_number_answers_its_double_on_both_routes(
    line: Callable[[Any], Any], dtype: pl.DataType, hand: list[Any]
) -> None:
    af = _flag_frame()
    answer = _answer(af, line)
    assert answer.dtype == dtype
    assert answer.to_list() == hand
    assert _record_dtype(af) == ("list[f64]" if isinstance(dtype, pl.List) else "f64")


def test_a_flag_and_a_whole_number_compute_as_a_double_downstream() -> None:
    # Float mod by zero is NaN (11.1.25); the integer the pair used to answer
    # gave a null instead.
    answer = _answer(
        _flag_frame(),
        lambda af: when(af.x > 2).then(True).otherwise(af.n) % 0,  # noqa: FBT003
    )
    assert answer.dtype == pl.Float64
    assert all(math.isnan(value) for value in answer.to_list())


@pytest.mark.parametrize(
    ("line", "dtype", "hand"),
    [
        (
            lambda af: when(af.x > 2).then(af.b).otherwise(0.25),
            pl.Float64(),
            [0.25, 0.0],
        ),
        (
            lambda af: when(af.x > 2).then(af.b).otherwise(True),  # noqa: FBT003
            pl.Boolean(),
            [True, False],
        ),
        (lambda af: when(af.x > 2).then(af.n).otherwise(5), pl.Int64(), [5, -3]),
        (
            lambda af: when(af.x > 2).then(None).otherwise(af.b),
            pl.Boolean(),
            [True, None],
        ),
    ],
    ids=[
        "a flag beside a decimal",
        "two flags",
        "two whole numbers",
        "a null beside a flag",
    ],
)
def test_the_other_pairs_keep_their_type(
    line: Callable[[Any], Any], dtype: pl.DataType, hand: list[Any]
) -> None:
    answer = _answer(_flag_frame(), line)
    assert answer.dtype == dtype
    assert answer.to_list() == hand


@pytest.mark.parametrize(
    "line",
    [
        lambda af: when(af.x > 2).then(af.b).otherwise(af.u),
        lambda af: when(af.m > 0).then(af.u).otherwise(af.b),
    ],
    ids=["per policy", "per period"],
)
def test_a_whole_number_past_i64_beside_a_flag_is_refused_as_in_arithmetic(
    line: Callable[[Any], Any],
) -> None:
    # Per policy the pair kept the column's UInt64 and answered 2**64 - 1;
    # per period it rounded it into a double. Arithmetic refuses it by name.
    af = _frame(b=[True, False], u=pl.Series([2**64 - 1, 3], dtype=pl.UInt64))
    with pytest.raises(pl.exceptions.InvalidOperationError) as refused:
        _answer(af, line)
    assert (
        str(refused.value)
        .splitlines()[0]
        .startswith("Column 'u' holds a whole number outside the signed 64-bit range")
    )


@pytest.mark.parametrize(
    ("line", "dtype", "hand"),
    [
        (
            lambda af: when(af.x > 2).then(af.b).otherwise(af.d),
            pl.Float64(),
            [1.25, 0.0],
        ),
        (
            lambda af: when(af.x > 2).then(af.d).otherwise(True),  # noqa: FBT003
            pl.Float64(),
            [1.0, 2.5],
        ),
        (
            lambda af: when(af.m > 0).then(af.b).otherwise(af.d),
            pl.List(pl.Float64),
            [[1.25, 1.0, 1.0], [2.5, 0.0, 0.0]],
        ),
    ],
    ids=["a flag column per policy", "a flag literal per policy", "per period"],
)
def test_a_flag_beside_a_fixed_point_decimal_answers_a_double_on_both_routes(
    line: Callable[[Any], Any], dtype: pl.DataType, hand: list[Any]
) -> None:
    # Per policy Polars found no type for a flag and a Decimal and stopped
    # the run in its own words; per period the pair already answered f64.
    af = _frame(
        b=[True, False],
        d=pl.Series([Decimal("1.25"), Decimal("2.5")], dtype=pl.Decimal(38, 4)),
    )
    answer = _answer(af, line)
    assert answer.dtype == dtype
    assert answer.to_list() == hand


def _reference_reader() -> Any:  # noqa: ANN401 -- the reader is untyped
    conformance = (
        Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
    )
    sys.path.insert(0, str(conformance))
    try:
        return importlib.import_module("reference")
    finally:
        sys.path.remove(str(conformance))


def _case(then: dict[str, Any], otherwise: dict[str, Any]) -> dict[str, Any]:
    cond = {
        "op": "binop",
        "kind": "gt",
        "left": {"op": "col", "name": "x"},
        "right": {"op": "lit", "value": 2.0, "dtype": "f64"},
    }
    return {"op": "when_then", "cond": cond, "then": then, "otherwise": otherwise}


@pytest.mark.parametrize(
    ("then", "otherwise", "dtype", "hand"),
    [
        ({"op": "col", "name": "b"}, {"op": "col", "name": "n"}, "f64", [7.0, 0.0]),
        ({"op": "col", "name": "n"}, {"op": "col", "name": "b"}, "f64", [1.0, -3.0]),
        (
            {"op": "lit", "value": True, "dtype": "bool"},
            {"op": "col", "name": "n"},
            "f64",
            [7.0, 1.0],
        ),
        (
            {"op": "col", "name": "b"},
            {"op": "col", "name": "k"},
            "list[f64]",
            [[10.0, 11.0], [0.0, 0.0]],
        ),
    ],
    ids=["flag then", "flag otherwise", "flag literal", "per period"],
)
def test_the_reference_reader_types_the_pair_a_double(
    then: dict[str, Any], otherwise: dict[str, Any], dtype: str, hand: list[Any]
) -> None:
    # The reader typed the pair by its then branch: a flag column beside a
    # whole number was bool [7, False], the other way round i64 [True, -3].
    reference = _reference_reader()
    column = reference.Column
    inputs = {
        "x": column("f64", [1.5, 3.5]),
        "b": column("bool", [True, False]),
        "n": column("i64", [7, -3]),
        "k": column("list[i64]", [[10, 11], [20, 21]]),
    }
    answer = reference.Reader(inputs, [], {}).evaluate(_case(then, otherwise))
    assert answer.dtype == dtype
    assert answer.values == hand


def test_the_reference_reader_refuses_the_pair_past_two_to_the_53() -> None:
    reference = _reference_reader()
    column = reference.Column
    inputs = {
        "x": column("f64", [1.5, 3.5]),
        "b": column("bool", [True, False]),
        "n": column("i64", [2**53 + 1, -3]),
    }
    case = _case({"op": "col", "name": "b"}, {"op": "col", "name": "n"})
    with pytest.raises(reference.DomainRefusal, match="exact-numeric-range"):
        reference.Reader(inputs, [], {}).evaluate(case)
