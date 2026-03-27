# Step 02 -- Conditional Shocks

Step 01 applied uniform shocks to entire assumption tables. Step 02 introduces
**conditional shocks** that target specific rows, times, or use chained
transformations.

## Shock Types Demonstrated

### FilteredShock (`where` clause)

Apply a shock only to rows matching a dimension filter. The PANDEMIC_ELDERLY
scenario uses two filtered shocks on `mortality_select`:

- `multiply: 1.5` where `attained_age >= 65` (elderly)
- `multiply: 1.1` where `attained_age < 65` (younger)

This models a pandemic that disproportionately affects older lives.

### TimeConditionalShock (`when` clause)

Apply a shock at specific projection times. The DELAYED_RATE_SHOCK scenario
adds -100bp to `risk_free_rates` only when `year >= 3`, modelling a delayed
economic downturn.

### PipelineShock (chained operations)

Chain multiple transformations in sequence. The MORT_FLOOR scenario applies:

1. `multiply: 1.3` (30% uplift)
2. `clip: {min: 0.005}` (floor at 0.5%)

The pipeline ensures shocked mortality rates never fall below the minimum,
regardless of the base rate.

## How to Run

```bash
uv run python tutorial/level-5-scenarios/steps/02-conditional-shocks/run_scenarios.py
```

## Output

The script produces `report/` containing:

- **cashflow_comparison.png** -- Monthly net cashflow for policy 1 across all
  scenarios. Look for the DELAYED_RATE_SHOCK line diverging at month 36
  (year 3) when the rate drop kicks in.
- **death_claims.png** -- PV death claims grouped by product and scenario.
  The PANDEMIC_ELDERLY scenario shows the largest increase because all model
  points are age 70+ and receive the full +50% shock.
- **report.md** -- Full report with results table, charts, and audit trail.

## What to Look For

1. **Pandemic timing**: The PANDEMIC_ELDERLY cashflow impact is immediate
   because the mortality shock applies from month 0. Compare with
   DELAYED_RATE_SHOCK which only diverges at year 3.
2. **Age targeting**: Since all 8 model points have `age_at_entry = 70`,
   every policy qualifies for the `attained_age >= 65` filter. With a
   younger portfolio, the two-tier shock would produce a split impact.
3. **Floor effect**: The MORT_FLOOR pipeline prevents low base mortality
   rates from staying below 0.5% after the 30% uplift. This is visible
   in the death claims bar chart.
