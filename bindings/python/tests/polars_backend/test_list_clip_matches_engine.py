# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The ``list_clip`` kernel answers what ``pl.Expr.clip`` answers.

``clip`` reaches Polars two ways. A per-policy value, or a per-period one
whose bounds are values, goes through the engine's own ``clip``; a
per-period value whose bounds read a column goes through the ``list_clip``
kernel, because a named column cannot be reached inside ``list.eval``.
Two paths for one formula is only safe while they agree, and on crossed
bounds -- ``lower`` above ``upper`` -- they did not: the engine answered
``[8.0, 8.0, 2.0]`` where the kernel answered ``[2.0, 2.0, 2.0]``.

The rule the engine keeps, read off its behaviour at Polars 1.42.1: the
lower bound is tested first, so a value below it becomes the lower bound,
and a value at or above it that is above the upper bound becomes the upper
bound. Crossed, that is a step at the lower bound rather than a constant.
The kernel had composed ``max`` then ``min``, which is the same answer
whenever the bounds are ordered and the upper bound everywhere when they
are not -- and which also swallowed a NaN into a bound, because Rust's
``f64::max`` returns its other operand against a NaN while a comparison
against one is simply false.

These tests hold the two paths to each other rather than to a transcript,
so the day Polars changes its mind the failure names the kernel that has
to follow.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio.frame.lowering._polars.plugins import list_clip

NAN = float("nan")

# (name, one row of values, lower bound, upper bound)
BOUND_SHAPES = [
    ("crossed", [0.0, 1.0, 2.0, 5.0, 8.0, 9.0, 10.0], 8.0, 2.0),
    ("touching", [0.0, 5.0, 10.0], 5.0, 5.0),
    ("normal", [0.0, 5.0, 10.0], 2.0, 8.0),
    ("crossed_wide_apart", [-100.0, 0.0, 100.0], 50.0, -50.0),
    ("crossed_negative", [-10.0, -5.0, -1.0], -2.0, -8.0),
]

# (name, one row of values) -- the shapes a list column comes in.
LIST_SHAPES = [
    ("empty", []),
    ("nulls_inside", [1.0, None, 10.0]),
    ("all_null", [None, None]),
    ("single_element", [1.0]),
]


def _kernel(values: list, lower: float, upper: float) -> list:
    """Clip one row through the kernel, its bounds arriving as columns."""
    frame = pl.DataFrame(
        {"v": [values], "lo": [lower], "hi": [upper]},
        schema={"v": pl.List(pl.Float64), "lo": pl.Float64, "hi": pl.Float64},
    )
    clipped = frame.select(
        list_clip(pl.col("v"), pl.col("lo"), pl.col("hi")).alias("r")
    )
    return clipped["r"].to_list()[0]


def _engine(values: list, lower: float, upper: float) -> list:
    """Clip the same row through Polars' own ``clip``, inside the list."""
    frame = pl.DataFrame({"v": [values]}, schema={"v": pl.List(pl.Float64)})
    clipped = frame.select(
        pl.col("v").list.eval(pl.element().clip(lower, upper)).alias("r")
    )
    return clipped["r"].to_list()[0]


def _same(left: list, right: list) -> bool:
    """Compare two clipped rows, counting NaN as equal to NaN."""
    if len(left) != len(right):
        return False
    return all(
        (a is None and b is None)
        or (
            a is not None
            and b is not None
            and (a == b or (math.isnan(a) and math.isnan(b)))
        )
        for a, b in zip(left, right, strict=True)
    )


class TestTheCrossedCaseItself:
    """The disagreement this alignment closes, written out in full."""

    def test_the_lower_bound_is_tested_first(self) -> None:
        """``clip(8, 2)`` steps at the lower bound; it is not a constant.

        Every value below 8 comes back 8; every value from 8 up is above
        the upper bound and comes back 2. The kernel used to answer 2 for
        all seven.
        """
        values = [0.0, 1.0, 2.0, 5.0, 8.0, 9.0, 10.0]
        expected = [8.0, 8.0, 8.0, 8.0, 2.0, 2.0, 2.0]

        assert _kernel(values, 8.0, 2.0) == expected
        assert _engine(values, 8.0, 2.0) == expected

    def test_the_flat_engine_path_answers_the_same(self) -> None:
        """The per-policy shape of the same formula, for the same values."""
        flat = pl.DataFrame({"v": [0.0, 1.0, 2.0, 5.0, 8.0, 9.0, 10.0]})
        clipped = flat.select(pl.col("v").clip(8.0, 2.0))["v"].to_list()

        assert clipped == [8.0, 8.0, 8.0, 8.0, 2.0, 2.0, 2.0]
        assert _kernel([0.0, 1.0, 2.0, 5.0, 8.0, 9.0, 10.0], 8.0, 2.0) == clipped

    def test_bounds_that_cross_on_some_rows_only(self) -> None:
        """Per-row bounds decide per row; one crossed row leaves its neighbour alone."""
        frame = pl.DataFrame(
            {
                "v": [[1.0, 5.0, 10.0], [1.0, 5.0, 10.0]],
                "lo": [8.0, 2.0],
                "hi": [2.0, 8.0],
            }
        )
        clipped = frame.select(
            list_clip(pl.col("v"), pl.col("lo"), pl.col("hi")).alias("r")
        )["r"].to_list()

        assert clipped == [[8.0, 8.0, 2.0], [2.0, 5.0, 8.0]]

    def test_bounds_that_cross_element_by_element(self) -> None:
        """List-typed bounds cross on their own elements, not on the row."""
        frame = pl.DataFrame(
            {
                "v": [[1.0, 5.0, 10.0]],
                "lo": [[8.0, 2.0, 8.0]],
                "hi": [[2.0, 8.0, 2.0]],
            }
        )
        clipped = frame.select(
            list_clip(pl.col("v"), pl.col("lo"), pl.col("hi")).alias("r")
        )["r"].to_list()

        assert clipped == [[8.0, 5.0, 2.0]]


class TestTheTwoPathsAgree:
    """Byte-equality between the kernel and the engine, shape by shape."""

    @pytest.mark.parametrize(("name", "values", "lower", "upper"), BOUND_SHAPES)
    def test_bound_shapes(
        self, name: str, values: list, lower: float, upper: float
    ) -> None:
        assert _kernel(values, lower, upper) == _engine(values, lower, upper), name

    @pytest.mark.parametrize(("name", "values"), LIST_SHAPES)
    @pytest.mark.parametrize(("lower", "upper"), [(2.0, 8.0), (8.0, 2.0), (5.0, 5.0)])
    def test_list_shapes(
        self, name: str, values: list, lower: float, upper: float
    ) -> None:
        assert _kernel(values, lower, upper) == _engine(values, lower, upper), name

    @pytest.mark.parametrize(("lower", "upper"), [(2.0, 8.0), (8.0, 2.0)])
    def test_a_nan_value_comes_back_nan_on_both_paths(
        self, lower: float, upper: float
    ) -> None:
        """A NaN passes neither comparison, so neither path moves it to a bound."""
        values = [NAN, 1.0, 10.0]
        kernel = _kernel(values, lower, upper)
        engine = _engine(values, lower, upper)

        assert math.isnan(kernel[0])
        assert _same(kernel, engine)

    @pytest.mark.parametrize(
        ("lower", "upper"),
        [(float("-inf"), 2.0), (8.0, float("inf"))],
    )
    def test_an_absent_bound_spelled_as_its_infinity(
        self, lower: float, upper: float
    ) -> None:
        """One-sided clips reach the kernel with an infinity for the missing side."""
        values = [0.0, 1.0, 2.0, 5.0, 8.0, 9.0, 10.0]

        assert _kernel(values, lower, upper) == _engine(values, lower, upper)
