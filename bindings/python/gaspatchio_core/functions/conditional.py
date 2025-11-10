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
        self._list_columns: set[str] | None = None
        self._otherwise_expr: pl.Expr | None = None

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

    def needs_list_broadcasting(self) -> bool:
        """Check if this conditional requires list broadcasting.

        Returns:
            True if any columns involved are list columns, False otherwise

        """
        if self._parent is None:
            return False

        # Detection hasn't happened yet - return False for now
        # Will be populated during otherwise()
        if self._list_columns is None:
            return False

        return len(self._list_columns) > 0

    def get_list_broadcasting_metadata(self) -> dict[str, Any]:
        """Get metadata needed for DataFrame-level list broadcasting.

        Returns:
            Dictionary containing:
            - conditions: List of condition expressions
            - values: List of then-value expressions
            - otherwise_expr: The otherwise value expression (if set)
            - list_columns: Set of detected list column names

        """
        # Detect list columns on-demand if not already done
        if self._list_columns is None:
            self._list_columns = self._detect_list_columns_from_current_state()

        return {
            "conditions": self._conditions,
            "values": self._values,
            "otherwise_expr": self._otherwise_expr,
            "list_columns": self._list_columns,
        }

    def _detect_list_columns_from_current_state(self) -> set[str]:
        """Detect list columns from conditions and values so far.

        Returns:
            Set of list column names detected in expressions

        """
        if self._parent is None:
            return set()

        from gaspatchio_core.column import dispatch

        detector = dispatch.ColumnTypeDetector(self._parent)  # type: ignore[attr-defined]

        list_columns = set()

        # Check all expressions so far
        all_exprs = self._conditions + self._values

        for expr in all_exprs:
            col_names = self._extract_column_names(expr)
            for col_name in col_names:
                if detector.is_list_column(col_name):
                    list_columns.add(col_name)

        return list_columns

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

        Raises:
            NotImplementedError: If list broadcasting is detected but not
                yet fully implemented

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Convert otherwise value to expression
        otherwise_expr = self._convert_value_to_expr(value)
        self._otherwise_expr = otherwise_expr

        # Detect if we need list broadcasting and store in _list_columns
        self._list_columns = self._detect_list_columns(otherwise_expr)

        # Build expression based on detection
        if self._list_columns:
            # Build scalar conditional (will be used after explode)
            expr = self._build_scalar_conditional(otherwise_expr)

            # Create ExpressionProxy with metadata
            result = ExpressionProxy(expr, self._parent)
            result._list_broadcast_metadata = {  # noqa: SLF001
                "list_columns": self._list_columns,
                "conditional_expr": expr,
            }
            return result
        # Scalar path - build simple when/then/otherwise
        expr = self._build_scalar_conditional(otherwise_expr)
        return ExpressionProxy(expr, self._parent)

    def _convert_value_to_expr(self, value: Any) -> pl.Expr:  # noqa: ANN401
        """Convert a value to a Polars expression."""
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if self._parent is not None:
            return self._parent._convert_to_expr(value)  # noqa: SLF001
        if isinstance(value, ExpressionProxy):
            return value._expr  # noqa: SLF001
        if isinstance(value, pl.Expr):
            return value
        return pl.lit(value)

    def _detect_list_columns(self, otherwise_expr: pl.Expr) -> set[str]:
        """Detect list columns in the conditional expressions."""
        if self._parent is None:
            return set()

        # Import at runtime to avoid circular imports
        from gaspatchio_core.column import dispatch

        detector = dispatch.ColumnTypeDetector(self._parent)  # type: ignore[attr-defined]
        list_columns: set[str] = set()

        # Check all expressions for list columns
        all_exprs = self._conditions + self._values + [otherwise_expr]

        for expr in all_exprs:
            col_names = self._extract_column_names(expr)
            for col_name in col_names:
                if detector.is_list_column(col_name):
                    list_columns.add(col_name)

        return list_columns

    def _extract_column_names(self, expr: pl.Expr) -> list[str]:
        """Extract column names from an expression, returning empty list on failure."""
        try:
            return expr.meta.root_names()
        except (AttributeError, RuntimeError):
            # meta.root_names() may fail for some expressions
            return []

    def _build_scalar_conditional(self, otherwise_expr: pl.Expr) -> pl.Expr:
        """Build a scalar when/then/otherwise expression."""
        expr = pl.when(self._conditions[0]).then(self._values[0])
        for condition, then_value in zip(
            self._conditions[1:], self._values[1:], strict=False
        ):
            expr = expr.when(condition).then(then_value)
        return expr.otherwise(otherwise_expr)

    def _build_list_broadcasting_expr(
        self, otherwise_expr: pl.Expr, list_columns: set[str]
    ) -> pl.Expr:
        """Build expression for list broadcasting (not yet implemented).

        This method will eventually implement the explode/re-aggregate pattern
        for list broadcasting. For now, it raises NotImplementedError with a
        clear message about which list columns were detected.

        Args:
            otherwise_expr: The otherwise value expression
            list_columns: Set of list column names detected in the expressions

        Raises:
            NotImplementedError: Always - list broadcasting not yet implemented

        """
        msg = (
            "List broadcasting in conditionals is not yet fully implemented. "
            "Polars does not automatically broadcast scalars in conditional "
            "expressions when list columns are involved. "
            f"List columns detected: {sorted(list_columns)}. "
            "Full implementation with explode/re-aggregate pattern is planned."
        )
        raise NotImplementedError(msg)

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
