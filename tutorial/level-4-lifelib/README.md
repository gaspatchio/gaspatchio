# Level 4: Reconciled Variable Annuity — Lifelib IntegratedLife

## Overview

This is the full appliedlife model, reconciled against lifelib's IntegratedLife implementation. It projects monthly cashflows and present values for GMDB/GMAB variable annuity products.

This model is the destination that Level 3's steps build toward. If you've completed Level 3, you understand every concept used here — this model just applies them all together with real assumption data.

## What it demonstrates

- Select/ultimate mortality with scalar adjustments (Step 02)
- GMDB and GMAB guarantee mechanics (Step 03)
- Dynamic lapse based on ITM ratio (Step 04)
- Risk-free rate curve discounting (Step 05)
- Full reconciliation against an industry reference model (Step 06)
- `accumulate()` for recursive account value rollforward (handles both IF and NB)
- Staggered new business entry with premium injection at diverse dates

## Reconciliation coverage

The model reconciles at **0.0000%** across three datasets, 35 variables, and approximately 9 million individual data points:

| Dataset | Points | Description | Timesteps |
|---------|--------|-------------|-----------|
| 2023Q4IF | 8 | In-force, age 70, M/F, 10yr term | 82 |
| 2022Q4IF | 8 | In-force, age 70, all male, underwater AVs | 82 |
| 202401NB | 1,000 | New business, ages 20-79, terms 5-20yr, zero AV | 252 |

Each dataset is compared on 10 PV aggregates and 25 intermediate variables (mortality, lapse, policy counts, account values, cashflows, discount factors) per point per timestep.

See `reconciliation_report.md` for the full breakdown including upstream bugs found in lifelib.

## Running the model

```bash
# Single policy (2023Q4IF)
uv run gspio run-single-policy tutorial/level-4-lifelib/base/model.py \
    tutorial/level-4-lifelib/base/model_points.parquet 1

# All 8 policies
uv run gspio run-model tutorial/level-4-lifelib/base/model.py \
    tutorial/level-4-lifelib/base/model_points.parquet

# With output file for analysis
uv run gspio run-single-policy tutorial/level-4-lifelib/base/model.py \
    tutorial/level-4-lifelib/base/model_points.parquet 1 \
    --output-file /tmp/result.parquet

# 2022Q4IF model points (all male, underwater AVs)
uv run gspio run-model tutorial/level-4-lifelib/base/model.py \
    tutorial/level-4-lifelib/base/model_points_2022Q4IF.parquet
```

## Reconciliation

**Quick PV check (original script):**

```bash
uv run python tutorial/level-4-lifelib/reconcile.py
```

**Full reconciliation (PVs + 25 intermediate variables per point per timestep):**

```bash
# 2023Q4IF — default
uv run python tutorial/level-4-lifelib/reconcile_full.py

# 2022Q4IF
uv run python tutorial/level-4-lifelib/reconcile_full.py \
    --gaspatchio-output /tmp/result.parquet \
    --reference tutorial/level-4-lifelib/reference/lifelib_reference_2022Q4IF.parquet

# Per-timestep detail for a specific point
uv run python tutorial/level-4-lifelib/reconcile_full.py --detail 1
```

For the 202401NB reconciliation, the lifelib reference must be generated from `gaspatchio-models` using a patched lifelib (see `reconciliation_report.md` for details).

## Assumption files

| File | Dimensions | What it contains |
|---|---|---|
| `mortality_select.parquet` | table_id x age x duration | Select mortality rates |
| `mortality_ultimate.parquet` | table_id x age | Ultimate mortality rates |
| `mortality_scalars.parquet` | scalar_id x duration | Mortality adjustment factors |
| `lapse_rates.parquet` | lapse_id x duration | Base annual lapse rates |
| `dynamic_lapse_params.parquet` | index | DL formula parameters (U, L, M, D, etc.) |
| `surrender_charges.parquet` | surr_charge_id x duration | Surrender charge schedule |
| `product_params_gmxb.parquet` | product_id x plan_id | Product configuration |
| `scenario_returns.parquet` | t | Monthly fund returns, 180 months (FUND1-FUND6) |
| `scenario_returns_nb.parquet` | t | Extended fund returns, 252 months (for NB) |
| `risk_free_rates.parquet` | scenario x currency x year | Discount rate curves |
| `space_params.parquet` | space | Expense parameters |
| `inflation_rates.parquet` | — | Inflation assumption |
| `run_params.parquet` | — | Model run configuration |

## Next: Level 5 — Scenarios

Level 5 adds scenario analysis: run this model across BASE/UP/DOWN interest rate scenarios, apply parameter shocks, and compare results. See `tutorial/level-5-scenarios/`.
