# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 02: Conditional Shocks

Step 01 applied flat shocks ("mortality up 20% everywhere"). Real stress
scenarios are usually targeted: "elderly lives only", "early policy years
only", "Solvency-II lapse-up with the 100% cap". This step demonstrates
three composable shock types that express those targeted stresses
declaratively.

The shock vocabulary
--------------------

  * ``FilteredShock``  — shock applies only to rows matching a WHERE clause.
                         e.g. "mortality up 25% for attained_age ≥ 65"

  * ``TimeConditionalShock`` — shock applies only during specified
                         projection periods. e.g. "10% expense overrun in
                         the first five years". Targets a time column on
                         the base table (here ``duration``).

  * ``PipelineShock``  — chain operations left-to-right. e.g. Solvency II
                         lapse-up: multiply by 1.5, then clip at 100%.

The five scenarios
------------------

  BASE                   — no shocks
  ELDERLY_MORT_UP_25     — FilteredShock on mortality_select, age ≥ 65
  EARLY_LAPSE_UP_25      — FilteredShock on lapse_rates, duration ≤ 3
  EARLY_EXPENSE_UP_10    — TimeConditionalShock on surrender_charges,
                           duration ≤ 5  (proxy for a first-five-years
                           expense overrun)
  SOLVENCY_II_LAPSE_UP   — PipelineShock on lapse_rates: ×1.5 then clip 1.0

Run::

    cd tutorial/level-5-scenarios/steps/02-conditional-shocks
    uv run python run_scenarios.py
"""

import sys
import time
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame, MortalityTable
from gaspatchio_core.scenarios import (
    ClipShock,
    FilteredShock,
    MultiplicativeShock,
    PipelineShock,
    ScenarioRun,
    Sum,
    TimeConditionalShock,
)

SCRIPT_DIR = Path(__file__).resolve().parent
L5_BASE_DIR = SCRIPT_DIR.parent.parent / "base"
sys.path.insert(0, str(L5_BASE_DIR))
import model  # noqa: E402

MODEL_POINTS_PATH = L5_BASE_DIR / "model_points.parquet"
SELECT_PERIOD = model.SELECT_PERIOD_LEN

# ---------------------------------------------------------------------------
# 1. Load base assumptions once.
# ---------------------------------------------------------------------------

assumptions = model.load_assumptions()
mortality_select_raw = assumptions["mortality"].table

BASE_TABLES = {
    "mortality_select": mortality_select_raw,
    "mortality_scalars": assumptions["mortality_scalars"],
    "lapse_rates": assumptions["lapse_rates"],
    "surrender_charges": assumptions["surrender_charges"],
}

# ---------------------------------------------------------------------------
# 2. Conditional shock specifications.
# ---------------------------------------------------------------------------

SHOCKS = {
    "BASE": [],
    "ELDERLY_MORT_UP_25": [
        FilteredShock(
            shock=MultiplicativeShock(factor=1.25),
            where={"age": {"gte": 65}},
            table="mortality_select",
        ),
    ],
    "EARLY_LAPSE_UP_25": [
        FilteredShock(
            shock=MultiplicativeShock(factor=1.25),
            where={"duration": {"lte": 3}},
            table="lapse_rates",
        ),
    ],
    "EARLY_EXPENSE_UP_10": [
        TimeConditionalShock(
            shock=MultiplicativeShock(factor=1.10),
            when={"duration": {"lte": 5}},
            table="surrender_charges",
            time_column="duration",
        ),
    ],
    "SOLVENCY_II_LAPSE_UP": [
        PipelineShock(
            shocks=(
                MultiplicativeShock(factor=1.5),
                ClipShock(max_value=1.0),
            ),
            table="lapse_rates",
        ),
    ],
}

# ---------------------------------------------------------------------------
# 3. Aggregations — same per-scenario PV roll-up as step 01.
# ---------------------------------------------------------------------------

AGGREGATIONS = (
    Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),
    Sum("pv_claims").alias("pv_claims").over("scenario_id"),
    Sum("pv_expenses").alias("pv_expenses").over("scenario_id"),
)

# ---------------------------------------------------------------------------
# 4. Model wrapper (identical adapter as step 01).
# ---------------------------------------------------------------------------


def model_fn(af: ActuarialFrame, *, tables: dict, drivers: dict) -> ActuarialFrame:
    """Rebuild typed assumptions dict from shocked base tables, then run."""
    del drivers
    overrides = dict(assumptions)
    overrides["mortality"] = MortalityTable(
        table=tables["mortality_select"],
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=SELECT_PERIOD,
    )
    overrides["mortality_scalars"] = tables["mortality_scalars"]
    overrides["lapse_rates"] = tables["lapse_rates"]
    overrides["surrender_charges"] = tables["surrender_charges"]
    return model.main(af, assumptions_override=overrides)


# ---------------------------------------------------------------------------
# 5. Run.
# ---------------------------------------------------------------------------

plan = ScenarioRun(
    shocks=SHOCKS,
    base_tables=BASE_TABLES,
    aggregations=AGGREGATIONS,
)

print(plan.describe())
print()

mp = pl.read_parquet(MODEL_POINTS_PATH)
af = ActuarialFrame(mp)

start = time.perf_counter()
result = plan.run(af, model_fn, audit=True)
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------

print(f"Runtime: {runtime:.2f}s")
print(f"Audit sidecar: {result.audit_path}")
print()

pv_components = ["pv_net_cf", "pv_claims", "pv_expenses"]
scenario_table = result.aggregations[pv_components[0]]
for name in pv_components[1:]:
    scenario_table = scenario_table.join(result.aggregations[name], on="scenario_id")
scenario_table = scenario_table.sort("scenario_id")

print("=== Per-Scenario PV Aggregates ===")
print(scenario_table)
print()

base_pv = scenario_table.filter(pl.col("scenario_id") == "BASE").get_column("pv_net_cf").item()

deltas = (
    scenario_table.filter(pl.col("scenario_id") != "BASE")
    .with_columns(
        (pl.col("pv_net_cf") - base_pv).alias("delta"),
        ((pl.col("pv_net_cf") - base_pv) / abs(base_pv) * 100).alias("delta_pct"),
    )
    .sort("delta")
    .select(["scenario_id", "delta", "delta_pct"])
)

print("=== Δ pv_net_cf vs BASE — by stress kind ===")
print(deltas)
