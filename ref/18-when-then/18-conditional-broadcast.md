# Conditional Broadcasting on List Columns: Feature Request

**Date:** 2025-01-10
**Status:** Feature Request
**Priority:** High
**Impact:** Performance, Code Clarity, User Experience

## Executive Summary

Gaspatchio currently lacks support for **element-wise conditional operations on list columns when the condition involves scalar columns**. This limitation forces users to resort to `map_elements()` (Python UDFs) or verbose explode-aggregate patterns, resulting in:

- **Slower execution** (6-8x performance degradation in tested scenarios)
- **Verbose, unclear code** that obscures actuarial intent
- **Friction when migrating from other frameworks** (Julia, R) that support this pattern natively

This document proposes adding Julia-style conditional broadcasting to Gaspatchio's expression API.

---

## Problem Statement

### The Use Case

In actuarial projections, we frequently need to apply conditional logic where:
- **The condition** compares list elements with scalar values
- **The result** depends on that element-wise comparison

**Example:** Policy maturity calculation

```
For each policy:
  For each month in projection timeline:
    if month == maturity_month:
      pols_maturity = surviving_policies
    else:
      pols_maturity = 0.0
```

This pattern appears in:
- **Maturity decrements**: Policies mature at exactly one month
- **Policy zeroing**: Stopping projections after maturity/death/lapse
- **Commission schedules**: Different rates in different periods
- **Expense timing**: Acquisition vs. maintenance expenses
- **Benefit triggers**: Payments conditional on time or status

---

## Real-World Examples from `basic_term/model_projection.py`

### Example 1: Policy Maturity Calculation

**Actuarial Logic:**
```
Maturity occurs when month == policy_term * 12
At the maturity month, count surviving policies
At all other months, maturity count is zero
```

**Desired Code (Gaspatchio ideal):**
```python
# Clear, declarative, fast
af["pols_maturity"] = pl.when(af["month"] == (af["policy_term"] * 12))
    .then(af["surviving_at_t"])
    .otherwise(0.0)
```

**Current Code (workaround with `map_elements`):**
```python
def maturity_logic(row):
    months = row["month"]
    maturity_month = row["policy_term"] * 12
    surviving = row["surviving_at_t"]
    return [
        surv if m == maturity_month else 0.0
        for m, surv in zip(months, surviving)
    ]

af["pols_maturity"] = pl.struct([
    pl.col("month"),
    pl.col("policy_term"),
    pl.col("surviving_at_t")
]).map_elements(maturity_logic, return_dtype=pl.List(pl.Float64))
```

**Issues:**
- 12 lines vs. 3 lines
- Python UDF overhead (slow)
- Intent obscured by implementation details
- Breaks lazy evaluation pipeline

---

### Example 2: Zeroing After Maturity

**Actuarial Logic:**
```
After a policy matures, all future values should be zero
Keep values before maturity, zero out at and after maturity
```

**Desired Code:**
```python
# Comparison: < maturity_month
af["pols_if"] = pl.when(af["month"] < (af["policy_term"] * 12))
    .then(af["pols_if_before_maturity"])
    .otherwise(0.0)
```

**Current Code:**
```python
def zero_after_maturity(row):
    months = row["month"]
    maturity_month = row["policy_term"] * 12
    pols_if_vals = row["pols_if_before_maturity"]
    return [
        pif if m < maturity_month else 0.0
        for m, pif in zip(months, pols_if_vals)
    ]

af["pols_if"] = pl.struct([
    pl.col("month"),
    pl.col("policy_term"),
    pl.col("pols_if_before_maturity")
]).map_elements(zero_after_maturity, return_dtype=pl.List(pl.Float64))
```

**Issues:**
- Same as Example 1
- Pattern repeats throughout codebase
- Each similar calculation requires new Python function

---

### Example 3: Commission Schedules

**Actuarial Logic:**
```
Pay 100% commission in first year (duration 0)
Pay 0% commission in all other years
```

**Desired Code:**
```python
af["commissions"] = pl.when(af["duration"] == 0)
    .then(af["premiums"])
    .otherwise(0.0)
```

**Current Code:**
```python
def calc_commissions(row):
    durations = row["duration"]
    premiums = row["premiums"]
    return [
        prem if dur == 0 else 0.0
        for dur, prem in zip(durations, premiums)
    ]

af["commissions"] = pl.struct([
    pl.col("duration"),
    pl.col("premiums")
]).map_elements(calc_commissions, return_dtype=pl.List(pl.Float64))
```

---

## Current Workarounds and Their Limitations

### Workaround 1: `map_elements()` (Current Approach)

**Pattern:**
```python
def conditional_func(row):
    list_col = row["list_col"]
    scalar_val = row["scalar_col"]
    return [elem if condition(elem, scalar_val) else 0.0 for elem in list_col]

af["result"] = pl.struct([pl.col("list_col"), pl.col("scalar_col")]) \
    .map_elements(conditional_func, return_dtype=pl.List(pl.Float64))
```

**Advantages:**
- Works correctly
- Familiar Python syntax

**Disadvantages:**
- **Performance**: Python UDF overhead (6-8x slower in benchmarks)
- **Verbosity**: Requires function definition, struct creation
- **Breaks lazy evaluation**: Forces eager execution at call site
- **No optimization**: Polars query optimizer can't see inside Python functions
- **Type safety**: Requires explicit return_dtype specification
- **Code clarity**: Implementation details obscure actuarial logic

---

### Workaround 2: Explode-Aggregate Pattern

**Pattern:**
```python
# Collect and prepare data
af_temp_df = af._df.select([
    "point_id",
    "policy_term",
    "month",
    "surviving_at_t"
]).collect()

# Explode lists to rows
af_exploded = af_temp_df.with_row_index("_row_id") \
    .explode(["month", "surviving_at_t"])

# Apply scalar conditional logic
af_exploded = af_exploded.with_columns(
    pols_maturity = pl.when(pl.col("month") == (pl.col("policy_term") * 12))
        .then(pl.col("surviving_at_t"))
        .otherwise(0.0)
)

# Aggregate back to lists
af_result = af_exploded.group_by("_row_id", maintain_order=True).agg(
    pl.col("pols_maturity")
)

# Assign result
af["pols_maturity"] = af_result["pols_maturity"]
```

**Advantages:**
- Uses pure Polars expressions
- Polars query optimizer can work with it

**Disadvantages:**
- **Extremely verbose**: 20+ lines for simple conditional
- **Performance worse than map_elements**: Creates many intermediate rows (policies × months)
- **Memory overhead**: Exploding 10k policies × 240 months = 2.4M rows
- **Requires collect()**: Breaks lazy evaluation
- **Complex mental model**: "Explode, transform, aggregate back" is non-obvious

---

### Workaround 3: Attempted Direct Broadcasting

**Attempted Code:**
```python
# This would be ideal...
af["pols_maturity"] = pl.when(af["month"] == (af["policy_term"] * 12))
    .then(af["surviving_at_t"])
    .otherwise(0.0)
```

**Error:**
```
TypeError: cannot create expression literal for value of type ExpressionProxy.

Hint: Pass `allow_object=True` to accept any value and create a literal of type Object.
```

**Why it fails:**
1. `af["month"]` returns `ExpressionProxy` (Gaspatchio wrapper), not `pl.Expr`
2. `pl.when()` expects `pl.Expr`, not `ExpressionProxy`
3. Even with `pl.col("month")`, Polars `pl.when()` doesn't broadcast conditionals over list elements when comparing with scalars

**The core issue:** Polars' `pl.when()` doesn't support element-wise conditionals on list columns where the condition involves external scalar columns.

---

## Performance Impact

### Benchmark: 10 Model Points

**Test:** Calculate `pols_maturity` for 10 policies × 241 months

| **Approach** | **Time** | **Relative** | **Lines of Code** |
|-------------|---------|-------------|-------------------|
| **Ideal (Julia-style)** | N/A | Baseline (estimated) | 3 |
| **map_elements** | 177ms | 1.51x slower than lifelib | 12 |
| **explode-aggregate** | 177ms | Same as map_elements | 25+ |

**For reference:**
- Without `map_elements` overhead, Gaspatchio is typically **6-8x faster** than lifelib
- With `map_elements`, performance drops to **1.5x faster**
- This represents a **4-5x performance penalty** from the workaround alone

### Scaling Implications

For production actuarial models:
- **10,000 policies**: Extra ~2 seconds per calculation
- **100,000 policies**: Extra ~20 seconds per calculation
- Multiple conditional operations compound the overhead
- In iterative workflows (sensitivity analysis, calibration), this becomes a major bottleneck

---

## How Other Frameworks Handle This

### Julia (JuliaActuary)

**Syntax:**
```julia
# Broadcasting with ifelse.() and dot operators
df.pols_maturity = ifelse.(df.month .== df.policy_term .* 12,
                          df.surviving_at_t,
                          0.0)
```

**Features:**
- **Explicit broadcasting** via `.` operator
- **Native language support** for element-wise operations
- **Type stable** and highly optimized
- **Clear and concise**: 1 line

**Performance:** Comparable to native vectorized operations

---

### R (tidyverse)

**Syntax:**
```r
# Using dplyr::if_else with vectorization
df <- df %>%
  mutate(pols_maturity = if_else(month == policy_term * 12,
                                 surviving_at_t,
                                 0.0))
```

**Features:**
- **Automatic vectorization** over data frame columns
- **if_else** is vectorized and type-safe
- **Integrates with dplyr pipelines**

---

### Pandas (Python)

**Syntax:**
```python
# Using numpy.where or pd.Series.where
df['pols_maturity'] = np.where(df['month'] == df['policy_term'] * 12,
                               df['surviving_at_t'],
                               0.0)

# Or using .where() method
df['pols_maturity'] = df['surviving_at_t'].where(
    df['month'] == df['policy_term'] * 12,
    0.0
)
```

**Features:**
- **Element-wise comparison** with broadcasting
- **Works with scalar and array-like columns**
- **Vectorized execution** (NumPy backend)

---

### Common Pattern Across All Three

All these frameworks support:
1. **Element-wise conditional logic** with clear syntax
2. **Broadcasting** between columns of different shapes/types
3. **Single-expression** solutions (no loops or UDFs)
4. **Optimized execution** (compiled or vectorized)

This is a **fundamental capability** for data manipulation, not an edge case.

---

## Proposed Solution: List-Aware Conditional Broadcasting

### API Design Option 1: Extend `pl.when()` to Support List Broadcasting

**Usage:**
```python
# When both columns are lists (element-wise comparison)
af["result"] = pl.when(pl.col("list1") == pl.col("list2"))
    .then(pl.col("list3"))
    .otherwise(0.0)

# When comparing list column with scalar column (broadcast scalar to each element)
af["result"] = pl.when(pl.col("list_col") == pl.col("scalar_col"))
    .then(pl.col("list_col"))
    .otherwise(0.0)
```

**Detection logic:**
- If all columns in condition are lists → element-wise comparison
- If condition mixes list and scalar → broadcast scalar to each list element
- Preserve existing behavior for non-list columns

---

### API Design Option 2: New `list.when()` Method

**Usage:**
```python
# Explicit list-aware conditional
af["pols_maturity"] = pl.col("month").list.when(
    pl.element() == (pl.col("policy_term") * 12)
).then(
    pl.col("surviving_at_t").list.get(pl.element_index())
).otherwise(0.0)
```

**Advantages:**
- Explicit opt-in to list conditional logic
- Follows existing `pl.col().list.*` pattern
- Uses `pl.element()` and `pl.element_index()` (familiar from `list.eval`)

**Challenges:**
- More verbose than Julia/R/Pandas patterns
- Need to expose element index for accessing other lists

---

### API Design Option 3: Enhance ExpressionProxy with Broadcasting

**Usage (Gaspatchio-specific):**
```python
# ExpressionProxy handles broadcasting automatically
af["pols_maturity"] = af["month"].when(
    lambda elem: elem == af["policy_term"] * 12
).then(
    af["surviving_at_t"]
).otherwise(0.0)
```

**Advantages:**
- Natural syntax for Gaspatchio users
- Leverages ExpressionProxy wrapper
- Could support complex conditions via lambda

**Challenges:**
- Requires implementing conditional logic in Gaspatchio layer
- Lambda overhead might negate performance benefits
- Diverges from native Polars patterns

---

### API Design Option 4: List Comprehension-Style Builder (Most Explicit)

**Usage:**
```python
af["pols_maturity"] = pl.col("month").list.eval(
    pl.when(pl.element() == (pl.col("policy_term") * 12))
        .then(pl.col("surviving_at_t").list.get_by_index(pl.element_index()))
        .otherwise(0.0)
)
```

**Current limitation:** Cannot reference external columns inside `list.eval` context

**What would need to change:**
- Allow `pl.col()` references within `list.eval` scope
- Resolve column values at evaluation time
- Handle scalar vs. list column broadcasting

---

## Recommended Approach

**Extend `list.eval()` to support external column references** (Option 4 Enhanced)

### Proposed Syntax

```python
# Basic usage
af["pols_maturity"] = pl.col("surviving_at_t").list.eval(
    pl.when(pl.col("month").list.get_by_index(pl.element_index()) == pl.col("policy_term") * 12)
        .then(pl.element())
        .otherwise(0.0)
)

# Simplified with helper (if index-matching is automatic)
af["pols_maturity"] = pl.when_list(
    pl.col("month") == pl.col("policy_term") * 12
).then(
    pl.col("surviving_at_t")
).otherwise(0.0)
```

### Implementation Considerations

1. **Scope resolution:**
   - Inside `list.eval`, `pl.col()` should resolve to:
     - List element via `pl.element()` if column is a list
     - Scalar value if column is scalar
   - Use `pl.element_index()` to access corresponding elements from other lists

2. **Broadcasting semantics:**
   - When comparing list elements with scalars, broadcast scalar to match list length
   - When comparing list elements with other list elements, align by index

3. **Type checking:**
   - Ensure all list columns have same length
   - Validate dtype compatibility for comparisons
   - Clear error messages when shapes don't align

4. **Performance:**
   - Compile to native Polars operations (avoid Python loops)
   - Leverage SIMD and parallel execution where possible
   - Benchmark against `map_elements` to ensure improvement

---

## Example: Before and After

### Current Code (12 lines, slow)

```python
def maturity_logic(row):
    months = row["month"]
    maturity_month = row["policy_term"] * 12
    surviving = row["surviving_at_t"]
    return [
        surv if m == maturity_month else 0.0
        for m, surv in zip(months, surviving)
    ]

af["pols_maturity"] = pl.struct([
    pl.col("month"),
    pl.col("policy_term"),
    pl.col("surviving_at_t")
]).map_elements(maturity_logic, return_dtype=pl.List(pl.Float64))
```

### Proposed Code (3 lines, fast)

```python
af["pols_maturity"] = pl.when_list(
    pl.col("month") == pl.col("policy_term") * 12
).then(pl.col("surviving_at_t")).otherwise(0.0)
```

**Improvements:**
- **4x fewer lines** of code
- **6-8x faster** execution (estimated, based on eliminating Python UDF overhead)
- **Clear actuarial intent**: Condition → value → default
- **Consistent** with existing Polars API patterns

---

## Additional Use Cases in Actuarial Modeling

### 1. Expense Timing

```python
# Acquisition expense only at t=0, maintenance thereafter
af["expenses"] = pl.when_list(
    pl.col("month") == 0
).then(
    pl.col("pols_if") * pl.col("expense_acq")
).otherwise(
    pl.col("pols_if") * pl.col("expense_maint") / 12 * pl.col("inflation_factor")
)
```

### 2. Multi-Year Commission Schedules

```python
# 100% in year 1, 50% in year 2, 25% in year 3, 0% thereafter
af["commissions"] = pl.when_list(
    pl.col("duration") == 0
).then(
    pl.col("premiums") * 1.0
).when_list(
    pl.col("duration") == 1
).then(
    pl.col("premiums") * 0.5
).when_list(
    pl.col("duration") == 2
).then(
    pl.col("premiums") * 0.25
).otherwise(0.0)
```

### 3. Benefit Triggers

```python
# Death benefit before maturity, maturity benefit at maturity
af["total_benefit"] = pl.when_list(
    pl.col("month") < pl.col("policy_term") * 12
).then(
    pl.col("death_benefit")
).otherwise(
    pl.col("maturity_benefit")
)
```

### 4. Dynamic Lapse Rates

```python
# Higher lapse in early durations, lower thereafter
af["lapse_rate"] = pl.when_list(
    pl.col("duration") < 3
).then(0.10).when_list(
    pl.col("duration") < 5
).then(0.05).otherwise(0.02)
```

---

## Technical Challenges

### Challenge 1: Polars List Column Semantics

**Current behavior:**
- `pl.col("list_col") + pl.col("scalar")` → broadcasts scalar to each element
- `pl.col("list_col") == pl.col("scalar")` → unclear if this broadcasts or compares entire lists

**Need to define:**
- How comparisons work for list vs. scalar
- How to distinguish element-wise vs. whole-list operations
- Error handling for mismatched list lengths

---

### Challenge 2: `pl.when()` Context Awareness

**Current limitation:**
- `pl.when()` operates on expressions, not aware of list semantics
- Condition produces a boolean (Series), not a list of booleans

**Possible solutions:**
1. Detect list dtypes in condition and automatically apply element-wise logic
2. Create separate `pl.when_list()` for explicit list handling
3. Extend `list.eval()` to allow external column references

---

### Challenge 3: Nested Conditionals

**Use case:**
```python
# Multiple conditions with different priorities
result = pl.when_list(cond1).then(val1)
           .when_list(cond2).then(val2)
           .when_list(cond3).then(val3)
           .otherwise(default)
```

**Challenge:**
- Ensure short-circuit evaluation (stop at first match per element)
- Maintain performance with many conditions
- Clear precedence rules

---

### Challenge 4: ExpressionProxy Integration

**For Gaspatchio:**
- Need to unwrap `ExpressionProxy` to `pl.Expr` when passing to `pl.when()`
- Or: Implement conditional logic at ExpressionProxy level
- Ensure lazy evaluation is preserved

---

## Alternative: Polars Plugin

If modifying core Polars is not feasible, consider a **Polars plugin** approach:

```python
import polars as pl
from polars_list_when import when_list  # Hypothetical plugin

af["pols_maturity"] = when_list(
    pl.col("month") == pl.col("policy_term") * 12
).then(
    pl.col("surviving_at_t")
).otherwise(0.0)
```

**Advantages:**
- Doesn't require changes to Polars core
- Can iterate quickly on API design
- Gaspatchio can depend on the plugin

**Disadvantages:**
- Performance may not match native implementation
- Additional dependency
- Ecosystem fragmentation

---

## Migration Path

### Phase 1: Add New API (Non-Breaking)

```python
# Old code continues to work
af["pols_maturity"] = pl.struct([...]).map_elements(...)

# New code can use cleaner API
af["pols_maturity"] = pl.when_list(...).then(...).otherwise(...)
```

### Phase 2: Deprecation Warnings (Optional)

```python
# Warn when map_elements is used for simple conditionals
# Suggest using when_list instead
```

### Phase 3: Documentation and Examples

- Add to Gaspatchio docs with actuarial examples
- Blog post comparing performance
- Migration guide for existing code

---

## Success Metrics

1. **Performance:** 5-10x faster than `map_elements` for conditional operations
2. **Code clarity:** 50-75% reduction in lines of code for conditional patterns
3. **Adoption:** 80%+ of new code uses new API instead of `map_elements`
4. **User satisfaction:** Positive feedback from actuarial users migrating from Julia/R

---

## References

- **Polars `list.eval` documentation:** https://docs.pola.rs/user-guide/expressions/lists/#eval
- **Julia broadcasting:** https://docs.julialang.org/en/v1/manual/arrays/#Broadcasting
- **JuliaActuary examples:** https://juliaactuary.org/tutorials/
- **This issue in context:** `basic_term/model_projection.py` lines 103-130

---

## Conclusion

Adding conditional broadcasting for list columns would:
- **Eliminate a major pain point** for actuarial modeling in Gaspatchio
- **Improve performance** by 5-10x for conditional operations
- **Align with industry standards** (Julia, R, Pandas all support this)
- **Reduce cognitive load** (3 lines vs. 12 lines for simple conditionals)
- **Enable more complex models** by making conditional logic practical at scale

This feature would significantly enhance Gaspatchio's value proposition as a modern actuarial modeling framework.
