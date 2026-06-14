# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 01: Parameter Shocks via ScenarioRun

Five scenarios — a base case plus four single-driver stresses — run through
the L5 mini-VA model. The plan is captured as a ``ScenarioRun``: shocks,
base tables, and the aggregations to read out of each scenario. The plan
runs via ``.run()`` which cross-joins the model points with scenarios,
applies the shocks to the named base tables, and aggregates per scenario.

What this demonstrates
----------------------

  * ``ScenarioRun`` — a typed, hashable plan you can serialise, replay, and
    log alongside your results. The SHA of the plan changes if any shock
    changes; identical plans produce identical SHAs.

  * ``MultiplicativeShock`` — the workhorse stress: "mortality up 20%",
    "lapse down 20%". Targets a base table by name.

  * Mergeable aggregators — ``Sum.alias("pv_net_cf")`` etc. carry their
    own output column name. Each scenario produces one row of aggregates.

  * Audit sidecar — ``.run(audit=True)`` writes a JSON file capturing the
    plan SHA, model points, runtime, and result alongside the run. The
    same plan re-run produces the same SHA — change detection for free.

The five scenarios
------------------

  BASE                    — no shocks (sanity baseline)
  MORT_UP_20              — mortality_select × 1.2
  LAPSE_DOWN_20           — lapse_rates × 0.8 (sticky policies hurt margin)
  SURR_CHARGES_DOWN_50    — surrender_charges × 0.5 (smaller exit penalty)
  ALL_ADVERSE             — all three combined

Tornado chart ranks the four shocks by absolute impact on pv_net_cf vs BASE.

Run::

    cd tutorial/level-5-scenarios/steps/01-parameter-shocks
    uv run python run_scenarios.py
"""

import sys
import time
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame, MortalityTable
from gaspatchio_core.scenarios import (
    MultiplicativeShock,
    ScenarioRun,
    Sum,
)

SCRIPT_DIR = Path(__file__).resolve().parent
L5_BASE_DIR = SCRIPT_DIR.parent.parent / "base"
sys.path.insert(0, str(L5_BASE_DIR))
import model  # noqa: E402 — sys.path manipulation must precede

MODEL_POINTS_PATH = L5_BASE_DIR / "model_points.parquet"
SELECT_PERIOD = model.SELECT_PERIOD_LEN

# ---------------------------------------------------------------------------
# 1. Load assumptions once. Pull out the raw Tables we'll shock.
# ---------------------------------------------------------------------------

assumptions = model.load_assumptions()

# MortalityTable wraps a raw Table. We shock the raw Table and re-wrap inside
# the model_fn so the actuarial dispatch (select/ultimate) still works.
mortality_select_raw = assumptions["mortality"].table

BASE_TABLES = {
    "mortality_select": mortality_select_raw,
    "mortality_scalars": assumptions["mortality_scalars"],
    "lapse_rates": assumptions["lapse_rates"],
    "surrender_charges": assumptions["surrender_charges"],
}

# ---------------------------------------------------------------------------
# 2. Define the five scenarios as shock specs.
# ---------------------------------------------------------------------------

SHOCKS = {
    "BASE": [],
    "MORT_UP_20": [
        MultiplicativeShock(factor=1.2, table="mortality_select"),
    ],
    "LAPSE_DOWN_20": [
        MultiplicativeShock(factor=0.8, table="lapse_rates"),
    ],
    "SURR_CHARGES_DOWN_50": [
        MultiplicativeShock(factor=0.5, table="surrender_charges"),
    ],
    "ALL_ADVERSE": [
        MultiplicativeShock(factor=1.2, table="mortality_select"),
        MultiplicativeShock(factor=0.8, table="lapse_rates"),
        MultiplicativeShock(factor=0.5, table="surrender_charges"),
    ],
}

# ---------------------------------------------------------------------------
# 3. Aggregations: one row per scenario, summed PVs across the portfolio.
# ---------------------------------------------------------------------------

# ``.over("scenario_id")`` partitions the aggregation per scenario so each
# alias returns a DataFrame keyed by scenario_id (one row per scenario)
# instead of collapsing to a single portfolio-wide scalar.
AGGREGATIONS = (
    Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),
    Sum("pv_claims").alias("pv_claims").over("scenario_id"),
    Sum("pv_premiums").alias("pv_premiums").over("scenario_id"),
    Sum("pv_expenses").alias("pv_expenses").over("scenario_id"),
    Sum("pv_commissions").alias("pv_commissions").over("scenario_id"),
)

# ---------------------------------------------------------------------------
# 4. Model wrapper. Bridges the shocked-Table dict from ScenarioRun into
#    the model's assumptions_override shape (which expects MortalityTable
#    around the raw mortality_select Table).
# ---------------------------------------------------------------------------


def model_fn(af: ActuarialFrame, *, tables: dict, drivers: dict) -> ActuarialFrame:
    """Rebuild the typed assumptions dict from shocked base tables, then run."""
    del drivers  # not used in this step
    overrides = dict(assumptions)  # start from base typed inputs
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
# 5. Build the plan and run.
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
# 6. Results — table + tornado chart prep
# ---------------------------------------------------------------------------

print(f"Runtime: {runtime:.2f}s")
print(f"Audit sidecar: {result.audit_path}")
print()

# Each alias is a per-scenario DataFrame keyed by scenario_id. Join them
# on scenario_id to produce one row per scenario with all PV components.
pv_components = ["pv_net_cf", "pv_claims", "pv_premiums", "pv_expenses", "pv_commissions"]
scenario_table = result.aggregations[pv_components[0]]
for name in pv_components[1:]:
    scenario_table = scenario_table.join(result.aggregations[name], on="scenario_id")
scenario_table = scenario_table.sort("scenario_id")

print("=== Per-Scenario PV Aggregates ===")
print(scenario_table)
print()

# Tornado data: delta vs BASE for pv_net_cf
base_pv = scenario_table.filter(pl.col("scenario_id") == "BASE").get_column("pv_net_cf").item()

deltas = (
    scenario_table.filter(pl.col("scenario_id") != "BASE")
    .with_columns(
        (pl.col("pv_net_cf") - base_pv).alias("delta"),
        ((pl.col("pv_net_cf") - base_pv) / abs(base_pv) * 100).alias("delta_pct"),
    )
    .sort("delta")  # ascending — biggest negative on top of bar chart
    .select(["scenario_id", "delta", "delta_pct"])
)

print("=== Tornado: Δ pv_net_cf vs BASE ===")
print(deltas)
