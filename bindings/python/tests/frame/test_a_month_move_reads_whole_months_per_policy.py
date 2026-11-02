# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.eomonth`` reads its months as ``excel.edate`` does; both are per policy.

``excel.edate`` moves a date a signed whole number of months (11.1.33): a whole
double is that number, a fraction is refused by value and text or a flag by
kind. ``excel.eomonth`` read its months as ``edate`` once did -- 1.5 moved one
month, ``"2"`` moved two, ``"1.5"`` answered a silent null, ``True`` moved one
-- where the JAX engine refused a double outright. It now takes edate's rule on
Polars, the JAX engine and the reader.

Section 11.1.33 states both for one date and one count per policy. A date or a
count held per period failed when the frame ran, in Polars' words (``cannot
cast List type``); it is refused by name where the line is written.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import polars as pl
import pytest

import gaspatchio
from gaspatchio import ActuarialFrame

_CONFORMANCE = Path(gaspatchio.__file__).resolve().parents[3] / (
    "spec/graph-artifact/conformance"
)
sys.path.insert(0, str(_CONFORMANCE))
try:
    from reader.shared import Column, DomainRefusal
    from reference import Reader
finally:
    sys.path.remove(str(_CONFORMANCE))

START = dt.date(2025, 1, 31)
ENGINES = ["in-memory", "streaming"]


def _moved(name: str, months: object, engine: str = "in-memory") -> list[object]:
    af = ActuarialFrame(pl.DataFrame({"start": [START] * 3, "months": months}))
    af.moved = getattr(af.start.excel, name)(af.months)
    return af.collect(engine=engine)["moved"].to_list()


@pytest.mark.parametrize("engine", ENGINES)
def test_eomonth_of_a_whole_double_is_that_number_of_months(engine: str) -> None:
    assert _moved("eomonth", [1.0, -2.0, None], engine) == [
        dt.date(2025, 2, 28),
        dt.date(2024, 11, 30),
        None,
    ]


def test_eomonth_of_a_whole_decimal_is_that_number_of_months() -> None:
    months = pl.Series([1, 2, 3], dtype=pl.Decimal(10, 2))
    assert _moved("eomonth", months) == [
        dt.date(2025, 2, 28),
        dt.date(2025, 3, 31),
        dt.date(2025, 4, 30),
    ]


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize(
    "months",
    [[1.5, 1.0, 1.0], pl.Series(["1.5", "2", "3"], dtype=pl.Decimal(10, 2))],
    ids=["double", "decimal"],
)
def test_eomonth_of_a_count_that_is_not_whole_is_refused_by_value(
    months: object, engine: str
) -> None:
    with pytest.raises(pl.exceptions.InvalidOperationError, match="not one"):
        _moved("eomonth", months, engine)


@pytest.mark.parametrize(
    ("months", "said"),
    [(["2", "1", "1"], "text"), ([True, False, True], "a flag")],
    ids=["text", "flag"],
)
def test_eomonth_refuses_text_and_a_flag_by_kind(months: object, said: str) -> None:
    with pytest.raises(TypeError, match=rf"eomonth.*whole number of months.*is {said}"):
        _moved("eomonth", months)


@pytest.mark.parametrize("name", ["edate", "eomonth"])
@pytest.mark.parametrize(
    ("start", "months", "held"),
    [
        ([START] * 2, [[1, 2], [3, 4]], "months"),
        ([START] * 2, [[1.0, 2.0], [3.0, 4.0]], "months"),
        ([[START, START]] * 2, [1, 2], "start"),
    ],
    ids=["whole-months", "double-months", "dates"],
)
def test_a_date_or_months_held_per_period_is_refused_where_written(
    name: str, start: object, months: object, held: str
) -> None:
    af = ActuarialFrame(pl.DataFrame({"start": start, "months": months}))
    with pytest.raises(
        ValueError, match=rf"excel\.{name}\(\).*'{held}' holds one value per period"
    ):
        af.moved = getattr(af.start.excel, name)(af.months)


def _read(months: Column) -> list[object]:
    tree = {
        "op": "call",
        "name": "excel.eomonth",
        "args": [{"op": "col", "name": "start"}, {"op": "col", "name": "months"}],
        "attrs": {},
    }
    book = {"start": Column("date", ["2025-01-31"] * 3), "months": months}
    return Reader(book, [], {}).evaluate(tree).values


def test_the_reader_reads_eomonth_months_as_edate_s() -> None:
    assert _read(Column("f64", [1.0, -2.0, None])) == [
        "2025-02-28",
        "2024-11-30",
        None,
    ]
    with pytest.raises(DomainRefusal) as fraction:
        _read(Column("f64", [1.0, 1.5, 1.0]))
    assert str(fraction.value) == "checked-integer-conversion"
    with pytest.raises(DomainRefusal) as flag:
        _read(Column("bool", [True, False, True]))
    assert str(flag.value) == "calendar-months-kind"


@pytest.mark.parametrize("name", ["edate", "eomonth"])
def test_the_raw_kernel_says_what_it_does_and_what_the_operation_does(
    name: str,
) -> None:
    # The kernel's docstring said "Non-integer values are truncated", which
    # is the raw cast and not the operation. It now states both, and the
    # kernel behaviour it states holds.
    from gaspatchio.frame.lowering._excel.edate import edate
    from gaspatchio.frame.lowering._excel.eomonth import eomonth

    kernel = {"edate": edate, "eomonth": eomonth}[name]
    doc = " ".join((kernel.__doc__ or "").split())
    assert "Non-integer values are truncated" not in doc
    assert "or a list column" not in doc
    assert "truncates a fraction toward zero (1.5 moves one month)" in doc
    assert f"``af.<date>.excel.{name}(...)`` never hands it such a value" in doc

    start = dt.date(2025, 1, 15)

    def moved(months: list[object]) -> list[object]:
        frame = pl.DataFrame({"d": [start] * len(months), "m": months})
        return frame.select(kernel(pl.col("d"), pl.col("m"))).to_series().to_list()

    one, two = (dt.date(2025, 2, 15), dt.date(2025, 3, 15))
    if name == "eomonth":
        one, two = (dt.date(2025, 2, 28), dt.date(2025, 3, 31))
    assert moved([1.5]) == [one]
    assert moved(["2", "1.5"]) == [two, None]
    assert moved([True]) == [one]
