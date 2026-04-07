---
name: gaspatchio-model-scenarios
description: Use when running scenario analysis, applying parameter shocks, performing sensitivity sweeps, or producing scenario comparison reports on a gaspatchio model.
allowed-tools: Bash(uv:*,gspio:*) Read Grep Glob
---

# Gaspatchio Model Scenarios

I'm using the gaspatchio model scenarios skill.

## When to use this skill

This skill can be used standalone on any gaspatchio model. It does NOT require model-building, model-discovery, or any other skill to have been run first. Use it whenever the user asks about:

- "What-if" analysis
- Sensitivity testing or sensitivity sweeps
- Stress testing or scenario analysis
- Comparing model results under different assumptions
- Parameter shocks (mortality, lapse, interest rates, expenses)
- Regulatory or economic scenario comparison

## Hard gate

Do NOT claim scenario analysis is complete until a `report/report.md` exists containing charts (embedded PNGs) and an audit trail from `describe_scenarios()`. Every scenario run produces a report.

---

## CRITICAL RULE: Two-Script Pattern

Scenario analysis uses two scripts with strict separation of concerns:

| Script | Purpose | Modify for scenarios? |
|---|---|---|
| `model.py` | The projection model (`def main(af, assumptions_override=None)`) | **NEVER** |
| `run_scenarios.py` | Scenario orchestration, shock application, charts, reports | **YES** |

**`model.py` stays UNCHANGED.** All scenario logic goes in `run_scenarios.py`.

The model accepts `assumptions_override` for shocked tables. This separation means `gspio run-model` still works for single-scenario debugging:

```bash
# Model works standalone -- no scenario machinery needed
uv run gspio run-single-policy model.py data.parquet 1

# Scenario analysis is layered on top
uv run python run_scenarios.py
```

---

## Scenario Types (Progressive)

Teach and apply these in order. Each level builds on the previous.

### Level 1 -- Interest Rate Scenarios (simplest)

The model's discount rate lookup uses `scenario_id` automatically if the rate table has rows for each scenario.

```python
from gaspatchio_core.scenarios import with_scenarios

af = with_scenarios(af, ["BASE", "UP", "DOWN"])
result = model.main(af).collect()
```

The assumption table `risk_free_rates.parquet` must have BASE/UP/DOWN rows. `with_scenarios()` cross-joins the ActuarialFrame with scenario IDs so every model point is projected under every scenario in a single pass.

**Chart**: Grouped bar chart comparing PV metrics across scenarios.

### Level 2 -- Parameter Shocks (declarative JSON)

**Note:** Stresses and shocks belong in this scenario system (`scenarios/shocks` composables), NOT as custom accessors. If someone asks to "add a lapse stress accessor," redirect them here. Use `gaspatchio-extending` only for new reusable calculations, not for stress/scenario modifications.

Define shocks in a `scenarios.json` config file:

```json
[
  {"id": "BASE"},
  {"id": "MORT_UP_20", "shocks": [{"table": "mortality_select", "multiply": 1.2}]},
  {"id": "RATES_DOWN_50BP", "shocks": [{"table": "risk_free_rates", "add": -0.005}]},
  {"id": "LAPSE_DOWN_20", "shocks": [{"table": "lapse_rates", "multiply": 0.8}]}
]
```

Load and apply with `parse_scenario_config()` and `Table.with_shock()`:

```python
import json
from pathlib import Path

from gaspatchio_core.scenarios import parse_scenario_config, describe_scenarios

config = json.loads(Path("scenarios.json").read_text())
scenario_shocks = parse_scenario_config(config)

results = []
for scenario_id, shocks in scenario_shocks.items():
    assumptions = model.load_assumptions()  # fresh copy every time
    for shock in shocks:
        table_name = getattr(shock, "table", None)
        if table_name and table_name in assumptions:
            assumptions[table_name] = assumptions[table_name].with_shock(shock)
    af = ActuarialFrame(mp)
    result = model.main(af, assumptions_override=assumptions).collect()
    result = result.with_columns(pl.lit(scenario_id).alias("scenario_id"))
    results.append(result)
```

Fresh assumptions every iteration -- shocks must never stack.

**Chart**: Tornado chart ranking sensitivities by absolute impact on the headline metric.

### Level 3 -- Conditional Shocks

Extend the JSON format with `where`, `when`, and `pipeline` keys:

```json
{"table": "mortality_select", "multiply": 1.5, "where": {"attained_age": {"gte": 65}}}
{"table": "risk_free_rates", "add": -0.01, "when": {"year": {"gte": 3}}}
{"table": "mortality_select", "pipeline": [{"multiply": 1.3}, {"clip": {"min": 0.005}}]}
```

| Key | Type | Meaning |
|---|---|---|
| `where` | FilteredShock | Dimension filter -- shock only applies to rows matching the condition |
| `when` | TimeConditionalShock | Time condition -- shock applies from a specific projection year onward |
| `pipeline` | PipelineShock | Chain operations -- apply multiple transformations in sequence |

These use the same `parse_scenario_config()` and `Table.with_shock()` API. The shock type is inferred from the JSON structure.

**Chart**: Cashflow line chart over projection time showing how conditional shocks diverge from base at specific points.

### Level 4 -- Sensitivity Sweeps

Systematically vary a single parameter across a range:

```python
from gaspatchio_core.scenarios import sensitivity_analysis

scenarios = sensitivity_analysis(
    table="mortality_select",
    shock_type="multiplicative",
    values=[0.8, 0.9, 1.0, 1.1, 1.2],
    include_base=True,
)
```

This generates one scenario per value with auto-generated IDs (e.g., `MORT_x0.8`, `MORT_x0.9`, ...).

For 2D interaction sweeps (e.g., mortality x lapse), build the cross-product manually:

```python
import itertools

mort_values = [0.8, 1.0, 1.2]
lapse_values = [0.8, 1.0, 1.2]

config = []
for m, l in itertools.product(mort_values, lapse_values):
    config.append({
        "id": f"MORT_{m}_LAPSE_{l}",
        "shocks": [
            {"table": "mortality_select", "multiply": m},
            {"table": "lapse_rates", "multiply": l},
        ],
    })

scenario_shocks = parse_scenario_config(config)
```

**Charts**: Sensitivity curve (1D) and heatmap (2D) showing how the metric responds across the parameter space.

### Level 5 -- Regulatory Comparison

Named scenarios as economic narratives. These combine multiple shocks into coherent stress scenarios:

```json
[
  {"id": "BASE", "description": "Central estimate"},
  {
    "id": "ADVERSE_MORTALITY",
    "description": "1-in-200 mortality stress",
    "shocks": [
      {"table": "mortality_select", "multiply": 1.4},
      {"table": "mortality_select", "multiply": 1.6, "where": {"attained_age": {"gte": 70}}}
    ]
  },
  {
    "id": "ECONOMIC_DOWNTURN",
    "description": "Simultaneous rate fall and lapse spike",
    "shocks": [
      {"table": "risk_free_rates", "add": -0.015},
      {"table": "lapse_rates", "multiply": 1.5, "when": {"year": {"gte": 2}}}
    ]
  }
]
```

Use `describe_scenarios()` to generate an audit trail for governance:

```python
audit_trail = describe_scenarios(scenario_shocks, output_format="markdown")
```

This produces a human-readable summary of every scenario and its shocks, suitable for inclusion in regulatory reports.

**Charts**: Grouped bar chart comparing scenario outcomes + full regulatory-style report with audit trail.

---

## Report Requirements (Non-Negotiable)

Every scenario run must produce `report/report.md` containing ALL of these sections:

### 1. Model Metadata

| Field | Example |
|---|---|
| Model points | 8 |
| Scenarios | 6 |
| Runtime | 4.2s |

### 2. Scenario Configuration

The JSON config inline (or a summary table for large configs).

### 3. Results Summary Table

| scenario_id | pv_net_cf | vs_base_pct |
|---|---|---|
| BASE | 1,234,567 | -- |
| MORT_UP_20 | 1,198,432 | -2.9% |
| RATES_DOWN | 1,301,234 | +5.4% |

Must include % change from base for every scenario.

### 4. Embedded Chart PNGs

Charts saved as PNGs in `report/` and embedded with `![](chart_name.png)`.

### 5. Key Findings

Auto-generated observations. At minimum:
- Which scenario has the largest impact (and direction)
- Which scenario has the smallest impact
- Any notable asymmetries (e.g., rate up vs rate down convexity)

### 6. Audit Trail

Output from `describe_scenarios()` documenting every shock applied.

Use the `charts.write_report()` helper from the tutorial's `charts.py` module where available.

---

## Chart Guidance

Match the chart to the analysis type. Using the wrong chart obscures the story.

| Analysis Type | Chart | What It Shows |
|---|---|---|
| Interest rate comparison | Grouped bar chart | Side-by-side scenario totals |
| Parameter shocks | Tornado chart | Ranked sensitivities by absolute impact |
| Conditional shocks | Cashflow line chart over time | Where and when scenarios diverge from base |
| Sensitivity sweep (1D) | Sensitivity curve | Metric response across parameter range |
| Sensitivity sweep (2D) | Heatmap | Interaction effects across two parameters |
| Regulatory comparison | Grouped bar + full report | Named scenarios with audit trail |

Use Altair for all charts. The `charts.py` module in the tutorial (`tutorial/level-5-scenarios/charts.py`) provides reusable chart functions: `tornado_chart()`, `sensitivity_curve()`, `heatmap_chart()`, `cashflow_lines()`, `grouped_bar()`, `write_report()`.

---

## Tutorial Reference

Level 5 of the tutorial (`tutorial/level-5-scenarios/`) is the worked example for this skill:

| Tutorial Step | Skill Level | What It Demonstrates |
|---|---|---|
| Base | Level 1 | Interest rate scenarios with `with_scenarios()` |
| Step 01 | Level 2 | Parameter shocks with tornado chart |
| Step 02 | Level 3 | Conditional shocks with cashflow lines |
| Step 03 | Level 4 | Sensitivity sweeps with heatmap |
| Step 04 | Level 5 | Regulatory comparison with full report |

Every step has a working `run_scenarios.py` and generates a `report/` directory. Start from the step closest to what the user needs and adapt.

---

## gaspatchio Scenario API Quick Reference

| Function | Import | What It Does |
|---|---|---|
| `with_scenarios(af, ids)` | `gaspatchio_core.scenarios` | Cross-join ActuarialFrame with scenario IDs |
| `parse_scenario_config(config)` | `gaspatchio_core.scenarios` | Parse JSON shock config into `dict[str, list[Shock]]` |
| `Table.with_shock(shock)` | `gaspatchio_core.assumptions` | Apply a shock to an assumption table, returning a new Table |
| `sensitivity_analysis(table, type, values)` | `gaspatchio_core.scenarios` | Generate 1D parameter sweep scenarios |
| `describe_scenarios(scenarios)` | `gaspatchio_core.scenarios` | Generate audit trail (markdown/text/dict) |

---

## Anti-Rationalizations

These are the most common ways agents try to shortcut scenario analysis. Each is wrong.

| Temptation | Correct Response |
|---|---|
| "I'll just modify the model for each scenario" | `model.py` stays unchanged. Use `assumptions_override`. The two-script pattern exists for a reason: the model must remain debuggable with `gspio run-model`. |
| "I don't need a report" | Reports with audit trails are required for governance. `describe_scenarios()` generates them automatically. A scenario analysis without a report is incomplete. |
| "The tornado chart is enough" | Different analysis types need different charts. A tornado chart is meaningless for time-conditional shocks. Match the visualization to what you're showing. |
| "I'll apply shocks in-place and reload" | Fresh assumptions every scenario. Shocks must never stack. Reload `model.load_assumptions()` at the start of every iteration. |
| "This is just one quick what-if" | Even a single what-if produces a report. The overhead is trivial and the audit trail is always valuable. |

---

## Completion Gate

Scenario analysis is complete when ALL of these are true:

- [ ] `model.py` was NOT modified -- all scenario logic is in `run_scenarios.py`
- [ ] `run_scenarios.py` executes without errors
- [ ] `report/report.md` exists and contains:
  - [ ] Model metadata (points, scenarios, runtime)
  - [ ] Scenario configuration (JSON or summary table)
  - [ ] Results summary table with % change from base
  - [ ] At least one embedded chart PNG appropriate to the analysis type
  - [ ] Key findings (auto-generated)
  - [ ] Audit trail from `describe_scenarios()`
- [ ] Charts match the analysis type (see Chart Guidance table)

Do not claim the scenario analysis is done until every item is checked.
