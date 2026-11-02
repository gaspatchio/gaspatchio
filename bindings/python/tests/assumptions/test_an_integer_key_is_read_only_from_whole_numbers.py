# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``DataDimension(dtype=pl.Int64)`` reads only whole numbers as keys.

The declared integer dtype was a truncating cast: keys 40.9 and 42 became 40
and 42, so a lookup at age 40 answered the 40.9 row's rate where it should
miss, and ``"-1.5"`` became -1. A key that is not whole is now refused, naming
its value and row; a flag under an integer dtype is refused by kind. Whole
numbers held as doubles, decimals or text (text spelling a whole number is read as that number) still read as those numbers.
"""

from __future__ import annotations

from decimal import Decimal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import DataDimension, Table


def _table(name: str, keys: pl.Series) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"age": keys, "q": [0.5, 0.7]}),
        dimensions={"age": DataDimension("age", dtype=pl.Int64)},
        value="q",
    )


@pytest.mark.parametrize(
    ("keys", "held"),
    [
        (pl.Series([40.9, 42.0]), "40.9"),
        (pl.Series(["40.9", "42"]), "'40.9'"),
        (pl.Series(["-1.5", "3"]), "'-1.5'"),
        (
            pl.Series([Decimal("40.5"), Decimal(42)], dtype=pl.Decimal(10, 1)),
            r"Decimal\('40.5'\)",
        ),
    ],
)
def test_a_key_that_is_not_whole_is_refused(keys: pl.Series, held: str) -> None:
    with pytest.raises(ValueError, match=rf"holds {held}.* at source row 0"):
        _table(f"iw_{abs(hash(held))}", keys)


def test_a_flag_under_an_integer_dtype_is_refused_by_kind() -> None:
    with pytest.raises(ValueError, match=r"holds flags"):
        _table("iw_flags", pl.Series([True, False]))


@pytest.mark.parametrize(
    "keys",
    [pl.Series([40.0, 42.0]), pl.Series(["40", "42"]), pl.Series([40, 42])],
)
def test_whole_keys_of_any_kind_answer(keys: pl.Series) -> None:
    table = _table(f"iw_ok_{keys.dtype}", keys)
    af = ActuarialFrame(pl.DataFrame({"a": [40, 42]}))
    af.q = table.lookup(age=af.a)
    assert af.collect()["q"].to_list() == [0.5, 0.7]
