# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Restrictions and helpers for working inside Polars ``list.eval()`` contexts.

Inside ``list.eval``, you cannot reference named columns — the evaluation
context is per-element, not per-frame. This module enforces that constraint
when unwrapping arguments destined for ``list.eval`` calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl


def unwrap_for_list_eval(arg: pl.Expr) -> pl.Expr:
    """Refuse named-column reads inside list.eval on an already lowered operand."""
    try:
        roots = arg.meta.root_names()
    except (AttributeError, RuntimeError):
        roots = []
    if roots:
        msg = "Cannot use expressions with named columns inside list.eval."
        raise TypeError(msg)
    return arg
