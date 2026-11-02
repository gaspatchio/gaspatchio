# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An operation carrying a wide column's type answers one type from both doors.

A ``UInt64`` book column whose values all fit an ``i64`` is read as ``Int64``
where a DataFrame enters the frame, but a LazyFrame's values are not in hand
there, so a least or greatest value, a bound, a rounding, a sign, a fill or a
period's value of it kept ``UInt64`` from that door alone: one book, two
types. Each now reads such a column as arithmetic does -- ``Int64`` where its
values fit, refused by name where one does not -- so the two doors agree. A
conversion, a test of presence and a comparison read the value by its digits
and are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

if TYPE_CHECKING:
    from collections.abc import Callable

_PAST = 2**64 - 1

# (what the author wrote, the line, the hand values):
# pid is [7, 8] and ids is [[1, 2], [3, 4]].
_CARRYING: list[tuple[str, Callable[[Any], Any], list[Any]]] = [
    ("ids.list.max()", lambda af: af.ids.list.max(), [2, 4]),
    ("ids.list.min()", lambda af: af.ids.list.min(), [1, 3]),
    ("ids.list.get(0)", lambda af: af.ids.list.get(0), [1, 3]),
    ("pid.clip(0, 7)", lambda af: af.pid.clip(0, 7), [7, 7]),
    ("pid.abs()", lambda af: af.pid.abs(), [7, 8]),
    ("pid.round(0)", lambda af: af.pid.round(0), [7, 8]),
    ("pid.floor()", lambda af: af.pid.floor(), [7, 8]),
    ("pid.sign()", lambda af: af.pid.sign(), [1, 1]),
    ("pid.fill_null(0)", lambda af: af.pid.fill_null(0), [7, 8]),
]


def _book(*, past: bool) -> pl.DataFrame:
    last = _PAST if past else 8
    return pl.DataFrame(
        {
            "pid": pl.Series([7, last], dtype=pl.UInt64),
            "ids": pl.Series([[1, 2], [3, last - 4]], dtype=pl.List(pl.UInt64)),
        }
    )


@pytest.mark.parametrize(
    ("written", "line", "expected"), _CARRYING, ids=[c[0] for c in _CARRYING]
)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_a_fitting_wide_column_answers_int64_from_both_doors(
    door: str,
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
    expected: list[Any],
) -> None:
    book = _book(past=False)
    af = ActuarialFrame(book.lazy() if door == "LazyFrame" else book)
    af.m = line(af)
    out = af.collect()

    assert out["m"].to_list() == expected
    assert out.schema["m"] == pl.Int64


@pytest.mark.parametrize(
    ("written", "line"),
    [(c[0], c[1]) for c in _CARRYING],
    ids=[c[0] for c in _CARRYING],
)
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_a_wide_column_past_i64_is_refused_from_both_doors(
    door: str,
    written: str,  # noqa: ARG001 -- the id
    line: Callable[[Any], Any],
) -> None:
    book = _book(past=True)
    af = ActuarialFrame(book.lazy() if door == "LazyFrame" else book)
    af.m = line(af)

    with pytest.raises(pl.exceptions.InvalidOperationError) as caught:
        af.collect()

    assert (
        "holds a whole number outside the signed 64-bit range, and an operation "
        in (str(caught.value))
    )
    assert ".to_text()" in str(caught.value)


@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_reading_the_digits_of_a_column_past_i64_is_unchanged(door: str) -> None:
    book = _book(past=True)
    af = ActuarialFrame(book.lazy() if door == "LazyFrame" else book)
    af.t = af.pid.to_text()
    af.n = af.pid.is_null()
    out = af.collect()

    assert out["t"].to_list() == ["7", str(_PAST)]
    assert out["n"].to_list() == [False, False]
