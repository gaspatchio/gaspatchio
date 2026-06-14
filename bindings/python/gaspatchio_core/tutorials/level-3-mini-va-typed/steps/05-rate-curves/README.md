# Step 05 (Typed Variant): Rate Curves — Parallel & Key-Rate Shifts

> **Prerequisites:** Read typed Step 02 (`02-select-mort/model.py`). This step
> builds directly on that model, replacing the flat discount rate with a
> non-flat yield curve and demonstrating curve shock API.

## What this adds

Replaces the flat 4% zero-rate curve from Step 02 with an upward-sloping
five-knot term structure, then runs three discount scenarios side-by-side using
the `Curve` shift API:

| Scenario | Description | API |
|---|---|---|
| BASE | Non-flat zero rates loaded from parquet | `Curve.from_zero_rates(...)` |
| PARALLEL+100 | All knots shifted +100 bps | `curve.shift_parallel(bps=100)` |
| KEYRATE+50 | 5-year knot only shifted +50 bps | `curve.key_rate_shift(tenor=5.0, bps=50)` |

The projection cashflows (mortality, lapses, account value, claims) are
identical across all three runs. Only the discount factors differ, so the
comparison isolates the rate sensitivity of present values.

## Why this matters

Regulatory frameworks (IFRS 17, US principle-based reserves, Solvency II)
require interest-rate sensitivity analysis. The `Curve` shift API makes it
straightforward to define a base economic scenario and apply standardised
shocks without constructing separate rate tables for each scenario.

## Data files

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `curve.parquet` | 5 | tenor (f64) | zero_rate (f64) | **Replaced.** Upward-sloping: 2.0% at 1y → 4.5% at 30y |
| `model_points.parquet` | 4 | point_id | — | Unchanged from Step 02 |
| `mortality_select.parquet` | 3500 | table_id, attained_age, duration | mort_rate | Unchanged |
| `mortality_scalars.parquet` | 15 | scalar_id, duration | mort_scalar | Unchanged |
| `inv_returns.parquet` | 241 | t, fund_index | inv_return_mth | Unchanged |

Curve knots:

```
tenor:     [1.0,  5.0,   10.0,  20.0,  30.0]
zero_rate: [0.02, 0.025, 0.035, 0.040, 0.045]
```

## Before → After: the untyped approach vs the typed Curve API

```python
# BEFORE (untyped step 05): build a rate table, look up by projection year
# Three scenarios require three separate rate tables in parquet.
risk_free_rates = Table(
    name="risk_free_rates",
    source=pl.read_parquet(DATA_DIR / "risk_free_rates.parquet"),
    dimensions={"scenario": "scenario", "currency": "currency", "year": "year"},
    value="forward_rate",
)
af.disc_rate = risk_free_rates.lookup(
    scenario=pl.lit("PARALLEL_UP"), currency=pl.lit("USD"), year=af.year
)
af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
af.disc_factors = af.per_period_disc.cum_prod()

# AFTER (typed step 05): derive shifted curves from a single base Curve object.
# No extra parquet files; shifts are applied in Python.
curve_base = Curve.from_zero_rates(tenors=[1.0, 5.0, 10.0, 20.0, 30.0],
                                   rates=[0.02, 0.025, 0.035, 0.040, 0.045])

curve_parallel = curve_base.shift_parallel(bps=100)    # NEW Curve — all knots +100bps
curve_keyrate  = curve_base.key_rate_shift(tenor=5.0, bps=50)  # NEW Curve — 5y knot +50bps

# Each curve returns a list[float] of discount factors at the projection t-grid.
disc_factors_list = curve.discount_factor(t_years_list)   # list[float], len 241
af.disc_factors = pl.lit(
    pl.Series("disc_factors", [disc_factors_list], dtype=pl.List(pl.Float64))
).first()
```

Key patterns:

- **`shift_parallel(bps=...)` returns a new `Curve`** — the original is unchanged
  (frozen dataclass). Never mutates in place.
- **`key_rate_shift(tenor=..., bps=...)` requires an exact knot tenor** — passing
  a tenor not in `curve.tenors` raises `ValueError`.
- **Factor the curve out of `main()`** — passing `curve` as an argument lets you
  call `main(af, curve)` three times with three Curves and compare the resulting
  DataFrames, rather than maintaining three copies of the full model.

## Expected output

```
Curve knots (zero rates):
  BASE:         [0.02, 0.025, 0.035, 0.04, 0.045]
  PARALLEL+100: [0.03, 0.035, 0.045, 0.05, 0.055]
  KEYRATE+50:   [0.02, 0.03, 0.035, 0.04, 0.045]

PV Net Cashflow — Three-Scenario Comparison
(BASE: non-flat curve | PARALLEL+100: all knots +100bps | KEYRATE+50: 5y knot +50bps)

shape: (4, 4)
┌──────────┬────────────────┬───────────────────────┬─────────────────────┐
│ point_id ┆ pv_net_cf_base ┆ pv_net_cf_parallel100 ┆ pv_net_cf_keyrate50 │
│ ---      ┆ ---            ┆ ---                   ┆ ---                 │
│ i64      ┆ f64            ┆ f64                   ┆ f64                 │
╞══════════╪════════════════╪═══════════════════════╪═════════════════════╡
│ 1        ┆ 393072.301156  ┆ 385877.270586         ┆ 388886.515582       │
│ 2        ┆ 205109.200413  ┆ 195879.052223         ┆ 203017.602365       │
│ 3        ┆ 714502.180263  ┆ 718681.961813         ┆ 721951.019996       │
│ 4        ┆ 366506.99478   ┆ 353820.425684         ┆ 360623.644778       │
└──────────┴────────────────┴───────────────────────┴─────────────────────┘

PV Impact (vs BASE):
shape: (4, 3)
┌──────────┬────────────────┬───────────────┐
│ point_id ┆ delta_parallel ┆ delta_keyrate │
│ ---      ┆ ---            ┆ ---           │
│ i64      ┆ f64            ┆ f64           │
╞══════════╪════════════════╪═══════════════╡
│ 1        ┆ -7195.03057    ┆ -4185.785574  │
│ 2        ┆ -9230.14819    ┆ -2091.598048  │
│ 3        ┆ 4179.78155     ┆ 7448.839733   │
│ 4        ┆ -12686.569095  ┆ -5883.350002  │
└──────────┴────────────────┴───────────────┘
```

### Reading the results

**Points 1, 2, 4** — parallel shift reduces PV (`delta_parallel < 0`): higher
discount rates shrink present values of future net cashflows for these longer
policies (10y, 20y, 15y terms). Key-rate impact is smaller in absolute terms
because only one knot changes.

**Point 3** — 5-year term, age 65. Both shifts *increase* PV here. The net
cashflow for a very short, high-AV policy includes large account-value changes;
at higher rates, those near-term AV changes are discounted less (they are
already near t=0). More strikingly, the 5y key-rate shock (+50bps) has a
*larger* absolute impact than the 100bps parallel shock — because this policy
matures at exactly 5 years, it is maximally sensitive to the 5y tenor. A
localised shock at 5y affects it more than the same total bps spread across 30
years of curve.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va-typed/steps/05-rate-curves/model.py

# Via CLI (single policy)
uv run gspio run-single-policy \
    tutorial/level-3-mini-va-typed/steps/05-rate-curves/model.py \
    tutorial/level-3-mini-va-typed/steps/05-rate-curves/data/model_points.parquet 1
```

## When a user asks about this

- "How do I apply a parallel shift to a yield curve?"
- "How do I do a key-rate duration shock?"
- "How do I run multiple interest rate scenarios without separate data files?"
- "How do I build a term structure of interest rates for discounting?"
- "How does `Curve.shift_parallel` work?"
- "How does `Curve.key_rate_shift` work?"
- "What is a key-rate sensitivity analysis?"
- "How do I stress-test a model under interest rate shocks?"
- "What does IFRS 17 require for interest rate sensitivity?"
