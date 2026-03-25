# Step 04: Conditionals on List Columns

## What changed from Step 03

- `policy_term` added to model points (in years: 1, 2, 2)
- Projection extended to 24 months
- `af.maturity_month` computed from `policy_term`
- `af.pols_if` zeroed after maturity using `when/then/otherwise`
- `af.commissions` added: 50% of premium income in year 1, 0% after

## Key patterns

### Maturity zeroing

```python
af.maturity_month = af.policy_term * 12

af.pols_if = (
    when(af.duration_mth_t < af.maturity_month)
    .then(af.survival_bop)
    .otherwise(0.0)
)
```

`af.duration_mth_t` is a list `[0, 1, 2, ..., 23]`. `af.maturity_month` is a
scalar per policy (e.g., 12 for a 1-year term). gaspatchio broadcasts the
scalar, evaluating the condition independently for each month. Months before
maturity get `survival_bop`; months at or after get `0.0`.

### Conditional commissions

```python
af.commissions = (
    when(af.month < 12)
    .then(af.premium_income * 0.50)
    .otherwise(0.0)
)
```

`af.month` is the projection month index `[0, 1, ..., 23]`. The comparison
`af.month < 12` produces a boolean list. Months 0–11 pay 50% commission;
months 12–23 pay nothing.

## How it differs from Level 1 `when/then/otherwise`

In Level 1, `when()` operates on scalar columns (one value per policy):

```python
# Level 1: scalar conditional
af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")
```

In Level 2+, after `create_projection_timeline()`, columns become lists.
`when()` operates element-wise across every `(policy, month)` cell:

```python
# Level 2: list conditional (element-wise across months)
af.pols_if = when(af.duration_mth_t < af.maturity_month).then(...).otherwise(0.0)
```

The API is identical — gaspatchio handles both cases transparently.

## Observable effects

- **POL001** (term=1 year): zero policies in force from month 12 onward.
  Only 12 months of cash flows contribute to `pv_net_cf`.
- **POL002/POL003** (term=2 years): full 24 months of cash flows, but
  year-1 commissions reduce profit in months 0–11.

## Data directory

```
data/
  model_points.parquet   — 3 policies with policy_term column
  mortality.parquet      — 92 rows (ages 25–70, M and F)
  lapse_rates.parquet    — 24 rows (two projection years)
```
