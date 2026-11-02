# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Condition expression wrapper for list_conditional plugin integration
# ABOUTME: Marks a comparison node as this formula's predicate
"""The predicate wrapper a comparison dunder returns.

``af.duration_mth_t == af.maturity_month`` emits a semantic ``BinOp``
node like every other operator. This class is what carries that node back
to the author, and it exists because *the same node means two different
things depending on where it lands*: as a ``when`` condition it is a
predicate; assigned to a column it is a Float64 0/1 indicator. Returning
``ConditionExpression`` rather than a plain expression proxy is how the
framework keeps that distinction without guessing.

The Polars expression, the lowered operands, and their shapes are all
derived from the node on demand -- a predicate that only ever feeds a
``when`` chain never needs them, because the chain lowers the whole
conditional in one pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import polars as pl

from gaspatchio._shape import _UNSET, Shape, _max_shape
from gaspatchio.column._declared import (
    _call_declared_comparison,
    _call_declared_operator,
    _refuse_a_truth_value,
    _refuse_an_exclusive_or,
)
from gaspatchio.column._generated_proxy import _GeneratedProxySurface
from gaspatchio.frame.lowering.context import context_for
from gaspatchio.frame.lowering.polars import (
    lower_binop_operands,
    lower_mask,
    lower_polars,
)

if TYPE_CHECKING:
    from typing import NoReturn

    from gaspatchio._semantic.ir import BinOp
    from gaspatchio.column.expression_proxy import ExpressionProxy
    from gaspatchio.frame.base import ActuarialFrame

# BinOp.op -> the operator name this class reports and the list_conditional
# kernel expects. The two vocabularies differ only in "le"/"ge" vs
# "lte"/"gte"; the kernel's spelling is the one on the wire.
_FRONTEND_OPERATOR: dict[str, str] = {
    "eq": "eq",
    "ne": "ne",
    "lt": "lt",
    "le": "lte",
    "gt": "gt",
    "ge": "gte",
}


class ConditionExpression:  # noqa: PLW1641 - comparisons build predicates
    """Wraps a comparison node with the metadata the conditional path needs.

    Created by ColumnProxy/ExpressionProxy comparison operators (__eq__,
    __lt__, etc.). Stores the operator type and the comparison node needed
    to call the list_conditional Rust plugin.

    This class enables the elimination of EXPLODE/GROUP_BY patterns by
    tracking comparison metadata at creation time, allowing ConditionalProxy
    to call the plugin directly instead of using the expensive EXPLODE
    pattern.

    Attributes:
        _node: The comparison ``BinOp`` node this predicate stands for
        _parent: Parent ActuarialFrame for context
        operator: Comparison operator ("eq", "ne", "lt", "lte", "gt", "gte")

    """

    def __init__(self, node: BinOp, parent: ActuarialFrame | None) -> None:
        """Initialize a predicate from its comparison node.

        Args:
            node: The comparison ``BinOp`` this predicate stands for
            parent: Parent ActuarialFrame for context

        """
        self._node = node
        self._parent = parent
        self.operator = _FRONTEND_OPERATOR[node.op]
        self._shape_cached: tuple[int, str] | object = _UNSET
        self._operands_cached: tuple[int, tuple[pl.Expr, Shape, pl.Expr, Shape]] | None
        self._operands_cached = None

    @classmethod
    def _from_node(
        cls, node: BinOp, parent: ActuarialFrame | None
    ) -> ConditionExpression:
        """Build a predicate from a comparison node (the emission entry point)."""
        return cls(node, parent)

    def _generation(self) -> int:
        """Return the parent frame's schema generation, or 0 when detached.

        Every derived value below is cached against it, so a column added
        to the frame after this predicate was built invalidates the cache
        rather than silently reusing a stale shape.
        """
        return getattr(self._parent, "_schema_generation", 0) if self._parent else 0

    def _operands(self) -> tuple[pl.Expr, Shape, pl.Expr, Shape]:
        """Lower both comparison operands, with their shapes, and cache them."""
        generation = self._generation()
        cached = self._operands_cached
        if cached is None or cached[0] != generation:
            resolved = lower_binop_operands(self._node, context_for(self._parent))
            self._operands_cached = (generation, resolved)
            return resolved
        return cached[1]

    @property
    def _expr(self) -> pl.Expr:
        """The native Polars predicate for this comparison.

        Only the scalar paths use it: a list-shaped comparison has no
        native Polars form at all (Polars refuses list-vs-scalar
        comparison), which is what ``normalize_for_list_path`` exists for.
        """
        return lower_polars(self._node, context_for(self._parent))

    @property
    def shape(self) -> Shape:
        """Resolved shape of this comparison — the max of operand shapes."""
        generation = self._generation()
        if self._shape_cached is _UNSET or self._shape_cached[0] != generation:  # type: ignore[index]
            _, left_shape, _, right_shape = self._operands()
            self._shape_cached = (generation, _max_shape(left_shape, right_shape))
        return self._shape_cached[1]  # type: ignore[index,return-value]

    kind: ClassVar[str] = "comparison"

    # Operator inverse table — used to commute operands when the list-typed
    # side ends up on the right (e.g. ``(scalar) == af.list_col``). Keeping
    # the table on the frontend because operator string identity is a
    # frontend concept (set by ColumnProxy/ExpressionProxy comparison dunders).
    _INVERSE_OPERATOR: ClassVar[dict[str, str]] = {
        "lt": "gt",
        "gt": "lt",
        "lte": "gte",
        "gte": "lte",
        "eq": "eq",
        "ne": "ne",
    }

    @property
    def left_shape(self) -> Shape:
        """Resolved shape of the left operand."""
        _, left_shape, _, _ = self._operands()
        return left_shape

    @property
    def right_shape(self) -> Shape:
        """Resolved shape of the right operand."""
        _, _, _, right_shape = self._operands()
        return right_shape

    def normalize_for_list_path(self) -> tuple[pl.Expr, pl.Expr, str]:
        """Return ``(left, right, operator)`` ordered for ``list_conditional``.

        The ``list_conditional`` plugin requires the list-typed operand on
        ``left`` ("left must be List dtype"). User code can produce commuted
        predicates like ``(scalar) == af.list_col`` where the list lands on
        the right; this swaps operands and inverts the operator so the
        plugin contract holds. Predicates already in canonical form pass
        through unchanged.
        """
        left, left_shape, right, right_shape = self._operands()
        if left_shape != "list" and right_shape == "list":
            return right, left, self._INVERSE_OPERATOR[self.operator]
        return left, right, self.operator

    def _to_boolean_expr(self) -> pl.Expr:
        """Convert this condition to its Float64 0/1 mask on the resolved shape.

        A per-period comparison is the indicator the lowering gives the same
        comparison written as a value (``lower_mask``): a per-period
        Categorical or Enum column compared for equality is handed to the
        kernel as its codes, and two whole numbers, dates and times or
        durations a double does not hold are compared exactly, so the
        column assigned and the ``when`` written over it answer alike.
        """
        if self.shape == "list" or _a_comparison(self._node):
            # Per policy too: a comparison with a NaN operand stores a NaN
            # indicator, which the predicate's cast cannot say (11.1.26).
            return lower_mask(self._node, context_for(self._parent))
        return self._expr.cast(pl.Float64)

    def __and__(self, other: object) -> ExpressionProxy:
        """Combine this predicate through the declared Boolean operator."""
        return _call_declared_operator("__and__", self, other)

    def __rand__(self, other: object) -> ExpressionProxy:
        """Combine this predicate through the declared Boolean operator."""
        return _call_declared_operator("__rand__", self, other)

    def __or__(self, other: object) -> ExpressionProxy:
        """Combine this predicate through the declared Boolean operator."""
        return _call_declared_operator("__or__", self, other)

    def __ror__(self, other: object) -> ExpressionProxy:
        """Combine this predicate through the declared Boolean operator."""
        return _call_declared_operator("__ror__", self, other)

    def __invert__(self) -> ExpressionProxy:
        """Combine this predicate through the declared Boolean operator."""
        return _call_declared_operator("__invert__", self)

    # A comparison in arithmetic is the 0.0/1.0 indicator section 11.1.25 reads
    # a flag as beside a number -- ``(af.age > 60) * af.loading`` already read
    # it so with the column on the left of the operator, and the same line
    # with the comparison on the left, or against a constant, raised Python's
    # own TypeError. Each operator below is the declared one the column
    # proxies carry, so either order records one node and lowers alike.

    def __add__(self, other: object) -> ExpressionProxy:
        """Add, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__add__", self, other)

    def __radd__(self, other: object) -> ExpressionProxy:
        """Add, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__radd__", self, other)

    def __sub__(self, other: object) -> ExpressionProxy:
        """Subtract, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__sub__", self, other)

    def __rsub__(self, other: object) -> ExpressionProxy:
        """Subtract, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__rsub__", self, other)

    def __mul__(self, other: object) -> ExpressionProxy:
        """Multiply, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__mul__", self, other)

    def __rmul__(self, other: object) -> ExpressionProxy:
        """Multiply, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__rmul__", self, other)

    def __truediv__(self, other: object) -> ExpressionProxy:
        """Divide, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__truediv__", self, other)

    def __rtruediv__(self, other: object) -> ExpressionProxy:
        """Divide, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__rtruediv__", self, other)

    def __floordiv__(self, other: object) -> ExpressionProxy:
        """Floor-divide, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__floordiv__", self, other)

    def __rfloordiv__(self, other: object) -> ExpressionProxy:
        """Floor-divide, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__rfloordiv__", self, other)

    def __mod__(self, other: object) -> ExpressionProxy:
        """Take the remainder, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__mod__", self, other)

    def __rmod__(self, other: object) -> ExpressionProxy:
        """Take the remainder, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__rmod__", self, other)

    def __pow__(self, other: object) -> ExpressionProxy:
        """Raise to a power, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__pow__", self, other)

    def __rpow__(self, other: object) -> ExpressionProxy:
        """Raise to a power, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__rpow__", self, other)

    def __neg__(self) -> ExpressionProxy:
        """Negate, reading this comparison as its 0.0/1.0 indicator."""
        return _call_declared_operator("__neg__", self)

    # A comparison compared is a column too. With no comparison operators of
    # its own, ``(af.k > 2) == 1`` fell through to Python's identity test and
    # answered a Python ``False`` -- stored, that was a column of False on
    # every policy, and nothing raised -- while ``<`` raised Python's own
    # TypeError. Each comparison below is the declared one the column proxies
    # carry, so it records one comparison over this one and answers as a
    # stored flag compared does: per policy as its truth value, per period as
    # its 0.0/1.0 indicator (section 11.1.26).

    def __eq__(self, other: object) -> ConditionExpression:  # type: ignore[override]
        """Compare this comparison's truth value, as a stored flag compares."""
        return _call_declared_comparison("__eq__", self, other)

    def __ne__(self, other: object) -> ConditionExpression:  # type: ignore[override]
        """Compare this comparison's truth value, as a stored flag compares."""
        return _call_declared_comparison("__ne__", self, other)

    def __lt__(self, other: object) -> ConditionExpression:
        """Compare this comparison's truth value, as a stored flag compares."""
        return _call_declared_comparison("__lt__", self, other)

    def __le__(self, other: object) -> ConditionExpression:
        """Compare this comparison's truth value, as a stored flag compares."""
        return _call_declared_comparison("__le__", self, other)

    def __gt__(self, other: object) -> ConditionExpression:
        """Compare this comparison's truth value, as a stored flag compares."""
        return _call_declared_comparison("__gt__", self, other)

    def __ge__(self, other: object) -> ConditionExpression:
        """Compare this comparison's truth value, as a stored flag compares."""
        return _call_declared_comparison("__ge__", self, other)

    def __xor__(self, other: object) -> NoReturn:
        """Refuse ``^``, as a column does: compare the two tests instead."""
        del other
        _refuse_an_exclusive_or()

    def __rxor__(self, other: object) -> NoReturn:
        """Refuse ``^``, as a column does: compare the two tests instead."""
        del other
        _refuse_an_exclusive_or()

    def __pos__(self) -> ConditionExpression:
        """Answer ``+(test)`` with the test itself, as a column answers itself."""
        return self

    def __abs__(self) -> ExpressionProxy:
        """Drop the sign of this comparison's 0.0/1.0 indicator, as of a flag."""
        return _call_declared_operator("__abs__", self)

    # The thirteen calls that read a number read a comparison as its 0.0 or
    # 1.0 and answer a double (sections 11.1.8, 11.1.12, 11.1.25), as they
    # read a stored flag. Without them ``(af.k > 2).round()`` raised Python's
    # own AttributeError. Each is the column's own declared method, so the
    # record, the signature and the documentation are the column's.
    abs = _GeneratedProxySurface.abs
    sign = _GeneratedProxySurface.sign
    sqrt = _GeneratedProxySurface.sqrt
    cbrt = _GeneratedProxySurface.cbrt
    exp = _GeneratedProxySurface.exp
    log = _GeneratedProxySurface.log
    log10 = _GeneratedProxySurface.log10
    log1p = _GeneratedProxySurface.log1p
    norm_cdf = _GeneratedProxySurface.norm_cdf
    round_sig_figs = _GeneratedProxySurface.round_sig_figs
    round = _GeneratedProxySurface.round
    floor = _GeneratedProxySurface.floor
    ceil = _GeneratedProxySurface.ceil

    def __getattr__(self, name: str) -> NoReturn:
        """Refuse, by name, a column's method a comparison does not answer.

        A comparison is a test, read as its truth value in a condition and as
        its 0.0/1.0 indicator in a number; which of the two a method such as
        ``fill_null`` or ``to_text`` would read is not stated, so it is
        refused here rather than guessed, naming the two ways to say which.
        Runs only for a name this class does not hold.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        msg = (
            f"{name} is not answered on a comparison. A comparison is a test: "
            "a condition reads its truth value, and arithmetic and the calls "
            "that read a number (abs, sign, sqrt, cbrt, exp, log, log10, "
            "log1p, norm_cdf, round, round_sig_figs, floor, ceil) read its "
            "0.0/1.0 indicator. Say which one the line means: store the "
            "indicator first, af.<name> = <comparison>, and call "
            f"af.<name>.{name}(...), or write the value you mean, "
            f"when(<comparison>).then(<value>).otherwise(<other value>).{name}(...)."
        )
        raise AttributeError(msg)

    def __bool__(self) -> NoReturn:  # noqa: PLE0304 - the refusal is the answer
        """Refuse ``and``, ``or``, ``not`` and a bare ``if`` on a predicate.

        The column proxies carry the same refusal from their generated
        base; this class is not built on it, so it states the refusal
        itself. A comparison answers per policy, and on a projection per
        period, so ``(af.age > 60) and (af.sum_assured > 1000000)`` would
        quietly evaluate to the second bracket alone -- every young life
        with a large sum assured included, and nothing raised.
        """
        _refuse_a_truth_value()


# What the API reference documents from this module.
__all__ = ["ConditionExpression"]


def _a_comparison(node: object) -> bool:
    """Say whether ``node`` is one of the six comparisons."""
    return getattr(node, "op", None) in {"lt", "le", "gt", "ge", "eq", "ne"}
