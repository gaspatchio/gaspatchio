# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A row operation written in Polars, over a per-period column, on a timeline frame.

On a frame with a projection timeline the rows are policies and each
per-period column holds one list per policy. A Polars expression that reads
neighbouring *rows* -- ``shift``, ``diff``, the fills, ``interpolate``, the
cumulative folds, ``rank``, ``reverse``, a sort, an aggregation, a statistic
of the column (``std``, ``quantile``, ``mode``), a comparison of one row with
the rest (``is_unique``, ``is_sorted``), a pick or reshape of the rows
(``unique``, ``shuffle``, ``top_k``, ``explode``) -- reads the neighbouring
*policies* there: ``pl.col("reserve").shift(1)`` hands each
policy the previous policy's whole timeline, and the answer comes back the
right shape and dtype with nothing to say which axis it ran along. It is a
number that changes with which other policies share the file and in what
order.

The framework's own surface already refuses this. A column, and every
expression a framework producer hands back bound to its frame, answers
``shift`` with a refusal naming the per-period form; the explicit escape,
``af.<column>.polars_native()``, refuses the same names on a per-period
column. What was left is a plain Polars expression -- one an author wrote
with ``pl.col``, or one a frame-independent producer such as
``Schedule.*_expr`` handed back and a Polars method then continued --
assigned straight to the frame. This module reads such an expression's plan
and finds the row operation and the operand it reads; the frame refuses the
assignment.

It is the period-method guard read the other way round. That guard
(``frame/lowering/rules/projection.py``) refuses a *period* method --
``cumulative_survival``, ``previous_period`` and the rest -- handed a column
not known to be per-period on a timeline frame, because the fold would run
down the policies; this refuses a *row* operation handed a column not known
to be per-policy there, for the same reason. Both read a timeline the same
way (``_shape.frame_has_a_timeline``: the frame's schedule, or on a rebuilt
frame its per-period ``month`` or the ``num_proj_months`` every axis
stamps), both leave a frame without one alone -- its rows are the periods,
a long-format frame, and running down them is the calculation -- and both
refuse a shape that cannot be resolved on a timeline frame.

What is read, and what is not:

- a plain Polars expression, and a plain Polars fragment an author used as
  an operand inside a framework formula (``af.x * pl.col("t").shift(1)``),
  which the operand door marks as raw; the rest of a framework proxy or a
  producer's ``ProxyAwareExpr`` was built through the vocabulary, whose own
  doors already decide this, and ``polars_native()`` is the explicit escape,
  which stays the author's to open;
- a row operation inside ``list.eval(...)`` reads the elements of one
  policy's own list, which is exactly the per-period form, and is not one;
- an elementwise operation reads nothing beyond its own row and is not one.

Which plan functions read other rows is measured, not listed by hand: each
public ``pl.Expr`` method is applied to one column and its answer for one
policy compared across the file it shares, alone and reordered, and every
method whose answer moves is one this module reads. A plan Polars cannot
serialise -- ``rolling_map`` holds a Python function -- is not read.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any, Final

import polars as pl

from gaspatchio._semantic.ir import EngineNative, walk
from gaspatchio._shape import _shape_from_expr_dtype, frame_has_a_timeline
from gaspatchio.frame.lowering.ingress import raw_operand_expr

if TYPE_CHECKING:
    from collections.abc import Iterator

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio._shape import Shape

# Polars' function names that read neighbouring rows, as the plan spells
# them, mapped to the method an author wrote. A function absent here reads
# only its own row.
_ROW_FUNCTIONS: Final[dict[str, str]] = {
    "Shift": "shift",
    "ShiftAndFill": "shift",
    "Diff": "diff",
    "Interpolate": "interpolate",
    "InterpolateBy": "interpolate_by",
    "CumSum": "cum_sum",
    "CumProd": "cum_prod",
    "CumMin": "cum_min",
    "CumMax": "cum_max",
    "CumCount": "cum_count",
    "PctChange": "pct_change",
    "RollingExpr": "rolling_*",
    "RollingExprBy": "rolling_*_by",
    "EwmMean": "ewm_mean",
    "EwmStd": "ewm_std",
    "EwmVar": "ewm_var",
    "Rank": "rank",
    "Reverse": "reverse",
    # Folds and statistics of the whole column, answered to every row.
    "Product": "product",
    "Quantile": "quantile",
    "Mode": "mode",
    "Skew": "skew",
    "Kurtosis": "kurtosis",
    "Entropy": "entropy",
    "ApproxNUnique": "approx_n_unique",
    "NullCount": "null_count",
    "UniqueCounts": "unique_counts",
    "ValueCounts": "value_counts",
    "Hist": "hist",
    "QCut": "qcut",
    "IndexOf": "index_of",
    "SearchSorted": "search_sorted",
    # Positions among the rows, and the row a position picks.
    "ArgMin": "arg_min",
    "ArgMax": "arg_max",
    "ArgSort": "arg_sort",
    "ArgUnique": "arg_unique",
    "ArgWhere": "arg_true",
    "MinBy": "min_by",
    "MaxBy": "max_by",
    "PeakMin": "peak_min",
    "PeakMax": "peak_max",
    "RLE": "rle",
    "RLEID": "rle_id",
    "EwmMeanBy": "ewm_mean_by",
    # Selections, reorders and reshapes of the rows.
    "Unique": "unique",
    "TopK": "top_k",
    "TopKBy": "top_k_by",
    "Random": "sample",
    "DropNulls": "drop_nulls",
    "DropNans": "drop_nans",
    "GatherEvery": "gather_every",
    "Append": "append",
    "ExtendConstant": "extend_constant",
    "Reshape": "reshape",
}

# Functions Polars files under a namespace, as the plan spells the namespace
# and then the function. The rest of each namespace reads only its own row
# -- ``is_in``, ``str.len_chars``, ``bitwise_count_ones`` -- and a
# namespace absent here (``ListExpr`` above all, which reads one policy's
# own list) is not read at all.
_NAMESPACED_ROW_FUNCTIONS: Final[dict[str, dict[str, str]]] = {
    "Boolean": {
        "All": "all",
        "Any": "any",
        "HasNulls": "has_nulls",
        "IsDuplicated": "is_duplicated",
        "IsUnique": "is_unique",
        "IsFirstDistinct": "is_first_distinct",
        "IsLastDistinct": "is_last_distinct",
        "IsSorted": "is_sorted",
    },
    "Bitwise": {"And": "bitwise_and", "Or": "bitwise_or", "Xor": "bitwise_xor"},
    "StringExpr": {"ConcatVertical": "str.join"},
    "Categorical": {"GetCategories": "cat.get_categories"},
}

# A null fill by strategy reads the rows around the gap, except the two
# strategies that fill with a constant.
_FILL_STRATEGIES: Final[dict[str, str]] = {
    "Forward": "forward_fill",
    "Backward": "backward_fill",
    "Mean": 'fill_null(strategy="mean")',
    "Min": 'fill_null(strategy="min")',
    "Max": 'fill_null(strategy="max")',
}

# Plan nodes that read, reorder or select among the rows as a whole.
_ROW_NODES: Final[dict[str, tuple[str, str]]] = {
    "Sort": ("sort", "expr"),
    "SortBy": ("sort_by", "expr"),
    "Gather": ("gather", "expr"),
    "Slice": ("slice", "input"),
    "Filter": ("filter", "input"),
    "Explode": ("explode", "input"),
}


def _row_operations(expr: pl.Expr) -> Iterator[tuple[str, pl.Expr]]:
    """Yield each row operation in ``expr``'s plan, with the operand it reads.

    The method is the name an author wrote (``shift``, ``cum_sum``); the
    operand is the expression the operation is applied to. Operations
    inside ``list.eval(...)`` read one policy's own elements and are not
    yielded. A plan Polars cannot serialise yields nothing: this is a guard
    against one silent mistake, not a parser every expression must satisfy.
    """
    try:
        tree = json.loads(expr.meta.serialize(format="json"))
    except Exception:  # noqa: BLE001 -- an unserialisable plan is left alone
        return
    for method, operand in _walk(tree):
        rebuilt = _rebuilt(operand)
        if rebuilt is not None:
            yield method, rebuilt


def _walk(node: Any) -> Iterator[tuple[str, Any]]:  # noqa: ANN401, C901, PLR0912 -- the plan is JSON
    """Find the row operations in one plan node and its children."""
    if isinstance(node, list):
        for child in node:
            yield from _walk(child)
        return
    if not isinstance(node, dict):
        return
    for kind, body in node.items():
        if kind == "Function" and isinstance(body, dict):
            method = _row_function(body.get("function"))
            inputs = body.get("input") or []
            if method is not None and inputs:
                yield method, inputs[0]
            yield from _walk(inputs)
        elif kind == "Agg" and isinstance(body, dict):
            for name, inner in body.items():
                operand = inner
                if isinstance(inner, dict) and ("input" in inner or "expr" in inner):
                    operand = inner.get("input", inner.get("expr"))
                elif isinstance(inner, list) and inner:
                    # ``std`` and ``var`` carry their operand first and their
                    # ``ddof`` after it.
                    operand = inner[0]
                yield name.lower(), operand
                yield from _walk(operand)
        elif kind in _ROW_NODES and isinstance(body, dict):
            method, key = _ROW_NODES[kind]
            yield method, body.get(key)
            yield from _walk(body)
        elif kind == "Eval" and isinstance(body, dict):
            # The evaluation runs over one policy's own list -- the
            # per-period form, whether it hands back a list (``list.eval``)
            # or one value (``list.agg``) -- unless it is the cumulative
            # variant, which evaluates over the rows read so far.
            if _evaluates_over_the_rows(body.get("variant")):
                yield "cumulative_eval", body.get("expr")
            yield from _walk(body.get("expr"))
        else:
            yield from _walk(body)


def _evaluates_over_the_rows(variant: object) -> bool:
    """Return whether an evaluation's variant runs over the rows, not one list.

    Polars writes the cumulative variant as ``{"Cumulative": {...}}``; every
    other variant -- ``"List"``, ``"ListAgg"``, an array's -- evaluates
    inside one row's own value.
    """
    if isinstance(variant, dict):
        return "Cumulative" in variant
    return variant == "Cumulative"


def _row_function(function: object) -> str | None:
    """Return the method a plan function names, if it reads other rows."""
    if isinstance(function, str):
        return _ROW_FUNCTIONS.get(function)
    if isinstance(function, dict):
        for name, setting in function.items():
            if name == "FillNullWithStrategy":
                strategy = setting if isinstance(setting, str) else next(iter(setting))
                return _FILL_STRATEGIES.get(strategy)
            if name in _NAMESPACED_ROW_FUNCTIONS:
                inner = (
                    setting if isinstance(setting, str) else next(iter(setting), None)
                )
                return _NAMESPACED_ROW_FUNCTIONS[name].get(str(inner))
            if name in _ROW_FUNCTIONS:
                return _as_written(_ROW_FUNCTIONS[name], setting)
    return None


def _as_written(method: str, setting: object) -> str:
    """Name the method an author wrote where one plan function stands for two.

    ``bottom_k`` is ``top_k`` descending in the plan, and ``shuffle`` is a
    ``sample`` by another method; a refusal names the one in the model.
    """
    if not isinstance(setting, dict):
        return method
    descending = setting.get("descending")
    if method in {"top_k", "top_k_by"} and (
        descending is True or (isinstance(descending, list) and any(descending))
    ):
        return method.replace("top", "bottom", 1)
    if method == "sample" and setting.get("method") == "Shuffle":
        return "shuffle"
    return method


def _rebuilt(operand: object) -> pl.Expr | None:
    """Turn one plan node back into the expression it stands for."""
    if operand is None:
        return None
    try:
        return pl.Expr.deserialize(io.StringIO(json.dumps(operand)), format="json")
    except Exception:  # noqa: BLE001 -- a fragment Polars will not rebuild is left alone
        return None


def refuse_a_row_operation_over_periods(frame: object, expr: pl.Expr) -> None:
    """Refuse ``expr`` where it runs a row operation down a per-period column.

    Only on a frame with a projection timeline, and only for an operand not
    known to hold one value per policy: a per-policy column's row operation
    is portfolio-level work and the calculation the author wrote.
    """
    # The plan is read first and the frame only where it holds a row
    # operation: typing the frame resolves its schema, which an ordinary
    # assignment does not otherwise pay for.
    found = list(_row_operations(expr))
    if not found or not frame_has_a_timeline(frame):
        return
    for method, operand in found:
        shape = _shape_from_expr_dtype(frame, operand)
        if shape != "scalar":
            raise ValueError(_refusal(method, operand, shape))


def refuse_a_raw_fragment_over_periods(frame: object, node: OpNode) -> None:
    """Refuse a formula carrying a raw row operation over a per-period column.

    ``af.x * pl.col("t").shift(1)`` reaches the frame as a framework formula
    with the author's raw Polars fragment inside it, as an engine-native
    leaf. The leaves that entered as raw operands are marked at the door
    (``ingress.RAW_OPERANDS``); each is read exactly as a raw expression
    assigned on its own is. A leaf the ``polars_native()`` escape minted is
    not marked and is not read.
    """
    for leaf in walk(node):
        if isinstance(leaf, EngineNative):
            raw = raw_operand_expr(leaf)
            if raw is not None:
                refuse_a_row_operation_over_periods(frame, raw)


def _refusal(method: str, operand: pl.Expr, shape: Shape) -> str:
    """Say what the row operation would do here, and the two ways to write it."""
    held = (
        "holds one value per projection period"
        if shape == "list"
        else "could not be resolved to one value per policy"
    )
    per_period = method.split("(", maxsplit=1)[0]
    return (
        f"{method} on {operand} runs down the rows, and on a frame with a "
        "projection timeline the rows are policies. This operand "
        f"{held}, so the calculation would move values between policies rather "
        "than between periods, and the answer would come back the right shape "
        "with nothing to say which axis it used. For the per-period form, "
        "evaluate it inside each policy's own list -- "
        f".list.eval(pl.element().{per_period}(...)) -- or write it on the "
        "column with the declared operation where there is one "
        "(af.<column>.cum_sum(), .projection.previous_period()). If the "
        "calculation really does run down the model points, take it on a "
        "per-policy column, or open the explicit escape, "
        "af.<column>.polars_native(), which records the line as engine-native "
        "and keeps its own refusals."
    )


__all__ = [
    "refuse_a_raw_fragment_over_periods",
    "refuse_a_row_operation_over_periods",
]
