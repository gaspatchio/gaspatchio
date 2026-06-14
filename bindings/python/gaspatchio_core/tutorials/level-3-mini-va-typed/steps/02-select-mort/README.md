# Typed Step 02: Select/Ultimate Mortality with MortalityTable

> **Prerequisites:** Read `level-3-mini-va-typed/base/model.py` (lines 1-85) for typed-input concepts. This step builds on typed Step 01 (file-based assumptions).

## What this adds

Replaces the simple aggregate mortality table from the typed base with a select/ultimate structure — the industry standard for life insurance pricing and reserving. Same actuarial logic as `level-3-mini-va/steps/02-select-mort/`, but using the `MortalityTable` typed input instead of manual `Table.lookup()` + `.clip()`.

## Why

Select/ultimate tables capture the "selection effect": newly underwritten policyholders have lower mortality than the general population at the same age. Mortality depends on both attained age AND how long since underwriting (duration). After the select period (25 years in this dataset), rates revert to "ultimate" rates.

`MortalityTable` with `structure="select_ultimate"` encodes this convention explicitly — the `select_period` metadata states the clamping rule, making it auditable without reading the calculation code.

## What's different in the typed version

### Mortality lookup: before (untyped) and after (typed)

**Untyped `level-3-mini-va/steps/02-select-mort/`:**

```python
# Original: manual 3-step pattern
af.duration_capped = af.duration.clip(upper_bound=SELECT_PERIOD_LEN - 1)  # cap manually
af.base_mort_rate = mortality_select.lookup(
    table_id=af.mort_table_id,
    attained_age=af.age,
    duration=af.duration_capped,                    # pass capped duration
)
```

**Typed `level-3-mini-va-typed/steps/02-select-mort/`:**

```python
# Typed: MortalityTable carries the select_period metadata; .at() clamps internally
af.base_mort_rate = mortality.at(
    age=af.age,
    duration=af.duration,                           # no manual .clip() needed
    table_id=af.mort_table_id,                      # extra dim flows through **other
)
```

The `select_period=24` argument to `MortalityTable` encodes the same rule as `.clip(upper_bound=24)` — both produce `min(duration, 24)`.

### Table construction: column renaming

The parquet's age column is named `attained_age`, but `MortalityTable.at()` dispatches via the dimension key `"age"`. `DataDimension(column="attained_age", rename_to="age")` renames the column during Table construction so both the dimension key and the internal DataFrame column are `"age"`:

```python
from gaspatchio_core.assumptions._dimensions import DataDimension

mortality_select_raw = Table(
    name="mortality_select",
    source=pl.read_parquet(DATA_DIR / "mortality_select.parquet"),
    dimensions={
        "table_id": "table_id",
        "age": DataDimension(column="attained_age", rename_to="age"),  # rename here
        "duration": "duration",
    },
    value="mort_rate",
)
mortality = MortalityTable(
    table=mortality_select_raw,
    age_basis="age_last_birthday",
    structure="select_ultimate",
    select_period=24,
)
```

### Mortality scalars stay as raw Table

`mortality_scalars` is a multiplier table (not mortality-shaped). It is not wrapped in `MortalityTable` — the manual `.clip(upper_bound=SCALAR_DURATION_CAP)` is preserved:

```python
af.mort_scalar = mortality_scalars.lookup(
    scalar_id=af.mort_scalar_id,
    duration=af.duration.clip(upper_bound=SCALAR_DURATION_CAP),
)
```

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `model_points.parquet` | 4 | point_id | — | **New columns:** `mort_table_male`, `mort_table_female`, `mort_scalar_id` |
| `mortality_select.parquet` | 3500 | table_id (String), attained_age (Int64), duration (Int64) | mort_rate (Float64) | T001=male, T002=female. 70 ages × 25 durations × 2 tables |
| `mortality_scalars.parquet` | 15 | scalar_id (String), duration (Int64) | mort_scalar (Float64) | S001: scalars from 0.80 (dur 0) to 1.08 (dur 14) |
| `inv_returns.parquet` | 241 | t, fund_index | inv_return_mth | Unchanged from Step 01 |
| `curve.parquet` | 2 | tenor | zero_rate | Flat 4% curve (same as Step 01) |

## Parity gate

This step is a parity test between typed and untyped semantics. The output must match `level-3-mini-va/steps/02-select-mort/` exactly.

**Parity: exact match (to 12 significant figures).**

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

Numbers changed from typed Step 01 (which used a simple aggregate mortality table). Select/ultimate mortality produces different rates than age-only lookup.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va-typed/steps/02-select-mort/model.py

# Via CLI (single policy)
uv run gspio run-single-policy tutorial/level-3-mini-va-typed/steps/02-select-mort/model.py tutorial/level-3-mini-va-typed/steps/02-select-mort/data/model_points.parquet 1
```

## Implementation notes for MortalityTable users

**Bug discovered and fixed during this step:** `MortalityTable._at_select_ultimate()` originally used `pl.when(duration > select_period)` for clamping. This fails when `duration` is a gaspatchio `ColumnProxy` (which returns a `ConditionExpression`, not a `pl.Expr`, from `>`), and also fails when duration is a list-typed column (post-timeline) because `pl.when` operates at the row level, not inside lists.

The fix uses `list_clip` (the Rust plugin backing `ColumnProxy.clip()`) for list-typed inputs, and `pl.Expr.clip()` for scalar inputs. Both paths are now covered and all 33 mortality unit tests pass.

**Column naming requirement:** `MortalityTable._at_select_ultimate` calls `self.table.lookup(age=..., duration=..., **other)`. The underlying Table's dimension key must be `"age"` (not the parquet column name `"attained_age"`). Use `DataDimension(column="attained_age", rename_to="age")` to align them.

## When a user asks about this

- "How do I use MortalityTable with a select/ultimate table?"
- "How does MortalityTable handle duration clamping in the typed API?"
- "What is select_period in MortalityTable?"
- "How do I rename a parquet column to match MortalityTable's expected dimension names?"
- "How do I pass extra table dimensions (like table_id) to MortalityTable.at()?"
