# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``excel.edate`` moves a date a signed whole number of months (11.1.33).

A months column of doubles that were not whole was truncated, text was
parsed (``"2"`` moved two months, ``"1.5"`` answered a silent null) and
``True`` moved one, where the JAX engine refused every one of them. A whole
double is that number; a fraction is refused by value, text and a flag by
kind.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

START = dt.date(2025, 1, 31)


def _moved(months: object) -> list[object]:
    af = ActuarialFrame(pl.DataFrame({"start": [START] * 3, "months": months}))
    af.moved = af.start.excel.edate(af.months)
    return af.collect()["moved"].to_list()


def test_a_whole_double_is_that_number_of_months() -> None:
    assert _moved([1.0, -2.0, None]) == [
        dt.date(2025, 2, 28),
        dt.date(2024, 11, 30),
        None,
    ]


def test_a_whole_decimal_is_that_number_of_months() -> None:
    months = pl.Series([1, 2, 3], dtype=pl.Decimal(10, 2))
    assert _moved(months) == [
        dt.date(2025, 2, 28),
        dt.date(2025, 3, 31),
        dt.date(2025, 4, 30),
    ]


@pytest.mark.parametrize(
    "months",
    [[1.5, 1.0, 1.0], pl.Series(["1.5", "2", "3"], dtype=pl.Decimal(10, 2))],
    ids=["double", "decimal"],
)
def test_a_count_that_is_not_whole_is_refused_by_value(months: object) -> None:
    with pytest.raises(pl.exceptions.InvalidOperationError, match="not one"):
        _moved(months)


@pytest.mark.parametrize(
    ("months", "said"),
    [(["2", "1", "1"], "text"), ([True, False, True], "a flag")],
    ids=["text", "flag"],
)
def test_text_and_a_flag_are_refused_by_kind(months: object, said: str) -> None:
    with pytest.raises(TypeError, match=rf"whole number of months.*is {said}"):
        _moved(months)
