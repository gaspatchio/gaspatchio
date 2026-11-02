# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Positive producer coverage for the bounded executable lookup contract."""

from __future__ import annotations

import json
import math

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.frame.graph import GraphExporter, validate_artifact


def _numeric_table(name: str) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"key": [1.5, 2.0], "rate": [0.15, 0.2]}),
        dimensions={"key": "key"},
        value="rate",
        storage_mode="hash",
    )


@pytest.mark.parametrize("on_missing", ["raise", "nan", 0.25])
def test_present_empty_list_lookup_preserves_empty_axis(
    on_missing: str | float,
) -> None:
    table = _numeric_table(f"portable_empty_{on_missing}")
    frame = ActuarialFrame(
        {"keys": pl.Series("keys", [[], []], dtype=pl.List(pl.Float64))}
    )
    frame.rates = table.lookup(key=frame.keys, on_missing=on_missing)

    result = frame.collect()["rates"]

    assert result.dtype == pl.List(pl.Float64)
    assert result.to_list() == [[], []]


@pytest.mark.parametrize("on_missing", ["raise", "nan", 0.25])
def test_zero_row_scalar_lookup_preserves_float_dtype(
    on_missing: str | float,
) -> None:
    table = _numeric_table(f"portable_zero_rows_{on_missing}")
    frame = ActuarialFrame({"key": pl.Series("key", [], dtype=pl.Float64)})
    frame.rate = table.lookup(key=frame.key, on_missing=on_missing)

    result = frame.collect()["rate"]

    assert result.dtype == pl.Float64
    assert result.len() == 0


def test_hash_lookup_matches_fractional_f64_keys_exactly() -> None:
    adjacent = math.nextafter(1.5, math.inf)
    table = Table(
        name="portable_fractional_exact",
        source=pl.DataFrame({"key": [1.5, adjacent], "rate": [0.15, 0.16]}),
        dimensions={"key": "key"},
        value="rate",
        storage_mode="hash",
        on_missing="nan",
    )
    frame = ActuarialFrame({"key": [1.5, adjacent, math.nextafter(adjacent, math.inf)]})
    frame.rate = table.lookup(key=frame.key)

    result = frame.collect()["rate"].to_list()

    assert result[:2] == pytest.approx([0.15, 0.16])
    assert math.isnan(result[2])


def test_integral_cross_numeric_lookup_is_exact_at_safe_range_boundary() -> None:
    boundary = 2**53
    table = Table(
        name="portable_safe_numeric_boundary",
        source=pl.DataFrame(
            {"key": pl.Series([float(boundary)], dtype=pl.Float64), "rate": [0.25]}
        ),
        dimensions={"key": "key"},
        value="rate",
        storage_mode="hash",
        on_missing="nan",
    )
    frame = ActuarialFrame({"key": pl.Series([boundary, boundary - 1], dtype=pl.Int64)})
    frame.rate = table.lookup(key=frame.key)

    result = frame.collect()["rate"].to_list()

    assert result[0] == pytest.approx(0.25)
    assert math.isnan(result[1])


def test_executable_lookup_binds_processed_key_column_order() -> None:
    table = Table(
        name="portable_processed_order",
        source=pl.DataFrame({"z": ["A", "B"], "rate": [0.11, 0.22], "a": [1.5, 2.0]}),
        dimensions={"a": "a", "z": "z"},
        value="rate",
        storage_mode="hash",
    )
    frame = ActuarialFrame({"z_query": ["A"], "a_query": [1.5]})
    # Written z first: the operands still bind in the canonical key order.
    frame.rate = table.lookup(z=frame.z_query, a=frame.a_query)

    document = GraphExporter(frame).export(profile="executable", include_tables="all")
    report = validate_artifact(document, deep=True)
    artifact = json.loads(document)
    lookup = next(node for node in artifact["nodes"] if node["kind"] == "computed")
    payload = artifact["assumptions"][0]["payload"]

    assert report.ok, report.findings
    # The source listed z, rate, a; the processed table holds its keys in
    # name order and its answer last (spec section 12.3), and the operands
    # follow it.
    assert [column["name"] for column in payload["columns"]] == ["a", "z", "rate"]
    assert payload["dimensions"] == ["a", "z"]
    assert lookup["expr"]["args"] == [
        {"op": "col", "name": "a_query"},
        {"op": "col", "name": "z_query"},
    ]
    assert frame.collect()["rate"].to_list() == pytest.approx([0.11])
