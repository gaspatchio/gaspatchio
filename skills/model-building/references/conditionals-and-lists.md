# Conditionals and List Operations

## The #1 Runtime Error: List/Scalar Mismatch

This is the single most common gaspatchio error. It crashes at runtime with:

```
"Unsupported combination of list/scalar inputs"
```

### What Causes It

`when().then(SCALAR).otherwise(LIST_COLUMN)` — mixing a literal scalar with a list column in the same conditional:

```python
# CRASHES — scalar 1.0 mixed with list column af.cso_table
af.cso_table = when(af.age > 99).then(1.0).otherwise(af.cso_table)
```

### The Fix: Arithmetic Masking

Create a 0/1 flag, then blend with arithmetic:

```python
# ALWAYS WORKS — arithmetic masking
af.is_age_over_99 = when(af.real_attained_age > 99).then(1.0).otherwise(0.0)
af.cso_table = af.cso_table * (1 - af.is_age_over_99) + 1.0 * af.is_age_over_99
```

The pattern is: `result = original * (1 - flag) + replacement * flag`

### When `when/then/otherwise` IS Safe

It works fine when both branches are the same type:

```python
# OK — both branches are scalars
af.commission = when(af.duration == 0).then(af.premium).otherwise(0.0)

# OK — both branches are list columns
af.rate = when(af.year <= 10).then(af.select_rate).otherwise(af.ultimate_rate)

# OK — flag creation (both branches are scalar literals)
af.is_male = when(af.sex == "M").then(1.0).otherwise(0.0)
```

### General Rule

- **Flag creation** (0.0 / 1.0 from a condition): `when/then/otherwise` is fine
- **Replacing values in a list column**: use arithmetic masking
- **Choosing between two list columns**: `when/then/otherwise` is fine
- When in doubt: use arithmetic masking — it never crashes

### Default: Prefer `when/then/otherwise` for Readability

Use `when().then().otherwise()` as the **default** for all conditional logic. It reads like English and mirrors Excel's `IF()`, making models accessible to actuaries who will review and audit the code.

```python
# PREFERRED — reads like a business rule
af.pols_if = (
    when(af.duration_mth_t < af.maturity_month)
    .then(af.survival_prob * af.policy_count)
    .otherwise(0.0)
)

# AVOID in teaching/audit code — reads like a programmer's trick
af.pols_if = af.survival_prob * af.policy_count * (af.duration_mth_t < af.maturity_month)
```

Boolean masking (`value * condition`) is an **advanced pattern** for performance-critical paths. Do not use it in models that will be reviewed by non-programmers.

### Shape-Preserving Zero in `otherwise()`

When the `then()` branch produces a list column, the `otherwise()` branch must also be list-shaped. A bare `0.0` scalar can cause "Unsupported combination of list/scalar inputs". Use a shape-preserving expression:

```python
# If both branches involve list columns, this works fine:
af.x = when(condition).then(af.list_col).otherwise(0.0)  # OK — gaspatchio handles this

# If you get a shape error, use a column expression that preserves shape:
af.x = when(condition).then(af.list_col).otherwise(af.duration * 0.0)
```

---

## Year-Varying Rate Pattern

When a rate changes by year (e.g., inflation schedule), use vectorized masks:

```python
def _year_rate(af_year, rates: tuple):
    """Build a year-varying column without loops or map_elements."""
    n = len(rates)
    if all(r == rates[0] for r in rates):
        return af_year * 0 + rates[0]  # flat — scalar broadcast

    result = af_year * 0.0
    for i in range(n - 1):
        mask = when(af_year == i + 1).then(1.0).otherwise(0.0)
        result = result + mask * rates[i]
    # Last rate applies to all subsequent years
    last_mask = when(af_year >= n).then(1.0).otherwise(0.0)
    result = result + last_mask * rates[n - 1]
    return result
```

Note: this `for` loop builds an expression tree — it does NOT iterate over data rows. The loop runs once at build time, not per policy.

---

## List Column Operations

After projection, many columns are lists (one element per projection period). Common operations:

### Aggregation

```python
# Sum across all periods (per policy)
af.total_claims = af.claims.list.sum()

# PV of cashflows (sum of discounted values)
af.pv_claims = (af.claims * af.discount_factors).list.sum()
```

### Cumulative Operations

```python
# Cumulative survival (from mortality rate)
af.survival = af.mort_rate.projection.cumulative_survival()

# Cumulative sum
af.running_total = af.cashflow.list.cumsum()

# Cumulative product (raw Polars, available on ExpressionProxy)
af.compound_factor = af.growth_rate.cum_prod()
```

### Period Shifting

```python
af.prev_inforce = af.pols_if.projection.previous_period(fill_value=1.0)
af.next_rate = af.rate.projection.next_period(fill_value=0.0)
af.rate_at_t5 = af.rate.projection.at_period(5)
```

### Modifying Specific Periods

```python
af.adjusted = af.cashflow.projection.with_period(0, 1000.0)       # set t=0
af.adjusted = af.cashflow.projection.with_periods({0: 100, 12: 50})  # set multiple
```

### List Slicing

When slicing list columns with other list columns, first broadcast to a named column:

```python
# WRONG — chaining .list.head() directly on pl.lit() can fail
result = df.with_columns(pl.lit(values).list.head(pl.col("n")).alias("sliced"))

# RIGHT — two-step: broadcast first, then operate
result = df.with_columns(
    pl.lit(values).alias("full_list")
).with_columns(
    pl.col("full_list").list.head(pl.col("n")).alias("sliced")
)
```
