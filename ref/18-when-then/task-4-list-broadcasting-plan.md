# Task 4+: List Broadcasting Implementation Plan

**Date:** 2025-01-10
**Status:** Design Phase - Not Yet Implemented
**Prerequisite:** Tasks 1-3 Complete ✅

---

## Executive Summary

**Goal:** Enable `when().then().otherwise()` to work with list columns using Polars' explode/re-aggregate pattern for 6-8x performance improvement over `map_elements`.

**Current State:**
- ✅ Scalar conditionals work perfectly
- ✅ List column detection works (raises NotImplementedError)
- ✅ Research complete - explode/re-aggregate achieves 111M ops/sec
- ❌ List broadcasting not yet implemented

**What Users Want to Write:**
```python
# Replace slow map_elements:
af.pols_maturity = (
    when(af.month == af.policy_term * 12)
    .then(af.surviving_at_t)
    .otherwise(0.0)
)
```

**Challenge:** Polars does NOT automatically broadcast scalars in conditional expressions when list columns are involved. We must implement the explode/re-aggregate pattern ourselves.

---

## The Core Problem

### What Polars Does

**Scalar conditionals (works now):**
```python
when(pl.col("age") > 65).then(0.05).otherwise(0.02)
# age=[25, 45, 70] → rate=[0.02, 0.02, 0.05] ✅
```

**List conditionals (doesn't auto-broadcast):**
```python
when(pl.col("month") == pl.col("policy_term") * 12).then(pl.col("pols_if")).otherwise(0.0)
# month=[[0,1,2,...12]], policy_term=[1]
# Polars doesn't know to broadcast scalar 12 to match list length ❌
```

### Why map_elements is Slow

Current workaround (6-8x slower):
```python
def maturity_logic(row):
    # Python function - can't be optimized by Polars
    months = row["month"]
    maturity_month = row["policy_term"] * 12
    surviving = row["surviving_at_t"]
    return [surv if m == maturity_month else 0.0 for m, surv in zip(months, surviving)]

af.pols_maturity = pl.struct(...).map_elements(maturity_logic, ...)
```

**Why it's slow:**
- Python function call overhead per row
- No SIMD vectorization
- No Polars query optimizer
- Serialization/deserialization costs

---

## The Explode/Re-aggregate Solution

### How It Works

**Pattern:**
```python
(
    df.with_row_index("_row_id")           # 1. Track rows
    .explode([list_col, then_col])         # 2. Explode lists to scalars
    .with_columns(                          # 3. Apply scalar conditional
        result_col=pl.when(...)
            .then(pl.col(then_col))
            .otherwise(otherwise_value)
    )
    .group_by("_row_id", maintain_order=True)  # 4. Re-aggregate
    .agg([                                  # 5. Collect back to lists
        pl.col(list_col),
        pl.col(scalar_col).first(),
        pl.col(then_col),
        pl.col(result_col),
    ])
    .drop("_row_id")                       # 6. Clean up
)
```

### Visual Example

**Input:**
```
┌───────────┬─────────────┬──────────────┬───────────────────┐
│ policy_id │ policy_term │ month        │ pols_if           │
│ 1         │ 1           │ [0,1,...,12] │ [100,99,...,88]   │
└───────────┴─────────────┴──────────────┴───────────────────┘
```

**After with_row_index:**
```
┌─────────┬───────────┬─────────────┬──────────────┬───────────────────┐
│ _row_id │ policy_id │ policy_term │ month        │ pols_if           │
│ 0       │ 1         │ 1           │ [0,1,...,12] │ [100,99,...,88]   │
└─────────┴───────────┴─────────────┴──────────────┴───────────────────┘
```

**After explode:**
```
┌─────────┬───────────┬─────────────┬───────┬─────────┐
│ _row_id │ policy_id │ policy_term │ month │ pols_if │
│ 0       │ 1         │ 1           │ 0     │ 100     │
│ 0       │ 1         │ 1           │ 1     │ 99      │
│ 0       │ 1         │ 1           │ 2     │ 98      │
│ ...     │ ...       │ ...         │ ...   │ ...     │
│ 0       │ 1         │ 1           │ 12    │ 88      │  ← maturity month!
└─────────┴───────────┴─────────────┴───────┴─────────┘
```

**After with_columns (conditional):**
```
┌─────────┬───────┬─────────┬──────────────┐
│ _row_id │ month │ pols_if │ pols_maturity│
│ 0       │ 0     │ 100     │ 0.0          │  ← 0 != 12
│ 0       │ 1     │ 99      │ 0.0          │  ← 1 != 12
│ ...     │ ...   │ ...     │ ...          │
│ 0       │ 12    │ 88      │ 88.0         │  ← 12 == 12 ✅
└─────────┴───────┴─────────┴──────────────┘
```

**After group_by + agg (back to lists):**
```
┌───────────┬─────────────┬──────────────┬─────────────────┬─────────────────────┐
│ policy_id │ policy_term │ month        │ pols_if         │ pols_maturity       │
│ 1         │ 1           │ [0,1,...,12] │ [100,99,...,88] │ [0.0,0.0,...,88.0]  │
└───────────┴─────────────┴──────────────┴─────────────────┴─────────────────────┘
```

### Why It's Fast

**Performance characteristics:**
- ✅ Pure Polars operations (native Rust)
- ✅ SIMD vectorization on scalar operations
- ✅ Polars query optimizer can work with it
- ✅ 111M operations/sec (measured - see `list_broadcasting_solution.py`)
- ✅ 6-8x faster than `map_elements`

---

## Implementation Strategy

### Architecture Decision

**Two possible approaches:**

#### Approach A: Expression-Level (Rejected)

Build the explode/re-aggregate into the expression tree itself.

**Problems:**
- Polars expressions can't contain explode/aggregate operations
- Would break computation graph integration
- Expressions must be "simple" - just column operations

#### Approach B: DataFrame-Level (Recommended) ✅

Detect list broadcasting in `ActuarialFrame.__setitem__` and apply the pattern there.

**Advantages:**
- ✅ Keeps expression building clean
- ✅ Works with computation graph (tracing)
- ✅ All complexity isolated in one place
- ✅ Easy to test and debug

### Implementation Location

**File:** `gaspatchio_core/frame/base.py`

**Method:** `ActuarialFrame.__setitem__()`

**Current implementation:**
```python
def __setitem__(self, key: str, value: Any):
    """Handle column assignment using df['column'] = value."""
    if key not in self._column_order:
        self._column_order.append(key)
        self._refresh_attr_columns_set()
    try:
        expr = self._convert_to_expr(value)  # ← ConditionalProxy → ExpressionProxy here

        if self._tracing:
            append_operation_to_graph(self, key, expr)
        else:
            self._df = self._df.with_columns(expr.alias(key))
```

**Proposed modification:**
```python
def __setitem__(self, key: str, value: Any):
    """Handle column assignment using df['column'] = value."""
    if key not in self._column_order:
        self._column_order.append(key)
        self._refresh_attr_columns_set()
    try:
        # Check if value is ConditionalProxy with list broadcasting
        if isinstance(value, ConditionalProxy) and value.needs_list_broadcasting():
            # Apply explode/re-aggregate pattern
            self._apply_conditional_list_broadcasting(key, value)
        else:
            # Standard path
            expr = self._convert_to_expr(value)

            if self._tracing:
                append_operation_to_graph(self, key, expr)
            else:
                self._df = self._df.with_columns(expr.alias(key))
```

---

## Detailed Task Breakdown

### Task 4.1: Add Metadata to ConditionalProxy

**File:** `gaspatchio_core/functions/conditional.py`

**Changes needed:**

1. **Add method to check if list broadcasting is needed:**
   ```python
   def needs_list_broadcasting(self) -> bool:
       """Check if this conditional requires list broadcasting."""
       if self._parent is None:
           return False

       list_columns = self._detect_list_columns(self._otherwise_expr)
       return len(list_columns) > 0
   ```

2. **Store detected list columns:**
   ```python
   def __init__(self, condition_expr: pl.Expr, parent: ActuarialFrame | None):
       self._conditions: list[pl.Expr] = [condition_expr]
       self._values: list[pl.Expr] = []
       self._parent = parent
       self._list_columns: set[str] | None = None  # ← Add this
   ```

3. **Populate during otherwise():**
   ```python
   def otherwise(self, value: Any) -> ExpressionProxy:
       # ... convert otherwise_expr ...

       # Detect and store list columns
       self._list_columns = self._detect_list_columns(otherwise_expr)

       if self._list_columns:
           # Don't raise NotImplementedError anymore
           # Return ExpressionProxy that signals list broadcasting needed
           return ExpressionProxy(self._build_placeholder_expr(), self._parent)
       else:
           # Scalar path
           return ExpressionProxy(self._build_scalar_conditional(otherwise_expr), self._parent)
   ```

4. **Add method to get broadcasting metadata:**
   ```python
   def get_list_broadcasting_metadata(self) -> dict[str, Any]:
       """Get metadata needed for DataFrame-level list broadcasting."""
       return {
           "conditions": self._conditions,
           "values": self._values,
           "otherwise_expr": self._otherwise_expr,
           "list_columns": self._list_columns,
       }
   ```

### Task 4.2: Modify ActuarialFrame.__setitem__

**File:** `gaspatchio_core/frame/base.py`

**Changes needed:**

1. **Import ConditionalProxy:**
   ```python
   from gaspatchio_core.functions.conditional import ConditionalProxy
   ```

2. **Add detection in __setitem__:**
   ```python
   def __setitem__(self, key: str, value: Any):
       if key not in self._column_order:
           self._column_order.append(key)
           self._refresh_attr_columns_set()

       # Detect ConditionalProxy with list broadcasting
       if isinstance(value, ConditionalProxy) and value.needs_list_broadcasting():
           self._apply_conditional_list_broadcasting(key, value)
           return

       # Standard path for scalars and other expressions
       try:
           expr = self._convert_to_expr(value)
           # ... rest of existing code
   ```

3. **Add list broadcasting method:**
   ```python
   def _apply_conditional_list_broadcasting(
       self,
       key: str,
       conditional: ConditionalProxy
   ) -> None:
       """Apply explode/re-aggregate pattern for list broadcasting.

       Args:
           key: Name of column to create
           conditional: ConditionalProxy with list broadcasting metadata
       """
       metadata = conditional.get_list_broadcasting_metadata()

       # Build the explode/re-aggregate expression
       result_df = self._build_list_broadcasting_df(key, metadata)

       # Handle tracing vs direct execution
       if self._tracing:
           # For tracing: store the operation in computation graph
           # This is complex - may need special handling
           raise NotImplementedError(
               "List broadcasting with computation graph tracing not yet supported. "
               "Use optimize mode for now."
           )
       else:
           # Direct execution: replace DataFrame
           self._df = result_df
   ```

4. **Implement explode/re-aggregate builder:**
   ```python
   def _build_list_broadcasting_df(
       self,
       result_col: str,
       metadata: dict[str, Any]
   ) -> pl.DataFrame:
       """Build DataFrame with list broadcasting using explode/re-aggregate.

       Args:
           result_col: Name of output column
           metadata: Broadcasting metadata from ConditionalProxy

       Returns:
           DataFrame with result_col added
       """
       conditions = metadata["conditions"]
       values = metadata["values"]
       otherwise_expr = metadata["otherwise_expr"]
       list_columns = metadata["list_columns"]

       # Identify all columns involved
       all_columns = set()
       for expr in conditions + values + [otherwise_expr]:
           try:
               all_columns.update(expr.meta.root_names())
           except (AttributeError, RuntimeError):
               pass

       # Separate list vs scalar columns
       scalar_columns = all_columns - list_columns

       # Build explode/re-aggregate
       return (
           self._df
           .with_row_index("_row_id")
           .explode(list(list_columns))  # Explode all list columns
           .with_columns(
               **{
                   result_col: self._build_conditional_expr(
                       conditions, values, otherwise_expr
                   )
               }
           )
           .group_by("_row_id", maintain_order=True)
           .agg([
               # Aggregate list columns back
               *[pl.col(col) for col in list_columns],
               # Keep scalar columns (take first)
               *[pl.col(col).first() for col in scalar_columns],
               # Aggregate result column
               pl.col(result_col),
           ])
           .drop("_row_id")
       )

   def _build_conditional_expr(
       self,
       conditions: list[pl.Expr],
       values: list[pl.Expr],
       otherwise_expr: pl.Expr
   ) -> pl.Expr:
       """Build standard when/then/otherwise expression."""
       expr = pl.when(conditions[0]).then(values[0])
       for condition, value in zip(conditions[1:], values[1:], strict=False):
           expr = expr.when(condition).then(value)
       return expr.otherwise(otherwise_expr)
   ```

### Task 4.3: Update Tests

**File:** `tests/functions/test_conditional.py`

**Changes needed:**

1. **Remove pytest.raises from list broadcasting tests:**
   ```python
   def test_maturity_calculation(self) -> None:
       """Test realistic maturity calculation."""
       af = ActuarialFrame({...})

       # This should now WORK instead of raising NotImplementedError
       af.pols_maturity = (
           when(af.month == af.policy_term * 12)
           .then(af.pols_if)
           .otherwise(0)
       )

       result = af.collect()

       # Verify results
       assert result["pols_maturity"][0] == [0, 0, ..., 88]
       assert result["pols_maturity"][1] == [0, 0, ..., 76]
   ```

2. **Add edge case tests:**
   ```python
   def test_list_broadcasting_with_all_scalar_results(self):
       """Test list condition with scalar then/otherwise."""

   def test_list_broadcasting_with_mixed_results(self):
       """Test mix of list and scalar in results."""

   def test_list_broadcasting_preserves_row_order(self):
       """Test maintain_order=True works."""
   ```

### Task 4.4: Handle Computation Graph Integration

**Challenge:** Tracing mode needs special handling.

**Options:**

**Option A: Disable for now (simple)**
```python
if self._tracing:
    raise NotImplementedError(
        "List broadcasting with tracing not yet supported. Use optimize mode."
    )
```

**Option B: Store as special operation (complex)**
```python
if self._tracing:
    # Store a special "list_broadcast_conditional" operation
    append_list_broadcast_operation(self, key, metadata)
```

**Recommendation:** Start with Option A, implement Option B in Task 5.

---

## Task Dependencies and Order

### Task 4: Core List Broadcasting (DataFrame level)

**Subtasks:**
- Task 4.1: Add metadata to ConditionalProxy (2 hours)
- Task 4.2: Modify ActuarialFrame.__setitem__ (4 hours)
- Task 4.3: Update tests to verify list broadcasting (2 hours)
- Task 4.4: Handle computation graph integration (2 hours)

**Total estimate:** 10 hours

**Deliverable:** List broadcasting works in optimize mode

### Task 5: Computation Graph Integration ✅ COMPLETED

**Goal:** Make list broadcasting work with tracing/debug mode

**Implementation:** Eager execution with tracing
- Executes explode/re-aggregate pattern immediately in debug mode
- Captures TracedOperation with list broadcasting metadata
- Shows operation in computation graph for debugging
- No changes needed to optimize mode (already working)

**Completed:** 2025-11-11
**Duration:** 8 hours

### Task 6: Comprehensive Testing

**Tests needed:**
- Edge cases (empty lists, nulls, mismatched lengths)
- Performance benchmarks (verify 6-8x improvement)
- Integration tests with other ActuarialFrame features
- Stress tests with large datasets

**Estimate:** 6 hours

### Task 7: Rich Documentation

**Following `ref/recipes/write-docstring.md`:**
- Add "When to use" admonition to `when()` docstring
- Add actuarial examples (maturity, premiums, commissions)
- Run examples to get exact output
- Document list broadcasting behavior
- Add performance notes

**Estimate:** 4 hours

### Task 8: Scratch Tests and Examples

**Already done! ✅**
- `tests/scratch/conditional_maturity.py`
- `tests/scratch/conditional_premium_holiday.py`

**Additional examples to add:**
- Commission schedules
- Zeroing after maturity
- Multiple simultaneous conditionals

**Estimate:** 2 hours

---

## Total Implementation Estimate

| Task | Description | Estimate | Status |
|------|-------------|----------|--------|
| Task 4 | Core list broadcasting | 10 hours | Not started |
| Task 5 | Computation graph integration | 8 hours | Not started |
| Task 6 | Comprehensive testing | 6 hours | Not started |
| Task 7 | Rich documentation | 4 hours | Not started |
| Task 8 | Additional scratch tests | 2 hours | Partially done |
| **Total** | | **30 hours** | **~7% done** |

---

## Risk Assessment

### Technical Risks

**Risk 1: Computation Graph Complexity** (Medium)
- Tracing mode may require significant refactoring
- Mitigation: Start with optimize-only, add tracing later

**Risk 2: Performance Edge Cases** (Low)
- Very large lists (>10K elements) may have performance issues
- Mitigation: Add benchmarks early, optimize if needed

**Risk 3: Column Name Collisions** (Low)
- `_row_id` might conflict with user columns
- Mitigation: Use UUID or check for collision

### Integration Risks

**Risk 4: Breaking Changes** (Low)
- Modifying `__setitem__` is risky
- Mitigation: Extensive tests, feature flag for rollback

**Risk 5: Type System** (Low)
- ConditionalProxy type checking in `__setitem__`
- Mitigation: Proper isinstance checks, type: ignore if needed

---

## Success Criteria

### Functional Requirements

- ✅ List broadcasting works for basic conditionals
- ✅ Handles multiple when conditions
- ✅ Preserves row order
- ✅ Integrates with existing ActuarialFrame features
- ✅ Works in optimize mode
- ⚠️ Works in debug/tracing mode (Task 5)

### Performance Requirements

- ✅ 6-8x faster than `map_elements` (measured)
- ✅ No regression on scalar conditionals
- ✅ Handles 10K+ rows with 120 element lists (<100ms)

### Code Quality Requirements

- ✅ Comprehensive test coverage (>90%)
- ✅ Clear error messages for edge cases
- ✅ Rich documentation with examples
- ✅ Type-safe implementation

---

## Alternative Approaches Considered

### Alternative 1: Custom Polars Expression

Build a custom Polars expression plugin.

**Rejected because:**
- Requires C/Rust implementation
- Much more complex than DataFrame approach
- Harder to maintain
- Overkill for this use case

### Alternative 2: Lazy Evaluation Trick

Store metadata in ExpressionProxy and defer execution.

**Rejected because:**
- Breaks existing computation graph assumptions
- Hard to reason about when expression is "ready"
- Complicates debugging

### Alternative 3: User-Level Helper Function

Provide `when_list()` separate from `when()`.

**Rejected because:**
- Poor UX - users shouldn't need to choose
- Violates "automatic smart behavior" design principle
- Breaks Excel IF() mental model

---

## References

**Research Files:**
- `list_broadcasting_solution.py` - Working implementation (111M ops/sec)
- `research_list_broadcasting.py` - Comprehensive tests
- `list_broadcasting_findings.md` - Technical findings
- `scalar_to_list_research.py` - Initial exploration

**Design Documents:**
- `18-when-then-design.md` - Original design
- `when-then-otherwise-implementation.md` - Tasks 1-3 plan
- `18-conditional-broadcast.md` - Performance problem analysis

**Related Code:**
- `gaspatchio_core/functions/conditional.py` - ConditionalProxy implementation
- `gaspatchio_core/frame/base.py` - ActuarialFrame.__setitem__
- `tests/functions/test_conditional.py` - Current tests

---

## Next Steps

**To start Task 4:**

1. **Create feature branch:**
   ```bash
   git checkout -b feature/list-broadcasting-task-4
   ```

2. **Start with Task 4.1** (ConditionalProxy metadata)
   - Add `needs_list_broadcasting()` method
   - Add `get_list_broadcasting_metadata()` method
   - Update `otherwise()` to not raise NotImplementedError

3. **Write tests first** (TDD)
   - Test that metadata is correctly populated
   - Test that detection works

4. **Implement Task 4.2** (ActuarialFrame changes)
   - Add detection in `__setitem__`
   - Implement `_apply_conditional_list_broadcasting()`
   - Implement `_build_list_broadcasting_df()`

5. **Verify with scratch examples**
   - Run `conditional_maturity.py`
   - Run `conditional_premium_holiday.py`
   - Should see "✅ SUCCESS!" instead of NotImplementedError

6. **Performance benchmark**
   - Compare to `map_elements` baseline
   - Verify 6-8x improvement
   - Document results

---

**Status:** Ready to begin implementation once Tasks 1-3 are merged.
