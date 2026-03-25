# Level 5 — Scenarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build tutorial Level 5 — deterministic scenario analysis with professional-grade Altair charts and markdown reports at every step.

**Architecture:** Two-script pattern: `model.py` (unchanged L4 projection model) + `run_scenarios.py` (scenario orchestration, charts, reports). Shared `charts.py` module for Altair helpers. All steps import the base model and share base data — no duplication.

**Tech Stack:** Python, gaspatchio_core (ActuarialFrame, Table, scenarios API), Polars, Altair + vl-convert-python

**Spec:** `docs/superpowers/specs/2026-03-25-level-5-scenarios-design.md`

**Reference files:**
- `tutorial/level-4-lifelib/base/model.py` — source model to copy
- `tutorial/level-4-lifelib/base/model_points.parquet` — model points
- `tutorial/level-4-lifelib/base/assumptions/` — 14 assumption parquet files
- `bindings/python/gaspatchio_core/scenarios/` — scenario API
- `bindings/python/tests/scratch/scenarios/` — example scenario scripts

---

## Task 1: Add dependencies and set up directory structure

**Files:**
- Modify: `pyproject.toml` (add altair, vl-convert-python; remove plotly)
- Create: `tutorial/level-5-scenarios/` directory structure

- [ ] **Step 1: Add altair and vl-convert-python**

```bash
uv add altair vl-convert-python
```

- [ ] **Step 2: Remove plotly**

```bash
uv remove plotly
```

- [ ] **Step 3: Verify imports**

```bash
uv run python -c "import altair as alt; print('altair', alt.__version__); chart = alt.Chart({'values': [{'x': 1, 'y': 2}]}).mark_point().encode(x='x:Q', y='y:Q'); print('chart created OK')"
```

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p tutorial/level-5-scenarios/base/assumptions
mkdir -p tutorial/level-5-scenarios/base/report
mkdir -p tutorial/level-5-scenarios/steps/01-parameter-shocks/report
mkdir -p tutorial/level-5-scenarios/steps/02-conditional-shocks/report
mkdir -p tutorial/level-5-scenarios/steps/03-sensitivity/report
mkdir -p tutorial/level-5-scenarios/steps/04-scenario-comparison/report
```

- [ ] **Step 5: Copy L4 data files**

```bash
cp tutorial/level-4-lifelib/base/model_points.parquet tutorial/level-5-scenarios/base/
cp -r tutorial/level-4-lifelib/base/assumptions/* tutorial/level-5-scenarios/base/assumptions/
```

- [ ] **Step 6: Commit**

```
feat(tutorial): set up L5 directory structure and dependencies
```

---

## Task 2: Create base model.py

**Files:**
- Create: `tutorial/level-5-scenarios/base/model.py`
- Source: `tutorial/level-4-lifelib/base/model.py`

This is a cleaned-up copy of L4's model. The model is unchanged across all L5 steps.

- [ ] **Step 1: Copy and clean up L4 model**

Copy `tutorial/level-4-lifelib/base/model.py` to `tutorial/level-5-scenarios/base/model.py`.

Changes from L4:
1. Replace the build-order docstring (phases 1-4) with:
   ```python
   """
   Level 5: Scenario-Ready Variable Annuity Model

   This is the reconciled L4 appliedlife model, ready for scenario analysis.
   The model accepts optional assumption overrides and scenario-specific
   investment returns, making it compatible with gaspatchio's scenario API.

   Key scenario entry points:
     - assumptions_override: dict of shocked Table objects (for parameter shocks)
     - scenario_returns_override: DataFrame with scenario_id column (for stochastic)
     - scenario_id column on ActuarialFrame: used for discount rate lookup (BASE/UP/DOWN)
   """
   ```
2. Change paths to point to local directory:
   ```python
   MODEL_DIR = Path(__file__).parent
   ASSUMPTIONS_DIR = MODEL_DIR / "assumptions"
   ```
3. Keep ALL existing functionality: `load_assumptions()`, `main()` with `scenario_returns_override`, `assumptions_override`, `projection_months` parameters
4. Keep stochastic detection code and scenario-aware discount rate lookup
5. Strip verbose build-phase comments but keep section headers and formula comments
6. Keep the `if __name__ == "__main__"` block

- [ ] **Step 2: Verify base model runs standalone**

```bash
uv run python tutorial/level-5-scenarios/base/model.py
```

Expected: 8 rows with PV columns (same values as L4).

- [ ] **Step 3: Verify with gspio CLI**

```bash
uv run gspio run-single-policy tutorial/level-5-scenarios/base/model.py \
    tutorial/level-5-scenarios/base/model_points.parquet 1
```

Expected: Single-policy output.

- [ ] **Step 4: Commit**

```
feat(tutorial): add L5 base model (cleaned-up L4 copy)
```

---

## Task 3: Create shared charts.py module

**Files:**
- Create: `tutorial/level-5-scenarios/charts.py`

Shared Altair chart helpers and report generation used by all steps.

- [ ] **Step 1: Create charts.py**

The module must provide these functions (all return `alt.Chart` or `alt.LayerChart`):

```python
"""Shared Altair chart helpers for Level 5 scenario reports."""

import altair as alt
import polars as pl
from pathlib import Path
from datetime import datetime

# Professional colour palette
PALETTE = {
    "BASE": "#4682B4",
    "favorable": "#2E8B57",
    "mild_adverse": "#CD853F",
    "moderate_adverse": "#CD5C5C",
    "severe_adverse": "#8B0000",
}

# Ordered scenario colours — BASE first, then severity gradient
SCENARIO_COLORS = ["#4682B4", "#2E8B57", "#CD853F", "#CD5C5C", "#8B0000", "#4B0082", "#2F4F4F"]
```

**Required functions:**

1. `scenario_bar_chart(df: pl.DataFrame, metric: str, group_col: str, scenario_col: str, title: str) -> alt.Chart`
   - Grouped bar chart: metric by scenario, grouped by group_col (e.g., product_id)
   - Colour by scenario using SCENARIO_COLORS
   - Value labels on bars
   - Professional axis labels with comma-formatted numbers

2. `tornado_chart(df: pl.DataFrame, base_scenario: str, metric: str, title: str) -> alt.Chart`
   - Horizontal bar chart ranked by absolute impact
   - Input df has columns: scenario_id, {metric}
   - Computes delta from base for each scenario
   - Bars extend left (negative) or right (positive) from zero
   - Sorted by absolute magnitude (largest impact at top)
   - Colour: red for adverse, green for favourable

3. `waterfall_chart(df: pl.DataFrame, components: list[str], base_scenario: str, target_scenario: str, title: str) -> alt.Chart`
   - Walk from base total to target total via component deltas
   - Input df has columns: scenario_id, pv_claims, pv_expenses, pv_inv_income, pv_premiums, pv_commissions, pv_av_change
   - Each bar is the delta for one component
   - Running total shown as connecting line
   - Red for negative deltas, green for positive

4. `sensitivity_line(df: pl.DataFrame, x_col: str, y_col: str, title: str, base_x: float | None = None) -> alt.Chart`
   - Line chart with points
   - Optional vertical reference line at base_x
   - Professional axis labels

5. `heatmap_2d(df: pl.DataFrame, x_col: str, y_col: str, value_col: str, title: str) -> alt.Chart`
   - Grid heatmap with text labels in each cell
   - Diverging colour scale (red-white-green or similar)
   - Axis labels

6. `cashflow_line(df: pl.DataFrame, time_col: str, value_col: str, scenario_col: str, title: str) -> alt.Chart`
   - Multi-line chart over time, one line per scenario
   - Colour by scenario

7. `write_report(path: Path, title: str, metadata: dict, sections: list[dict]) -> None`
   - Writes `report/report.md`
   - `metadata`: {"points": 8, "scenarios": 3, "runtime_s": 0.42}
   - `sections`: list of {"heading": str, "content": str} or {"heading": str, "table": pl.DataFrame} or {"heading": str, "chart": str (filename)}
   - Creates report/ directory if needed
   - Formats numbers with commas, percentages with 1 decimal

- [ ] **Step 2: Verify chart creation with a smoke test**

```bash
uv run python -c "
import sys; sys.path.insert(0, 'tutorial/level-5-scenarios')
from charts import scenario_bar_chart
import polars as pl
df = pl.DataFrame({'scenario_id': ['BASE', 'UP', 'DOWN'], 'product_id': ['GMDB']*3, 'pv_net_cf': [1000, 1200, 800]})
chart = scenario_bar_chart(df, 'pv_net_cf', 'product_id', 'scenario_id', 'Test Chart')
chart.save('/tmp/test_chart.png')
print('Chart saved OK')
"
```

- [ ] **Step 3: Commit**

```
feat(tutorial): add L5 shared charts.py module
```

---

## Task 4: Create base run_scenarios.py (BASE/UP/DOWN rate scenarios)

**Files:**
- Create: `tutorial/level-5-scenarios/base/run_scenarios.py`

The simplest multi-scenario run: cross-join model points with BASE/UP/DOWN rate scenarios.

- [ ] **Step 1: Create run_scenarios.py**

Key logic:

```python
"""
Level 5 Base: Interest Rate Scenarios (BASE / UP / DOWN)

Uses with_scenarios() to cross-join model points with scenario IDs.
The risk_free_rates.parquet already contains rate curves for BASE, UP, and DOWN.
The model's discount rate lookup uses the scenario_id column automatically.

Usage:
    uv run python tutorial/level-5-scenarios/base/run_scenarios.py
"""

import sys
import time
from pathlib import Path

import polars as pl

# Add parent for charts import
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios

import charts
import model

SCENARIOS = ["BASE", "UP", "DOWN"]

def main():
    start = time.perf_counter()

    # Load model points
    mp = pl.read_parquet(SCRIPT_DIR / "model_points.parquet")

    # Cross-join with scenario IDs
    af = ActuarialFrame(mp)
    af = with_scenarios(af, SCENARIOS)

    # Run model — scenario_id flows through to discount rate lookup
    result = model.main(af).collect()

    elapsed = time.perf_counter() - start

    # Split results by scenario
    # Generate: grouped bar chart, waterfall chart
    # Write report

    # Chart 1: Grouped bar — PV_net_cf by scenario × product
    bar_chart = charts.scenario_bar_chart(
        result, "pv_net_cf", "product_id", "scenario_id",
        "Present Value of Net Cashflows by Scenario"
    )
    bar_chart.save(str(SCRIPT_DIR / "report" / "scenario_comparison.png"))

    # Chart 2: Waterfall — BASE to UP component breakdown
    pv_components = ["pv_claims", "pv_expenses", "pv_inv_income",
                     "pv_premiums", "pv_commissions", "pv_av_change"]
    # Aggregate across all points per scenario
    agg = result.group_by("scenario_id").agg([
        pl.col(c).sum() for c in ["pv_net_cf"] + pv_components
    ])
    waterfall = charts.waterfall_chart(
        agg, pv_components, "BASE", "UP",
        "Waterfall: BASE → UP Scenario"
    )
    waterfall.save(str(SCRIPT_DIR / "report" / "waterfall.png"))

    # Write report
    charts.write_report(
        path=SCRIPT_DIR / "report",
        title="Interest Rate Scenarios",
        metadata={"points": len(mp), "scenarios": len(SCENARIOS), "runtime_s": elapsed},
        sections=[
            {"heading": "Scenario Configuration", "content": "BASE/UP/DOWN interest rate curves from risk_free_rates.parquet"},
            {"heading": "Results Summary", "table": agg},
            {"heading": "Scenario Comparison", "chart": "scenario_comparison.png"},
            {"heading": "Component Waterfall: BASE → UP", "chart": "waterfall.png"},
            # Key findings generated from data
        ],
    )

    print(f"Report generated in {elapsed:.2f}s → {SCRIPT_DIR / 'report' / 'report.md'}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run and verify**

```bash
uv run python tutorial/level-5-scenarios/base/run_scenarios.py
```

Expected:
- `report/report.md` generated
- `report/scenario_comparison.png` generated
- `report/waterfall.png` generated
- Runtime displayed
- Terminal output: "Report generated in X.XXs"

- [ ] **Step 3: Verify report content**

Open `tutorial/level-5-scenarios/base/report/report.md` and check:
- Header has model name, points (8), scenarios (3), runtime
- Results table shows PV values for BASE, UP, DOWN
- Charts are embedded and render
- UP scenario shows lower PV (higher rates → lower present values)

- [ ] **Step 4: Commit**

```
feat(tutorial): add L5 base run_scenarios.py — interest rate scenarios
```

---

## Task 5: Create Step 01 — Parameter Shocks

**Files:**
- Create: `tutorial/level-5-scenarios/steps/01-parameter-shocks/run_scenarios.py`
- Create: `tutorial/level-5-scenarios/steps/01-parameter-shocks/scenarios.json`
- Create: `tutorial/level-5-scenarios/steps/01-parameter-shocks/README.md`

- [ ] **Step 1: Create scenarios.json**

```json
[
  {"id": "BASE"},
  {
    "id": "MORT_UP_20",
    "description": "Mortality rates increased by 20%",
    "shocks": [{"table": "mortality_select", "multiply": 1.2}]
  },
  {
    "id": "LAPSE_DOWN_20",
    "description": "Lapse rates decreased by 20%",
    "shocks": [{"table": "lapse_rates", "multiply": 0.8}]
  },
  {
    "id": "RATES_UP_50BP",
    "description": "Risk-free rates +50 basis points",
    "shocks": [{"table": "risk_free_rates", "add": 0.005}]
  },
  {
    "id": "RATES_DOWN_50BP",
    "description": "Risk-free rates -50 basis points",
    "shocks": [{"table": "risk_free_rates", "add": -0.005}]
  },
  {
    "id": "EXPENSES_UP_10",
    "description": "Maintenance expenses +10%",
    "shocks": [{"table": "space_params", "multiply": 1.1, "column": "expense_maint"}]
  }
]
```

- [ ] **Step 2: Create run_scenarios.py**

Key pattern — the shock loop:

```python
import json
from gaspatchio_core.scenarios import parse_scenario_config, describe_scenarios

BASE_DIR = STEP_DIR.parent.parent / "base"
sys.path.insert(0, str(BASE_DIR.parent))  # for charts
sys.path.insert(0, str(BASE_DIR))          # for model

import charts
import model

# Load config
config = json.loads((STEP_DIR / "scenarios.json").read_text())
scenario_shocks = parse_scenario_config(config)

# Run each scenario
mp = pl.read_parquet(BASE_DIR / "model_points.parquet")
results = []
for scenario_id, shocks in scenario_shocks.items():
    assumptions = model.load_assumptions()
    for shock in shocks:
        if hasattr(shock, 'table') and shock.table in assumptions:
            assumptions[shock.table] = assumptions[shock.table].with_shock(shock)
    af = ActuarialFrame(mp)
    result = model.main(af, assumptions_override=assumptions).collect()
    result = result.with_columns(pl.lit(scenario_id).alias("scenario_id"))
    results.append(result)

all_results = pl.concat(results)
audit = describe_scenarios(scenario_shocks, output_format="markdown")

# Generate tornado chart + report
```

The **tornado chart** is the star of this step. Aggregate PV_net_cf across all points per scenario, compute delta from BASE, sort by absolute delta, and plot horizontal bars.

- [ ] **Step 3: Create README.md**

Brief README explaining: what parameter shocks are, how `scenarios.json` format works, how to run, what to look for in the report.

- [ ] **Step 4: Run and verify**

```bash
uv run python tutorial/level-5-scenarios/steps/01-parameter-shocks/run_scenarios.py
```

Expected: report/ with tornado chart PNG and report.md.

- [ ] **Step 5: Commit**

```
feat(tutorial): add L5 Step 01 — parameter shocks with tornado chart
```

---

## Task 6: Create Step 02 — Conditional Shocks

**Files:**
- Create: `tutorial/level-5-scenarios/steps/02-conditional-shocks/run_scenarios.py`
- Create: `tutorial/level-5-scenarios/steps/02-conditional-shocks/scenarios.json`
- Create: `tutorial/level-5-scenarios/steps/02-conditional-shocks/README.md`

- [ ] **Step 1: Create scenarios.json**

```json
[
  {"id": "BASE"},
  {
    "id": "PANDEMIC_ELDERLY",
    "description": "Pandemic: mortality +50% ages 65+, +10% younger",
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
    "description": "Mortality +30% but floored at 0.5%",
    "shocks": [
      {"table": "mortality_select", "pipeline": [{"multiply": 1.3}, {"clip": {"min": 0.005}}]}
    ]
  }
]
```

- [ ] **Step 2: Create run_scenarios.py**

Same shock loop pattern as Step 01. Charts:

**Chart 1 — Cashflow line chart**: For point_id=1, extract `net_cf` list column, plot monthly values over time for each scenario. Use `charts.cashflow_line()`. This requires running the model and keeping the list columns (not just PV aggregates). The run_scenarios.py should:
1. Run with `model.main(af, assumptions_override=...).collect()`
2. For the cashflow chart: extract `net_cf` for point_id=1, explode from list to rows, add a `month` column
3. For the summary: use PV scalar columns

**Chart 2 — Grouped bar**: Scenario comparison on PV_claims_death (to show pandemic impact on death claims specifically).

- [ ] **Step 3: Create README.md**

Explains: FilteredShock (where clause), TimeConditionalShock (when clause), PipelineShock (chaining). Why conditional shocks matter for realistic stress testing.

- [ ] **Step 4: Run and verify**

```bash
uv run python tutorial/level-5-scenarios/steps/02-conditional-shocks/run_scenarios.py
```

- [ ] **Step 5: Commit**

```
feat(tutorial): add L5 Step 02 — conditional shocks with cashflow charts
```

---

## Task 7: Create Step 03 — Sensitivity Analysis

**Files:**
- Create: `tutorial/level-5-scenarios/steps/03-sensitivity/run_scenarios.py`
- Create: `tutorial/level-5-scenarios/steps/03-sensitivity/README.md`

- [ ] **Step 1: Create run_scenarios.py**

No scenarios.json — the sweep is built programmatically:

```python
from gaspatchio_core.scenarios import sensitivity_analysis, parse_scenario_config

# 1D sweep: mortality
mort_scenarios = sensitivity_analysis(
    table="mortality_select",
    shock_type="multiplicative",
    values=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
    include_base=True,
)

# Run each scenario (same loop pattern)
# Collect results into DataFrame with mortality_factor column

# Chart 1: sensitivity_line — PV_net_cf vs mortality factor

# 2D sweep: mortality × lapse (3×3 = 9 scenarios)
mort_values = [0.8, 1.0, 1.2]
lapse_values = [0.8, 1.0, 1.2]
grid_scenarios = {}
for m in mort_values:
    for l in lapse_values:
        sid = f"mort_{m}_lapse_{l}"
        shocks = []
        if m != 1.0:
            shocks.append({"table": "mortality_select", "multiply": m})
        if l != 1.0:
            shocks.append({"table": "lapse_rates", "multiply": l})
        parsed = parse_scenario_config([{"id": sid, "shocks": shocks}])
        grid_scenarios.update(parsed)

# Run 9 scenarios, collect into DataFrame with mort_factor and lapse_factor columns

# Chart 2: heatmap_2d — PV_net_cf grid, mortality vs lapse
```

- [ ] **Step 2: Create README.md**

Explains: sensitivity_analysis() API, 1D sweeps, manual 2D cross-product, interpreting linearity/convexity, interaction effects in the heatmap.

- [ ] **Step 3: Run and verify**

```bash
uv run python tutorial/level-5-scenarios/steps/03-sensitivity/run_scenarios.py
```

Expected: report/ with sensitivity curve PNG, heatmap PNG, and report.md.

- [ ] **Step 4: Commit**

```
feat(tutorial): add L5 Step 03 — sensitivity analysis with heatmap
```

---

## Task 8: Create Step 04 — Scenario Comparison & Reporting

**Files:**
- Create: `tutorial/level-5-scenarios/steps/04-scenario-comparison/run_scenarios.py`
- Create: `tutorial/level-5-scenarios/steps/04-scenario-comparison/scenarios.json`
- Create: `tutorial/level-5-scenarios/steps/04-scenario-comparison/README.md`

- [ ] **Step 1: Create scenarios.json**

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
    "shocks": [{"table": "risk_free_rates", "add": -0.02}]
  },
  {
    "id": "MASS_LAPSE",
    "description": "Mass lapse event: lapse rates doubled",
    "shocks": [{"table": "lapse_rates", "multiply": 2.0}]
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

- [ ] **Step 2: Create run_scenarios.py**

Same shock loop. This step's report is the "full regulatory" version:

1. **Executive summary**: 3 sentences about worst-case findings (auto-generated from results)
2. **Scenario descriptions table**: from `describe_scenarios()` output
3. **Results matrix**: all PV metrics × all scenarios with % change from BASE
4. **Per-product breakdown**: GMDB vs GMAB results separately
5. **Grouped bar chart**: all 5 scenarios compared
6. **Audit trail**: timestamp, model info, config hash, scenario descriptions

The report should be noticeably more polished than previous steps — this is the "bling" demo.

- [ ] **Step 3: Create README.md**

Explains: named scenarios as economic narratives, multi-shock combinations, audit trails for governance, regulatory reporting (ORSA/IFRS 17 context).

- [ ] **Step 4: Run and verify**

```bash
uv run python tutorial/level-5-scenarios/steps/04-scenario-comparison/run_scenarios.py
```

Expected: report/ with grouped bar chart PNG and a comprehensive report.md that looks regulatory-quality.

- [ ] **Step 5: Commit**

```
feat(tutorial): add L5 Step 04 — scenario comparison with regulatory report
```

---

## Task 9: Create Level README and update tutorial README

**Files:**
- Create: `tutorial/level-5-scenarios/README.md`
- Modify: `tutorial/README.md`

- [ ] **Step 1: Create L5 README**

Structure:
- Overview (2 sentences)
- What it teaches (scenario analysis, shocks, sensitivity, reporting)
- Prerequisites (L4)
- Quick start (run base, then steps)
- Steps table with what each adds
- How to run (two commands: model standalone, scenarios with report)
- Chart gallery (reference to charts in each step's report/)
- Next: Level 6 (Monte Carlo + performance)

- [ ] **Step 2: Update tutorial/README.md**

In the levels table, change L5 from "Coming soon" to "Ready":
```markdown
| 5 | Scenarios | Deterministic scenario analysis: interest rate scenarios, parameter shocks, sensitivity sweeps, regulatory-style reports with Altair charts | Level 4 | Ready |
```

Add L5 steps table.

Add L5 to directory structure.

- [ ] **Step 3: Commit**

```
docs(tutorial): add L5 README and update tutorial overview
```

---

## Parallelization Notes

- **Task 1** (deps + dirs) must be first
- **Task 2** (base model) and **Task 3** (charts.py) can run in parallel after Task 1
- **Task 4** (base run_scenarios) depends on Tasks 2 and 3
- **Tasks 5-8** (steps 01-04) depend on Task 4 (establishes the shock loop pattern) and Task 3 (charts)
- **Tasks 5-8** are independent of each other and can run in parallel
- **Task 9** (READMEs) depends on all steps being complete

**Recommended sequence**: Task 1 → [Task 2 + Task 3] → Task 4 → [Tasks 5-8 in parallel] → Task 9
