# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowering for the bound: a value held between a floor and a cap.

``af.duration.clip(0, 14)`` is the line an actuary writes when a select
table runs out of durations and every later one reads the ultimate row.
The operation is one value at a time -- each period's own duration held
against the same two bounds -- and the three ways it reaches Polars are
the three shapes a projection puts it in.

A per-policy value clips with Polars' own ``clip``. A per-period one has
to clip inside each row's list, and which way it does that depends on the
bounds: bounds that are values run inside ``list.eval``, where a named
column cannot be reached at all; bounds that read a column go to the
``list_clip`` kernel, which takes the three columns side by side. That
split is not a preference between two ways of writing one thing -- it is
the only pair of forms Polars offers, and the rule picks between them on
the one fact that decides it.

The two forms answer alike, which is what makes the split safe to make
on a fact about the bounds rather than about the formula. They did not
always: on bounds that cross the kernel answered the upper bound
everywhere where Polars' own ``clip`` tests the lower bound first, so
one line meant two things depending on where its floor came from. The
kernel keeps Polars' rule now, and 11.1.3 of the artifact format states
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from gaspatchio._semantic.ir import Col, col_refs
from gaspatchio._semantic.operations import CLIP_OPERATION
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.once import read_once
from gaspatchio.frame.lowering._polars.validation import (
    CLIP_PAST_2_53_RULE,
    require_valid_rows,
    tagged_refusal,
)
from gaspatchio.frame.lowering.polars import lower_arg, register_lowering

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import Call, OpNode
    from gaspatchio.frame.lowering.context import LoweringContext

# What the missing side of a one-sided bound is: the bound that excludes
# nothing. Polars' own ``clip`` takes ``None`` for an absent bound, and the
# kernel takes an infinity, so each branch spells its own.
_NO_BOUND: dict[str, float] = {"lower": float("-inf"), "upper": float("inf")}

# The largest whole number every smaller one of which a double holds exactly.
_DOUBLE_EXACT = 2.0**53


def _bounds(node: Call) -> tuple[OpNode | None, OpNode | None]:
    """Return the lower and upper operands of a clip, either possibly absent.

    ``bounds`` says which of the two the operands after the value are, so
    a one-sided clip is read the right way round rather than by counting.
    """
    given = dict(node.attrs)["bounds"]
    _, *rest = node.args
    if given == "both":
        return rest[0], rest[1]
    if given == "lower":
        return rest[0], None
    return None, rest[0]


def _refuse_a_bound_of_another_kind(  # noqa: PLR0913 -- the clip, its value, and one bound as written and as lowered
    *,
    node: Call,
    value_expr: pl.Expr,
    side: str,
    bound: OpNode,
    bound_expr: pl.Expr,
    ctx: LoweringContext | None,
) -> None:
    """Refuse a bound that would be converted into the value's own type.

    Polars' ``clip`` casts its bounds into the type of the value it holds,
    so whole numbers held between 0.5 and 1.5 were held between 0 and 1: a
    policy at 2 came back as 1, against the 1.5 the line wrote. The second
    engine refuses the mixed form and 11.1.3 states no answer for it, so a
    bound of another kind, or a decimal bound on whole numbers, is refused
    here, naming the bound to write.
    """
    receiver = kinds.operand_dtype(node.args[0], value_expr, ctx)
    written = kinds.operand_dtype(bound, bound_expr, ctx)
    if (
        receiver is None
        or written is None
        or not kinds.apart(receiver, written, keeps_receiver_type=True)
    ):
        return
    raise kinds.refusal(
        line="clip()",
        role=f"{side} bound",
        operand=bound,
        fill=written,
        beside="the value it holds",
        receiver=receiver,
        move=(
            f"Write the bound as {kinds.describe(receiver)}; if the value is "
            "meant to be held at a fraction, make it a decimal first with "
            ".to_float() and clip that."
            if kinds.kind_of(written) == kinds.kind_of(receiver)
            else f"Write the bound as {kinds.describe(receiver)}, the value's kind."
        ),
        keeps_receiver_type=True,
    )


@register_lowering(CLIP_OPERATION.identifier)
def _lower_clip(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Hold every value between the bounds the call carries.

    A value below the lower bound becomes the lower bound, one above the
    upper becomes the upper, and one already between them is unchanged.
    Nulls stay null. An absent bound excludes nothing on that side.
    """
    lower, upper = _bounds(node)
    value_expr, value_shape = lower_arg(node.args[0], ctx)
    lowered = {
        side: None if bound is None else lower_arg(bound, ctx)
        for side, bound in (("lower", lower), ("upper", upper))
    }
    lower_expr = None if lowered["lower"] is None else lowered["lower"][0]
    upper_expr = None if lowered["upper"] is None else lowered["upper"][0]
    for side, bound, bound_expr in (
        ("lower", lower, lower_expr),
        ("upper", upper, upper_expr),
    ):
        if bound is not None and bound_expr is not None:
            _refuse_a_bound_of_another_kind(
                node=node,
                value_expr=value_expr,
                side=side,
                bound=bound,
                bound_expr=bound_expr,
                ctx=ctx,
            )

    if value_shape != "list":
        return value_expr.clip(lower_expr, upper_expr)

    reads_a_column = any(
        col_refs(bound) for bound in (lower, upper) if bound is not None
    )
    if not reads_a_column:
        return value_expr.list.eval(pl.element().clip(lower_expr, upper_expr))

    from gaspatchio.frame.lowering._polars.plugins import list_clip  # noqa: PLC0415

    def clipped_by(
        value: pl.Expr, low: pl.Expr | None, high: pl.Expr | None
    ) -> pl.Expr:
        return list_clip(
            value,
            pl.lit(_NO_BOUND["lower"]) if low is None else low,
            pl.lit(_NO_BOUND["upper"]) if high is None else high,
        )

    dtype = None if ctx is None else ctx.dtype_of_expr(value_expr)
    if not isinstance(dtype, pl.List):
        return clipped_by(value_expr, lower_expr, upper_expr)
    element = dtype.inner
    if not isinstance(element, pl.DataType) or not element.is_integer():
        return clipped_by(value_expr, lower_expr, upper_expr)
    present = [(side, one) for side, one in lowered.items() if one is not None]

    def answer(value: pl.Expr, *held: pl.Expr) -> pl.Expr:
        bound = dict(zip((side for side, _ in present), held, strict=True))
        clipped = clipped_by(value, bound.get("lower"), bound.get("upper"))
        bounds = [
            (field, one[1] == "list")
            for field, (_, one) in zip(held, present, strict=True)
        ]
        return _whole_numbers_as_they_were(node, clipped, dtype, value, bounds)

    # The value and each bound are read three times or more; held once, a
    # nested clip's plan grows with the lines written (audit D1-H1's class).
    return read_once(
        value_expr, *(one[0] for _, one in present), answer=answer, as_written=True
    )


def _magnitude(operand: pl.Expr, *, per_period: bool) -> pl.Expr:
    """Return the largest magnitude one operand of a clip holds, as a double."""
    if not per_period:
        return operand.cast(pl.Float64).abs()
    return pl.max_horizontal(
        operand.list.max().cast(pl.Float64).abs(),
        operand.list.min().cast(pl.Float64).abs(),
    )


def _whole_numbers_as_they_were(
    node: Call,
    clipped: pl.Expr,
    dtype: pl.DataType,
    value_expr: pl.Expr,
    bounds: list[tuple[pl.Expr, bool]],
) -> pl.Expr:
    """Answer a per-period clip of whole numbers in the value's own type.

    The kernel a bound read from a column takes holds the value in doubles
    and answered ``list[f64]`` -- ``af.duration.clip(upper_bound=af.cap)``
    over whole numbers came back ``[0.0, 5.0, 10.0]`` -- where a literal
    bound and a per-policy value keep the whole numbers. A clip answers
    the value, or one of the bounds, so where every one of them is below
    ``2**53`` the double is the whole number exactly and is read back as
    one. A policy holding a larger one would be compared and answered by
    its nearest double, so it is refused by name rather than answered so.
    """
    magnitudes = [_magnitude(value_expr, per_period=True)] + [
        _magnitude(bound, per_period=per_period) for bound, per_period in bounds
    ]
    # Strictly below: a double reads 2**53 + 1 as 2**53 itself.
    held = pl.max_horizontal(magnitudes).fill_null(0.0) < _DOUBLE_EXACT
    fits = value_expr.is_null() | held
    column = node.args[0].name if isinstance(node.args[0], Col) else None
    refused = require_valid_rows(
        fits, message=tagged_refusal(CLIP_PAST_2_53_RULE, column)
    )
    return pl.when(refused == 0).then(clipped.cast(dtype, strict=False))
