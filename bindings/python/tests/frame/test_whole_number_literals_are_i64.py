# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A whole number written into a formula is the ``i64`` the record names it.

Polars gives an integer literal no width of its own, and where nothing beside
it set the type it settled on ``Int32``. ``af.c = 5`` stored an ``Int32``
column; ``when(af.x > 2).then(70000).otherwise(0)`` answered one; and
``* 70000`` downstream wrapped to 605,032,704 where the hand value is
4,900,000,000 -- in a model whose record, and whose JAX replay, said ``i64``
and computed 4,900,000,000. Every place the frame turns a Python whole number
into a Polars literal now states it as ``Int64``: an operand, a branch, a
fill, a constant assigned as a column, a NumPy integer, and a Series or array
of integers handed in as a column.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
import pytest

from gaspatchio import ActuarialFrame, when

if TYPE_CHECKING:
    from collections.abc import Callable


def _book() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame({"pid": [1, 2], "x": [1.5, 3.5], "flag": pl.Series([True, None])})
    )


def _projected() -> ActuarialFrame:
    return _book().projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_months",
        until_value=3,
        frequency="monthly",
    )


# One value per policy: (what the author wrote, the line, the hand values).
_PER_POLICY: list[tuple[str, Callable[[Any], Any], list[int | None]]] = [
    ("c = 5", lambda _: 5, [5, 5]),
    (
        "when(x > 2).then(70000).otherwise(0) * 70000",
        lambda af: when(af.x > 2).then(70000).otherwise(0) * 70000,
        [0, 4_900_000_000],
    ),
    (
        "when(x > 2).then(70000).otherwise(0)",
        lambda af: when(af.x > 2).then(70000).otherwise(0),
        [0, 70000],
    ),
    (
        "a chain of whole-number branches",
        lambda af: when(af.x > 3).then(2).when(af.x > 1).then(1).otherwise(0),
        [1, 2],
    ),
    (
        "when(flag).then(None).otherwise(3)",
        lambda af: when(af.flag).then(None).otherwise(3),
        [None, 3],
    ),
    (
        "-(when(...).then(1).otherwise(0))",
        lambda af: -(when(af.x > 2).then(1).otherwise(0)),
        [0, -1],
    ),
    (
        "when(...).then(1).otherwise(0).abs()",
        lambda af: when(af.x > 2).then(-1).otherwise(0).abs(),
        [0, 1],
    ),
    (
        "when(...).then(-3).otherwise(2).sign()",
        lambda af: when(af.x > 2).then(-3).otherwise(2).sign(),
        [1, -1],
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _PER_POLICY, ids=[c[0] for c in _PER_POLICY]
)
def test_a_whole_number_per_policy_is_an_int64(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[int | None],
) -> None:
    af = _book()
    af.r = line(af)
    out = af.collect()

    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == expected


def test_a_constant_column_times_70000_twice_does_not_wrap() -> None:
    """Hand value: 5 * 70,000 * 70,000 = 24,500,000,000 (was -1,269,803,776)."""
    af = _book()
    af.c = 5
    af.d = af.c * 70000 * 70000
    out = af.collect()

    assert out.schema["c"] == pl.Int64
    assert out["d"].to_list() == [24_500_000_000, 24_500_000_000]


def test_a_numpy_whole_number_assigned_is_an_int64() -> None:
    """numpy.int32(70000) stored an Int32; times 70,000 is 4,900,000,000."""
    af = _book()
    af.c = np.int32(70000)
    af.d = af.c * 70000
    out = af.collect()

    assert out.schema["c"] == pl.Int64
    assert out["d"].to_list() == [4_900_000_000, 4_900_000_000]


@pytest.mark.parametrize(
    ("column", "expected"),
    [
        (pl.Series("c", [70000, 1], dtype=pl.Int32), [70_000_000_000, 1_000_000]),
        (np.array([70000, 1], dtype=np.int32), [70_000_000_000, 1_000_000]),
        (np.array([30000, 1], dtype=np.int16), [30_000_000_000, 1_000_000]),
    ],
    ids=["Int32 series", "int32 array", "int16 array"],
)
def test_a_narrow_integer_column_handed_in_is_an_int64(
    column: object, expected: list[int]
) -> None:
    """A column of data enters as a book column does, so a million times it fits."""
    af = _book()
    af.c = column
    af.d = af.c * 1_000_000
    out = af.collect()

    assert out.schema["c"] == pl.Int64
    assert out["d"].to_list() == expected


def test_a_whole_number_beside_a_decimal_still_widens_to_the_decimal() -> None:
    af = _book()
    af.r = when(af.x > 2).then(1).otherwise(0.5)
    out = af.collect()

    assert out.schema["r"] == pl.Float64
    assert out["r"].to_list() == [0.5, 1.0]


def test_a_whole_number_beside_an_int64_column_is_unchanged() -> None:
    af = _book()
    af.r = af.pid * 3 - 1
    out = af.collect()

    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == [2, 5]


# One value per period: (what the author wrote, the line, the hand values).
_PER_PERIOD: list[tuple[str, Callable[[Any], Any], list[Any]]] = [
    ("c = 5 on a projected frame", lambda _: 5, [5, 5]),
    (
        "when(month > 0).then(70000).otherwise(0) * 70000",
        lambda af: when(af.month > 0).then(70000).otherwise(0) * 70000,
        [[0, 4_900_000_000, 4_900_000_000, 4_900_000_000]] * 2,
    ),
    (
        "when(month > 0).then(1).otherwise(0).cum_sum()",
        lambda af: when(af.month > 0).then(1).otherwise(0).cum_sum(),
        [[0, 1, 2, 3]] * 2,
    ),
    (
        "when(month > 0).then(70000).otherwise(0).fill_null(0)",
        lambda af: when(af.month > 0).then(70000).otherwise(0).fill_null(0),
        [[0, 70000, 70000, 70000]] * 2,
    ),
]


@pytest.mark.parametrize(
    ("written", "line", "expected"), _PER_PERIOD, ids=[c[0] for c in _PER_PERIOD]
)
def test_a_whole_number_per_period_is_an_int64(
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[Any],
) -> None:
    af = _projected()
    af.r = line(af)
    out = af.collect()

    dtype = out.schema["r"]
    assert (dtype.inner if isinstance(dtype, pl.List) else dtype) == pl.Int64
    assert out["r"].to_list() == expected


def test_a_per_period_total_of_whole_number_branches_is_an_int64() -> None:
    """Three periods past month 0 hold 1 each: the total is 3."""
    af = _projected()
    af.r = when(af.month > 0).then(1).otherwise(0).list.sum()
    out = af.collect()

    assert out.schema["r"] == pl.Int64
    assert out["r"].to_list() == [3, 3]
