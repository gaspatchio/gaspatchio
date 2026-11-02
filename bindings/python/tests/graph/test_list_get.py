# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Portable positional list selection keeps indexing strict and auditable."""

from __future__ import annotations

import datetime
import json

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import GraphExporter


def test_zero_negative_and_per_policy_positions_select_without_dtype_drift() -> None:
    frame = ActuarialFrame(
        {
            "values": [[10, 20], [30, 40]],
            "position": pl.Series([1, -1], dtype=pl.Int16),
        }
    )
    frame.first = frame.values.list.get(0)
    frame.last = frame.values.list.get(-1)
    frame.selected = frame.values.list.get(frame.position)

    result = frame.collect()
    assert result.select("first", "last", "selected").to_dict(as_series=False) == {
        "first": [10, 30],
        "last": [20, 40],
        "selected": [20, 40],
    }
    assert result.schema["selected"] == pl.Int64


def test_chained_signed_index_uses_each_jagged_rows_own_length() -> None:
    frame = ActuarialFrame(
        {
            "values": pl.Series(
                "values",
                [[10, 20, 30], [40], [50, 60]],
                dtype=pl.List(pl.Int32),
            ),
            "base": pl.Series("base", [-2, 0, -1], dtype=pl.Int16),
            "offset": pl.Series("offset", [-1, 0, 1], dtype=pl.Int8),
        }
    )
    frame.selected = frame.values.list.get(frame.base + frame.offset)

    result = frame.collect()
    assert result["selected"].to_list() == [10, 40, 50]
    # The book's list[Int32] arrives as list[Int64], the record's i64.
    assert result.schema["selected"] == pl.Int64


def test_selection_over_no_policies_preserves_the_inner_dtype() -> None:
    frame = ActuarialFrame(
        pl.DataFrame(schema={"values": pl.List(pl.String), "position": pl.Int64})
    )
    frame.selected = frame.values.list.get(frame.position)

    result = frame.collect()
    assert result.shape == (0, 3)
    assert result.schema["selected"] == pl.String


@pytest.mark.parametrize(
    ("series", "expected_dtype"),
    [
        (pl.Series("values", [[1], [2]], dtype=pl.List(pl.Int32)), pl.Int64),
        (pl.Series("values", [["a"], ["b"]], dtype=pl.List(pl.String)), pl.String),
        (
            pl.Series(
                "values",
                [[datetime.date(2025, 1, 1)], [datetime.date(2025, 2, 1)]],
                dtype=pl.List(pl.Date),
            ),
            pl.Date,
        ),
    ],
)
def test_selection_preserves_the_list_inner_dtype(
    series: pl.Series,
    expected_dtype: pl.DataType,
) -> None:
    frame = ActuarialFrame({"values": series})
    frame.selected = frame.values.list.get(0)
    assert frame.collect().schema["selected"] == expected_dtype


def test_selecting_a_null_element_preserves_source_absence() -> None:
    frame = ActuarialFrame({"values": pl.Series([[10, None]], dtype=pl.List(pl.Int64))})
    frame.selected = frame.values.list.get(1)
    assert frame.collect()["selected"].to_list() == [None]


@pytest.mark.parametrize(
    ("values", "positions"),
    [
        (pl.Series("values", [[1]], dtype=pl.List(pl.Int64)), [1]),
        (pl.Series("values", [[1]], dtype=pl.List(pl.Int64)), [-2]),
        (pl.Series("values", [[]], dtype=pl.List(pl.Int64)), [0]),
        (
            pl.Series("values", [[1]], dtype=pl.List(pl.Int64)),
            pl.Series([None], dtype=pl.Int64),
        ),
        (pl.Series("values", [None], dtype=pl.List(pl.Int64)), [0]),
        (
            pl.Series("values", [None], dtype=pl.List(pl.Int64)),
            pl.Series([None], dtype=pl.Int64),
        ),
    ],
    ids=(
        "positive-oob",
        "negative-oob",
        "empty",
        "null-index",
        "null-list",
        "both-null",
    ),
)
def test_absent_or_out_of_bounds_selection_refuses_the_whole_evaluation(
    values: pl.Series,
    positions: list[int] | pl.Series,
) -> None:
    frame = ActuarialFrame({"values": values, "position": positions})
    frame.selected = frame.values.list.get(frame.position)
    with pytest.raises(pl.exceptions.ComputeError, match="out of bounds"):
        frame.collect()


@pytest.mark.parametrize(
    "positions",
    [
        pl.Series([0.0], dtype=pl.Float64),
        pl.Series([False], dtype=pl.Boolean),
        pl.Series([[0]], dtype=pl.List(pl.Int64)),
    ],
    ids=("float", "boolean", "list-shaped"),
)
def test_only_a_signed_scalar_integer_index_is_accepted(positions: pl.Series) -> None:
    frame = ActuarialFrame({"values": [[1]], "position": positions})
    with pytest.raises(TypeError, match="signed integer scalar"):
        frame.selected = frame.values.list.get(frame.position)


def test_an_unsigned_index_the_model_computes_is_refused() -> None:
    # A book's UInt32 column arrives as Int64 and selects; an unsigned count
    # the model works out itself -- str.len_chars() is UInt32 -- does not.
    frame = ActuarialFrame({"values": [[1, 2]], "text": ["a"]})
    frame.n = frame.text.polars_native().str.len_chars()
    with pytest.raises(TypeError, match="signed integer scalar"):
        frame.selected = frame.values.list.get(frame.n)


def test_an_unsigned_count_less_a_whole_number_is_signed_and_selects() -> None:
    # The whole number written beside it is an Int64, so the difference is
    # signed: "a" has 1 character, 1 - 2 is -1, the last element. In the
    # count's own UInt32 it wrapped to 4294967295.
    frame = ActuarialFrame({"values": [[1, 2]], "text": ["a"]})
    frame.n = frame.text.polars_native().str.len_chars() - 2
    frame.selected = frame.values.list.get(frame.n)
    out = frame.collect()
    assert out["n"].to_list() == [-1]
    assert out["selected"].to_list() == [2]


def test_an_unsigned_book_position_arrives_signed_and_selects() -> None:
    frame = ActuarialFrame(
        {"values": [[10, 20]], "position": pl.Series([1], dtype=pl.UInt32)}
    )
    frame.selected = frame.values.list.get(frame.position)
    assert frame.collect()["selected"].to_list() == [20]


@pytest.mark.parametrize("index", [True, 0.0, 1 << 63, -(1 << 63) - 1])
def test_invalid_literal_indices_are_refused_at_the_method_door(index: object) -> None:
    frame = ActuarialFrame({"values": [[1]]})
    with pytest.raises(TypeError, match=r"list\.get"):
        frame.values.list.get(index)


def test_executable_tree_records_positional_selection_as_two_operands() -> None:
    frame = ActuarialFrame({"values": [[10, 20]], "position": [1]})
    frame.selected = frame.values.list.get(frame.position)
    artifact = json.loads(GraphExporter(frame).export(profile="executable"))
    node = next(node for node in artifact["nodes"] if node["id"] == "selected@1")

    assert node["shape"] == "scalar"
    assert node["dtype"] == "i64"
    assert node["expr"] == {
        "op": "call",
        "name": "list.get",
        "args": [
            {"op": "col", "name": "values"},
            {"op": "col", "name": "position"},
        ],
        "attrs": {},
    }
