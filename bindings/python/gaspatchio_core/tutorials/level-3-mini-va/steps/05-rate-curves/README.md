# Step 05: Valuation Basis — Rate Curve Discounting

> **Prerequisites:** Read the base model docstring (`base/model.py` lines 1-55). This step builds on Step 04 (dynamic lapse).

## What this adds

Replaces the constant discount rate with a term-structure of risk-free rates loaded from a table. Discount rates now vary by projection year.

## Why

Insurance regulators and accounting standards require discounting at risk-free rates that reflect the term structure of interest rates — not a single flat rate. Short-term cashflows are discounted at lower rates than long-term ones (typically). This affects present values and therefore reserves, capital requirements, and pricing.

The rate curve also enables scenario analysis (Level 5): different interest rate scenarios (BASE, UP, DOWN) use different rate curves, and the model needs to look up the right curve for each scenario.

## Data files in this step

| File | Rows | Key columns | Value column | Notes |
|---|---|---|---|---|
| `risk_free_rates.parquet` | 21 | scenario (String), currency (String), year (Int64) | forward_rate (Float64) | **New file.** BASE scenario, USD, years 0-20. Upward-sloping: 2.0% at year 0 → 4.5% at year 10+ |
| All other files | | | | Unchanged from Step 04 |

## Before → After

Section 11 (discounting) is rewritten:

```python
# BEFORE (step 04): constant rate
disc_rate_mth = (1 + DISCOUNT_RATE_ANNUAL) ** (1 / 12) - 1
af.disc_factors = (af.month.cast(pl.Float64) * -1.0 * math.log(1 + disc_rate_mth)).exp()

# AFTER (step 05): rate curve lookup
af.year = af.month // 12
af.disc_rate = risk_free_rates.lookup(
    scenario=pl.lit("BASE"), currency=pl.lit("USD"), year=af.year
)
af.disc_rate_mth = (1.0 + af.disc_rate) ** (1.0 / 12.0) - 1.0

# Cumulative product of per-period discount factors (correct for varying rates)
af.per_period_disc = 1.0 / (1.0 + af.disc_rate_mth)
af.disc_factors = af.per_period_disc.cum_prod()
```

Key patterns:
- **`pl.lit("BASE")`** — hardcodes the scenario dimension for now. In Level 5, this becomes `af.scenario_id` for multi-scenario runs.
- **Rate varies by year** — different projection years use different discount rates from the curve
- **Cumulative product for varying rates** — with a constant rate you can use `(1+r)^(-t)`, but with varying rates you must multiply per-period factors: `df[t] = 1/(1+r[0]) × 1/(1+r[1]) × ... × 1/(1+r[t])`

## Expected output

```
┌──────────┬───────────────┬───────────┬─────────────┐
│ point_id ┆ pv_net_cf     ┆ pv_claims ┆ pv_premiums │
│ ---      ┆ ---           ┆ ---       ┆ ---         │
│ i64      ┆ f64           ┆ f64       ┆ f64         │
╞══════════╪═══════════════╪═══════════╪═════════════╡
│ 1        ┆ 400199.765956 ┆ 6.0555e6  ┆ 0.0         │
│ 2        ┆ 243426.696042 ┆ 1.9904e6  ┆ 0.0         │
│ 3        ┆ 682007.713398 ┆ 2.0143e7  ┆ 0.0         │
│ 4        ┆ 403898.847295 ┆ 4.0664e6  ┆ 0.0         │
└──────────┴───────────────┴───────────┴─────────────┘
```

PV values changed from Step 04 — the lower short-end rates (2% vs 4% constant) increase PVs for near-term cashflows. The cumulative product formula correctly handles the varying rate across projection years.

## Running this step

```bash
# Standalone
uv run python tutorial/level-3-mini-va/steps/05-rate-curves/model.py

# Via CLI
uv run gspio run-single-policy tutorial/level-3-mini-va/steps/05-rate-curves/model.py tutorial/level-3-mini-va/steps/05-rate-curves/data/model_points.parquet 1
```

## When a user asks about this

- "How do I use a yield curve for discounting?"
- "How do I look up rates by projection year?"
- "How do I implement term-structure discounting?"
- "How do I prepare my model for scenario analysis?"
- "What does pl.lit() do?"
