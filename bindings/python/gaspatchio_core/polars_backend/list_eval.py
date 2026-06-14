# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Restrictions and helpers for working inside Polars ``list.eval()`` contexts.

Inside ``list.eval``, you cannot reference named columns — the evaluation
context is per-element, not per-frame. This module enforces that constraint
when unwrapping arguments destined for ``list.eval`` calls.
"""

from __future__ import annotations

from typing import Any

import polars as pl


def unwrap_for_list_eval(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap an argument for use inside ``list.eval(...)`` context.

    Inside list.eval, named-column references are illegal. Detect them via
    structural ``meta.root_names()`` (not string inspection) and raise.
    """
    # Defer proxy imports to avoid frontend dependency cycles.
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        msg = f"Cannot reference column '{arg.name}' inside list.eval context."
        raise TypeError(msg)
    if isinstance(arg, ExpressionProxy):
        msg = "Cannot use complex expressions inside list.eval context."
        raise TypeError(msg)
    if isinstance(arg, pl.Expr):
        try:
            roots = arg.meta.root_names()
        except (AttributeError, RuntimeError):
            roots = []
        if roots:
            msg = "Cannot use expressions with named columns inside list.eval."
            raise TypeError(msg)
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return arg
