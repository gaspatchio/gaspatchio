# Technique: Error Heatmap (Tier 3)

## When to Use

Run this when:
- You need to visualize WHERE errors concentrate across the full policy x time-step space
- You want to quickly see if errors are scattered randomly or cluster in specific blocks
- Other techniques have identified a problem but you need to see the spatial pattern before fixing

A heatmap of the full (policy x period) difference matrix makes structure visible at a glance.

## How to Run

### Single-Variable Heatmap

```python
import polars as pl
import altair as alt
import numpy as np

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

variable = "pv_claims_death"
max_period = 120  # limit to first 120 periods for readability

# Compute percentage difference per (policy, period)
gas_sub = gas.filter(pl.col("t") <= max_period).select(["Policy number", "t", variable])
excel_sub = excel.filter(pl.col("t") <= max_period).select([
    "Policy number", "t",
    pl.col(variable).alias(f"{variable}_excel"),
])

joined = gas_sub.join(excel_sub, on=["Policy number", "t"])
joined = joined.with_columns(
    ((pl.col(variable) - pl.col(f"{variable}_excel"))
     / pl.col(f"{variable}_excel").abs().clip(lower_bound=1e-10) * 100)
    .alias("pct_diff")
)

# Heatmap
chart = alt.Chart(joined).mark_rect().encode(
    x=alt.X("t:O", title="Period", axis=alt.Axis(values=list(range(0, max_period + 1, 12)))),
    y=alt.Y("Policy number:O", title="Policy", sort="ascending"),
    color=alt.Color(
        "pct_diff:Q",
        scale=alt.Scale(scheme="redblue", domainMid=0, domain=[-5, 5]),
        title="% Diff",
    ),
    tooltip=["Policy number", "t", "pct_diff"],
).properties(
    title=f"{variable}: Error Heatmap (Policy x Period)",
    width=600, height=800,
)
chart.save(f"reconciliation/plots/heatmap_{variable}.png")
```

### Aggregate Heatmap (Mean Error Across Variables)

```python
variables = ["mortality_rate", "lapse_rate", "pols_if", "claims_death", "premium_income"]

# Build mean absolute error across all variables per (policy, period)
all_diffs = gas.filter(pl.col("t") <= max_period).select(["Policy number", "t"])

for var in variables:
    if var in gas.columns and var in excel.columns:
        gas_col = gas.filter(pl.col("t") <= max_period)[var].to_numpy().astype(float)
        excel_col = excel.filter(pl.col("t") <= max_period)[var].to_numpy().astype(float)
        denom = np.where(np.abs(excel_col) > 1e-10, np.abs(excel_col), 1.0)
        pct = np.abs((gas_col - excel_col) / denom * 100)
        all_diffs = all_diffs.with_columns(pl.Series(name=f"{var}_err", values=pct))

err_cols = [c for c in all_diffs.columns if c.endswith("_err")]
all_diffs = all_diffs.with_columns(
    pl.mean_horizontal(err_cols).alias("mean_abs_err")
)

chart = alt.Chart(all_diffs).mark_rect().encode(
    x=alt.X("t:O", title="Period", axis=alt.Axis(values=list(range(0, max_period + 1, 12)))),
    y=alt.Y("Policy number:O", title="Policy", sort="ascending"),
    color=alt.Color(
        "mean_abs_err:Q",
        scale=alt.Scale(scheme="reds", domain=[0, 5]),
        title="Mean |% Err|",
    ),
    tooltip=["Policy number", "t", "mean_abs_err"],
).properties(
    title="Mean Absolute Error Across All Variables",
    width=600, height=800,
)
chart.save("reconciliation/plots/heatmap_aggregate.png")
```

### Compact Heatmap (Variable x Period, Averaged Across Policies)

For a quick overview when the full policy x period heatmap is too large:

```python
# Mean error by (variable, period)
records = []
for var in variables:
    if var not in gas.columns or var not in excel.columns:
        continue
    for t in range(0, min(max_period, 60), 6):  # sample every 6 months
        gas_vals = gas.filter(pl.col("t") == t)[var].to_numpy().astype(float)
        excel_vals = excel.filter(pl.col("t") == t)[var].to_numpy().astype(float)
        denom = np.where(np.abs(excel_vals) > 1e-10, np.abs(excel_vals), 1.0)
        mean_pct = float(np.mean(np.abs((gas_vals - excel_vals) / denom * 100)))
        records.append({"variable": var, "period": t, "mean_abs_pct_err": mean_pct})

compact_df = pl.DataFrame(records)

chart = alt.Chart(compact_df).mark_rect().encode(
    x=alt.X("period:O", title="Period"),
    y=alt.Y("variable:N", title="Variable"),
    color=alt.Color(
        "mean_abs_pct_err:Q",
        scale=alt.Scale(scheme="reds", domain=[0, 5]),
        title="Mean |% Err|",
    ),
    tooltip=["variable", "period", "mean_abs_pct_err"],
).properties(
    title="Error Concentration: Variable x Period",
    width=500, height=300,
)
chart.save("reconciliation/plots/heatmap_compact.png")
```

## How to Interpret

| Visual Pattern | Interpretation | Next Step |
|---|---|---|
| **Horizontal stripe** (one policy red across all periods) | That policy has a unique error — different inputs or edge case | Inspect that policy with Tier 1 |
| **Vertical stripe** (one period red across all policies) | Something triggers at that period — rate change, boundary, event | Check what changes at that period (year boundary, rate update) |
| **Block** (specific policies AND specific periods) | Cohort-specific, duration-dependent bug | Cross-reference with Cohort Analysis |
| **Gradient** (error increasing left to right) | Compounding error over time | Escalate to Time-series Residual technique |
| **Checkerboard** (alternating high/low) | Timing convention mismatch (BOP vs EOP) | Check period alignment and timing assumptions |
| **Bottom-right corner** (late periods, high-numbered policies) | Boundary handling at policy maturity or max age | Check max age, maturity, and end-of-projection logic |
| **Uniform red** (everything equally off) | Global systematic error | Check discount rate, survival probabilities, or shared input |
| **Mostly green, scattered red dots** | A few edge-case policies at specific periods | List the (policy, period) pairs and trace each one |

## What to Do Next

1. Save the heatmap to `reconciliation/plots/` and reference it in the build log
2. Identify the dominant pattern from the table above
3. For horizontal stripes: inspect those specific policies with Tier 1
4. For vertical stripes: check what assumption or rate changes at that period
5. For blocks: cross-reference with cohort analysis to identify the shared attribute
6. For gradients: use Time-series Residual technique to quantify the drift rate
7. After fixing, regenerate the heatmap to confirm the error pattern has disappeared
