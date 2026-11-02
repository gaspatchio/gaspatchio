# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Lowerings for the three ways a model sorts values into named groups.

``is_in`` asks whether each value is one of a set the formula names.
``cut`` places each value in one of the intervals a set of breakpoints
divides the line into. ``replace`` substitutes one value for another, one
for one. All three are banding: an age band, a set of product codes that
share a basis, a table's own spelling of a rider mapped onto the model's.

What identifies each of them is the values written into it -- the
breakpoints, the labels, the membership set, the substitution's two sides
-- and those travel as sequence literals in the tree rather than as
configuration, so the tree holds them rather than the engine's abbreviated
display of them. A rule below reads them straight off the literal, because
what Polars is handed is the sequence itself: a band's breakpoints are an
argument to the operation, not a column beside it.

**All three answer one value at a time, on a projection as well as on a
model point.** Sections 11.1.4, 11.1.5 and 11.1.6 each say so in the same
words -- *each value* takes its interval, is or is not a member, keeps
itself or takes its replacement -- and until a rule here read the shape
its operand resolved to, none of them did. Handed a per-period column,
Polars' own column-level ``is_in`` answered one Boolean for the whole
policy and its ``replace`` matched nothing and returned the periods
unchanged, both under a node recorded as the operation rather than as an
engine fragment: the file asserted a portable calculation whose answer was
wrong. Polars says the same thing about the first of them itself, raising
``DeprecationWarning: 'is_in' with a collection of the same datatype is
ambiguous`` on exactly the call that produced the single Boolean. Each
rule now runs the engine's method inside each row's list where the value
is per-period, which is the operation the format already describes, and
reaches Polars' column-level method only where the column is per-policy.

**One shape has no per-element form and is refused rather than answered.**
A membership set that arrives as a column cannot be reached from inside
``list.eval`` -- nothing there can see another column -- so a per-period
value tested against one has no per-element route at all. That case
refuses at the line, rather than falling back to the column-level call
whose answer is the wrong-shaped one this module just stopped giving.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio._semantic.ir import Lit
from gaspatchio._semantic.operations import (
    CUT_OPERATION,
    IS_IN_OPERATION,
    REPLACE_OPERATION,
)
from gaspatchio.frame.lowering import kinds
from gaspatchio.frame.lowering._polars.validation import WIDE_BAND_RULE
from gaspatchio.frame.lowering.polars import (
    LoweringError,
    lower_arg,
    lower_arg_read_as_i64,
    register_lowering,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio._semantic.ir import Call, OpNode
    from gaspatchio.frame.lowering.context import LoweringContext

# How many operands a ``cut`` carries before the labels: the value and the
# breakpoints. A third is the labels, and its absence means the intervals
# name themselves.
_CUT_LABELS_AT = 2


def _sequence(node: OpNode) -> list[Any] | None:
    """Return the sequence a literal holds, or ``None`` if it is not one.

    Polars takes a band's breakpoints and a substitution's two sides as the
    sequences they are, so the rule reads the values off the literal rather
    than lowering it to an expression over them.
    """
    if isinstance(node, Lit) and isinstance(node.value, tuple):
        return list(node.value)
    return None


def _written(node: Call, operand: OpNode, what: str) -> list[Any]:
    """Return an operand's sequence, refusing loudly if it is not one.

    Unreachable through the recording door, which mints one of these calls
    only where the sequence was written out. Reachable through a file: an
    artifact carrying a ``cut`` whose breakpoints are a column reference is
    a document this vocabulary does not describe, and saying so beats
    computing a band out of whatever the reference resolved to.
    """
    values = _sequence(operand)
    if values is None:
        reason = (
            f"{what} has to be a sequence of values written into the "
            "formula -- it is half of what identifies a banding, and a "
            "band assembled from a column is not this operation. Record "
            "the values, or record the calculation as engine-native."
        )
        raise LoweringError(node, reason)
    return values


def _flag(node: Call, name: str) -> bool:
    """Return one of a call's boolean attributes."""
    return bool(dict(node.attrs)[name])


def _refuse_members_of_another_kind(
    value: OpNode,
    value_expr: pl.Expr,
    members: OpNode,
    written: list[Any] | None,
    ctx: LoweringContext | None,
) -> None:
    """Refuse a membership set whose members are another kind than the value.

    Membership is equality (11.1.5), and equality between two kinds is no
    comparison 11.1.26 states: ``af.d.is_in([1, 2])`` over dates, or
    ``af.x.is_in(["a"])`` over decimals, was refused only when the frame ran,
    in Polars' own words. A whole number beside a decimal is one kind, as
    it is for the six comparisons. A flag beside a number is too, but Polars
    has no membership test between them, so that pair is refused here with
    the move rather than at ``collect()``.
    """
    held = kinds.operand_dtype(value, value_expr, ctx)
    if held is None or kinds.kind_of(held) is None:
        return
    candidates: list[tuple[OpNode | str, pl.DataType | None]]
    if written is None:
        members_expr, _ = lower_arg(members, ctx)
        candidates = [(members, kinds.operand_dtype(members, members_expr, ctx))]
    else:
        candidates = [(repr(v), kinds.literal_dtype(v)) for v in written]
    for shown, member in candidates:
        if member is None or kinds.kind_of(member) is None:
            continue
        if not kinds.apart(held, member) and kinds.is_flag(held) == kinds.is_flag(
            member
        ):
            continue
        raise kinds.refusal(
            line="is_in()",
            role="member",
            operand=shown,
            fill=member,
            beside="the value it tests",
            receiver=held,
            move=_members_move(value, held),
        )


def _members_move(value: OpNode, held: pl.DataType) -> str:
    """Return the move for members of another kind, by the value's own kind."""
    if kinds.kind_of(held) in {"date", "datetime"}:
        column = kinds.written(value)
        return (
            "A set of dates is not written as members; test them with "
            f"comparisons instead: ({column} == date(2025, 6, 1)) | "
            f"({column} == date(2026, 6, 1))."
        )
    if kinds.is_flag(held):
        return "Write each member as True or False, the kind the column holds."
    if kinds.kind_of(held) == "number":
        return (
            "Write each member as a number, the kind the column holds; if the "
            "members are codes, test the column as text: "
            f"{kinds.written(value)}.to_text().is_in([...])."
        )
    return f"Write each member as {kinds.describe(held)}, the kind the column holds."


@register_lowering(IS_IN_OPERATION.identifier)
def _lower_is_in(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Test each value for membership of the set the second operand names.

    Per-period, the test runs inside each row's list and answers one
    Boolean per period, which is what 11.1.5 describes. Polars' own
    column-level ``is_in`` over a ``list`` column asks a different
    question -- whether the whole run of periods is a member -- and
    answers one Boolean for the policy, which is neither this operation
    nor an answer a projection has any use for.

    A set that arrives as a column has no per-element form: ``list.eval``
    sees the element and nothing else on the frame. That combination is
    refused here rather than sent to the column-level call, because the
    column-level call is the wrong-shaped answer above.

    The refusal is a ``ValueError`` and not a ``LoweringError``, for the
    same reason the two refusals in ``methods.py`` are: it is about the
    argument the author wrote, not about a node nothing can lower. The
    node has a lowering; what it has no form for is this operand on this
    shape, and the author is the one who can change that.
    """
    value_expr, shape = lower_arg(node.args[0], ctx)
    members = node.args[1]
    nulls_equal = _flag(node, "nulls_equal")
    written = _sequence(members)
    _refuse_members_of_another_kind(node.args[0], value_expr, members, written, ctx)
    value_expr = _a_band_read_as_its_text(node.args[0], value_expr, shape, ctx)
    if shape == "list":
        if written is None:
            msg = (
                "A per-period value can only be tested against a set "
                "written into the formula. The membership set here is a "
                "column, and nothing inside a projection's periods can "
                "read one -- so there is no per-period answer to give, "
                "and the whole-column answer is one Boolean for the "
                "policy rather than one per period. Write the members "
                "out, or test the per-policy value instead."
            )
            raise ValueError(msg)
        return value_expr.list.eval(
            pl.element().is_in(written, nulls_equal=nulls_equal)
        )
    if written is not None:
        return value_expr.is_in(written, nulls_equal=nulls_equal)
    members_expr, _ = lower_arg(members, ctx)
    answer = value_expr.is_in(members_expr, nulls_equal=nulls_equal)
    held = kinds.operand_dtype(node.args[0], value_expr, ctx)
    if held is None or not held.is_float():
        return answer
    # A NaN equals no member under IEEE equality (11.1.26), a NaN among the
    # members included; Polars hashes one NaN equal to another and answered
    # true for a NaN in a set read from a column that held one. A literal
    # set cannot hold a NaN, so only this path meets it.
    return pl.when(value_expr.is_nan()).then(pl.lit(value=False)).otherwise(answer)


@register_lowering(CUT_OPERATION.identifier)
def _lower_cut(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Place each value in the interval the breakpoints put it in.

    Both operands are sequences written into the formula, so the
    per-period form needs nothing the element cannot see and every band
    reaches its own periods.

    A value is placed by comparing it with breakpoints that are decimals, so
    a whole number wider than ``i64`` is read as the ``Int64`` it fits, on
    either door, and a value past ``i64`` is refused by name (section 10).
    Inside ``i64`` the comparison is the mixed whole-number/decimal one of
    section 11.1.26, stated only for values within ``2**53``: past that a
    whole number is compared with a breakpoint as its nearest double, so
    ``2**53 + 1`` is placed at or below a breakpoint of ``2**53``.
    """
    value_expr, shape = lower_arg_read_as_i64(node.args[0], ctx, rule=WIDE_BAND_RULE)
    breaks = _written(node, node.args[1], "a band's breakpoints")
    labels = (
        _written(node, node.args[_CUT_LABELS_AT], "a band's labels")
        if len(node.args) > _CUT_LABELS_AT
        else None
    )
    left_closed = _flag(node, "left_closed")
    include_breaks = _flag(node, "include_breaks")
    if shape == "list":
        return value_expr.list.eval(
            pl.element().cut(
                breaks,
                labels=labels,
                left_closed=left_closed,
                include_breaks=include_breaks,
            )
        )
    return value_expr.cut(
        breaks,
        labels=labels,
        left_closed=left_closed,
        include_breaks=include_breaks,
    )


@register_lowering(REPLACE_OPERATION.identifier)
def _lower_replace(node: Call, ctx: LoweringContext | None) -> pl.Expr:
    """Substitute the new value for the old, one for one, elsewhere unchanged.

    Both sides of the substitution are written into the formula, so the
    per-period form reaches every period. Polars' column-level
    ``replace`` over a ``list`` column matches none of them and hands the
    run of periods back untouched, which is a substitution that silently
    substitutes nothing.
    """
    value_expr, shape = lower_arg(node.args[0], ctx)
    old = _written(node, node.args[1], "the values a substitution replaces")
    replacement = node.args[2]
    written = _sequence(replacement)
    if written is not None:
        new: Any = written
    elif isinstance(replacement, Lit):
        new = replacement.value
    else:
        reason = (
            "a substitution's replacements have to be values written into "
            "the formula -- either one for each of the values replaced, or "
            "a single one standing for all of them. Record them, or record "
            "the calculation as engine-native."
        )
        raise LoweringError(node, reason)
    _refuse_a_substitution_of_another_kind(node, value_expr, old, new, ctx)
    value_expr = _a_band_read_as_its_text(node.args[0], value_expr, shape, ctx)
    if shape == "list":
        return value_expr.list.eval(pl.element().replace(old, new))
    return value_expr.replace(old, new)


def _a_band_read_as_its_text(
    value: OpNode, value_expr: pl.Expr, shape: str, ctx: LoweringContext | None
) -> pl.Expr:
    """Return a band (an ``Enum``) read as its text, anything else as it was.

    A band is an ordered category the record has no name for, so it is
    read where it enters a membership test or a substitution as the kind it
    denotes, its text (spec 11.1.26). Polars cast a member or a value
    replaced into the band's categories first and stopped the run in its
    own words where one was not among them (``conversion from str to enum
    failed for value "Zeta"``); read as text, a label outside the
    categories is simply not a member, and is replaced nowhere.
    """
    dtype = kinds.operand_dtype(value, value_expr, ctx)
    element = dtype.inner if isinstance(dtype, pl.List) else dtype
    if not isinstance(element, pl.Enum):
        return value_expr
    if shape == "list":
        return value_expr.list.eval(pl.element().cast(pl.String))
    return value_expr.cast(pl.String)


def _refuse_a_substitution_of_another_kind(
    node: Call,
    value_expr: pl.Expr,
    old: Sequence[object],
    new: object,
    ctx: LoweringContext | None,
) -> None:
    """Refuse a substitution that would convert the values it is written over.

    ``replace`` keeps the column's own type, so Polars casts what it was
    handed into it: ``{2.5: 9}`` over whole numbers matched the policy
    holding 2, ``{2: 2.5}`` stored 2, ``{"a": 1.0}`` over codes stored the
    text ``'1.0'``, and ``{"2": 5}`` over whole numbers matched 2. Each is a
    conversion nobody wrote, so a value replaced or a replacement of another
    kind, or a wider number than the column holds, is refused naming it.
    """
    receiver = kinds.operand_dtype(node.args[0], value_expr, ctx)
    if receiver is None:
        return
    replacements = list(new) if isinstance(new, tuple | list) else [new]
    for role, values in (("value replaced", old), ("replacement", replacements)):
        for value in values:
            written = kinds.literal_dtype(value)
            if written is None or not kinds.apart(
                receiver, written, keeps_receiver_type=True
            ):
                continue
            raise kinds.refusal(
                line="replace()",
                role=role,
                operand=repr(value),
                fill=written,
                beside="the column it substitutes in",
                receiver=receiver,
                move=(
                    f"Write each value as {kinds.describe(receiver)}, the "
                    "kind the column holds; to substitute into another kind, "
                    "convert the column first (.to_text(), .to_float())."
                ),
                keeps_receiver_type=True,
            )
