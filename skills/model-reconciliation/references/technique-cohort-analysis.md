# Technique: Cohort Analysis (Tier 3)

## When to Use

Run this when:
- Tier 2 residual histogram is bimodal or has heavy tails
- Tier 2 quick cohort grouping shows one age band, product, or duration bucket has significantly higher errors
- You suspect a lookup table, boundary condition, or rate schedule affects specific policy subgroups differently

Cohort analysis answers: "Which policies are wrong, and what do they have in common?"

## How to Run

### Step 1: Compute Per-Policy Error Metrics

```python
import polars as pl
import numpy as np

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

variable = "pv_claims_death"

# Compute per-policy error across all periods
def per_policy_error(gas_df, excel_df, variable):
    """Mean absolute percentage error per policy across all periods."""
    gas_agg = gas_df.group_by("Policy number").agg(
        pl.col(variable).sum().alias("gas_total")
    )
    excel_agg = excel_df.group_by("Policy number").agg(
        pl.col(variable).sum().alias("excel_total")
    )
    joined = gas_agg.join(excel_agg, on="Policy number")
    return joined.with_columns(
        ((pl.col("gas_total") - pl.col("excel_total")) / pl.col("excel_total").abs().clip(lower_bound=1e-10) * 100)
        .alias("pct_error"),
        (pl.col("gas_total") - pl.col("excel_total")).alias("abs_error"),
    )

errors = per_policy_error(gas, excel, variable)
```

### Step 2: Join with Policy Attributes

```python
mp = pl.read_parquet("model_points.parquet")

# Select key segmentation attributes
attrs = mp.select([
    "Policy number",
    "Issue age",
    "Sex",
    "Smoker Status",
    "Policy term",
    "Face amount",
    # Add any other relevant attributes
])

analysis = errors.join(attrs, on="Policy number")

# Create derived grouping columns
analysis = analysis.with_columns(
    (pl.col("Issue age") // 10 * 10).cast(pl.Int32).cast(pl.Utf8).alias("age_band"),
    pl.when(pl.col("Policy term") <= 10).then(pl.lit("short"))
      .when(pl.col("Policy term") <= 20).then(pl.lit("medium"))
      .otherwise(pl.lit("long")).alias("term_bucket"),
    pl.when(pl.col("Face amount") <= 100000).then(pl.lit("small"))
      .when(pl.col("Face amount") <= 500000).then(pl.lit("medium"))
      .otherwise(pl.lit("large")).alias("face_bucket"),
)
```

### Step 3: Group-By Analysis

```python
def cohort_stats(df, group_col):
    """Compute error statistics by cohort."""
    return df.group_by(group_col).agg(
        pl.col("pct_error").mean().alias("mean_pct_error"),
        pl.col("pct_error").std().alias("std_pct_error"),
        pl.col("pct_error").abs().mean().alias("mean_abs_pct_error"),
        pl.col("pct_error").abs().max().alias("max_abs_pct_error"),
        pl.len().alias("count"),
    ).sort(group_col)

# Run for each grouping dimension
for dim in ["age_band", "Sex", "Smoker Status", "term_bucket", "face_bucket"]:
    if dim in analysis.columns:
        print(f"\n=== Error by {dim} ===")
        print(cohort_stats(analysis, dim))
```

### Step 4: Identify the Problem Cohort

```python
# Find cohorts with significantly higher error than average
overall_mean = float(analysis["pct_error"].abs().mean())

for dim in ["age_band", "Sex", "Smoker Status", "term_bucket"]:
    if dim not in analysis.columns:
        continue
    stats = cohort_stats(analysis, dim)
    problem_cohorts = stats.filter(pl.col("mean_abs_pct_error") > overall_mean * 2)
    if problem_cohorts.height > 0:
        print(f"\n** PROBLEM COHORT in {dim}: **")
        print(problem_cohorts)
```

### Step 5: Drill Into the Problem Cohort

```python
# Example: if age_band 60 is the problem
problem_policies = analysis.filter(pl.col("age_band") == "60").sort("pct_error", descending=True)
print(f"\nTop 5 worst policies in problem cohort:")
print(problem_policies.head(5).select(["Policy number", "Issue age", "pct_error", "gas_total", "excel_total"]))

# Now inspect the worst policy with Tier 1 (single-cell trace)
worst_policy = int(problem_policies["Policy number"].head(1).item())
print(f"\nInspect policy {worst_policy} with single-cell trace")
```

### Visualize: Error by Cohort

```python
import altair as alt

# Box plot of errors by age band
box = alt.Chart(analysis).mark_boxplot().encode(
    x=alt.X("age_band:N", title="Age Band"),
    y=alt.Y("pct_error:Q", title="% Error (Gas - Excel)"),
).properties(
    title=f"{variable}: Error Distribution by Age Band",
    width=500, height=300,
)
box.save(f"reconciliation/plots/cohort_{variable}_age.png")

# Bar chart of mean absolute error by cohort
bars = alt.Chart(cohort_stats(analysis, "age_band")).mark_bar().encode(
    x=alt.X("age_band:N", title="Age Band"),
    y=alt.Y("mean_abs_pct_error:Q", title="Mean |% Error|"),
    color=alt.condition(
        alt.datum.mean_abs_pct_error > overall_mean * 2,
        alt.value("#e45756"),  # red for problem cohorts
        alt.value("#4c78a8"),  # blue for normal
    ),
).properties(
    title=f"{variable}: Mean Absolute Error by Age Band",
    width=500, height=300,
)
bars.save(f"reconciliation/plots/cohort_bar_{variable}_age.png")
```

## How to Interpret

| Pattern | Interpretation | Likely Root Cause |
|---|---|---|
| Error concentrated in oldest age band | Age-dependent calculation boundary | Mortality table cap, max age handling, `age_under_100` logic |
| Error differs by Sex | Gender-specific table lookup wrong | Mortality table gender column mapping, select vs ultimate |
| Error differs by Smoker Status | Smoker/non-smoker rate lookup wrong | VBT table dimension, smoker indicator coding |
| Error concentrated in short-term policies | Duration-dependent boundary | Surrender charge schedule, premium term vs policy term |
| Error concentrated in large face amounts | Scale-dependent calculation | Per-unit vs per-policy rates, banding thresholds |
| Error in in-force (1-36) but not future-dated | Existing vs new business treatment | Valuation date handling, initial reserve, retroactive adjustments |

## What to Do Next

1. Record cohort analysis results in the build log: which dimension, which cohort, mean error, count
2. Pick the worst policy from the problem cohort and run Tier 1 (single-cell trace) on it
3. Compare the problem cohort's calculation inputs (rates, factors) against a normal cohort's — the difference reveals which input is wrong for that group
4. After fixing, re-run cohort analysis to confirm the problem cohort's error dropped to match other cohorts
5. If multiple cohorts are problematic across different dimensions, each is likely a separate bug — fix one at a time
