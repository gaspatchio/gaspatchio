# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Single source of truth for shape and kind metadata on proxy objects.

This module defines:
- `Shape` and `Kind` typed literals
- `_UNSET` sentinel distinguishing "not yet computed" from "computed and got Unknown"
- `resolve_shape()`: the one resolver that all callers route through
- `_max_shape()`: combiner for binary operations
- `_kind_from_dtype()`: dtype-driven fallback for kind classification

This is the only place shape and kind inference logic lives. All other code
reads `shape` and `kind` as properties on proxies, never re-derives them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, Union

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame


Shape = Literal["scalar", "list", "unknown"]
Kind = Literal["value", "comparison", "boolean_mask", "unknown"]


_UNSET = object()  # module-level sentinel


def _max_shape(a: Shape, b: Shape) -> Shape:
    """Combine two shapes per binary-op semantics.

    Combining list and scalar produces list (broadcast).
    Any unknown operand produces unknown (forces explicit handling).
    """
    if a == "unknown" or b == "unknown":
        return "unknown"
    if a == "list" or b == "list":
        return "list"
    return "scalar"


def _shape_from_schema(parent: ActuarialFrame | None, column_name: str) -> Shape:
    """Read shape from the parent frame's cached schema."""
    if parent is None:
        return "unknown"
    schema = getattr(parent, "_schema", None)
    if schema is None:
        return "unknown"
    dtype = schema.get(column_name)
    if dtype is None:
        return "unknown"
    if isinstance(dtype, pl.List):
        return "list"
    return "scalar"


def resolve_shape(value: object, parent: ActuarialFrame | None) -> Shape:
    """The single source of shape truth. All callers route through here.

    Note: a bare string is treated as `unknown` — it's ambiguous between
    "literal scalar" and "column name". Callers that know which use the
    appropriate helper directly (`_shape_from_schema` for column names).
    """
    # Defer proxy imports to avoid circular imports
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    if isinstance(value, (ColumnProxy, ExpressionProxy, ConditionExpression)):
        return value.shape
    if isinstance(value, pl.Expr):
        # Fast path: literal expressions (pl.lit, etc.) have no column roots
        # and are always scalar. Skip the select(expr).collect_schema() probe
        # — for chained when() construction it fires twice per case (left +
        # right) and dominates wall time at small frame sizes.
        try:
            if not value.meta.root_names():
                return "scalar"
        except (AttributeError, RuntimeError):
            pass
        return _shape_from_expr_dtype(parent, value)
    if isinstance(value, bool):
        return "scalar"
    if isinstance(value, (int, float)):
        return "scalar"
    if isinstance(value, str):
        # Ambiguous — could be column name or literal. Caller must disambiguate.
        return "unknown"
    return "unknown"


def _is_literal_expr(expr: pl.Expr) -> bool:
    """True for expressions with no column roots — literals like pl.lit(0)."""
    try:
        return not expr.meta.root_names()
    except (AttributeError, RuntimeError):
        return False


_MINIMAL_FRAME_CACHE: dict[tuple[tuple[str, pl.DataType], ...], pl.LazyFrame] = {}

# Building a minimal schema-only frame costs ~60us; the deep probe
# ``df.select(expr).collect_schema()`` costs only as much as the plan is deep
# (~4us/node). So the minimal frame only pays off once the plan is non-trivial.
# Below this many columns (~= plan depth at probe time) the deep probe is already
# cheaper, so we skip the build and avoid regressing trivial frames (e.g. a
# freshly-built chained ``when()`` over a one-column frame). A cache HIT (~15us)
# is always used regardless of depth.
_MINIMAL_PROBE_MIN_COLS = 16


def _resolve_expr_output_dtype(
    parent: ActuarialFrame | None, expr: pl.Expr
) -> pl.DataType | None:
    """Resolve an expression's output dtype as cheaply as possible.

    The naive probe ``df.select(expr).collect_schema()`` re-resolves the whole
    (growing, ~90-node) lazy plan on every call — that cost scales with plan
    depth and, summed over a model's column assignments, dominates plan-build
    wall time (~400us/probe late in an L4 build vs the numbers below).

    Output dtype depends only on the *input column dtypes* and the expression,
    never on plan depth or data. So resolve the expr against a MINIMAL frame
    carrying only the columns the expr actually references
    (``expr.meta.root_names()``), pulled from the parent's cached schema. That
    minimal frame is ~62us to build fresh and ~15us reused — vs ~400us for the
    deep probe on a deep plan. On shallow plans the deep probe is already cheap,
    so it is used directly (see ``_MINIMAL_PROBE_MIN_COLS``). Falls back to the
    authoritative full-plan probe whenever the minimal resolution can't type the
    expr (missing root in cache, plugin needing real context, etc.).
    """
    df = getattr(parent, "_df", None)
    if df is None:
        return None
    # Only engage the minimal-frame machinery on a deep enough plan that the deep
    # probe is actually expensive. On shallow plans skip it entirely (don't even
    # compute root_names / cache keys) so trivial frames pay exactly the cheap
    # deep probe, same as before this optimisation.
    schema = getattr(parent, "_schema", None)
    if schema is not None and len(schema) >= _MINIMAL_PROBE_MIN_COLS:
        try:
            key = tuple((name, schema[name]) for name in expr.meta.root_names())
            frame = _MINIMAL_FRAME_CACHE.get(key)
            if frame is None:
                frame = pl.LazyFrame(schema=dict(key))
                if len(_MINIMAL_FRAME_CACHE) < 4096:  # bounded; avoid unbounded growth
                    _MINIMAL_FRAME_CACHE[key] = frame
            return frame.select(expr.alias("_t")).collect_schema().get("_t")
        except Exception:  # noqa: BLE001
            pass  # fall through to the authoritative full-plan probe
    try:
        return df.select(expr.alias("_t")).collect_schema().get("_t")
    except Exception:  # noqa: BLE001
        return None


def _shape_from_expr_dtype(parent: ActuarialFrame | None, expr: pl.Expr) -> Shape:
    """Fall back: probe the wrapped expression's output dtype via parent frame."""
    if parent is None:
        return "unknown"
    if getattr(parent, "_df", None) is None:
        return "unknown"
    # Literals are always scalar — skip the dtype probe.
    if _is_literal_expr(expr):
        return "scalar"
    dtype = _resolve_expr_output_dtype(parent, expr)
    if dtype is None:
        return "unknown"
    if isinstance(dtype, pl.List):
        return "list"
    return "scalar"


def _kind_from_dtype(expr: pl.Expr, parent: ActuarialFrame | None) -> Kind:
    """Infer kind from the wrapped expression's output dtype.

    Boolean dtype (or List<Boolean>) -> boolean_mask.
    Anything else -> value.

    Used as the fallback when an ExpressionProxy is constructed without an
    explicit kind (i.e. from autopatched dispatch or `_wrap` calls). Catches
    predicate-producing methods (is_null, is_in, is_unique, etc.) including
    those reflectively added by _autopatch.
    """
    if parent is None:
        return "value"
    if getattr(parent, "_df", None) is None:
        return "value"
    # Literals are always value — skip the probe.
    if _is_literal_expr(expr):
        return "value"
    dtype = _resolve_expr_output_dtype(parent, expr)
    if dtype == pl.Boolean:
        return "boolean_mask"
    if isinstance(dtype, pl.List) and dtype.inner == pl.Boolean:
        return "boolean_mask"
    return "value"
