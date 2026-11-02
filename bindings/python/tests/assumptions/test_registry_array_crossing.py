# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A table over a sliced array column is refused in words, never a panic.

Polars 1.42.1's Arrow export double-counts the offset of a fixed-width array
that is a slice of a larger one with a missing value inside the slice
(pola-rs/polars#28583, fixed in 1.43.2). A frame crossing into the extension
with such a column panics, and a ``PanicException`` gets past every
``except Exception``. 1.0.0 stays on 1.42.1, and moves to Polars 2 as a
project of its own. What keeps a table safe is that the registry is handed a
frame freshly sorted by its keys, so no array crosses as a slice. These tests
hold that: an array where a value or a key belongs is refused as the wrong
type, which is a sentence a modeller can act on, and never a crash.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio.assumptions import Table


def _sliced_with_missing() -> pl.DataFrame:
    """Return a slice of a larger frame whose array column has nulls inside it."""
    rates = [None if age % 7 == 0 else [age / 100, age / 50] for age in range(40)]
    frame = pl.DataFrame(
        {
            "age": list(range(40)),
            "band": pl.Series(rates, dtype=pl.Array(pl.Float64, 2)),
            "rate": [age / 1000 for age in range(40)],
        }
    )
    return frame.slice(5, 30)


def test_an_array_value_column_is_refused_by_type_not_by_a_panic() -> None:
    # Refused before it reaches the registry: a lookup answers a number.
    with pytest.raises(ValueError, match=r"answer column 'band' holds Array"):
        Table(
            name="sliced_array_value",
            source=_sliced_with_missing(),
            dimensions={"age": "age"},
            value="band",
        )


def test_an_array_key_column_is_refused_by_type_not_by_a_panic() -> None:
    # Refused by its kind before it reaches the registry: a key is one value
    # per row, so no array crosses, sliced or not.
    with pytest.raises(ValueError, match=r"key column 'band' holds Array"):
        Table(
            name="sliced_array_key",
            source=_sliced_with_missing(),
            dimensions={"band": "band"},
            value="rate",
        )


@pytest.mark.parametrize(
    "keys",
    [
        pl.Series([[1, 2], [3]], dtype=pl.List(pl.Int64)),
        pl.Series([{"a": 1}, {"a": 2}]),
        pl.Series([[1.0, 2.0], [3.0, 4.0]], dtype=pl.Array(pl.Float64, 2)),
    ],
)
def test_a_key_column_of_no_scalar_kind_is_refused_by_kind(keys: pl.Series) -> None:
    with pytest.raises(ValueError, match=r"key column 'k' holds .*one value per row"):
        Table(
            name="nested_key",
            source=pl.DataFrame({"k": keys, "rate": [0.1, 0.2]}),
            dimensions={"k": "k"},
            value="rate",
        )
