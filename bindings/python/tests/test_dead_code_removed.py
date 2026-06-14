# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Regression guard for code deleted in the GSP-95 dispatch refactor.

If any of these imports/attributes come back, something has reverted a
piece of the shape-SOT cutover.
"""

from __future__ import annotations

import polars as pl
import pytest


def test_columntypedetector_removed() -> None:
    """ColumnTypeDetector should no longer be importable from dispatch."""
    from gaspatchio_core.column import dispatch

    assert not hasattr(dispatch, "ColumnTypeDetector")


def test_expr_references_list_column_removed() -> None:
    """The regex-based reference helper is gone."""
    from gaspatchio_core.column import dispatch

    assert not hasattr(dispatch, "_expr_references_list_column")


def test_get_list_columns_from_graph_removed() -> None:
    """The computation-graph dtype probe is gone — schema is the only SOT."""
    from gaspatchio_core.column import dispatch

    assert not hasattr(dispatch, "_get_list_columns_from_graph")


def test_list_broadcast_metadata_removed() -> None:
    """ExpressionProxy no longer carries the duck-typed _list_broadcast_metadata."""
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    proxy = ExpressionProxy(pl.lit(1), parent=None)
    assert not hasattr(proxy, "_list_broadcast_metadata")


def test_actuarialframe_expr_to_str_removed() -> None:
    """ActuarialFrame._expr_to_str method is gone."""
    from gaspatchio_core.frame import base

    assert not hasattr(base.ActuarialFrame, "_expr_to_str")


def test_is_boolean_list_attribute_not_set_by_mask_ops() -> None:
    """The mask-producing operators no longer stamp the duck-typed flag."""
    from gaspatchio_core import ActuarialFrame

    af = ActuarialFrame({"x": [1, 2, 3]})
    cond = (af["x"] > 1) & (af["x"] < 3)
    # The new typed channel is `kind`; the duck-typed flag must not be set.
    assert cond.kind == "boolean_mask"
    assert not getattr(cond, "_is_boolean_list", False)


def test_no_direct_underlying_df_writes_outside_property() -> None:
    """Defense in depth: no other code may write to self._ActuarialFrame__df directly.

    All `self._df = ...` mutations route through the property setter, which
    refreshes the cached schema and bumps `_schema_generation`. If a future
    contributor reaches into `_ActuarialFrame__df` directly, the cache will
    silently rot. We bound the number of direct writes to two: the
    name-mangled `self.__df = None` initialization in `__init__`, and the
    one inside the `@_df.setter` body.
    """
    import re
    from pathlib import Path

    base_py = (
        Path(__file__).resolve().parent.parent
        / "gaspatchio_core"
        / "frame"
        / "base.py"
    )
    src = base_py.read_text()

    # Match both the source-level `self.__df = ...` and the post-mangle form.
    pattern = re.compile(r"self\.(?:__df|_ActuarialFrame__df)\s*=")
    matches = list(pattern.finditer(src))

    assert len(matches) <= 2, (
        f"Too many direct __df writes ({len(matches)}). "
        "All mutations must go through the @_df.setter property."
    )
