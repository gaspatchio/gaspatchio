# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for _kind_from_dtype — dtype-driven kind classification."""

from __future__ import annotations

import polars as pl
import pytest


class TestKindFromDtype:
    def test_boolean_scalar_is_boolean_mask(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        class FakeParent:
            _df = pl.LazyFrame({"x": [1, 2, 3]})

        # is_null produces Boolean
        assert _kind_from_dtype(pl.col("x").is_null(), FakeParent()) == "boolean_mask"

    def test_boolean_list_is_boolean_mask(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        class FakeParent:
            _df = pl.LazyFrame({"m": [[1, 2, 3]]})

        # list.eval(is_null) produces List<Boolean>
        expr = pl.col("m").list.eval(pl.element().is_null())
        assert _kind_from_dtype(expr, FakeParent()) == "boolean_mask"

    def test_numeric_is_value(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        class FakeParent:
            _df = pl.LazyFrame({"x": [1.0, 2.0, 3.0]})

        assert _kind_from_dtype(pl.col("x") + 1.0, FakeParent()) == "value"

    def test_no_parent_returns_value(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        # Without a parent, can't probe dtype; fall back to value
        assert _kind_from_dtype(pl.col("x"), None) == "value"

    def test_probe_failure_returns_value(self) -> None:
        from gaspatchio_core.column.shape import _kind_from_dtype

        # Reference a column that doesn't exist
        class FakeParent:
            _df = pl.LazyFrame({"x": [1, 2, 3]})

        # collect_schema on pl.col("does_not_exist") raises
        result = _kind_from_dtype(pl.col("does_not_exist"), FakeParent())
        # Either probe fails -> "value", or schema is permissive -> "value"
        assert result == "value"
