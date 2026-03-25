# Step 02: Cumulative Survival

Adds policy counts over time. After this step, each projection period has a fraction of the original cohort still in force.

## What changes from Step 01

Three new concepts: actuarially correct monthly rates, combined decrements, and cumulative survival.

## Actuarially correct monthly rates

Do NOT divide annual rates by 12. The correct formula is:

```python
q_monthly = 1 - (1 - q_annual) ** (1 / 12)
```

This ensures that applying the monthly rate 12 times gives exactly the annual decrement. For small rates the difference is minor; over a long projection it compounds significantly.

## Combined decrement

When policies can exit by death OR lapse, the combined monthly rate is:

```python
combined = 1 - (1 - mort_mth) * (1 - lapse_mth)
```

NOT `mort_mth + lapse_mth` — that would double-count policies that die and lapse simultaneously (which is impossible).

## Cumulative survival

`.projection.cumulative_survival()` converts a per-period decrement rate into the fraction of policies still in force at each period:

```
t=0:  1.000  (start — everyone in force)
t=1:  1 - d
t=2:  (1-d)^2
...
```

This is the vectorised equivalent of an Excel column like `=IF(t=0, 1, prev_cell * (1 - d))`.

## Broadcasting scalars to lists

`.projection.cumulative_survival()` requires a list column — one rate per period. In this model, rates are scalar (constant across all 12 months). To broadcast:

```python
af.decrement_list = af.combined_decrement + af.month * 0.0
af.pols_if = af.decrement_list.projection.cumulative_survival()
```

This is a workaround needed only when rates are constant. In Level 2, `Table.lookup()` naturally produces list columns — no broadcast needed.

## Using pols_if

Once you have `pols_if`, weight any per-policy quantity by it to get the portfolio total for that period:

```python
af.premium_income = af.monthly_premium * af.pols_if   # only active policies pay
af.expected_claims = af.sum_assured * af.mort_rate_mth * af.pols_if
```

## Next step

Step 03 introduces `.projection.previous_period()` — shifting `pols_if` by one period to get the correct starting cohort for deaths and lapses in each period.
