# Step 03: Product Features — Guarantees & Surrender Charges

> **Prerequisites:** Read the base model docstring (`base/model.py` lines 1-55). This step builds on Step 02 (select mortality).

## What this adds

Introduces the product features that make a variable annuity different from a savings account: guaranteed minimum benefits on death (GMDB) and maturity (GMAB), plus surrender charges on early withdrawal.

## Why

A VA promises the policyholder that even if investment markets fall, they will receive at least a guaranteed amount. On death (GMDB): beneficiaries receive the greater of the account value or the sum assured. On maturity (GMAB): the policyholder receives the greater of the account value or the sum assured. These guarantees are the core risk the insurer takes on.

Surrender charges discourage early withdrawal and compensate the insurer for upfront acquisition costs. They decrease over time (typically 10% in year 1 down to 0% by year 5-6).

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `model_points.parquet` | 4 | point_id | — | **New columns:** `has_gmdb` (Boolean), `has_gmab` (Boolean), `has_surr_charge` (Boolean), `surr_charge_id` (String) |
| `surrender_charges.parquet` | 10 | surr_charge_id (String), duration (Int64) | surr_charge_rate (Float64) | **New file.** SC001: 10% at dur 0, declining 2% per year to 0% at dur 5+ |
| `mortality_select.parquet` | 3500 | table_id, attained_age, duration | mort_rate | Unchanged |
| `mortality_scalars.parquet` | 15 | scalar_id, duration | mort_scalar | Unchanged |
| `inv_returns.parquet` | 241 | t, fund_index | inv_return_mth | Unchanged |

## Before → After

Section 5 adds mid-month AV (new timing concept):

```python
# NEW: Mid-month account value — assumes decrements occur mid-period
af.av_pp_mid_mth = af.av_pp_after_fee + 0.5 * af.inv_income_pp
```

Section 7 (claims) is completely rewritten with nested `when/then`:

```python
# BEFORE (step 02): simple AV payout
af.claims_death = af.av_pp * af.pols_death

# AFTER (step 03): GMDB guarantee — max(sum_assured, AV)
af.claim_pp_death = (
    when(af.has_gmdb)
    .then(
        when(af.av_pp_mid_mth > af.sum_assured_f)    # nested when!
        .then(af.av_pp_mid_mth)
        .otherwise(af.sum_assured_f)                   # guarantee kicks in
    )
    .otherwise(af.av_pp_mid_mth)                       # no guarantee: just AV
)
```

Surrender charges use conditional lookup:

```python
# Only look up charge if policy has surrender charges
af.surr_charge_rate = (
    when(af.has_surr_charge)
    .then(surrender_charges.lookup(surr_charge_id=..., duration=...))
    .otherwise(af.duration * 0.0)
)
af.claims_lapse = af.av_pp_mid_mth * af.pols_lapse - af.surr_charge
```

## Expected output

```
┌──────────┬───────────────┬───────────┬─────────────────┬─────────────────┐
│ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_claims_death ┆ pv_claims_lapse │
│ ---      ┆ ---           ┆ ---       ┆ ---             ┆ ---             │
│ i64      ┆ f64           ┆ f64       ┆ f64             ┆ f64             │
╞══════════╪═══════════════╪═══════════╪═════════════════╪═════════════════╡
│ 1        ┆ 379962.301269 ┆ 5.6564e6  ┆ 130452.825861   ┆ 1.4584e6        │
│ 2        ┆ 193471.054449 ┆ 1.8378e6  ┆ 21731.79167     ┆ 794076.899928   │
│ 3        ┆ 707533.406838 ┆ 1.9303e7  ┆ 403087.859985   ┆ 2.7051e6        │
│ 4        ┆ 343907.097037 ┆ 3.7494e6  ┆ 63270.974286    ┆ 1.3516e6        │
└──────────┴───────────────┴───────────┴─────────────────┴─────────────────┘
```

Notice: claims are now broken out by type (death, lapse). Lapse claims are reduced by surrender charges.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va/steps/03-guarantees/model.py

# Via CLI
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/03-guarantees/model.py tutorial/level-3-mini-va/steps/03-guarantees/data/model_points.parquet 1
```

## When a user asks about this

- "How do I model guaranteed minimum death benefits?"
- "How do I implement GMDB or GMAB guarantees?"
- "How do I add surrender charges?"
- "How do I use nested when/then/otherwise?"
- "What is av_pp_mid_mth and why does it matter?"
