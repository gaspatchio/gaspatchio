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

`af.duration_mth_t` counts months since **issue** — `duration_mth_init +
af.month`, one list per policy over the 25-period timeline (projection months
0–24 inclusive). A policy issued at the valuation date sees `[0, 1, ..., 24]`;
POL003, issued 22 months earlier, sees `[22, 23, ..., 46]`.
`af.maturity_month` is a scalar per policy (e.g., 12 for a 1-year term).
gaspatchio broadcasts the scalar, evaluating the condition independently for
each month. Months before maturity get `survival_bop`; months at or after get
`0.0`.

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
months 12–24 pay nothing.

## How it differs from Level 1 `when/then/otherwise`

In Level 1, `when()` operates on scalar columns (one value per policy):

```python
# Level 1: scalar conditional
af.is_profitable = when(af.profit > 0).then("Yes").otherwise("No")
```

In Level 2+, after `af.projection.set()`, columns become lists.
`when()` operates element-wise across every `(policy, month)` cell:

```python
# Level 2: list conditional (element-wise across months)
af.pols_if = when(af.duration_mth_t < af.maturity_month).then(...).otherwise(0.0)
```

The API is identical — gaspatchio handles both cases transparently.

## Observable effects

- **POL001** (term=1 year, issued at valuation): zero policies in force from
  projection month 12 onward. Only 12 months of cash flows contribute to
  `pv_net_cf`.
- **POL002** (term=2 years, issued Jun 2023): already 7 months into its term
  at valuation, so it matures at projection month 17 — months 0–16 contribute,
  with 50% commissions dragging on months 0–11.
- **POL003** (term=2 years, issued Mar 2022): already 22 months into its term,
  so it matures at projection month 2 — **only months 0–1 contribute**. Its
  small `pv_net_cf` is maturity truncation, not claims experience (claims
  total ~25.6 against ~231.9 of commissions over those two months).

## Data directory

```
data/
  model_points.parquet   — 3 policies with policy_term column
  mortality.parquet      — 92 rows (ages 25–70, M and F)
  lapse_rates.parquet    — 25 rows (months 0–24: two projection years plus
                           the closing boundary month)
```
