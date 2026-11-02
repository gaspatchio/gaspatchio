# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Resolve authoring operands through the shared shape/dtype rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._shape import (
    Kind,
    Shape,
    _is_literal_expr,
    _literal_dtype,
    _shape_from_expr_dtype,
    shape_from_dtype,
)
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.condition_expression import ConditionExpression
from gaspatchio.column.expression_proxy import ExpressionProxy

if TYPE_CHECKING:
    from gaspatchio.frame.base import ActuarialFrame


def resolve_shape(value: object, parent: ActuarialFrame | None) -> Shape:
    """Return the shape of ``value``: the single source of shape truth.

    All callers route through here.

    Note: a bare string is treated as `unknown` — it's ambiguous between
    "literal scalar" and "column name". Callers that know which use the
    appropriate helper directly (`_shape_from_schema` for column names).
    """
    if isinstance(value, (ColumnProxy, ExpressionProxy, ConditionExpression)):
        return value.shape
    if isinstance(value, pl.Expr):
        # Fast path: literal expressions (pl.lit, etc.) have no column roots,
        # so they are typed against an empty frame rather than the parent's
        # plan -- the deep select(expr).collect_schema() probe fires twice
        # per case for chained when() construction and dominates wall time
        # at small frame sizes. A list literal is a shared per-period
        # timeline (a projection's own year fractions on a uniform grid),
        # not one value per policy.
        if _is_literal_expr(value):
            return "list" if isinstance(_literal_dtype(value), pl.List) else "scalar"
        return _shape_from_expr_dtype(parent, value)
    if isinstance(value, (bool, int, float)):
        return "scalar"
    if isinstance(value, str):
        # Ambiguous — could be column name or literal. Caller must disambiguate.
        return "unknown"
    return "unknown"


__all__ = ["Kind", "Shape", "resolve_shape", "shape_from_dtype"]
