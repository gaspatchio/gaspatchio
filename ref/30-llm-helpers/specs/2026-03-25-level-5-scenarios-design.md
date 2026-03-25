# Level 5 — Scenarios: Design Spec

## Overview

Level 5 teaches deterministic scenario analysis for actuarial models. The student takes the reconciled L4 model and learns to run it across multiple scenarios, apply parameter shocks, perform sensitivity analysis, and produce professional-grade reports with charts.

Every step produces a markdown report with Altair charts, scenario descriptions, results tables, and audit trails. The report is generated programmatically — not hand-written.

Monte Carlo / stochastic scenarios and performance at scale are deferred to Level 6.

## Audience

Actuaries who have completed L3-L4 and understand the full VA model. They know `ActuarialFrame`, `Table.lookup()`, `when/then/otherwise`, `accumulate()`, and reconciliation. Now they need to learn scenario analysis — a core part of actuarial work (Solvency II ORSA, IFRS 17 sensitivity, profit testing).

## Architecture

### Two-script pattern

Every step has two scripts:

- **`model.py`** — The projection model. `def main(af) -> ActuarialFrame`. Runs one scenario at a time. Compatible with `gspio run-model` and `gspio run-single-policy`. Unchanged across all steps.
- **`run_scenarios.py`** — Orchestration. Loads data, configures scenarios (shocks, sweeps, named configs), calls `model.main()` for each scenario, collects results, generates Altair charts and a markdown report into `report/`.

This separation means:
- The model can always be run standalone for debugging: `uv run gspio run-model model.py model_points.parquet`
- Scenario analysis is layered on top, not baked into the model
- The same model code works for 1 scenario or 100

### Data

Complete self-contained copy of L4's data into `level-5-scenarios/base/`:
- `model_points.parquet` — 8 IF model points (2023Q4IF)
- `assumptions/` — all 14 parquet files from L4

All steps share the base data via a relative path constant (`BASE_DIR = STEP_DIR.parent.parent / "base"`). No symlinks, no data duplication between steps. Steps that add scenario configs have their own `scenarios.json`.

### Dependencies

- **Add**: `altair`, `vl-convert-python` (for static PNG export via `chart.save("chart.png")`)
- **Remove**: `plotly`

## Directory Structure

```
tutorial/level-5-scenarios/
├── README.md                          ← level overview, quick start
├── charts.py                          ← shared Altair chart helpers
├── base/
│   ├── model.py                       ← L4 model, cleaned up
│   ├── run_scenarios.py               ← BASE/UP/DOWN rate scenarios
│   ├── model_points.parquet
│   ├── assumptions/                   ← full copy from L4
│   └── report/                        ← generated output
│       ├── report.md
│       ├── scenario_comparison.png
│       └── waterfall.png
└── steps/
    ├── 01-parameter-shocks/
    │   ├── run_scenarios.py           ← shock orchestration
    │   ├── scenarios.json             ← declarative shock config
    │   ├── README.md
    │   └── report/
    ├── 02-conditional-shocks/
    │   ├── run_scenarios.py
    │   ├── scenarios.json
    │   ├── README.md
    │   └── report/
    ├── 03-sensitivity/
    │   ├── run_scenarios.py
    │   ├── README.md
    │   └── report/
    └── 04-scenario-comparison/
        ├── run_scenarios.py
        ├── scenarios.json
        ├── README.md
        └── report/
```

Note: Steps do NOT have their own `model.py` — they import and run `base/model.py`. The model is unchanged across all steps.

## Scenario API Reference

The gaspatchio scenario API lives in `gaspatchio_core.scenarios`. Key functions and their actual signatures:

### parse_scenario_config

```python
def parse_scenario_config(
    config: list[str | dict[str, Any]],
) -> dict[str, list[Shock | ParameterShock]]:
```

Accepts a **Python list** (not a file path). Each element is a string (simple scenario ID) or a dict with `id` and `shocks` keys. Returns a dict mapping scenario IDs to shock lists.

Usage pattern:
```python
import json
config = json.loads(Path("scenarios.json").read_text())
scenario_shocks = parse_scenario_config(config)
# Returns: {"BASE": [], "MORT_UP": [MultiplicativeShock(factor=1.2, table="mortality_select")]}
```

### JSON shock schema (actual API)

The shock config uses **operation keys directly** — no `"type"` field:

```json
{"table": "mortality_select", "multiply": 1.2}
{"table": "risk_free_rates", "add": 0.005}
{"table": "lapse_rates", "set": 0.05}
{"table": "mortality_select", "multiply": 1.5, "where": {"attained_age": {"gte": 65}}}
{"table": "risk_free_rates", "add": -0.01, "when": {"year": {"gte": 3}}}
{"table": "mortality_select", "pipeline": [{"multiply": 1.3}, {"clip": {"min": 0.005}}]}
{"table": "lapse_rates", "multiply": 1.5, "clip": [null, 1.0]}
{"param": "infl_rate", "add": 0.01}
```

Filter operators (`where`/`when`): `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between`, `in`, `not_in`.

Clip syntax: `{"min": 0.0, "max": 1.0}` or `[0.0, 1.0]` or `[null, 1.0]` (max only).

### Applying shocks to Tables

Shocks are applied via `Table.with_shock(shock)` which returns a new Table:

```python
for scenario_id, shocks in scenario_shocks.items():
    assumptions = model.load_assumptions()  # fresh copy each iteration
    for shock in shocks:
        table_name = shock.table
        if table_name in assumptions:
            assumptions[table_name] = assumptions[table_name].with_shock(shock)
    af = ActuarialFrame(mp)
    result = model.main(af, assumptions_override=assumptions).collect()
```

Note: `load_assumptions()` already returns a dict. `main()` already accepts `assumptions_override`.

### sensitivity_analysis (1D only)

```python
def sensitivity_analysis(
    table: str,
    shock_type: Literal["multiplicative", "additive", "override"],
    values: list[float],
    *,
    column: str | None = None,
    scenario_format: str | None = None,
    include_base: bool = False,
) -> dict[str, list[Shock]]:
```

Returns a dict mapping auto-generated scenario IDs to single-shock lists. **1D only** — for 2D sweeps, build the cross-product manually with `parse_scenario_config`.

### with_scenarios (cross-join)

```python
def with_scenarios(
    af: ActuarialFrame,
    scenario_ids: list[str] | list[int],
    scenario_column: str = "scenario_id",
) -> ActuarialFrame:
```

Cross-joins the ActuarialFrame with scenario IDs, adding a `scenario_id` column. The model's discount rate lookup uses this column to select the correct rate curve.

### describe_scenarios (audit trail)

```python
def describe_scenarios(
    scenarios: dict[str, list[Shock]],
    output_format: Literal["text", "markdown", "dict"] = "markdown",
) -> str | dict[str, list[str]]:
```

Generates human-readable scenario descriptions for audit trails.

## Base Model

### model.py

A cleaned-up copy of `tutorial/level-4-lifelib/base/model.py`. Changes from L4:

1. Strip the build-order docstring (phases 1-4) — replace with a short description
2. Keep `scenario_returns_override`, `assumptions_override`, and `projection_months` parameters on `main()`
3. Keep the stochastic detection code (checks for `scenario_id` column on scenario_returns)
4. Keep the scenario-aware discount rate lookup (string scenario_id → use for rate lookup)
5. Paths point to local `assumptions/` directory
6. `load_assumptions()` returns a dict keyed by table name — same as L4
7. ~700 lines (vs L4's 860 — less commentary)

### run_scenarios.py

The simplest possible multi-scenario run using `with_scenarios()`:

```python
from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios

# Load model points
mp = pl.read_parquet(MODEL_POINTS_PATH)

# Cross-join with scenario IDs — creates 3× the rows, each tagged with scenario_id
af = ActuarialFrame(mp)
af = with_scenarios(af, ["BASE", "UP", "DOWN"])

# Run model — scenario_id column flows through to discount rate lookup
# risk_free_rates.parquet already contains BASE/UP/DOWN rate curves
result = model.main(af).collect()

# Group results by scenario_id, compute aggregates
# Generate charts and report
```

This works because `risk_free_rates.parquet` already contains rows for BASE, UP, and DOWN scenarios. The `with_scenarios()` call adds a `scenario_id` column to each model point, and the model's discount rate lookup uses it: `risk_free_rates.lookup(scenario=af.scenario_id, ...)`.

**Chart 1 — Grouped bar**: PV_net_cf by scenario for each product (GMDB vs GMAB). Shows that rate-sensitive products (GMAB) swing more than mortality-dominated products (GMDB).

**Chart 2 — Waterfall**: Walk from BASE PV_net_cf to UP scenario, showing contribution of each PV component. Waterfall data preparation: for each PV component (claims, expenses, inv_income, av_change, premiums, commissions), compute `component_UP - component_BASE`. The sum of component deltas equals the total PV_net_cf delta.

## Step 01 — Parameter Shocks

### What it teaches

Apply assumption-level shocks using gaspatchio's declarative shock API. Instead of manually editing assumption files, describe the shock in JSON and let the framework apply it.

### scenarios.json

```json
[
  {"id": "BASE"},
  {
    "id": "MORT_UP_20",
    "description": "Mortality rates increased by 20%",
    "shocks": [
      {"table": "mortality_select", "multiply": 1.2}
    ]
  },
  {
    "id": "LAPSE_DOWN_20",
    "description": "Lapse rates decreased by 20%",
    "shocks": [
      {"table": "lapse_rates", "multiply": 0.8}
    ]
  },
  {
    "id": "RATES_UP_50BP",
    "description": "Risk-free rates increased by 50 basis points",
    "shocks": [
      {"table": "risk_free_rates", "add": 0.005}
    ]
  },
  {
    "id": "RATES_DOWN_50BP",
    "description": "Risk-free rates decreased by 50 basis points",
    "shocks": [
      {"table": "risk_free_rates", "add": -0.005}
    ]
  },
  {
    "id": "EXPENSES_UP_10",
    "description": "Maintenance expenses increased by 10%",
    "shocks": [
      {"table": "space_params", "multiply": 1.1, "column": "expense_maint"}
    ]
  }
]
```

### run_scenarios.py

```python
import json
from gaspatchio_core.scenarios import parse_scenario_config, describe_scenarios

# Load and parse config
config = json.loads(Path("scenarios.json").read_text())
scenario_shocks = parse_scenario_config(config)

# For each scenario: apply shocks to assumption tables, run model, collect results
results = []
for scenario_id, shocks in scenario_shocks.items():
    assumptions = model.load_assumptions()  # fresh copy
    for shock in shocks:
        if shock.table in assumptions:
            assumptions[shock.table] = assumptions[shock.table].with_shock(shock)
    af = ActuarialFrame(mp)
    result = model.main(af, assumptions_override=assumptions).collect()
    result = result.with_columns(pl.lit(scenario_id).alias("scenario_id"))
    results.append(result)

all_results = pl.concat(results)

# Generate audit trail
audit = describe_scenarios(scenario_shocks, output_format="markdown")

# Generate tornado chart + report
```

**Chart — Tornado chart**: Horizontal bars ranked by absolute impact on total PV_net_cf. Each bar shows the delta from base. The classic actuarial sensitivity visualization.

### Key concepts taught

- `parse_scenario_config()` — load shocks from JSON
- `Table.with_shock()` — apply a shock to an assumption table
- `assumptions_override` on `model.main()` — inject modified tables
- `describe_scenarios()` — generate audit trail
- Tornado chart — the universal actuarial sensitivity visualization

## Step 02 — Conditional Shocks

### What it teaches

Shocks that apply selectively — only to certain rows, only at certain times, or in combination. This is how actuaries model realistic stress scenarios.

### scenarios.json

```json
[
  {"id": "BASE"},
  {
    "id": "PANDEMIC_ELDERLY",
    "description": "Pandemic: mortality +50% for ages 65+, +10% for younger",
    "shocks": [
      {"table": "mortality_select", "multiply": 1.5, "where": {"attained_age": {"gte": 65}}},
      {"table": "mortality_select", "multiply": 1.1, "where": {"attained_age": {"lt": 65}}}
    ]
  },
  {
    "id": "DELAYED_RATE_SHOCK",
    "description": "Rates drop 100bp starting year 3",
    "shocks": [
      {"table": "risk_free_rates", "add": -0.01, "when": {"year": {"gte": 3}}}
    ]
  },
  {
    "id": "MORT_FLOOR",
    "description": "Mortality increased by 30% but floored at 0.5%",
    "shocks": [
      {"table": "mortality_select", "pipeline": [{"multiply": 1.3}, {"clip": {"min": 0.005}}]}
    ]
  }
]
```

### Charts

**Chart 1 — Line chart over time**: Monthly net cashflow for one representative policy under BASE vs PANDEMIC_ELDERLY vs DELAYED_RATE_SHOCK. Shows how conditional shocks create non-parallel shifts — the cashflow curves diverge at specific points.

**Chart 2 — Stacked area**: Claim components (death, lapse, maturity) under the pandemic shock vs base for all 8 points aggregated. Shows how the shock redistributes claim types.

### Key concepts taught

- `FilteredShock` via `"where"` — apply only to rows matching dimension filters
- `TimeConditionalShock` via `"when"` — apply at specific time conditions
- `PipelineShock` via `"pipeline"` — chain multiple operations (multiply then floor)
- How conditional shocks create non-parallel shifts in projections

## Step 03 — Sensitivity Analysis

### What it teaches

Systematic parameter sweeps to understand how a target metric responds to assumption changes.

### run_scenarios.py

```python
from gaspatchio_core.scenarios import sensitivity_analysis

# 1D sweep: mortality scalar from 0.8 to 1.4
mort_scenarios = sensitivity_analysis(
    table="mortality_select",
    shock_type="multiplicative",
    values=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
    include_base=True,
)
# Returns: {"BASE": [], "mortality_select_0.8": [MultiplicativeShock(0.8)], ...}

# Run each scenario through the standard shock loop
# (same pattern as Step 01)

# 2D sweep (mortality × lapse interaction) — built manually
mort_values = [0.8, 1.0, 1.2]
lapse_values = [0.8, 1.0, 1.2]
interaction_scenarios = {}
for m in mort_values:
    for l in lapse_values:
        sid = f"mort_{m}_lapse_{l}"
        shocks = []
        if m != 1.0:
            shocks.append({"table": "mortality_select", "multiply": m})
        if l != 1.0:
            shocks.append({"table": "lapse_rates", "multiply": l})
        interaction_scenarios[sid] = parse_scenario_config(
            [{"id": sid, "shocks": shocks}]
        )[sid]
```

### Charts

**Chart 1 — Sensitivity curve**: Line chart of total PV_net_cf (y-axis) vs mortality scalar (x-axis, 0.8 to 1.4). Shows linearity/convexity of the response. Annotate with base case marker.

**Chart 2 — 2D Heatmap**: Grid of PV_net_cf values with mortality scalar on x-axis and lapse scalar on y-axis. Color intensity shows the metric value. Reveals interaction effects — does high mortality + high lapse compound or offset?

### Key concepts taught

- `sensitivity_analysis()` — systematic 1D parameter sweeps
- Manual cross-product for 2D sweeps
- Sensitivity curves — understanding linearity vs convexity
- Heatmaps — interaction effects between risk factors

## Step 04 — Scenario Comparison & Reporting

### What it teaches

Combine multiple named scenarios into a regulatory-style stress test suite. Each scenario is a meaningful economic story, and the report includes full audit trail and governance information.

### scenarios.json

```json
[
  {
    "id": "BASE",
    "description": "Current best-estimate assumptions"
  },
  {
    "id": "PANDEMIC",
    "description": "Severe pandemic: mortality +50% ages 65+, +20% younger, lapses -30%",
    "shocks": [
      {"table": "mortality_select", "multiply": 1.5, "where": {"attained_age": {"gte": 65}}},
      {"table": "mortality_select", "multiply": 1.2, "where": {"attained_age": {"lt": 65}}},
      {"table": "lapse_rates", "multiply": 0.7}
    ]
  },
  {
    "id": "RATE_SHOCK",
    "description": "Sudden rate drop: risk-free rates -200bp across all years",
    "shocks": [
      {"table": "risk_free_rates", "add": -0.02}
    ]
  },
  {
    "id": "MASS_LAPSE",
    "description": "Mass lapse event: lapse rates doubled",
    "shocks": [
      {"table": "lapse_rates", "multiply": 2.0}
    ]
  },
  {
    "id": "COMBINED_STRESS",
    "description": "Combined adverse: pandemic + rate shock + expense inflation",
    "shocks": [
      {"table": "mortality_select", "multiply": 1.3},
      {"table": "risk_free_rates", "add": -0.01},
      {"table": "space_params", "multiply": 1.2, "column": "expense_maint"},
      {"table": "lapse_rates", "multiply": 1.3}
    ]
  }
]
```

### Charts

**Chart — Grouped bar**: All 5 scenarios compared on PV_net_cf, grouped by product. The "board-level" chart that shows the full stress test suite at a glance.

### Report enhancements (beyond the standard template)

This step's report is the "full regulatory" version:

1. **Executive summary** — 3-sentence overview of worst-case findings
2. **Scenario descriptions table** — generated by `describe_scenarios()`: scenario name, narrative, parameter changes
3. **Results matrix** — all metrics x all scenarios, with conditional formatting (pass/warning/fail thresholds)
4. **Per-product breakdown** — GMDB vs GMAB respond differently to each scenario
5. **Key risk indicators** — which scenarios breach defined thresholds
6. **Audit trail** — model version, run timestamp, assumption file hashes, scenario config version

### Key concepts taught

- Named scenarios as economic narratives (not just parameter sets)
- `describe_scenarios()` for audit trail generation
- Multi-shock scenarios (combining mortality + rates + expenses)
- Regulatory-style reporting (ORSA-inspired structure)
- The difference between individual shocks and combined stress

## Report Design

### Consistent structure

Every `report/report.md` follows this template:

```markdown
# [Step Name] — Scenario Analysis Report

**Model**: gaspatchio appliedlife VA  |  **Points**: 8  |  **Scenarios**: N  |  **Runtime**: X.XXs

---

## Scenario Configuration

| Scenario | Description | Parameter Changes |
|---|---|---|
| BASE | Current best-estimate | None |
| MORT_UP_20 | Mortality +20% | mortality_select x 1.2 |

## Results Summary

| Scenario | PV Net CF | PV Claims | PV Premiums | vs BASE |
|---|---|---|---|---|
| BASE | 1,234,567 | 2,345,678 | 456,789 | -- |
| MORT_UP_20 | 1,123,456 | 2,567,890 | 456,789 | -9.0% |

## Analysis

![Scenario Comparison](scenario_comparison.png)

[1-3 sentences interpreting the chart]

## Key Findings

- Mortality shocks have the largest single-factor impact at X% of base PV
- Rate scenarios show asymmetric response: DOWN impacts more than UP
- GMAB products are more sensitive to rate changes than GMDB products

## Audit Trail

Generated: 2026-03-25 14:30:00
Model: gaspatchio appliedlife VA v1.0
Points: 8 (2023Q4IF)
[describe_scenarios() output]
```

### Chart design principles

- **Consistent colour palette**: BASE = steel blue, adverse = red gradient (light to dark by severity), favourable = green
- **Professional labels**: Axis titles with units, scenario names as legend entries, value annotations on bars
- **Runtime badge**: Every report header shows execution time
- **Per-product detail**: Charts show GMDB vs GMAB breakdown where relevant
- **Altair theme**: Set a custom theme once in a shared module, reuse across all steps

### Shared charting module

Create `tutorial/level-5-scenarios/charts.py` — shared Altair helpers and report generation:

```python
import altair as alt

# Colour palette
COLORS = {
    "BASE": "#4682B4",      # steel blue
    "favorable": "#2E8B57", # sea green
    "adverse_1": "#CD853F", # peru (mild)
    "adverse_2": "#CD5C5C", # indian red (moderate)
    "adverse_3": "#8B0000", # dark red (severe)
}

def scenario_bar_chart(df, metric, title): ...
def tornado_chart(df, base_scenario, metric, title): ...
def sensitivity_line(df, x_col, y_col, title): ...
def heatmap_2d(df, x_col, y_col, value_col, title): ...
def waterfall_chart(df, components, base_scenario, target_scenario, title): ...
def cashflow_line(df, time_col, value_col, scenario_col, title): ...
def write_report(path, title, metadata, sections): ...
```

Each chart function returns an `alt.Chart` object. The caller saves it: `chart.save("report/chart.png")`.

`write_report()` accepts structured sections (config table, results table, chart paths, findings, audit) and writes `report/report.md`.

## model.py evolution

| Step | Change to model.py from base |
|---|---|
| Base | L4 copy, cleaned up docstring, local paths |
| Step 01 | None — shocks modify Tables before model runs |
| Step 02 | None |
| Step 03 | None |
| Step 04 | None |

The model stays completely stable. All scenario logic lives in `run_scenarios.py`. Steps import `base/model.py` directly.

## What L5 does NOT cover (deferred to L6)

- Stochastic / Monte Carlo scenario generation
- 1,000+ scenarios
- Risk metrics from distributions (VaR, CTE, percentiles)
- Memory-efficient batching (`batch_scenarios()`)
- Large model point sets (1,000+ points)
- Streaming execution
- Performance profiling and optimization
- Cloud execution (ScenarioRun)

## Success Criteria

1. Every step runs with `uv run python run_scenarios.py` and produces a `report/` directory
2. Every report has embedded charts (PNG) and is readable as standalone markdown
3. Charts are professional quality — consistent colours, clear labels, proper formatting
4. model.py is unchanged across steps (all steps import base/model.py)
5. The tornado chart (Step 01) is instantly recognisable to any actuary
6. The 2D heatmap (Step 03) shows interaction effects clearly
7. Runtime is displayed in every report header (sub-second for 8 points x N scenarios)
8. `describe_scenarios()` audit trail is included in every report
9. An actuary reading the Step 04 report would consider it regulatory-quality structure
