# Level 1: Hello World

The entry point for gaspatchio. Three term life insurance policies, no prior Python experience required.

Start with `base/model.py`. It's about 60 lines and introduces the four things you need to know before building any actuarial model in gaspatchio: ActuarialFrame, column arithmetic, `when/then/otherwise`, and `.collect()`.

## What it teaches

**base/** — scalar portfolio, no time dimension
- Creating an ActuarialFrame from a Python dict
- Assigning computed columns with `af.column_name = expression`
- Element-wise arithmetic across all policies at once
- `when(condition).then(value).otherwise(value)` — gaspatchio's `IF()`
- `.collect()` to materialise the lazy frame as a Polars DataFrame

**steps/01-projections/** — add time dimension
- `af.projection.set()` — declare the projection time axis on the frame
- `af.projection.period_dates()` — materialise the per-period date vector as a list column
- How scalar columns combine with list-valued projection accessors to produce list columns
- Month index derivation from projection dates

**steps/02-survival/** — add policy counts over time
- Actuarially correct annual-to-monthly rate conversion
- Combined decrement (death and lapse together)
- `.projection.cumulative_survival()` — fraction of policies in force at each period
- Broadcasting a scalar to a list column

**steps/03-time-shifting/** — add per-period cashflows
- `.projection.previous_period(fill_value)` — look back one period
- Death/lapse ordering (UDD assumption)
- Per-period death claims and net cashflow
- `.list.sum()` to aggregate over the projection

## How to run

```bash
# Base model — scalar results, no projections
uv run python tutorial/level-1-hello-world/base/model.py

# Step 01 — adds list columns (one element per month)
uv run python tutorial/level-1-hello-world/steps/01-projections/model.py

# Step 02 — adds policies in force
uv run python tutorial/level-1-hello-world/steps/02-survival/model.py

# Step 03 — adds per-period cashflows and net cashflow
uv run python tutorial/level-1-hello-world/steps/03-time-shifting/model.py
```

## What to look for in the output

**Base model:** three rows, all scalar columns. POL001 is loss-making (high mortality for its premium), POL002 and POL003 are profitable. The `is_profitable` column shows "Yes"/"No" — this is `when/then/otherwise` at work.

**Step 01:** `month` is a list column — 13 elements, one per projection month (0 through 12). `expected_claims_monthly` and `net_premium_monthly` are still scalar because they derive only from scalar inputs. They would broadcast automatically in list arithmetic.

**Step 02:** `pols_if` is a list starting at 1.0 and declining as policies exit by death or lapse. `total_premium` and `total_claims` are the undiscounted sums over 12 months.

**Step 03:** `net_cf` is a list — the profit or loss in each month. `pv_net_cf` is the total over the projection. POL001 is loss-making (sum assured large relative to premium); POL002 and POL003 are profitable.

## Next steps

**Steps 01-03** in this level each add one feature. Work through them in order.

**Level 2** replaces the hardcoded `mortality_rate` column with a `Table` lookup — the same projection as Step 03 but with real actuarial assumption tables.

**Level 3** is a complete variable annuity model with investment returns, account values, guarantees, and discounting. The docstring in `level-3-mini-va/base/model.py` explains every gaspatchio concept in detail.
