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
