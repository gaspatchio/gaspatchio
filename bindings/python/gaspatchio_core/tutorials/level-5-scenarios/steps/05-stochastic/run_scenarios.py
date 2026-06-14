# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 05: Stochastic Monte Carlo via `master_seed`

Steps 01-04 ran deterministic scenarios — every shock value was chosen by
the actuary. Real-economy capital calcs (Solvency II SCR at 99.5%, IFRS 17
risk adjustment, ORSA) need stochastic scenarios: draws from a distribution
across hundreds or thousands of paths, with tail aggregators (`CTE`,
`Quantile`) reducing to a single capital figure.

The same `ScenarioRun` plan handles this. The only addition is
``master_seed=42``: a deterministic 32-bit per-scenario seed gets derived
via SHA-256 from `(master_seed, scenario_id)` and injected as
``drivers['rng_seed']``. Same `master_seed` + same scenario_ids → same
seeds → same draws → same SHA → byte-identical results across processes.

Demonstration in this step
--------------------------

200 stochastic scenarios named ``S0000..S0199``. Each one draws a per-period
mortality shock from a log-normal distribution (μ=0, σ=0.15) and runs the
L5 model against the shocked mortality table. Aggregators:

  * ``CTE("pv_net_cf", level=0.005, direction="lower")`` — 99.5% adverse
    tail (the SCR-shape capital figure for a positive-is-profit column).
  * ``Quantile("pv_net_cf", levels=(0.05, 0.50, 0.95))`` — best estimate
    + tail percentiles.
  * ``Mean("pv_net_cf")``, ``Std("pv_net_cf")`` — central + dispersion.

Reproducibility check
---------------------

Two runs of the same plan against the same model points produce identical
plan SHAs (the plan content didn't change) AND identical aggregate values
(``master_seed`` makes the draws deterministic). Change ``master_seed`` →
SHA changes → draws change → aggregates change.

Run::

    cd tutorial/level-5-scenarios/steps/05-stochastic
    uv run python run_scenarios.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from gaspatchio_core import ActuarialFrame, MortalityTable
from gaspatchio_core.assumptions import Table
from gaspatchio_core.scenarios import (
    CTE,
    Mean,
    Quantile,
    ScenarioRun,
    Std,
)

SCRIPT_DIR = Path(__file__).resolve().parent
L5_BASE_DIR = SCRIPT_DIR.parent.parent / "base"
sys.path.insert(0, str(L5_BASE_DIR))
import model  # noqa: E402

MODEL_POINTS_PATH = L5_BASE_DIR / "model_points.parquet"
SELECT_PERIOD = model.SELECT_PERIOD_LEN
N_SCENARIOS = 200
MASTER_SEED = 42

# ---------------------------------------------------------------------------
# 1. Load assumptions; we'll override mortality per scenario via the RNG.
# ---------------------------------------------------------------------------

assumptions = model.load_assumptions()
mortality_select_raw = assumptions["mortality"].table
# Materialised source view we'll multiply per scenario. Each scenario builds a
# fresh Table around this — the base mortality_select remains untouched.
mortality_source = mortality_select_raw.to_dataframe()

# ---------------------------------------------------------------------------
# 2. Plan — 200 scenarios, no shocks dict (RNG drives the variation instead).
#    Each scenario gets a unique seed from drivers['rng_seed'].
# ---------------------------------------------------------------------------

SCENARIOS = [f"S{i:04d}" for i in range(N_SCENARIOS)]

# We use the "drivers" shape — empty driver dict per scenario; master_seed
# does the work of differentiating scenarios via the rng_seed injection.
DRIVERS: dict = {sid: {} for sid in SCENARIOS}

AGGREGATIONS = (
    CTE("pv_net_cf", level=0.005, direction="lower").alias("scr_995"),
    Quantile("pv_net_cf", levels=(0.05, 0.50, 0.95)).alias("quantiles"),
    Mean("pv_net_cf").alias("mean_pv"),
    Std("pv_net_cf").alias("std_pv"),
)

# ---------------------------------------------------------------------------
# 3. Model wrapper — uses drivers['rng_seed'] to make a stochastic mortality
#    table on every scenario.
# ---------------------------------------------------------------------------


def model_fn(af: ActuarialFrame, *, tables: dict, drivers: dict) -> ActuarialFrame:
    """Draw a log-normal mortality multiplier; wrap into a fresh MortalityTable."""
    del tables  # plan has no shocks; base tables flow through unchanged
    rng = np.random.default_rng(drivers["rng_seed"])

    # Log-normal multiplier — mean ~1.0, σ=0.15 — applied uniformly across age/duration.
    mortality_mult = float(rng.lognormal(mean=0.0, sigma=0.15))
    shocked_source = mortality_source.with_columns(
        (pl.col("mort_rate") * mortality_mult).alias("mort_rate"),
    )
    shocked_table = Table(
        name="mortality_select_stochastic",
        source=shocked_source,
        dimensions={
            "table_id": "table_id",
            "age": "age",
            "duration": "duration",
        },
        value="mort_rate",
    )
    overrides = dict(assumptions)
    overrides["mortality"] = MortalityTable(
        table=shocked_table,
        age_basis="age_last_birthday",
        structure="select_ultimate",
        select_period=SELECT_PERIOD,
    )
    return model.main(af, assumptions_override=overrides)


# ---------------------------------------------------------------------------
# 4. Build the plan + run.
# ---------------------------------------------------------------------------

plan = ScenarioRun(
    shocks={sid: [] for sid in SCENARIOS},
    base_tables={},  # no shock-stacked tables; stochastic variation comes via rng_seed
    aggregations=AGGREGATIONS,
    master_seed=MASTER_SEED,
)

print(f"Plan SHA: {plan.source_sha()}")
print(f"Master seed: {MASTER_SEED}  |  Scenarios: {N_SCENARIOS}")
print()

mp = pl.read_parquet(MODEL_POINTS_PATH)
af = ActuarialFrame(mp)

start = time.perf_counter()
# batch_size=1 is mandatory when master_seed is set — the rng_seed is
# injected per scenario, not per batch.
result = plan.run(af, model_fn, batch_size=1, audit=True)
runtime = time.perf_counter() - start

# ---------------------------------------------------------------------------
# 5. Capital figures.
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
# 6. Reproducibility check — same plan, same SHA, same numbers.
# ---------------------------------------------------------------------------

print("=== Reproducibility: re-running with the same plan ===")
result2 = plan.run(af, model_fn, batch_size=1)
assert result2.plan_sha == result.plan_sha, "plan SHA drifted"
assert result2.aggregations["scr_995"] == result.aggregations["scr_995"], "SCR drifted"
assert result2.aggregations["mean_pv"] == result.aggregations["mean_pv"], "mean drifted"
print(f"  Same plan SHA   : {result2.plan_sha}")
print(f"  Same SCR        : {result2.aggregations['scr_995']:,.0f}")
print(f"  Same mean       : {result2.aggregations['mean_pv']:,.0f}")
print()
print("Reproducibility verified — same master_seed gives identical aggregates.")
print()
print("=== What changing master_seed does ===")
plan_b = ScenarioRun(
    shocks={sid: [] for sid in SCENARIOS},
    base_tables={},
    aggregations=AGGREGATIONS,
    master_seed=MASTER_SEED + 1,  # different seed
)
result_b = plan_b.run(af, model_fn, batch_size=1)
print(f"  Different SHA    : {plan_b.source_sha()}")
print(f"  Different SCR    : {result_b.aggregations['scr_995']:,.0f}")
print(f"  Different mean   : {result_b.aggregations['mean_pv']:,.0f}")
