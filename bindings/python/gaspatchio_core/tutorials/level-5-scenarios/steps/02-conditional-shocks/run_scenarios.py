# ruff: noqa: INP001, T201
"""
Level 5 Step 02: Conditional Shocks

Demonstrates three conditional shock types:

- **FilteredShock** (``where`` clause): Apply shocks only to rows matching
  a dimension filter (e.g., mortality +50 % for attained_age >= 65).
- **TimeConditionalShock** (``when`` clause): Apply shocks only at specific
  projection times (e.g., rates drop 100 bp starting year 3).
- **PipelineShock**: Chain multiple operations (e.g., multiply then clip).

Produces:
  - cashflow_comparison.png -- monthly net cashflow for policy 1
  - death_claims.png -- PV death claims by scenario and product
  - report/report.md -- full Markdown report with audit trail

Usage:
    uv run python tutorial/level-5-scenarios/steps/02-conditional-shocks/run_scenarios.py
"""

import json
import sys
import time
from pathlib import Path

import polars as pl

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parents[1] / "base"
sys.path.insert(0, str(SCRIPT_DIR.parents[1]))  # for charts import
sys.path.insert(0, str(BASE_DIR))  # for model import

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import describe_scenarios, parse_scenario_config

import charts  # noqa: E402
import model  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCENARIOS_FILE = SCRIPT_DIR / "scenarios.json"
MODEL_POINTS_PATH = BASE_DIR / "model_points.parquet"

PV_COMPONENTS = [
    "pv_claims",
    "pv_expenses",
    "pv_inv_income",
    "pv_premiums",
    "pv_commissions",
    "pv_av_change",
]

# ---------------------------------------------------------------------------
# Load scenario config
# ---------------------------------------------------------------------------

config_text = SCENARIOS_FILE.read_text()
raw_config = json.loads(config_text)

scenarios = parse_scenario_config(raw_config)
scenario_ids = list(scenarios.keys())

# Build audit trail description
audit_trail = describe_scenarios(scenarios)

# ---------------------------------------------------------------------------
# Run each scenario
# ---------------------------------------------------------------------------

start = time.perf_counter()

mp = pl.read_parquet(MODEL_POINTS_PATH)
n_points = len(mp)

all_frames: list[pl.DataFrame] = []

for scenario_id, shocks in scenarios.items():
    # Load fresh assumptions for each scenario
    assumptions = model.load_assumptions()

    # Apply table shocks to the relevant assumption tables
    for shock in shocks:
        table_name = getattr(shock, "table", None)
        if table_name and table_name in assumptions:
            table_obj = assumptions[table_name]
            assumptions[table_name] = table_obj.with_shock(shock)

    # Run the model
    af = ActuarialFrame(mp)
    result_af = model.main(af, assumptions_override=assumptions)
    result = result_af.collect()

    # Tag with scenario_id
    result = result.with_columns(pl.lit(scenario_id).alias("scenario_id"))
    all_frames.append(result)

all_results = pl.concat(all_frames)

runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# Chart 1: Cashflow line chart -- monthly net cashflow for policy 1
# ---------------------------------------------------------------------------

point1 = all_results.filter(pl.col("point_id") == 1)

cashflow_rows: list[dict[str, object]] = []
for row in point1.iter_rows(named=True):
    ncf = row["net_cf"]  # list column
    scenario = row["scenario_id"]
    for i, val in enumerate(ncf):
        cashflow_rows.append({"scenario_id": scenario, "month": i, "net_cf": val})

cashflow_df = pl.DataFrame(cashflow_rows)

cashflow_chart = charts.cashflow_line(
    df=cashflow_df,
    time_col="month",
    value_col="net_cf",
    scenario_col="scenario_id",
    title="Monthly Net Cashflow: Policy 1",
)

report_dir = SCRIPT_DIR / "report"
report_dir.mkdir(parents=True, exist_ok=True)
cashflow_chart.save(str(report_dir / "cashflow_comparison.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Chart 2: Grouped bar -- PV death claims by scenario x product
# ---------------------------------------------------------------------------

scenario_product_death = all_results.group_by("scenario_id", "product_id").agg(
    pl.col("pv_claims_death").sum(),
)

death_bar = charts.scenario_bar_chart(
    df=scenario_product_death,
    metric="pv_claims_death",
    group_col="product_id",
    scenario_col="scenario_id",
    title="PV Death Claims by Scenario",
)

death_bar.save(str(report_dir / "death_claims.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Results summary table
# ---------------------------------------------------------------------------

scenario_totals = all_results.group_by("scenario_id").agg(
    pl.col("pv_net_cf").sum(),
    *[pl.col(c).sum() for c in PV_COMPONENTS],
)

base_pv = scenario_totals.filter(pl.col("scenario_id") == "BASE")["pv_net_cf"][0]

summary_table = (
    scenario_totals.select("scenario_id", "pv_net_cf", "pv_claims")
    .sort("scenario_id")
    .with_columns(
        ((pl.col("pv_net_cf") - base_pv) / abs(base_pv)).alias("vs_base_pct"),
    )
)

summary_table_display = summary_table.with_columns(
    pl.col("pv_net_cf")
    .map_elements(charts.format_number, return_dtype=pl.String)
    .alias("pv_net_cf"),
    pl.col("pv_claims")
    .map_elements(charts.format_number, return_dtype=pl.String)
    .alias("pv_claims"),
    pl.col("vs_base_pct")
    .map_elements(charts.format_pct, return_dtype=pl.String)
    .alias("vs_base_pct"),
)

# ---------------------------------------------------------------------------
# Key findings (auto-generated)
# ---------------------------------------------------------------------------

findings: list[str] = []

# Death claims impact from pandemic scenario
pandemic_death = scenario_totals.filter(pl.col("scenario_id") == "PANDEMIC_ELDERLY")
if not pandemic_death.is_empty():
    base_death = scenario_totals.filter(pl.col("scenario_id") == "BASE")[
        "pv_claims"
    ][0]
    pandemic_death_val = pandemic_death["pv_claims"][0]
    delta_pct = (pandemic_death_val - base_death) / abs(base_death) * 100
    findings.append(
        f"PANDEMIC_ELDERLY increases total PV claims by {delta_pct:+.1f}% vs BASE, "
        "reflecting the age-targeted mortality shock on this elderly portfolio."
    )

# Delayed rate shock timing
delayed = scenario_totals.filter(pl.col("scenario_id") == "DELAYED_RATE_SHOCK")
if not delayed.is_empty():
    delayed_pv = delayed["pv_net_cf"][0]
    delayed_pct = (delayed_pv - base_pv) / abs(base_pv) * 100
    findings.append(
        f"DELAYED_RATE_SHOCK changes PV net cashflows by {delayed_pct:+.1f}% vs BASE. "
        "The impact appears at year 3 when the 100bp rate drop takes effect."
    )

# Mortality floor effect
mort_floor = scenario_totals.filter(pl.col("scenario_id") == "MORT_FLOOR")
if not mort_floor.is_empty():
    floor_death = mort_floor["pv_claims"][0]
    base_death = scenario_totals.filter(pl.col("scenario_id") == "BASE")[
        "pv_claims"
    ][0]
    floor_pct = (floor_death - base_death) / abs(base_death) * 100
    findings.append(
        f"MORT_FLOOR increases PV claims by {floor_pct:+.1f}% vs BASE. "
        "The pipeline applies a 30% uplift then floors at 0.5%, "
        "preventing any mortality rate from falling below the minimum."
    )

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

report_path = charts.write_report(
    path=SCRIPT_DIR,
    title="Conditional Shocks",
    metadata={
        "points": n_points,
        "scenarios": len(scenario_ids),
        "runtime_s": runtime,
    },
    sections=[
        {
            "heading": "Scenario Configuration",
            "content": (
                "This step demonstrates three conditional shock types:\n\n"
                "- **FilteredShock** (`where` clause) -- applies only to rows matching "
                "a dimension filter (e.g., mortality +50% for ages 65+)\n"
                "- **TimeConditionalShock** (`when` clause) -- applies at specific "
                "projection times (e.g., rates drop 100bp starting year 3)\n"
                "- **PipelineShock** -- chains multiple operations "
                "(e.g., multiply by 1.3 then floor at 0.5%)\n\n"
                "All scenarios are defined declaratively in `scenarios.json` "
                "and parsed via `parse_scenario_config()`."
            ),
        },
        {
            "heading": "Scenario Parameters",
            "content": "```json\n" + config_text + "\n```",
        },
        {
            "heading": "Audit Trail",
            "content": audit_trail,
        },
        {
            "heading": "Results Summary",
            "table": summary_table_display,
        },
        {
            "heading": "Cashflow Comparison (Policy 1)",
            "chart": "cashflow_comparison.png",
        },
        {
            "heading": "PV Death Claims by Scenario",
            "chart": "death_claims.png",
        },
        {
            "heading": "Key Findings",
            "findings": findings,
        },
    ],
)

print(f"Report generated in {runtime:.2f}s -> {report_path}")
