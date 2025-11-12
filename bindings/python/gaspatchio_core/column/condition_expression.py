# ABOUTME: Condition expression wrapper for list_conditional plugin integration
# ABOUTME: Stores comparison operator metadata to enable plugin calls without EXPLODE
"""Condition expression wrapper for list_conditional plugin integration.

This module provides the ConditionExpression class that wraps comparison operations
with metadata needed to call the list_conditional Rust plugin, eliminating the need
for EXPLODE/GROUP_BY patterns in when/then/otherwise conditionals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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

    def __and__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with AND (&).

        Converts both conditions to boolean lists using list_conditional plugin,
        then combines via element-wise multiplication.

        Returns:
            ExpressionProxy wrapping combined boolean list expression

        """
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.functions.vector import list_conditional

        # Convert self to boolean list (lazy)
        left_bool = list_conditional(
            self.left, self.right, pl.lit(1.0), pl.lit(0.0), self.operator
        )

        # Convert other to boolean list (lazy)
        right_bool = list_conditional(
            other.left, other.right, pl.lit(1.0), pl.lit(0.0), other.operator
        )

        # Element-wise AND via multiplication (lazy)
        combined = left_bool * right_bool

        # Mark as boolean list for later detection
        result = ExpressionProxy(combined, self._parent)
        result._is_boolean_list = True  # type: ignore[attr-defined]
        return result

    def __or__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with OR (|).

        Uses formula: 1 - ((1 - left) * (1 - right)) for element-wise OR

        Returns:
            ExpressionProxy wrapping combined boolean list expression

        """
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.functions.vector import list_conditional

        # Convert to boolean lists
        left_bool = list_conditional(
            self.left, self.right, pl.lit(1.0), pl.lit(0.0), self.operator
        )
        right_bool = list_conditional(
            other.left, other.right, pl.lit(1.0), pl.lit(0.0), other.operator
        )

        # OR logic: 1 - ((1 - a) * (1 - b))
        combined = pl.lit(1.0) - (
            (pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool)
        )

        result = ExpressionProxy(combined, self._parent)
        result._is_boolean_list = True  # type: ignore[attr-defined]
        return result

    def __invert__(self) -> ExpressionProxy:
        """Negate condition with NOT (~).

        Uses formula: 1.0 - boolean_result for element-wise negation

        Returns:
            ExpressionProxy wrapping negated boolean list expression

        """
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.functions.vector import list_conditional

        # Convert to boolean list
        bool_result = list_conditional(
            self.left, self.right, pl.lit(1.0), pl.lit(0.0), self.operator
        )

        # NOT logic: 1 - boolean
        negated = pl.lit(1.0) - bool_result

        result = ExpressionProxy(negated, self._parent)
        result._is_boolean_list = True  # noqa: SLF001  # type: ignore[attr-defined]
        return result
