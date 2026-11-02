# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The reference reader keeps a whole number's every digit, and refuses one past i64.

``floor``, ``ceil``, ``abs`` and ``sign`` of a whole number, and a run's
``sum``, ``cum_sum``, ``cum_prod`` and ``remaining_sum``, went through doubles,
so past 2^53 they lost digits: ``floor`` of 2^53 + 1 answered 2^53.
``round_sig_figs`` put the sign back through a double, so 2^62 to seventeen
figures came back unrounded and 2^63 - 1 to seventeen figures, which an
``i64`` holds, was refused. Each is now taken in whole numbers, and an answer
an ``i64`` does not hold -- a total past 2^63 - 1, a running product past it,
the absolute value of -2^63 -- is refused by name rather than wrapped or carried
into a double. Every hand value below is Python whole-number arithmetic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

_CONFORMANCE = Path(__file__).resolve().parents[4] / "spec/graph-artifact/conformance"
sys.path.insert(0, str(_CONFORMANCE))
from reader.shared import Column, DomainRefusal  # noqa: E402
from reference import Reader  # noqa: E402

_TOP, _LEAST = 2**63 - 1, -(2**63)
_PAST = 2**53 + 1  # the least positive whole number a double does not hold


def _call(name: str, column: Column, **attrs: object) -> Column:
    tree = {"op": "call", "name": name, "args": [{"op": "col", "name": "x"}]}
    return Reader({"x": column}, [], {}).evaluate({**tree, "attrs": attrs})


@pytest.mark.parametrize("name", ["floor", "ceil"])
def test_floor_and_ceil_of_a_whole_number_are_the_number(name: str) -> None:
    values = [_PAST, _TOP, _LEAST, -_PAST - 2, None]

    answer = _call(name, Column("i64", values))

    assert answer.dtype == "i64"
    assert answer.values == [9007199254740993, _TOP, _LEAST, -9007199254740995, None]
    assert [type(v) for v in answer.values[:4]] == [int] * 4


def test_abs_and_sign_of_a_whole_number_are_exact() -> None:
    runs = [[_PAST, -3], [-(2**60) - 7, 5], None]

    absolute = _call("abs", Column("list[i64]", runs))
    sign = _call("sign", Column("list[i64]", runs))

    assert absolute.dtype == sign.dtype == "list[i64]"
    assert absolute.values == [[9007199254740993, 3], [1152921504606846983, 5], None]
    assert sign.values == [[1, -1], [-1, 1], None]


def test_abs_of_the_least_whole_number_is_refused_by_name() -> None:
    # 2^63 is the one absolute value of an i64 that no i64 holds.
    with pytest.raises(DomainRefusal, match=r"^integer-overflow$"):
        _call("abs", Column("i64", [_LEAST, 5]))


@pytest.mark.parametrize(
    ("name", "attrs", "hand"),
    [
        ("sum", {}, [9007199254740996, 1152921504606846988]),
        (
            "cum_sum",
            {"reverse": False},
            [[9007199254740993, 9007199254740996], [5, 1152921504606846988]],
        ),
        (
            "cum_sum",
            {"reverse": True},
            [[9007199254740996, 3], [1152921504606846988, 1152921504606846983]],
        ),
        (
            "projection.remaining_sum",
            {},
            [[9007199254740996, 3], [1152921504606846988, 1152921504606846983]],
        ),
    ],
)
def test_a_total_of_whole_numbers_keeps_every_digit(
    name: str, attrs: dict, hand: list
) -> None:
    runs = Column("list[i64]", [[_PAST, 3], [5, 2**60 + 7]])

    answer = _call(name, runs, **attrs)

    assert answer.values == hand
    assert answer.dtype == ("i64" if name == "sum" else "list[i64]")


def test_a_running_product_of_whole_numbers_keeps_every_digit() -> None:
    runs = Column("list[i64]", [[2**31 - 1, 2**31 + 1], [-(2**31), 2**32 - 1]])

    answer = _call("cum_prod", runs, reverse=False)

    assert answer.values == [
        [2147483647, 4611686018427387903],
        [-2147483648, -9223372034707292160],
    ]


@pytest.mark.parametrize(
    ("value", "digits", "hand"),
    [
        (2**62, 17, 4611686018427387900),
        (-(2**62), 17, -4611686018427387900),
        (_TOP, 17, 9223372036854775800),
        (_TOP, 2, 9200000000000000000),
        (_PAST, 2, 9000000000000000),
        (-_PAST - 2, 15, -9007199254741000),
    ],
)
def test_significant_figures_of_a_whole_number_are_kept_exactly(
    value: int, digits: int, hand: int
) -> None:
    answer = _call("round_sig_figs", Column("i64", [value]), digits=digits)

    assert answer.dtype == "i64"
    assert answer.values == [hand]


def test_significant_figures_past_i64_are_still_refused() -> None:
    # 2^63 - 1 to ten figures is 9223372037000000000, which no i64 holds.
    with pytest.raises(DomainRefusal, match=r"^integer-overflow$"):
        _call("round_sig_figs", Column("i64", [_TOP]), digits=10)


@pytest.mark.parametrize(
    ("name", "attrs", "run"),
    [
        ("sum", {}, [_TOP, 1]),
        ("sum", {}, [_LEAST, -1]),
        ("cum_sum", {"reverse": False}, [_TOP, 1]),
        ("cum_sum", {"reverse": True}, [1, _TOP]),
        ("projection.remaining_sum", {}, [1, _TOP]),
        ("cum_prod", {"reverse": False}, [_LEAST, -1]),
        ("cum_prod", {"reverse": True}, [2**32, 2**31]),
    ],
)
def test_a_fold_past_i64_is_refused_by_name(
    name: str, attrs: dict, run: list[int]
) -> None:
    with pytest.raises(DomainRefusal, match=r"^integer-overflow$"):
        _call(name, Column("list[i64]", [[1, 2], run]), **attrs)


def test_a_total_whose_answer_fits_is_answered_though_a_period_passed_i64() -> None:
    # The answer is the total: 2^63 - 1 + 1 - 1, which an i64 holds.
    answer = _call("sum", Column("list[i64]", [[_TOP, 1, -1]]))

    assert answer.values == [_TOP]


def test_a_mean_of_whole_numbers_is_their_exact_total_divided_once() -> None:
    # 2^63 - 1 + 2^63 - 1 is past i64 and the mean is not: the total stays
    # whole and is divided once, correctly rounded.
    answer = _call("mean", Column("list[i64]", [[_TOP, _TOP], [100, 101, 101, 101]]))

    assert answer.dtype == "f64"
    assert answer.values == [9.223372036854775807e18, 100.75]


@pytest.mark.parametrize("name", ["fill_null", "fill_nan"])
def test_a_whole_number_past_2_53_does_not_meet_a_double_fill(name: str) -> None:
    tree = {
        "op": "call",
        "name": name,
        "args": [{"op": "col", "name": "x"}, {"op": "lit", "value": 0.5}],
        "attrs": {},
    }
    reader = Reader({"x": Column("i64", [_PAST, None])}, [], {})

    with pytest.raises(
        DomainRefusal, match=r"^arithmetic-outside-exact-numeric-range$"
    ):
        reader.evaluate(tree)


@pytest.mark.parametrize(
    ("write", "hand"),
    [
        (lambda af: af.n.floor(), [9007199254740993, _TOP]),
        (lambda af: af.n.abs(), [9007199254740993, _TOP]),
        (lambda af: af.L.list.sum(), [9007199254740996, 1152921504606846988]),
        (
            lambda af: af.L.cum_sum(reverse=False),
            [[9007199254740993, 9007199254740996], [5, 1152921504606846988]],
        ),
        (lambda af: af.n.round_sig_figs(17), [9007199254740993, 9223372036854775800]),
    ],
)
def test_the_reader_answers_the_producers_record_digit_for_digit(
    write: object, hand: list
) -> None:
    book = pl.DataFrame(
        [
            pl.Series("n", [_PAST, _TOP], dtype=pl.Int64),
            pl.Series("L", [[_PAST, 3], [5, 2**60 + 7]], dtype=pl.List(pl.Int64)),
        ]
    )
    af = ActuarialFrame(book)
    af.r = write(af)  # type: ignore[operator]
    document = json.loads(GraphExporter(af).export(profile="executable"))
    node = next(n for n in document["nodes"] if n.get("column") == "r")
    columns = {
        "n": Column("i64", [_PAST, _TOP]),
        "L": Column("list[i64]", [[_PAST, 3], [5, 2**60 + 7]]),
    }

    answer = Reader(columns, [], {}).evaluate(node["expr"])

    assert answer.dtype == node["dtype"]
    assert answer.values == hand == af.collect()["r"].to_list()
