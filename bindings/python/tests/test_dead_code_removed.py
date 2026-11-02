# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Regression guard for code deleted in the GSP-95 dispatch refactor.

If any of these imports/attributes come back, something has reverted a
piece of the shape-SOT cutover.
"""

from __future__ import annotations

import ast
from pathlib import Path

import polars as pl
import pytest


@pytest.mark.parametrize(
    "removed_name",
    [
        "ColumnTypeDetector",
        "_expr_references_list_column",
        "_get_list_columns_from_graph",
    ],
)
def test_removed_shape_detectors_do_not_return(removed_name: str) -> None:
    """The old shape probes stay absent from the package, wherever it puts them.

    Replacing reflective dispatch with declared operations deleted these along
    with the dispatch they served, and moved the surviving shape machinery out
    of ``column`` into ``frame/lowering``. Scanning ``column`` alone therefore
    passed on a
    detector reintroduced at the address the machinery had actually gone to --
    the reversion this guard exists to refuse. The scan is the package, since
    a detector coming back anywhere in it is the same reversion.
    """
    package = Path(__file__).resolve().parent.parent / "gaspatchio"
    scanned: set[Path] = set()
    for source in package.rglob("*.py"):
        definitions = {
            node.name
            for node in ast.walk(ast.parse(source.read_text(), filename=str(source)))
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert removed_name not in definitions, source
        scanned.add(source)

    # A scan that reaches nothing reports clean. Bind the two directories this
    # machinery has lived in, so a root that stops resolving fails here and
    # names the file it expected rather than passing on an empty walk.
    for anchor in (
        package / "column" / "column_proxy.py",
        package / "frame" / "lowering" / "methods.py",
    ):
        assert anchor in scanned, anchor


def test_list_broadcast_metadata_removed() -> None:
    """ExpressionProxy no longer carries the duck-typed _list_broadcast_metadata."""
    from gaspatchio.column.expression_proxy import ExpressionProxy

    proxy = ExpressionProxy(pl.lit(1), parent=None)
    assert not hasattr(proxy, "_list_broadcast_metadata")


def test_actuarialframe_expr_to_str_removed() -> None:
    """ActuarialFrame._expr_to_str method is gone."""
    from gaspatchio.frame import base

    assert not hasattr(base.ActuarialFrame, "_expr_to_str")


def test_is_boolean_list_attribute_not_set_by_mask_ops() -> None:
    """The mask-producing operators no longer stamp the duck-typed flag."""
    from gaspatchio import ActuarialFrame

    af = ActuarialFrame({"x": [1, 2, 3]})
    cond = (af["x"] > 1) & (af["x"] < 3)
    # The new typed channel is `kind`; the duck-typed flag must not be set.
    assert cond.kind == "boolean_mask"
    assert not getattr(cond, "_is_boolean_list", False)


def test_no_direct_underlying_df_writes_outside_property() -> None:
    """Defense in depth: no other code may write to self._ActuarialFrame__df directly.

    Every plan change routes through `_set_plan`, which refreshes the cached
    schema and bumps `_schema_generation`; the `_df` setter, the route a
    model's own write takes, reads that write and then calls it too. If a
    future contributor reaches into `_ActuarialFrame__df` directly, the cache
    will silently rot. We bound the number of direct writes to two: the
    name-mangled `self.__df = None` initialization in `__init__`, and the
    one inside `_set_plan`.
    """
    import re
    from pathlib import Path

    base_py = (
        Path(__file__).resolve().parent.parent / "gaspatchio" / "frame" / "base.py"
    )
    src = base_py.read_text()

    # Match both the source-level `self.__df = ...` and the post-mangle form.
    pattern = re.compile(r"self\.(?:__df|_ActuarialFrame__df)\s*=")
    matches = list(pattern.finditer(src))

    assert len(matches) <= 2, (
        f"Too many direct __df writes ({len(matches)}). "
        "All mutations must go through _set_plan."
    )
