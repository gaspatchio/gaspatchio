# Step 01: Load Assumptions from Files

> **Prerequisites:** Read the typed base model docstring (`base/model.py` lines 1-85) for key concepts: ActuarialFrame, `.projection`, `when/then/otherwise`, `.collect()`, and the typed-input primitives `MortalityTable`, `Curve`, and `Schedule`.

## What this adds

Replaces all inline data dictionaries with parquet files loaded from disk. The model logic is identical — only the data source changes.

This step covers the same refactor as `level-3-mini-va/steps/01-from-files`, with the additional requirement that **typed inputs** (`MortalityTable` and `Curve`) are also built from parquet rather than from inline literals. The `Curve` is now loaded from `curve.parquet` (tenor + zero_rate columns) instead of hardcoded `[1.0, 30.0]` / `[0.04, 0.04]` lists.

## Why

Real actuarial models load assumptions from files (parquet, CSV, Excel) maintained by assumption teams. Inline data is fine for learning, but production models separate code from data so assumptions can be updated without touching the model. This applies equally to raw tables and to typed primitives like `Curve` — a yield curve lives in a data store, not in source code.

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `model_points.parquet` | 4 | point_id (Int64) | — | Same 4 policies as typed base |
| `mortality.parquet` | 70 | age (Int64) | mort_rate (Float64) | Ages 30–99 annual qx |
| `inv_returns.parquet` | 241 | t (Int64), fund_index (String) | inv_return_mth (Float64) | FUND1 only, 0.5% monthly |
| `curve.parquet` | 2 | tenor (Float64) | zero_rate (Float64) | Flat 4% curve at tenors 1yr and 30yr |

## Before → After

The only change is Section 1 and `__main__` — inline dicts become file reads:

```python
# BEFORE (typed base): inline data
MORTALITY_DATA = {"age": list(range(30, 100)), "mort_rate": [...]}
mortality_table_raw = Table(name="mortality", source=pl.DataFrame(MORTALITY_DATA), ...)

curve = Curve.from_zero_rates(tenors=[1.0, 30.0], rates=[0.04, 0.04])

# AFTER (step 01): load from parquet
mortality_table_raw = Table(name="mortality", source=pl.read_parquet(DATA_DIR / "mortality.parquet"), ...)

curve_df = pl.read_parquet(DATA_DIR / "curve.parquet")
curve = Curve.from_zero_rates(
    tenors=curve_df["tenor"].to_list(),   # Curve.from_zero_rates requires list[float]
    rates=curve_df["zero_rate"].to_list(),
)
```

All other sections (2-11) are identical — same formulas, same variable names, same typed primitives (`MortalityTable.at()`, `Schedule`, discount factor broadcast).

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

These match the typed base model exactly — confirming the refactor from inline to files is clean.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va-typed/steps/01-from-files/model.py

# Via CLI (single policy)
uv run gspio run-single-policy tutorial/level-3-mini-va-typed/steps/01-from-files/model.py tutorial/level-3-mini-va-typed/steps/01-from-files/data/model_points.parquet 1

# With output file for analysis
uv run gspio run-single-policy tutorial/level-3-mini-va-typed/steps/01-from-files/model.py tutorial/level-3-mini-va-typed/steps/01-from-files/data/model_points.parquet 1 --output-file /tmp/typed-step01.parquet
```

## When a user asks about this

- "How do I load a Curve from a parquet file?"
- "How do I load a MortalityTable from a parquet file?"
- "How do I separate typed assumption data from model code?"
- "How do I use parquet files with gaspatchio typed inputs?"
- "Why does Curve.from_zero_rates need `.to_list()` when reading from Polars?"
