# Technique: Time-Series Residual Analysis (Tier 3)

## When to Use

Run this when:
- The error heatmap shows a gradient (error growing over time)
- Tier 2 shows early periods match but late periods diverge
- You suspect a compounding error, timing drift, or rate that changes at a specific period
- A previous fix (e.g., YEARFRAC, leap year) suggests time-dependent behavior

Time-series residual analysis answers: "Does the error grow, oscillate, or step-change over the projection?"

## How to Run

### Per-Policy Difference Trajectory

```python
import polars as pl
import numpy as np
import altair as alt

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

variable = "pv_claims_death"
sample_policies = [1, 5, 15, 30, 100, 250, 500]  # representative sample

# Compute difference trajectory for each policy
trajectories = []
for pid in sample_policies:
    gas_p = gas.filter(pl.col("Policy number") == pid).sort("t")
    excel_p = excel.filter(pl.col("Policy number") == pid).sort("t")

    if gas_p.height == 0 or excel_p.height == 0:
        continue

    g = gas_p[variable].to_numpy().astype(float)
    e = excel_p[variable].to_numpy().astype(float)
    t = gas_p["t"].to_numpy()

    denom = np.where(np.abs(e) > 1e-10, np.abs(e), 1.0)
    pct_diff = (g - e) / denom * 100

    for i in range(len(t)):
        trajectories.append({
            "Policy number": int(pid),
            "t": int(t[i]),
            "pct_diff": float(pct_diff[i]),
            "abs_diff": float(g[i] - e[i]),
        })

traj_df = pl.DataFrame(trajectories)

# Line chart: difference over time per policy
chart = alt.Chart(traj_df).mark_line(opacity=0.6).encode(
    x=alt.X("t:Q", title="Period"),
    y=alt.Y("pct_diff:Q", title="% Difference (Gas - Excel)"),
    color=alt.Color("Policy number:N", title="Policy"),
    tooltip=["Policy number", "t", "pct_diff"],
).properties(
    title=f"{variable}: Difference Trajectory Over Time",
    width=700, height=400,
)
chart.save(f"reconciliation/plots/timeseries_{variable}.png")
```

### Detect Drift Rate

```python
from scipy import stats

# For each policy, fit a linear trend to the difference trajectory
drift_results = []
for pid in sample_policies:
    pdf = traj_df.filter(pl.col("Policy number") == pid)
    t = pdf["t"].to_numpy().astype(float)
    d = pdf["pct_diff"].to_numpy().astype(float)

    mask = np.isfinite(d)
    if mask.sum() < 10:
        continue

    reg = stats.linregress(t[mask], d[mask])

    drift_results.append({
        "policy": pid,
        "drift_per_period": reg.slope,
        "drift_per_year": reg.slope * 12,  # if monthly periods
        "intercept": reg.intercept,
        "r_squared": reg.rvalue ** 2,
    })

drift_df = pl.DataFrame(drift_results)
print("Drift Analysis:")
print(drift_df)

mean_drift = float(drift_df["drift_per_period"].mean())
if abs(mean_drift) > 0.001:
    print(f"\n** SYSTEMATIC DRIFT: {mean_drift:.6f}% per period ({mean_drift*12:.4f}% per year) **")
else:
    print("\nNo systematic drift detected")
```

### Detect Step Changes

```python
# Find periods where the difference trajectory has sudden jumps
for pid in [1]:  # inspect one policy in detail
    pdf = traj_df.filter(pl.col("Policy number") == pid)
    d = pdf["pct_diff"].to_numpy().astype(float)
    t = pdf["t"].to_numpy()

    # First difference of the trajectory
    jumps = np.abs(np.diff(d))
    mean_jump = np.mean(jumps)
    std_jump = np.std(jumps)

    # Flag periods where jump > mean + 3*std
    threshold = mean_jump + 3 * std_jump
    step_periods = t[1:][jumps > threshold]

    if len(step_periods) > 0:
        print(f"\nPolicy {pid} - Step changes detected at periods: {step_periods.tolist()}")
        for sp in step_periods:
            idx = int(np.where(t == sp)[0][0])
            print(f"  Period {sp}: diff jumped from {d[idx-1]:.4f}% to {d[idx]:.4f}%")
    else:
        print(f"\nPolicy {pid} - No step changes detected")
```

### Mean Trajectory Across All Policies

```python
# Average the difference trajectory across all policies to see the aggregate pattern
mean_traj = gas.join(
    excel.select(["Policy number", "t", pl.col(variable).alias(f"{variable}_excel")]),
    on=["Policy number", "t"],
).with_columns(
    ((pl.col(variable) - pl.col(f"{variable}_excel"))
     / pl.col(f"{variable}_excel").abs().clip(lower_bound=1e-10) * 100)
    .alias("pct_diff")
).group_by("t").agg(
    pl.col("pct_diff").mean().alias("mean_pct_diff"),
    pl.col("pct_diff").std().alias("std_pct_diff"),
    pl.col("pct_diff").median().alias("median_pct_diff"),
).sort("t")

# Plot with confidence band
band = alt.Chart(mean_traj).mark_area(opacity=0.2).encode(
    x="t:Q",
    y=alt.Y("y_lo:Q"),
    y2="y_hi:Q",
).transform_calculate(
    y_lo="datum.mean_pct_diff - datum.std_pct_diff",
    y_hi="datum.mean_pct_diff + datum.std_pct_diff",
)

line = alt.Chart(mean_traj).mark_line(color="red").encode(
    x=alt.X("t:Q", title="Period"),
    y=alt.Y("mean_pct_diff:Q", title="Mean % Diff"),
)

zero = alt.Chart(pl.DataFrame({"y": [0.0]})).mark_rule(
    color="gray", strokeDash=[4, 4]
).encode(y="y:Q")

chart = (band + line + zero).properties(
    title=f"{variable}: Mean Difference Trajectory (all policies)",
    width=700, height=300,
)
chart.save(f"reconciliation/plots/timeseries_mean_{variable}.png")
```

## How to Interpret

| Pattern | Interpretation | Likely Root Cause |
|---|---|---|
| **Linear drift upward** | Compounding error — model over-predicts more each period | Rate applied per-period that should be annual, or vice versa. Small interest/mortality rate offset that compounds |
| **Linear drift downward** | Model under-predicts more each period | Missing a small per-period component that accumulates |
| **Step change at period N** | Something triggers at that specific time | Rate schedule change, policy anniversary, assumption update, leap year, year boundary |
| **Oscillating (12-month cycle)** | Monthly vs annual timing mismatch | Check annualization, monthly rate derivation, YEARFRAC |
| **Flat then sudden divergence** | A boundary condition triggers | Max age, maturity, end-of-guarantee period, CSO boundary |
| **Convergence over time** | Error self-corrects | Initialization offset that washes out (may be acceptable) |
| **All policies drift the same way** | Global systematic error | Discount rate, survival probability, or shared timing convention |
| **Some policies drift, others don't** | Cohort-specific time-dependent error | Cross-reference with Cohort Analysis by the drifting policies |

### Common Drift Rates and Their Meaning

| Drift Rate (per period) | Possible Cause |
|---|---|
| ~0.0021% monthly (~0.025% annual) | Discount rate off by 1bp |
| ~0.083% monthly (~1% annual) | Annual rate not converted to monthly correctly |
| Exactly 0% for 12 periods then step | Policy year boundary handling |
| Step at month 49 (year 5) | Surrender charge period ending differently |

## What to Do Next

1. Record the time-series analysis in the build log: drift rate, step-change periods, pattern type
2. If linear drift: compute the implied rate difference. A drift of X% per month = X*12% per year. Search for assumption rates that differ by this amount
3. If step change at period N: identify what changes at that period — rate schedule, policy year boundary, age milestone. Compare the inputs at periods N-1 and N between models
4. If oscillating: check monthly vs annual rate conversion. Compare the monthly rate derivation formula
5. After fixing, re-plot the trajectory to confirm it's now flat at 0%
