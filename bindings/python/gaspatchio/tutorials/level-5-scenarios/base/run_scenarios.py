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
    table shock, the plan still carries the scenario ids and the aggregations
    to read out of each scenario. ``.run(af, model.main)`` runs the model you
    reconciled as it is: no wrapper, no override, no scenario guard.

  * Rate scenarios live *inside* the model. ``model.main()`` holds three
    ``Curve`` instances (BASE / UP / DOWN zero curves), reads each on the
    frame with ``curve.discount_factor(af.t_years)``, and picks the right one
    per row on the ``scenario_id`` column that ``ScenarioRun`` cross-joins
    onto the frame. Reading the curves on the frame is what puts them in the
    model's exported graph artifact — three assumption entries here, one per
    curve, each carrying its knots and their digest — so the record names the
    three term structures this sweep discounted on rather than only the tables
    it shocked. No table is shocked here — the scenario shock lists are empty
    — so this is a pure rate-curve sweep.

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

The plan is declared at module level as ``SCENARIO_RUN``, with ``MODEL_FN``
beside it, and the sweep itself sits under ``__main__``. That is what lets
the same file be a script you run and a plan the exporter runs::

    uv run gspio calc-graph model.py model_points.parquet \
        --scenarios run_scenarios.py -o level5.json

which writes a calculation graph of the cross-joined run: every entry of the
policy axis naming its scenario, one assumption entry per rate curve, and
the plan's own per-scenario totals as the folds at the head of that axis.

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

from gaspatchio import ActuarialFrame, ScenarioRun
from gaspatchio.scenarios import Sum

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
# 1. The model. ``model.main`` is the reconciled model, run as it is: it loads
#    its own assumptions, and the scenario_id column the plan cross-joins onto
#    the frame drives its Curve dispatch. Nothing wraps it.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 2. Aggregations: one row per scenario, summed PVs across the portfolio.
# ---------------------------------------------------------------------------

# ``.over("scenario_id")`` partitions each aggregation per scenario so each
# alias returns a DataFrame keyed by scenario_id (one row per scenario).
AGGREGATIONS = tuple(
    Sum(component).alias(component).over("scenario_id") for component in PV_COMPONENTS
)

# ---------------------------------------------------------------------------
# 3. Build the plan and run.
# ---------------------------------------------------------------------------

# ``SCENARIO_RUN`` and ``MODEL_FN`` are the two names ``gspio calc-graph
# --scenarios`` reads out of this file, the way ``--portfolio`` reads a
# model's ``AGGREGATIONS``. The script declares; the exporter reads. Run
# this file and it does its own sweep; point the exporter at it and the
# same plan is run once and written up as a calculation graph::
#
#     uv run gspio calc-graph model.py model_points.parquet \
#         --scenarios run_scenarios.py -o level5.json
SCENARIO_RUN = ScenarioRun(
    shocks=SCENARIOS,
    aggregations=AGGREGATIONS,
)
MODEL_FN = model.main


# ---------------------------------------------------------------------------
# 4. Run it, and print the per-scenario PV totals (BASE vs UP vs DOWN).
# ---------------------------------------------------------------------------
#
# Under ``__main__`` so that reading this file for its declarations does not
# run the sweep. The exporter imports the script to reach SCENARIO_RUN, and
# anything left at module level here would run before the export started —
# the same numbers, twice, for nobody.


def main() -> None:
    """Run the plan and print the per-scenario totals."""
    print(SCENARIO_RUN.describe())
    print()

    mp = pl.read_parquet(MODEL_POINTS_PATH)
    n_points = len(mp)
    af = ActuarialFrame(mp)

    start = time.perf_counter()
    result = SCENARIO_RUN.run(af, MODEL_FN)
    runtime = time.perf_counter() - start

    print(
        f"\nTyped L5 run: {n_points} model points x {len(SCENARIOS)} scenarios = "
        f"{n_points * len(SCENARIOS)} rows"
    )
    print(f"Runtime: {runtime:.2f}s\n")

    # Per-scenario totals — join the per-scenario aggregator outputs on scenario_id.
    scenario_totals = result.aggregations[PV_COMPONENTS[0]]
    for name in PV_COMPONENTS[1:]:
        scenario_totals = scenario_totals.join(
            result.aggregations[name], on="scenario_id"
        )

    print("=== Per-Scenario Totals (PV by component) ===")
    print(scenario_totals.sort("scenario_id"))


if __name__ == "__main__":
    main()
