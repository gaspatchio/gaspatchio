# Step 01: Projections

Adds the time dimension to the base model. After this step, each policy has a list of values — one per projection month — instead of a single scalar.

## What changes from base

One function call declares the time axis: `af.projection.set()`.

Before calling it, every column is a scalar — one value per policy. After calling it, the frame knows about a projection grid; assigning a list-valued projection accessor (e.g. `af.projection.period_dates()`) produces a list column — one value per policy per month. Existing scalar columns remain scalar and broadcast automatically when you use them in arithmetic with list columns.

## What is a list column?

A list column stores a Python list in each cell. For a 3-policy model with 12 projection months, a list column looks like:

```
┌───────────┬──────────────┐
│ policy_id ┆ month        │
│ str       ┆ list[i32]    │
╞═══════════╪══════════════╡
│ POL001    ┆ [0, 1, … 12] │
│ POL002    ┆ [0, 1, … 12] │
│ POL003    ┆ [0, 1, … 12] │
└───────────┴──────────────┘
```

Each element is one projection period. All 13 months are computed simultaneously — no loops.

## How `af.projection.set()` works

```python
af = af.projection.set(
    valuation_date=VALUATION_DATE,    # projection starts here
    until="term_months",              # end after a fixed number of months
    until_value=12,                   # 12 months
    frequency="monthly",              # one period per month
)
af.projection_date = af.projection.period_dates()
```

`af.projection.set()` declares the projection grid on the frame. Assigning `af.projection.period_dates()` materialises the per-period date vector as a list column — the first day of each projected month.

## Broadcasting scalars to lists

Scalar arithmetic still works after `af.projection.set()`. If `af.annual_premium` is scalar (one value per policy) and `af.month` is a list, then:

```python
af.monthly_premium = af.annual_premium / 12.0   # stays scalar
af.expected_claims = af.sum_assured * af.mortality_rate   # stays scalar
```

These scalars broadcast automatically when multiplied against list columns — no manual replication needed.

## Next step

Step 02 introduces `.projection.cumulative_survival()` — the key method for computing how many policies are still in force at each projection period.
