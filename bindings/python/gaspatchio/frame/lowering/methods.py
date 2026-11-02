# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Adapt declared method operands to the op tree and recognise namespaces.

The direct column-method declarations live in :mod:`gaspatchio._semantic.operations`,
which remains importable with the standard library alone. This module owns the
engine-aware ingress boundary they deliberately do not: proxy nodes, Polars
expressions and series, dates, times and numeric scalar types become op-tree
operands here. A validated sequence literal arrives in a neutral marker so it
cannot be confused with an arbitrary container the previous recognisers declined.

String and list namespace methods use those same declarations.
Lowering stays separately owned by ``frame/lowering/rules/``.
"""

from __future__ import annotations

import datetime
import math
import numbers
from typing import TYPE_CHECKING, Any, Final

import polars as pl

from gaspatchio._semantic.operations import (
    ACCUMULATION_OPERATIONS,
    LIST_OPERATIONS,
    PROXY_OPERATIONS,
    STRING_OPERATIONS,
    CoreCall,
    _LiteralOperand,
)
from gaspatchio.frame.lowering.ingress import recordable_node

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaspatchio._semantic.ir import OpNode


__all__ = [
    "ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE",
    "ALONG_THE_PERIOD_AXIS",
    "DOWN_THE_ROWS",
    "FOLDS_WITH_A_PERIOD_FORM",
    "CoreCall",
    "core_call",
    "core_list_call",
    "core_string_call",
]

# What an operand may be, beyond a proxy carrying its own node: the value
# forms ``ingress.to_node`` has an answer for that cannot fail on the way
# in. Anything else -- a set, a NumPy array, an engine object this package
# has never met -- leaves the call on the engine path rather than being
# pushed through ``pl.lit`` to find out.
_OPERAND_VALUES: Final[tuple[type, ...]] = (
    bool,
    str,
    numbers.Real,
    datetime.date,
    datetime.time,
    pl.Expr,
    pl.Series,
)


def _is_operand(value: object) -> bool:
    """Check an operator operand without retaining an engine-native node."""
    if getattr(value, "_node", None) is not None:
        return True
    if not isinstance(value, _OPERAND_VALUES):
        return False
    return (
        isinstance(value, numbers.Integral)
        or not isinstance(value, numbers.Real)
        or math.isfinite(value)
    )


def _operand(value: object) -> OpNode | None:
    """Return the node standing for one argument, or ``None`` to decline it.

    A proxy carries its own node and is always an operand. Everything else
    has to be a value form the op-tree or its engine-native escape has an
    answer for; a value neither of them holds is not an argument this
    module can record, and saying so is what leaves the call where it was.

    Two things can make the answer ``None``: a value form nothing here
    recognises, and a value that is the right form but one the tree cannot
    hold -- a NaN or an infinity, which ``recordable_node`` declines rather
    than raising over. Both leave the call where it was, which is what a
    caller of this function is asking for.
    """
    if isinstance(value, _LiteralOperand):
        return recordable_node(value.values)
    if getattr(value, "_node", None) is not None:
        return recordable_node(value)
    if isinstance(value, _OPERAND_VALUES):
        return recordable_node(value)
    return None


# --- the two doors -----------------------------------------------------------

# The engine's method name -> the recogniser for the operation it means, on
# a proxy's own method surface. Every entry here is an identifier section
# 11.1 lists; a name absent from it is a method the vocabulary does not
# reach, and the node a call to it mints says so.
# The operations whose meaning is the axis they fold along. Every other
# name above answers one value at a time, so the shape of the value it was
# called on changes how the operation reaches the engine and never what
# the operation is. These two are different: along a projection's periods
# a cumulative product is the fund's growth from the start of the
# projection, and down the model points it is a running product over
# whichever order the rows happen to stand in -- a different calculation,
# with a different answer, that section 11.1 does not name. The receiver's
# shape is resolved against the frame at the door, which is the only place
# that holds one; what lives here is which operations the question is
# asked about.
ALONG_THE_PERIOD_AXIS: Final[frozenset[str]] = frozenset(
    operation.identifier for operation in ACCUMULATION_OPERATIONS
)

# The same question asked of the names the vocabulary does *not* hold. The
# set above protects an operation that has two meanings; these have two
# meanings and no operation at all, so the engine escape is the only way to
# reach them and there is nothing on the ordinary surface to decline the
# wrong one. On a per-period column Polars reads the whole column as one
# value per policy, so `polars_native().shift(1)` moves each policy's entire
# timeline onto the next policy, `diff()` subtracts one policy from another,
# and the three fills walk down the model points instead of along the
# periods -- leaving an interior gap unfilled, or dragging a neighbouring
# policy's values across the boundary. Each answer comes back the right
# shape and the right dtype, with no error, which is what makes these worth
# naming: an actuary reading `shift` reads the period before, and the escape
# hands back the policy before.
#
# What is *not* here, and why. `sum`, `mean`, `min`, `max`, `cum_sum`,
# `cum_prod`, `cum_max`, `cum_min` and `pct_change` ask the same question,
# but Polars refuses the list dtype outright -- "`sum` operation not
# supported for dtype `list[f64]`" -- so they fail loudly and need no guard;
# the first four also have a declared per-period form in the list namespace.
# `rank`, `sort` and `reverse` order the book, which is the portfolio-level
# work the escape is documented for, so refusing them would close the door
# on its own stated purpose. That is about the escape, where the author has
# said they are writing Polars; on the ordinary surface a column refuses all
# of them as names the vocabulary does not hold, and a producer's expression
# answers them as a column does (`DOWN_THE_ROWS`, below).
ACROSS_MODEL_POINTS_THROUGH_THE_ESCAPE: Final[frozenset[str]] = frozenset(
    {"backward_fill", "diff", "forward_fill", "interpolate", "shift"}
)

# The Polars names that read the other rows -- fold them (`sum`, `mean`,
# `std`, `quantile`, `any`), run along them (`cum_max`, `rolling_*`,
# `ewm_*`), order or rank them (`sort`, `rank`, `arg_sort`, `shuffle`),
# compare one row with the rest (`is_unique`, `is_sorted`, `index_of`) or
# select, drop and reshape them (`filter`, `head`, `unique`, `drop_nulls`,
# `explode`) -- that the declared vocabulary does not hold. Each is a name
# whose plan the row-operation guard (`frame/_row_operations.py`) reads as a
# row operation, measured over every public `pl.Expr` name applied, as
# Polars' own method, to a frame-bound per-policy lookup; the five above are
# kept apart because the escape refuses them as well. The guard's tables are
# measured in turn, against the rows each name's answer actually reads.
#
# A column refuses these names, and the explicit escape is the door. A
# producer's frame-bound expression (`table.lookup(age=af.age)`) is a
# `pl.Expr` and so inherited Polars' own method, which answered down the
# model points: `.sum()` on a per-policy lookup handed every policy the
# total over the book, a number that changed with which policies shared the
# file, and the row guard passes a per-policy operand as the portfolio-level
# work a raw Polars author wrote on purpose. The same formula split over
# two lines -- assign the lookup, then `.sum()` it -- was refused. A bound
# expression now answers these names as the column does.
DOWN_THE_ROWS: Final[frozenset[str]] = frozenset(
    {
        "agg_groups",
        "all",
        "any",
        "append",
        "approx_n_unique",
        "arg_max",
        "arg_min",
        "arg_sort",
        "arg_true",
        "arg_unique",
        "bitwise_and",
        "bitwise_or",
        "bitwise_xor",
        "bottom_k",
        "bottom_k_by",
        "count",
        "cum_count",
        "cum_max",
        "cum_min",
        "cumulative_eval",
        "dot",
        "drop_nans",
        "drop_nulls",
        "entropy",
        "ewm_mean",
        "ewm_mean_by",
        "ewm_std",
        "ewm_var",
        "explode",
        "extend_constant",
        "filter",
        "first",
        "flatten",
        "gather",
        "gather_every",
        "get",
        "has_nulls",
        "head",
        "hist",
        "implode",
        "index_of",
        "interpolate_by",
        "is_duplicated",
        "is_first_distinct",
        "is_last_distinct",
        "is_sorted",
        "is_unique",
        "item",
        "kurtosis",
        "last",
        "len",
        "limit",
        "max",
        "max_by",
        "mean",
        "median",
        "min",
        "min_by",
        "mode",
        "n_unique",
        "nan_max",
        "nan_min",
        "null_count",
        "pct_change",
        "peak_max",
        "peak_min",
        "product",
        "qcut",
        "quantile",
        "rank",
        "reshape",
        "reverse",
        "rle",
        "rle_id",
        "rolling_kurtosis",
        "rolling_max",
        "rolling_max_by",
        "rolling_mean",
        "rolling_mean_by",
        "rolling_median",
        "rolling_median_by",
        "rolling_min",
        "rolling_min_by",
        "rolling_quantile",
        "rolling_quantile_by",
        "rolling_rank",
        "rolling_rank_by",
        "rolling_skew",
        "rolling_std",
        "rolling_std_by",
        "rolling_sum",
        "rolling_sum_by",
        "rolling_var",
        "rolling_var_by",
        "sample",
        "search_sorted",
        "shuffle",
        "skew",
        "slice",
        "sort",
        "sort_by",
        "std",
        "sum",
        "tail",
        "top_k",
        "top_k_by",
        "unique",
        "unique_counts",
        "value_counts",
        "var",
        "where",
    }
)

# The folds whose per-period form the list namespace declares (section
# 11.1.14 to 11.1.17): a refusal of one names `.list.<name>()`.
FOLDS_WITH_A_PERIOD_FORM: Final[frozenset[str]] = frozenset(
    {"sum", "mean", "min", "max"}
)

_STRING_METHODS = {
    operation.identifier.rsplit(".", 1)[-1]: operation
    for operation in STRING_OPERATIONS
}
_LIST_METHODS = {
    operation.identifier.rsplit(".", 1)[-1]: operation for operation in LIST_OPERATIONS
}


def core_call(
    method: str,
    receiver: OpNode,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> CoreCall | None:
    """Return the core operation a proxy method call means, or ``None``.

    Args:
        method: The engine's own name for the method that was called.
        receiver: The node standing for the value it was called on.
        args: The call's positional arguments, as the author wrote them.
        kwargs: The call's keyword arguments, likewise.

    Returns:
        The operation, its operands and its configuration, where the
        vocabulary names it in the form it was written; ``None`` where it
        does not. Reflective callers then use the engine path; explicit
        generated callers refuse the form and name ``polars_native()``.

    """
    operation = PROXY_OPERATIONS.get(method)
    if operation is None:
        return None
    return operation.bind(receiver, args, kwargs, _operand)


def core_string_call(
    method: str,
    receiver: OpNode,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> CoreCall | None:
    """Return the core operation a ``.str`` method call means, or ``None``.

    The string namespace's own door, with the same contract as
    :func:`core_call`: a namespace is a second method surface rather than a
    second kind of question.
    """
    recognise = _STRING_METHODS.get(method)
    if recognise is None:
        return None
    return recognise.bind(receiver, args, kwargs, _operand)


def core_list_call(
    method: str,
    receiver: OpNode,
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
) -> CoreCall | None:
    """Return the core operation a ``.list`` method call means, or ``None``.

    The third method surface, with the same contract as the two above. What
    it does not carry is the shape question every name behind it turns on:
    a fold is the operation section 11.1 names only where the receiver is a
    per-period column, and only a frame can say which axis a value has. The
    door that calls this resolves that first, which is why the string
    namespace's wiring is copied here and the column door's guard is copied
    beside it.
    """
    recognise = _LIST_METHODS.get(method)
    if recognise is None:
        return None
    return recognise.bind(receiver, args, kwargs, _operand)
