# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A per-period clip of whole numbers by a column's bound answers whole numbers.

``af.duration.clip(upper_bound=af.cap)`` over a whole-number run answered
``list[f64]`` -- ``[0.0, 5.0, 10.0]`` -- while ``clip(upper_bound=10)`` kept
``list[i64]``, the record said ``list[f64]``, the JAX engine followed the
record and the reference reader answered ``list[i64]``. A clip keeps the
column's own type (11.1.3), whatever its bound is: a literal, a per-policy
column, or a per-period one. The kernel a column's bound takes holds the
values in doubles, so a value or bound at or past 2**53 in magnitude is
refused by name rather than compared as its nearest double.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

if TYPE_CHECKING:
    from collections.abc import Callable

# By hand: [0, 5, 12] and [3, 20, 1], capped at 10 and 4, floored at 2.
_BOOK = pl.DataFrame(
    [
        pl.Series("dur", [[0, 5, 12], [3, 20, 1]], dtype=pl.List(pl.Int64)),
        pl.Series("cap", [10, 4], dtype=pl.Int64),
        pl.Series("floor", [2, 2], dtype=pl.Int64),
        pl.Series("caps", [[10, 10, 10], [4, 4, 4]], dtype=pl.List(pl.Int64)),
    ]
)
_LINES: dict[str, tuple[Callable[[ActuarialFrame], object], list[list[int]]]] = {
    "a column's cap": (
        lambda af: af.dur.clip(upper_bound=af.cap),
        [[0, 5, 10], [3, 4, 1]],
    ),
    "a column's floor": (
        lambda af: af.dur.clip(lower_bound=af.floor),
        [[2, 5, 12], [3, 20, 2]],
    ),
    "two columns": (lambda af: af.dur.clip(af.floor, af.cap), [[2, 5, 10], [3, 4, 2]]),
    "a literal floor and a column's cap": (
        lambda af: af.dur.clip(2, af.cap),
        [[2, 5, 10], [3, 4, 2]],
    ),
    "a run of caps": (
        lambda af: af.dur.clip(upper_bound=af.caps),
        [[0, 5, 10], [3, 4, 1]],
    ),
    "a literal cap": (lambda af: af.dur.clip(upper_bound=10), [[0, 5, 10], [3, 10, 1]]),
}


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
@pytest.mark.parametrize("width", [pl.Int64, pl.Int32, pl.UInt8], ids=str)
@pytest.mark.parametrize("bound", list(_LINES))
def test_a_clip_keeps_the_whole_numbers_whatever_its_bound(
    engine: str, width: type[pl.DataType], bound: str
) -> None:
    line, expected = _LINES[bound]
    book = _BOOK.with_columns(pl.col("dur").cast(pl.List(width)))
    af = ActuarialFrame(book)
    af.capped = line(af)
    out = af.collect(engine=engine)  # type: ignore[arg-type]
    assert out.schema["capped"] == pl.List(pl.Int64)
    assert out["capped"].to_list() == expected


def test_the_record_names_the_whole_numbers_it_answers() -> None:
    af = ActuarialFrame(_BOOK)
    af.capped = af.dur.clip(upper_bound=af.cap)
    document = json.loads(GraphExporter(af).export(af.collect(), profile="executable"))
    (node,) = [one for one in document["nodes"] if one["column"] == "capped"]
    assert node["dtype"] == "list[i64]"


def test_a_value_past_2_53_is_refused_by_name_rather_than_read_as_a_double() -> None:
    book = pl.DataFrame(
        {
            "dur": pl.Series([[2**53 + 1, 2]], dtype=pl.List(pl.Int64)),
            "floor": pl.Series([2**53], dtype=pl.Int64),
        }
    )
    af = ActuarialFrame(book)
    af.held = af.dur.clip(lower_bound=af.floor)
    with pytest.raises(
        pl.exceptions.InvalidOperationError,
        match=r"Column 'dur' is held between bounds a column gives",
    ):
        af.collect()
