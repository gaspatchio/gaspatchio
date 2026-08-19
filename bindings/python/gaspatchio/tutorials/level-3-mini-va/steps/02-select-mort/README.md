# Step 02: Select/Ultimate Mortality

> **Prerequisites:** Read the base model docstring (`base/model.py` lines 1-55) for key concepts. This step builds on Step 01 (file-based assumptions).

## What this adds

Replaces the simple age-based mortality table with a select/ultimate mortality structure — the industry standard for life insurance pricing and reserving.

## Why

Newly underwritten policyholders have lower mortality than the general population at the same age — this is called "selection effect." A select table captures this: mortality depends on both attained age AND how long since underwriting (duration). After the select period (typically 15-25 years), rates revert to "ultimate" rates that depend on age only.

Real VA models also apply mortality scalars — multiplicative adjustments by duration that calibrate the base table to the specific product experience.

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `model_points.parquet` | 4 | point_id | — | **New columns:** `mort_table_male`, `mort_table_female`, `mort_scalar_id` |
| `mortality_select.parquet` | 3500 | table_id (String), attained_age (Int64), duration (Int64) | mort_rate (Float64) | **New file.** T001=male, T002=female. 70 ages × 25 durations × 2 tables |
| `mortality_scalars.parquet` | 15 | scalar_id (String), duration (Int64) | mort_scalar (Float64) | **New file.** S001: scalars from 0.80 (dur 0) to 1.08 (dur 14) |
| `inv_returns.parquet` | 241 | t, fund_index | inv_return_mth | Unchanged from Step 01 |

## Before → After

Section 3 (mortality) is completely rewritten:

```python
# BEFORE (step 01): 1-dimensional lookup
af.mort_rate = mortality_table.lookup(age=af.age)

# AFTER (step 02): 3-dimensional lookup + scalar adjustment
af.mort_table_id = when(af.sex == "M").then(af.mort_table_male).otherwise(af.mort_table_female)
af.duration_capped = af.duration.clip(upper_bound=SELECT_PERIOD_LEN - 1)

af.base_mort_rate = mortality_select.lookup(
    table_id=af.mort_table_id, attained_age=af.age, duration=af.duration_capped,
)
af.mort_scalar = mortality_scalars.lookup(
    scalar_id=af.mort_scalar_id, duration=af.duration.clip(upper_bound=SCALAR_DURATION_CAP),
)
af.mort_rate = af.base_mort_rate * af.mort_scalar
```

Key patterns introduced:
- **Sex-based table selection** using `when/then/otherwise`
- **Duration capping** with `.clip(upper_bound=N)` — the select table only covers durations 0-24
- **Multi-key lookup** — Table.lookup() with 3 dimensions
- **Scalar adjustment** — final rate = base × scalar

## Expected output

```
┌──────────┬───────────────┬───────────┬─────────────┐
│ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_premiums │
│ ---      ┆ ---           ┆ ---       ┆ ---         │
│ i64      ┆ f64           ┆ f64       ┆ f64         │
╞══════════╪═══════════════╪═══════════╪═════════════╡
│ 1        ┆ 376438.012877 ┆ 5.6599e6  ┆ 0.0         │
│ 2        ┆ 194486.999155 ┆ 1.8367e6  ┆ 0.0         │
│ 3        ┆ 715390.400219 ┆ 1.9295e7  ┆ 0.0         │
│ 4        ┆ 345669.048411 ┆ 3.7476e6  ┆ 0.0         │
└──────────┴───────────────┴───────────┴─────────────┘
```

Numbers changed from Step 01 — the select mortality table produces different rates than the simple age-only table. This is expected.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va/steps/02-select-mort/model.py

# Via CLI
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/02-select-mort/model.py tutorial/level-3-mini-va/steps/02-select-mort/data/model_points.parquet 1
```

## When a user asks about this

- "How do I use select/ultimate mortality tables?"
- "How do I do multi-dimensional table lookups?"
- "How do I handle different assumptions for male vs female?"
- "What are mortality scalars?"
- "How do I cap lookup dimensions with .clip()?"
