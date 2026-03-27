"""
Level 5 Step 01: Parameter Shocks with Tornado Chart

Loads a declarative scenarios.json config, applies shocks to assumption
tables (mortality, lapse, rates, expenses), runs the model once per
scenario, and produces a tornado chart ranking sensitivities by impact.

Key APIs demonstrated:
  - parse_scenario_config()  -- JSON list -> dict[str, list[Shock]]
  - Table.with_shock()       -- create a shocked copy of an assumption table
  - describe_scenarios()     -- audit-trail markdown from shock specs

Usage:
    uv run python tutorial/level-5-scenarios/steps/01-parameter-shocks/run_scenarios.py
"""

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
config = json.loads(config_text)
scenario_shocks = parse_scenario_config(config)

MODEL_POINTS_PATH = BASE_DIR / "model_points.parquet"

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
            # Plain DataFrame with a targeted column (e.g. space_params.expense_maint)
            original_dtype = target.schema[column_name]
            assumptions[table_name] = target.with_columns(
                shock.to_expression(pl.col(column_name))
                .cast(original_dtype)
                .alias(column_name)
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

all_results = pl.concat(results)
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# Aggregate results
# ---------------------------------------------------------------------------

scenario_totals = all_results.group_by("scenario_id").agg(
    pl.col("pv_net_cf").sum(),
)

base_pv = scenario_totals.filter(pl.col("scenario_id") == "BASE")["pv_net_cf"][0]

# ---------------------------------------------------------------------------
# Chart: Tornado
# ---------------------------------------------------------------------------

tornado = charts.tornado_chart(
    df=scenario_totals,
    base_scenario="BASE",
    metric="pv_net_cf",
    title="Sensitivity: Impact on PV Net Cashflows",
)

report_dir = STEP_DIR / "report"
report_dir.mkdir(parents=True, exist_ok=True)
tornado.save(str(report_dir / "tornado.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Results summary table
# ---------------------------------------------------------------------------

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
# Audit trail from describe_scenarios()
# ---------------------------------------------------------------------------

audit_trail = describe_scenarios(scenario_shocks, output_format="markdown")

# ---------------------------------------------------------------------------
# Key findings (auto-generated)
# ---------------------------------------------------------------------------

findings: list[str] = []

# Rank scenarios by absolute impact
impact_df = (
    scenario_totals.filter(pl.col("scenario_id") != "BASE")
    .with_columns(
        (pl.col("pv_net_cf") - base_pv).alias("delta"),
    )
    .with_columns(pl.col("delta").abs().alias("abs_delta"))
    .sort("abs_delta", descending=True)
)

biggest = impact_df.row(0, named=True)
biggest_pct = (biggest["delta"] / abs(base_pv)) * 100
findings.append(
    f"The largest sensitivity is **{biggest['scenario_id']}** "
    f"({biggest_pct:+.1f}% impact on PV of net cashflows)."
)

smallest = impact_df.row(-1, named=True)
smallest_pct = (smallest["delta"] / abs(base_pv)) * 100
findings.append(
    f"The smallest sensitivity is **{smallest['scenario_id']}** "
    f"({smallest_pct:+.1f}% impact)."
)

# Rate asymmetry check
rates_up = scenario_totals.filter(pl.col("scenario_id") == "RATES_UP_50BP")
rates_down = scenario_totals.filter(pl.col("scenario_id") == "RATES_DOWN_50BP")
if not rates_up.is_empty() and not rates_down.is_empty():
    up_delta = abs(rates_up["pv_net_cf"][0] - base_pv)
    down_delta = abs(rates_down["pv_net_cf"][0] - base_pv)
    if up_delta != down_delta:
        larger = "UP" if up_delta > down_delta else "DOWN"
        findings.append(
            f"Interest rate shocks are asymmetric -- the {larger} shock has a "
            f"larger absolute impact, reflecting the convexity of discounting."
        )

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

report_path = charts.write_report(
    path=STEP_DIR,
    title="Parameter Shocks -- Sensitivity Analysis",
    metadata={
        "points": n_points,
        "scenarios": len(scenario_shocks),
        "runtime_s": runtime,
    },
    sections=[
        {
            "heading": "Scenario Parameters",
            "content": "```json\n" + config_text + "\n```",
        },
        {
            "heading": "Scenario Configuration (Audit Trail)",
            "content": audit_trail,
        },
        {
            "heading": "Results Summary",
            "table": summary_table_display,
        },
        {
            "heading": "Tornado Chart",
            "chart": "tornado.png",
        },
        {
            "heading": "Key Findings",
            "findings": findings,
        },
    ],
)

print(f"Report generated in {runtime:.2f}s -> {report_path}")
