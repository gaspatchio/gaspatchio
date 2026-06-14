# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test Sum/Count/Min/Max — trivial mergeable aggregators on the new Protocol."""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio_core.scenarios._aggregators import Count, Max, Min, Sum


def test_sum_correctness() -> None:
    """Sum across-scenarios returns total."""
    a = Sum("v")
    s = a.create_accumulator()
    for v in [1.0, 2.0, 3.0]:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(6.0)


def test_count_correctness() -> None:
    """Count returns number of values added."""
    a = Count("v")
    s = a.create_accumulator()
    for _ in range(5):
        s = a.add_input(s, 1.0)
    assert a.extract_output(s) == 5


def test_min_correctness() -> None:
    """Min across-scenarios returns smallest."""
    a = Min("v")
    s = a.create_accumulator()
    for v in [3.0, 1.0, 2.0]:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(1.0)


def test_max_correctness() -> None:
    """Max across-scenarios returns largest."""
    a = Max("v")
    s = a.create_accumulator()
    for v in [3.0, 1.0, 2.0]:
        s = a.add_input(s, v)
    assert a.extract_output(s) == pytest.approx(3.0)


def test_sum_within_expr_default() -> None:
    """Default within reduction is sum-of-column."""
    a = Sum("loss")
    cf = a.canonical_form()
    assert cf["within"] == "sum"
    assert cf["column"] == "loss"


def test_sum_named_within() -> None:
    """Explicit within= reduction name surfaces in canonical_form."""
    a = Sum("loss", within="mean")
    cf = a.canonical_form()
    assert cf["within"] == "mean"


def test_invalid_within_raises() -> None:
    """Unknown within name raises ValueError listing valid names."""
    with pytest.raises(ValueError, match="within must be one of"):
        Sum("loss", within="invalid")


def test_within_expr_is_polars_expr() -> None:
    """within_expr() returns a polars expression usable in group_by.agg."""
    a = Sum("loss")
    expr = a.within_expr()
    assert isinstance(expr, pl.Expr)


def test_sum_merge() -> None:
    """Sum.merge_accumulators is associative."""
    a = Sum("v")
    left = a.create_accumulator()
    for v in [1.0, 2.0]:
        left = a.add_input(left, v)
    right = a.create_accumulator()
    for v in [3.0, 4.0]:
        right = a.add_input(right, v)
    merged = a.merge_accumulators(left, right)
    assert a.extract_output(merged) == pytest.approx(10.0)


def test_min_max_empty_extract() -> None:
    """Min/Max on empty state returns NaN."""
    assert math.isnan(Min("v").extract_output(Min("v").create_accumulator()))
    assert math.isnan(Max("v").extract_output(Max("v").create_accumulator()))
