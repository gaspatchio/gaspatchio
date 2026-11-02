# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A projection horizon is a whole number, read as one or refused.

§11.1.1: ``term_months`` and ``term_years`` take a whole term and
``maximum_age`` a whole attained age. A decimal ``term_years`` column was
truncated to whole years before it was multiplied out -- ``[2.5, 0.75, 1.0]``
years at monthly cadence projected ``[24, 0, 12]`` periods, so the 0.75-year
policy projected nowhere -- a text column was read as numbers, ``True`` was
read as 1, and a decimal literal failed in raw Python words. Now a whole value
of any numeric kind is that number, a value that is not whole is refused by
value, and text and flags are refused by kind.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame


def _boundaries(book: pl.DataFrame, **kwargs: object) -> list[int]:
    af = ActuarialFrame(book).projection.set(
        valuation_date=dt.date(2025, 1, 1), frequency="monthly", **kwargs
    )
    return af.collect()["num_proj_months"].to_list()


def _book(values: list[object], dtype: pl.DataType) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "pid": list(range(len(values))),
            "h": pl.Series(values, dtype=dtype),
            "issue_age": [40] * len(values),
        }
    )


@pytest.mark.parametrize("per_policy", [None, False])
def test_a_decimal_term_is_refused_naming_the_value(
    per_policy: bool | None,  # noqa: FBT001 -- a parametrised layout
) -> None:
    book = _book([2.5, 0.75, 1.0], pl.Float64)
    with pytest.raises(ValueError, match=r"column 'h' holds 2\.5, which is not one"):
        _boundaries(book, until="term_years", until_value="h", per_policy=per_policy)


@pytest.mark.parametrize("until_value", [2.5, Decimal("2.5")])
def test_a_decimal_literal_is_refused_by_value(until_value: object) -> None:
    with pytest.raises(ValueError, match=r"would be cut to 2"):
        _boundaries(_book([1], pl.Int64), until="term_years", until_value=until_value)


@pytest.mark.parametrize(
    ("until", "expr"), [("term_months", pl.col("h")), ("maximum_age", "h")]
)
def test_an_expression_or_an_age_that_is_not_whole_is_refused(
    until: str, expr: object
) -> None:
    with pytest.raises(ValueError, match=r"which is not one"):
        _boundaries(_book([62.5, 61.0], pl.Float64), until=until, until_value=expr)


@pytest.mark.parametrize(
    ("values", "dtype"), [(["2", "1"], pl.String), ([True, False], pl.Boolean)]
)
def test_text_and_flags_are_refused_by_kind(
    values: list[object], dtype: pl.DataType
) -> None:
    with pytest.raises(TypeError, match=r"a horizon is a whole number"):
        _boundaries(_book(values, dtype), until="term_years", until_value="h")


def test_a_flag_literal_is_refused_by_kind() -> None:
    with pytest.raises(TypeError, match=r"a flag"):
        _boundaries(_book([1], pl.Int64), until="term_years", until_value=True)


@pytest.mark.parametrize(
    ("values", "dtype"),
    [([2.0, 1.0], pl.Float64), ([Decimal(2), Decimal(1)], pl.Decimal(10, 0))],
)
def test_a_whole_value_of_any_numeric_kind_is_that_number(
    values: list[object], dtype: pl.DataType
) -> None:
    assert _boundaries(_book(values, dtype), until="term_years", until_value="h") == [
        25,
        13,
    ]
    assert _boundaries(_book([1], pl.Int64), until="term_years", until_value=2.0) == [
        25
    ]


@pytest.mark.parametrize("n_periods", [3.0, Decimal(3)])
def test_a_whole_period_count_of_any_numeric_kind_is_that_number(
    n_periods: object,
) -> None:
    af = ActuarialFrame(pl.DataFrame({"pid": [1]})).projection.set(
        start_date=dt.date(2025, 1, 31), n_periods=n_periods, frequency="annual"
    )
    assert af.collect()["num_proj_months"].to_list() == [4]


@pytest.mark.parametrize(
    ("name", "value", "error"),
    [
        ("n_periods", 2.5, ValueError),
        ("n_periods", True, TypeError),
        ("n_periods", "3", TypeError),
        ("steps_per_year", 2.5, ValueError),
        ("steps_per_year", True, TypeError),
    ],
)
def test_a_count_that_is_not_a_whole_number_is_refused(
    name: str, value: object, error: type[Exception]
) -> None:
    kwargs: dict[str, object] = {"n_periods": 2, name: value}
    if name == "n_periods":
        kwargs |= {"start_date": dt.date(2025, 1, 31), "frequency": "annual"}
    with pytest.raises(error, match=rf"projection.set\({name}="):
        ActuarialFrame(pl.DataFrame({"pid": [1]})).projection.set(**kwargs)
