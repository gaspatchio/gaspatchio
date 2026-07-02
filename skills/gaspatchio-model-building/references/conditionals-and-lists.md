# Conditionals and List Operations

## `when().then().otherwise()` is the canonical conditional

Use `when().then().otherwise()` as the **default** for all conditional logic. It reads like English, mirrors Excel's `IF()`, and gaspatchio routes it correctly regardless of whether the branches are scalars, list columns, or a mix:

```python
# All four forms are supported and lower to the same correct result.

# Both scalars
af.commission = when(af.duration == 0).then(af.premium).otherwise(0.0)

# Two list columns
af.rate = when(af.year <= 10).then(af.select_rate).otherwise(af.ultimate_rate)

# Scalar predicate, list `then`, scalar `otherwise` — broadcasts correctly
af.cso_table = when(af.age > 99).then(1.0).otherwise(af.cso_table)

# List predicate, mixed branches — element-wise via list_conditional
af.pols_if = (
    when(af.duration_mth_t < af.maturity_month)
    .then(af.survival_prob * af.policy_count)
    .otherwise(0.0)
)
```

The dispatch refactor (PRs #99 / #100 / #101) eliminated the old "list/scalar mismatch" failure mode. Earlier docs taught arithmetic-masking blends (`original * (1 - flag) + replacement * flag`) and shape-preserving zeros (`.otherwise(af.duration * 0.0)`) as workarounds for limitations that no longer exist. **Do not write those patterns in new code** — they obscure intent and the underlying issue is gone.

### Boolean masking remains a valid optimisation, not a teaching pattern

`value * (predicate)` still works and is occasionally useful in performance-critical paths. It is **not** the recommended style for model code that other actuaries will read or audit:

```python
# PREFERRED — reads like a business rule
af.pols_if = (
    when(af.duration_mth_t < af.maturity_month)
    .then(af.survival_prob * af.policy_count)
    .otherwise(0.0)
)

# AVOID in teaching / audit code — reads like a programmer's trick
af.pols_if = af.survival_prob * af.policy_count * (af.duration_mth_t < af.maturity_month)
```

The two forms produce identical results.

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

### Recursive Accumulation (`accumulate`)

For values that depend on their own prior state — account values, fund balances, cumulative gains:

```python
# Linear recurrence: state[t] = state[t-1] * multiply[t] + add[t]
# Example: account value with growth and deposits
af.shifted_growth = af.growth_factor.projection.previous_period(fill_value=1.0)
af.account_value = af.shifted_growth.projection.accumulate(
    initial=af.opening_balance,
    multiply=af.shifted_growth,
    add=af.deposits,
)
```

**When to use:** Any time you're tempted to write `for t in range(n): state[t] = f(state[t-1])`.
`accumulate` handles the sequential dependency per policy while Polars parallelises across policies.

Look up before using: `uv run gspio docs "accumulate" -t code_example`

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
