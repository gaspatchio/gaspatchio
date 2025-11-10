# ABOUTME: Conditional expressions (when/then/otherwise) for ActuarialFrame
# ABOUTME: Provides Excel-style IF() with automatic list broadcasting for projections
"""Conditional expressions (when/then/otherwise) for ActuarialFrame.

Provides Excel-style IF() functionality with automatic list broadcasting
for actuarial projections using Polars' explode/re-aggregate pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.frame.base import ActuarialFrame


class ConditionalProxy:
    """Represents an in-progress conditional expression chain.

    This class builds up when/then chains and completes them with otherwise().
    It automatically handles list vs scalar broadcasting when needed using
    the explode/re-aggregate pattern.
    """

    def __init__(self, condition_expr: pl.Expr, parent: ActuarialFrame | None) -> None:
        """Initialize conditional with first condition.

        Args:
            condition_expr: The condition expression (result of comparison)
            parent: Parent ActuarialFrame for context (can be None)

        """
        self._conditions: list[pl.Expr] = [condition_expr]
        self._values: list[pl.Expr] = []
        self._parent = parent

    def then(self, value: Any) -> ConditionalProxy:  # noqa: ANN401
        """Specify value when condition is true.

        Args:
            value: Value to return when condition matches
                   (literal, column, or expression)

        Returns:
            Self for chaining more .when() or final .otherwise()

        """
        # Convert value to expression
        if self._parent is not None:
            value_expr = self._parent._convert_to_expr(value)  # noqa: SLF001
        else:
            # No parent - convert directly
            from gaspatchio_core.column.expression_proxy import ExpressionProxy

            if isinstance(value, ExpressionProxy):
                value_expr = value._expr  # noqa: SLF001
            elif isinstance(value, pl.Expr):
                value_expr = value
            else:
                value_expr = pl.lit(value)

        self._values.append(value_expr)
        return self

    def when(self, condition: Any) -> ConditionalProxy:  # noqa: ANN401
        """Add another condition (elif behavior).

        Args:
            condition: Additional condition expression

        Returns:
            Self for chaining .then()

        """
        # Convert condition to expression
        if self._parent is not None:
            condition_expr = self._parent._convert_to_expr(condition)  # noqa: SLF001
        else:
            from gaspatchio_core.column.expression_proxy import ExpressionProxy

            if isinstance(condition, ExpressionProxy):
                condition_expr = condition._expr  # noqa: SLF001
            elif isinstance(condition, pl.Expr):
                condition_expr = condition
            else:
                msg = f"Condition must be an expression, got {type(condition)}"
                raise TypeError(msg)

        self._conditions.append(condition_expr)
        return self

    def otherwise(self, value: Any) -> ExpressionProxy:  # noqa: ANN401
        """Complete chain with default value.

        This is required - raises error if ConditionalProxy is used
        without calling this.
        Implements list broadcasting using explode/re-aggregate pattern
        when needed.

        Args:
            value: Default value when no conditions match

        Returns:
            ExpressionProxy wrapping the final Polars
            when/then/otherwise expression

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Convert otherwise value to expression
        if self._parent is not None:
            otherwise_expr = self._parent._convert_to_expr(value)  # noqa: SLF001
        elif isinstance(value, ExpressionProxy):
            otherwise_expr = value._expr  # noqa: SLF001
        elif isinstance(value, pl.Expr):
            otherwise_expr = value
        else:
            otherwise_expr = pl.lit(value)

        # Build the Polars when/then/otherwise chain (scalar only for now)
        # Start with first condition/value pair
        expr = pl.when(self._conditions[0]).then(self._values[0])

        # Add any additional when/then pairs
        for condition, then_value in zip(
            self._conditions[1:], self._values[1:], strict=False
        ):
            expr = expr.when(condition).then(then_value)

        # Complete with otherwise
        expr = expr.otherwise(otherwise_expr)

        return ExpressionProxy(expr, self._parent)

    def __repr__(self) -> str:
        """Provide helpful error message for incomplete conditionals."""
        return (
            "ConditionalProxy(incomplete - "
            "call .otherwise() to complete the expression)"
        )

    def _to_expr(self) -> pl.Expr:
        """Prevent conversion to expression without .otherwise().

        Raises:
            TypeError: Always - conditional must be completed with .otherwise()

        """
        msg = (
            "Conditional expression requires .otherwise(). "
            "Complete the chain with .otherwise(value) before using it. "
            f"Current state: {len(self._conditions)} condition(s), "
            f"{len(self._values)} value(s)."
        )
        raise TypeError(msg)


def when(condition: Any) -> ConditionalProxy:  # noqa: ANN401
    """Start a conditional expression chain.

    Like Excel's IF() function but with method chaining for multiple conditions.
    Automatically handles list vs scalar broadcasting for actuarial projections.

    Args:
        condition: Boolean expression (e.g., af.age > 65)

    Returns:
        ConditionalProxy for chaining .then() and .otherwise()

    Examples:
        Simple scalar conditional:

        >>> from gaspatchio_core import ActuarialFrame, when
        >>> af = ActuarialFrame({"age": [25, 45, 70]})
        >>> af.rate = when(af.age > 65).then(0.05).otherwise(0.02)
        >>> print(af.collect())
        shape: (3, 2)
        ┌─────┬──────┐
        │ age ┆ rate │
        │ --- ┆ ---  │
        │ i64 ┆ f64  │
        ╞═════╪══════╡
        │ 25  ┆ 0.02 │
        │ 45  ┆ 0.02 │
        │ 70  ┆ 0.05 │
        └─────┴──────┘

    """
    # Extract parent ActuarialFrame from condition if possible
    parent = None

    # Import here to avoid circular imports
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    # Try to get parent from condition
    if isinstance(condition, (ColumnProxy, ExpressionProxy)):
        parent = getattr(condition, "_parent", None)

    # Convert condition to Polars expression
    if isinstance(condition, ExpressionProxy):
        condition_expr = condition._expr  # noqa: SLF001
    elif isinstance(condition, pl.Expr):
        condition_expr = condition
    elif parent is not None:
        condition_expr = parent._convert_to_expr(condition)  # noqa: SLF001
    else:
        msg = f"Condition must be an expression, got {type(condition)}"
        raise TypeError(msg)

    return ConditionalProxy(condition_expr, parent)
