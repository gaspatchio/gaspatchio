"""
Level 5 Step 04: Scenario Comparison & Regulatory Reporting

The capstone step -- combines multiple named scenarios into a regulatory-style
stress test suite.  Each scenario represents a meaningful economic narrative
(pandemic, rate shock, mass lapse, combined adverse), not just an isolated
parameter change.

The report is the most comprehensive in Level 5: executive summary, scenario
configuration table, full results matrix, per-product breakdown, key risk
indicators with warning/breach thresholds, and a complete governance audit
trail.

Key APIs demonstrated:
  - parse_scenario_config()  -- JSON list -> dict[str, list[Shock]]
  - Table.with_shock()       -- create a shocked copy of an assumption table
  - describe_scenarios()     -- audit-trail markdown from shock specs
  - scenario_bar_chart()     -- grouped bar comparison across scenarios

Usage:
    uv run python tutorial/level-5-scenarios/steps/04-scenario-comparison/run_scenarios.py
"""

import datetime
import json
import sys
import time
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import describe_scenarios, parse_scenario_config
from gaspatchio_core.scenarios.shocks import Shock

STEP_DIR = Path(__file__).resolve().parent
BASE_DIR = STEP_DIR.parent.parent / "base"
sys.path.insert(0, str(BASE_DIR.parent))  # for charts import
sys.path.insert(0, str(BASE_DIR))  # for model import

import charts 
import model 

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

config_text = (STEP_DIR / "scenarios.json").read_text()
raw_config = json.loads(config_text)
scenario_shocks = parse_scenario_config(raw_config)

# Build a description lookup from the raw JSON (parse_scenario_config drops it)
scenario_descriptions: dict[str, str] = {}
for item in raw_config:
    if isinstance(item, dict):
        scenario_descriptions[item["id"]] = item.get("description", "")
    elif isinstance(item, str):
        scenario_descriptions[item] = ""

MODEL_POINTS_PATH = BASE_DIR / "model_points.parquet"
PROJECTION_MONTHS = 82

PV_METRICS = [
    "pv_net_cf",
    "pv_claims",
    "pv_expenses",
    "pv_premiums",
    "pv_inv_income",
    "pv_av_change",
]

# Risk indicator thresholds (% change vs BASE)
WARNING_THRESHOLD = 0.10  # 10%
BREACH_THRESHOLD = 0.20  # 20%

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_shocks(
    assumptions: dict[str, object],
    shocks: list[Shock],
) -> dict[str, object]:
    """Apply a list of shocks to assumption tables, returning a modified copy.

    For Table objects the shock is applied via Table.with_shock().
    For plain DataFrames (e.g. space_params) a column-specific shock is
    applied directly using the shock's Polars expression.
    """
    for shock in shocks:
        table_name = getattr(shock, "table", None)
        if not table_name or table_name not in assumptions:
            continue

        target = assumptions[table_name]
        column_name = getattr(shock, "column", None)

        if isinstance(target, Table):
            assumptions[table_name] = target.with_shock(shock)
        elif isinstance(target, pl.DataFrame) and column_name:
            assumptions[table_name] = target.with_columns(
                shock.to_expression(pl.col(column_name)).alias(column_name)
            )

    return assumptions


# ---------------------------------------------------------------------------
# Run each scenario
# ---------------------------------------------------------------------------

start = time.perf_counter()

mp = pl.read_parquet(MODEL_POINTS_PATH)
n_points = len(mp)

results: list[pl.DataFrame] = []

for scenario_id, shocks in scenario_shocks.items():
    # Fresh assumptions for every scenario so shocks don't stack
    assumptions = model.load_assumptions()
    assumptions = _apply_shocks(assumptions, shocks)

    af = ActuarialFrame(mp)
    result = model.main(af, assumptions_override=assumptions).collect()
    result = result.with_columns(pl.lit(scenario_id).alias("scenario_id"))
    results.append(result)

all_results = pl.concat(results, how="diagonal_relaxed")
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# Aggregate results
# ---------------------------------------------------------------------------

# Per-scenario totals (sum all points within each scenario)
scenario_totals = all_results.group_by("scenario_id").agg(
    *[pl.col(m).sum() for m in PV_METRICS],
)

# Per-scenario x product (for grouped bar chart)
scenario_product = all_results.group_by("scenario_id", "product_id").agg(
    *[pl.col(m).sum() for m in PV_METRICS],
)

base_pv = scenario_totals.filter(pl.col("scenario_id") == "BASE")["pv_net_cf"][0]

# ---------------------------------------------------------------------------
# Chart: Grouped bar -- all 5 scenarios by product
# ---------------------------------------------------------------------------

bar_chart = charts.scenario_bar_chart(
    df=scenario_product,
    metric="pv_net_cf",
    group_col="product_id",
    scenario_col="scenario_id",
    title="Regulatory Stress Test: PV Net Cashflows by Scenario",
)

report_dir = STEP_DIR / "report"
report_dir.mkdir(parents=True, exist_ok=True)
bar_chart.save(str(report_dir / "scenario_comparison.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Section 1: Executive Summary (auto-generated)
# ---------------------------------------------------------------------------

# Find worst-case scenario
worst_row = (
    scenario_totals.filter(pl.col("scenario_id") != "BASE")
    .with_columns(
        ((pl.col("pv_net_cf") - base_pv) / abs(base_pv)).alias("pct_change"),
    )
    .sort("pv_net_cf")
    .head(1)
)
worst_id = worst_row["scenario_id"][0]
worst_pct = worst_row["pct_change"][0] * 100

# Check product sensitivity to rate shocks
rate_shock_product = scenario_product.filter(pl.col("scenario_id") == "RATE_SHOCK")
base_product = scenario_product.filter(pl.col("scenario_id") == "BASE")

product_rate_impact: dict[str, float] = {}
for product in base_product["product_id"].to_list():
    base_val = base_product.filter(pl.col("product_id") == product)["pv_net_cf"][0]
    rate_val = rate_shock_product.filter(pl.col("product_id") == product)["pv_net_cf"][0]
    product_rate_impact[product] = abs((rate_val - base_val) / abs(base_val)) * 100

more_sensitive_product = max(product_rate_impact, key=product_rate_impact.get)  # type: ignore[arg-type]
less_sensitive_product = min(product_rate_impact, key=product_rate_impact.get)  # type: ignore[arg-type]

exec_summary = (
    f"The model was run across {len(scenario_shocks)} scenarios covering pandemic, "
    f"interest rate, lapse, and combined adverse stresses. "
    f"The worst-case scenario is **{worst_id}** with a "
    f"**{worst_pct:+.1f}%** impact on PV of net cashflows vs the base case. "
    f"{more_sensitive_product} products show greater sensitivity to interest rate "
    f"shocks ({product_rate_impact[more_sensitive_product]:.1f}% impact) than "
    f"{less_sensitive_product} products "
    f"({product_rate_impact[less_sensitive_product]:.1f}% impact)."
)

# ---------------------------------------------------------------------------
# Section 2: Scenario Configuration Table
# ---------------------------------------------------------------------------

# Build a table with: Scenario | Description | Parameter Changes
audit_dict = describe_scenarios(scenario_shocks, output_format="dict")

config_rows: list[dict[str, str]] = []
for sid in scenario_shocks:
    desc = scenario_descriptions.get(sid, "")
    changes = audit_dict.get(sid, ["No shocks (base case)"])
    changes_str = "; ".join(changes)
    config_rows.append({
        "Scenario": sid,
        "Description": desc,
        "Parameter Changes": changes_str,
    })

config_table = pl.DataFrame(config_rows)

# ---------------------------------------------------------------------------
# Section 3: Results Summary (all PV metrics)
# ---------------------------------------------------------------------------

results_summary = (
    scenario_totals.select("scenario_id", *PV_METRICS)
    .sort("scenario_id")
    .with_columns(
        ((pl.col("pv_net_cf") - base_pv) / abs(base_pv)).alias("vs_base"),
    )
)

results_display = results_summary.with_columns(
    *[
        pl.col(m)
        .map_elements(charts.format_number, return_dtype=pl.String)
        .alias(m)
        for m in PV_METRICS
    ],
    pl.col("vs_base")
    .map_elements(charts.format_pct, return_dtype=pl.String)
    .alias("vs_base"),
)

# ---------------------------------------------------------------------------
# Section 4: Per-Product Breakdown
# ---------------------------------------------------------------------------

products = sorted(all_results["product_id"].unique().to_list())

product_sections: list[dict[str, object]] = []
for product in products:
    prod_data = scenario_product.filter(pl.col("product_id") == product)
    prod_base_pv = prod_data.filter(pl.col("scenario_id") == "BASE")["pv_net_cf"][0]

    prod_summary = (
        prod_data.select("scenario_id", "pv_net_cf", "pv_claims", "pv_expenses")
        .sort("scenario_id")
        .with_columns(
            ((pl.col("pv_net_cf") - prod_base_pv) / abs(prod_base_pv)).alias(
                "vs_base"
            ),
        )
    )

    prod_display = prod_summary.with_columns(
        pl.col("pv_net_cf")
        .map_elements(charts.format_number, return_dtype=pl.String)
        .alias("pv_net_cf"),
        pl.col("pv_claims")
        .map_elements(charts.format_number, return_dtype=pl.String)
        .alias("pv_claims"),
        pl.col("pv_expenses")
        .map_elements(charts.format_number, return_dtype=pl.String)
        .alias("pv_expenses"),
        pl.col("vs_base")
        .map_elements(charts.format_pct, return_dtype=pl.String)
        .alias("vs_base"),
    )

    product_sections.append({
        "heading": f"Product: {product}",
        "table": prod_display,
    })

# ---------------------------------------------------------------------------
# Section 6: Key Risk Indicators
# ---------------------------------------------------------------------------

risk_indicators: list[str] = []

for row in results_summary.iter_rows(named=True):
    sid = row["scenario_id"]
    if sid == "BASE":
        continue
    vs_base = abs(row["vs_base"])
    if vs_base >= BREACH_THRESHOLD:
        risk_indicators.append(
            f"[BREACH] **{sid}**: PV net CF change of "
            f"{row['vs_base'] * 100:+.1f}% exceeds {BREACH_THRESHOLD * 100:.0f}% "
            f"breach threshold"
        )
    elif vs_base >= WARNING_THRESHOLD:
        risk_indicators.append(
            f"[WARNING] **{sid}**: PV net CF change of "
            f"{row['vs_base'] * 100:+.1f}% exceeds {WARNING_THRESHOLD * 100:.0f}% "
            f"warning threshold"
        )
    else:
        risk_indicators.append(
            f"[OK] **{sid}**: PV net CF change of "
            f"{row['vs_base'] * 100:+.1f}% within acceptable limits"
        )

# ---------------------------------------------------------------------------
# Section 7: Key Findings (auto-generated)
# ---------------------------------------------------------------------------

findings: list[str] = []

# 1. Worst-case scenario
findings.append(
    f"**{worst_id}** is the worst-case scenario with a "
    f"{worst_pct:+.1f}% impact on total PV of net cashflows."
)

# 2. Rank all scenarios by impact
impact_df = (
    scenario_totals.filter(pl.col("scenario_id") != "BASE")
    .with_columns(
        (pl.col("pv_net_cf") - base_pv).alias("delta"),
    )
    .with_columns(pl.col("delta").abs().alias("abs_delta"))
    .sort("abs_delta", descending=True)
)

scenario_ranking = ", ".join(
    f"{r['scenario_id']} ({(r['delta'] / abs(base_pv)) * 100:+.1f}%)"
    for r in impact_df.iter_rows(named=True)
)
findings.append(f"Impact ranking (largest to smallest): {scenario_ranking}.")

# 3. Combined stress vs individual
combined_pv = scenario_totals.filter(
    pl.col("scenario_id") == "COMBINED_STRESS"
)["pv_net_cf"][0]
combined_pct = (combined_pv - base_pv) / abs(base_pv) * 100

# Sum individual single-factor impacts
individual_ids = ["PANDEMIC", "RATE_SHOCK", "MASS_LAPSE"]
individual_sum = 0.0
for sid in individual_ids:
    sid_rows = scenario_totals.filter(pl.col("scenario_id") == sid)
    if not sid_rows.is_empty():
        individual_sum += sid_rows["pv_net_cf"][0] - base_pv

individual_sum_pct = individual_sum / abs(base_pv) * 100
diversification = combined_pct - individual_sum_pct
findings.append(
    f"The combined stress ({combined_pct:+.1f}%) differs from the sum of "
    f"individual stresses ({individual_sum_pct:+.1f}%) by "
    f"{diversification:+.1f} percentage points, revealing "
    f"{'diversification benefit' if abs(combined_pct) < abs(individual_sum_pct) else 'compounding risk'}."
)

# 4. Product sensitivity
findings.append(
    f"{more_sensitive_product} products are more sensitive to rate shocks "
    f"({product_rate_impact[more_sensitive_product]:.1f}% change) than "
    f"{less_sensitive_product} products "
    f"({product_rate_impact[less_sensitive_product]:.1f}% change), reflecting "
    f"the longer duration of guarantee-linked liabilities."
)

# 5. Threshold breaches
n_breaches = sum(1 for ri in risk_indicators if ri.startswith("[BREACH]"))
n_warnings = sum(1 for ri in risk_indicators if ri.startswith("[WARNING]"))
findings.append(
    f"Of {len(scenario_shocks) - 1} stress scenarios, "
    f"**{n_breaches}** breach the {BREACH_THRESHOLD * 100:.0f}% threshold "
    f"and **{n_warnings}** trigger the {WARNING_THRESHOLD * 100:.0f}% warning level."
)

# ---------------------------------------------------------------------------
# Section 8: Audit Trail
# ---------------------------------------------------------------------------

timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
audit_md = describe_scenarios(scenario_shocks, output_format="markdown")

audit_content = f"""- **Generated**: {timestamp}
- **Model**: gaspatchio appliedlife VA
- **Model Points**: {n_points} (2023Q4IF)
- **Projection**: {PROJECTION_MONTHS} months
- **Scenario Config**: scenarios.json
- **Runtime**: {runtime:.2f}s

### Scenario Descriptions

{audit_md}"""

# ---------------------------------------------------------------------------
# Assemble and write report
# ---------------------------------------------------------------------------

# Build sections list
sections: list[dict[str, object]] = [
    {
        "heading": "Executive Summary",
        "content": exec_summary,
    },
    {
        "heading": "Scenario Configuration",
        "table": config_table,
    },
    {
        "heading": "Scenario Parameters (scenarios.json)",
        "content": "```json\n" + config_text + "\n```",
    },
    {
        "heading": "Results Summary",
        "table": results_display,
    },
]

# Per-product breakdown sections
for ps in product_sections:
    sections.append(ps)

# Chart, risk indicators, findings, audit
sections.extend([
    {
        "heading": "Scenario Comparison",
        "chart": "scenario_comparison.png",
    },
    {
        "heading": "Key Risk Indicators",
        "findings": risk_indicators,
    },
    {
        "heading": "Key Findings",
        "findings": findings,
    },
    {
        "heading": "Audit Trail",
        "content": audit_content,
    },
])

report_path = charts.write_report(
    path=STEP_DIR,
    title="Scenario Comparison -- Regulatory Stress Test",
    metadata={
        "points": n_points,
        "scenarios": len(scenario_shocks),
        "runtime_s": runtime,
    },
    sections=sections,
)

print(f"Report generated in {runtime:.2f}s -> {report_path}")
