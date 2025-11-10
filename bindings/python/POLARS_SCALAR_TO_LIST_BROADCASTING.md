# Polars Scalar-to-List Broadcasting Research

## Summary

This document provides research findings on efficiently broadcasting scalar column values to match list column lengths in Polars for optimal performance.

## Recommended Approach: `repeat_by()`

The **recommended method** for broadcasting scalar columns to list columns is using `pl.Expr.repeat_by()`:

```python
import polars as pl

df = pl.DataFrame({
    "policy_term": [10, 20, 15],
    "month": [[0,1,2,...11], [0,1,2,...11], [0,1,2,...11]]
})

# Create scalar column
df = df.with_columns(
    (pl.col("policy_term") * 12).alias("total_months")
)

# Broadcast scalar to list matching the length of 'month'
df = df.with_columns(
    pl.col("total_months")
    .repeat_by(pl.col("month").list.len())
    .alias("total_months_list")
)
```

**Result:**
- Scalar column: `[120, 240, 180]`
- List column: `[[120,120,...120], [240,240,...240], [180,180,...180]]`

### Performance
- **Small dataset (3 rows)**: ~0.004 seconds
- **Large dataset (100k rows, 12 elements per list)**: ~0.006 seconds
- **Excellent scaling**: Near-linear performance with dataset size

## Alternative Approach: Direct Arithmetic (Polars 1.8+)

Since **Polars 1.8.0**, direct arithmetic operations between list and scalar columns are supported with automatic broadcasting:

```python
# Direct arithmetic - scalar broadcasts automatically
df = df.with_columns(
    (pl.col("month") + pl.col("total_months")).alias("result")
)
```

**Performance**: Slightly faster (~0.0025s vs ~0.004s on small datasets)

**Key Difference**: This approach performs the arithmetic operation element-wise, not just broadcasting the scalar. If you need the scalar repeated without transformation, use `repeat_by()`.

## Methods That Don't Work

### list.eval with External Columns

```python
# This FAILS - list.eval cannot reference named columns
pl.col("month").list.eval(pl.lit(pl.col("total_months")))
```

**Error**: `cannot create expression literal for value of type Expr`

**Reason**: `list.eval` is designed to work with `pl.element()` for operations within the list context, not for referencing external columns. This limitation exists for performance reasons.

## Performance Considerations

### Memory Efficiency

1. **`repeat_by()` materializes the list**
   - Creates an actual list column with repeated values
   - Memory usage: O(n * list_length) where n is number of rows
   - Polars may use ScalarColumn optimization internally to avoid full duplication

2. **Direct arithmetic broadcasts at computation time**
   - May be more memory efficient for operations
   - Scalar is broadcast during the arithmetic operation
   - Does not materialize a repeated list unless needed

### When to Use Each Method

| Use Case | Method | Reason |
|----------|--------|--------|
| Need list of repeated scalars | `repeat_by()` | Explicitly creates the list structure |
| Arithmetic with list elements | Direct arithmetic | More concise, potentially faster |
| Complex operations | `repeat_by()` first | Convert to list, then chain operations |
| Memory constrained | Direct arithmetic | Avoids materialization |

## Implementation Details

### repeat_by Signature

```python
def repeat_by(self, n: int | Expr) -> Expr:
    """
    Repeat elements by the values in another column/expression.

    Parameters
    ----------
    n : int | Expr
        Column or expression containing repeat counts

    Returns
    -------
    Expr
        Expression with repeated elements expanded into a List
    """
```

### Recent Improvements

- **Polars 1.8.0** (2023): Added arithmetic operations for list types
- **Polars 1.10.0** (2024): Improved list arithmetic support (#19162)
- **PR #21206** (2025): Extended `repeat_by` to support list datatypes

## Key Documentation Links

1. **repeat_by API**: https://docs.pola.rs/api/python/stable/reference/expressions/api/polars.Expr.repeat_by.html
2. **Lists and Arrays Guide**: https://docs.pola.rs/user-guide/expressions/lists-and-arrays/
3. **GitHub PR #17823**: Added arithmetic between Series with dtype list
4. **GitHub Issue #10918**: Discussion of list operations with scalar columns

## Example: Actuarial Use Case

```python
# Actuarial model with projection periods
policies = pl.DataFrame({
    "policy_id": ["P001", "P002", "P003"],
    "policy_term": [10, 20, 15],
    "premium": [1000, 2000, 1500],
    "month": [list(range(12)), list(range(12)), list(range(12))]
})

# Calculate values that need to be broadcast to match projection periods
result = policies.with_columns([
    # Scalar calculations
    (pl.col("policy_term") * 12).alias("total_months"),
    (pl.col("premium") * 12).alias("annual_premium"),
])

# Broadcast scalars to lists for projection calculations
result = result.with_columns([
    # Method 1: Create repeated list
    pl.col("total_months")
    .repeat_by(pl.col("month").list.len())
    .alias("total_months_list"),

    # Method 2: Direct arithmetic (adds premium to each month value)
    (pl.col("month") + pl.col("premium")).alias("month_plus_premium"),
])
```

## Best Practices

1. **Use `repeat_by()` when you need the actual list structure**
   - Clearest intent
   - Explicit about creating lists
   - Works well with subsequent list operations

2. **Use direct arithmetic for computational operations**
   - More concise
   - Potentially more memory efficient
   - Natural syntax for mathematical operations

3. **Avoid `list.eval` for referencing external columns**
   - Not supported by design
   - Use `repeat_by()` instead

4. **Consider memory usage for large datasets**
   - Test both approaches with representative data
   - Profile memory usage if working with millions of rows
   - Consider Polars lazy API for larger-than-memory datasets

## Testing

Run the research script to verify behavior:

```bash
cd ~/Projects/gaspatchio/gaspatchio-core/bindings/python
uv run python scalar_to_list_research.py
```

This tests:
- `repeat_by()` method
- `list.eval` method (demonstrates failure)
- Direct arithmetic method
- Performance with 100k rows
- Memory efficiency considerations
