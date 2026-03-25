# Step 04: Policyholder Behaviour — Dynamic Lapse

> **Prerequisites:** Read the base model docstring (`base/model.py` lines 1-55). This step builds on Step 03 (guarantees).

## What this adds

Replaces the constant lapse rate with duration-based lapse rates from a table, adjusted by a dynamic lapse factor that depends on how "in the money" the guarantee is.

## Why

Policyholders are rational: if their guarantee is worth more than their account value (the guarantee is "in the money"), they are less likely to lapse. If their account value has grown well beyond the guarantee, the guarantee has little value and they may lapse to access better rates elsewhere.

Dynamic lapse captures this: the lapse rate is multiplied by a factor that depends on the ITM (in-the-money) ratio = AV / sum_assured. When ITM is high (AV >> guarantee), the factor increases lapses. When ITM is low (guarantee >> AV), the factor reduces lapses.

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `model_points.parquet` | 4 | point_id | — | **New columns:** `lapse_id`, `formula_id`, `dyn_lapse_floor`, `U`, `L`, `M_param`, `D_param` |
| `lapse_rates.parquet` | 15 | lapse_id (String), duration (Int64) | lapse_rate (Float64) | **New file.** L001: 10% at dur 0, declining to 2% at dur 8+ |
| All other files | | | | Unchanged from Step 03 |

## Before → After

**Section ordering changes:** AV (Section 5) must now come BEFORE lapse (Section 4) because dynamic lapse depends on account value. The section order is now: 2, 3, **5, 4**, 6, 7, 8, 9, 10, 11.

Section 4 (lapse) is completely rewritten:

```python
# BEFORE (step 03): constant scalar lapse
af.lapse_rate = LAPSE_RATE_ANNUAL  # scalar, broadcasts automatically
af.lapse_rate_mth = 1 - (1 - af.lapse_rate) ** (1 / 12)

# AFTER (step 04): table lookup + dynamic adjustment
af.base_lapse_rate = lapse_rates.lookup(lapse_id=af.lapse_id, duration=af.lapse_duration_capped)

# ITM ratio: how valuable is the guarantee?
af.itm = af.av_pp_mid_mth / af.sum_assured.cast(pl.Float64)

# Dynamic factor: clip(1 - M * (1/ITM - D), L, U)
af.dyn_lapse_factor = (1.0 - af.M_param * (1.0 / af.itm - af.D_param)).clip(af.L, af.U)

# Final lapse: apply factor, enforce floor
af.lapse_rate = (af.dyn_lapse_factor * af.base_lapse_rate).clip(af.dyn_lapse_floor, None)
```

Key concepts:
- **ITM ratio** = AV / guarantee. ITM > 1 means AV exceeds guarantee (guarantee less valuable)
- **Dynamic lapse formula DL001**: `clip(1 - M × (1/ITM - D), lower, upper)`
- With the tutorial's simplified params (M=0, D=0), the factor is 1.0 (no adjustment). Try M=0.5, D=1.0 to see the effect.
- **Floor**: lapse rate can't go below `dyn_lapse_floor` even with dynamic adjustment

## Expected output

```
┌──────────┬───────────────┬───────────┬─────────────────┬─────────────────┐
│ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_claims_death ┆ pv_claims_lapse │
│ ---      ┆ ---           ┆ ---       ┆ ---             ┆ ---             │
│ i64      ┆ f64           ┆ f64       ┆ f64             ┆ f64             │
╞══════════╪═══════════════╪═══════════╪═════════════════╪═════════════════╡
│ 1        ┆ 385563.409171 ┆ 5.6571e6  ┆ 132594.132756   ┆ 1.1054e6        │
│ 2        ┆ 228378.306826 ┆ 1.8531e6  ┆ 26157.960627    ┆ 369548.234741   │
│ 3        ┆ 682271.816322 ┆ 1.9293e7  ┆ 388026.685306   ┆ 3.7133e6        │
│ 4        ┆ 381320.192969 ┆ 3.7652e6  ┆ 71210.087424    ┆ 699530.682781   │
└──────────┴───────────────┴───────────┴─────────────────┴─────────────────┘
```

Lapse claims changed from Step 03 — the duration-based lapse table produces different rates than the constant 5%.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va/steps/04-dynamic-lapse/model.py

# Via CLI
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/04-dynamic-lapse/model.py tutorial/level-3-mini-va/steps/04-dynamic-lapse/data/model_points.parquet 1
```

## When a user asks about this

- "How do I model dynamic lapse?"
- "What is the ITM ratio?"
- "How does policyholder behaviour depend on market conditions?"
- "How do I make lapse rates depend on account value?"
- "What is a dynamic lapse floor?"
- "Why did the section ordering change?"
