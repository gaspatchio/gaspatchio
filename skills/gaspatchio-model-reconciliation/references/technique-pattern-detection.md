# Technique: Pattern Detection (Tier 2)

## When to Use

Run this when Tier 1 (Direct Inspection) didn't identify the root cause. You need to see the **shape** of the error across all policies before choosing a Tier 3 statistical technique.

## Steps

### 1. Scatter Plot: Model vs Gold Standard

Plot gaspatchio values (y-axis) against Excel values (x-axis) for all policies at a representative time step. Perfect agreement = points on the y=x line.

```python
import polars as pl
import altair as alt
import numpy as np

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

variable = "pv_claims_death"
period = 12  # pick a representative period

# Join on policy + period
gas_slice = gas.filter(pl.col("t") == period).select(["Policy number", variable])
excel_slice = excel.filter(pl.col("t") == period).select([
    "Policy number",
    pl.col(variable).alias(f"{variable}_excel"),
])

joined = gas_slice.join(excel_slice, on="Policy number")

# Scatter with identity line
points = alt.Chart(joined).mark_point(opacity=0.4, size=15).encode(
    x=alt.X(f"{variable}_excel:Q", title="Excel (Gold Standard)"),
    y=alt.Y(f"{variable}:Q", title="Gaspatchio (Model)"),
    tooltip=["Policy number"],
)

# y = x reference line
x_min = float(joined[f"{variable}_excel"].min())
x_max = float(joined[f"{variable}_excel"].max())
identity = alt.Chart(pl.DataFrame({
    "x": [x_min, x_max], "y": [x_min, x_max],
})).mark_line(color="gray", strokeDash=[4, 4]).encode(x="x:Q", y="y:Q")

chart = (points + identity).properties(
    title=f"{variable} at period {period}: Model vs Gold Standard",
    width=500, height=400,
)
chart.save(f"reconciliation/plots/scatter_{variable}_t{period}.png")
```

**What to look for:**

| Pattern | Interpretation | Next Step |
|---|---|---|
| Tight cluster on y=x line | Good match, small random differences | Probably done, or check edge policies |
| Linear but shifted off y=x | Systematic proportional or additive bias | Escalate to **Linear Regression** (Tier 3) |
| Two distinct clusters | Cohort-specific error | Escalate to **Cohort Analysis** (Tier 3) |
| Fan shape (spreads with magnitude) | Proportional error that grows with value | Escalate to **Linear Regression** (Tier 3) |
| Random scatter (low R^2) | Multiple error sources or fundamentally different calculation | Escalate to **PCA** (Tier 3) |

### 2. Residual Histogram: Distribution of Differences

```python
diffs = joined.with_columns(
    ((pl.col(variable) - pl.col(f"{variable}_excel")) / pl.col(f"{variable}_excel").abs().clip(lower_bound=1e-10) * 100)
    .alias("pct_diff")
)

hist = alt.Chart(diffs).mark_bar().encode(
    x=alt.X("pct_diff:Q", bin=alt.Bin(maxbins=50), title="% Difference (Gas - Excel)"),
    y=alt.Y("count()", title="Number of Policies"),
).properties(
    title=f"{variable} at period {period}: Residual Distribution",
    width=500, height=300,
)
hist.save(f"reconciliation/plots/hist_{variable}_t{period}.png")

# Summary statistics
print(f"Mean diff:   {diffs['pct_diff'].mean():.4f}%")
print(f"Median diff: {diffs['pct_diff'].median():.4f}%")
print(f"Std diff:    {diffs['pct_diff'].std():.4f}%")
print(f"Max diff:    {diffs['pct_diff'].max():.4f}%")
print(f"Min diff:    {diffs['pct_diff'].min():.4f}%")
```

**What to look for:**

| Pattern | Interpretation | Next Step |
|---|---|---|
| Tight peak at 0% | Good match | Investigate the tail outliers only |
| Peak shifted from 0% | Systematic bias | Escalate to **Linear Regression** |
| Bimodal (two peaks) | Two policy groups behave differently | Escalate to **Cohort Analysis** |
| Wide flat distribution | Many different error sources | Escalate to **PCA** |
| Long right/left tail | A few outlier policies with large errors | Examine those specific policies with Tier 1 |

### 3. Quick Cohort Grouping

Group policies by key attributes and check if errors concentrate in specific cohorts.

```python
# Add policy attributes for grouping
mp = pl.read_parquet("model_points.parquet")
analysis = diffs.join(mp.select(["Policy number", "Issue age", "Sex", "Policy term"]), on="Policy number")

# Age band grouping
analysis = analysis.with_columns(
    (pl.col("Issue age") // 10 * 10).alias("age_band")
)

cohort_stats = analysis.group_by("age_band").agg(
    pl.col("pct_diff").mean().alias("mean_diff"),
    pl.col("pct_diff").std().alias("std_diff"),
    pl.col("pct_diff").abs().mean().alias("mean_abs_diff"),
    pl.len().alias("count"),
).sort("age_band")

print(cohort_stats)
```

**What to look for:**

| Pattern | Interpretation | Next Step |
|---|---|---|
| All cohorts have similar mean_diff | Error is uniform across cohorts — not cohort-specific | Try **Linear Regression** or **Time-series** |
| One age band has much higher error | Age-dependent bug (lookup table, boundary) | Escalate to **Cohort Analysis** for deep drill-down |
| Error differs by Sex | Gender-specific table lookup error | Check mortality/assumption table gender mapping |
| Error differs by Policy term | Duration-dependent calculation bug | Escalate to **Time-series Residual** |

## Output

Save all plots to `reconciliation/plots/` and report key findings in the build log. Include:
- Which pattern you observed (from the tables above)
- The summary statistics (mean, median, std of differences)
- Which Tier 3 technique you're escalating to and why
