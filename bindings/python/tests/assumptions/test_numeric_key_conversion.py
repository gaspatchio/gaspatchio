# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Large table keys retain their identity through Python preprocessing."""

import polars as pl
import pytest

from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.assumptions import Table
from gaspatchio.assumptions._utils import _normalise_key_dtypes
from gaspatchio.frame.lowering.artefacts import register_table

_ON_THE_BOUNDARY = 2**53


def _table_of(name: str, keys: pl.Series) -> Table:
    """One table shape, so only the type the keys arrived in differs."""
    return Table(
        name=name,
        source=pl.DataFrame({"key": keys, "rate": [0.25]}),
        dimensions={"key": "key"},
        value="rate",
        storage_mode="hash",
    )


@pytest.mark.parametrize(
    ("dtype", "keys"),
    [
        (pl.Int8, [-(2**7), 2**7 - 1]),
        (pl.Int16, [-(2**15), 2**15 - 1]),
        (pl.Int32, [-(2**31), 2**31 - 1]),
        (pl.UInt8, [0, 2**8 - 1]),
        (pl.UInt16, [0, 2**16 - 1]),
        (pl.UInt32, [0, 2**32 - 1]),
    ],
)
def test_narrow_integer_endpoints_convert_without_overflowing_the_guard(
    dtype: type[pl.DataType], keys: list[int]
) -> None:
    source = pl.DataFrame({"key": pl.Series(keys, dtype=dtype)})

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.Float64
    assert converted["key"].to_list() == [float(key) for key in keys]


def test_adjacent_large_signed_integer_keys_remain_distinct() -> None:
    source = pl.DataFrame(
        {"key": pl.Series([2**53, 2**53 + 1], dtype=pl.Int64), "rate": [0.1, 0.2]}
    )

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.Int64
    assert converted["key"].to_list() == [2**53, 2**53 + 1]


def test_wide_unsigned_integer_keys_take_the_signed_name_they_fit() -> None:
    """Above 2**53, so not f64; inside the signed range, so i64."""
    source = pl.DataFrame(
        {
            "key": pl.Series([2**53 + 1, 2**63 - 1], dtype=pl.UInt64),
            "rate": [0.1, 0.2],
        }
    )

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.Int64
    assert converted["key"].to_list() == [2**53 + 1, 2**63 - 1]


def test_full_width_unsigned_integer_keys_refuse_naming_the_value() -> None:
    """Past the signed maximum no exact name is left, and the refusal says which."""
    source = pl.DataFrame(
        {"key": pl.Series([2**63, 2**64 - 1], dtype=pl.UInt64), "rate": [0.1, 0.2]}
    )

    with pytest.raises(UnmappedDtypeError, match="18446744073709551615"):
        _normalise_key_dtypes(source, ["key"])


def test_inclusive_exact_integer_endpoints_still_convert() -> None:
    source = pl.DataFrame(
        {
            "key": pl.Series([-(2**53), 0, 2**53], dtype=pl.Int64),
            "rate": [0.1, 0.2, 0.3],
        }
    )

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.Float64
    assert converted["key"].to_list() == [float(-(2**53)), 0.0, float(2**53)]


def test_text_on_the_boundary_converts_like_the_integer_it_spells() -> None:
    """2**53 is inside the closed interval whichever type spells it.

    An ``Int64`` column of this value converts, and the interval the format
    publishes carries no source-type qualifier. A file writer choosing text
    for the same number does not move the number.
    """
    source = pl.DataFrame({"key": ["9007199254740992"], "rate": [0.25]})

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.Float64
    assert converted["key"].to_list() == [float(_ON_THE_BOUNDARY)]


def test_text_on_the_boundary_stamps_as_its_integer_source_does() -> None:
    """One set of values publishes one content digest, whichever file wrote it.

    ``table_fingerprint`` is the content hash of the processed table, and
    the content grammar names each column by the type it carries. The text
    source used to stop at the boundary and stamp under ``str`` where the
    integer source of the same key stamped under ``f64``; both now stamp
    the same digest.
    """
    from_int64 = _table_of(
        "boundary_key_from_int64",
        pl.Series([_ON_THE_BOUNDARY], dtype=pl.Int64),
    )
    from_text = _table_of(
        "boundary_key_from_text",
        pl.Series([str(_ON_THE_BOUNDARY)], dtype=pl.String),
    )

    assert from_text.to_dataframe()["key"].dtype == pl.Float64
    assert register_table(from_text) == register_table(from_int64)


@pytest.mark.parametrize(
    "keys",
    [
        ["9007199254740993"],
        ["9007199254740992", "9007199254740993"],
    ],
)
def test_text_past_the_boundary_keeps_every_digit(keys: list[str]) -> None:
    """One past 2**53 a double stops separating neighbours, so the text stays.

    The mixed column is the same refusal read from the other end: the
    boundary value alone would convert, and it does not convert here,
    because the key beside it has no exact double of its own.
    """
    source = pl.DataFrame({"key": keys, "rate": [0.1] * len(keys)})

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.String
    assert converted["key"].to_list() == keys


def test_large_numeric_text_keeps_its_original_identity() -> None:
    source = pl.DataFrame(
        {"key": ["9007199254740992", "9007199254740993"], "rate": [0.1, 0.2]}
    )

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.String
    assert converted["key"].to_list() == ["9007199254740992", "9007199254740993"]


def test_ordinary_numeric_text_keeps_existing_conversion() -> None:
    source = pl.DataFrame({"key": ["1", "2.5"], "rate": [0.1, 0.2]})

    converted = _normalise_key_dtypes(source, ["key"])

    assert converted["key"].dtype == pl.Float64
    assert converted["key"].to_list() == [1.0, 2.5]
