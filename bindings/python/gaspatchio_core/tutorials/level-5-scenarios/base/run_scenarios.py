# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Typed Base: Interest Rate Scenarios (BASE / UP / DOWN)

Uses ``with_scenarios()`` to cross-join model points with scenario IDs,
then runs the typed-input model.  Scenario-aware discount-factor dispatch
is handled inside ``model.main()`` via three ``Curve`` instances.

Usage::

    cd tutorial/level-5-scenarios-typed/base
    uv run python run_scenarios.py

Parity note:
    This model uses Curve-based zero-rate discounting, which is the
    mathematically correct approach.  The untyped L5 model uses an
    approximation (current year forward rate applied cumulatively).
    BASE-scenario PV deviations are typically 1.5–4% vs untyped L5.
    See ``model.py`` docstring for a detailed explanation.
"""

import sys
import time
from pathlib import Path

import polars as pl

SCRIPT_DIR = Path(__file__).resolve().parent
# model.py lives in the same directory
sys.path.insert(0, str(SCRIPT_DIR))

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios

import model

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

# 1. Load model points (shared with untyped L5)
mp = pl.read_parquet(MODEL_POINTS_PATH)
n_points = len(mp)

# 2. Expand across scenarios (8 points x 3 scenarios = 24 rows)
af = ActuarialFrame(mp)
af = with_scenarios(af, SCENARIOS)

# 3. Run typed model — scenario_id flows through to Curve dispatch
result_af = model.main(af)
result = result_af.collect()

runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

print(f"\nTyped L5 run: {n_points} model points x {len(SCENARIOS)} scenarios = {n_points * len(SCENARIOS)} rows")
print(f"Runtime: {runtime:.2f}s\n")

# Per-scenario totals
scenario_totals = result.group_by("scenario_id").agg(
    pl.col("pv_net_cf").sum(),
    *[pl.col(c).sum() for c in PV_COMPONENTS],
)

print("=== Per-Scenario Totals ===")
print(scenario_totals.sort("scenario_id"))
print()

# Per-scenario x policy detail (BASE only — matches expected_output.txt format)
base_result = result.filter(pl.col("scenario_id") == "BASE")
up_result = result.filter(pl.col("scenario_id") == "UP")
down_result = result.filter(pl.col("scenario_id") == "DOWN")

print("=== BASE Scenario (per-policy) ===")
print(base_result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"]))
print()

print("=== UP Scenario (per-policy) ===")
print(up_result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"]))
print()

print("=== DOWN Scenario (per-policy) ===")
print(down_result.select(["point_id", "product_id", "plan_id", "pv_net_cf", "pv_claims"]))
