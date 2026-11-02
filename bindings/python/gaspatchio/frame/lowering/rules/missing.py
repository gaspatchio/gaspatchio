# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the six tests of a value that is not there, and the two fills.

A model point arrives with no smoker status; a lookup answers a key its
base does not carry; a discount factor divides by something that turned
out to be zero. ``af.rate.is_null()``, ``af.factor.is_finite()`` and
``af.rate.fill_null(0.0)`` are the lines an actuary writes about it, and
each was an engine fragment until now. ``fill_nan`` is the fill for the
other absence: it replaces a NaN and leaves a null where it is.

**Null and NaN are two different absences and the vocabulary keeps them
apart.** A null is a value that was never there -- an empty cell in the
extract, a lookup that missed. A NaN is a value an arithmetic produced and
cannot name: zero over zero, the logarithm of a negative rate. ``is_null``
answers the first, ``is_nan`` the second, and a model that tests one where
it meant the other passes every row it has data for.

**The negations are their own operations, not ``not_`` over the
affirmatives.** ``not_(is_nan(x))`` would be two fewer identifiers to
carry, and on a per-policy column it answers identically. On a per-period
one it does not: ``not_`` has no element-wise ``~`` that reaches inside a
``list``, so the ``not_`` lowering in ``predicates.py`` negates it
arithmetically as ``1.0 - <the 0/1 mask>``, and the subtraction is what
makes the answer ``List(Float64)`` where ``is_not_nan`` hands back
``List(Boolean)``. Composing would therefore change the type of a
per-period predicate to buy a shorter table, which is a numbers-move to
save a maintenance cost. The lineage argument points the same way and is
the one that would decide it on its own: an actuary who wrote
``is_not_null`` should read ``is_not_null`` back off the artifact, on a
framework whose claim is that the trace matches the code.

That type change is what a *producer* would record if it rewrote one
identifier as the other, and it is not what a model author meets. ``~`` on
the proxy an absence test hands back is Polars' own ``~``, never
``Call("not_")``, and over a per-period column Polars raises
``InvalidOperationError: dtype List(Boolean) not supported in 'not'
operation``. Two facts, then, not one: an author cannot write the
composition at all, and a producer that records it changes the type of the
answer. Either would carry the decision to keep six identifiers rather
than four.

**A fill is an operand, never an attribute**, because what fills a gap is
as often a column as a number -- a scheme's own default premium, last
quarter's rate. An attribute is one flat typed value (section 12.1) and
could hold neither, so a vocabulary that put the fill there would record
the constant fills and silently drop every varying one, which is the worst
outcome available: a document that reads as a complete account of a
calculation it has lost half of.

**A fill is the receiver's kind.** Polars makes a fill fit by finding a type
both sides can be written in, so ``af.rate.fill_null("n/a")`` over decimals
answered text, ``['1.0', 'n/a']``. A fill of another kind -- text into
numbers, a number into text or dates -- is refused at the line instead
(:mod:`gaspatchio.frame.lowering.kinds`), and a whole number beside a
decimal stays the declared widening it is (11.1.13). ``fill_nan``'s fill is
a whole number or a decimal, the domain 11.1.13 states, so a flag is
refused there too.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._semantic.ir import Call, WhenThen, col_refs
from gaspatchio._semantic.operations import (
    ABSENCE_PREDICATE_OPERATIONS,
    FILL_NAN_OPERATION,
    FILL_NULL_OPERATION,
)
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering.polars import (
    lower_arg,
    register_elementwise,
    register_lowering,
)

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.frame.lowering.context import LoweringContext

for _operation in ABSENCE_PREDICATE_OPERATIONS:
    register_elementwise(_operation.identifier)

# What may stand in for a NaN: a whole number or a decimal (11.1.13). A flag
# is a number to this framework, and still not a value a NaN is filled with.
_NAN_FILLS = frozenset({1, 2})


def _refuse_a_fill_of_another_kind(  # noqa: PLR0913 -- the value and the fill, each as written and as lowered
    *,
    line: str,
    value: OpNode,
    value_expr: pl.Expr,
    fill: OpNode,
    fill_expr: pl.Expr,
    ctx: LoweringContext | None,
    numbers: frozenset[int] | None = None,
) -> None:
    """Refuse a fill that would convert the column it fills, naming the move.

    The move depends on which way the conversion ran. Text written into a
    column of numbers or dates is most often a label meant for a report,
    and the column says so first with ``to_text()``; anything else written
    into a column is written as what the column holds.
    """
    receiver = kinds.operand_dtype(value, value_expr, ctx)
    if numbers is not None:
        _refuse_a_nan_fill_where_no_nan_can_be(value, receiver)
    filled = kinds.operand_dtype(fill, fill_expr, ctx)
    if receiver is None or filled is None:
        return
    if numbers is None and _a_number_filling_a_flag(receiver, filled):
        raise kinds.refusal(
            line=line,
            role="fill",
            operand=fill,
            fill=filled,
            beside="the value it fills",
            receiver=receiver,
            move=(
                "Fill with True or False; if a number is meant where the flag "
                "is missing, write the conditional, whose branches may be a "
                f"flag and a number: when({kinds.written(value)}.is_null())"
                f".then(0.0).otherwise({kinds.written(value)})."
            ),
        )
    if not kinds.apart(receiver, filled, numbers=numbers):
        return
    if kinds.kind_of(filled) == "text" and line == "fill_null()":
        move = (
            f"Fill with {kinds.describe(receiver)}; if the column is meant to "
            "hold text, say so first and fill that: "
            "af.x.to_text().fill_null('n/a')."
        )
    elif kinds.kind_of(filled) == "text":
        move = (
            "Fill with a number; if a label is meant where the value is NaN, "
            "write the conditional with both branches text: "
            "when(af.x.is_nan()).then('n/a').otherwise(af.x.to_text())."
        )
    else:
        move = f"Fill with {kinds.describe(receiver)}, the kind the column holds."
    raise kinds.refusal(
        line=line,
        role="fill",
        operand=fill,
        fill=filled,
        beside="the value it fills",
        receiver=receiver,
        move=move,
    )


def _a_number_filling_a_flag(receiver: pl.DataType, filled: pl.DataType) -> bool:
    """Return whether a whole number or a decimal fills a column of flags.

    A flag is a number to this framework, so ``af.rate.fill_null(False)``
    is the 0.0 it always was. The other way round there is no type the
    pair shares that is still a flag: Polars refused ``fill_null(0.0)``
    over flags with its own dtype error, and answered ``fill_null(0)`` by
    turning every flag into a 32-bit whole number.
    """
    return (
        kinds.is_flag(receiver)
        and kinds.kind_of(filled) == "number"
        and not kinds.is_flag(filled)
    )


def _refuse_a_nan_fill_where_no_nan_can_be(
    value: OpNode, receiver: pl.DataType | None
) -> None:
    """Refuse ``fill_nan`` over a value that cannot hold a NaN, at the line.

    11.1.13 answers it over decimals and whole numbers and states no answer
    over a flag, text or a date: none of them holds a NaN, and the engine
    has no NaN test over any of them. That refusal reached the author only
    when the frame ran, as Polars' ``is_not_nan ... not supported for
    dtype``; it is made here, naming the value's kind.
    """
    if receiver is None or kinds.can_hold_nan(receiver) is not False:
        return
    column = kinds.written(value)
    msg = (
        f"fill_nan(): the value it fills -- {kinds.shown(value)} -- is "
        f"{kinds.describe(receiver)}, which never holds a NaN, so there is "
        "nothing for fill_nan() to replace and the line is refused. A value "
        f"that is missing is a null, and its fill is {column}.fill_null(...)."
    )
    raise TypeError(msg)


def _refuse_a_run_filling_one_value(
    *, line: str, value: OpNode, fill: OpNode, value_shape: str, fill_shape: str
) -> None:
    """Refuse a per-period fill for a per-policy value, at the line.

    The answer keeps the value's shape (11.1.13), and a run of periods
    filling one number would answer a list for it, which is outside the
    entry; Polars refused the pair when the frame ran, in its own words
    (``failed to determine supertype of f64 and list[f64]``).
    """
    if value_shape == "list" or fill_shape != "list":
        return
    msg = (
        f"{line}: the value it fills -- {kinds.shown(value)} -- holds one "
        f"value per policy, and the fill -- {kinds.shown(fill)} -- one per "
        "period, so the fill would answer a run of periods for one number "
        "and the line is refused. Fill each period of a per-period value, or "
        "pick the one period that fills it -- "
        f"{kinds.written(fill)}.list.get(0), say."
    )
    raise TypeError(msg)


@register_lowering(FILL_NULL_OPERATION.identifier)
def _lower_fill_null(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Put the fill where the value is missing, on the shape it is missing in.

    Per-policy, the engine's own ``fill_null`` answers it -- and this is
    where a fill that reads a column is the ordinary case: a rate missing
    for a scheme takes that scheme's own default premium, one value per
    policy beside one value per policy.

    Per-period, each period is filled one value at a time (11.1.13). A fill
    that is a *value* runs inside each row's list and replaces the missing
    periods. A fill that reads a *column* cannot be reached inside
    ``list.eval`` at all, so the line lowers as the conditional it means,
    ``when(is_null(value)).then(fill).otherwise(value)``, as ``fill_nan``'s
    does: a per-policy fill -- the scheme's own default premium -- reaches
    every missing period of its policy, and a per-period fill the same
    period. A policy with no run at all stays null, as it does under a
    fill that is a value.

    The row form Polars' own ``fill_null`` takes there filled the wrong
    thing: a per-period column's run replaced a policy whose whole run was
    missing and left a gap inside a run that was otherwise present, and a
    per-policy column failed in Polars' words (``SchemaError: failed to
    determine supertype of list[f64] and f64``).
    """
    value_expr, shape = lower_arg(node.args[0], ctx)
    fill = node.args[1]
    fill_expr, fill_shape = lower_arg(fill, ctx)
    _refuse_a_run_filling_one_value(
        line="fill_null()",
        value=node.args[0],
        fill=fill,
        value_shape=shape,
        fill_shape=fill_shape,
    )
    _refuse_a_fill_of_another_kind(
        line="fill_null()",
        value=node.args[0],
        value_expr=value_expr,
        fill=fill,
        fill_expr=fill_expr,
        ctx=ctx,
    )
    if shape != "list":
        return value_expr.fill_null(fill_expr)
    if not col_refs(fill):
        return value_expr.list.eval(pl.element().fill_null(fill_expr))
    value = node.args[0]
    conditional, _ = lower_arg(WhenThen(Call("is_null", (value,)), fill, value), ctx)
    return conditional


@register_lowering(FILL_NAN_OPERATION.identifier)
def _lower_fill_nan(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Put the fill where the value is NaN, and leave a null where it is.

    Per-policy, the engine's own ``fill_nan`` answers it, with a fill that
    is a value or a column alike. Per-period with a fill that is a *value*,
    the same method runs inside each row's list.

    Per-period with a fill that reads a *column*, ``list.eval`` cannot see
    the column, and unlike ``fill_null`` there is no row form to fall back
    on: a NaN is a period's value, never a whole run's. So the line lowers
    as the conditional it means, ``when(is_nan(value)).then(fill)
    .otherwise(value)``, which the conditional's own rule runs period for
    period -- a per-policy fill reaching every NaN period of its policy, a
    per-period fill reaching the same period. ``is_nan`` answers null for a
    null and a null condition takes the otherwise branch, so a null stays
    null on this route as on the other two.
    """
    value, fill = node.args
    value_expr, shape = lower_arg(value, ctx)
    fill_expr, fill_shape = lower_arg(fill, ctx)
    _refuse_a_run_filling_one_value(
        line="fill_nan()",
        value=value,
        fill=fill,
        value_shape=shape,
        fill_shape=fill_shape,
    )
    _refuse_a_fill_of_another_kind(
        line="fill_nan()",
        value=value,
        value_expr=value_expr,
        fill=fill,
        fill_expr=fill_expr,
        ctx=ctx,
        numbers=_NAN_FILLS,
    )
    if shape != "list":
        return value_expr.fill_nan(fill_expr)
    if not col_refs(fill):
        return value_expr.list.eval(pl.element().fill_nan(fill_expr))
    conditional, _ = lower_arg(WhenThen(Call("is_nan", (value,)), fill, value), ctx)
    return conditional
