# Step 01: Projections

Adds the time dimension to the base model. After this step, each policy has a list of values — one per projection month — instead of a single scalar.

## What changes from base

One function call transforms everything: `af.date.create_projection_timeline()`.

Before calling it, every column is a scalar — one value per policy. After calling it, any column you assign becomes a list — one value per policy per month. Existing scalar columns remain scalar and broadcast automatically when you use them in arithmetic with list columns.

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

## How create_projection_timeline works

```python
af = af.date.create_projection_timeline(
    valuation_date=VALUATION_DATE,          # projection starts here
    projection_end_type="term_months",      # end after a fixed number of months
    projection_end_value=12,               # 12 months
    projection_frequency="monthly",         # one period per month
    output_column="projection_date",        # name of the new date list column
)
```

This adds a `projection_date` list column — the first day of each projected month. All subsequent column assignments produce list columns automatically.

## Broadcasting scalars to lists

Scalar arithmetic still works after create_projection_timeline. If `af.annual_premium` is scalar (one value per policy) and `af.month` is a list, then:

```python
af.monthly_premium = af.annual_premium / 12.0   # stays scalar
af.expected_claims = af.sum_assured * af.mortality_rate   # stays scalar
```

These scalars broadcast automatically when multiplied against list columns — no manual replication needed.

## Next step

Step 02 introduces `.projection.cumulative_survival()` — the key method for computing how many policies are still in force at each projection period.
