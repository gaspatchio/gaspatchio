# Phase 2: list_conditional Plugin Integration Design

**Date:** 2025-11-12
**Status:** Ready for Implementation
**Goal:** Eliminate EXPLODE/GROUP_BY bottleneck in `when/then/otherwise` conditionals

---

## Executive Summary

This design solves the performance crisis where `when().then().otherwise()` conditionals on list columns cause OOM at 1K-10K model points due to EXPLODE operations consuming 75.9% of execution time.

**Solution:** Integrate the existing `list_conditional` Rust plugin into the `when/then/otherwise` API by wrapping comparison operations with metadata, enabling direct plugin calls without EXPLODE.

**Expected Impact:**
- Eliminate 4 of 4 remaining EXPLODE operations (75.9% of time)
- Enable 10K+ model points without OOM
- Maintain existing API - zero breaking changes for actuaries

---

## Problem Statement

### Current Performance Crisis

**Profiling Results (1,000 Model Points):**
```
Total execution time: 4.84ms

| Operation   | Count | Time (ms) | % of Total |
|-------------|-------|-----------|------------|
| EXPLODE     | 4     | 3.68ms    | 75.9%      |
| GROUP_BY    | 4     | 1.05ms    | 21.7%      |
| with_column | 33    | 0.12ms    | 2.4%       |
```

**Critical Issue:** EXPLODE + GROUP_BY = 97.6% of execution time

**The 4 EXPLODE operations:**
1. `pols_maturity` when/then/otherwise (model_projection.py:112-114)
2. `pols_if` when/then/otherwise (model_projection.py:119-123)
3. `acq_expense` when/then/otherwise (model_projection.py:209)
4. `commissions` when/then/otherwise (model_projection.py:224)

**Impact:**
- ❌ OOM at 1K-10K model points
- ❌ Cannot scale to production workloads
- ❌ EXPLODE pattern fundamentally doesn't scale

### Why Previous Attempt Failed

**Phase 2 Integration Attempt (from Appendix):**
- ✅ Rust plugin works perfectly in isolation
- ✅ PyO3 wrapper exports correctly
- ❌ Integration caused **double-wrapping bug**

**Root Cause:** Metadata semantic conflict
- Old metadata meaning: "Please apply EXPLODE for me"
- New metadata meaning: "I already optimized, skip EXPLODE"
- Result: Plugin returned `list[f64]`, but system wrapped it to `list[list[f64]]`

**Key Learning:** Cannot reuse `_list_broadcast_metadata` - need different approach.

---

## Design Overview

### Core Insight

**Don't reuse existing metadata** - instead, track comparison operator at creation time and route conditionals based on type detection.

**Flow:**
1. Comparison operators (`==`, `<`, etc.) return `ConditionExpression` wrapper
2. `ConditionExpression` stores operator metadata needed for plugin
3. `ConditionalProxy` detects type and calls plugin directly
4. **No metadata set** → no EXPLODE applied → no double-wrapping

### Architecture Diagram

```
Python Layer (Lazy - No Computation):
┌─────────────────────────────────────────────────────────────┐
│ af.month == af.term                                         │
│   ↓                                                          │
│ ColumnProxy.__eq__() creates ConditionExpression            │
│   - Stores: operator="eq", left=col("month"), right=term    │
│   - Returns: ConditionExpression (not ExpressionProxy)      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ when(condition).then(1.0).otherwise(0.0)                    │
│   ↓                                                          │
│ ConditionalProxy.otherwise() calls:                         │
│   _build_scalar_conditional()                               │
│     ↓                                                        │
│   Detects ConditionExpression                               │
│     ↓                                                        │
│   Calls list_conditional plugin:                            │
│     list_conditional(                                       │
│       left=col("month"),                                    │
│       right=term,                                           │
│       then_val=1.0,                                         │
│       otherwise_val=0.0,                                    │
│       operator="eq"                                         │
│     )                                                        │
│     ↓                                                        │
│   Returns pl.Expr (lazy, not computed)                      │
│     ↓                                                        │
│   Wraps in ExpressionProxy                                  │
│   ⚠️  DOES NOT SET _list_broadcast_metadata                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ af.result = expression                                      │
│   ↓                                                          │
│ ActuarialFrame.__setattr__()                                │
│   ↓                                                          │
│ No _list_broadcast_metadata → No EXPLODE applied            │
│   ↓                                                          │
│ Just adds column with plugin expression                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ af.collect()                                                │
│   ↓                                                          │
│ Rust Layer Execution:                                       │
│   - list_conditional plugin executes                        │
│   - Element-wise comparison on list column                  │
│   - Returns list[f64] directly                              │
│   - NO EXPLODE, NO GROUP_BY                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Design

### Component 1: ConditionExpression Class

**Location:** `gaspatchio_core/column/condition_expression.py` (new file)

**Purpose:** Wrap comparison expressions with metadata for plugin calls

**Implementation:**
```python
"""Condition expression wrapper for list_conditional plugin integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame


class ConditionExpression:
    """Wraps a comparison expression with metadata for list_conditional plugin.

    Created by ColumnProxy/ExpressionProxy comparison operators (__eq__, __lt__, etc.).
    Stores the operator type and operands needed to call list_conditional Rust plugin.

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
        result._is_boolean_list = True  # noqa: SLF001
        return result

    def __or__(self, other: ConditionExpression) -> ExpressionProxy:
        """Combine conditions with OR (|).

        Uses formula: 1 - ((1 - left) * (1 - right)) for element-wise OR

        Returns:
            ExpressionProxy wrapping combined boolean list expression
        """
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
        combined = pl.lit(1.0) - ((pl.lit(1.0) - left_bool) * (pl.lit(1.0) - right_bool))

        result = ExpressionProxy(combined, self._parent)
        result._is_boolean_list = True  # noqa: SLF001
        return result

    def __invert__(self) -> ExpressionProxy:
        """Negate condition with NOT (~).

        Uses formula: 1.0 - boolean_result for element-wise negation

        Returns:
            ExpressionProxy wrapping negated boolean list expression
        """
        from gaspatchio_core.column.expression_proxy import ExpressionProxy
        from gaspatchio_core.functions.vector import list_conditional

        # Convert to boolean list
        bool_result = list_conditional(
            self.left, self.right, pl.lit(1.0), pl.lit(0.0), self.operator
        )

        # NOT logic: 1 - boolean
        negated = pl.lit(1.0) - bool_result

        result = ExpressionProxy(negated, self._parent)
        result._is_boolean_list = True  # noqa: SLF001
        return result
```

**Key Design Decisions:**
- ✅ Has `._expr` and `._parent` for duck-type compatibility
- ✅ Stores operator, left, right for plugin call
- ✅ Binary operations convert to boolean lists eagerly (in expression tree)
- ✅ Binary operations return `ExpressionProxy` (no longer `ConditionExpression`)
- ✅ Sets `_is_boolean_list` flag for later detection

---

### Component 2: Comparison Operator Modifications

**Location:** `gaspatchio_core/column/column_proxy.py` (lines 91-119)

**Change:** Return `ConditionExpression` instead of `ExpressionProxy`

**Before:**
```python
def __eq__(self, other: Any) -> ExpressionProxy:
    other_expr = self._convert_other(other)
    return ExpressionProxy(self._to_expr() == other_expr, self._parent)
```

**After:**
```python
def __eq__(self, other: Any) -> ConditionExpression:
    from gaspatchio_core.column.condition_expression import ConditionExpression

    left_expr = self._to_expr()
    right_expr = self._convert_other(other)
    comparison_expr = left_expr == right_expr

    return ConditionExpression(
        expr=comparison_expr,
        parent=self._parent,
        operator="eq",
        left=left_expr,
        right=right_expr,
    )
```

**Apply to all 6 operators:**
- `__eq__` → `operator="eq"`
- `__ne__` → `operator="ne"`
- `__lt__` → `operator="lt"`
- `__lte__` → `operator="lte"`
- `__gt__` → `operator="gt"`
- `__gte__` → `operator="gte"`

**Also modify:** `gaspatchio_core/column/expression_proxy.py` (same changes)

---

### Component 3: ConditionalProxy Integration

**Location:** `gaspatchio_core/functions/conditional.py`

**Change 1: Update `_build_scalar_conditional()` method**

**Before:**
```python
def _build_scalar_conditional(self, otherwise_expr: pl.Expr) -> pl.Expr:
    """Build scalar conditional using Polars when/then/otherwise."""
    expr = pl.when(self._conditions[0]).then(self._values[0])

    for cond, val in zip(self._conditions[1:], self._values[1:], strict=False):
        expr = expr.when(cond).then(val)

    return expr.otherwise(otherwise_expr)
```

**After:**
```python
def _build_scalar_conditional(self, otherwise_expr: pl.Expr) -> pl.Expr:
    """Build conditional - uses list_conditional plugin for list columns."""
    from gaspatchio_core.column.condition_expression import ConditionExpression
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.functions.vector import list_conditional
    from loguru import logger

    # Only handle single condition for now
    if len(self._conditions) > 1:
        raise NotImplementedError(
            "Multiple chained .when() not yet supported with list_conditional plugin. "
            "Use separate conditionals or combine with & operator."
        )

    condition = self._conditions[0]
    then_val = self._convert_value_to_expr(self._values[0])

    # Try to use plugin first
    try:
        # Case 1: Direct comparison (ConditionExpression)
        if isinstance(condition, ConditionExpression):
            return list_conditional(
                left=condition.left,
                right=condition.right,
                then_val=then_val,
                otherwise_val=otherwise_expr,
                operator=condition.operator,
            )

        # Case 2: Binary operation result (ExpressionProxy with boolean list)
        elif isinstance(condition, ExpressionProxy) and hasattr(condition, '_is_boolean_list'):
            return list_conditional(
                left=condition._expr,
                right=pl.lit(1.0),
                then_val=then_val,
                otherwise_val=otherwise_expr,
                operator="eq",
            )

        # Case 3: Regular ExpressionProxy (might be scalar, try plugin anyway)
        elif isinstance(condition, ExpressionProxy):
            # Try using plugin - will fail if not a list column
            return list_conditional(
                left=condition._expr,
                right=pl.lit(True),
                then_val=then_val,
                otherwise_val=otherwise_expr,
                operator="eq",
            )

        else:
            # Unknown type - fall back to standard Polars
            raise TypeError(f"Unexpected condition type: {type(condition)}")

    except Exception as e:
        # Plugin failed (likely scalar column) - use standard Polars when/then
        logger.debug(f"list_conditional plugin failed, using standard Polars: {e}")
        return pl.when(condition._expr).then(then_val).otherwise(otherwise_expr)
```

**Change 2: Update `otherwise()` method**

**Before:**
```python
def otherwise(self, value: Any) -> ExpressionProxy:
    otherwise_expr = self._convert_value_to_expr(value)
    self._otherwise_expr = otherwise_expr

    self._list_columns = self._detect_list_columns(otherwise_expr)

    if self._list_columns:
        expr = self._build_scalar_conditional(otherwise_expr)
        result = ExpressionProxy(expr, self._parent)
        result._list_broadcast_metadata = {  # ← CAUSES DOUBLE-WRAPPING!
            "list_columns": self._list_columns,
            "conditional_expr": expr,
        }
        return result
    else:
        expr = self._build_scalar_conditional(otherwise_expr)
        return ExpressionProxy(expr, self._parent)
```

**After:**
```python
def otherwise(self, value: Any) -> ExpressionProxy:
    """Complete conditional chain with default value.

    Uses list_conditional plugin for list columns, eliminating EXPLODE pattern.
    """
    otherwise_expr = self._convert_value_to_expr(value)
    self._otherwise_expr = otherwise_expr

    # Build expression - now uses plugin internally for list columns
    expr = self._build_scalar_conditional(otherwise_expr)

    # Return ExpressionProxy WITHOUT _list_broadcast_metadata
    # The plugin already handled list operations - no EXPLODE needed!
    return ExpressionProxy(expr, self._parent)
```

**Critical Fix:** By NOT setting `_list_broadcast_metadata`, we prevent `ActuarialFrame.__setattr__()` from applying the EXPLODE pattern. This eliminates the double-wrapping bug.

---

## Implementation Strategy

### MVP (Minimum Viable Product)

**Goal:** Prove the concept works with smallest possible change

**MVP Scope:**
1. ✅ Create `ConditionExpression` class (basic version, no binary ops)
2. ✅ Modify `ColumnProxy.__eq__()` only (prove pattern works)
3. ✅ Update `ConditionalProxy._build_scalar_conditional()` (single condition only)
4. ✅ Update `ConditionalProxy.otherwise()` (remove metadata setting)
5. ✅ One test: `when(af.month == af.term).then(1.0).otherwise(0.0)`
6. ✅ Verify no EXPLODE in query plan

**MVP Success Criteria:**
- Test passes with correct results
- Query plan shows **zero EXPLODE operations**
- No double-wrapping bug
- Code is clean and understandable

**If MVP works → expand to:**
- Other comparison operators (`<`, `>`, `<=`, `>=`, `!=`)
- Binary operations (`&`, `|`, `~`)
- ExpressionProxy comparisons
- Comprehensive tests
- Error handling

### Full Implementation Phases

**Phase 1: Core Operators (Week 1)**
- Task 1: Create ConditionExpression class
- Task 2: Modify all 6 ColumnProxy comparison operators
- Task 3: Modify all 6 ExpressionProxy comparison operators
- Task 4: Update ConditionalProxy integration
- Task 5: Unit tests for each operator
- Task 6: Verify no EXPLODE in query plans

**Phase 2: Binary Operations (Week 2)**
- Task 7: Implement `__and__` in ConditionExpression
- Task 8: Implement `__or__` in ConditionExpression
- Task 9: Implement `__invert__` in ConditionExpression
- Task 10: Tests for binary operations
- Task 11: Integration test with model code

**Phase 3: Edge Cases & Production (Week 3)**
- Task 12: Error handling and fallback for scalar columns
- Task 13: Performance testing at 10K points
- Task 14: Memory profiling validation
- Task 15: Documentation updates
- Task 16: Code review and merge

---

## Testing Strategy

### Unit Tests

**File:** `tests/functions/test_conditional_plugin.py` (new)

**Test Classes:**

1. **TestSimpleComparisons**
   - `test_eq_operator_scalar_then_otherwise()`
   - `test_lt_operator()`
   - `test_gt_operator()`
   - `test_lte_operator()`
   - `test_gte_operator()`
   - `test_ne_operator()`
   - `test_list_then_value()`
   - `test_list_otherwise_value()`

2. **TestBinaryOperations**
   - `test_and_operation()`
   - `test_or_operation()`
   - `test_not_operation()`
   - `test_complex_combination()` (e.g., `(a & b) | c`)

3. **TestEdgeCases**
   - `test_scalar_column_fallback()`
   - `test_chained_when_raises_error()`
   - `test_null_handling()`
   - `test_empty_list_handling()`

4. **TestNoExplodeInPlan**
   - `test_no_explode_simple_comparison()`
   - `test_no_explode_binary_operation()`
   - `test_no_explode_complex_model()`

### Integration Tests

**File:** `tests/integration/test_conditional_integration.py` (new)

**Tests:**
- `test_full_model_10k_points_no_oom()`
- `test_all_four_conditionals_from_profiling()`
- `test_numerical_accuracy_vs_explode_method()`

### Performance Tests

**Validation:**
1. Run profiler before changes (baseline)
2. Run profiler after changes
3. Compare:
   - EXPLODE count: 4 → 0
   - Total time: 4.84ms → ~0.5ms (90% faster)
   - Memory: No OOM at 10K points

---

## Edge Cases and Limitations

### Supported Cases

✅ **Simple comparisons with scalar then/otherwise**
```python
af.loading = when(af.age >= 65).then(0.002).otherwise(0.0)
```

✅ **Simple comparisons with list then/otherwise**
```python
af.maturity = when(af.month == af.term_months).then(af.benefit).otherwise(0.0)
```

✅ **Binary AND operation**
```python
af.extra = when((af.age >= 65) & (af.sum_assured > 500000)).then(0.002).otherwise(0.0)
```

✅ **Binary OR operation**
```python
af.discount = when((af.age < 30) | (af.duration > 10)).then(0.1).otherwise(0.0)
```

✅ **Binary NOT operation**
```python
af.standard = when(~(af.age >= 65)).then(1.0).otherwise(0.0)
```

✅ **Scalar column conditionals** (fallback to standard Polars)
```python
af.category = when(af.age > 65).then("senior").otherwise("standard")
```

### Not Supported (Initially)

❌ **Chained when() conditions**
```python
# NOT SUPPORTED - Raises NotImplementedError
af.rate = when(af.age < 35).then(0.001) \
         .when(af.age < 50).then(0.002) \
         .otherwise(0.003)

# WORKAROUND - Nest conditionals
af.rate = when(af.age < 35).then(0.001).otherwise(
    when(af.age < 50).then(0.002).otherwise(0.003)
)
```

**Rationale:** Chained when() would require handling multiple conditions in plugin call. Can be added later if needed, but nested conditionals work fine.

---

## Error Handling

### Fallback Strategy

**Approach:** Try plugin first, fall back to standard Polars if it fails

**Implementation:**
```python
try:
    # Attempt to use list_conditional plugin
    return list_conditional(...)
except Exception as e:
    # Plugin failed - likely scalar column
    logger.debug(f"list_conditional plugin failed, using standard Polars: {e}")
    return pl.when(condition._expr).then(then_val).otherwise(otherwise_expr)
```

**Cases Handled:**
- ✅ Scalar columns (plugin expects List type)
- ✅ Unsupported data types
- ✅ Unknown edge cases

**Logging:**
- Debug-level logs for fallback (not errors)
- Helps diagnose why plugin wasn't used

---

## Performance Expectations

### Current State (Baseline)

**1,000 Model Points:**
- Total time: 4.84ms
- EXPLODE: 3.68ms (75.9%)
- GROUP_BY: 1.05ms (21.7%)
- EXPLODE + GROUP_BY: 97.6% of time

**Memory:** OOM at 1K-10K points

### Expected After Implementation

**1,000 Model Points:**
- Total time: ~0.5ms (90% faster)
- EXPLODE: 0ms (0 operations)
- GROUP_BY: 0ms (0 operations)
- All computation in Rust plugins

**10,000 Model Points:**
- Total time: ~5ms (scales linearly)
- Memory: ~170MB (no OOM)

**100,000 Model Points:**
- Total time: ~50ms
- Memory: ~1.7GB (fits in laptop RAM)

### Benchmark Expectations

**list_conditional performance (1,000 rows × 240 elements):**
- EXPLODE approach: ~3.5ms
- Plugin approach: ~65μs
- **Speedup: 54x**

---

## Success Metrics

### Technical Metrics

1. **EXPLODE Elimination**
   - Before: 4 EXPLODE operations
   - After: 0 EXPLODE operations
   - ✅ 100% elimination

2. **Performance**
   - Before: 4.84ms @ 1K points
   - After: <0.5ms @ 1K points
   - ✅ >90% speedup

3. **Scalability**
   - Before: OOM at 1K-10K points
   - After: 100K points in <50ms
   - ✅ 10-100x scale improvement

4. **Memory**
   - Before: OOM
   - After: 170MB @ 1K points, 1.7GB @ 100K points
   - ✅ Predictable, linear scaling

### Quality Metrics

1. **Test Coverage**
   - ✅ All 6 comparison operators tested
   - ✅ Binary operations tested
   - ✅ Edge cases covered
   - ✅ Integration tests pass
   - ✅ No numerical regressions

2. **Code Quality**
   - ✅ Type hints on all new code
   - ✅ Docstrings with examples
   - ✅ Clean error messages
   - ✅ Passes ruff linting

3. **API Stability**
   - ✅ Zero breaking changes
   - ✅ Existing code works unchanged
   - ✅ Graceful fallback for edge cases

---

## Comparison with Phase 1 (list_pow)

### What Phase 1 Did Right

✅ **Simple integration point:** `discount_factor()` method
✅ **Clear ownership:** Finance accessor owns the optimization
✅ **No metadata needed:** Direct plugin call, no signaling required
✅ **Clean success:** 23% speedup, zero complexity

### What Phase 2 Learns

✅ **Different approach:** Don't reuse `_list_broadcast_metadata`
✅ **Type-based routing:** Use `ConditionExpression` vs `ExpressionProxy`
✅ **No signaling:** Plugin call returns result directly
✅ **Graceful fallback:** Try plugin, fall back to Polars

### Key Differences

| Aspect | Phase 1 (list_pow) | Phase 2 (list_conditional) |
|--------|-------------------|---------------------------|
| **Integration Point** | Single method | Comparison operators |
| **Metadata Used** | None | Type detection only |
| **Fallback Needed** | No | Yes (scalar columns) |
| **Binary Operations** | N/A | Supported |
| **Complexity** | Low | Medium |
| **Impact** | 23% speedup | 90% speedup |

---

## Risks and Mitigations

### Risk 1: Type Detection Failure

**Risk:** `isinstance()` checks fail or miss cases
**Mitigation:** Fallback to standard Polars when/then
**Impact:** Low - just uses EXPLODE for that case

### Risk 2: Binary Operations Break

**Risk:** `__and__`, `__or__`, `__invert__` have bugs
**Mitigation:** Comprehensive tests, MVP approach
**Impact:** Medium - but rare usage pattern

### Risk 3: Performance Regression on Scalar Columns

**Risk:** Try/except overhead slows scalar conditionals
**Mitigation:** Benchmark scalar performance
**Impact:** Low - scalar conditionals are fast anyway

### Risk 4: Chained when() User Confusion

**Risk:** NotImplementedError frustrates users
**Mitigation:** Clear error message with workaround
**Impact:** Low - can add support later if needed

---

## Future Enhancements

### Post-MVP Improvements

1. **Chained when() support**
   - Handle multiple `.when().when().when()` chains
   - Requires plugin to accept multiple conditions
   - Or nest conditionals automatically

2. **SIMD optimization**
   - Rust plugin uses SIMD for comparisons
   - 2-4x additional speedup possible

3. **GPU acceleration**
   - For 1M+ policy projections
   - Use cuDF or similar for list operations

4. **Integer list support**
   - Currently Float64 only
   - Add Int64 variant for counters

---

## MVP Implementation Results (2025-11-12)

### What We Learned

**✅ MVP Successfully Completed**

The MVP implementation validated the core design approach and proved the concept works:

1. **Query Plan Verification**
   ```
   WITH_COLUMNS:
   [col("month").list_conditional([col("term"), 1.0, 0.0]).alias("result")]
   ```
   - **Zero EXPLODE operations** - Successfully eliminated!
   - Plugin call visible in query plan
   - Test passes with correct results: `[0.0, 0.0, 1.0, 0.0]`

2. **Key Implementation Insights**

   **Critical Discovery: `when()` must pass through `ConditionExpression` as-is**
   - Original design didn't account for `when()` function converting conditions to `pl.Expr`
   - **Fix:** Added `isinstance(condition, ConditionExpression)` check in `when()` to return `ConditionalProxy(condition, parent)` directly
   - Without this, the metadata would be lost before reaching `_build_scalar_conditional()`

3. **Type System Works Perfectly**
   - `isinstance(condition, ConditionExpression)` detection in `_build_scalar_conditional()` works
   - No metadata signaling needed - type-based routing is clean and explicit
   - Graceful fallback to standard Polars for `ExpressionProxy` conditions

4. **No Double-Wrapping Bug**
   - Removing `_list_broadcast_metadata` setting in `otherwise()` successfully prevents double-wrapping
   - Plugin returns `list[f64]` directly, no unwanted nesting
   - ActuarialFrame.__setattr__() doesn't apply EXPLODE pattern

5. **MVP Scope Was Right Size**
   - Single `==` operator proved the concept
   - Single condition restriction simplified initial implementation
   - Clear path to expand to other operators now established

### Implementation Commits

**Commit:** `462677f` - feat(python): integrate list_conditional plugin into when/then/otherwise (MVP)

**Files Modified:**
- `gaspatchio_core/column/condition_expression.py` (new) - 62 lines
- `gaspatchio_core/column/column_proxy.py` - Modified `__eq__()`
- `gaspatchio_core/functions/conditional.py` - Modified `_build_scalar_conditional()`, `otherwise()`, `when()`
- `tests/functions/test_conditional_plugin_mvp.py` (new) - MVP test

**Lines of Code:** ~150 LOC for complete MVP

### Next Steps for Full Implementation

Based on MVP learnings, the full implementation path is clear:

**Phase 1: All Comparison Operators** (straightforward, copy `__eq__()` pattern)
- Implement `__ne__`, `__lt__`, `__le__`, `__gt__`, `__gte__` in `ColumnProxy`
- Implement same 6 operators in `ExpressionProxy`
- Add tests for each operator
- Estimated: 2-3 hours

**Phase 2: Binary Operations** (more complex, but design is solid)
- Implement `__and__`, `__or__`, `__invert__` in `ConditionExpression`
- These convert to boolean lists and return `ExpressionProxy` with `_is_boolean_list` flag
- Update `_build_scalar_conditional()` to handle `_is_boolean_list` flag
- Add tests for binary operations
- Estimated: 3-4 hours

**Phase 3: Edge Cases & Production** (validation and cleanup)
- Remove single condition restriction (support chained `.when()`)
- Comprehensive test suite
- Performance benchmarking at 10K points
- Documentation updates
- Code review and merge
- Estimated: 4-5 hours

**Total Estimated Time:** 10-12 hours to complete full implementation

### Confidence Level

**Very High (95%+)**

The MVP proved every critical assumption:
- ✅ Type-based routing works
- ✅ No double-wrapping bug
- ✅ Plugin call succeeds
- ✅ Zero EXPLODE in query plan
- ✅ Correct numerical results
- ✅ Clean, maintainable code

The only unknowns remaining are:
- Binary operations implementation details (design is solid, just needs coding)
- Performance benchmarking numbers (expected to match predictions)

---

## Conclusion

This design solves the critical performance bottleneck by integrating the `list_conditional` Rust plugin into the `when/then/otherwise` API without falling into the double-wrapping trap that blocked the previous attempt.

**Key Innovation:** Track operator metadata at comparison creation time, detect via type system, call plugin directly without metadata signaling.

**MVP Results:**
- ✅ Zero EXPLODE operations confirmed
- ✅ Plugin integration works perfectly
- ✅ Type-based routing validated
- ✅ No double-wrapping bug
- ✅ Clean, maintainable code

**Expected Full Implementation Outcome:**
- ✅ 90% speedup at all scales
- ✅ Eliminate OOM issues
- ✅ Zero API breaking changes
- ✅ All 6 comparison operators
- ✅ Binary operations (&, |, ~)

**Status:** MVP Complete → Ready for Full Implementation → Production
