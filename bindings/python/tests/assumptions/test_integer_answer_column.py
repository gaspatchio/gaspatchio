# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""An assumption table whose answers are whole numbers is read as the doubles they are.

A lookup answers ``f64`` (section 11.1.24), and a published table whose answers
are counts, integer percentages or basis points arrives as an integer column.
Building one used to fail inside registration with the kernel's own words --
``invalid series dtype: expected `Float64`, got `i32``` -- and no sentence of
this project's. The answer column is now read as ``f64`` where the double holds
it exactly, so the table is the one its ``3.0``-spelled twin is, under the same
fingerprint; an integer past ``2**53`` and a column that is not a number are
refused by name.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import MeltDimension, Table
from gaspatchio.assumptions._processing import content_fingerprint_of

_WIDTHS = [
    pl.Int8,
    pl.Int16,
    pl.Int32,
    pl.Int64,
    pl.UInt8,
    pl.UInt16,
    pl.UInt32,
    pl.UInt64,
    pl.Float32,
]


def _looked_up(table: Table, ages: list[int]) -> pl.Series:
    af = ActuarialFrame(pl.DataFrame({"age": ages}))
    af.rate = table.lookup(age=af.age)
    return af.collect()["rate"]


@pytest.mark.parametrize("width", _WIDTHS, ids=str)
def test_a_whole_number_answer_is_read_as_its_double(width: type[pl.DataType]) -> None:
    source = pl.DataFrame({"age": [40, 41], "rate": pl.Series([3, 5]).cast(width)})
    table = Table(
        name=f"whole_{width}", source=source, dimensions={"age": "age"}, value="rate"
    )

    answered = _looked_up(table, [41, 40, 41])

    assert answered.dtype == pl.Float64
    assert answered.to_list() == [5.0, 3.0, 5.0]


def test_the_whole_number_table_is_the_table_its_doubles_spell() -> None:
    whole = Table(
        name="whole_basis_points",
        source=pl.DataFrame(
            {"age": [40, 41], "bp": pl.Series([25, 30], dtype=pl.Int32)}
        ),
        dimensions={"age": "age"},
        value="bp",
    )
    doubles = Table(
        name="double_basis_points",
        source=pl.DataFrame({"age": [40, 41], "bp": [25.0, 30.0]}),
        dimensions={"age": "age"},
        value="bp",
    )

    assert whole.fingerprint() == doubles.fingerprint()
    # A reviewer re-reading the integer file reaches the table's own stamp.
    assert (
        content_fingerprint_of(
            pl.DataFrame({"age": [40, 41], "bp": pl.Series([25, 30], dtype=pl.Int32)}),
            {"age": "age"},
            "bp",
        )
        == whole.fingerprint()
    )


def test_a_wide_table_of_whole_numbers_is_read_as_doubles() -> None:
    wide = pl.DataFrame(
        {
            "age": [40, 41],
            "1": pl.Series([10, 20], dtype=pl.Int32),
            "2": pl.Series([11, 21], dtype=pl.Int32),
        }
    )
    table = Table(
        name="wide_whole",
        source=wide,
        dimensions={
            "age": "age",
            "duration": MeltDimension(columns=["1", "2"], name="duration"),
        },
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame({"age": [41, 40], "duration": [2, 1]}))
    af.rate = table.lookup(age=af.age, duration=af.duration)

    assert af.collect()["rate"].to_list() == [21.0, 10.0]


def test_an_extension_of_whole_numbers_is_read_as_doubles() -> None:
    table = Table(
        name="whole_extended",
        source=pl.DataFrame({"age": [40], "rate": [0.5]}),
        dimensions={"age": "age"},
        value="rate",
        storage_mode="hash",
    )
    table.extend(pl.DataFrame({"age": [41], "rate": pl.Series([2], dtype=pl.Int16)}))

    assert _looked_up(table, [40, 41]).to_list() == [0.5, 2.0]


def test_an_integer_the_double_cannot_hold_is_refused_by_its_value() -> None:
    past = 2**53 + 1
    source = pl.DataFrame({"age": [40, 41], "rate": [1, past]})

    with pytest.raises(
        ValueError, match=r"Table 'too_wide': .*holds 9007199254740993"
    ) as raised:
        Table(name="too_wide", source=source, dimensions={"age": "age"}, value="rate")

    assert "2**53" in str(raised.value)
    assert "invalid series dtype" not in str(raised.value)


@pytest.mark.parametrize(
    "answers",
    [
        pl.Series([True, False]),
        pl.Series(["3%", "5%"]),
    ],
    ids=["flag", "text"],
)
def test_an_answer_that_is_not_a_number_is_refused_naming_the_cast(
    answers: pl.Series,
) -> None:
    source = pl.DataFrame({"age": [40, 41], "rate": answers})

    with pytest.raises(
        ValueError, match=r"Table 'not_a_number': the answer column 'rate'"
    ) as raised:
        Table(
            name="not_a_number", source=source, dimensions={"age": "age"}, value="rate"
        )

    message = str(raised.value)
    assert "pl.col('rate').cast(pl.Float64)" in message
    assert "invalid series dtype" not in message
