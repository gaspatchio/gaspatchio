# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the two folds that run along a projection's periods.

``af.growth_factor.cum_prod()`` is the fund's growth from the start of the
projection, and ``af.cashflow.cum_sum()`` the premium taken so far -- the
closed forms an actuarial model reaches for instead of a state machine
whenever the within-period charge does not depend on the running balance.
Both fold *along the period axis*, within one policy, which is why both
lower inside each row's list and neither has a second form: a value with
no period axis is not the operation section 11.1 names, and the recogniser
declines it at the door rather than borrowing this name for a running
product down the model points.

``reverse`` is on the record because the direction is the calculation: the
premium still to come is not the premium already taken -- and it is the
direction a lost period runs in too. A period carrying no value ends the
fold's knowledge of its own total, so the fold says so in every period it
would have carried that value into, which under ``reverse`` is the periods
toward the start rather than the end.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._semantic.operations import ACCUMULATION_OPERATIONS
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.validation import (
    RUNNING_PRODUCT_PAST_I64_RULE,
    RUNNING_SUM_PAST_I64_RULE,
    WIDE_RUNNING_PRODUCT_RULE,
    WIDE_RUNNING_SUM_RULE,
)
from gaspatchio.frame.lowering.polars import (
    lower_arg_read_as_i64,
    register_lowering,
    whole_numbers_folded_exactly,
)

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call
    from gaspatchio.frame.lowering.context import LoweringContext


def _lower_accumulation(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Fold each policy's periods with its declared operation and direction.

    A period carrying no value ends the fold's knowledge of its own total,
    and it is not a period carrying nought: the fold answers null at that
    period and at every period after it, counting "after" in the direction
    the fold runs. The same null indicator, cumulated the same way round, is
    the mask -- a position whose running count of lost periods is above
    nought has lost one.

    A run wider than ``i64`` is folded as the ``Int64`` its values fit, and
    refused by name where one does not: in its own width a ``UInt64`` running
    sum of ``[2**63, 2**63, 1]`` answered ``[2**63, 0, 1]`` (section 10). A
    run of whole numbers is folded exactly, and a period whose running sum
    or product is past ``i64`` is refused by name rather than wrapped:
    ``[2**63 - 1, 1].cum_sum()`` answered ``[2**63 - 1, -2**63]``.
    """
    reverse = bool(dict(node.attrs)["reverse"])
    is_sum = node.name == "cum_sum"
    rule = WIDE_RUNNING_SUM_RULE if is_sum else WIDE_RUNNING_PRODUCT_RULE
    value_expr, shape = lower_arg_read_as_i64(node.args[0], ctx, rule=rule)
    kinds.refuse_a_fold_over_one_value(node.name, node.args[0], shape)
    kinds.refuse_unless_a_number(
        line=f"{node.name}()",
        operand=node.args[0],
        dtype=kinds.operand_dtype(node.args[0], value_expr, ctx),
        decimal=not is_sum,
        duration=not is_sum,
    )
    fold = getattr(pl.element(), node.name)
    lost_a_period = pl.element().is_null().cum_sum(reverse=reverse) > 0
    folded = pl.when(lost_a_period).then(None).otherwise(fold(reverse=reverse))
    exact = whole_numbers_folded_exactly(
        value_expr,
        node.args[0],
        ctx,
        lambda run: run.list.eval(folded),
        per_period=True,
        rule=RUNNING_SUM_PAST_I64_RULE if is_sum else RUNNING_PRODUCT_PAST_I64_RULE,
        product=not is_sum,
    )
    return value_expr.list.eval(folded) if exact is None else exact


for _operation in ACCUMULATION_OPERATIONS:
    register_lowering(_operation.identifier)(_lower_accumulation)
