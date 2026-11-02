# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the four folds that reduce a projection's periods to one number.

``(af.claims * af.disc_factors).list.sum()`` is the present value of a whole
discounted cashflow -- the plainest closed form in an actuarial model, and the
line a supervisory reader asks for by name. Beside it sit the average, the
least and the greatest of a policy's own periods.

**These fold along the period axis and along nothing else.** The operand is
one policy's own sequence of periods, and no value of one policy reaches
another's answer. An engine's method of the same name applied to a per-policy
column folds down the rows of the model-point file instead -- a different
calculation, whose answer depends on the order those rows happen to stand in,
and one the vocabulary does not name. The recogniser's door asks the receiver's
shape and declines that case, exactly as it declines a per-policy ``cum_sum``.

**They are the vocabulary's first operations whose answer has a different
shape from their operand**, taking a list and answering a scalar. Nothing here
records that: a node already states the shape of its own answer and its
operand's node states the operand's, so a third statement would be free to
disagree with the two that exist. Section 11.1.14 states it in prose, per
entry, beside the operation it is a fact about.

**A null period makes the total null.** A total is the one number a reviewer
signs, and nothing in one number can say a period went missing underneath it
-- so the four answer null wherever any period of the operand does.
``[10.0, None, 30.0, 40.0]`` answers null through all four, where it used to
answer ``sum`` 80.0, ``mean`` 26.666666666666668, ``min`` 10.0 and ``max``
40.0, each of them the answer ``[10.0, 30.0, 40.0]`` gives. A run of nothing
but nulls answers null for all four, so ``sum`` no longer parts company with
its siblings at nought. This is the rule the running folds already follow,
reaching the last place it was not applied: a modeller who means nought says
so with ``fill_null`` before the total, where a reviewer can read it.

A run whose periods all carry a value is untouched, and so is the empty run,
whose sum is still nought: there is no period missing from a run that has
none.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._semantic.operations import LIST_OPERATIONS
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.validation import (
    SUM_PAST_I64_RULE,
    WIDE_SUM_RULE,
)
from gaspatchio.frame.lowering.polars import (
    lower_arg,
    lower_arg_read_as_i64,
    register_lowering,
    whole_numbers_folded_exactly,
)

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call, OpNode
    from gaspatchio.frame.lowering.context import LoweringContext


def _null_if_a_period_is_missing(value_expr: pl.Expr, total_expr: pl.Expr) -> pl.Expr:
    """Answer null wherever any period of the operand carries no value.

    The test is over the whole run rather than in the fold's direction,
    because a total has no direction: every period is in the one number, so
    a period missing anywhere is a period missing from it. The indicator is
    built from the operand's own nulls inside the same expression, which
    keeps the answer's type the operand's -- an integer timeline stays
    integer on its way past.
    """
    lost_a_period = value_expr.list.eval(pl.element().is_null()).list.any()
    return pl.when(lost_a_period).then(None).otherwise(total_expr)


@register_lowering(LIST_OPERATIONS[3].identifier)
def _lower_sum(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Add every period of one policy's own timeline into one number.

    There is no ``reverse`` and no seed: a fold over the whole axis reaches
    the same number in either direction, the sum of an empty run is nought,
    and the sum of one period is that period. A null period makes the total
    null, and a run of nothing but nulls answers null with it. A run wider
    than ``i64`` is read as the ``Int64`` its values fit, and refused by
    name where one does not: summed in its own width, ``[2**63, 2**63, 1]``
    of a ``UInt64`` answered 1 (section 10). A run of whole numbers is
    summed exactly, and a total past ``i64`` is refused by name rather than
    wrapped: ``[2**63 - 1, 1]`` answered ``-2**63``.
    """
    value_expr, shape = lower_arg_read_as_i64(node.args[0], ctx, rule=WIDE_SUM_RULE)
    kinds.refuse_a_fold_over_one_value(node.name, node.args[0], shape)
    dtype = kinds.operand_dtype(node.args[0], value_expr, ctx)
    kinds.refuse_unless_a_number(line="sum()", operand=node.args[0], dtype=dtype)
    total = whole_numbers_folded_exactly(
        value_expr,
        node.args[0],
        ctx,
        lambda run: _null_if_a_period_is_missing(run, run.list.sum()),
        per_period=False,
        rule=SUM_PAST_I64_RULE,
    )
    if total is None:
        doubles = isinstance(dtype, pl.List) and dtype.inner in (pl.Float64, pl.Float32)
        total_expr = _summed(value_expr) if doubles else value_expr.list.sum()
        return _null_if_a_period_is_missing(value_expr, total_expr)
    return total


def _summed(run: pl.Expr) -> pl.Expr:
    """Return each policy's total, an empty run's being +0.0.

    Polars' list kernel starts a sum of doubles from -0.0, IEEE's additive
    identity, so the total of a policy with no periods came back -0.0 -- and
    a division by it pointed the infinity the other way from the JAX engine,
    the reader and Polars' own column sum, which all answer +0.0 (11.1.14:
    "an empty sum is +0.0"). A run with a period keeps the sum Polars gives.
    """
    return pl.when(run.list.len() == 0).then(pl.lit(0.0)).otherwise(run.list.sum())


@register_lowering(LIST_OPERATIONS[1].identifier)
def _lower_mean(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Average the periods of one policy's own timeline into one number.

    The denominator is the count of *this policy's* own periods and never the
    grid's. A per-policy timeline gives each policy its own number of periods,
    and the two denominators differ for every policy but the longest -- a
    difference a level timeline hides, which is what makes it a valuation
    error that survives testing. A null period makes the answer null: a
    period carrying no value leaves no denominator worth dividing by. A run
    of text has no average, and Polars answered null for one -- even for
    ``["1", "2"]`` -- so it is refused where the line is written; the
    average of a run of dates is a date and time, as Polars gives it.
    """
    value_expr, shape = lower_arg(node.args[0], ctx)
    kinds.refuse_a_fold_over_one_value(node.name, node.args[0], shape)
    dtype = kinds.operand_dtype(node.args[0], value_expr, ctx)
    if kinds.kind_of(dtype) == "text" and dtype is not None:
        raise kinds.not_a_number_refusal(
            line="mean()", operand=node.args[0], dtype=dtype
        )
    return _null_if_a_period_is_missing(value_expr, value_expr.list.mean())


@register_lowering(LIST_OPERATIONS[2].identifier)
def _lower_min(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Return the least of the periods of one policy's own timeline.

    A null period makes the answer null: a period carrying no value could
    have been the least of them, so a run holding one answers null rather
    than the least of what is left. A NaN period makes it NaN, wherever in
    the run it stands (:func:`_extreme`).
    """
    value_expr, shape = lower_arg(node.args[0], ctx)
    kinds.refuse_a_fold_over_one_value(node.name, node.args[0], shape)
    least = _extreme(value_expr, node.args[0], ctx, least=True)
    return _null_if_a_period_is_missing(value_expr, least)


@register_lowering(LIST_OPERATIONS[0].identifier)
def _lower_max(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Return the greatest of the periods of one policy's own timeline.

    A null period makes the answer null: a period carrying no value could
    have been the greatest of them, so a run holding one answers null rather
    than the greatest of what is left. A NaN period makes it NaN, wherever
    in the run it stands (:func:`_extreme`).
    """
    value_expr, shape = lower_arg(node.args[0], ctx)
    kinds.refuse_a_fold_over_one_value(node.name, node.args[0], shape)
    greatest = _extreme(value_expr, node.args[0], ctx, least=False)
    return _null_if_a_period_is_missing(value_expr, greatest)


def _extreme(
    value_expr: pl.Expr, operand: OpNode, ctx: LoweringContext | None, *, least: bool
) -> pl.Expr:
    """Return the least or greatest period, a NaN period answering NaN.

    Polars' ``list.min`` and ``list.max`` skip a NaN, so ``[0.0, NaN, 0.2]``
    answered 0.0 -- the 0/0 an in-the-money ratio over a zero guarantee gives
    (11.1.25) left the worst funding level as though that period were not
    there -- where the JAX engine answered NaN. A NaN is a value no period
    can be ordered against, so a run holding one has no least and no
    greatest: the fold answers NaN on every side (11.1.16, 11.1.17), as the
    folds across policies already do. A run of numbers that cannot hold a
    NaN folds as it did.
    """
    dtype = kinds.operand_dtype(operand, value_expr, ctx)
    inner = dtype.inner if isinstance(dtype, pl.List) else None
    if inner in (pl.Float64, pl.Float32):
        fold = pl.element().nan_min() if least else pl.element().nan_max()
        return value_expr.list.eval(fold).list.first()
    return value_expr.list.min() if least else value_expr.list.max()
