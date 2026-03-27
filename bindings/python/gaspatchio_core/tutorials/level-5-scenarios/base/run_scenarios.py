# ruff: noqa: INP001, T201
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

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))  # for charts import
sys.path.insert(0, str(SCRIPT_DIR))  # for model import

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios

import charts  # noqa: E402
import model  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCENARIOS = ["BASE", "UP", "DOWN"]
MODEL_POINTS_PATH = SCRIPT_DIR / "model_points.parquet"

PV_COMPONENTS = [
    "pv_claims",
    "pv_expenses",
    "pv_inv_income",
    "pv_premiums",
    "pv_commissions",
    "pv_av_change",
]

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

start = time.perf_counter()

# 1. Load model points
mp = pl.read_parquet(MODEL_POINTS_PATH)
n_points = len(mp)

# 2. Expand across scenarios (8 points x 3 scenarios = 24 rows)
af = ActuarialFrame(mp)
af = with_scenarios(af, SCENARIOS)

# 3. Run model — scenario_id flows through to discount rate lookup
result_af = model.main(af)
result = result_af.collect()

runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# Aggregate results
# ---------------------------------------------------------------------------

# Per-scenario totals (sum all points within each scenario)
scenario_totals = result.group_by("scenario_id").agg(
    pl.col("pv_net_cf").sum(),
    *[pl.col(c).sum() for c in PV_COMPONENTS],
)

# Per-scenario x product (for grouped bar chart)
scenario_product = result.group_by("scenario_id", "product_id").agg(
    pl.col("pv_net_cf").sum(),
)

# ---------------------------------------------------------------------------
# Chart 1: Grouped bar — PV of Net Cashflows by Scenario x Product
# ---------------------------------------------------------------------------

bar_chart = charts.scenario_bar_chart(
    df=scenario_product,
    metric="pv_net_cf",
    group_col="product_id",
    scenario_col="scenario_id",
    title="Present Value of Net Cashflows by Scenario",
)

report_dir = SCRIPT_DIR / "report"
report_dir.mkdir(parents=True, exist_ok=True)
bar_chart.save(str(report_dir / "scenario_comparison.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Chart 2: Waterfall — BASE → UP component walk
# ---------------------------------------------------------------------------

# Build signed component columns so they sum to pv_net_cf.
# pv_net_cf = pv_premiums + pv_inv_income - pv_claims - pv_expenses
#             - pv_commissions - pv_av_change
waterfall_data = scenario_totals.with_columns(
    (-pl.col("pv_claims")).alias("Claims"),
    (-pl.col("pv_expenses")).alias("Expenses"),
    pl.col("pv_inv_income").alias("Inv Income"),
    pl.col("pv_premiums").alias("Premiums"),
    (-pl.col("pv_commissions")).alias("Commissions"),
    (-pl.col("pv_av_change")).alias("AV Change"),
)

waterfall_components = [
    "Claims",
    "Expenses",
    "Inv Income",
    "Premiums",
    "Commissions",
    "AV Change",
]

waterfall = charts.waterfall_chart(
    df=waterfall_data,
    components=waterfall_components,
    base_scenario="BASE",
    target_scenario="UP",
    title="Waterfall: BASE \u2192 UP Scenario",
    scenario_col="scenario_id",
)

waterfall.save(str(report_dir / "waterfall.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Results summary table
# ---------------------------------------------------------------------------

base_pv = scenario_totals.filter(pl.col("scenario_id") == "BASE")["pv_net_cf"][0]

summary_table = (
    scenario_totals.select("scenario_id", "pv_net_cf")
    .sort("scenario_id")
    .with_columns(
        ((pl.col("pv_net_cf") - base_pv) / abs(base_pv)).alias("vs_base_pct"),
    )
)

summary_table_display = summary_table.with_columns(
    pl.col("pv_net_cf")
    .map_elements(charts.format_number, return_dtype=pl.String)
    .alias("pv_net_cf"),
    pl.col("vs_base_pct")
    .map_elements(charts.format_pct, return_dtype=pl.String)
    .alias("vs_base_pct"),
)

# ---------------------------------------------------------------------------
# Key findings (auto-generated)
# ---------------------------------------------------------------------------

findings: list[str] = []

# Which scenario has the largest impact?
up_pv = scenario_totals.filter(pl.col("scenario_id") == "UP")["pv_net_cf"][0]
down_pv = scenario_totals.filter(pl.col("scenario_id") == "DOWN")["pv_net_cf"][0]

up_delta_pct = (up_pv - base_pv) / abs(base_pv) * 100
down_delta_pct = (down_pv - base_pv) / abs(base_pv) * 100

if abs(up_delta_pct) > abs(down_delta_pct):
    findings.append(
        f"The UP scenario has the largest impact on PV of net cashflows "
        f"({up_delta_pct:+.1f}% vs BASE)."
    )
else:
    findings.append(
        f"The DOWN scenario has the largest impact on PV of net cashflows "
        f"({down_delta_pct:+.1f}% vs BASE)."
    )

# Direction check — for net-negative cashflows, UP rates make PV less negative
# (liability shrinks), DOWN rates make PV more negative (liability grows).
if abs(up_pv) < abs(base_pv):
    findings.append(
        "Higher interest rates (UP) reduce the absolute present value of net "
        "cashflows, as expected from heavier discounting."
    )
if abs(down_pv) > abs(base_pv):
    findings.append(
        "Lower interest rates (DOWN) increase the absolute present value of net "
        "cashflows, as expected from lighter discounting."
    )

# Which product is more sensitive?
product_sensitivity = (
    scenario_product.pivot(on="scenario_id", index="product_id", values="pv_net_cf")
    .with_columns(
        ((pl.col("UP") - pl.col("BASE")) / pl.col("BASE").abs()).alias("up_pct"),
        ((pl.col("DOWN") - pl.col("BASE")) / pl.col("BASE").abs()).alias("down_pct"),
    )
    .with_columns(
        (pl.col("up_pct").abs() + pl.col("down_pct").abs()).alias("total_sensitivity"),
    )
    .sort("total_sensitivity", descending=True)
)

most_sensitive = product_sensitivity["product_id"][0]
least_sensitive = product_sensitivity["product_id"][-1]
findings.append(
    f"{most_sensitive} products are more sensitive to interest rate changes "
    f"than {least_sensitive} products."
)

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

report_path = charts.write_report(
    path=SCRIPT_DIR,
    title="Interest Rate Scenarios",
    metadata={
        "points": n_points,
        "scenarios": len(SCENARIOS),
        "runtime_s": runtime,
    },
    sections=[
        {
            "heading": "Scenario Configuration",
            "content": (
                "Three interest rate scenarios from the risk-free rate term structure:\n\n"
                "- **BASE** -- Current market yield curve (no shock)\n"
                "- **UP** -- Parallel upward shift of the yield curve\n"
                "- **DOWN** -- Parallel downward shift of the yield curve\n\n"
                "The `with_scenarios()` API cross-joins the 8 model points with the "
                "3 scenario IDs, producing 24 rows. The model's discount rate lookup "
                "automatically selects the correct rate curve via the `scenario_id` column."
            ),
        },
        {
            "heading": "Results Summary",
            "table": summary_table_display,
        },
        {
            "heading": "Scenario Comparison",
            "chart": "scenario_comparison.png",
        },
        {
            "heading": "Waterfall: BASE to UP",
            "chart": "waterfall.png",
        },
        {
            "heading": "Key Findings",
            "findings": findings,
        },
    ],
)

print(f"Report generated in {runtime:.2f}s \u2192 {report_path}")
