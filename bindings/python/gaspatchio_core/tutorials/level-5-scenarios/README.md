# Level 5: Scenario Analysis

Deterministic scenario analysis for the reconciled VA model. Run the same model across multiple scenarios, apply parameter shocks, perform sensitivity sweeps, and produce professional-grade reports with Altair charts.

## What it demonstrates

- Interest rate scenarios (BASE/UP/DOWN) via `with_scenarios()`
- Parameter shocks via declarative JSON config and `Table.with_shock()`
- Conditional shocks: filtered by dimension (`where`), time-conditional (`when`), chained (`pipeline`)
- Sensitivity analysis: 1D parameter sweeps and 2D interaction heatmaps
- Regulatory-style scenario comparison with audit trails via `describe_scenarios()`
- Professional Altair charts: tornado charts, waterfall charts, sensitivity curves, heatmaps

## Prerequisites

Complete Level 4 (or understand the reconciled appliedlife model). Familiarity with `ActuarialFrame`, `Table.lookup()`, and the L4 model structure.

## Architecture

Every step has two scripts:

| Script | Purpose | CLI compatible? |
|---|---|---|
| `base/model.py` | The projection model (`def main(af)`) | Yes — works with `gspio run-model` |
| `run_scenarios.py` | Scenario orchestration, charts, reports | Run directly with `uv run python` |

The model is **unchanged across all steps**. All scenario logic lives in `run_scenarios.py`. This separation means you can always debug the model standalone, and scenario analysis is layered on top.

## Quick start

```bash
# Run the model standalone (single BASE scenario)
uv run gspio run-single-policy tutorial/level-5-scenarios/base/model.py \
    tutorial/level-5-scenarios/base/model_points.parquet 1

# Run interest rate scenarios with report
uv run python tutorial/level-5-scenarios/base/run_scenarios.py

# Run the full stress test suite
uv run python tutorial/level-5-scenarios/steps/04-scenario-comparison/run_scenarios.py
```

Each `run_scenarios.py` generates a `report/` directory with a markdown report and chart PNGs.

## Steps

| Step | Name | What it adds | Key chart |
|---|---|---|---|
| Base | Interest Rate Scenarios | `with_scenarios()` for BASE/UP/DOWN rate curves | Grouped bar + waterfall |
| 01 | Parameter Shocks | Declarative JSON shocks, `Table.with_shock()` | Tornado chart |
| 02 | Conditional Shocks | `where` filters, `when` time conditions, `pipeline` chains | Cashflow line chart |
| 03 | Sensitivity Analysis | `sensitivity_analysis()` 1D sweeps, manual 2D cross-product | Sensitivity curve + 2D heatmap |
| 04 | Scenario Comparison | Named regulatory scenarios, audit trail, full report | Grouped bar + regulatory report |

## gaspatchio scenario API

| Function | What it does |
|---|---|
| `with_scenarios(af, ids)` | Cross-join ActuarialFrame with scenario IDs |
| `parse_scenario_config(config)` | Parse JSON shock config into Shock objects |
| `Table.with_shock(shock)` | Apply a shock to an assumption table |
| `sensitivity_analysis(table, type, values)` | Generate 1D parameter sweep scenarios |
| `describe_scenarios(scenarios)` | Generate audit trail (markdown/text/dict) |

## JSON shock format

```json
{"table": "mortality_select", "multiply": 1.2}
{"table": "risk_free_rates", "add": -0.005}
{"table": "mortality_select", "multiply": 1.5, "where": {"attained_age": {"gte": 65}}}
{"table": "risk_free_rates", "add": -0.01, "when": {"year": {"gte": 3}}}
{"table": "mortality_select", "pipeline": [{"multiply": 1.3}, {"clip": {"min": 0.005}}]}
```

## Report output

Every step produces a `report/report.md` with:
- Model metadata (points, scenarios, runtime)
- Scenario configuration table
- Results summary with % change from base
- Embedded charts (PNG)
- Key findings (auto-generated)
- Audit trail (from `describe_scenarios()`)

## Next: Level 6 — Monte Carlo & Performance

Level 6 adds stochastic scenarios (1,000+ generated paths), risk metrics (VaR, CTE), memory-efficient batching, and performance profiling at scale.
