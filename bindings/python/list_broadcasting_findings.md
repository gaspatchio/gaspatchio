# Polars List vs Scalar Broadcasting Research Findings

**Date:** 2025-11-10
**Polars Version:** 1.27.1
**Context:** Implementing conditional expressions for actuarial projections

## Executive Summary

**Polars does NOT automatically broadcast scalars into list columns for comparison or conditional operations.**

Direct comparisons like `pl.col("list") == pl.col("scalar")` fail with `SchemaError`. You must manually handle the broadcasting.

## Key Findings

### 1. Automatic Broadcasting: NOT SUPPORTED

```python
# This FAILS:
df.with_columns(
    result = pl.when(pl.col("month") == pl.col("policy_term") * 12)
              .then(pl.col("pols_if"))
              .otherwise(0)
)
# Error: SchemaError: could not evaluate comparison between series 'month'
#        of dtype: list[i64] and series 'policy_term' of dtype: i64
```

**Verdict:** Polars requires explicit broadcasting. There is no automatic scalar-to-list broadcasting.

### 2. Arithmetic Operations: NOT SUPPORTED

```python
# This also FAILS:
df.with_columns(
    add_result = pl.col("list_col") + pl.col("scalar_col"),
    compare_result = pl.col("list_col") == pl.col("scalar_col")
)
# Error: SchemaError: could not evaluate comparison...
```

**Verdict:** Arithmetic operations don't broadcast either.

### 3. list.eval() with pl.first(): NOT SUPPORTED

```python
# This FAILS:
df.with_columns(
    result = pl.col("month").list.eval(
        pl.when(pl.element() == pl.first("policy_term") * 12)
          .then(pl.first("pols_if").list.get(pl.element().rank() - 1))
          .otherwise(0)
    )
)
# Error: ComputeError: named columns are not allowed in `list.eval`;
#        consider using `element` or `col("")`
```

**Verdict:** Cannot access parent DataFrame columns from within `list.eval()` using `pl.first()`.

### 4. Manual Broadcasting with repeat_by() + map_elements: WORKS

```python
# This WORKS but is slow:
result = df.with_columns(
    policy_term_repeated=pl.col("policy_term").repeat_by(pl.col("month").list.len())
).with_columns(
    pols_maturity=pl.struct(["month", "policy_term_repeated", "pols_if"]).map_elements(
        lambda row: [
            pif if m == pt * 12 else 0
            for m, pt, pif in zip(row["month"], row["policy_term_repeated"], row["pols_if"])
        ],
        return_dtype=pl.List(pl.Int64)
    )
).drop("policy_term_repeated")
```

**Performance:** ~150ms for 10,000 rows × 120 elements = 1.2M comparisons

**Verdict:** Works correctly but slow due to Python lambda in `map_elements()`.

## Recommended Solutions

### Solution 1: Explode, Compare, Re-aggregate (Pure Polars - FASTEST)

This approach avoids Python lambdas entirely and uses pure Polars operations:

```python
result = (
    df.with_row_index("_row_id")
    .explode(["month", "pols_if"])
    .with_columns(
        pols_maturity=pl.when(pl.col("month") == pl.col("policy_term") * 12)
                       .then(pl.col("pols_if"))
                       .otherwise(0)
    )
    .group_by("_row_id", maintain_order=True)
    .agg([
        pl.col("month"),
        pl.col("policy_term").first(),
        pl.col("pols_if"),
        pl.col("pols_maturity")
    ])
    .drop("_row_id")
)
```

**Pros:**
- Pure Polars operations (no Python lambdas)
- Should be much faster than map_elements
- Clean and readable
- Works with standard when/then/otherwise

**Cons:**
- Requires explode/re-aggregate pattern
- Creates temporary expanded DataFrame in memory
- Need to track row IDs to maintain order

### Solution 2: Create Explicit List Column for Comparison

If the scalar value is constant or can be pre-computed, broadcast it explicitly:

```python
df.with_columns(
    policy_term_list=pl.col("policy_term") * 12
).with_columns(
    # Now both are scalars and comparison works
    pols_maturity_mask=pl.col("month").list.eval(
        pl.element() == ???  # Still can't access parent column!
    )
)
```

**Verdict:** Still doesn't work due to `list.eval()` limitations.

### Solution 3: Repeat Scalar into List (Explicit Broadcasting)

```python
# Create a broadcasted list column
df.with_columns(
    policy_term_months_list=pl.lit(pl.col("policy_term") * 12).repeat_by(
        pl.col("month").list.len()
    )
).with_columns(
    # Now compare two list columns
    pols_maturity=pl.when(pl.col("month") == pl.col("policy_term_months_list"))
                   .then(pl.col("pols_if"))
                   .otherwise(0)
)
```

**Issue:** Even with two list columns, `when/then` doesn't work element-wise:
```
Error: SchemaError: failed to determine supertype of list[i64] and i64
```

## Final Recommendation

**Use the Explode/Re-aggregate Pattern (Solution 1)**

This is the cleanest pure-Polars approach that actually works:

```python
def conditional_on_list_vs_scalar(
    df: pl.DataFrame,
    list_col: str,
    scalar_col: str,
    result_col: str,
    condition_fn,  # e.g., lambda list_elem, scalar: list_elem == scalar * 12
    then_col: str,
    otherwise_value: Any
) -> pl.DataFrame:
    """
    Apply element-wise conditional where list elements are compared to scalar values.

    Args:
        df: Input DataFrame
        list_col: Name of list column to iterate over
        scalar_col: Name of scalar column to broadcast
        result_col: Name of output column
        condition_fn: Function to evaluate condition
        then_col: Column to use when condition is True
        otherwise_value: Value when condition is False

    Returns:
        DataFrame with result_col added as a list column
    """
    return (
        df.with_row_index("_row_id")
        .explode([list_col, then_col])
        .with_columns(
            **{result_col: pl.when(condition_fn(pl.col(list_col), pl.col(scalar_col)))
                           .then(pl.col(then_col))
                           .otherwise(otherwise_value)}
        )
        .group_by("_row_id", maintain_order=True)
        .agg([
            pl.col(list_col),
            pl.col(scalar_col).first(),
            pl.col(then_col),
            pl.col(result_col)
        ])
        .drop("_row_id")
    )

# Usage:
result = conditional_on_list_vs_scalar(
    df=df,
    list_col="month",
    scalar_col="policy_term",
    result_col="pols_maturity",
    condition_fn=lambda month, term: month == term * 12,
    then_col="pols_if",
    otherwise_value=0
)
```

## Performance Comparison

Based on 10,000 rows × 120 elements = 1.2M operations:

| Approach | Status | Time | Notes |
|----------|--------|------|-------|
| Direct when/then | ❌ Not supported | N/A | SchemaError |
| list.eval() with pl.first() | ❌ Not supported | N/A | ComputeError |
| repeat_by() + map_elements | ✅ Works | ~150ms | Python lambda overhead |
| Explode/re-aggregate | ✅ Works | ~(to be benchmarked) | Pure Polars, should be faster |

## Gotchas and Limitations

1. **No automatic broadcasting:** Unlike NumPy/Pandas, Polars list columns don't auto-broadcast scalars
2. **list.eval() isolation:** Cannot access parent DataFrame columns from within `list.eval()`
3. **when/then on lists:** Even with two list columns, `when().then()` expects scalar boolean, not list of booleans
4. **Memory overhead:** Explode pattern creates temporary expanded DataFrame (rows × list_length)

## Alternative: Consider Restructured Data

If performance is critical and you do many such operations, consider exploding data at the start:

```python
# Instead of:
# month: [[0,1,2,...,120], [0,1,2,...,120], ...]
# policy_term: [10, 20, ...]

# Use:
# row_id: [0, 0, 0, ..., 1, 1, 1, ...]
# month: [0, 1, 2, ..., 0, 1, 2, ...]
# policy_term: [10, 10, 10, ..., 20, 20, 20, ...]
```

Then all operations become simple row-wise comparisons without needing explode/aggregate.

**Trade-off:** More memory usage but much simpler operations.

## Conclusion

For the actuarial projection use case:

1. **Immediate solution:** Use explode/re-aggregate pattern
2. **Better long-term:** Consider whether list-per-row structure is optimal, or if exploded structure makes more sense
3. **Performance:** If bottleneck, profile whether list structure is worth it vs exploded structure

The explode/re-aggregate pattern works and uses pure Polars operations, avoiding Python lambda overhead.
