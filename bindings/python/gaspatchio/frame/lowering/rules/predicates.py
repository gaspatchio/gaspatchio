# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the predicate operations that are not binary operators.

``&`` and ``|`` are ``BinOp("and")``/``BinOp("or")`` and lower in
``polars.py`` with the rest of the operator vocabulary. ``~`` has no
binary form -- and cannot be given one, because ``BinOp`` would turn a
Boolean predicate into a Float64 mask and ``pl.when()`` rejects those --
so it emits ``Call("not_")`` and its former body lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio.frame.lowering._polars.unknown import unknown_guard
from gaspatchio.frame.lowering.polars import (
    lower_predicate,
    lower_predicate_mask,
    register_lowering,
    unknown_of,
)

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext


@register_lowering("not_")
def _lower_not(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Negate a predicate, one way per shape.

    A scalar predicate negates with Polars' own ``~`` and stays Boolean,
    which is required because the result routinely feeds ``pl.when()``.
    A per-period predicate has no native element-wise ``~`` that reaches
    inside a ``list``, so it negates arithmetically over the Float64 0/1
    mask: ``1.0 - mask``.

    A direct reference to a stored ``f64`` column negates as the flag it is,
    under the exact 0/1 check a ``when`` condition applies (§11.1.27).
    """
    (operand,) = node.args
    expr, shape = lower_predicate(operand, ctx)
    if shape == "list":
        return pl.lit(1.0) - lower_predicate_mask(operand, ctx)
    unknown = unknown_of(operand, ctx)
    if unknown is not None:
        # A test with no truth value (a NaN reached its comparison) has no
        # negation either; a Boolean holds no NaN, so it is a null (11.1.26).
        return unknown_guard(unknown, pl.lit(None), ~expr)
    return ~expr
