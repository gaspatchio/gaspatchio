# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Section 11.1.12's rule for one line, read in one Polars pass.

``gspio compare`` reads every line through :func:`read_line`, and a comparison
of two versions of a model is to call it too. These cases pin what one line's
reading says, apart from any report: which exact aspect parts a float line and
where, what the policies before the first parted one come to, which cell
decided the ratio, and what a policy's magnitude is.
"""

from __future__ import annotations

import math

import polars as pl
import pytest

from gaspatchio.engines._agreement import (
    Cell,
    policy_magnitude,
    read_line,
    read_scale,
)

FLOATS = pl.List(pl.Float64)
NESTED = pl.List(pl.List(pl.Float64))


def _floats(values: list[object], dtype: pl.DataType = FLOATS) -> pl.Series:
    return pl.Series(values, dtype=dtype)


def test_a_policy_s_magnitude_is_its_largest_finite_value_through_every_list() -> None:
    values = _floats(
        [
            [1.0, -7.0, 2.0],
            [math.nan, 3.0],
            [3.0, math.nan],
            [math.inf, -2.0],
            [None, -0.5],
            [],
            None,
        ]
    )
    assert policy_magnitude(values).to_list() == [7.0, 3.0, 3.0, 2.0, 0.5, 0.0, 0.0]

    nested = _floats([[[1.0], [-9.0, math.inf]], [None, []], None], NESTED)
    assert policy_magnitude(nested).to_list() == [9.0, 0.0, 0.0]

    integers = pl.Series([[1, -12], [3]], dtype=pl.List(pl.Int32))
    assert policy_magnitude(integers).to_list() == [12.0, 3.0]


@pytest.mark.parametrize(
    "values",
    [
        pl.Series([[True, False]]),
        pl.Series(["text"]),
        pl.Series([[1, 2]], dtype=pl.List(pl.Date)),
    ],
)
def test_values_that_are_not_numbers_add_nothing_to_a_scale(values: pl.Series) -> None:
    assert policy_magnitude(values).to_list() == [0.0]


def test_each_side_s_reads_supply_its_own_floor() -> None:
    # Two versions of a model: the after side's line reads a node the before
    # side's does not. Each side's floor is its own reads', and the scale is
    # the larger of the two.
    before_reads = [pl.Series([5.0, 1.0])]
    after_reads = [pl.Series([2.0, 8.0]), pl.Series([0.0, 3.0])]
    assert read_scale(before_reads, after_reads, 2).to_list() == [5.0, 8.0]
    assert read_scale([], [], 2).to_list() == [0.0, 0.0]


def test_an_exact_line_reads_a_null_list_as_a_list_of_one_null() -> None:
    before = pl.Series([None, [1, 2]], dtype=pl.List(pl.Int64))
    after = pl.Series([[None], [1, 2]], dtype=pl.List(pl.Int64))
    assert read_line(before, after, exact=True).parted is False

    longer = pl.Series([[None], [1, 2, 3]], dtype=pl.List(pl.Int64))
    reading = read_line(before, longer, exact=True)
    assert reading.parted is True
    assert reading.parted_policy == 1
    assert reading.parted_on is None
    assert reading.strict is False


def test_integer_widths_and_datetime_units_compare_as_values() -> None:
    narrow = pl.Series([[7, 8]], dtype=pl.List(pl.Int32))
    wide = pl.Series([[7, 8]], dtype=pl.List(pl.Int64))
    assert read_line(narrow, wide, exact=True).parted is False

    micro = pl.Series([1_000], dtype=pl.Datetime("us"))
    nano = pl.Series([1_000_000], dtype=pl.Datetime("ns"))
    assert read_line(micro, nano, exact=True).parted is False

    zoned = pl.Series([1_000], dtype=pl.Datetime("us", "UTC"))
    assert read_line(micro, zoned, exact=True).parted is True
    nulls = pl.Series([None], dtype=pl.Datetime("us"))
    assert (
        read_line(
            nulls, pl.Series([None], dtype=pl.Datetime("us", "UTC")), exact=True
        ).parted
        is False
    )


@pytest.mark.parametrize(
    ("before", "after", "aspect"),
    [
        # A list's own length is read before any of its elements.
        ([[1.0, math.nan]], [[1.0]], "length"),
        # An element that is a list on one side and a null on the other is
        # read before anything at a later period.
        ([[[1.0], [2.0]]], [[None, [2.0, 3.0]]], "null-positions"),
        ([[[1.0], [2.0]]], [[[1.0], [2.0, 3.0]]], "length"),
        # Among one value's classes, a null decides before a NaN, and a NaN
        # before an infinity's sign.
        ([[None]], [[math.nan]], "null-positions"),
        ([[math.nan]], [[math.inf]], "nan-class"),
        ([[math.inf]], [[-math.inf]], "inf-sign"),
        ([[1.0]], [[math.inf]], "inf-sign"),
        # The first place in the timeline decides, whatever parts later.
        ([[1.0, math.nan, None]], [[1.0, 2.0, 3.0]], "nan-class"),
    ],
)
def test_a_float_line_parts_on_the_first_exact_aspect_in_its_timeline(
    before: list[object], after: list[object], aspect: str
) -> None:
    depth = 2 if isinstance(before[0], list) and isinstance(before[0][0], list) else 1
    dtype = NESTED if depth == 2 else FLOATS
    reading = read_line(_floats(before, dtype), _floats(after, dtype), exact=False)
    assert reading.parted is True
    assert reading.parted_on == aspect
    assert reading.parted_policy == 0
    assert reading.strict is False


def test_the_policies_before_the_first_parted_one_supply_the_ratio() -> None:
    before = _floats([[100.0, 1.0], [10.0], [1.0, 2.0], [4.0]])
    after = _floats([[100.0, 1.0 + 1e-9], [10.0 + 1e-6], [1.0], [4.0 + 1.0]])
    reading = read_line(before, after, exact=False)
    assert reading.parted_on == "length"
    assert reading.parted_policy == 2
    # Policy 3 differs by far more, and is past the parted one.
    assert reading.max_abs == pytest.approx(1e-6)
    assert reading.max_ratio == pytest.approx(1e-7)
    # The second policy's own scale, over both sides.
    assert reading.scale == pytest.approx(10.0 + 1e-6)


def test_the_worst_cell_is_the_one_that_decided_the_ratio() -> None:
    before = _floats([[1000.0, 1000.0], [1.0, 1.0, 1.0]])
    after = _floats([[1000.0, 1000.0 + 1e-6], [1.0, 1.0 + 1e-9, 1.0 + 1e-9]])
    reading = read_line(before, after, exact=False, read_scale=pl.Series([0.0, 0.0]))
    assert reading.parted is False
    assert reading.max_ratio == pytest.approx(1e-9, rel=1e-3)
    assert reading.worst == Cell(policy=1, period=(1,), before=1.0, after=1.0 + 1e-9)
    assert reading.scale == pytest.approx(1.0 + 1e-9)


def test_a_read_s_magnitude_widens_that_policy_s_band_and_no_other() -> None:
    before = _floats([[0.0], [0.0]])
    after = _floats([[7e-10], [7e-10]])
    scale = read_scale([pl.Series([17000.0, 1.0])], [pl.Series([17000.0, 1.0])], 2)
    reading = read_line(before, after, exact=False, read_scale=scale)
    assert reading.max_ratio == pytest.approx(7e-10)
    assert reading.scale == 1.0
    assert reading.worst == Cell(policy=1, period=(0,), before=0.0, after=7e-10)


def test_a_line_that_moved_nothing_has_no_worst_cell() -> None:
    values = _floats([[1.0, -0.0], [2.0]])
    same = _floats([[1.0, 0.0], [2.0]])
    reading = read_line(values, same, exact=False)
    assert reading.parted is False
    assert reading.max_ratio == 0.0
    assert reading.max_abs == 0.0
    assert reading.strict is True
    assert reading.worst is None


def test_one_value_per_policy_is_a_timeline_of_one_value() -> None:
    before = pl.Series([1.0, None, 3.0])
    after = pl.Series([1.0, None, 3.0 + 3e-12])
    reading = read_line(before, after, exact=False)
    assert reading.parted is False
    assert reading.worst == Cell(policy=2, period=(), before=3.0, after=3.0 + 3e-12)

    parted = read_line(before, pl.Series([1.0, 2.0, 3.0]), exact=False)
    assert parted.parted_on == "null-positions"
    assert parted.parted_policy == 1


def test_two_columns_of_different_books_are_refused() -> None:
    with pytest.raises(ValueError, match="pair the rows"):
        read_line(pl.Series([1.0]), pl.Series([1.0, 2.0]), exact=False)
