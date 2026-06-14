# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Level 5 Step 04: Regulatory-Style Comparison with the Audit Chain

A regulatory stress run isn't just "did the numbers move?" — it's "can you
prove which stresses were applied, by whom, against which model, and with
which result?". Gaspatchio gives you three artefacts to do that:

  * ``ScenarioRun.source_sha()`` — a SHA over the plan (shocks +
    base-table identities + aggregations). Same shocks against the same
    tables → same SHA. Different SHA → something in the plan changed.

  * ``ScenarioRun.to_yaml(path)`` — write the recipe (shocks +
    aggregations + master_seed) to a YAML file. ``from_yaml(path,
    base_tables=…)`` reconstructs it. The point: the recipe is portable,
    inspectable, and version-controllable — sit it alongside the
    valuation outputs in your release evidence.

  * ``.run(audit=True)`` — JSON sidecar capturing the plan SHA, model
    points fingerprint, runtime, and the aggregator results. Drop it in
    your audit folder next to the report.

The scenarios in this step are written as named regulatory stresses —
"adverse mortality", "economic downturn", "operational shock" — each
combining multiple per-table shocks. Pattern is the same as Steps 01-02;
the new content is the audit-chain finalisation at the bottom.

Run::

    cd tutorial/level-5-scenarios/steps/04-scenario-comparison
    uv run python run_scenarios.py
"""

import sys
import time
from pathlib import Path

import polars as pl

from gaspatchio_core import ActuarialFrame, MortalityTable
from gaspatchio_core.scenarios import (
    FilteredShock,
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
# 1. Base tables + adapter (same shape as steps 01-03).
# ---------------------------------------------------------------------------

assumptions = model.load_assumptions()
mortality_select_raw = assumptions["mortality"].table

BASE_TABLES = {
    "mortality_select": mortality_select_raw,
    "mortality_scalars": assumptions["mortality_scalars"],
    "lapse_rates": assumptions["lapse_rates"],
    "surrender_charges": assumptions["surrender_charges"],
}


def model_fn(af: ActuarialFrame, *, tables: dict, drivers: dict) -> ActuarialFrame:
    """Plan-agnostic adapter — override only the tables the plan supplies."""
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
# 2. Named regulatory stresses — each combines several shocks under a
#    business label.
# ---------------------------------------------------------------------------

SHOCKS = {
    "CENTRAL_ESTIMATE": [],
    "ADVERSE_MORTALITY": [
        # 40% mortality stress overall, with an extra 20% on top for the
        # 65+ band to model the elderly tail.
        MultiplicativeShock(factor=1.40, table="mortality_select"),
        FilteredShock(
            shock=MultiplicativeShock(factor=1.20),
            where={"age": {"gte": 65}},
            table="mortality_select",
        ),
    ],
    "ECONOMIC_DOWNTURN": [
        # Persistent lapses fall (sticky policies in a bad market) and
        # surrender charges are waived more often.
        MultiplicativeShock(factor=0.75, table="lapse_rates"),
        MultiplicativeShock(factor=0.50, table="surrender_charges"),
    ],
    "OPERATIONAL_SHOCK": [
        # Combined operational stress — lapses elevated 30%, expenses
        # (surrender-charge income) cut 25%.
        MultiplicativeShock(factor=1.30, table="lapse_rates"),
        MultiplicativeShock(factor=0.75, table="surrender_charges"),
    ],
}

AGGREGATIONS = (
    Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),
    Sum("pv_claims").alias("pv_claims").over("scenario_id"),
    Sum("pv_expenses").alias("pv_expenses").over("scenario_id"),
)

# ---------------------------------------------------------------------------
# 3. Build the plan; pin the audit chain artefacts.
# ---------------------------------------------------------------------------

plan = ScenarioRun(
    shocks=SHOCKS,
    base_tables=BASE_TABLES,
    aggregations=AGGREGATIONS,
)

print("=== Plan identity ===")
print(plan.describe())
print()

# ---------------------------------------------------------------------------
# 4. Run with audit sidecar.
# ---------------------------------------------------------------------------

mp = pl.read_parquet(MODEL_POINTS_PATH)
af = ActuarialFrame(mp)

start = time.perf_counter()
result = plan.run(af, model_fn, audit=True)
runtime = time.perf_counter() - start

print(f"Runtime: {runtime:.2f}s")
print(f"Audit sidecar: {result.audit_path}")
print()

# ---------------------------------------------------------------------------
# 5. Comparison table.
# ---------------------------------------------------------------------------

pv_components = ["pv_net_cf", "pv_claims", "pv_expenses"]
scenario_table = result.aggregations[pv_components[0]]
for name in pv_components[1:]:
    scenario_table = scenario_table.join(result.aggregations[name], on="scenario_id")

# Compute Δ vs central estimate for each non-base scenario
central_pv = (
    scenario_table.filter(pl.col("scenario_id") == "CENTRAL_ESTIMATE")
    .get_column("pv_net_cf")
    .item()
)

scenario_table = scenario_table.with_columns(
    (pl.col("pv_net_cf") - central_pv).alias("delta_vs_central"),
    ((pl.col("pv_net_cf") - central_pv) / abs(central_pv) * 100).alias("delta_pct"),
)

# Reorder so CENTRAL_ESTIMATE is first
preferred_order = ["CENTRAL_ESTIMATE", "ADVERSE_MORTALITY", "ECONOMIC_DOWNTURN", "OPERATIONAL_SHOCK"]
scenario_table = scenario_table.with_columns(
    pl.col("scenario_id")
    .replace_strict(preferred_order, range(len(preferred_order)), default=99)
    .alias("_order")
).sort("_order").drop("_order")

print("=== Regulatory Comparison ===")
print(scenario_table)
print()

# ---------------------------------------------------------------------------
# 6. Key findings — the prose to drop into a stress-test memo.
# ---------------------------------------------------------------------------

worst = scenario_table.filter(pl.col("scenario_id") != "CENTRAL_ESTIMATE").sort("delta_vs_central").row(0, named=True)
best = scenario_table.filter(pl.col("scenario_id") != "CENTRAL_ESTIMATE").sort("delta_vs_central", descending=True).row(0, named=True)

print("=== Key Findings ===")
print(f"  Plan SHA: {plan.source_sha()}")
print(f"  Worst case:   {worst['scenario_id']:<20} Δ pv_net_cf = {worst['delta_vs_central']:>+15,.0f} ({worst['delta_pct']:+6.2f}%)")
print(f"  Best case:    {best['scenario_id']:<20} Δ pv_net_cf = {best['delta_vs_central']:>+15,.0f} ({best['delta_pct']:+6.2f}%)")
print()
print(f"Reproduce: same shocks dict + same base_tables (model points {MODEL_POINTS_PATH.name}),")
print(f"expect plan SHA {plan.source_sha()} and the audit sidecar above.")
print()

# ---------------------------------------------------------------------------
# 7. YAML round-trip — separate small demo. Today only the flat shocks
#    (MultiplicativeShock / AdditiveShock / OverrideShock) round-trip
#    through YAML; FilteredShock / TimeConditionalShock / PipelineShock
#    don't yet. For non-flat plans, governance leans on the plan SHA plus
#    the JSON audit sidecar (both above) rather than the YAML recipe.
# ---------------------------------------------------------------------------

print("=== YAML round-trip (flat shocks only) ===")
flat_plan = ScenarioRun(
    shocks={
        "BASE": [],
        "MORT_UP_20": [MultiplicativeShock(factor=1.20, table="mortality_select")],
        "LAPSE_DOWN_20": [MultiplicativeShock(factor=0.80, table="lapse_rates")],
    },
    base_tables=BASE_TABLES,
    aggregations=(Sum("pv_net_cf").alias("pv_net_cf").over("scenario_id"),),
)
yaml_path = SCRIPT_DIR / "plan.yaml"
flat_plan.to_yaml(yaml_path)
flat_reloaded = ScenarioRun.from_yaml(yaml_path, base_tables=BASE_TABLES)
assert flat_reloaded.source_sha() == flat_plan.source_sha(), "YAML drift"
print(f"  Wrote: {yaml_path.name}")
print(f"  Plan SHA pre-write:  {flat_plan.source_sha()}")
print(f"  Plan SHA post-load:  {flat_reloaded.source_sha()} (matches — recipe is faithful)")
