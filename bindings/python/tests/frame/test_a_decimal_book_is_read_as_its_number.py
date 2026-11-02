# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A fixed-point decimal is read as the number it denotes where it enters the frame.

A book drawn from a database arrives with money as ``Decimal(12, 2)``. Kept
in that type, the most ordinary line of a model answered at the decimal's
own places: ``1000.00 / 12`` was ``83.33`` and ``0.05 / 12`` was ``0.00``,
``1000.00 / 12 * 12`` came back ``999.96``, ``prem * rate`` kept three
places, and ``round_sig_figs`` fell through to the engine's own rounding
(``0.05`` to two figures was ``0.06``). The record has no name for the type,
so such a book had no record at all.

Section 10 names no fixed-point decimal, so the value is read, at every door
a value enters by -- the book, a join's right side, a table's answer column,
a column injected as a Series and a literal written into a formula -- as the
number it denotes: with places, the double nearest it; with none, the whole
number (``i64``, or kept wide and judged on its values past ``i64``, as an
``Int128`` is). Every line then answers as the same line over doubles,
results store ``Float64``, and the book has a record whose digest reads the
double the value entered as.
"""

from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, run_aggregated
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter
from gaspatchio.scenarios import Sum

if TYPE_CHECKING:
    from collections.abc import Callable

_PREMIUMS = ["1000.00", "0.05", "99.99", "1234.56"]
_RATES = ["0.035", "0.001", "0.123", "0.020"]


def _book(*, as_decimal: bool = True) -> pl.DataFrame:
    if as_decimal:
        return pl.DataFrame(
            {
                "pid": [1, 2, 3, 4],
                "prem": pl.Series(
                    [Decimal(p) for p in _PREMIUMS], dtype=pl.Decimal(12, 2)
                ),
                "rate": pl.Series([Decimal(r) for r in _RATES], dtype=pl.Decimal(8, 3)),
                "n": [12, 12, 7, 4],
            }
        )
    return pl.DataFrame(
        {
            "pid": [1, 2, 3, 4],
            "prem": [float(p) for p in _PREMIUMS],
            "rate": [float(r) for r in _RATES],
            "n": [12, 12, 7, 4],
        }
    )


def _model(af: ActuarialFrame) -> ActuarialFrame:
    af.monthly = af.prem / 12
    af.per_n = af.prem / af.n
    af.prem_x_rate = af.prem * af.rate
    af.back = af.prem / 12 * 12
    af.sig2 = af.prem.round_sig_figs(2)
    af.r2 = (af.prem * af.rate).round(2)
    af.cheap = af.prem < 100
    return af


def test_a_monthly_premium_is_the_quotient_not_the_decimal_s_two_places() -> None:
    out = _model(ActuarialFrame(_book())).collect()

    assert out.schema["monthly"] == pl.Float64
    for got, premium in zip(out["monthly"], _PREMIUMS, strict=True):
        exact = Fraction(Decimal(premium)) / 12
        assert abs(Fraction(got) - exact) <= abs(exact) * Fraction(1, 2**52)
    assert out["back"].to_list() == [1000.0, 0.05, 99.99, 1234.56]
    assert out["prem_x_rate"].to_list()[1] == pytest.approx(5e-05, rel=1e-15)


def test_significant_figures_of_a_decimal_are_its_double_s() -> None:
    out = _model(ActuarialFrame(_book())).collect()

    assert out["sig2"].to_list() == [1000.0, 0.05, 100.0, 1200.0]


@pytest.mark.parametrize("lazy", [False, True], ids=["frame", "plan"])
def test_every_line_answers_as_over_the_same_book_in_doubles(*, lazy: bool) -> None:
    decimals = _book().lazy() if lazy else _book()
    doubles = _book(as_decimal=False)

    got = _model(ActuarialFrame(decimals)).collect()
    want = _model(ActuarialFrame(doubles)).collect()

    assert got.schema == want.schema
    assert got.to_dicts() == want.to_dicts()


def test_a_run_of_decimals_is_a_run_of_doubles() -> None:
    book = pl.DataFrame(
        {
            "pid": [1, 2],
            "prem_run": pl.Series(
                [[Decimal("1000.00")] * 2, [Decimal("0.05")] * 2],
                dtype=pl.List(pl.Decimal(12, 2)),
            ),
        }
    )
    af = ActuarialFrame(book)
    af.monthly_run = af.prem_run / 12
    out = af.collect()

    assert out.schema["monthly_run"] == pl.List(pl.Float64)
    assert out["monthly_run"].to_list() == [[1000.0 / 12] * 2, [0.05 / 12] * 2]


def test_a_decimal_of_no_places_is_a_whole_number() -> None:
    book = pl.DataFrame(
        {
            "units": pl.Series([Decimal(7), Decimal(-99)], dtype=pl.Decimal(10, 0)),
            "wide": pl.Series([Decimal(7), Decimal(8)], dtype=pl.Decimal(38, 0)),
        }
    )
    af = ActuarialFrame(book)
    af.twice = af.units * 2 + af.wide

    out = af.collect()
    assert out.schema["units"] == pl.Int64
    assert out.schema["wide"] == pl.Int64
    assert out["twice"].to_list() == [21, -190]


@pytest.mark.parametrize("lazy", [False, True], ids=["frame", "plan"])
def test_a_whole_decimal_past_i64_keeps_its_digits_and_is_refused_in_arithmetic(
    *, lazy: bool
) -> None:
    book = pl.DataFrame(
        {
            "polno": pl.Series(
                [Decimal(123456789012345678901234567890), Decimal(1)],
                dtype=pl.Decimal(38, 0),
            )
        }
    )
    af = ActuarialFrame(book.lazy() if lazy else book)
    af.label = af.polno.to_text()
    assert af.collect()["label"].to_list() == ["123456789012345678901234567890", "1"]

    af = ActuarialFrame(book.lazy() if lazy else book)
    af.x = af.polno * 2
    with pytest.raises(
        pl.exceptions.InvalidOperationError, match=r"(?s)'polno'.*to_text"
    ):
        af.collect()


def _looked_up(book: pl.DataFrame) -> ActuarialFrame:
    table = Table(
        name="premiums",
        source=book.select("pid", "prem"),
        dimensions={"pid": "pid"},
        value="prem",
    )
    af = ActuarialFrame(book.select("pid", "n"))
    af.prem = table.lookup(pid=af.pid)
    return af


def _injected(book: pl.DataFrame) -> ActuarialFrame:
    af = ActuarialFrame(book.select("pid", "n"))
    af.prem = book["prem"]
    return af


_DOORS: dict[str, Callable[[pl.DataFrame], ActuarialFrame]] = {
    "a join's right side": lambda book: ActuarialFrame(book.select("pid", "n")).join(
        book.select("pid", "prem"), on="pid"
    ),
    "a table's answer": _looked_up,
    "an injected Series": _injected,
}


@pytest.mark.parametrize("door", list(_DOORS))
def test_every_door_a_decimal_enters_by_reads_it_as_its_double(door: str) -> None:
    af = _DOORS[door](_book())
    af.monthly = af.prem / 12
    out = af.collect()

    assert out.schema["prem"] == pl.Float64
    assert out["monthly"].to_list() == [float(p) / 12 for p in _PREMIUMS]


def test_a_decimal_written_into_a_formula_is_its_number() -> None:
    af = ActuarialFrame(_book(as_decimal=False))
    af.loaded = af.prem * Decimal("1.05")
    af.months = af.n * Decimal(12)
    out = af.collect()

    assert out["loaded"].to_list() == [float(p) * 1.05 for p in _PREMIUMS]
    assert out.schema["months"] == pl.Int64


def test_a_decimal_book_has_a_record_whose_digest_reads_the_double() -> None:
    over_decimals = _model(ActuarialFrame(_book()))
    over_doubles = _model(ActuarialFrame(_book(as_decimal=False)))

    decimal_document = json.loads(GraphExporter(over_decimals).export())
    double_document = json.loads(GraphExporter(over_doubles).export())

    assert decimal_document["book"]["digest"] == double_document["book"]["digest"]


@pytest.mark.parametrize("batch_size", [1, 4])
def test_a_batched_run_reads_the_decimal_book_as_one(batch_size: int) -> None:
    aggregations = [Sum("monthly").alias("monthly"), Sum("sig2").alias("sig2")]

    got = run_aggregated(
        _model, _book(), aggregations, batch_size=batch_size
    ).aggregations
    want = run_aggregated(
        _model, _book(as_decimal=False), aggregations, batch_size=batch_size
    ).aggregations

    assert got == want
