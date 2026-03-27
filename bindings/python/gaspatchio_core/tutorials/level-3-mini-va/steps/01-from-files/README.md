# Step 01: Load Assumptions from Files

> **Prerequisites:** Read the base model docstring (`base/model.py` lines 1-55) for key concepts: ActuarialFrame, `.projection`, `when/then/otherwise`, `.collect()`, and the gaspatchio vs Polars method distinction.

## What this adds

Replaces inline data dictionaries with parquet files loaded from disk. The model logic is identical — only the data source changes.

## Why

Real actuarial models load assumptions from files (parquet, CSV, Excel) maintained by assumption teams. Inline data is fine for learning, but production models separate code from data so assumptions can be updated without touching the model.

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `model_points.parquet` | 4 | point_id (Int64) | — | Same 4 policies as base, now in parquet |
| `mortality.parquet` | 70 | age (Int64) | mort_rate (Float64) | Ages 30-99 |
| `inv_returns.parquet` | 241 | t (Int64), fund_index (String) | inv_return_mth (Float64) | FUND1 only, 0.5% monthly |

## Before → After

The only change is Section 1 — inline dicts become file reads:

```python
# BEFORE (base): inline data
MORTALITY_DATA = {"age": list(range(30, 100)), "mort_rate": [...]}
mortality_table = Table(name="mortality", source=pl.DataFrame(MORTALITY_DATA), ...)

# AFTER (step 01): load from parquet
mortality_table = Table(name="mortality", source=pl.read_parquet(DATA_DIR / "mortality.parquet"), ...)
```

All other sections (2-11) are identical — same formulas, same variable names.

## Expected output

```
┌──────────┬───────────────┬───────────┬─────────────┐
│ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_premiums │
│ ---      ┆ ---           ┆ ---       ┆ ---         │
│ i64      ┆ f64           ┆ f64       ┆ f64         │
╞══════════╪═══════════════╪═══════════╪═════════════╡
│ 1        ┆ 345203.112821 ┆ 5.6454e6  ┆ 0.0         │
│ 2        ┆ 183780.777719 ┆ 1.8317e6  ┆ 0.0         │
│ 3        ┆ 643026.987196 ┆ 1.9260e7  ┆ 0.0         │
│ 4        ┆ 311048.533918 ┆ 3.7319e6  ┆ 0.0         │
└──────────┴───────────────┴───────────┴─────────────┘
```

These match the base model exactly — confirming the refactor from inline to files is clean.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va/steps/01-from-files/model.py

# Via CLI (single policy)
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/01-from-files/model.py tutorial/level-3-mini-va/steps/01-from-files/data/model_points.parquet 1

# With output file for analysis
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/01-from-files/model.py tutorial/level-3-mini-va/steps/01-from-files/data/model_points.parquet 1 --output-file /tmp/step01.parquet
```

## When a user asks about this

- "How do I load assumptions from files?"
- "How do I use parquet files with gaspatchio?"
- "How do I separate my data from my model code?"
- "How do I switch from inline data to file-based assumptions?"
