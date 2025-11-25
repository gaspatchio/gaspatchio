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

    def _has_list_column(self, expr: pl.Expr) -> bool:
        """Check if expression involves any list columns.

        Args:
            expr: The expression to check

        Returns:
            True if any column in the expression is a list column

        """
        if self._parent is None:
            return False

        from gaspatchio_core.column import dispatch

        detector = dispatch.ColumnTypeDetector(self._parent)  # type: ignore[attr-defined]

        try:
            col_names = expr.meta.root_names()
        except (AttributeError, RuntimeError):
            return False

        return any(detector.is_list_column(col_name) for col_name in col_names)

    def _to_boolean_expr(self) -> pl.Expr:
        """Convert this condition to a boolean expression (0.0/1.0).

        Uses list_conditional for list columns, standard Polars for scalars.

        Returns:
            Polars expression evaluating to 0.0 or 1.0 (scalar or list)

        """
        import polars as pl

        # Check if left operand involves list columns
        if self._has_list_column(self.left):
            from gaspatchio_core.functions.vector import list_conditional

            return list_conditional(
                self.left, self.right, pl.lit(1.0), pl.lit(0.0), self.operator
            )
        # Scalar case - use standard Polars comparison, cast to float
        return self._expr.cast(pl.Float64)

    def _other_to_boolean_expr(
        self, other: ConditionExpression | ExpressionProxy
    ) -> pl.Expr:
        """Convert 'other' operand to boolean expression.

        Handles ConditionExpression, ExpressionProxy, and ColumnProxy.

        Args:
            other: The other operand

        Returns:
            Polars expression evaluating to 0.0/1.0 or boolean

        """
        import polars as pl

        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # ConditionExpression - use its _to_boolean_expr method
        if isinstance(other, ConditionExpression):
            return other._to_boolean_expr()  # noqa: SLF001

        # ColumnProxy (boolean column) - convert to expr and cast to float
        if isinstance(other, ColumnProxy):
            return other._to_expr().cast(pl.Float64)  # noqa: SLF001

        # ExpressionProxy - already boolean, just extract expr
        if isinstance(other, ExpressionProxy):
            return other._expr  # noqa: SLF001

        # Fallback - assume it's a pl.Expr
        return other

    def _involves_list_columns(
        self, other: ConditionExpression | ExpressionProxy
    ) -> bool:
        """Check if self or other involves any list columns."""
        from gaspatchio_core.column.column_proxy import ColumnProxy
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Check self
        if self._has_list_column(self.left):
            return True

        # Check other based on its type
        if isinstance(other, ConditionExpression):
            if other._has_list_column(other.left):  # noqa: SLF001
                return True
        elif isinstance(other, (ColumnProxy, ExpressionProxy)):
            # Check columns in the expression
            try:
                if isinstance(other, ColumnProxy):
                    col_names = [other.name]
                else:
                    col_names = other._expr.meta.root_names()  # noqa: SLF001
                if self._parent is not None:
                    from gaspatchio_core.column import dispatch

                    detector = dispatch.ColumnTypeDetector(self._parent)  # type: ignore[attr-defined]
                    if any(detector.is_list_column(cn) for cn in col_names):
                        return True
            except (AttributeError, RuntimeError):
                pass

        return False

    def __and__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with AND (&).

        For list columns: converts to Float64 boolean expressions (0.0/1.0)
        and combines via multiplication (for use with list_conditional plugin).

        For scalar columns: uses native Polars boolean AND operation.

        Returns:
            ExpressionProxy wrapping combined boolean expression

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Check if ANY columns involved are list columns
        has_list = self._involves_list_columns(other)

        if has_list:
            # List path: use Float64 multiplication
            left_bool = self._to_boolean_expr()
            right_bool = self._other_to_boolean_expr(other)
            combined = left_bool * right_bool

            result = ExpressionProxy(combined, self._parent)
            result._is_boolean_list = True  # type: ignore[attr-defined]
            return result
        # Scalar path: use native Polars boolean AND
        from gaspatchio_core.column.column_proxy import ColumnProxy

        if isinstance(other, ConditionExpression):
            other_expr = other._expr
        elif isinstance(other, ColumnProxy):
            other_expr = other._to_expr()
        else:
            other_expr = other._expr

        combined = self._expr & other_expr
        return ExpressionProxy(combined, self._parent)

    def __rand__(self, other: ExpressionProxy) -> ExpressionProxy:
        """Handle ExpressionProxy & ConditionExpression (reverse AND)."""
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # other is ExpressionProxy (likely from previous binary op)
        left_bool = other._expr
        right_bool = self._to_boolean_expr()

        combined = left_bool * right_bool

        result = ExpressionProxy(combined, self._parent)
        result._is_boolean_list = True  # type: ignore[attr-defined]
        return result

    def __or__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with OR (|).

        Uses formula: 1 - ((1 - left) * (1 - right)) for element-wise OR

        Returns:
            ExpressionProxy wrapping combined boolean expression

        """
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Convert to boolean expressions
        left_bool = self._to_boolean_expr()
        right_bool = self._other_to_boolean_expr(other)

        # OR logic: 1 - ((1 - a) * (1 - b))
        combined = pl.lit(1.0) - (
            (pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool)
        )

        result = ExpressionProxy(combined, self._parent)
        result._is_boolean_list = True  # type: ignore[attr-defined]
        return result

    def __ror__(self, other: ExpressionProxy) -> ExpressionProxy:
        """Handle ExpressionProxy | ConditionExpression (reverse OR)."""
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # other is ExpressionProxy (likely from previous binary op)
        left_bool = other._expr
        right_bool = self._to_boolean_expr()

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
            ExpressionProxy wrapping negated boolean expression

        """
        import polars as pl

        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Convert to boolean expression
        bool_result = self._to_boolean_expr()

        # NOT logic: 1 - boolean
        negated = pl.lit(1.0) - bool_result

        result = ExpressionProxy(negated, self._parent)
        result._is_boolean_list = True  # noqa: SLF001  # type: ignore[attr-defined]
        return result
