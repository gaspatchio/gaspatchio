# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Condition expression wrapper for list_conditional plugin integration
# ABOUTME: Stores comparison operator metadata to enable plugin calls without EXPLODE
"""Condition expression wrapper for list_conditional plugin integration.

This module provides the ConditionExpression class that wraps comparison operations
with metadata needed to call the list_conditional Rust plugin, eliminating the need
for EXPLODE/GROUP_BY patterns in when/then/otherwise conditionals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from gaspatchio_core.column.shape import _UNSET, Shape, _max_shape, resolve_shape

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame


class ConditionExpression:
    """Wraps a comparison expression with metadata for list_conditional plugin.

    Created by ColumnProxy/ExpressionProxy comparison operators (__eq__, __lt__, etc.).
    Stores the operator type and operands needed to call list_conditional Rust plugin.

    This class enables the elimination of EXPLODE/GROUP_BY patterns by tracking
    comparison metadata at creation time, allowing ConditionalProxy to call the
    plugin directly instead of using the expensive EXPLODE pattern.

    Attributes:
        _expr: The Polars comparison expression (lazy, for compatibility)
        _parent: Parent ActuarialFrame for context
        operator: Comparison operator ("eq", "ne", "lt", "lte", "gt", "gte")
        left: Left operand expression
        right: Right operand expression

    """

    def __init__(
        self,
        expr: pl.Expr,
        parent: ActuarialFrame,
        operator: str,
        left: pl.Expr,
        right: pl.Expr,
    ) -> None:
        """Initialize condition expression with metadata.

        Args:
            expr: The Polars comparison expression (for compatibility)
            parent: Parent ActuarialFrame for context
            operator: Comparison operator ("eq", "ne", "lt", "lte", "gt", "gte")
            left: Left operand expression
            right: Right operand expression

        """
        self._expr = expr  # For duck-type compatibility with ExpressionProxy
        self._parent = parent
        self.operator = operator
        self.left = left
        self.right = right
        self._shape_cached: tuple[int, str] | object = _UNSET

    @property
    def shape(self) -> Shape:
        """Resolved shape of this comparison — the max of operand shapes."""
        gen = getattr(self._parent, "_schema_generation", 0) if self._parent else 0
        if self._shape_cached is _UNSET or self._shape_cached[0] != gen:  # type: ignore[index]
            self._shape_cached = (
                gen,
                _max_shape(
                    resolve_shape(self.left, self._parent),
                    resolve_shape(self.right, self._parent),
                ),
            )
        return self._shape_cached[1]  # type: ignore[index]

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
        return resolve_shape(self.left, self._parent)

    @property
    def right_shape(self) -> Shape:
        """Resolved shape of the right operand."""
        return resolve_shape(self.right, self._parent)

    def normalize_for_list_path(self) -> tuple[pl.Expr, pl.Expr, str]:
        """Return ``(left, right, operator)`` ordered for ``list_conditional``.

        The ``list_conditional`` plugin requires the list-typed operand on
        ``left`` ("left must be List dtype"). User code can produce commuted
        predicates like ``(scalar) == af.list_col`` where the list lands on
        the right; this swaps operands and inverts the operator so the
        plugin contract holds. Predicates already in canonical form pass
        through unchanged.
        """
        if self.left_shape != "list" and self.right_shape == "list":
            return self.right, self.left, self._INVERSE_OPERATOR[self.operator]
        return self.left, self.right, self.operator

    def _has_list_column(self, expr: pl.Expr) -> bool:
        """Check if expression involves any list columns.

        Args:
            expr: The expression to check

        Returns:
            True if any column in the expression is a list column

        """
        if self._parent is None:
            return False

        from gaspatchio_core.column.shape import _shape_from_expr_dtype

        return _shape_from_expr_dtype(self._parent, expr) == "list"

    def _to_boolean_expr(self) -> pl.Expr:
        """Convert this condition to a boolean expression (0.0/1.0).

        Delegates to ``polars_backend.masks.to_boolean_expr`` — the
        arithmetic-as-logic implementation now lives in the backend.
        """
        from gaspatchio_core.polars_backend.masks import to_boolean_expr

        return to_boolean_expr(self)

    def __and__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with AND (&).

        For list columns: converts to Float64 boolean expressions (0.0/1.0)
        and combines via multiplication (for use with list_conditional plugin).

        For scalar columns: uses native Polars boolean AND operation.
        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.polars_backend.masks import boolean_and

        combined, is_list_path = boolean_and(self, other)
        if is_list_path:
            return ExpressionProxy(combined, self._parent, kind="boolean_mask")
        return ExpressionProxy(combined, self._parent)

    def __rand__(self, other: ExpressionProxy) -> ExpressionProxy:
        """Handle ExpressionProxy & ConditionExpression (reverse AND)."""
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.polars_backend.masks import to_boolean_expr

        left_bool = other._expr  # noqa: SLF001
        right_bool = to_boolean_expr(self)
        combined = left_bool * right_bool
        return ExpressionProxy(combined, self._parent, kind="boolean_mask")

    def __or__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with OR (|).

        Uses formula: 1 - ((1 - left) * (1 - right)) for element-wise OR.
        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.polars_backend.masks import boolean_or

        combined = boolean_or(self, other)
        return ExpressionProxy(combined, self._parent, kind="boolean_mask")

    def __ror__(self, other: ExpressionProxy) -> ExpressionProxy:
        """Handle ExpressionProxy | ConditionExpression (reverse OR)."""
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.polars_backend.masks import to_boolean_expr

        left_bool = other._expr  # noqa: SLF001
        right_bool = to_boolean_expr(self)
        combined = pl.lit(1.0) - ((pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool))
        return ExpressionProxy(combined, self._parent, kind="boolean_mask")

    def __invert__(self) -> ExpressionProxy:
        """Negate condition with NOT (~)."""
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.polars_backend.masks import boolean_not

        return ExpressionProxy(boolean_not(self), self._parent, kind="boolean_mask")
