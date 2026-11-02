# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Single source of truth for shape and kind metadata on proxy objects.

This module defines:
- `Shape` and `Kind` typed literals
- `_UNSET` sentinel distinguishing "not yet computed" from "computed and got Unknown"
- Proxy-specific resolution stays in `column.shape.resolve_shape()`.
- `_max_shape()`: combiner for binary operations
- `_kind_from_dtype()`: dtype-driven fallback for kind classification

This is the only place shape and kind inference logic lives. All other code
reads `shape` and `kind` as properties on proxies, never re-derives them.
"""

from __future__ import annotations

from typing import Literal

import polars as pl
from loguru import logger

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


def shape_from_dtype(dtype: pl.DataType | None) -> Shape:
    """Classify a resolved Polars dtype as scalar or list.

    The dtype-only entry point for callers that hold a schema or probed
    dtype rather than an expression (e.g. the calculation-graph exporter).
    Lives here so the classification rule has exactly one home.
    """
    if dtype is None:
        return "unknown"
    if isinstance(dtype, pl.List):
        return "list"
    return "scalar"


def _shape_from_schema(parent: object | None, column_name: str) -> Shape:
    """Read shape from the parent frame's cached schema."""
    if parent is None:
        return "unknown"
    schema = getattr(parent, "_schema", None)
    if schema is None:
        return "unknown"
    return shape_from_dtype(schema.get(column_name))


# The boundary count ``projection.set()`` stamps on every axis it lays --
# monthly or weekly, a shared grid or each policy's own, a calendar or a fixed
# step -- where ``month`` is stamped only on the month-aligned,
# projection-anchored ones, and ``step`` only on a fixed-step axis.
_BOUNDARY_COUNT_COLUMN = "num_proj_months"

# The per-period indexes an axis stamps, either of which marks a frame rebuilt
# from a collected projection as one whose rows are still policies.
_PERIOD_INDEX_COLUMNS = ("month", "step")


def frame_has_a_timeline(frame: object | None) -> bool:
    """Whether the frame's rows are policies laid along a projection timeline.

    The one reading both timeline guards share: the period methods' (a
    per-policy column refused) and the row operations' (a per-period column
    refused). Any of three signals is enough:

    - the schedule ``projection.set()`` keeps on the frame;
    - a per-period ``month`` or ``step`` column, which a frame rebuilt from a
      collected monthly, quarterly, semi-annual or annual projection, or from
      a fixed-step one, still carries;
    - ``num_proj_months``, which every axis stamps, beside a per-period
      column: a frame rebuilt from a weekly, daily or inception axis, none of
      which stamps ``month``.

    ``num_proj_months`` alone is not enough. A projection's output exploded
    to one row per period still carries it, and nothing on that frame is laid
    along periods any more: its rows are the periods, and the methods run
    down them as on any long-format frame.
    """
    if frame is None:
        return False
    if getattr(frame, "_projection", None) is not None:
        return True
    schema = getattr(frame, "_schema", None) or {}
    if any(
        shape_from_dtype(schema.get(index)) == "list" for index in _PERIOD_INDEX_COLUMNS
    ):
        return True
    return _BOUNDARY_COUNT_COLUMN in schema and any(
        shape_from_dtype(dtype) == "list" for dtype in schema.values()
    )


def _is_literal_expr(expr: pl.Expr) -> bool:
    """Identify expressions with no column roots, such as pl.lit(0)."""
    try:
        return not expr.meta.root_names()
    except (AttributeError, RuntimeError):
        return False


# Typing an expression that reads no column needs no plan at all: an empty
# frame resolves it. Built once; a LazyFrame is immutable, so sharing it is safe.
_NO_COLUMNS = pl.LazyFrame()


def _literal_dtype(expr: pl.Expr) -> pl.DataType | None:
    """Resolve the dtype of an expression that reads no column.

    A root-less expression is not always one value per policy. A projection
    on a shared grid lowers its timeline -- ``af.projection.year_fractions()``,
    ``t_years()``, ``anniversary_mask()`` -- to a literal *list*, one value per
    period that every policy shares, so "no columns, therefore scalar" read a
    per-period timeline as per-policy and sent ``cum_sum`` and ``list.get``
    on it down the wrong path. The dtype says which it is; ``None`` where it
    cannot be typed.
    """
    try:
        return _NO_COLUMNS.select(expr.alias("_t")).collect_schema().get("_t")
    except Exception as error:  # noqa: BLE001 -- untypable stays the old answer
        logger.trace("Literal dtype probe failed: {}", error)
        return None


_MINIMAL_FRAME_CACHE: dict[tuple[tuple[str, pl.DataType], ...], pl.LazyFrame] = {}

# Building a minimal schema-only frame costs ~60us; the deep probe
# ``df.select(expr).collect_schema()`` costs only as much as the plan is deep
# (~4us/node). So the minimal frame only pays off once the plan is non-trivial.
# Below this many columns (~= plan depth at probe time) the deep probe is already
# cheaper, so we skip the build and avoid regressing trivial frames (e.g. a
# freshly-built chained ``when()`` over a one-column frame). A cache HIT (~15us)
# is always used regardless of depth.
_MINIMAL_PROBE_MIN_COLS = 16
_MINIMAL_FRAME_CACHE_LIMIT = 4096


def _resolve_expr_output_dtype(
    parent: object | None, expr: pl.Expr
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
    df: pl.LazyFrame | None = getattr(parent, "_df", None)
    if df is None:
        return None
    # Only engage the minimal-frame machinery on a deep enough plan that the deep
    # probe is actually expensive. On shallow plans skip it entirely (don't even
    # compute root_names / cache keys) so trivial frames pay exactly the cheap
    # deep probe, same as before this optimisation.
    schema = getattr(parent, "_schema", None)
    # A plan that no longer resolves cannot answer the deep probe at all, so
    # the cached schema -- which each assignment keeps typed -- answers it.
    unresolved = bool(vars(parent).get("_schema_unresolved", False))
    if schema is not None and (len(schema) >= _MINIMAL_PROBE_MIN_COLS or unresolved):
        try:
            key = tuple((name, schema[name]) for name in expr.meta.root_names())
            frame = _MINIMAL_FRAME_CACHE.get(key)
            if frame is None:
                frame = pl.LazyFrame(schema=dict(key))
                if (
                    len(_MINIMAL_FRAME_CACHE) < _MINIMAL_FRAME_CACHE_LIMIT
                ):  # bounded; avoid unbounded growth
                    _MINIMAL_FRAME_CACHE[key] = frame
            return frame.select(expr.alias("_t")).collect_schema().get("_t")
        except Exception as error:  # noqa: BLE001
            logger.trace(
                "Schema-only dtype probe failed; using the full plan: {}", error
            )
    try:
        probed = _with_unmaterialised_rollforwards(parent, df, expr)
        return probed.select(expr.alias("_t")).collect_schema().get("_t")
    except Exception:  # noqa: BLE001
        return None


def _with_unmaterialised_rollforwards(
    parent: object | None, df: pl.LazyFrame, expr: pl.Expr
) -> pl.LazyFrame:
    """Return ``df`` with any rollforward struct ``expr`` reads added, for typing.

    ``compiled.expr_for("av")`` reads the hidden struct column its kernel
    writes, and the frame adds that column only when the read is assigned.
    Before then the read could not be typed, so a method chained on it --
    ``expr_for("av").list.get(-1)`` -- found no period axis. Typing it
    against the plan with the struct added answers what the assignment
    would; the frame's own plan is not touched.
    """
    from gaspatchio.rollforward import _registry  # noqa: PLC0415 -- import cycle

    if not _registry.has_entries():
        return df
    schema = getattr(parent, "_schema", None) or {}
    missing = [
        name
        for name in expr.meta.root_names()
        if name.startswith(_registry.HIDDEN_PREFIX) and name not in schema
    ]
    if not missing:
        return df
    return df.with_columns(
        *(_registry.plugin_expr_for(name).alias(name) for name in missing)
    )


def _shape_from_expr_dtype(parent: object | None, expr: pl.Expr) -> Shape:
    """Fall back: probe the wrapped expression's output dtype via parent frame."""
    if parent is None:
        return "unknown"
    if getattr(parent, "_df", None) is None:
        return "unknown"
    # A literal needs no plan to type: a list literal is a shared timeline,
    # anything else one value for every policy.
    if _is_literal_expr(expr):
        return "list" if isinstance(_literal_dtype(expr), pl.List) else "scalar"
    dtype = _resolve_expr_output_dtype(parent, expr)
    if dtype is None:
        return "unknown"
    if isinstance(dtype, pl.List):
        return "list"
    return "scalar"


def _kind_from_dtype(expr: pl.Expr, parent: object | None) -> Kind:
    """Infer kind from the wrapped expression's output dtype.

    Boolean dtype (or List<Boolean>) -> boolean_mask.
    Anything else -> value.

    Used as the fallback when an ExpressionProxy is constructed without an
    explicit kind, including expressions returned by the native escape.
    Recognizes Boolean results from predicates such as is_unique.
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
