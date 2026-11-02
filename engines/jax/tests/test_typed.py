# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The typed path's witnesses: an integer stays an integer, a date a day count.

The case against a float64 carrier for everything, run as tests. Each of these
passes trivially under a typed path and fails under a float one, which is what
makes them witnesses rather than coverage.
"""

from __future__ import annotations

from tests.conftest import answered, invocation, run_scalar, run_unary


def _binop(kind: str, left: dict, right: dict) -> dict:
    return {"op": "binop", "kind": kind, "left": left, "right": right}


def _col(name: str) -> dict:
    return {"op": "col", "name": name}


def _lit(value: object) -> dict:
    return {"op": "lit", "value": value}


def _date(day: str) -> dict:
    """Return a date literal, which carries its day under its own key (12.1)."""
    return {"op": "lit", "date": day}


def test_two_to_the_fifty_three_minus_one_plus_two_is_exact() -> None:
    outcome = run_scalar("add", 2**53 - 1, 2)
    assert outcome.value == 2**53 + 1


def test_the_nested_delta_of_two_survives_its_own_subtraction() -> None:
    """(2^53 - 1 + 2) - (2^53 - 1) is 2, and is 0 under a float carrier."""
    outcome = answered(
        invocation(
            _binop(
                "sub",
                _binop("add", _col("a"), _lit(2)),
                _col("a"),
            ),
            {"a": {"dtype": "i64", "values": [2**53 - 1]}},
            "i64",
        )
    )
    assert outcome.value == 2


def test_an_integer_beyond_two_to_the_fifty_three_meeting_a_double_refuses() -> None:
    outcome = answered(
        invocation(
            _binop("add", _col("a"), _col("b")),
            {
                "a": {"dtype": "i64", "values": [2**53 + 1]},
                "b": {"dtype": "f64", "values": [0.5]},
            },
            "f64",
        )
    )
    assert outcome.refused_with == "mixed.2p53"


def test_two_integers_inside_the_range_meet_a_double_without_a_word() -> None:
    outcome = answered(
        invocation(
            _binop("add", _col("a"), _col("b")),
            {
                "a": {"dtype": "i64", "values": [2**53]},
                "b": {"dtype": "f64", "values": [0.0]},
            },
            "f64",
        )
    )
    assert outcome.value == float(2**53)


def test_a_date_stays_a_calendar_day_and_compares_as_one() -> None:
    outcome = answered(
        invocation(
            _binop("lt", _col("d"), _date("2024-06-01")),
            {"d": {"dtype": "date", "values": ["2024-01-31", "2024-12-31"]}},
            "bool",
        )
    )
    assert outcome.value is True


def test_a_date_against_a_number_is_refused_rather_than_compared() -> None:
    outcome = answered(
        invocation(
            _binop("lt", _col("d"), _col("n")),
            {
                "d": {"dtype": "date", "values": ["2024-01-31"]},
                "n": {"dtype": "i64", "values": [5]},
            },
            "bool",
        )
    )
    assert outcome.value is None
    assert "infers no ordering between them" in outcome.report


def test_a_boolean_stays_a_boolean() -> None:
    outcome = answered(
        invocation(
            _binop("and", _col("a"), _col("b")),
            {
                "a": {"dtype": "bool", "values": [True]},
                "b": {"dtype": "bool", "values": [False]},
            },
            "bool",
        )
    )
    assert outcome.value is False


def test_text_has_equality_and_code_point_order() -> None:
    equal = answered(
        invocation(
            _binop("eq", _col("s"), _lit("A")),
            {"s": {"dtype": "str", "values": ["A", "B"]}},
            "bool",
        )
    )
    assert equal.value is True
    # 11.1.26: text orders by code point, so the capital sorts before the
    # small letter -- "B" < "a" -- whatever order the run interned them in.
    ordered = answered(
        invocation(
            _binop("lt", _col("s"), _lit("a")),
            {"s": {"dtype": "str", "values": ["B", "b"]}},
            "bool",
        )
    )
    assert ordered.value is True
    across = answered(
        invocation(
            _binop("lt", _col("s"), _col("n")),
            {
                "s": {"dtype": "str", "values": ["A"]},
                "n": {"dtype": "i64", "values": [5]},
            },
            "bool",
        )
    )
    assert across.value is None
    assert "infers no ordering between them" in across.report


def test_a_comparison_assigned_to_a_double_column_is_one_and_zero() -> None:
    """11.1.26's stored indicator: the same truth value, another representation."""
    outcome = answered(
        invocation(
            _binop("gt", _col("a"), _lit(0)),
            {"a": {"dtype": "i64", "values": [3]}},
            "f64",
        )
    )
    assert outcome.value == 1.0


def test_an_integer_absolute_value_stays_an_integer() -> None:
    outcome = run_unary("abs", -(2**62))
    assert outcome.value == 2**62
