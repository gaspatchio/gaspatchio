# Technique: Waterfall Decomposition (Tier 3)

## When to Use

Run this when:
- An aggregate metric (BEL, total reserve, PV profit) doesn't match, but individual variables are unclear
- You need to attribute the total difference to specific components
- You want to show stakeholders exactly where the mismatch comes from

Waterfall answers: "Of the total X% BEL difference, how much comes from death benefits, how much from surrenders, how much from expenses, and how much from premiums?"

## How to Run

### Single-Policy Waterfall

```python
import polars as pl
import numpy as np

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

policy_id = 1

# Sum PV components across all periods for this policy
def sum_pv_components(df, policy_id):
    policy_df = df.filter(pl.col("Policy number") == policy_id)
    return {
        "PV Death Benefit": float(policy_df["pv_claims_death"].sum()),
        "PV Surrender": float(policy_df["pv_surrender_benefit"].sum()),
        "PV Expenses": float(policy_df["pv_total_expense"].sum()),
        "PV Premium": float(policy_df["pv_premium_subtotal"].sum()),
    }

gas_pv = sum_pv_components(gas, policy_id)
excel_pv = sum_pv_components(excel, policy_id)

# Component-level differences
print(f"Policy {policy_id} - PV Component Differences (Gas - Excel):")
total_diff = 0
for component in gas_pv:
    diff = gas_pv[component] - excel_pv[component]
    total_diff += diff
    pct = diff / abs(excel_pv[component]) * 100 if excel_pv[component] != 0 else float("inf")
    print(f"  {component:20s}: diff={diff:12.2f}  ({pct:+.4f}%)")
print(f"  {'Total BEL diff':20s}: {total_diff:12.2f}")
```

### Portfolio-Level Waterfall

```python
# Aggregate across all policies (or a subset like in-force only)
def portfolio_pv(df):
    return {
        "PV Death Benefit": float(df["pv_claims_death"].sum()),
        "PV Surrender": float(df["pv_surrender_benefit"].sum()),
        "PV Expenses": float(df["pv_total_expense"].sum()),
        "PV Premium": float(df["pv_premium_subtotal"].sum()),
    }

gas_total = portfolio_pv(gas)
excel_total = portfolio_pv(excel)

print("Portfolio PV Component Differences:")
for component in gas_total:
    diff = gas_total[component] - excel_total[component]
    pct = diff / abs(excel_total[component]) * 100 if excel_total[component] != 0 else 0
    print(f"  {component:20s}: gas={gas_total[component]:14.2f}  excel={excel_total[component]:14.2f}  diff={diff:12.2f} ({pct:+.3f}%)")
```

### Visualize: Waterfall Chart

```python
import altair as alt

def plot_waterfall(gas_components, excel_components, title, output_path):
    """Waterfall chart showing which components drive the total difference."""
    names = []
    diffs = []
    for component in gas_components:
        names.append(component)
        diffs.append(gas_components[component] - excel_components[component])

    names.append("Total BEL Diff")
    diffs.append(sum(diffs))

    # Build waterfall coordinates
    starts, ends, types = [], [], []
    running = 0.0
    for i, (name, diff) in enumerate(zip(names, diffs)):
        if i == len(names) - 1:  # total bar
            starts.append(0.0)
            ends.append(diff)
            types.append("total")
        else:
            starts.append(running)
            running += diff
            ends.append(running)
            types.append("increase" if diff > 0 else "decrease")

    df = pl.DataFrame({
        "component": names,
        "start": starts,
        "end": ends,
        "diff": diffs,
        "type": types,
    })

    chart = alt.Chart(df).mark_bar(size=45).encode(
        x=alt.X("component:N", sort=None, title=""),
        y=alt.Y("start:Q", title="Difference (Gas - Excel)"),
        y2="end:Q",
        color=alt.Color("type:N", scale=alt.Scale(
            domain=["increase", "decrease", "total"],
            range=["#e45756", "#54a24b", "#4c78a8"],
        )),
        tooltip=["component:N", alt.Tooltip("diff:Q", format=",.2f")],
    ).properties(title=title, width=500, height=400)
    chart.save(output_path)

plot_waterfall(gas_total, excel_total, "BEL Difference Attribution", "reconciliation/plots/waterfall_bel.png")
```

### Scenario-Level Waterfall (for BSCR)

```python
# Compare base vs stressed scenario to attribute stress impact
def scenario_waterfall(gas_base, gas_stress, excel_base, excel_stress, scenario_name):
    """Waterfall: how does the stress impact differ between models?"""
    components = list(gas_base.keys())

    print(f"\n{scenario_name} - Stress Impact Attribution:")
    print(f"{'Component':25s} {'Gas Impact':>14s} {'Excel Impact':>14s} {'Diff':>12s}")

    for comp in components:
        gas_impact = gas_stress[comp] - gas_base[comp]
        excel_impact = excel_stress[comp] - excel_base[comp]
        diff = gas_impact - excel_impact
        print(f"  {comp:23s} {gas_impact:14.2f} {excel_impact:14.2f} {diff:12.2f}")
```

## How to Interpret

| Pattern | Interpretation | Next Step |
|---|---|---|
| One component dominates the total diff | That component's calculation is the main bug | Focus Tier 1/2/3 diagnostics on that variable |
| All components contribute proportionally | Likely a shared upstream cause (discount rate, timing, survival probability) | Check discount rates, `pols_if`, or other shared inputs |
| Components partially offset each other | Multiple bugs with canceling effects | Fix each component independently (do NOT rely on net cancellation) |
| Stress impact differs but base matches | The stress application logic differs | Check how the scenario modifies rates/assumptions |

### Red Flag: Offsetting Errors

If PV Death Benefit is +$500 too high and PV Premium is +$500 too high, the net BEL might look correct, but you have two bugs. **Always check components, not just totals.**

## What to Do Next

1. Record the waterfall results in the build log with exact numbers per component
2. Focus diagnostic effort on the component with the largest absolute difference
3. For that component, run the full Tier 1 → 2 → 3 diagnostic sequence
4. After fixing, re-run the waterfall to confirm the component difference resolved and no other component shifted (regression check)
5. For BSCR scenarios: compare the stress impact (delta from base) rather than absolute values — this isolates stress-specific bugs from base-case bugs
