# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every integer narrower than i64 is read as Int64 where it enters the frame.

The record names every integer ``i64`` and an engine reading the record
computes in it. A frame that kept a book's ``Int32`` sum assured in four
bytes computed ``sa * 100`` in them and wrapped -- 25,000,000 x 100 came back
as -1,794,967,296 while the record said the calculation was carried in i64
and the JAX engine answered 2,500,000,000. So the book's columns, the columns
a join brings, and the integer axis columns a projection stamps (``month``,
``step``, ``num_proj_months``) all arrive as Int64; an assumption table's keys
were already normalised and stay so. The widening is exact, so the record's
digests do not move -- only the values that had wrapped, and a results file's
stored type.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter

_NARROW = [pl.Int8, pl.Int16, pl.Int32, pl.UInt8, pl.UInt16, pl.UInt32]

# 25,000,000 x 100 by hand: 2,500,000,000, past Int32's 2,147,483,647.
_SA = 25_000_000
_SA_CENTS = 2_500_000_000


def _book(dtype: pl.DataType) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "policy_id": ["A", "B"],
            "sa": pl.Series([_SA, 1000], dtype=dtype),
            "term_m": [4, 3],
        }
    )


@pytest.mark.parametrize("shape", ["DataFrame", "LazyFrame", "dict"])
def test_an_int32_sum_assured_times_100_is_2_5_billion(shape: str) -> None:
    book = _book(pl.Int32())
    handed: Any = {
        "DataFrame": book,
        "LazyFrame": book.lazy(),
        "dict": {name: book[name] for name in book.columns},
    }[shape]
    af = ActuarialFrame(handed)
    af.sa_cents = af.sa * 100
    out = af.collect()
    assert out.schema["sa"] == pl.Int64
    assert out.schema["sa_cents"] == pl.Int64
    assert out["sa_cents"].to_list() == [_SA_CENTS, 100_000]


@pytest.mark.parametrize("dtype", _NARROW, ids=str)
def test_every_narrow_width_arrives_as_int64(dtype: type[pl.DataType]) -> None:
    af = ActuarialFrame(pl.DataFrame({"a": pl.Series([1, 2], dtype=dtype)}))
    assert af.collect().schema["a"] == pl.Int64


def test_an_unsigned_difference_is_signed() -> None:
    # 1 - 2 in UInt32 wraps to 4,294,967,295; read as i64 it is -1.
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "a": pl.Series([1], dtype=pl.UInt32),
                "b": pl.Series([2], dtype=pl.UInt32),
            }
        )
    )
    af.d = af.a - af.b
    assert af.collect()["d"].to_list() == [-1]


def test_an_int16_age_in_months_does_not_wrap() -> None:
    # 100 x 12 x 30 = 36,000, past Int16's 32,767.
    af = ActuarialFrame(pl.DataFrame({"a": pl.Series([100], dtype=pl.Int16)}))
    af.d = af.a * 12 * 30
    assert af.collect()["d"].to_list() == [36_000]


def test_a_list_of_narrow_integers_arrives_as_a_list_of_int64() -> None:
    book = pl.DataFrame(
        {"units": pl.Series([[2_000_000_000, 1]], dtype=pl.List(pl.Int32))}
    )
    af = ActuarialFrame(book)
    af.doubled = af.units * 2
    out = af.collect()
    assert out.schema["units"] == pl.List(pl.Int64)
    assert out["doubled"].to_list() == [[4_000_000_000, 2]]


def test_wide_columns_and_other_types_are_left_as_they_arrived() -> None:
    book = pl.DataFrame(
        {
            "i": [1],
            "f": [1.0],
            "s": ["x"],
            "d": [datetime.date(2025, 1, 1)],
        }
    )
    assert ActuarialFrame(book).collect().schema == book.schema


def test_a_joined_narrow_integer_arrives_as_int64() -> None:
    af = ActuarialFrame(_book(pl.Int64()))
    other = pl.DataFrame(
        {
            "policy_id": ["A", "B"],
            "units": pl.Series([2_000_000_000, 1], dtype=pl.Int32),
        }
    )
    af = af.join(other, on="policy_id")
    af.doubled = af.units * 2
    out = af.collect()
    assert out.schema["units"] == pl.Int64
    assert out["doubled"].to_list() == [4_000_000_000, 2]


def _projected(**projection: Any) -> pl.DataFrame:  # noqa: ANN401
    af = ActuarialFrame(_book(pl.Int32()))
    af = af.projection.set(valuation_date=datetime.date(2025, 1, 1), **projection)
    af.big = af.month * 1_000_000_000
    return af.collect()


@pytest.mark.parametrize(
    "projection",
    [
        {"until": "term_months", "until_value": "term_m", "frequency": "monthly"},
        {"until": "term_months", "until_value": 4, "frequency": "monthly"},
    ],
    ids=["per-policy", "calendar-grid"],
)
def test_the_month_a_projection_stamps_is_int64(projection: dict[str, Any]) -> None:
    out = _projected(**projection)
    assert out.schema["month"] == pl.List(pl.Int64)
    assert out.schema["num_proj_months"] == pl.Int64
    # 3 x 1,000,000,000 by hand, past Int32.
    assert out["big"].to_list()[0][3] == 3_000_000_000


def test_a_fixed_step_axis_stamps_int64() -> None:
    af = ActuarialFrame(_book(pl.Int32()))
    af = af.projection.set(n_periods=3, steps_per_year=12)
    out = af.collect()
    assert out.schema["step"] == pl.List(pl.Int64)
    assert out.schema["month"] == pl.List(pl.Int64)
    assert out.schema["num_proj_months"] == pl.Int64


def _figures(book: pl.DataFrame) -> tuple[str, str, str]:
    af = ActuarialFrame(book)
    af.sa_cents = af.sa * 100
    document = json.loads(GraphExporter(af).export(profile="audit"))  # type: ignore[arg-type]
    return (
        document["graph_fingerprint"],
        document["formulas_fingerprint"],
        document["book"]["digest"],
    )


def test_the_record_is_the_same_for_a_narrow_book_and_a_wide_one() -> None:
    # The record already said i64; widening at the door moves no digest.
    small = _book(pl.Int32()).filter(pl.col("policy_id") == "B")
    assert _figures(small) == _figures(small.cast({"sa": pl.Int64}))


def test_a_narrow_table_key_is_the_table_a_wide_one_is() -> None:
    rates = {"age": [30, 31], "rate": [0.1, 0.2]}
    narrow = Table(
        name="w5s_narrow_key",
        source=pl.DataFrame(rates).cast({"age": pl.Int16}),
        dimensions={"age": "age"},
        value="rate",
    )
    wide = Table(
        name="w5s_wide_key",
        source=pl.DataFrame(rates),
        dimensions={"age": "age"},
        value="rate",
    )
    assert narrow.fingerprint() == wide.fingerprint()
    af = ActuarialFrame(pl.DataFrame({"age": pl.Series([31], dtype=pl.Int8)}))
    af.q = narrow.lookup(age=af.age)
    assert af.collect()["q"].to_list() == [0.2]
