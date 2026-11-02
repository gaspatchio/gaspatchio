# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 01: Parameter Shocks via ScenarioRun

Five scenarios — a base case plus four single-driver stresses — run through
the L5 mini-VA model. The plan is captured as a ``ScenarioRun``: the shocks
and the aggregations to read out of each scenario. ``.run(af, model.main)``
cross-joins the model points with the scenarios, runs the model you
reconciled unchanged, and answers the model's own reads of each table a
shock names with that table shocked for each scenario.

What this demonstrates
----------------------

  * ``ScenarioRun`` — a typed, hashable plan you can serialise, replay, and
    log alongside your results. The SHA of the plan changes if any shock
    changes; identical plans produce identical SHAs.

  * ``MultiplicativeShock`` — the workhorse stress: "mortality up 20%",
    "lapse down 20%". Targets a table by the name its ``Table`` was built
    with in ``model.load_assumptions()``. A scalar the model reads off each
    policy is shocked the same way with ``column=`` (``AdditiveShock(0.01,
    column="valuation_rate")``).

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

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import (
    MultiplicativeShock,
    ScenarioRun,
    Sum,
)

SCRIPT_DIR = Path(__file__).resolve().parent
L5_BASE_DIR = SCRIPT_DIR.parent.parent / "base"
sys.path.insert(0, str(L5_BASE_DIR))
import model  # noqa: E402 — sys.path manipulation must precede

MODEL_POINTS_PATH = L5_BASE_DIR / "model_points.parquet"

# ---------------------------------------------------------------------------
# 1. Define the five scenarios as shock specs. Each names a table the
#    model builds, by the name it is built with.
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
# 2. Aggregations: one row per scenario, summed PVs across the portfolio.
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
# 3. Build the plan and run the model as it is.
# ---------------------------------------------------------------------------

plan = ScenarioRun(
    shocks=SHOCKS,
    aggregations=AGGREGATIONS,
)

print(plan.describe())
print()

mp = pl.read_parquet(MODEL_POINTS_PATH)
af = ActuarialFrame(mp)

start = time.perf_counter()
result = plan.run(af, model.main, audit=True)
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# 4. Results — table + tornado chart prep
# ---------------------------------------------------------------------------

print(f"Runtime: {runtime:.2f}s")
print(f"Audit sidecar: {result.audit_path}")
print()

# Each alias is a per-scenario DataFrame keyed by scenario_id. Join them
# on scenario_id to produce one row per scenario with all PV components.
pv_components = [
    "pv_net_cf",
    "pv_claims",
    "pv_premiums",
    "pv_expenses",
    "pv_commissions",
]
scenario_table = result.aggregations[pv_components[0]]
for name in pv_components[1:]:
    scenario_table = scenario_table.join(result.aggregations[name], on="scenario_id")
scenario_table = scenario_table.sort("scenario_id")

print("=== Per-Scenario PV Aggregates ===")
print(scenario_table)
print()

# Tornado data: delta vs BASE for pv_net_cf
base_pv = (
    scenario_table.filter(pl.col("scenario_id") == "BASE")
    .get_column("pv_net_cf")
    .item()
)

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
