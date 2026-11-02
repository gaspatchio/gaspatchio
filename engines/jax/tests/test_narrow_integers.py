# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A book's narrow integers are read as i64 at this door, as the producer reads them.

The reference producer reads an ``Int8`` through ``UInt32`` book column -- and
a list of one -- as ``Int64`` where it enters the frame, so an ``Int32`` sum
assured of 25,000,000 times 100 is 2,500,000,000 and the record says ``i64``.
This door refused that same book file -- "cast 'sa' to i64 before the run" --
so the two engines did not take one book. It now reads the book as the
producer does, and the result matches the producer's to the integer. A
``UInt64``, ``Int128`` or ``UInt128`` column is one rule with the producer's
door too: read as i64 where every value fits, and refused by the value that
does not, never wrapped.
"""

from __future__ import annotations

import json
from decimal import Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.engines import engine_named
from gaspatchio.engines.protocol import FrameSink
from gaspatchio.engines.report import EngineRefusal
from gaspatchio.frame.graph import GraphExporter

_BOOK = pl.DataFrame(
    {
        "sa": pl.Series([25_000_000, 1_000], dtype=pl.Int32),
        "age": pl.Series([40, 50], dtype=pl.UInt8),
    }
)


def _document(book: pl.DataFrame) -> dict[str, object]:
    af = ActuarialFrame(book)
    af.c = af.sa * 100
    af.d = af.age - 41
    return json.loads(GraphExporter(af).export(profile="executable"))


def test_a_narrow_book_runs_and_answers_the_producer_s_integers() -> None:
    document = _document(_BOOK)

    result = engine_named("jax").run(document, _BOOK, FrameSink())

    assert result.columns["c"].to_list() == [2_500_000_000, 100_000]
    assert result.columns["d"].to_list() == [-1, 9]
    assert result.columns["c"].dtype == pl.Int64
    # One book: the digest the document recorded is the one this run records.
    assert result.manifest.inputs_digest == document["book"]["digest"]


def test_a_list_of_narrow_integers_is_read_as_a_list_of_i64() -> None:
    book = pl.DataFrame(
        {"n": pl.Series([[1, 2, 3], [4, 5, 6]], dtype=pl.List(pl.Int16))}
    )
    af = ActuarialFrame(book)
    af.big = af.n * 1_000_000_000
    document = json.loads(GraphExporter(af).export(profile="executable"))

    result = engine_named("jax").run(document, book, FrameSink())

    assert result.columns["big"].to_list() == [
        [1_000_000_000, 2_000_000_000, 3_000_000_000],
        [4_000_000_000, 5_000_000_000, 6_000_000_000],
    ]


@pytest.mark.parametrize("width", [pl.UInt64, pl.Int128, pl.UInt128], ids=str)
def test_a_wide_column_whose_values_fit_is_read_as_i64(
    width: type[pl.DataType],
) -> None:
    """One rule with the producer's door: every value fits, so the column is an i64.

    It was refused by width ("cast 'sa' to i64 before the run") whatever it
    held; the producer reads it as Int64 where it arrives, and so does this
    door, so the two engines take one book and record one digest.
    """
    document = _document(_BOOK)
    book = _BOOK.with_columns(pl.col("sa").cast(width))

    result = engine_named("jax").run(document, book, FrameSink())

    # Hand values: 25,000,000 * 100 and 1,000 * 100.
    assert result.columns["c"].to_list() == [2_500_000_000, 100_000]
    assert result.columns["c"].dtype == pl.Int64
    assert result.manifest.inputs_digest == document["book"]["digest"]


@pytest.mark.parametrize(
    ("width", "past"),
    [(pl.UInt64, 2**64 - 1), (pl.Int128, -(2**70)), (pl.UInt128, 2**64 - 1)],
    ids=str,
)
def test_a_value_past_i64_is_refused_by_that_value(
    width: type[pl.DataType], past: int
) -> None:
    """The column keeps its width; carried as i64 here, it is refused, not wrapped."""
    document = _document(_BOOK)
    book = _BOOK.with_columns(pl.Series("sa", [past, 1_000], dtype=width))

    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(document, book, FrameSink())

    rendered = refused.value.report.render()
    assert f"'sa' arrives as {width} and holds {past}" in rendered
    assert "outside the signed 64-bit range" in rendered
    assert "refused rather than wrapped" in rendered
    assert "to_text()" in rendered
    assert "narrower type" in rendered
    assert "cast 'sa' to i64 before the run" not in rendered


def test_a_list_of_wide_integers_is_judged_element_by_element() -> None:
    book = pl.DataFrame(
        {"n": pl.Series([[1, 2, 3], [4, 5, 6]], dtype=pl.List(pl.Int64))}
    )
    af = ActuarialFrame(book)
    af.big = af.n * 1_000_000_000
    document = json.loads(GraphExporter(af).export(profile="executable"))

    fits = book.with_columns(pl.col("n").cast(pl.List(pl.UInt64)))
    result = engine_named("jax").run(document, fits, FrameSink())
    assert result.columns["big"].to_list()[1] == [
        4_000_000_000,
        5_000_000_000,
        6_000_000_000,
    ]

    past = pl.DataFrame(
        {"n": pl.Series([[1, 2**63], [4, 5, 6]], dtype=pl.List(pl.UInt64))}
    )
    with pytest.raises(EngineRefusal) as refused:
        engine_named("jax").run(document, past, FrameSink())
    assert "holds 9223372036854775808" in refused.value.report.render()


def test_a_decimal_book_is_read_as_the_numbers_it_denotes() -> None:
    """A fixed-point decimal enters as the producer reads it: a double, or an i64."""
    book = pl.DataFrame(
        {
            "prem": pl.Series(
                [Decimal("1000.00"), Decimal("0.05")], dtype=pl.Decimal(12, 2)
            ),
            "units": pl.Series([Decimal(7), Decimal(9)], dtype=pl.Decimal(10, 0)),
        }
    )
    af = ActuarialFrame(book)
    af.monthly = af.prem / 12
    af.twice = af.units * 2
    produced = af.collect()
    document = json.loads(GraphExporter(af).export(profile="executable"))

    result = engine_named("jax").run(document, book, FrameSink())

    assert result.columns["monthly"].to_list() == produced["monthly"].to_list()
    assert result.columns["monthly"].to_list() == [1000.0 / 12, 0.05 / 12]
    assert result.columns["twice"].to_list() == [14, 18]
    assert result.manifest.inputs_digest == document["book"]["digest"]
