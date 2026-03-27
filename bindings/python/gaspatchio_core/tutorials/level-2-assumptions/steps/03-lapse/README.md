# Step 03: Lapse Rate Table

## What changed from Step 02

- `lapse_rate` column removed from model points (it's no longer a scalar per policy)
- `lapse_rates.parquet` added to `data/` (dimension: `month`, values: monthly rates)
- `lapse_table` added alongside `mort_table` in `load_assumptions()`
- `af.lapse_rate_monthly` now comes from `lapse_table.lookup(month=af.month)`

## Key pattern

```python
lapse_table = Table(
    name="lapse",
    source=pl.read_parquet(DATA_DIR / "lapse_rates.parquet"),
    dimensions={"month": "month"},
    value="lapse_rate_mth",
)

af.lapse_rate_monthly = lapse_table.lookup(month=af.month)
```

The lapse table contains one row per projection month (0–11). The lookup
returns the pre-computed monthly rate directly — no annual-to-monthly
conversion needed because the table already holds monthly values.

## Combined decrements

With two stochastic decrements, the survival factor at each month is:

```python
af.combined_decrement = 1.0 - (1.0 - af.qx_monthly) * (1.0 - af.lapse_rate_monthly)
```

This is the **independent decrements model**: it assumes death and lapse happen
independently. The survival at each month is the probability of surviving both.

## Lapse schedule

| Month | lapse_rate_mth | Why |
|-------|---------------|-----|
| 0     | 0.012         | Highest lapse at policy inception |
| 6     | 0.005         | Declining as committed policyholders remain |
| 11    | 0.003         | Lowest by end of year 1 |

## Observable difference

Compared to Step 02, `pv_net_cf` is slightly lower because more policies
lapse in month 0 (rate 1.2%) than Step 02's constant monthly equivalent of
~0.43% (5% annual lapse / 12).

## Data directory

```
data/
  model_points.parquet   — 3 policies (no lapse_rate column)
  mortality.parquet      — 92 rows (ages 25–70, M and F)
  lapse_rates.parquet    — 12 rows (one per projection month)
```
