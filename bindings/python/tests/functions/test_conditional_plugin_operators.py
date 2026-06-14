# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for all comparison operators with list_conditional plugin
# ABOUTME: Verifies all 6 operators (==, !=, <, <=, >, >=) work with plugin integration
# ruff: noqa: S101, PLR2004
# type: ignore[call-non-callable]
"""Tests for all comparison operators with list_conditional plugin integration."""

import polars as pl

from gaspatchio_core import ActuarialFrame, when


def test_ne_operator() -> None:
    """Test != operator with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
        }
    )

    af.result = when(af.month != af.term).then(1.0).otherwise(0.0)  # type: ignore[operator]

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    expected = [1.0, 1.0, 0.0, 1.0]  # Everything except month==2
    assert result_list == expected


def test_lt_operator() -> None:
    """Test < operator with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
        }
    )

    af.result = when(af.month < af.term).then(1.0).otherwise(0.0)  # type: ignore[operator]

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    expected = [1.0, 1.0, 0.0, 0.0]  # Months 0,1 < 2
    assert result_list == expected


def test_lte_operator() -> None:
    """Test <= operator with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
        }
    )

    af.result = when(af.month <= af.term).then(1.0).otherwise(0.0)  # type: ignore[operator]

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    expected = [1.0, 1.0, 1.0, 0.0]  # Months 0,1,2 <= 2
    assert result_list == expected


def test_gt_operator() -> None:
    """Test > operator with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
        }
    )

    af.result = when(af.month > af.term).then(1.0).otherwise(0.0)  # type: ignore[operator]

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    expected = [0.0, 0.0, 0.0, 1.0]  # Only month 3 > 2
    assert result_list == expected


def test_gte_operator() -> None:
    """Test >= operator with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
        }
    )

    af.result = when(af.month >= af.term).then(1.0).otherwise(0.0)  # type: ignore[operator]

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    expected = [0.0, 0.0, 1.0, 1.0]  # Months 2,3 >= 2
    assert result_list == expected


def test_all_operators_no_explode() -> None:
    """Verify all operators produce no EXPLODE in query plan."""
    # Test each operator separately to avoid reusing ActuarialFrame
    test_cases = [
        ("eq", "=="),
        ("ne", "!="),
        ("lt", "<"),
        ("lte", "<="),
        ("gt", ">"),
        ("gte", ">="),
    ]

    for op_name, op_symbol in test_cases:
        af = ActuarialFrame(
            {
                "month": [[0, 1, 2, 3]],
                "value": [100.0],
            }
        )

        # Apply operator based on name
        if op_symbol == "==":
            condition = af.month == 2
        elif op_symbol == "!=":
            condition = af.month != 2
        elif op_symbol == "<":
            condition = af.month < 2
        elif op_symbol == "<=":
            condition = af.month <= 2
        elif op_symbol == ">":
            condition = af.month > 2
        else:  # >=
            condition = af.month >= 2

        af.result = when(condition).then(af.value).otherwise(0.0)  # type: ignore[arg-type]

        # Access internal LazyFrame and check plan
        lf = object.__getattribute__(af, "_df")
        plan = lf.explain()

        assert "EXPLODE" not in plan, (
            f"Operator {op_name} should not produce EXPLODE in query plan"
        )
        assert "list_conditional" in plan.lower() or "FUNCTION" in plan, (
            f"Operator {op_name} should use list_conditional plugin"
        )
