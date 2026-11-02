# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The frame view lowering consults when a rule depends on column shape.

The op-tree is shape-blind on purpose: ``BinOp("sub", Col("month"),
Col("maturity_month"))`` says *subtract*, not *subtract a per-period list
from a per-policy scalar*. Whether that subtraction needs Polars' native
operator, an element-wise ``list.eval``, or an explicit ``repeat_by``
broadcast depends on the dtypes the frame actually holds -- so the rule
that decides lives in lowering, and this is how lowering gets to see them.

``LoweringContext`` is a read-only view over one ``ActuarialFrame``:
column shapes from its cached schema, expression shapes from the same
minimal-frame dtype probe the proxy layer uses. Resolution is lazy -- a
context is cheap to build and costs nothing until a rule asks a question.

``lower_polars(node)`` without a context cannot resolve a column's shape or
dtype. Ordinary arithmetic can still lower without that information, but
typed operations such as ``list.get`` and ``to_integer`` refuse it. The
assignment door supplies the frame's context so that shape and dtype checks
can happen without evaluating its values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    import polars as pl

    from gaspatchio._shape import Shape


@dataclass(frozen=True, slots=True)
class LoweringContext:
    """The frame whose schema types the formula being lowered."""

    frame: object

    def shape_of_column(self, name: str) -> Shape:
        """Return the shape of column ``name`` on this context's frame."""
        from gaspatchio._shape import _shape_from_schema  # noqa: PLC0415

        return _shape_from_schema(self.frame, name)

    def shape_of_expr(self, expr: pl.Expr) -> Shape:
        """Return the shape ``expr`` resolves to against this context's frame."""
        from gaspatchio._shape import _shape_from_expr_dtype  # noqa: PLC0415

        return _shape_from_expr_dtype(self.frame, expr)

    def dtype_of_expr(self, expr: pl.Expr) -> pl.DataType | None:
        """Return the dtype ``expr`` resolves to against this frame."""
        from gaspatchio._shape import _resolve_expr_output_dtype  # noqa: PLC0415

        return _resolve_expr_output_dtype(self.frame, expr)


def context_for(parent: object | None) -> LoweringContext | None:
    """Build the lowering context for ``parent``, or ``None`` if detached.

    A proxy with no parent frame (``ExpressionProxy(expr, parent=None)``)
    has no schema to resolve shapes against, so it lowers shape-blind --
    the same contract as calling ``lower_polars(node)`` with no context.
    """
    if parent is None:
        return None
    return LoweringContext(frame=parent)


def context_for_operands(values: Iterable[object]) -> LoweringContext | None:
    """Find a lowering context among a call's operands, if any has one.

    Some things a formula reads are frame-independent -- an assumption
    ``Table``, a ``MortalityTable`` wrapping one -- and can be built and
    read against any frame, so the read has no context of its own. Its
    operands usually do: ``lookup(age=af.attained_age)`` passes a proxy
    that knows which frame it came from. Taking the first such context is
    what keeps a computed key like ``af.issue_age + af.month // 12`` on
    the per-period path, instead of re-lowering it shape-blind and
    quietly producing a different plan from the one that expression
    already had.

    Returns ``None`` when every operand is a literal or a raw expression,
    which is correct: there is no frame in the picture at all.
    """
    for value in values:
        parent = getattr(value, "_parent", None)
        if parent is not None:
            return context_for(parent)
    return None
