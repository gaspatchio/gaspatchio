# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for column/shape.py — _max_shape, resolve_shape, _kind_from_dtype."""

from __future__ import annotations

import pytest


class TestMaxShape:
    def test_two_scalars_is_scalar(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("scalar", "scalar") == "scalar"

    def test_scalar_and_list_is_list(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("scalar", "list") == "list"
        assert _max_shape("list", "scalar") == "list"

    def test_two_lists_is_list(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("list", "list") == "list"

    def test_unknown_propagates(self) -> None:
        from gaspatchio_core.column.shape import _max_shape

        assert _max_shape("unknown", "scalar") == "unknown"
        assert _max_shape("scalar", "unknown") == "unknown"
        assert _max_shape("unknown", "list") == "unknown"
        assert _max_shape("list", "unknown") == "unknown"
        assert _max_shape("unknown", "unknown") == "unknown"


class TestResolveShapeBasics:
    def test_scalar_literal_int(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape(42, parent=None) == "scalar"

    def test_scalar_literal_float(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape(3.14, parent=None) == "scalar"

    def test_scalar_literal_str(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape("hello", parent=None) == "unknown"
        # Strings are AMBIGUOUS — could be a column name or a literal. resolve_shape
        # treats them as scalar literals only when called via known-literal contexts;
        # for raw resolve_shape() with a string, return unknown until a parent
        # context disambiguates. Callers that know the string is a column name use
        # _shape_from_schema directly.

    def test_scalar_literal_bool(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        assert resolve_shape(True, parent=None) == "scalar"
        assert resolve_shape(False, parent=None) == "scalar"

    def test_unknown_for_arbitrary_object(self) -> None:
        from gaspatchio_core.column.shape import resolve_shape

        class Foo:
            pass

        assert resolve_shape(Foo(), parent=None) == "unknown"


class TestShapeFromSchema:
    def test_scalar_column(self) -> None:
        import polars as pl

        from gaspatchio_core.column.shape import _shape_from_schema

        # Mock parent with a cached schema
        class FakeParent:
            _schema = pl.Schema({"age": pl.Int64})

        assert _shape_from_schema(FakeParent(), "age") == "scalar"

    def test_list_column(self) -> None:
        import polars as pl

        from gaspatchio_core.column.shape import _shape_from_schema

        class FakeParent:
            _schema = pl.Schema({"month": pl.List(pl.Int64)})

        assert _shape_from_schema(FakeParent(), "month") == "list"

    def test_missing_column_returns_unknown(self) -> None:
        import polars as pl

        from gaspatchio_core.column.shape import _shape_from_schema

        class FakeParent:
            _schema = pl.Schema({"age": pl.Int64})

        assert _shape_from_schema(FakeParent(), "nonexistent") == "unknown"

    def test_no_parent_returns_unknown(self) -> None:
        from gaspatchio_core.column.shape import _shape_from_schema

        assert _shape_from_schema(None, "any") == "unknown"
