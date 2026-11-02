# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Exact native lookup identity outside the portable artifact numeric envelope."""

from __future__ import annotations

import json
import math
from typing import Literal

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio._dtypes import UnmappedDtypeError
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter, validate_artifact


@pytest.mark.parametrize("storage_mode", ["auto", "hash", "array"])
@pytest.mark.parametrize("list_keys", [False, True])
@pytest.mark.parametrize(
    ("keys", "dtype"),
    [
        ([2**53, 2**53 + 1], pl.Int64),
        ([-(2**63), 2**63 - 1], pl.Int64),
        (["9007199254740992", "9007199254740993"], pl.String),
    ],
)
def test_distinct_large_keys_survive_table_processing_and_lookup(
    *,
    storage_mode: Literal["auto", "hash", "array"],
    list_keys: bool,
    keys: list[int] | list[str],
    dtype: type[pl.DataType],
) -> None:
    table = Table(
        name="distinct_large_keys",
        source=pl.DataFrame({"key": pl.Series(keys, dtype=dtype), "rate": [0.1, 0.2]}),
        dimensions={"key": "key"},
        value="rate",
        storage_mode=storage_mode,
    )
    points = pl.Series(
        "key",
        [keys] if list_keys else keys,
        dtype=pl.List(dtype) if list_keys else dtype,
    )
    frame = ActuarialFrame(pl.DataFrame(points))
    frame.rate = table.lookup(key=frame.key)

    assert frame.collect()["rate"].to_list() == (
        [[0.1, 0.2]] if list_keys else [0.1, 0.2]
    )


def test_adjacent_large_signed_keys_remain_i64_in_the_artifact() -> None:
    """The portable payload preserves adjacent integers above f64 precision."""
    keys = [2**53, 2**53 + 1]
    table = Table(
        name="large_int64_artifact_identity",
        source=pl.DataFrame(
            {"key": pl.Series(keys, dtype=pl.Int64), "rate": [0.1, 0.2]}
        ),
        dimensions={"key": "key"},
        value="rate",
        storage_mode="hash",
    )
    frame = ActuarialFrame({"key": keys})
    frame.rate = table.lookup(key=frame.key)

    document = GraphExporter(frame).export()
    artifact = json.loads(document)
    entry = next(
        item
        for item in artifact["assumptions"]
        if item["name"] == "large_int64_artifact_identity"
    )
    payload = entry["payload"]

    assert payload["columns"] == [
        {"name": "key", "dtype": "i64"},
        {"name": "rate", "dtype": "f64"},
    ]
    assert [row[0] for row in payload["rows"]] == keys
    assert all(type(row[0]) is int for row in payload["rows"])
    assert validate_artifact(artifact, deep=True).ok


@pytest.mark.parametrize("storage_mode", ["auto", "hash", "array"])
@pytest.mark.parametrize(
    "case",
    [
        (2**63 - 1, pl.Int64, float(2**63), pl.Float64, False),
        (1, pl.Int64, float.fromhex("0x0.0000000000001p-1022"), pl.Float64, False),
        (2**53 + 1, pl.Int64, float(2**53), pl.Float64, False),
        (-(2**63), pl.Int64, float(-(2**63)), pl.Float64, True),
    ],
)
def test_mixed_numeric_keys_match_only_the_same_value(
    storage_mode: Literal["auto", "hash", "array"],
    case: tuple[int, type[pl.DataType], float, type[pl.DataType], bool],
) -> None:
    stored, stored_dtype, query, query_dtype, matches = case
    table = Table(
        name="mixed_numeric_value",
        source=pl.DataFrame(
            {"key": pl.Series([stored], dtype=stored_dtype), "rate": [0.25]}
        ),
        dimensions={"key": "key"},
        value="rate",
        storage_mode=storage_mode,
    )
    frame = ActuarialFrame(
        pl.DataFrame({"key": pl.Series([[query]], dtype=pl.List(query_dtype))})
    )
    frame.rate = table.lookup(key=frame.key, on_missing="nan")

    result = frame.collect()["rate"].to_list()[0][0]
    assert result == 0.25 if matches else math.isnan(result)


@pytest.mark.parametrize("storage_mode", ["auto", "hash", "array"])
@pytest.mark.parametrize("query_dtype", [pl.UInt64, pl.Int64, pl.List(pl.UInt64)])
def test_unsigned_table_keys_within_the_signed_range_keep_their_digits(
    storage_mode: Literal["auto", "hash", "array"],
    query_dtype: pl.DataType | type[pl.DataType],
) -> None:
    """An unsigned key is only a problem where its values have no signed name.

    These two are above 2**53, where a float would start folding neighbours
    together, and both fit a signed 64-bit integer exactly. The table takes
    the name they fit, and the lookup answers on it however the query column
    happens to be stored -- per policy, and per period, which is the shape a
    projection actually looks a key up in.
    """
    keys = [2**53 + 1, 2**63 - 1]
    name = f"unsigned_within_signed_range_{storage_mode}"  # one name per mode
    table = Table(
        name=name,
        source=pl.DataFrame(
            {"key": pl.Series(keys, dtype=pl.UInt64), "rate": [0.1, 0.2]}
        ),
        dimensions={"key": "key"},
        value="rate",
        storage_mode=storage_mode,
    )
    per_period = isinstance(query_dtype, pl.List)
    queried = [keys] if per_period else keys
    frame = ActuarialFrame(pl.DataFrame({"key": pl.Series(queried, dtype=query_dtype)}))
    frame.rate = table.lookup(key=frame.key)

    answered = frame.collect()["rate"].to_list()
    assert answered == ([[0.1, 0.2]] if per_period else [0.1, 0.2])


def test_an_unsigned_table_key_is_published_as_the_integer_it_became() -> None:
    """The payload declares the type it wrote, with every digit still in it.

    The query column here is signed because the refusal on a model's own
    ``UInt64`` column is a separate rule on a separate surface: this one is
    about what the table did with its keys.
    """
    keys = [2**53 + 1, 2**63 - 1]
    table = Table(
        name="unsigned_within_signed_range_artifact",
        source=pl.DataFrame(
            {"key": pl.Series(keys, dtype=pl.UInt64), "rate": [0.1, 0.2]}
        ),
        dimensions={"key": "key"},
        value="rate",
        storage_mode="hash",
    )
    frame = ActuarialFrame(pl.DataFrame({"key": pl.Series(keys, dtype=pl.Int64)}))
    frame.rate = table.lookup(key=frame.key)

    artifact = json.loads(GraphExporter(frame).export())
    payload = next(
        item["payload"]
        for item in artifact["assumptions"]
        if item["name"] == "unsigned_within_signed_range_artifact"
    )

    assert payload["columns"][0] == {"name": "key", "dtype": "i64"}
    assert [row[0] for row in payload["rows"]] == keys
    assert all(type(row[0]) is int for row in payload["rows"])
    assert validate_artifact(artifact, deep=True).ok


@pytest.mark.parametrize("storage_mode", ["auto", "hash", "array"])
def test_unsigned_table_keys_above_the_signed_range_refuse_by_value(
    storage_mode: Literal["auto", "hash", "array"],
) -> None:
    """Keeping wide keys exact must not silently widen the signed wire type.

    Above the signed maximum there is no exact numeric name, so the refusal
    stands -- but it stands on the value that has none rather than on the
    dtype, and it says which key the author has to go and look at.
    """
    with pytest.raises(UnmappedDtypeError, match="18446744073709551615") as caught:
        Table(
            name="unsigned_identity_boundary",
            source=pl.DataFrame(
                {
                    "key": pl.Series([2**63, 2**64 - 1], dtype=pl.UInt64),
                    "rate": [0.1, 0.2],
                }
            ),
            dimensions={"key": "key"},
            value="rate",
            storage_mode=storage_mode,
        )

    message = str(caught.value)
    assert message.splitlines()[0] == (
        "Assumption table key column 'key' holds 18446744073709551615, which "
        "is larger than the signed 64-bit integer a lookup key travels as."
    )
    assert ".cast(pl.String)" in message


def test_the_remedy_the_unsigned_refusal_names_carries_the_same_keys() -> None:
    """Text is offered as the way to keep every digit, so text has to work."""
    keys = ["18446744073709551614", "18446744073709551615"]
    table = Table(
        name="unsigned_beyond_signed_range_as_text",
        source=pl.DataFrame({"key": keys, "rate": [0.1, 0.2]}),
        dimensions={"key": "key"},
        value="rate",
    )
    frame = ActuarialFrame(pl.DataFrame({"key": keys}))
    frame.rate = table.lookup(key=frame.key)

    assert frame.collect()["rate"].to_list() == [0.1, 0.2]


@pytest.mark.parametrize("storage_mode", ["auto", "hash", "array"])
@pytest.mark.parametrize("list_keys", [False, True])
def test_unsigned_polars_queries_match_only_exact_representable_float_keys(
    *,
    storage_mode: Literal["auto", "hash", "array"],
    list_keys: bool,
) -> None:
    """The native engine supports UInt64 queries without changing graph dtypes."""
    table = Table(
        name="unsigned_native_query",
        source=pl.DataFrame({"key": [float(2**63)], "rate": [0.25]}),
        dimensions={"key": "key"},
        value="rate",
        storage_mode=storage_mode,
    )
    keys = [2**63, 2**64 - 1]
    points = pl.DataFrame(
        {
            "key": pl.Series(
                [keys] if list_keys else keys,
                dtype=pl.List(pl.UInt64) if list_keys else pl.UInt64,
            )
        }
    )
    result = (
        points.select(table.lookup(key=pl.col("key"), on_missing="nan"))
        .to_series()
        .to_list()
    )
    values = result[0] if list_keys else result
    assert values[0] == 0.25
    assert math.isnan(values[1])
