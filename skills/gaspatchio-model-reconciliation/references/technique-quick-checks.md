# Technique: Quick Checks (Tier 1 — Direct Inspection)

## When to Use

**Always.** This is the first thing you do for every mismatch, every time. Most mismatches are caught here — a wrong column name, an off-by-one in age lookup, a timing convention difference.

## Steps

### 1. Sign Check

Is the value positive when it should be negative, or vice versa?

Common causes of sign errors:
- Premium income coded as positive outflow instead of negative
- Surrender value deducted instead of added
- PV formula negating when it shouldn't (or not negating when it should)
- BEL components with wrong sign convention

```python
# Quick sign check across all policies at period 0
import polars as pl

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

variable = "pv_claims_death"
gas_sign = gas[variable].mean() > 0
excel_sign = excel[variable].mean() > 0
if gas_sign != excel_sign:
    print(f"SIGN MISMATCH: gaspatchio mean={gas[variable].mean():.4f}, excel mean={excel[variable].mean():.4f}")
```

### 2. Magnitude Check

Is the value in the right order of magnitude?

```python
gas_mean = gas[variable].mean()
excel_mean = excel[variable].mean()
ratio = gas_mean / excel_mean if excel_mean != 0 else float("inf")
print(f"Magnitude ratio: {ratio:.4f} (expect ~1.0)")

if ratio > 10 or ratio < 0.1:
    print("ORDER OF MAGNITUDE ERROR — check units, scaling, or annualization")
elif ratio > 1.5 or ratio < 0.67:
    print("LARGE BIAS — likely a rate or factor applied incorrectly")
elif abs(ratio - 1.0) > 0.01:
    print("SMALL BIAS — could be timing, interpolation, or rounding")
```

### 3. Single-Cell Trace

Pick one policy, one period. Compare every input to the formula.

```python
policy_id = 1  # pick a representative policy
period = 12    # pick a mid-projection period

gas_row = gas.filter(
    (pl.col("Policy number") == policy_id) & (pl.col("t") == period)
)
excel_row = excel.filter(
    (pl.col("Policy number") == policy_id) & (pl.col("t") == period)
)

# Compare all shared columns
shared_cols = [c for c in gas_row.columns if c in excel_row.columns]
for col in shared_cols:
    g_val = gas_row[col].item()
    e_val = excel_row[col].item()
    if isinstance(g_val, (int, float)) and isinstance(e_val, (int, float)):
        if e_val != 0:
            pct_diff = abs(g_val - e_val) / abs(e_val) * 100
        else:
            pct_diff = abs(g_val) * 100
        if pct_diff > 0.01:
            print(f"  {col}: gas={g_val:.6f} excel={e_val:.6f} diff={pct_diff:.4f}%")
```

### 4. Input Parity Check

Before blaming the formula, confirm the inputs match:

```python
# Check assumption inputs at the same point
input_cols = ["mortality_rate", "lapse_rate", "discount_rate", "expense_rate"]
for col in input_cols:
    if col in gas_row.columns and col in excel_row.columns:
        g = gas_row[col].item()
        e = excel_row[col].item()
        if abs(g - e) > 1e-10:
            print(f"  INPUT MISMATCH: {col} gas={g} excel={e}")
```

If any inputs differ, fix those first. Formula debugging with wrong inputs is wasted time.

## What to Do Next

- If root cause found: fix it, record in build log, re-run diff
- If sign or magnitude is off by a clear factor (2x, 12x, 100x): check annualization, unit conversion, or rate scaling
- If single-cell trace shows matching inputs but different output: the formula logic differs — check the calculation step by step
- If everything looks right at this level but aggregate still differs: escalate to Tier 2 (Pattern Detection)
