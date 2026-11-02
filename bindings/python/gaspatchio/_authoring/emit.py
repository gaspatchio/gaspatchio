# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What an operator dunder does now: build a node, wrap it, return.

``af.claims = af.sum_assured * af.pols_death`` used to run a shape
dispatcher inside ``__mul__`` and hand back a proxy wrapping a finished
Polars expression. It now builds ``BinOp("mul", Col("sum_assured"),
Col("pols_death"))`` and hands back a proxy wrapping *that*; the Polars
expression is derived later, once, when something actually needs it (see
``lower_polars``). The two helpers here are the whole of that change --
every arithmetic and comparison dunder on ``ColumnProxy``,
``ExpressionProxy``, and ``ConditionExpression`` is a one-line call into
one of them.

The node is built with plain dataclass construction and nothing else: no
schema is read, no dtype is probed, no expression is built. That matters
because emission is on the per-assignment hot path, and a model builds
tens of thousands of these while a projection is being written.

The proxy classes live in ``gaspatchio.column`` and are imported inside
the functions rather than at module scope -- ``column`` imports this
package while it is still initialising, so a module-level edge back would
close the cycle. Call recognition reads the semantic vocabulary and live
extension names; it does not import or load a backend's lowering rules.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from gaspatchio._dtypes import I64_MAX, I64_MIN, wider_than_i64_at
from gaspatchio._semantic.calls import is_known_call
from gaspatchio._semantic.ir import (
    BinOp,
    Call,
    Col,
    non_finite_literal_message,
)
from gaspatchio.frame.lowering.ingress import (
    IntegerLiteralPastI64Error,
    compared_against_a_wide_column,
    past_i64_setting_message,
    to_node,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    import polars as pl

    from gaspatchio._semantic.ir import AttrValue, BinOpKind, OpNode
    from gaspatchio._shape import Kind
    from gaspatchio.column.condition_expression import ConditionExpression
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame


def binary(
    op: BinOpKind,
    left: object,
    right: object,
    parent: ActuarialFrame | None,
    *,
    kind: Kind | None = None,
) -> ExpressionProxy:
    """Emit ``left op right`` as a ``BinOp`` node carried by an ``ExpressionProxy``.

    Operand order is the order the author wrote, so a reflected dunder
    passes the *other* operand as ``left``: ``1 - af.pols_if`` emits
    ``BinOp("sub", Lit(1), Col("pols_if"))``, not the mirror image.

    ``kind`` stamps the result's classification when the dtype alone would
    not reveal it -- ``&``/``|`` over list operands produce a Float64 0/1
    mask, which is a predicate, not a measurement.
    """
    from gaspatchio.column.expression_proxy import ExpressionProxy  # noqa: PLC0415

    node = BinOp(op=op, left=to_node(left), right=to_node(right))
    return ExpressionProxy._from_node(node, parent, kind=kind)  # noqa: SLF001


def call_node(
    name: str,
    args: Iterable[object],
    attrs: tuple[tuple[str, AttrValue], ...] = (),
) -> Call:
    """Build the ``Call`` node for a named operation, checking it is known.

    Every named method the framework owns -- an accessor method, a table
    lookup, a rollforward read -- emits one of these instead of building
    a Polars expression. ``args`` are the operation's *operands*, each run
    through ``to_node``; ``attrs`` are its configuration, and stay typed
    (an offset of ``-1`` is the int ``-1``, never the string ``"-1"``).

    The membership check is the point of doing this here rather than in
    the caller: an unknown name fails at the line the
    actuary wrote, naming the operation, instead of three phases later
    inside ``.collect()`` where the traceback points at the engine.

    **A non-finite configuration is refused for the same reason, and it is
    the same rule an operand already meets.** ``Lit`` rejects a NaN, which
    is what makes ``af.account_value * float("nan")`` raise where it was
    written; an attribute had no such door, so
    ``cumulative_survival(start_at=float("nan"))`` built, ran, and put a
    NaN at the head of every policy's survival curve. The rule then arrived
    anyway, at ``export()``, as ``Out of range float values are not JSON
    compliant`` -- naming neither the column nor the line, a whole model
    after the argument, and with a run in between whose numbers a reader
    would have believed. ``Call`` itself stays unvalidated so the canonical
    encoding remains total over everything ``AttrValue`` admits; this door
    is where an author's value arrives.

    **A whole number no ``i64`` holds is refused here too**, and for the
    reason an operand's is (``ingress.within_i64``): section 12.1 writes a
    whole number as an ``i64``, so ``at_period(2**64)`` built a record no
    consumer could read and answered a column of nulls.

    Raises:
        ValueError: If ``name`` is not a recognized call, or an
            attribute's value is a non-finite float.
        IntegerLiteralPastI64Error: If an attribute's value is a whole
            number outside the signed 64-bit range.

    """
    if not is_known_call(name):
        msg = (
            f"{name!r} is not a known operation: it has no registered "
            "lowering, so nothing can compute it. Check the spelling "
            "against the names registered in gaspatchio/frame/lowering/rules/."
        )
        raise ValueError(msg)
    for attribute, value in attrs:
        if isinstance(value, float) and not math.isfinite(value):
            msg = non_finite_literal_message(value, f" as {name}'s {attribute!r}")
            raise ValueError(msg)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and not I64_MIN <= value <= I64_MAX
        ):
            raise IntegerLiteralPastI64Error(
                past_i64_setting_message(value, name, attribute)
            )
    return Call(name=name, args=tuple(to_node(arg) for arg in args), attrs=attrs)


def column_args(*exprs: pl.Expr) -> tuple[Col, ...]:
    """Return the columns ``exprs`` read, as the ``Col`` args a node declares.

    Some operations are a function of a whole configuration object rather
    than of operands the author passed one at a time -- a projection
    timeline, a schedule's boundary dates or in-force mask. The
    configuration travels in ``attrs``, but the expression it produces may
    still genuinely read columns off the frame: each policy's inception
    date, its own horizon, its termination date. A node that declared no
    arguments there would tell every reader of the calculation graph that
    a projection depends on nothing.

    The declaration is read back off the expression the call actually
    lowers to, which is what stops it drifting from what runs: a rule that
    starts or stops reading a column changes this answer with it, without
    anybody having to remember two places. Names are de-duplicated, first
    occurrence first, so a boundary mask that names one column once per
    period declares it once.
    """
    seen: dict[str, None] = {}
    for expr in exprs:
        try:
            roots = expr.meta.root_names()
        except (AttributeError, RuntimeError):
            # Same best-effort contract as ``ingress.native_node``: an
            # expression that refuses to report its roots understates the
            # reads rather than having them invented for it.
            continue
        for name in roots:
            seen.setdefault(name, None)
    return tuple(Col(name) for name in seen)


def call(
    name: str,
    args: Iterable[object],
    parent: ActuarialFrame | None,
    attrs: tuple[tuple[str, AttrValue], ...] = (),
    *,
    kind: Kind | None = None,
) -> ExpressionProxy:
    """Emit a named operation as a ``Call`` node carried by an ``ExpressionProxy``.

    The accessor-method counterpart of ``binary``: the method validates
    its own arguments (an actuary's mistake belongs at the actuary's
    line), builds this node, and returns. Everything about *how* the
    operation becomes Polars lives in its registered lowering.
    """
    from gaspatchio.column.expression_proxy import ExpressionProxy  # noqa: PLC0415

    return ExpressionProxy._from_node(  # noqa: SLF001
        call_node(name, args, attrs), parent, kind=kind
    )


def comparison(
    op: BinOpKind,
    left: object,
    right: object,
    parent: ActuarialFrame | None,
) -> ConditionExpression:
    """Emit ``left op right`` as the predicate wrapper a ``when`` chain consumes.

    A comparison is still a ``BinOp`` node; ``ConditionExpression`` is the
    frontend wrapper that marks it as *this formula's predicate*, which is
    what distinguishes a condition from an indicator column when the same
    node is lowered.
    """
    from gaspatchio.column.condition_expression import (  # noqa: PLC0415
        ConditionExpression,
    )

    left_node = to_node(left)
    if is_a_column_wider_than_i64(left_node, parent):
        with compared_against_a_wide_column():
            right_node = to_node(right)
    else:
        right_node = to_node(right)
    node = BinOp(op=op, left=left_node, right=right_node)
    return ConditionExpression._from_node(node, parent)  # noqa: SLF001


def is_a_column_wider_than_i64(node: OpNode, parent: ActuarialFrame | None) -> bool:
    """Say whether ``node`` names a column of ``parent`` still wider than ``i64``.

    Read off the frame's schema, so a book handed over lazily answers by the
    width its column arrived in, whether or not its values turn out to fit.
    """
    if not isinstance(node, Col):
        return False
    schema = getattr(parent, "_schema", None)
    dtype = schema.get(node.name) if schema is not None else None
    return dtype is not None and wider_than_i64_at(dtype) is not None
