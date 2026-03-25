# Step 03: Time Shifting

Adds per-period death and lapse counts, and computes net cashflow. After this step the model produces a complete monthly profit projection.

## What changes from Step 02

One new method: `.projection.previous_period(fill_value)`. Everything else follows from it.

## What is previous_period?

`.projection.previous_period(fill_value)` shifts a list column right by one period:

```
[v0, v1, v2, v3, ...] → [fill_value, v0, v1, v2, ...]
```

This is gaspatchio's vectorised "look back one period" — equivalent to `=B2` in Excel (the cell above) or `pols_if(t-1)` in lifelib. All periods are computed simultaneously; no recursion.

## Why use previous_period for deaths?

Deaths in period t happen to the policies that were alive at the **start** of period t — before those deaths occurred. `pols_if` at period t has already had those deaths removed. So we need the prior-period value:

```python
af.pols_if_prev = af.pols_if.projection.previous_period(fill_value=1.0)
af.pols_death = af.pols_if_prev * af.mort_rate_mth   # correct
# NOT: af.pols_if * af.mort_rate_mth                 # undercounts deaths
```

## Why fill_value=1.0?

At t=0 there is no prior period. `fill_value=1.0` means: at the very start, treat the cohort as 1 full policy. Deaths in the first period are computed from this starting value, which is the correct actuarial assumption.

## Death/lapse ordering

Deaths are applied before lapses (UDD — Uniform Distribution of Deaths):

```python
pols_death = pols_if_prev * mort_rate_mth
pols_lapse = (pols_if_prev - pols_death) * lapse_rate_mth
```

This is standard in most life models. The order matters: applying lapse first would slightly change the result because the lapsing pool would still include policies that are about to die.

## Net cashflow

```python
net_cf = premium_income - claims_death - expenses
```

The undiscounted sum over the projection gives a first-pass profit figure. Discounting (converting future cashflows to present value) is introduced in Level 3.

## Next steps

This is the foundation for all gaspatchio models. From here:

**Level 2** replaces the hardcoded `mortality_rate` column with a `Table.lookup()` call — the same projection structure, with age-varying mortality from an assumption table.

**Level 3** builds a full variable annuity model on this foundation: investment returns, account values, GMDB/GMAB guarantees, and rate-curve discounting.
