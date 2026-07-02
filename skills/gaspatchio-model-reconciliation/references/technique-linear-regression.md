# Technique: Linear Regression for Bias Detection (Tier 3)

## When to Use

Run this when the Tier 2 scatter plot shows:
- A clear linear relationship between gaspatchio and Excel values
- But the line does not pass through the origin with slope 1.0
- Suggesting a systematic proportional (slope) or additive (intercept) bias

## How to Run

```python
import polars as pl
import numpy as np
from scipy import stats

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

variable = "pv_claims_death"
period = 12

# Extract paired values
gas_slice = gas.filter(pl.col("t") == period)
excel_slice = excel.filter(pl.col("t") == period)

x = excel_slice[variable].to_numpy().astype(float)
y = gas_slice[variable].to_numpy().astype(float)

# Remove NaN/inf pairs
mask = np.isfinite(x) & np.isfinite(y)
x, y = x[mask], y[mask]

# Fit regression: gaspatchio = slope * excel + intercept
reg = stats.linregress(x, y)
n = len(x)
t_crit = stats.t.ppf(0.975, df=n - 2)

# Test H0: slope = 1 (no multiplicative bias)
t_slope = (reg.slope - 1.0) / reg.stderr
p_slope_eq_1 = 2 * stats.t.sf(abs(t_slope), df=n - 2)

# Test H0: intercept = 0 (no additive bias)
t_int = reg.intercept / reg.intercept_stderr
p_int_eq_0 = 2 * stats.t.sf(abs(t_int), df=n - 2)

print(f"Variable: {variable} at period {period}")
print(f"  Slope:     {reg.slope:.6f}  (95% CI: {reg.slope - t_crit * reg.stderr:.6f} to {reg.slope + t_crit * reg.stderr:.6f})")
print(f"  Intercept: {reg.intercept:.6f}")
print(f"  R-squared: {reg.rvalue**2:.6f}")
print(f"  p(slope=1):     {p_slope_eq_1:.6f}")
print(f"  p(intercept=0): {p_int_eq_0:.6f}")

if p_slope_eq_1 < 0.01:
    print(f"  ** PROPORTIONAL BIAS: slope is {reg.slope:.6f}, not 1.0 **")
if p_int_eq_0 < 0.01:
    print(f"  ** ADDITIVE BIAS: intercept is {reg.intercept:.6f}, not 0.0 **")
```

### Run Across All Variables

```python
def regression_diagnostics(gas_df, excel_df, variables, period):
    """Run regression diagnostics for all variables at a given period."""
    results = []
    gas_slice = gas_df.filter(pl.col("t") == period)
    excel_slice = excel_df.filter(pl.col("t") == period)

    for var in variables:
        if var not in gas_slice.columns or var not in excel_slice.columns:
            continue

        x = excel_slice[var].to_numpy().astype(float)
        y = gas_slice[var].to_numpy().astype(float)
        mask = np.isfinite(x) & np.isfinite(y) & (x != 0)
        if mask.sum() < 3:
            continue
        x, y = x[mask], y[mask]

        reg = stats.linregress(x, y)
        t_slope = (reg.slope - 1.0) / reg.stderr if reg.stderr > 0 else 0
        p_slope_eq_1 = 2 * stats.t.sf(abs(t_slope), df=len(x) - 2)

        results.append({
            "variable": var,
            "slope": reg.slope,
            "intercept": reg.intercept,
            "r_squared": reg.rvalue ** 2,
            "p_slope_eq_1": p_slope_eq_1,
            "bias_type": (
                "PROPORTIONAL" if abs(reg.slope - 1.0) > 0.001 and p_slope_eq_1 < 0.01
                else "ADDITIVE" if abs(reg.intercept) > 0.01 and reg.intercept_stderr > 0
                else "NONE"
            ),
        })

    return pl.DataFrame(results).sort("bias_type", descending=True)
```

### Visualize with Regression Line

```python
import altair as alt

def plot_regression(joined_df, variable, output_path):
    """Scatter with regression line and y=x reference."""
    excel_col = f"{variable}_excel"

    points = alt.Chart(joined_df).mark_point(opacity=0.3, size=10).encode(
        x=alt.X(f"{excel_col}:Q", title="Excel"),
        y=alt.Y(f"{variable}:Q", title="Gaspatchio"),
    )

    regression_line = points.transform_regression(
        excel_col, variable
    ).mark_line(color="red", strokeWidth=2)

    x_min = float(joined_df[excel_col].min())
    x_max = float(joined_df[excel_col].max())
    identity = alt.Chart(pl.DataFrame({
        "x": [x_min, x_max], "y": [x_min, x_max],
    })).mark_line(color="gray", strokeDash=[4, 4]).encode(x="x:Q", y="y:Q")

    chart = (points + regression_line + identity).properties(
        title=f"{variable}: Regression (red) vs Perfect Match (gray dashed)",
        width=500, height=400,
    )
    chart.save(output_path)
```

## How to Interpret

| Result | Interpretation | Likely Root Cause |
|---|---|---|
| slope ~1.0, intercept ~0.0, R^2 ~1.0 | No bias detected | Error is elsewhere (timing, edge cases) |
| slope > 1.0, intercept ~0.0 | Model over-predicts by a fixed proportion | Rate too high, or multiplied by wrong factor |
| slope < 1.0, intercept ~0.0 | Model under-predicts proportionally | Rate too low, missing a component, or wrong divisor |
| slope ~1.0, intercept > 0 | Constant positive offset | Extra fixed expense, fee, or initialization value |
| slope ~1.0, intercept < 0 | Constant negative offset | Missing fixed component |
| slope != 1.0, intercept != 0.0 | Both proportional and additive error | Multiple bugs, or formula with both rate and fixed parts |
| R^2 << 1.0 | Not a linear relationship | This technique doesn't apply — try PCA or Cohort Analysis |

### Common Slope Values and Their Meaning

| Slope | Possible Cause |
|---|---|
| 1.0833 (~= 13/12) | Annual rate used where monthly expected |
| 0.9231 (~= 12/13) | Monthly rate used where annual expected |
| 2.0 | Double-counting a component |
| 0.5 | Missing half the calculation (e.g., only one gender) |
| 1.0025 | Discount rate applied once extra (compounding) |
| 0.9975 | Discount rate missing one period |

## What to Do Next

1. Record the regression results in the build log (slope, intercept, R^2, p-values)
2. If slope != 1.0: search for rate tables, percentages, or scaling factors. Check annualization (monthly vs annual), and look for unit mismatches
3. If intercept != 0.0: search for fixed expenses, flat fees, or per-policy charges. Check initialization values at t=0
4. If R^2 is low: this technique doesn't explain the error — try Cohort Analysis or PCA instead
5. After identifying the bias source, fix it and re-run the regression to confirm slope returns to 1.0 and intercept to 0.0
