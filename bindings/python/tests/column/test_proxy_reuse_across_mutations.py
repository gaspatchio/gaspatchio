# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Verify shape/kind cached on a retained proxy re-resolves after frame mutations."""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


class TestProxyReuseAcrossMutations:
    def test_column_proxy_shape_re_resolves_after_setitem(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3]})
        proxy = af["x"]
        assert proxy.shape == "scalar"

        # Mutate frame: replace x with a list column via expression
        af["x"] = pl.concat_list(pl.col("x"))

        # Re-acquire (most natural path) — shape reflects new schema
        proxy_new = af["x"]
        assert proxy_new.shape == "list"

    def test_expression_proxy_shape_invalidates_on_mutation(self) -> None:
        af = ActuarialFrame({"x": [1.0, 2.0, 3.0]})
        expr_proxy = af["x"] * 2.0
        gen0 = af._schema_generation
        # First access — caches shape against gen0
        shape_a = expr_proxy.shape
        assert shape_a == "scalar"

        # Mutate frame
        af["new_col"] = af["x"] + 1.0
        gen1 = af._schema_generation
        assert gen1 == gen0 + 1

        # Access again — cache is now stale (gen0 != gen1), re-resolves
        # The wrapped pl.Expr (col(x) * 2.0) still resolves to scalar
        shape_b = expr_proxy.shape
        assert shape_b == "scalar"
        # Internal cache should now reflect gen1
        assert expr_proxy._shape_cached[0] == gen1  # type: ignore[index]

    def test_kind_invalidates_on_mutation(self) -> None:
        af = ActuarialFrame({"x": [1, 2, 3]})
        is_null_proxy = af["x"].is_null()
        gen0 = af._schema_generation
        kind_a = is_null_proxy.kind
        assert kind_a == "boolean_mask"

        af["y"] = af["x"] + 1
        # Cache invalidates; re-resolution still says boolean_mask
        kind_b = is_null_proxy.kind
        assert kind_b == "boolean_mask"
        assert is_null_proxy._kind_cached[0] == af._schema_generation  # type: ignore[index]
