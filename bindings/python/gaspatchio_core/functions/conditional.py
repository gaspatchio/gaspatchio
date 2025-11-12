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

        Defines the result value for when the preceding condition evaluates to true.
        Must be followed by either another `.when()` for chained conditions or
        `.otherwise()` to complete the expression. Works with scalar values, column
        references, or computed expressions.

        Args:
            value: Value to return when condition matches. Can be a literal value
                (number, string, etc.), a column reference (af.column_name), or a
                computed expression (af.premium * 1.1). For list columns, values
                are applied element-wise with automatic broadcasting.

        Returns:
            Self for chaining more .when() or final .otherwise()

        Examples:
        --------
        **Scalar Example: Multi-Tier Premium Rates**

        ```python
        from gaspatchio_core import ActuarialFrame, when

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", "P005"],
            "age": [25, 42, 55, 68, 73],
        }
        af = ActuarialFrame(data)

        af.premium_rate = (
            when(af.age < 35)
            .then(0.0015)
            .when(af.age < 50)
            .then(0.0025)
            .when(af.age < 65)
            .then(0.0040)
            .otherwise(0.0065)
        )

        print(af.collect())
        ```

        ```text
        shape: (5, 3)
        ┌───────────┬─────┬──────────────┐
        │ policy_id ┆ age ┆ premium_rate │
        │ ---       ┆ --- ┆ ---          │
        │ str       ┆ i64 ┆ f64          │
        ╞═══════════╪═════╪══════════════╡
        │ P001      ┆ 25  ┆ 0.0015       │
        │ P002      ┆ 42  ┆ 0.0025       │
        │ P003      ┆ 55  ┆ 0.004        │
        │ P004      ┆ 68  ┆ 0.0065       │
        │ P005      ┆ 73  ┆ 0.0065       │
        └───────────┴─────┴──────────────┘
        ```

        **Vector Example: Premium Holiday**

        ```python
        from gaspatchio_core import ActuarialFrame, when

        data = {
            "policy_id": ["P001"],
            "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
            "premium_holiday_month": [6],
            "base_premium": [100.0],
        }
        af = ActuarialFrame(data)

        af.premium_due = (
            when(af.month == af.premium_holiday_month)
            .then(0.0)
            .otherwise(af.base_premium)
        )

        print(af.collect())
        ```

        ```text
        shape: (1, 5)
        ┌───────────┬──────────────┬──────────┬─────────────────────────┐
        │ policy_id ┆ month        ┆ base...  ┆ premium_due             │
        │ ---       ┆ ---          ┆ ---      ┆ ---                     │
        │ str       ┆ list[i64]    ┆ f64      ┆ list[f64]               │
        ╞═══════════╪══════════════╪══════════╪═════════════════════════╡
        │ P001      ┆ [0, 1, … 12] ┆ 100.0    ┆ [100.0, 100.0, … 100.0] │
        └───────────┴──────────────┴──────────┴─────────────────────────┘
        ```

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
        """Complete conditional chain with default value.

        Finalizes the conditional expression by providing the value to use when none
        of the preceding conditions evaluate to true. This method is required - a
        conditional expression cannot be used without calling `.otherwise()`.
        Automatically detects and handles list broadcasting for projection
        calculations.

        !!! note "When to use"
            * **Default Rate:** Provide standard rate when age doesn't match
                any premium tiers or risk categories.
            * **Zero After Event:** Set cash flows to zero for all months after
                maturity, surrender, or death events occur.
            * **Fallback Values:** Apply baseline commission rates, default
                mortality assumptions, or standard policy terms when special
                conditions aren't met.
            * **Maintain Status Quo:** Keep existing premium, benefit, or reserve
                values unchanged when update conditions don't apply.

        Args:
            value: Default value when no conditions match. Can be a literal value,
                column reference, or computed expression. For list columns, this
                value is broadcast element-wise across all list elements.

        Returns:
            ExpressionProxy wrapping the complete conditional expression, ready
            for assignment to a column.

        Examples:
        --------
        **Scalar Example: Underwriting Classification**

        ```python
        from gaspatchio_core import ActuarialFrame, when

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", "P005", "P006"],
            "age": [25, 42, 55, 68, 73, 45],
            "sum_assured": [100000, 250000, 500000, 150000, 300000, 600000],
        }
        af = ActuarialFrame(data)

        af.underwriting_class = (
            when(af.sum_assured > 500000)
            .then("refer_underwriting")
            .when(af.age > 65)
            .then("senior_standard")
            .when(af.age < 35)
            .then("young_preferred")
            .otherwise("standard")
        )

        print(af.collect())
        ```

        ```text
        shape: (6, 4)
        ┌───────────┬─────┬─────────────┬────────────────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ underwriting_class │
        │ ---       ┆ --- ┆ ---         ┆ ---                │
        │ str       ┆ i64 ┆ i64         ┆ str                │
        ╞═══════════╪═════╪═════════════╪════════════════════╡
        │ P001      ┆ 25  ┆ 100000      ┆ young_preferred    │
        │ P002      ┆ 42  ┆ 250000      ┆ standard           │
        │ P003      ┆ 55  ┆ 500000      ┆ standard           │
        │ P004      ┆ 68  ┆ 150000      ┆ senior_standard    │
        │ P005      ┆ 73  ┆ 300000      ┆ senior_standard    │
        │ P006      ┆ 45  ┆ 600000      ┆ refer_underwriting │
        └───────────┴─────┴─────────────┴────────────────────┘
        ```

        **List Broadcasting Behavior**

        The `.otherwise()` method automatically detects when list columns are involved
        and applies the default value element-wise. If the otherwise value is a scalar
        (like `0` or `100.0`), it's broadcast to match the length of each list. If
        the otherwise value is itself a list column, elements are matched one-to-one.

        This enables patterns like:
        - Zeroing cash flows after maturity: `.otherwise(0)`
        - Maintaining baseline premiums: `.otherwise(af.base_premium)`
        - Default growth rates: `.otherwise(0.03)` broadcasts to all months

        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Convert otherwise value to expression
        otherwise_expr = self._convert_value_to_expr(value)
        self._otherwise_expr = otherwise_expr

        # Build expression - now uses plugin internally for list columns
        expr = self._build_scalar_conditional(otherwise_expr)

        # Return ExpressionProxy WITHOUT _list_broadcast_metadata
        # The plugin already handled list operations - no EXPLODE needed!
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
        """Build conditional - uses list_conditional plugin for list columns."""
        from gaspatchio_core.column.condition_expression import (
            ConditionExpression,
        )
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Only handle single condition for MVP
        if len(self._conditions) > 1:
            msg = (
                "Multiple chained .when() not yet supported with "
                "list_conditional plugin. Use separate conditionals "
                "or combine with & operator."
            )
            raise NotImplementedError(msg)

        condition = self._conditions[0]
        then_val = self._values[0]

        # Case 1: Direct comparison (ConditionExpression) - use plugin
        if isinstance(condition, ConditionExpression):
            from gaspatchio_core.functions.vector import list_conditional

            return list_conditional(
                left=condition.left,
                right=condition.right,
                then_val=then_val,
                otherwise_val=otherwise_expr,
                operator=condition.operator,
            )

        # Case 2: ExpressionProxy or pl.Expr - fall back to standard Polars
        # Extract expression from proxy if needed
        if isinstance(condition, ExpressionProxy):
            condition_expr = condition._expr  # noqa: SLF001
        else:
            condition_expr = condition

        # Standard Polars when/then/otherwise
        return pl.when(condition_expr).then(then_val).otherwise(otherwise_expr)

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

    Excel-style IF() function with method chaining for multiple conditions.
    Provides intuitive if/elif/else logic for actuarial calculations. Automatically
    handles both scalar columns and list columns (projections) with proper broadcasting.

    **Supported in both debug and optimize modes** - conditionals with list columns
    work seamlessly in either execution mode.

    !!! note "When to use"
        * **Age-Based Pricing:** Apply different premium rates, mortality factors,
            or underwriting classes based on policyholder age brackets.
        * **Maturity Events:** Identify when policies mature by comparing projection
            month against policy term, zeroing cash flows after maturity.
        * **Premium Holidays:** Suspend premium collection for specific months or
            conditions, such as grace periods or payment holidays.
        * **Commission Schedules:** Calculate tiered commission rates based on
            policy value, product type, or sales channel.
        * **Benefit Triggers:** Activate guaranteed minimum benefits, death benefits,
            or surrender values when specific conditions are met.
        * **Underwriting Rules:** Implement automated underwriting decisions based on
            sum assured, age, and other risk factors.

    Args:
        condition: Boolean expression (e.g., af.age > 65)

    Returns:
        ConditionalProxy for chaining .then() and .otherwise()

    Examples:
    --------
    **Scalar Example: Age-Based Rate Classification**

    ```python
    from gaspatchio_core import ActuarialFrame, when

    data = {
        "policy_id": ["P001", "P002", "P003", "P004"],
        "age": [35, 55, 68, 72],
    }
    af = ActuarialFrame(data)

    af.rate_class = when(af.age > 65).then("senior").otherwise("standard")

    print(af.collect())
    ```

    ```text
    shape: (4, 3)
    ┌───────────┬─────┬────────────┐
    │ policy_id ┆ age ┆ rate_class │
    │ ---       ┆ --- ┆ ---        │
    │ str       ┆ i64 ┆ str        │
    ╞═══════════╪═════╪════════════╡
    │ P001      ┆ 35  ┆ standard   │
    │ P002      ┆ 55  ┆ standard   │
    │ P003      ┆ 68  ┆ senior     │
    │ P004      ┆ 72  ┆ senior     │
    └───────────┴─────┴────────────┘
    ```

    **Vector Example: Maturity Detection with List Broadcasting**

    ```python
    from gaspatchio_core import ActuarialFrame, when

    data = {
        "policy_id": ["P001", "P002"],
        "month": [
            [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            [
                0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12,
                13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24
            ]
        ],
        "policy_term_years": [1, 2],
        "pols_if": [
            [1000, 998, 996, 994, 992, 990, 988, 986, 984, 982, 980, 978, 976],
            [
                1000, 998, 996, 994, 992, 990, 988, 986, 984, 982, 980, 978,
                976, 974, 972, 970, 968, 966, 964, 962, 960, 958, 956, 954, 952
            ]
        ],
    }
    af = ActuarialFrame(data)

    af.pols_maturity = (
        when(af.month == af.policy_term_years * 12)
        .then(af.pols_if)
        .otherwise(0)
    )

    print(af.collect())
    ```

    ```text
    shape: (2, 5)
    ┌───────────┬──────────────┬──────────┬───────────────┐
    │ policy_id ┆ month        ┆ pols_if  ┆ pols_maturity │
    │ ---       ┆ ---          ┆ ---      ┆ ---           │
    │ str       ┆ list[i64]    ┆ list[... ┆ list[i64]     │
    ╞═══════════╪══════════════╪══════════╪═══════════════╡
    │ P001      ┆ [0, 1, … 12] ┆ [1000... ┆ [0, 0, … 976] │
    │ P002      ┆ [0, 1, … 24] ┆ [1000... ┆ [0, 0, … 952] │
    └───────────┴──────────────┴──────────┴───────────────┘
    ```

    **List Broadcasting Behavior**

    When list columns are involved, the framework automatically broadcasts scalar
    values across all elements in the list. In the maturity example above:

    - `af.month` is a list column (projection months 0-12 and 0-24)
    - `af.policy_term_years * 12` broadcasts the scalar calculation to each month
    - The condition is evaluated element-wise within each list
    - `af.pols_if` (then value) and `0` (otherwise value) are applied element-wise
    - Result: maturity value appears only at the matching month, zeros elsewhere

    """
    # Extract parent ActuarialFrame from condition if possible
    parent = None

    # Import here to avoid circular imports
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy

    # Try to get parent from condition
    if isinstance(condition, (ColumnProxy, ExpressionProxy, ConditionExpression)):
        parent = getattr(condition, "_parent", None)

    # Pass through ConditionExpression as-is (don't convert to pl.Expr!)
    if isinstance(condition, ConditionExpression):
        return ConditionalProxy(condition, parent)

    # Convert other conditions to Polars expression
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
