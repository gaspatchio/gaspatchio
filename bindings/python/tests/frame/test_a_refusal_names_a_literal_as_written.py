# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A refusal names a date-and-time literal as the literal it is, not "an expression".

A date and time, a duration and a time of day have no literal of the tree's
own, so one written into a formula is held as the engine's literal of it.
The refusal of a zoned date and time compared with a zone-naive one named
such a literal "an expression" -- ``against an expression, a date and time
with no time zone`` -- though the author wrote one value on the line. It now
names it by that value, as a number or a date written there is named. A
column, and a computed operand, are named as before.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from gaspatchio import ActuarialFrame

_N = 1_735_689_600_000_000


def _frame() -> ActuarialFrame:
    book = pl.DataFrame(
        {"naive": pl.Series([_N, _N], dtype=pl.Int64).cast(pl.Datetime("us"))}
    ).with_columns(pl.col("naive").dt.replace_time_zone("UTC").alias("zoned"))
    return ActuarialFrame(book)


def test_a_naive_literal_beside_a_zoned_column_is_named_by_its_value() -> None:
    af = _frame()
    with pytest.raises(TypeError) as caught:
        af.r = af.zoned > dt.datetime(2025, 1, 1)  # noqa: DTZ001 -- zone-naive on purpose
    text = str(caught.value)
    assert "against datetime.datetime(2025, 1, 1, 0, 0), a date and time" in text
    assert "an expression" not in text


def test_a_zoned_literal_beside_a_naive_column_is_named_by_its_value() -> None:
    af = _frame()
    with pytest.raises(TypeError) as caught:
        af.r = af.naive > dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
    text = str(caught.value)
    assert "A comparison sets datetime.datetime(2025, 1, 1, 0, 0, tzinfo=" in text
    assert "against the column 'naive'" in text


def test_a_literal_written_through_polars_is_named_by_its_value_too() -> None:
    af = _frame()
    with pytest.raises(TypeError, match=r"against datetime\.datetime\(2025, 1, 1"):
        af.r = af.zoned > pl.lit(dt.datetime(2025, 1, 1))  # noqa: DTZ001 -- zone-naive on purpose


def test_two_columns_are_named_as_before() -> None:
    af = _frame()
    with pytest.raises(
        TypeError, match=r"sets the column 'zoned', .* against the column 'naive'"
    ):
        af.r = af.zoned > af.naive
