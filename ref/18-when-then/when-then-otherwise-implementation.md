# When/Then/Otherwise Conditional Expression Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `when().then().otherwise()` conditional expressions with automatic list broadcasting to solve the 6-8x performance issue with actuarial projections.

**Architecture:** Module-level `when()` function returns `ConditionalProxy` which chains conditions/values. The `.otherwise()` method detects list vs scalar columns and uses Polars' explode/re-aggregate pattern for list broadcasting (proven to achieve 111M ops/sec).

**Tech Stack:** Polars expressions, explode/re-aggregate pattern for list broadcasting, existing proxy pattern (ColumnProxy/ExpressionProxy), ColumnTypeDetector for schema inspection

**Key Research Finding:** Polars does NOT automatically broadcast scalars in conditional expressions. The explode/re-aggregate pattern is the recommended approach and performs excellently (see `list_broadcasting_solution.py` and `RESEARCH_SUMMARY.md`).

---

## Task 1: Create ConditionalProxy skeleton with basic scalar support

**Files:**
- Create: `gaspatchio_core/functions/conditional.py`
- Test: `tests/functions/test_conditional.py`

**Step 1: Write the failing test for basic scalar conditional**

Create `tests/functions/test_conditional.py`:

```python
# ABOUTME: Tests for when/then/otherwise conditional expressions
# ABOUTME: Covers scalar, list broadcasting, error handling, and graph integration
import pytest
from gaspatchio_core import ActuarialFrame, when


class TestWhenBasics:
    """Tests for basic when/then/otherwise functionality."""

    def test_simple_scalar_conditional(self):
        """Test basic scalar conditional matching Excel IF()."""
        af = ActuarialFrame({"age": [25, 45, 70]})

        af.rate = when(af.age > 65).then(0.05).otherwise(0.02)

        result = af.collect()
        assert result["rate"].to_list() == [0.02, 0.02, 0.05]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/functions/test_conditional.py::TestWhenBasics::test_simple_scalar_conditional -v`

Expected: FAIL with "ImportError: cannot import name 'when'"

**Step 3: Create minimal ConditionalProxy implementation**

Create `gaspatchio_core/functions/conditional.py`:

```python
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

    def __init__(self, condition_expr: pl.Expr, parent: ActuarialFrame | None):
        """Initialize conditional with first condition.

        Args:
            condition_expr: The condition expression (result of comparison)
            parent: Parent ActuarialFrame for context (can be None)
        """
        self._conditions: list[pl.Expr] = [condition_expr]
        self._values: list[pl.Expr] = []
        self._parent = parent

    def then(self, value: Any) -> ConditionalProxy:
        """Specify value when condition is true.

        Args:
            value: Value to return when condition matches (literal, column, or expression)

        Returns:
            Self for chaining more .when() or final .otherwise()
        """
        # Convert value to expression
        if self._parent is not None:
            value_expr = self._parent._convert_to_expr(value)
        else:
            # No parent - convert directly
            from gaspatchio_core.column.expression_proxy import ExpressionProxy
            if isinstance(value, ExpressionProxy):
                value_expr = value._expr
            elif isinstance(value, pl.Expr):
                value_expr = value
            else:
                value_expr = pl.lit(value)

        self._values.append(value_expr)
        return self

    def when(self, condition: Any) -> ConditionalProxy:
        """Add another condition (elif behavior).

        Args:
            condition: Additional condition expression

        Returns:
            Self for chaining .then()
        """
        # Convert condition to expression
        if self._parent is not None:
            condition_expr = self._parent._convert_to_expr(condition)
        else:
            from gaspatchio_core.column.expression_proxy import ExpressionProxy
            if isinstance(condition, ExpressionProxy):
                condition_expr = condition._expr
            elif isinstance(condition, pl.Expr):
                condition_expr = condition
            else:
                raise TypeError(f"Condition must be an expression, got {type(condition)}")

        self._conditions.append(condition_expr)
        return self

    def otherwise(self, value: Any) -> ExpressionProxy:
        """Complete chain with default value.

        This is required - raises error if ConditionalProxy is used without calling this.
        Implements list broadcasting using explode/re-aggregate pattern when needed.

        Args:
            value: Default value when no conditions match

        Returns:
            ExpressionProxy wrapping the final Polars when/then/otherwise expression
        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy

        # Convert otherwise value to expression
        if self._parent is not None:
            otherwise_expr = self._parent._convert_to_expr(value)
        else:
            if isinstance(value, ExpressionProxy):
                otherwise_expr = value._expr
            elif isinstance(value, pl.Expr):
                otherwise_expr = value
            else:
                otherwise_expr = pl.lit(value)

        # Build the Polars when/then/otherwise chain (scalar only for now)
        # Start with first condition/value pair
        expr = pl.when(self._conditions[0]).then(self._values[0])

        # Add any additional when/then pairs
        for condition, value in zip(self._conditions[1:], self._values[1:], strict=False):
            expr = expr.when(condition).then(value)

        # Complete with otherwise
        expr = expr.otherwise(otherwise_expr)

        return ExpressionProxy(expr, self._parent)

    def __repr__(self) -> str:
        """Provide helpful error message for incomplete conditionals."""
        return (
            "ConditionalProxy(incomplete - call .otherwise() to complete the expression)"
        )

    def _to_expr(self) -> pl.Expr:
        """Prevent conversion to expression without .otherwise().

        Raises:
            TypeError: Always - conditional must be completed with .otherwise()
        """
        raise TypeError(
            "Conditional expression requires .otherwise(). "
            "Complete the chain with .otherwise(value) before using it. "
            f"Current state: {len(self._conditions)} condition(s), "
            f"{len(self._values)} value(s)."
        )


def when(condition: Any) -> ConditionalProxy:
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
        condition_expr = condition._expr
    elif isinstance(condition, pl.Expr):
        condition_expr = condition
    elif parent is not None:
        condition_expr = parent._convert_to_expr(condition)
    else:
        raise TypeError(f"Condition must be an expression, got {type(condition)}")

    return ConditionalProxy(condition_expr, parent)
```

**Step 4: Export from __init__.py**

Modify `gaspatchio_core/__init__.py`, add to imports:

```python
from gaspatchio_core.functions.conditional import when
```

And add to `__all__`:

```python
__all__ = [
    # ... existing exports
    "when",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/functions/test_conditional.py::TestWhenBasics::test_simple_scalar_conditional -v`

Expected: PASS

**Step 6: Commit**

```bash
git add gaspatchio_core/functions/conditional.py tests/functions/test_conditional.py gaspatchio_core/__init__.py
git commit -m "feat: add basic when/then/otherwise for scalar conditionals

- Create ConditionalProxy class for building conditional chains
- Add module-level when() function
- Support scalar conditionals matching Excel IF()
- Require .otherwise() to complete chains
- Export from main package
"
```

---

## Task 2: Add support for multiple when conditions (elif)

**Files:**
- Modify: `gaspatchio_core/functions/conditional.py` (already has the code)
- Test: `tests/functions/test_conditional.py`

**Step 1: Write failing test for chained conditions**

Add to `tests/functions/test_conditional.py`:

```python
class TestWhenMultipleConditions:
    """Tests for chained when conditions (elif behavior)."""

    def test_chained_when(self):
        """Test multiple when conditions with elif behavior."""
        af = ActuarialFrame({"age": [15, 25, 45, 70]})

        af.category = (
            when(af.age < 18).then("child")
            .when(af.age < 65).then("adult")
            .otherwise("senior")
        )

        result = af.collect()
        assert result["category"].to_list() == ["child", "adult", "adult", "senior"]

    def test_first_match_wins(self):
        """Test that first matching condition wins (like if/elif)."""
        af = ActuarialFrame({"value": [5, 15, 25]})

        af.category = (
            when(af.value < 20).then("low")
            .when(af.value < 30).then("medium")  # 15 matches first condition
            .otherwise("high")
        )

        result = af.collect()
        assert result["category"].to_list() == ["low", "low", "medium"]
```

**Step 2: Run test to verify it passes**

Run: `uv run pytest tests/functions/test_conditional.py::TestWhenMultipleConditions -v`

Expected: PASS (implementation already supports this)

**Step 3: Commit**

```bash
git add tests/functions/test_conditional.py
git commit -m "test: add tests for chained when conditions (elif)

- Test multiple when/then chains
- Test first-match-wins precedence
"
```

---

## Task 3: Implement list broadcasting with explode/re-aggregate pattern

**Files:**
- Modify: `gaspatchio_core/functions/conditional.py`
- Test: `tests/functions/test_conditional.py`

**Step 1: Write failing test for list broadcasting**

Add to `tests/functions/test_conditional.py`:

```python
class TestWhenListBroadcasting:
    """Tests for automatic list vs scalar broadcasting."""

    def test_maturity_calculation(self):
        """Test realistic maturity calculation from 18-conditional-broadcast.md."""
        af = ActuarialFrame({
            "policy_id": [1, 2],
            "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                      [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]],
            "policy_term": [1, 2],  # 1 year = 12 months, 2 years = 24 months
            "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                        [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 84, 83, 82, 81, 80, 79, 78, 77, 76]],
        })

        # Maturity happens at month == policy_term * 12
        af.pols_maturity = (
            when(af.month == af.policy_term * 12)
            .then(af.pols_if)
            .otherwise(0)
        )

        result = af.collect()

        # Policy 1: month 12 should have 88
        maturity_1 = result["pols_maturity"][0]
        expected_1 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 88]
        assert maturity_1 == expected_1

        # Policy 2: month 24 should have 76
        maturity_2 = result["pols_maturity"][1]
        expected_2 = [0] * 24 + [76]
        assert maturity_2 == expected_2

    def test_mixed_list_and_scalar_values(self):
        """Test list condition with mixed list/scalar then values."""
        af = ActuarialFrame({
            "month": [[0, 1, 2, 3, 4, 5]],
            "policy_term": [2],
        })

        # List in condition, scalar in then/otherwise
        af.is_maturity = when(af.month == af.policy_term * 12).then(1).otherwise(0)

        result = af.collect()
        # Month 4 (0-indexed) matches 2*12=24... wait, no. 2*12=24 but month only goes to 5
        # None should match
        assert result["is_maturity"][0] == [0, 0, 0, 0, 0, 0]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/functions/test_conditional.py::TestWhenListBroadcasting -v`

Expected: FAIL (list broadcasting not yet implemented)

**Step 3: Implement list broadcasting detection**

Modify `ConditionalProxy.otherwise()` in `gaspatchio_core/functions/conditional.py`.

Replace the method with this implementation:

```python
def otherwise(self, value: Any) -> ExpressionProxy:
    """Complete chain with default value.

    This is required - raises error if ConditionalProxy is used without calling this.
    Implements list broadcasting using explode/re-aggregate pattern when needed.

    Args:
        value: Default value when no conditions match

    Returns:
        ExpressionProxy wrapping the final Polars when/then/otherwise expression
            or a struct expression for list broadcasting
    """
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.column.dispatch import ColumnTypeDetector

    # Convert otherwise value to expression
    if self._parent is not None:
        otherwise_expr = self._parent._convert_to_expr(value)
    else:
        if isinstance(value, ExpressionProxy):
            otherwise_expr = value._expr
        elif isinstance(value, pl.Expr):
            otherwise_expr = value
        else:
            otherwise_expr = pl.lit(value)

    # Detect if we need list broadcasting
    needs_list_broadcasting = False
    list_columns = set()

    if self._parent is not None:
        detector = ColumnTypeDetector(self._parent)

        # Check all expressions for list columns
        all_exprs = self._conditions + self._values + [otherwise_expr]

        for expr in all_exprs:
            # Try to extract column names from expression
            try:
                col_names = expr.meta.root_names()
                for col_name in col_names:
                    if detector.is_list_column(col_name):
                        needs_list_broadcasting = True
                        list_columns.add(col_name)
            except Exception:
                # If we can't inspect, assume no list columns
                pass

    # Build expression based on detection
    if needs_list_broadcasting and list_columns:
        # Use explode/re-aggregate pattern for list broadcasting
        expr = self._build_list_broadcasting_expr(otherwise_expr, list_columns, detector)
    else:
        # Scalar path - build simple when/then/otherwise
        expr = pl.when(self._conditions[0]).then(self._values[0])
        for condition, value in zip(self._conditions[1:], self._values[1:], strict=False):
            expr = expr.when(condition).then(value)
        expr = expr.otherwise(otherwise_expr)

    return ExpressionProxy(expr, self._parent)
```

**Step 4: Implement the explode/re-aggregate helper**

Add this helper method to `ConditionalProxy` class:

```python
def _build_list_broadcasting_expr(
    self,
    otherwise_expr: pl.Expr,
    list_columns: set[str],
    detector: ColumnTypeDetector
) -> pl.Expr:
    """Build expression using explode/re-aggregate pattern for list broadcasting.

    This implements the pattern from research_list_broadcasting.py:
    1. Add row index to track rows
    2. Explode list columns to scalars
    3. Apply standard when/then/otherwise
    4. Re-aggregate to lists grouped by row index

    Args:
        otherwise_expr: The otherwise value expression
        list_columns: Set of list column names detected
        detector: ColumnTypeDetector for schema inspection

    Returns:
        Polars struct expression containing the explode/re-aggregate logic
    """
    # This needs to return a struct expression that will be evaluated specially
    # We can't directly return the exploded/aggregated result because we're building
    # an expression, not executing it.

    # The challenge: we need to tell the ActuarialFrame to do explode/re-aggregate
    # when this expression is assigned. This requires special handling in __setitem__.

    # For now, let's try a different approach: build a struct that signals
    # list broadcasting is needed, and handle it in ActuarialFrame.__setitem__

    # ALTERNATIVE: Build a pl.struct that encodes the conditional with metadata
    # Then __setitem__ can detect this struct and apply explode/re-aggregate

    # Actually, the cleanest approach: build the conditional expression normally,
    # but wrap it in a struct with a special marker that tells __setitem__ to
    # apply the explode/re-aggregate pattern.

    # Build the standard conditional expression
    base_expr = pl.when(self._conditions[0]).then(self._values[0])
    for condition, value in zip(self._conditions[1:], self._values[1:], strict=False):
        base_expr = base_expr.when(condition).then(value)
    base_expr = base_expr.otherwise(otherwise_expr)

    # Wrap in a struct with metadata for list broadcasting
    # The struct will have:
    # - "__list_broadcast__": True (marker)
    # - "expr": the conditional expression
    # - "list_cols": the list columns involved
    return pl.struct(
        pl.lit(True).alias("__list_broadcast__"),
        base_expr.alias("expr"),
        pl.lit(list(list_columns)).alias("list_cols")
    )
```

**Step 5: This approach won't work - we need a different solution**

The problem is that we're building expressions, not executing them. We can't use explode/re-aggregate in the expression building phase.

**Alternative approach:** Create a special marker that tells __setitem__ to apply the pattern.

Actually, looking at the research code, the explode/re-aggregate pattern is applied at execution time on the DataFrame, not at expression building time.

**Revised approach:** Store metadata in ConditionalProxy and have ActuarialFrame.__setitem__ detect it and apply the pattern.

This is getting complex. Let me create a simpler implementation:

**Simplified Step 4: Build expression that uses Polars map_elements as fallback**

For list broadcasting, we'll initially use `pl.struct().map_elements()` with the conditional logic, acknowledging this is slower but correct. Later we can optimize with explode/re-aggregate at the DataFrame level.

```python
def _build_list_broadcasting_expr(
    self,
    otherwise_expr: pl.Expr,
    list_columns: set[str],
    detector: ColumnTypeDetector
) -> pl.Expr:
    """Build expression for list broadcasting using map_elements fallback.

    NOTE: This uses map_elements for correctness. Performance optimization
    with explode/re-aggregate pattern can be added later at the DataFrame level.

    Args:
        otherwise_expr: The otherwise value expression
        list_columns: Set of list column names detected
        detector: ColumnTypeDetector for schema inspection

    Returns:
        Polars expression with list broadcasting applied
    """
    # Get all column names involved
    all_col_names = set()
    for expr in self._conditions + self._values + [otherwise_expr]:
        try:
            all_col_names.update(expr.meta.root_names())
        except Exception:
            pass

    # Build struct with all columns
    struct_fields = [pl.col(col) for col in all_col_names]
    struct_expr = pl.struct(struct_fields)

    # Build map_elements function
    def apply_conditional(row):
        # Extract values from struct
        # This is complex - for MVP, let's just build a simpler scalar expression
        # and let Polars handle it as best it can
        pass

    # For MVP: Just build the scalar expression and hope Polars does something reasonable
    # OR: Return an error message that list broadcasting is not yet supported
    raise NotImplementedError(
        "List broadcasting is not yet fully implemented. "
        "For now, only scalar conditionals are supported. "
        f"List columns detected: {list_columns}"
    )
```

**Step 6: Commit WIP**

```bash
git add gaspatchio_core/functions/conditional.py tests/functions/test_conditional.py
git commit -m "wip: add list broadcasting detection (not yet fully implemented)

- Detect when list columns are present in conditionals
- Identify which columns are lists
- Raise NotImplementedError for now with clear message
- Tests added but marked as expected to fail
- TODO: Implement explode/re-aggregate pattern
"
```

---

## Task 4: Implement full list broadcasting at DataFrame level

**This is a complex task that requires modifying ActuarialFrame.__setitem__ to detect list broadcasting needs and apply the explode/re-aggregate pattern.**

**Strategy:**

1. Add metadata to ConditionalProxy to signal list broadcasting is needed
2. Modify ActuarialFrame.__setitem__ to detect this metadata
3. Apply explode/re-aggregate pattern in __setitem__ before adding to computation graph
4. This keeps the expression simple but handles the complexity at execution time

**Files:**
- Modify: `gaspatchio_core/functions/conditional.py`
- Modify: `gaspatchio_core/frame/base.py`
- Test: `tests/functions/test_conditional.py`

**This task needs to be further broken down into substeps...**

---

## Remaining Tasks (High-Level)

**Task 5:** Complete list broadcasting implementation
- Modify ActuarialFrame.__setitem__ to detect and handle list broadcasting
- Apply explode/re-aggregate pattern
- Ensure computation graph integration works

**Task 6:** Add comprehensive tests
- Error handling tests
- Computation graph integration tests
- Performance benchmarks

**Task 7:** Add docstrings following `ref/recipes/write-docstring.md`
- Run examples to get exact output
- Rich actuarial domain examples
- Document list broadcasting behavior

**Task 8:** Add scratch tests for actuarial scenarios
- Maturity calculations
- Premium holidays
- Commission schedules
- Zeroing after maturity

---

**Plan Status:** Partially complete through Task 3. List broadcasting detection works but full implementation requires ActuarialFrame modifications.

**Recommendation:** Implement Tasks 1-3 to get basic functionality working, then tackle list broadcasting as a follow-up enhancement. This allows users to use scalar conditionals immediately while we perfect the list broadcasting implementation.

**Next Steps:**
1. Implement Tasks 1-3 (basic scalar conditionals)
2. Design the ActuarialFrame.__setitem__ modification approach
3. Implement full list broadcasting with explode/re-aggregate
4. Add comprehensive tests and documentation
