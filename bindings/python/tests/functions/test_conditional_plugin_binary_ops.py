# ABOUTME: Tests for binary operations (&, |, ~) with list_conditional plugin
# ABOUTME: Verifies AND, OR, NOT work correctly with plugin integration
# ruff: noqa: S101, PLR2004
# type: ignore[call-non-callable]
"""Tests for binary operations with list_conditional plugin integration."""

import polars as pl

from gaspatchio_core import ActuarialFrame, when


def test_and_operation() -> None:
    """Test & (AND) operation with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "age": [[25, 35, 45, 55, 65, 75]],
            "sum_assured": [500000],
        }
    )

    # Senior (age >= 65) AND high value (sum_assured > 400000)
    af.result = (
        when((af.age >= 65) & (af.sum_assured > 400000)).then(0.002).otherwise(0.0)
    )

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    # Only ages 65, 75 meet BOTH conditions
    expected = [0.0, 0.0, 0.0, 0.0, 0.002, 0.002]
    assert result_list == expected


def test_or_operation() -> None:
    """Test | (OR) operation with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "age": [[25, 35, 45, 55, 65, 75]],
            "duration": [5],
        }
    )

    # Young (age < 30) OR long duration (duration > 4)
    af.result = when((af.age < 30) | (af.duration > 4)).then(0.1).otherwise(0.0)

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    # Age 25 < 30 OR duration 5 > 4 (all elements match because duration=5 for all)
    expected = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    assert result_list == expected


def test_not_operation() -> None:
    """Test ~ (NOT) operation with list_conditional plugin."""
    af = ActuarialFrame(
        {
            "age": [[25, 35, 45, 55, 65, 75]],
        }
    )

    # Not senior (NOT age >= 65)
    af.result = when(~(af.age >= 65)).then(1.0).otherwise(0.0)

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    # Ages < 65
    expected = [1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
    assert result_list == expected


def test_complex_combination() -> None:
    """Test complex combination: (a & b) | c."""
    af = ActuarialFrame(
        {
            "age": [[25, 35, 45, 55, 65, 75]],
            "sum_assured": [500000],
            "duration": [3],
        }
    )

    # (Senior AND high value) OR short duration
    af.result = (
        when(((af.age >= 65) & (af.sum_assured > 400000)) | (af.duration < 5))
        .then(1.0)
        .otherwise(0.0)
    )

    result = af.collect()

    assert result["result"].dtype == pl.List(pl.Float64)
    result_list = result["result"].to_list()[0]
    # duration < 5 is True for all, so all should be 1.0
    expected = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    assert result_list == expected


def test_binary_ops_no_explode() -> None:
    """Verify binary operations produce no EXPLODE in query plan."""
    # Test AND operation
    af_and = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
            "value": [100.0],
        }
    )
    af_and.result = (
        when((af_and.month >= 1) & (af_and.month <= 2))
        .then(af_and.value)
        .otherwise(0.0)
    )

    # Access internal LazyFrame and check plan
    lf = object.__getattribute__(af_and, "_df")
    plan = lf.explain()

    assert "EXPLODE" not in plan, "AND operation should not produce EXPLODE"
    assert "list_conditional" in plan.lower() or "FUNCTION" in plan, (
        "AND operation should use list_conditional plugin"
    )

    # Test OR operation
    af_or = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
            "value": [100.0],
        }
    )
    af_or.result = (
        when((af_or.month < 1) | (af_or.month > 2)).then(af_or.value).otherwise(0.0)
    )

    lf_or = object.__getattribute__(af_or, "_df")
    plan_or = lf_or.explain()

    assert "EXPLODE" not in plan_or, "OR operation should not produce EXPLODE"

    # Test NOT operation
    af_not = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
            "value": [100.0],
        }
    )
    af_not.result = when(~(af_not.month == 2)).then(af_not.value).otherwise(0.0)

    lf_not = object.__getattribute__(af_not, "_df")
    plan_not = lf_not.explain()

    assert "EXPLODE" not in plan_not, "NOT operation should not produce EXPLODE"
