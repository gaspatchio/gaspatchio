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

from typing import TYPE_CHECKING, Any, NoReturn

import polars as pl

from gaspatchio._semantic.ir import WhenThen
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.condition_expression import ConditionExpression
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.lowering.context import context_for
from gaspatchio.frame.lowering.ingress import to_node
from gaspatchio.frame.lowering.polars import shape_of

if TYPE_CHECKING:
    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.frame.base import ActuarialFrame


class ConditionalProxy:
    """Represents an in-progress conditional expression chain.

    Each ``.when()``/``.then()`` pair is recorded as a pair of semantic
    op-tree nodes; ``.otherwise()`` folds the chain into nested ``WhenThen``
    nodes, innermost-default-first, exactly the shape the reverse fold used
    to build by hand. Whether a case lowers to the ``list_conditional`` Rust
    kernel or to a native ``pl.when()`` is decided by lowering, from the
    frame's own dtypes -- see ``frame/lowering/polars.py``.
    """

    def __init__(self, condition: OpNode, parent: ActuarialFrame | None) -> None:
        """Initialize conditional with first condition.

        Args:
            condition: The first condition, as an op-tree node
            parent: Parent ActuarialFrame for context (can be None)

        """
        self._conditions: list[OpNode] = [condition]
        self._values: list[OpNode] = []
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
        from gaspatchio import ActuarialFrame, when

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
        from gaspatchio import ActuarialFrame, when

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
        self._values.append(to_node(value))
        return self

    def when(self, condition: Any) -> ConditionalProxy:  # noqa: ANN401
        """Add another condition (elif behavior).

        Args:
            condition: Additional condition expression

        Returns:
            Self for chaining .then()

        """
        self._conditions.append(_condition_to_node(condition, self._parent))
        return self

    def needs_list_broadcasting(self) -> bool:
        """Check if this conditional requires list broadcasting.

        Returns:
            True if any columns involved are list columns, False otherwise

        """
        ctx = context_for(self._parent)
        return any(shape_of(condition, ctx) == "list" for condition in self._conditions)

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
        from gaspatchio import ActuarialFrame, when

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
        node = to_node(value)
        for condition, then_value in reversed(
            list(zip(self._conditions, self._values, strict=True))
        ):
            node = WhenThen(cond=condition, then=then_value, otherwise=node)
        return ExpressionProxy._from_node(node, self._parent)  # noqa: SLF001

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
        self._refuse_unfinished()

    def _refuse_unfinished(self, *_operands: object) -> NoReturn:
        """Refuse a chain with no ``.otherwise()`` wherever it is used as a value.

        An unfinished chain has no value for a policy none of its tests holds
        for, so there is nothing to compute with. With no operators of its
        own, ``when(af.age > 60).then(1.2) == 1.2`` fell through to Python's
        identity test and answered a Python ``False`` -- stored, a column of
        False on every policy -- while ``+`` raised Python's own TypeError and
        the chain beside a column raised Polars' words about a literal.
        """
        msg = (
            "Conditional expression requires .otherwise(). "
            "Complete the chain with .otherwise(value) before using it: "
            "an unfinished when(...).then(...) has no value for a policy none "
            "of its tests holds for, so it cannot be compared, combined or "
            "computed with. "
            f"Current state: {len(self._conditions)} condition(s), "
            f"{len(self._values)} value(s)."
        )
        raise TypeError(msg)

    # Every operator, and a truth test, is refused in the chain's own words.
    __eq__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _refuse_unfinished  # type: ignore[assignment]
    __and__ = __rand__ = __or__ = __ror__ = __xor__ = __rxor__ = _refuse_unfinished
    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _refuse_unfinished
    __truediv__ = __rtruediv__ = __floordiv__ = __rfloordiv__ = _refuse_unfinished
    __mod__ = __rmod__ = __pow__ = __rpow__ = _refuse_unfinished
    __neg__ = __pos__ = __abs__ = __invert__ = __bool__ = _refuse_unfinished


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
    from gaspatchio import ActuarialFrame, when

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
    from gaspatchio import ActuarialFrame, when

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
    # Try to get parent from condition. A producer's expression bound to a
    # frame (``af.projection.anniversary_mask()``, a lookup keyed by a
    # column) carries one too; without it a per-period mask reached
    # ``pl.when`` as if it held one flag per policy.
    parent = None
    if isinstance(
        condition, (ColumnProxy, ExpressionProxy, ConditionExpression, ProxyAwareExpr)
    ):
        parent = getattr(condition, "_parent", None)

    return ConditionalProxy(_condition_to_node(condition, parent), parent)


def _condition_to_node(condition: Any, parent: ActuarialFrame | None) -> OpNode:  # noqa: ANN401
    """Turn one ``when()`` condition into the op-tree node standing for it.

    A predicate that is neither an expression nor attached to a frame has
    no meaning the chain can use, so it is refused by name rather than
    quietly becoming a constant.
    """
    if isinstance(condition, ConditionalProxy):
        condition._refuse_unfinished()  # noqa: SLF001 - its own refusal
    is_expression = getattr(condition, "_node", None) is not None or isinstance(
        condition, pl.Expr
    )
    if not is_expression and parent is None:
        msg = f"Condition must be an expression, got {type(condition)}"
        raise TypeError(msg)
    return to_node(condition)


# What the API reference documents from this module.
__all__ = ["ConditionalProxy", "when"]
