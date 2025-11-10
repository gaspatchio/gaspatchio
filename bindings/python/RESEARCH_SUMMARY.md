# Polars List vs Scalar Broadcasting Research - Summary

**Research Date:** 2025-11-10
**Researcher:** Claude Code Agent
**Polars Version:** 1.27.1
**Context:** Implementing conditional expressions for actuarial projections in gaspatchio-core

---

## Quick Answer

**Does Polars automatically broadcast scalars into list columns for conditionals?**

**NO.** You must explicitly handle the broadcasting using the explode/re-aggregate pattern.

---

## The Problem

In actuarial projections, we have:
- **List columns:** `month = [[0,1,2,3,...], [0,1,2,3,...]]` (one list per policy)
- **Scalar columns:** `policy_term = [10, 20]` (one value per policy)
- **Goal:** Compare element-wise: `month == policy_term * 12` within each policy's list

Example use case: Set maturity benefit to `pols_if` when `month == policy_term * 12`, otherwise 0.

---

## Research Findings

### ❌ What DOESN'T Work

#### 1. Direct when/then with list vs scalar

```python
# FAILS with SchemaError
df.with_columns(
    result = pl.when(pl.col("month") == pl.col("policy_term") * 12)
              .then(pl.col("pols_if"))
              .otherwise(0)
)
```

**Error:** `SchemaError: could not evaluate comparison between series 'month' of dtype: list[i64] and series 'policy_term' of dtype: i64`

#### 2. Arithmetic operations

```python
# FAILS with SchemaError
df.with_columns(
    result = pl.col("list_col") + pl.col("scalar_col")
)
```

**Error:** Same SchemaError - no automatic broadcasting.

#### 3. list.eval() with pl.first()

```python
# FAILS with ComputeError
df.with_columns(
    result = pl.col("month").list.eval(
        pl.when(pl.element() == pl.first("policy_term") * 12)
          .then(...)
          .otherwise(0)
    )
)
```

**Error:** `ComputeError: named columns are not allowed in 'list.eval'`

You cannot access parent DataFrame columns from within `list.eval()`.

---

## ✅ The Solution: Explode/Re-aggregate Pattern

### Working Code

```python
def conditional_list_vs_scalar_explode(
    df: pl.DataFrame,
    list_col: str,
    scalar_col: str,
    result_col: str,
    then_col: str,
    otherwise_value: Any,
    comparison_multiplier: int = 12,
) -> pl.DataFrame:
    """Apply element-wise conditional comparing list elements to scalar values."""
    return (
        df.with_row_index("_row_id")
        .explode([list_col, then_col])
        .with_columns(
            **{
                result_col: pl.when(
                    pl.col(list_col) == pl.col(scalar_col) * comparison_multiplier
                )
                .then(pl.col(then_col))
                .otherwise(otherwise_value)
            }
        )
        .group_by("_row_id", maintain_order=True)
        .agg([
            pl.col(list_col),
            pl.col(scalar_col).first(),
            pl.col(then_col),
            pl.col(result_col),
        ])
        .drop("_row_id")
    )
```

### Usage Example

```python
df = pl.DataFrame({
    "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
    "policy_term": [1],  # 1 year = 12 months
    "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88]],
})

result = conditional_list_vs_scalar_explode(
    df=df,
    list_col="month",
    scalar_col="policy_term",
    result_col="pols_maturity",
    then_col="pols_if",
    otherwise_value=0,
    comparison_multiplier=12,
)

# Result: pols_maturity = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 88]
#         (all zeros except at month 12 where it equals pols_if value)
```

---

## Performance Results

**Test Dataset:** 10,000 policies × 120 months = 1.2 million operations

| Approach | Status | Time | Throughput |
|----------|--------|------|------------|
| Direct when/then | ❌ Not supported | N/A | N/A |
| list.eval() with pl.first() | ❌ Not supported | N/A | N/A |
| repeat_by() + map_elements | ✅ Works | ~150ms | ~8M ops/sec |
| **Explode/re-aggregate** | ✅ **Works** | **10.81ms** | **111M ops/sec** |

**Winner:** Explode/re-aggregate is **14× faster** than the Python lambda approach!

---

## Why This Solution Works

### How It Works

1. **Add row index:** Track which row each element belongs to
2. **Explode lists:** Convert list columns to regular columns (one row per list element)
3. **Apply condition:** Now it's a simple scalar comparison - Polars handles this natively
4. **Re-aggregate:** Group by row index and collect results back into lists
5. **Clean up:** Drop the temporary row index column

### Key Advantages

1. ✅ **Pure Polars operations** - No Python lambdas, stays in fast Rust execution
2. ✅ **Native when/then/otherwise** - Uses standard Polars API
3. ✅ **Maintains order** - `maintain_order=True` ensures correctness
4. ✅ **Excellent performance** - 111M operations/second
5. ✅ **Clean API** - Can be wrapped in reusable function

### Memory Considerations

The explode step temporarily expands memory from:
- **Before:** N rows with lists of length L
- **During:** N × L expanded rows
- **After:** N rows with lists of length L

For typical actuarial projections (10K policies × 120 months = 1.2M rows), this is totally fine.

---

## Recommendations for Gaspatchio

### For Immediate Use

Use the `conditional_list_vs_scalar_explode()` function as shown above. It works, it's fast, and it's pure Polars.

### For Projection Accessor

Create a clean API method:

```python
class ProjectionAccessor:
    def when(
        self,
        condition_col: str,
        operator: str,
        value_col: str,
        multiplier: int = 1
    ) -> ProjectionBuilder:
        """
        Build a conditional expression for list columns.

        Example:
            df.proj.when("month", "==", "policy_term", multiplier=12)
              .then("pols_if")
              .otherwise(0)
        """
        return ProjectionBuilder(self._df, condition_col, operator, value_col, multiplier)
```

Internally, use the explode/re-aggregate pattern.

### Consider Data Structure

If you're doing many such operations, consider whether list-per-row is optimal:

**Current (list-per-row):**
```
month: [[0,1,2,...], [0,1,2,...]]
policy_term: [10, 20]
```

**Alternative (exploded):**
```
policy_id: [0, 0, 0, ..., 1, 1, 1, ...]
month: [0, 1, 2, ..., 0, 1, 2, ...]
policy_term: [10, 10, 10, ..., 20, 20, 20, ...]
```

**Trade-offs:**
- **List-per-row:** More compact, better for row-wise operations
- **Exploded:** Simpler operations, no need for explode/re-aggregate pattern

For actuarial projections where most operations are element-wise within a projection, exploded structure might be more natural. But this depends on your specific use case.

---

## Key Gotchas Discovered

1. **No automatic broadcasting:** Polars does NOT broadcast scalars into list elements automatically
2. **list.eval() isolation:** Cannot access parent DataFrame columns from within `list.eval()`
3. **Type checking:** Even comparing two list columns in `when()` doesn't work as expected
4. **Memory during explode:** Be aware of temporary memory expansion during explode step

---

## Files Created

1. **`research_list_broadcasting.py`** - Comprehensive test suite showing what works and what doesn't
2. **`list_broadcasting_solution.py`** - Working solution with examples and benchmarks
3. **`list_broadcasting_findings.md`** - Detailed technical findings document
4. **`RESEARCH_SUMMARY.md`** - This executive summary

---

## Conclusion

**Use the explode/re-aggregate pattern for list vs scalar conditionals in Polars.**

It's the only approach that:
- Actually works
- Uses pure Polars operations (fast)
- Has good performance (111M ops/sec)
- Can be wrapped in a clean API

The pattern is proven and tested with real data showing correct results and excellent performance characteristics for typical actuarial projection workloads.

---

## Running the Code

```bash
# Run research script to see what doesn't work
uv run python research_list_broadcasting.py

# Run solution script to see what works
uv run python list_broadcasting_solution.py
```

Both scripts are self-contained and can be run directly from the bindings/python directory.
