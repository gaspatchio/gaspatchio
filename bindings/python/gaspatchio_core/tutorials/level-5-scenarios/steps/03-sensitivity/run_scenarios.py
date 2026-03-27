# ruff: noqa: INP001, T201
"""
Level 5 Step 03: Sensitivity Analysis

Demonstrates two techniques for systematic parameter sweeps:

1. **1D sweep** -- Use ``sensitivity_analysis()`` to vary a single parameter
   (mortality factor 0.8 to 1.4) and plot the resulting PV of net cashflows
   as a sensitivity curve.

2. **2D sweep** -- Build a mortality x lapse cross-product grid manually with
   ``parse_scenario_config()`` and visualise the results as a heatmap.

No ``scenarios.json`` is required -- sweeps are built programmatically.

Usage:
    uv run python tutorial/level-5-scenarios/steps/03-sensitivity/run_scenarios.py
"""

import sys
import time
from pathlib import Path

import polars as pl

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parents[1] / "base"
sys.path.insert(0, str(SCRIPT_DIR.parents[1]))  # for charts import
sys.path.insert(0, str(BASE_DIR))  # for model import

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import parse_scenario_config, sensitivity_analysis

import charts  # noqa: E402
import model  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_POINTS_PATH = BASE_DIR / "model_points.parquet"

MORT_SWEEP_VALUES = [0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4]
MORT_GRID_VALUES = [0.8, 1.0, 1.2]
LAPSE_GRID_VALUES = [0.8, 1.0, 1.2]

# ---------------------------------------------------------------------------
# Helper: run a single scenario and return aggregated PV net CF
# ---------------------------------------------------------------------------


def run_scenario(
    mp: pl.DataFrame,
    shocks: list[object],
) -> float:
    """Run the model with the given shocks and return the total pv_net_cf."""
    assumptions = model.load_assumptions()

    for shock in shocks:
        table_name = shock.table  # type: ignore[attr-defined]
        if table_name in assumptions and hasattr(assumptions[table_name], "with_shock"):
            assumptions[table_name] = assumptions[table_name].with_shock(shock)

    af = ActuarialFrame(mp)
    result_af = model.main(af, assumptions_override=assumptions)
    result = result_af.collect()
    return result["pv_net_cf"].sum()


# ===========================================================================
# PART 1: 1D Mortality Sweep
# ===========================================================================

start = time.perf_counter()

mp = pl.read_parquet(MODEL_POINTS_PATH)
n_points = len(mp)

# Generate shock specifications for the mortality sweep.
# Note: 1.0 is in MORT_SWEEP_VALUES so it acts as the base case (identity shock).
# We don't set include_base=True since that would add a duplicate 1.0 entry.
mort_scenarios = sensitivity_analysis(
    table="mortality_select",
    shock_type="multiplicative",
    values=MORT_SWEEP_VALUES,
)

# Run each scenario
sweep_records: list[dict[str, float]] = []

for scenario_id, shocks in mort_scenarios.items():
    pv_net_cf = run_scenario(mp, shocks)

    # Extract the mortality factor from the scenario_id
    # Format: "mortality_select_0.8" -> 0.8
    factor = float(scenario_id.split("_")[-1])

    sweep_records.append({
        "scenario_id": scenario_id,
        "mortality_factor": factor,
        "pv_net_cf": pv_net_cf,
    })

sweep_df = pl.DataFrame(sweep_records).sort("mortality_factor")

part1_time = time.perf_counter() - start

# Chart 1: Sensitivity curve
sensitivity_chart = charts.sensitivity_line(
    sweep_df,
    "mortality_factor",
    "pv_net_cf",
    "Sensitivity: PV Net CF vs Mortality Factor",
    base_x=1.0,
)

report_dir = SCRIPT_DIR / "report"
report_dir.mkdir(parents=True, exist_ok=True)
sensitivity_chart.save(str(report_dir / "sensitivity_mortality.png"), scale_factor=2)

# ===========================================================================
# PART 2: 2D Sweep (Mortality x Lapse)
# ===========================================================================

part2_start = time.perf_counter()

grid_scenarios: dict[str, list[object]] = {}

for m in MORT_GRID_VALUES:
    for lps in LAPSE_GRID_VALUES:
        sid = f"mort_{m}_lapse_{lps}"
        shock_configs: list[dict[str, object]] = []
        if m != 1.0:
            shock_configs.append({"table": "mortality_select", "multiply": m})
        if lps != 1.0:
            shock_configs.append({"table": "lapse_rates", "multiply": lps})

        parsed = parse_scenario_config([{"id": sid, "shocks": shock_configs}])
        grid_scenarios.update(parsed)

# Run all 9 scenarios
grid_records: list[dict[str, float]] = []

for scenario_id, shocks in grid_scenarios.items():
    pv_net_cf = run_scenario(mp, shocks)

    # Extract factors from scenario_id: "mort_0.8_lapse_1.0"
    parts = scenario_id.split("_")
    mort_factor = float(parts[1])
    lapse_factor = float(parts[3])

    grid_records.append({
        "mortality_factor": mort_factor,
        "lapse_factor": lapse_factor,
        "pv_net_cf": pv_net_cf,
    })

grid_df = pl.DataFrame(grid_records).sort("mortality_factor", "lapse_factor")

part2_time = time.perf_counter() - part2_start
total_time = time.perf_counter() - start

# Chart 2: 2D Heatmap
heatmap_chart = charts.heatmap_2d(
    grid_df,
    "mortality_factor",
    "lapse_factor",
    "pv_net_cf",
    "Interaction: Mortality x Lapse Impact on PV Net CF",
)

heatmap_chart.save(str(report_dir / "heatmap_interaction.png"), scale_factor=2)

# ---------------------------------------------------------------------------
# Format display tables
# ---------------------------------------------------------------------------

sweep_display = sweep_df.select("mortality_factor", "pv_net_cf").with_columns(
    pl.col("pv_net_cf")
    .map_elements(charts.format_number, return_dtype=pl.String)
    .alias("pv_net_cf"),
)

grid_display = grid_df.with_columns(
    pl.col("pv_net_cf")
    .map_elements(charts.format_number, return_dtype=pl.String)
    .alias("pv_net_cf"),
)

# ---------------------------------------------------------------------------
# Key findings (auto-generated)
# ---------------------------------------------------------------------------

findings: list[str] = []

# 1D sweep: linearity / convexity check
base_pv = sweep_df.filter(pl.col("mortality_factor") == 1.0)["pv_net_cf"][0]
low_pv = sweep_df.filter(pl.col("mortality_factor") == 0.8)["pv_net_cf"][0]
high_pv = sweep_df.filter(pl.col("mortality_factor") == 1.4)["pv_net_cf"][0]

# Check for convexity: if the midpoint (1.0) differs from the average of
# endpoints, there is curvature.
midpoint_avg = (low_pv + high_pv) / 2.0
convexity = abs(base_pv - midpoint_avg) / abs(base_pv) * 100

if convexity < 1.0:
    findings.append(
        f"The mortality sensitivity curve is approximately **linear** "
        f"(midpoint deviation {convexity:.2f}%)."
    )
else:
    findings.append(
        f"The mortality sensitivity curve shows **convexity** "
        f"(midpoint deviation {convexity:.2f}% from the average of endpoints)."
    )

# Range of impact
pv_range = high_pv - low_pv
pv_range_pct = pv_range / abs(base_pv) * 100
findings.append(
    f"Varying mortality from 0.8x to 1.4x changes PV net CF by "
    f"{charts.format_number(pv_range)} ({pv_range_pct:+.1f}% of base)."
)

# 2D interaction effects
# Compare the combined shock to the sum of individual effects
base_grid = grid_df.filter(
    (pl.col("mortality_factor") == 1.0) & (pl.col("lapse_factor") == 1.0)
)["pv_net_cf"][0]

mort_only = grid_df.filter(
    (pl.col("mortality_factor") == 1.2) & (pl.col("lapse_factor") == 1.0)
)["pv_net_cf"][0]

lapse_only = grid_df.filter(
    (pl.col("mortality_factor") == 1.0) & (pl.col("lapse_factor") == 1.2)
)["pv_net_cf"][0]

both = grid_df.filter(
    (pl.col("mortality_factor") == 1.2) & (pl.col("lapse_factor") == 1.2)
)["pv_net_cf"][0]

# Interaction = combined effect - (sum of individual effects)
individual_sum = (mort_only - base_grid) + (lapse_only - base_grid)
combined_effect = both - base_grid
interaction = combined_effect - individual_sum

if abs(interaction) > 0.01 * abs(base_grid):
    interaction_pct = interaction / abs(base_grid) * 100
    findings.append(
        f"Mortality and lapse shocks show a **non-trivial interaction** effect "
        f"({interaction_pct:+.2f}% of base). The combined impact differs from "
        f"the sum of individual effects."
    )
else:
    findings.append(
        "Mortality and lapse shocks are approximately **additive** -- "
        "the combined impact is close to the sum of individual effects."
    )

# Which dimension dominates?
mort_effect = abs(mort_only - base_grid)
lapse_effect = abs(lapse_only - base_grid)

if mort_effect > lapse_effect * 1.5:
    findings.append(
        "Mortality shocks have a **larger impact** on PV net CF than lapse shocks "
        "at the same shock magnitude."
    )
elif lapse_effect > mort_effect * 1.5:
    findings.append(
        "Lapse shocks have a **larger impact** on PV net CF than mortality shocks "
        "at the same shock magnitude."
    )
else:
    findings.append(
        "Mortality and lapse shocks have **similar magnitudes** of impact on PV net CF."
    )

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

report_path = charts.write_report(
    path=SCRIPT_DIR,
    title="Sensitivity Analysis",
    metadata={
        "points": n_points,
        "scenarios": len(mort_scenarios) + len(grid_scenarios),
        "runtime_s": total_time,
    },
    sections=[
        {
            "heading": "Overview",
            "content": (
                "This step demonstrates systematic parameter sweeps using gaspatchio's "
                "scenario API:\n\n"
                "1. **1D sweep** -- `sensitivity_analysis()` generates multiplicative "
                "shocks for mortality from 0.8x to 1.4x (7 data points plus base).\n"
                "2. **2D sweep** -- A manual cross-product of mortality (0.8, 1.0, 1.2) "
                "and lapse (0.8, 1.0, 1.2) factors produces a 3x3 grid.\n\n"
                "No `scenarios.json` file is needed -- all scenarios are built "
                "programmatically with `sensitivity_analysis()` and "
                "`parse_scenario_config()`."
            ),
        },
        {
            "heading": "Scenario Parameters",
            "content": (
                "```python\n"
                "# 1D sweep: mortality factor\n"
                f"MORT_SWEEP_VALUES = {MORT_SWEEP_VALUES!r}\n"
                "\n"
                "mort_scenarios = sensitivity_analysis(\n"
                '    table="mortality_select",\n'
                '    shock_type="multiplicative",\n'
                "    values=MORT_SWEEP_VALUES,\n"
                ")\n"
                "\n"
                "# 2D sweep: mortality x lapse grid\n"
                f"MORT_GRID_VALUES = {MORT_GRID_VALUES!r}\n"
                f"LAPSE_GRID_VALUES = {LAPSE_GRID_VALUES!r}\n"
                "# Cross-product: 3 x 3 = 9 scenarios\n"
                "```"
            ),
        },
        {
            "heading": "1D Mortality Sweep",
            "table": sweep_display,
        },
        {
            "heading": "Sensitivity Curve",
            "chart": "sensitivity_mortality.png",
        },
        {
            "heading": "2D Mortality x Lapse Grid",
            "table": grid_display,
        },
        {
            "heading": "Interaction Heatmap",
            "chart": "heatmap_interaction.png",
        },
        {
            "heading": "Key Findings",
            "findings": findings,
        },
    ],
)

print(f"Report generated in {total_time:.2f}s -> {report_path}")
