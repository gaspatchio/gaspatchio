# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Typed Base: Interest Rate Scenarios (BASE / UP / DOWN)

Three interest-rate scenarios run through the typed L5 mini-VA model. The plan
is captured as a :class:`ScenarioRun` — the typed, hashable default for
scenario work. ``.run()`` cross-joins the model points with the scenarios,
hands each batch to the model, and folds the requested aggregations into one
row per scenario. The headline is the per-scenario PV comparison: BASE vs UP
vs DOWN.

What this demonstrates
----------------------

  * ``ScenarioRun`` — the typed scenario plan, and the default for scenario
    work. Even when the per-scenario variation is a rate curve rather than a
    table shock, the plan still carries the scenario ids, the base tables (for
    the audit SHA), and the aggregations to read out of each scenario.

  * Rate scenarios live *inside* the model. ``model.main()`` holds three
    ``Curve`` instances (BASE / UP / DOWN zero curves) and dispatches the
    right one per row on the ``scenario_id`` column that ``ScenarioRun``
    cross-joins onto the frame. No table is shocked here — the scenario shock
    lists are empty — so this is a pure rate-curve sweep.

  * Mergeable aggregators — ``Sum(...).alias(...).over("scenario_id")`` fold
    the portfolio into one summed row per scenario. Reading off a portfolio
    aggregate is exactly what ``ScenarioRun`` is for; you never materialise
    the per-policy grid for the headline numbers.

``with_scenarios()`` is the lower-level primitive underneath — ``ScenarioRun``
cross-joins via it internally. Reach for ``with_scenarios`` directly only when
you want the raw expanded frame without the typed plan / aggregations.

Per-policy detail (the debugging view) is intentionally not printed here — run
a single policy through the model when you need it::

    uv run gspio run-single-policy model.py model_points.parquet 1

``model.py``'s own ``__main__`` also prints the reconciled per-policy BASE
block against ``expected_output.txt``.

Usage::

    cd tutorial/level-5-scenarios/base
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

from gaspatchio_core import ActuarialFrame, MortalityTable, ScenarioRun
from gaspatchio_core.scenarios import Sum

import model

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_POINTS_PATH = SCRIPT_DIR / "model_points.parquet"

# The three rate scenarios. Shock lists are empty: the per-scenario variation
# is the discount curve, which model.main() selects internally on scenario_id.
SCENARIOS: dict[str, list] = {
    "BASE": [],
    "UP": [],
    "DOWN": [],
}

PV_COMPONENTS = [
    "pv_net_cf",
    "pv_claims",
    "pv_expenses",
    "pv_inv_income",
    "pv_premiums",
    "pv_commissions",
    "pv_av_change",
]

# ---------------------------------------------------------------------------
# 1. Load assumptions once. Carry the raw Tables for the plan's audit identity.
# ---------------------------------------------------------------------------

assumptions = model.load_assumptions()
SELECT_PERIOD = model.SELECT_PERIOD_LEN

# MortalityTable wraps a raw Table; the plan tracks the raw Table.
mortality_select_raw = assumptions["mortality"].table

BASE_TABLES = {
    "mortality_select": mortality_select_raw,
    "mortality_scalars": assumptions["mortality_scalars"],
    "lapse_rates": assumptions["lapse_rates"],
    "surrender_charges": assumptions["surrender_charges"],
}


# ---------------------------------------------------------------------------
# 2. Model wrapper. No tables are shocked here, so the model runs on its own
#    typed assumptions; the scenario_id column drives Curve dispatch inside
#    model.main(). Re-wrap mortality so select/ultimate dispatch still works.
# ---------------------------------------------------------------------------


def model_fn(af: ActuarialFrame, *, tables: dict, drivers: dict) -> ActuarialFrame:
    """Run the typed L5 model for one batch of scenarios."""
    del drivers  # rate scenarios carry no per-scenario drivers
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
# 3. Aggregations: one row per scenario, summed PVs across the portfolio.
# ---------------------------------------------------------------------------

# ``.over("scenario_id")`` partitions each aggregation per scenario so each
# alias returns a DataFrame keyed by scenario_id (one row per scenario).
AGGREGATIONS = tuple(
    Sum(component).alias(component).over("scenario_id") for component in PV_COMPONENTS
)

# ---------------------------------------------------------------------------
# 4. Build the plan and run.
# ---------------------------------------------------------------------------

plan = ScenarioRun(
    shocks=SCENARIOS,
    base_tables=BASE_TABLES,
    aggregations=AGGREGATIONS,
)

print(plan.describe())
print()

mp = pl.read_parquet(MODEL_POINTS_PATH)
n_points = len(mp)
af = ActuarialFrame(mp)

start = time.perf_counter()
result = plan.run(af, model_fn)
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# 5. Results — per-scenario PV totals (BASE vs UP vs DOWN)
# ---------------------------------------------------------------------------

print(
    f"\nTyped L5 run: {n_points} model points x {len(SCENARIOS)} scenarios = "
    f"{n_points * len(SCENARIOS)} rows"
)
print(f"Runtime: {runtime:.2f}s\n")

# Per-scenario totals — join the per-scenario aggregator outputs on scenario_id.
scenario_totals = result.aggregations[PV_COMPONENTS[0]]
for name in PV_COMPONENTS[1:]:
    scenario_totals = scenario_totals.join(result.aggregations[name], on="scenario_id")

print("=== Per-Scenario Totals (PV by component) ===")
print(scenario_totals.sort("scenario_id"))
