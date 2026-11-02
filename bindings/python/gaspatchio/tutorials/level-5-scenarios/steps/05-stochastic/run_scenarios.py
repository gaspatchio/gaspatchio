# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 05: Stochastic Monte Carlo — the draws are the plan

Steps 01-04 ran deterministic scenarios — every shock value was chosen by
the actuary. Real-economy capital calcs (Solvency II SCR at 99.5%, IFRS 17
risk adjustment, ORSA) need stochastic scenarios: draws from a distribution
across hundreds or thousands of paths, with tail aggregators (`CTE`,
`Quantile`) reducing to a single capital figure.

The same `ScenarioRun` plan handles this. Each scenario's draw is made up
front, from one seeded generator, and becomes that scenario's shock: a
log-normal mortality multiplier on ``mortality_select``. So the draws are
part of the plan — its SHA covers every one of them, ``to_yaml`` writes
them down — and the model is the one you reconciled, run unchanged at any
batch size. Same ``MASTER_SEED`` → same draws → same plan SHA → identical
results across processes.

A model that draws its own randomness inside instead reads its seed off the
frame: ``ScenarioRun(..., master_seed=42)`` hands each scenario a
deterministic 32-bit seed as the ``rng_seed`` column, at any batch size.

Demonstration in this step
--------------------------

200 stochastic scenarios named ``S0000..S0199``. Each one draws a mortality
multiplier from a log-normal distribution (μ=0, σ=0.15) and runs the L5
model against mortality shocked by it. Aggregators:

  * ``CTE("pv_net_cf", level=0.005, direction="lower")`` — 99.5% adverse
    tail (the SCR-shape capital figure for a positive-is-profit column).
  * ``Quantile("pv_net_cf", levels=(0.05, 0.50, 0.95))`` — best estimate
    + tail percentiles.
  * ``Mean("pv_net_cf")``, ``Std("pv_net_cf")`` — central + dispersion.

Reproducibility check
---------------------

Two runs of the same plan against the same model points produce identical
plan SHAs (the plan content didn't change) AND identical aggregate values,
bit for bit, whatever batch size each run used.
Change ``MASTER_SEED`` → the draws change → the SHA changes → the
aggregates change.

Run::

    cd tutorial/level-5-scenarios/steps/05-stochastic
    uv run python run_scenarios.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.scenarios import (
    CTE,
    Mean,
    MultiplicativeShock,
    Quantile,
    ScenarioRun,
    Std,
)

SCRIPT_DIR = Path(__file__).resolve().parent
L5_BASE_DIR = SCRIPT_DIR.parent.parent / "base"
sys.path.insert(0, str(L5_BASE_DIR))
import model  # noqa: E402

MODEL_POINTS_PATH = L5_BASE_DIR / "model_points.parquet"
N_SCENARIOS = 200
MASTER_SEED = 42

SCENARIOS = [f"S{i:04d}" for i in range(N_SCENARIOS)]

AGGREGATIONS = (
    CTE("pv_net_cf", level=0.005, direction="lower").alias("scr_995"),
    Quantile("pv_net_cf", levels=(0.05, 0.50, 0.95)).alias("quantiles"),
    Mean("pv_net_cf").alias("mean_pv"),
    Std("pv_net_cf").alias("std_pv"),
)


# ---------------------------------------------------------------------------
# 1. The draws. One seeded generator, one log-normal multiplier per scenario
#    (mean ~1.0, σ=0.15), each written into the plan as that scenario's
#    shock on the mortality table the model builds.
# ---------------------------------------------------------------------------


def stochastic_plan(seed: int) -> ScenarioRun:
    """Return the plan whose scenarios are this seed's mortality draws."""
    rng = np.random.default_rng(seed)
    multipliers = rng.lognormal(mean=0.0, sigma=0.15, size=N_SCENARIOS)
    return ScenarioRun(
        shocks={
            sid: [MultiplicativeShock(factor=float(m), table="mortality_select")]
            for sid, m in zip(SCENARIOS, multipliers, strict=True)
        },
        aggregations=AGGREGATIONS,
    )


plan = stochastic_plan(MASTER_SEED)

print(f"Plan SHA: {plan.source_sha()}")
print(f"Master seed: {MASTER_SEED}  |  Scenarios: {N_SCENARIOS}")
print()

# ---------------------------------------------------------------------------
# 2. Run the model as it is, at whatever batch size the memory search picks.
#    Each scenario is folded on its own rows in the run's order, so every
#    figure below is the same bits at any batch size and on every run.
# ---------------------------------------------------------------------------

mp = pl.read_parquet(MODEL_POINTS_PATH)
af = ActuarialFrame(mp)

start = time.perf_counter()
result = plan.run(af, model.main, audit=True)
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# 3. Capital figures.
# ---------------------------------------------------------------------------

print(f"Runtime: {runtime:.2f}s  ({runtime / N_SCENARIOS * 1000:.1f}ms/scenario)")
print(f"Audit sidecar: {result.audit_path}")
print()
print("=== Capital figures (PV net cashflow across 200 Monte Carlo paths) ===")
print(f"  Mean PV          : {result.aggregations['mean_pv']:>14,.0f}")
print(f"  Std PV           : {result.aggregations['std_pv']:>14,.0f}")
quantiles = result.aggregations["quantiles"]
print(f"  5th percentile   : {quantiles[0.05]:>14,.0f}")
print(f"  Median           : {quantiles[0.5]:>14,.0f}")
print(f"  95th percentile  : {quantiles[0.95]:>14,.0f}")
print(f"  SCR (99.5% CTE)  : {result.aggregations['scr_995']:>14,.0f}")
print()

# ---------------------------------------------------------------------------
# 4. Reproducibility check — same seed, same plan, same SHA, same numbers.
# ---------------------------------------------------------------------------

print("=== Reproducibility: re-drawing with the same seed, at another batch size ===")
result2 = stochastic_plan(MASTER_SEED).run(af, model.main, batch_size=7)
assert result2.plan_sha == result.plan_sha, "plan SHA drifted"
assert result2.aggregations["scr_995"] == result.aggregations["scr_995"], "SCR drifted"
assert result2.aggregations["mean_pv"] == result.aggregations["mean_pv"], "mean drifted"
print(f"  Same plan SHA   : {result2.plan_sha}")
print(f"  Same SCR        : {result2.aggregations['scr_995']:,.0f}")
print(f"  Same mean       : {result2.aggregations['mean_pv']:,.0f}")
print()
print("Reproducibility verified — the same seed draws the same plan.")
print()
print("=== What changing the seed does ===")
plan_b = stochastic_plan(MASTER_SEED + 1)
result_b = plan_b.run(af, model.main)
print(f"  Different SHA    : {plan_b.source_sha()}")
print(f"  Different SCR    : {result_b.aggregations['scr_995']:,.0f}")
print(f"  Different mean   : {result_b.aggregations['mean_pv']:,.0f}")
