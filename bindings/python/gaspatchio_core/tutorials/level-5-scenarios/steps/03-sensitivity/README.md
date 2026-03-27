# Step 03 -- Sensitivity Analysis

## What this step teaches

- Using `sensitivity_analysis()` to generate 1D parameter sweeps automatically
- Building 2D cross-product grids with `parse_scenario_config()`
- Interpreting sensitivity curves (linearity vs convexity)
- Interpreting heatmaps (interaction effects between parameters)

## Key APIs

### `sensitivity_analysis()` -- 1D sweeps

Generates a dict of shock specifications for a single parameter:

```python
from gaspatchio_core.scenarios import sensitivity_analysis

mort_scenarios = sensitivity_analysis(
    table="mortality_select",
    shock_type="multiplicative",
    values=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
    include_base=True,
)
# Returns: {"BASE": [], "mortality_select_0.8": [...], ...}
```

Each scenario's shocks are applied to the base assumptions via `Table.with_shock()`, then the model is re-run.

### `parse_scenario_config()` -- 2D sweeps

For multi-parameter sweeps, build the cross-product manually and parse each combination:

```python
from gaspatchio_core.scenarios import parse_scenario_config

for m in [0.8, 1.0, 1.2]:
    for l in [0.8, 1.0, 1.2]:
        sid = f"mort_{m}_lapse_{l}"
        shocks = []
        if m != 1.0:
            shocks.append({"table": "mortality_select", "multiply": m})
        if l != 1.0:
            shocks.append({"table": "lapse_rates", "multiply": l})
        parsed = parse_scenario_config([{"id": sid, "shocks": shocks}])
```

## Interpreting results

### Sensitivity curves

- A **linear** curve means the metric scales proportionally with the parameter. Small changes in assumptions produce predictable, proportional changes in results.
- A **convex** (or concave) curve signals non-linear risk. The impact of large shocks is disproportionately larger (or smaller) than small ones. This matters for tail-risk capital calculations.
- The **base marker** (dashed vertical line at 1.0) helps identify asymmetry: if the curve is steeper on one side of the base, adverse shocks are more impactful than favourable ones.

### Heatmaps

- **Diagonal gradients** (top-left to bottom-right) indicate that both parameters push the metric in the same direction.
- **Interaction effects** appear when the combined shock differs from the sum of individual shocks. If `effect(A+B) != effect(A) + effect(B)`, the parameters interact.
- A strong interaction means you cannot analyse parameters in isolation -- combined stress tests are essential.

## Running

```bash
uv run python tutorial/level-5-scenarios/steps/03-sensitivity/run_scenarios.py
```

### Output

```
report/
  sensitivity_mortality.png   # 1D sensitivity curve
  heatmap_interaction.png     # 2D interaction heatmap
  report.md                   # Full report with tables and findings
```
