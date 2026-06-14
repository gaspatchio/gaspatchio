# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

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
    It automatically routes to the list_conditional Rust plugin for list columns
    or standard Polars when/then/otherwise for scalar columns.
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
        from gaspatchio_core.column.condition_expression import ConditionExpression
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Handle ConditionExpression directly (don't try to convert)
        if isinstance(condition, ConditionExpression):
            self._conditions.append(condition)
            return self

        # Convert other conditions to expression
        if isinstance(condition, ExpressionProxy):
            condition_expr = condition._expr  # noqa: SLF001
        elif isinstance(condition, pl.Expr):
            condition_expr = condition
        elif self._parent is not None:
            condition_expr = self._parent._convert_to_expr(condition)  # noqa: SLF001
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
        return self._any_condition_has_list_columns()

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

        # Build expression - routes to plugin for lists, Polars for scalars
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

    def _extract_column_names(self, expr: pl.Expr) -> list[str]:
        """Extract column names from an expression, returning empty list on failure."""
        try:
            return expr.meta.root_names()
        except (AttributeError, RuntimeError):
            # meta.root_names() may fail for some expressions
            return []

    def _condition_has_list_columns(self, condition: Any) -> bool:  # noqa: ANN401
        """Check whether a condition involves a list-shaped operand.

        Reads the resolved shape from the condition (or its proxy) directly via
        the cached ``shape`` property when wrapped. For bare ``pl.Expr``
        conditions appended through chained ``.when()`` calls, falls back to
        ``_shape_from_expr_dtype`` against the parent frame so list-typed
        Polars predicates still route through ``list_conditional`` instead of
        colliding with scalar ``pl.when()``.
        """
        from gaspatchio_core.column.condition_expression import ConditionExpression
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        if isinstance(condition, (ConditionExpression, ExpressionProxy)):
            return condition.shape == "list"
        if isinstance(condition, pl.Expr):
            return self._expr_is_list_shaped(condition)
        return False

    def _any_condition_has_list_columns(self) -> bool:
        """Check if any condition in the chain involves list columns.

        Returns:
            True if any condition involves list columns

        """
        for condition in self._conditions:
            if self._condition_has_list_columns(condition):
                return True
        return False

    def _expr_is_list_shaped(self, expr: pl.Expr) -> bool:
        """Check whether a Polars expression resolves to a list-shaped output.

        Used by chain-shape detection to decide whether reverse-fold should
        run in 'list mode' (lifting scalar predicates through list_conditional
        so a scalar then() doesn't collide with a list-shaped acc).

        Routes through the shape SOT — `_shape_from_expr_dtype` probes the
        wrapped expression's dtype against the parent frame's `_df`.
        """
        if self._parent is None or not isinstance(expr, pl.Expr):
            return False

        from gaspatchio_core.column.shape import _shape_from_expr_dtype

        return _shape_from_expr_dtype(self._parent, expr) == "list"

    def _lower_one_case(  # noqa: PLR0911
        self,
        condition: Any,  # noqa: ANN401
        then_val: pl.Expr,
        acc: pl.Expr,
        *,
        acc_is_list: bool = False,
    ) -> tuple[pl.Expr, bool]:
        """Lower a single (condition, then, else=acc) tuple to a Polars expression.

        Returns (lowered_expr, output_is_list). The caller threads `output_is_list`
        as `acc_is_list` for the next iteration so the fold knows when the running
        accumulator becomes list-shaped.

        Routes per the design's per-case lowering rules:
        - ConditionExpression involving a list column -> list_conditional kernel
        - ExpressionProxy with _is_boolean_list -> list_conditional with mask
        - Scalar predicate where any operand (acc or then) is list-shaped ->
          list_conditional with the scalar predicate broadcast via `repeat_by`
          so left satisfies the kernel's List-dtype requirement
        - Otherwise -> native pl.when().then().otherwise()
        """
        from gaspatchio_core.column.condition_expression import ConditionExpression
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.functions.vector import list_conditional

        # Vector comparison predicate (ConditionExpression with list operands).
        # Normalize operand order so the list-typed side is on `left` (plugin
        # contract). Handles commuted predicates like (scalar) == af.list_col.
        if isinstance(condition, ConditionExpression) and self._condition_has_list_columns(
            condition
        ):
            left, right, operator = condition.normalize_for_list_path()
            return list_conditional(
                left=left,
                right=right,
                then_val=then_val,
                otherwise_val=acc,
                operator=operator,
            ), True

        # Vector boolean-mask predicate (Float64-list masks from &/|/~ on lists).
        # `condition.shape == "list"` distinguishes these from native pl.Boolean
        # masks (e.g. scalar `&`, `is_null`, `is_in`) which would route through
        # native pl.when() in the scalar branch below.
        if (
            isinstance(condition, ExpressionProxy)
            and condition.kind == "boolean_mask"
            and condition.shape == "list"
        ):
            return list_conditional(
                left=condition._expr,  # noqa: SLF001
                right=pl.lit(1.0),
                then_val=then_val,
                otherwise_val=acc,
                operator="eq",
            ), True

        # Bare ``pl.Expr`` that resolves to a list-shaped boolean mask — e.g.
        # ``pl.col(list_col).list.eval(pl.element() > k)`` produces ``list[bool]``.
        # Treat the same way as the proxy boolean_mask path: ``mask == 1.0``
        # under list_conditional.
        if (
            isinstance(condition, pl.Expr)
            and not isinstance(condition, (ConditionExpression, ExpressionProxy))
            and self._expr_is_list_shaped(condition)
        ):
            return list_conditional(
                left=condition,
                right=pl.lit(1.0),
                then_val=then_val,
                otherwise_val=acc,
                operator="eq",
            ), True

        # Scalar predicate over a list-shaped acc OR list-shaped then-branch:
        # broadcast via list_conditional. Without this,
        # `pl.when(scalar).then(scalar).otherwise(list_acc)` or
        # `pl.when(scalar).then(list).otherwise(scalar_acc)` raises
        # `SchemaError: failed to determine supertype of f64 and list[f64]`.
        # We broadcast the scalar predicate to list shape via repeat_by()
        # using the list-shaped operand's length.
        then_is_list = self._expr_is_list_shaped(then_val)
        if acc_is_list or then_is_list:
            if isinstance(condition, (ConditionExpression, ExpressionProxy)):
                cond_expr = condition._expr  # noqa: SLF001
            elif isinstance(condition, pl.Expr):
                cond_expr = condition
            else:
                msg = (
                    f"Unexpected condition type {type(condition)} "
                    "in chained when() lowering"
                )
                raise TypeError(msg)
            length_ref = acc.list.len() if acc_is_list else then_val.list.len()
            cond_broadcast = cond_expr.cast(pl.Float64).repeat_by(length_ref)
            return list_conditional(
                left=cond_broadcast,
                right=pl.lit(1.0),
                then_val=then_val,
                otherwise_val=acc,
                operator="eq",
            ), True

        # Scalar predicate over a scalar acc — native pl.when().then().otherwise()
        if isinstance(condition, (ConditionExpression, ExpressionProxy)):
            return pl.when(condition._expr).then(then_val).otherwise(acc), False  # noqa: SLF001

        if isinstance(condition, pl.Expr):
            return pl.when(condition).then(then_val).otherwise(acc), False

        msg = f"Unexpected condition type {type(condition)} in chained when() lowering"
        raise TypeError(msg)

    def _build_scalar_conditional(self, otherwise_expr: pl.Expr) -> pl.Expr:
        """Build conditional expression via per-case lowering + reverse-fold.

        Single-when (n=1) is treated as a degenerate chain — same lowering as
        the chained case, just one iteration. This means a scalar predicate
        over a list-shaped ``then`` (or vice versa) routes through
        ``list_conditional`` instead of native ``pl.when`` which can't resolve
        the supertype and produces ``Unknown`` dtype downstream.
        """
        acc = otherwise_expr
        acc_is_list = self._expr_is_list_shaped(otherwise_expr)
        for cond, then_val in reversed(
            list(zip(self._conditions, self._values, strict=True))
        ):
            acc, acc_is_list = self._lower_one_case(
                cond, then_val, acc, acc_is_list=acc_is_list
            )
        return acc

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

    # Pass through ExpressionProxy with kind="boolean_mask" (from binary ops)
    if isinstance(condition, ExpressionProxy) and condition.kind == "boolean_mask":
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
