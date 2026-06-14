# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 03: Sensitivity Sweeps

A sensitivity sweep is just a list of scenarios where one driver varies
across a range. There is no special helper for this — you build the
``shocks`` dict with a list comprehension, hand it to ``ScenarioRun``,
and the loop runs them all. Two patterns are shown here:

  * **1D sweep** — vary mortality multiplier across 0.8, 0.9, 1.0, 1.1, 1.2.
    Result: one number per multiplier — the response curve.

  * **2D sweep** — vary mortality AND lapse simultaneously over the same
    grid. Result: a 5×5 surface of interactions, suitable for a heatmap.

The 1D version generates 5 scenarios; the 2D version generates 25
(``itertools.product``). Both runs share the L5 model and the bounded-
memory ``for_each_scenario`` loop, so the cost scales linearly with the
number of scenarios.

Run::

    cd tutorial/level-5-scenarios/steps/03-sensitivity
    uv run python run_scenarios.py
"""

import itertools
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
import model  # noqa: E402

MODEL_POINTS_PATH = L5_BASE_DIR / "model_points.parquet"
SELECT_PERIOD = model.SELECT_PERIOD_LEN

# ---------------------------------------------------------------------------
# 1. Base tables + model wrapper (identical to step 01/02).
# ---------------------------------------------------------------------------

assumptions = model.load_assumptions()
mortality_select_raw = assumptions["mortality"].table

BASE_TABLES = {
    "mortality_select": mortality_select_raw,
    "lapse_rates": assumptions["lapse_rates"],
}


def model_fn(af: ActuarialFrame, *, tables: dict, drivers: dict) -> ActuarialFrame:
    """Plan-agnostic adapter: override whichever tables the current plan supplies."""
    del drivers
    overrides = dict(assumptions)
    if "mortality_select" in tables:
        overrides["mortality"] = MortalityTable(
            table=tables["mortality_select"],
            age_basis="age_last_birthday",
            structure="select_ultimate",
            select_period=SELECT_PERIOD,
        )
    for name in ("mortality_scalars", "lapse_rates", "surrender_charges"):
        if name in tables:
            overrides[name] = tables[name]
    return model.main(af, assumptions_override=overrides)


# ---------------------------------------------------------------------------
# 2. 1D sweep — mortality multiplier across a range.
# ---------------------------------------------------------------------------

MORT_VALUES = [0.8, 0.9, 1.0, 1.1, 1.2]


def mort_sweep_id(mult: float) -> str:
    return f"MORT_x{mult:.2f}"


sweep_1d_shocks = {
    mort_sweep_id(m): (
        [MultiplicativeShock(factor=m, table="mortality_select")] if m != 1.0 else []
    )
    for m in MORT_VALUES
}

plan_1d = ScenarioRun(
    shocks=sweep_1d_shocks,
    base_tables={"mortality_select": mortality_select_raw},
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)

print("=== 1D Sweep: mortality multiplier ===")
print(plan_1d.describe())

mp = pl.read_parquet(MODEL_POINTS_PATH)
af = ActuarialFrame(mp)

start = time.perf_counter()
result_1d = plan_1d.run(af, model_fn, audit=True)
runtime_1d = time.perf_counter() - start

curve_1d = (
    result_1d.aggregations["pv_net_cf"]
    .with_columns(
        pl.col("scenario_id")
        .str.replace("MORT_x", "")
        .cast(pl.Float64)
        .alias("mortality_mult")
    )
    .sort("mortality_mult")
    .select(["mortality_mult", "pv_net_cf"])
)

print(f"\nRuntime: {runtime_1d:.2f}s")
print(curve_1d)
print()

# ---------------------------------------------------------------------------
# 3. 2D sweep — mortality × lapse interaction grid.
# ---------------------------------------------------------------------------

LAPSE_VALUES = [0.8, 0.9, 1.0, 1.1, 1.2]


def grid_id(mort: float, lapse: float) -> str:
    return f"M{mort:.2f}_L{lapse:.2f}"


sweep_2d_shocks = {}
for m, lap in itertools.product(MORT_VALUES, LAPSE_VALUES):
    shocks: list = []
    if m != 1.0:
        shocks.append(MultiplicativeShock(factor=m, table="mortality_select"))
    if lap != 1.0:
        shocks.append(MultiplicativeShock(factor=lap, table="lapse_rates"))
    sweep_2d_shocks[grid_id(m, lap)] = shocks

plan_2d = ScenarioRun(
    shocks=sweep_2d_shocks,
    base_tables=BASE_TABLES,
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)

print("=== 2D Sweep: mortality × lapse (25 cells) ===")
print(plan_2d.describe())

start = time.perf_counter()
result_2d = plan_2d.run(af, model_fn, audit=True)
runtime_2d = time.perf_counter() - start

# scenario_id format is "M{mort:.2f}_L{lapse:.2f}" — split on '_' then strip the prefix.
heatmap = (
    result_2d.aggregations["pv_net_cf"]
    .with_columns(
        pl.col("scenario_id")
        .str.split("_")
        .list.get(0)
        .str.strip_prefix("M")
        .cast(pl.Float64)
        .alias("mortality_mult"),
        pl.col("scenario_id")
        .str.split("_")
        .list.get(1)
        .str.strip_prefix("L")
        .cast(pl.Float64)
        .alias("lapse_mult"),
    )
    .pivot(
        values="pv_net_cf",
        index="mortality_mult",
        on="lapse_mult",
    )
    .sort("mortality_mult")
)

print(f"\nRuntime: {runtime_2d:.2f}s ({len(sweep_2d_shocks)} scenarios)")
print(heatmap)
