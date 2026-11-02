# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A float narrower than f64 is read as Float64 where it enters the frame.

The record names every float ``f64``, and the reader and the JAX engine
compute in a double. A frame that kept a book's ``Float32`` mortality rates
in four bytes carried the calculation in them: ``qx.list.sum()`` over
``[0.001, 0.0015, 0.002]`` answered 0.0044999998062849045, which is the
single-precision sum, while the record said ``f64`` and the reader answered
0.00450000015553087. Nothing refused and nothing said so. The book's columns
and the columns a join brings now arrive as Float64, as a narrow integer
arrives as Int64. The widening is exact -- every single-precision value is a
double -- so the book's digest and every fingerprint stay where they were;
only the numbers carried in four bytes, and a results file's stored type,
move.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter

# The stored single-precision rates read exactly as doubles, by hand:
# 0.001f is 0.0010000000474974513, 0.0015f is 0.001500000013038516 and
# 0.002f is 0.0020000000949949026.
_Q = [0.001, 0.0015, 0.002]
# Their sum in a double: 0.00450000015553087 (single precision gave
# 0.0044999998062849045).
_Q_SUM = 0.00450000015553087
# Survival at the start of each period: 1, 1 - q0, (1 - q0)(1 - q1).
_SURVIVAL = [1.0, 0.9989999999525025, 0.9975014999395483]
# exp of the stored 0.001f, 0.0010000000474974513: single precision gave
# 1.0010005235671997.
_EXP = 1.0010005002142532


def _book(width: pl.DataType) -> pl.DataFrame:
    return pl.DataFrame(
        [
            pl.Series("pid", [1], dtype=pl.Int64),
            pl.Series("qx", [_Q], dtype=pl.List(width)),
            pl.Series("q0", [_Q[0]], dtype=width),
        ]
    )


def _run(book: pl.DataFrame | pl.LazyFrame, engine: str) -> pl.DataFrame:
    af = ActuarialFrame(book)
    af.total = af.qx.list.sum()
    af.tpx = af.qx.projection.cumulative_survival()
    af.grown = af.q0.exp()
    return af.collect(engine=engine)  # type: ignore[arg-type]


@pytest.mark.parametrize("engine", ["in-memory", "streaming"])
@pytest.mark.parametrize("door", ["DataFrame", "LazyFrame"])
def test_a_float32_rate_is_summed_and_compounded_in_a_double(
    engine: str, door: str
) -> None:
    book = _book(pl.Float32())
    handed: Any = book if door == "DataFrame" else book.lazy()

    out = _run(handed, engine)

    assert out.schema["qx"] == pl.List(pl.Float64)
    assert out.schema["q0"] == pl.Float64
    assert out["total"].dtype == pl.Float64
    assert out["total"].to_list() == [_Q_SUM]
    assert out["tpx"].to_list() == [_SURVIVAL]
    assert out["grown"].to_list() == [_EXP]


def test_a_float32_book_answers_what_the_same_book_in_doubles_answers() -> None:
    narrow = _book(pl.Float32())
    wide = narrow.with_columns(
        pl.col("qx").cast(pl.List(pl.Float64)), pl.col("q0").cast(pl.Float64)
    )
    assert _run(narrow, "in-memory").equals(_run(wide, "in-memory"))


def test_a_float16_column_is_read_as_a_double_too() -> None:
    af = ActuarialFrame(pl.DataFrame({"h": pl.Series([0.5, 0.25], dtype=pl.Float16)}))
    af.third = af.h / 3.0
    out = af.collect()
    assert out.schema["h"] == pl.Float64
    assert out["third"].to_list() == [0.5 / 3.0, 0.25 / 3.0]


def test_a_joined_float32_column_is_read_as_a_double() -> None:
    af = ActuarialFrame(pl.DataFrame({"pid": [1, 2]}))
    other = pl.DataFrame({"pid": [1, 2], "w": pl.Series([0.5, 0.25], dtype=pl.Float32)})
    af = af.join(other, on="pid")
    af.z = af.w / 3.0
    out = af.collect()
    assert out.schema["w"] == pl.Float64
    # 0.5 / 3 in a double; single precision gave 0.1666666716337204.
    assert out["z"].to_list() == [0.16666666666666666, 0.08333333333333333]


def test_the_record_of_a_float32_book_is_the_record_of_the_same_book_in_doubles() -> (
    None
):
    """The widening is exact, so no digest, fingerprint or sample tells them apart."""

    def _record(book: pl.DataFrame) -> dict[str, Any]:
        af = ActuarialFrame(book)
        af.total = af.qx.list.sum()
        return json.loads(
            GraphExporter(af).export(
                af.collect(), profile="executable", include_source=False
            )
        )

    narrow = _book(pl.Float32())
    wide = narrow.with_columns(
        pl.col("qx").cast(pl.List(pl.Float64)), pl.col("q0").cast(pl.Float64)
    )
    one, other = _record(narrow), _record(wide)
    assert one["book"] == other["book"]
    keep = ("id", "dtype", "fingerprint", "value_sample")
    assert [{k: n.get(k) for k in keep} for n in one["nodes"]] == [
        {k: n.get(k) for k in keep} for n in other["nodes"]
    ]
    total = next(n for n in one["nodes"] if n["column"] == "total")
    assert total["value_sample"] == _Q_SUM
