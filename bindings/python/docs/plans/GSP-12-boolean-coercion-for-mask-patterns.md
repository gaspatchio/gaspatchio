# GSP-12: Support boolean coercion for mask patterns

## Problem Statement

Actuaries frequently use boolean masks in formulas (e.g., `value * (time == target_time)`).
This pattern currently fails when comparing list columns to scalar columns:

```python
# Fails - can't compare list to scalar column
af.mask = af.duration_mth_t == af.maturity_month
# Error: cannot create expression literal for value of type ConditionExpression

# Also fails at collect time
af.result = af.pols_if * (af.duration_mth_t == af.maturity_month)
# SchemaError: could not evaluate comparison between list[i64] and i64
```

## Root Cause Analysis

### Issue 1: Direct comparison assignment

When assigning a comparison directly to a column:
```python
af.mask = af.duration_mth_t == af.maturity_month
```

1. `af.duration_mth_t == af.maturity_month` creates a `ConditionExpression`
2. `base.py:__setitem__` calls `_convert_to_expr(value)`
3. `_convert_to_expr` doesn't handle `ConditionExpression`, falls through to `pl.lit(value)`
4. `pl.lit(ConditionExpression)` fails

**Fix location**: `base.py:_convert_to_expr`

### Issue 2: Arithmetic with comparison fails at collect

When multiplying by a comparison:
```python
af.result = af.pols_if * (af.duration_mth_t == af.maturity_month)
```

1. Creates `ConditionExpression` for the comparison
2. `ColumnProxy.__mul__` calls `self.mul(other)` through dispatch
3. `dispatch.py:_unwrap(ConditionExpression)` returns `condition._expr` (raw Polars comparison)
4. Expression is created: `pols_if * (duration_mth_t == maturity_month)`
5. At collect time, Polars fails because it can't compare `list[i64]` to `i64`

**Fix location**: `dispatch.py:_unwrap`

## Existing Infrastructure

The solution already exists but isn't being used:

```python
# condition_expression.py
def _to_boolean_expr(self) -> pl.Expr:
    """Convert this condition to a boolean expression (0.0/1.0)."""
    if self._has_list_column(self.left):
        from gaspatchio_core.functions.vector import list_conditional
        return list_conditional(
            self.left, self.right, pl.lit(1.0), pl.lit(0.0), self.operator
        )
    # Scalar case - use standard Polars comparison, cast to float
    return self._expr.cast(pl.Float64)
```

This method:
- Detects if the left operand is a list column
- If so, uses `list_conditional` Rust plugin with `then=1.0, otherwise=0.0`
- Otherwise, uses native Polars comparison cast to Float64

## Implementation Plan

### Phase 1: Fix direct comparison assignment (Python-only)

**File: `gaspatchio_core/frame/base.py`**

Add `ConditionExpression` handling in `_convert_to_expr`:

```python
def _convert_to_expr(self, value: Any) -> pl.Expr:
    """Convert a value to a Polars expression."""
    from gaspatchio_core.column.condition_expression import ConditionExpression

    if isinstance(value, ColumnProxy):
        return pl.col(value.name)
    if isinstance(value, ExpressionProxy):
        return value._expr
    if isinstance(value, ConditionExpression):
        # Use _to_boolean_expr which handles list vs scalar columns
        return value._to_boolean_expr()
    if isinstance(value, pl.Expr):
        return value
    # ... rest unchanged
```

### Phase 2: Fix arithmetic with comparisons (Python-only)

**File: `gaspatchio_core/column/dispatch.py`**

Modify `_unwrap` to use `_to_boolean_expr()` for `ConditionExpression`:

```python
def _unwrap(arg: Any) -> Any:
    """Unwrap ColumnProxy, ExpressionProxy, or ConditionExpression to Polars expr."""
    from .column_proxy import ColumnProxy
    from .condition_expression import ConditionExpression
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr
    if isinstance(arg, ConditionExpression):
        # Use _to_boolean_expr() to handle list vs scalar columns properly
        return arg._to_boolean_expr()
    return arg
```

### Phase 3: Tests (TDD)

**File: `tests/column/test_boolean_mask_patterns.py`**

```python
"""Tests for boolean mask patterns: list == scalar and list * bool (GSP-12)."""

import pytest
import polars as pl
from gaspatchio_core import ActuarialFrame, when


class TestListComparisonToScalar:
    """Test list column compared to scalar column."""

    def test_direct_comparison_assignment(self):
        """af.mask = af.list_col == af.scalar_col should work."""
        af = ActuarialFrame({
            'duration_mth_t': [[0, 1, 2, 3]],
            'maturity_month': [2],
        })

        af.mask = af.duration_mth_t == af.maturity_month

        result = af.collect()
        # Should be [0.0, 0.0, 1.0, 0.0] for months 0,1,2,3 compared to maturity=2
        assert result['mask'].to_list() == [[0.0, 0.0, 1.0, 0.0]]

    def test_comparison_all_operators(self):
        """All comparison operators should work: ==, !=, <, <=, >, >=."""
        af = ActuarialFrame({
            'values': [[0, 1, 2, 3, 4]],
            'threshold': [2],
        })

        # Equal
        af.eq_mask = af.values == af.threshold
        # Not equal
        af.ne_mask = af.values != af.threshold
        # Less than
        af.lt_mask = af.values < af.threshold
        # Less than or equal
        af.le_mask = af.values <= af.threshold
        # Greater than
        af.gt_mask = af.values > af.threshold
        # Greater than or equal
        af.ge_mask = af.values >= af.threshold

        result = af.collect()
        assert result['eq_mask'].to_list() == [[0.0, 0.0, 1.0, 0.0, 0.0]]
        assert result['ne_mask'].to_list() == [[1.0, 1.0, 0.0, 1.0, 1.0]]
        assert result['lt_mask'].to_list() == [[1.0, 1.0, 0.0, 0.0, 0.0]]
        assert result['le_mask'].to_list() == [[1.0, 1.0, 1.0, 0.0, 0.0]]
        assert result['gt_mask'].to_list() == [[0.0, 0.0, 0.0, 1.0, 1.0]]
        assert result['ge_mask'].to_list() == [[0.0, 0.0, 1.0, 1.0, 1.0]]


class TestMultiplicationWithBooleanMask:
    """Test list * bool pattern."""

    def test_list_times_comparison_result(self):
        """af.pols_if * (af.month == af.maturity) should work."""
        af = ActuarialFrame({
            'duration_mth_t': [[0, 1, 2, 3]],
            'maturity_month': [2],
            'pols_if': [[100.0, 100.0, 100.0, 100.0]],
        })

        af.pols_maturity = af.pols_if * (af.duration_mth_t == af.maturity_month)

        result = af.collect()
        # pols_if * [0, 0, 1, 0] = [0, 0, 100, 0]
        assert result['pols_maturity'].to_list() == [[0.0, 0.0, 100.0, 0.0]]

    def test_ideal_actuarial_pattern(self):
        """The pattern from the Linear ticket should work."""
        af = ActuarialFrame({
            'duration_mth_t': [[0, 1, 2, 3, 4, 5]],
            'maturity_month': [3],
            'pols_if_bef_mat': [[1000.0, 995.0, 990.0, 985.0, 980.0, 975.0]],
        })

        # Natural actuarial formula
        af.pols_maturity = af.pols_if_bef_mat * (af.duration_mth_t == af.maturity_month)

        result = af.collect()
        # Only month 3 should have non-zero value
        expected = [0.0, 0.0, 0.0, 985.0, 0.0, 0.0]
        assert result['pols_maturity'].to_list() == [expected]


class TestScalarComparisonsUnaffected:
    """Ensure scalar-to-scalar comparisons still work normally."""

    def test_scalar_comparison_still_works(self):
        """Scalar comparisons should be unaffected."""
        af = ActuarialFrame({
            'age': [25, 45, 65, 75],
            'threshold': [65, 65, 65, 65],
        })

        af.is_senior = af.age >= af.threshold

        result = af.collect()
        # Should be boolean True/False, not float
        assert result['is_senior'].to_list() == [False, False, True, True]
```

## Expected Results After Implementation

```python
from gaspatchio_core import ActuarialFrame

af = ActuarialFrame({
    'duration_mth_t': [[0, 1, 2, 3]],
    'maturity_month': [2],
    'pols_if': [[100.0, 100.0, 100.0, 100.0]]
})

# Direct comparison - should create list[f64] of 0.0/1.0
af.mask = af.duration_mth_t == af.maturity_month
# Result: [[0.0, 0.0, 1.0, 0.0]]

# Multiplication pattern - should work naturally
af.pols_maturity = af.pols_if * (af.duration_mth_t == af.maturity_month)
# Result: [[0.0, 0.0, 100.0, 0.0]]
```

## Files to Modify

1. `gaspatchio_core/frame/base.py` - Add ConditionExpression handling in `_convert_to_expr`
2. `gaspatchio_core/column/dispatch.py` - Modify `_unwrap` to call `_to_boolean_expr()`
3. `tests/column/test_boolean_mask_patterns.py` - New test file

## Risk Assessment

**Low risk changes:**
- The `_to_boolean_expr()` method already exists and is well-tested via `when/then/otherwise`
- Changes are additive (new cases in existing functions)
- Scalar comparisons continue to work as before (the method casts to Float64 for scalars)

**Potential concerns:**
- Scalar comparisons will now return `Float64` instead of `Boolean` when assigned directly
  - This is actually correct for mask patterns (0.0/1.0 is more useful than True/False for arithmetic)
  - If boolean is needed, users can use `.cast(pl.Boolean)` or `when/then/otherwise`

## Dependencies

- Uses existing `list_conditional` Rust plugin (already tested and working)
- No new Rust code required
- Python-only changes
