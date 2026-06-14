# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Explicit Scenario Example: Interest Rate Sensitivity (BASE/UP/DOWN)

Demonstrates running the appliedlife model across multiple economic
scenarios using pre-built assumption files.

The risk_free_rates.parquet file contains three interest rate scenarios:
- BASE: Base interest rate curve
- UP: Rates shifted up by ~100bp
- DOWN: Rates shifted down by ~100bp

Usage:
    uv run python appliedlife/model_scenarios.py
"""

import sys
from pathlib import Path

import polars as pl
from gaspatchio_core import ActuarialFrame, with_scenarios

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from appliedlife.model_applied_life import main as run_model

MODEL_DIR = Path(__file__).parent


def main():
    """Run model across BASE/UP/DOWN interest rate scenarios."""
    print("=" * 70)
    print("EXPLICIT SCENARIOS: Interest Rate Sensitivity")
    print("=" * 70)

    # 1. Load model points
    print("\n1. Loading model points...")
    mp = pl.read_parquet(MODEL_DIR / "model_points.parquet")
    af = ActuarialFrame(mp)
    print(f"   Loaded {len(mp)} policies")

    # 2. Expand across scenarios
    print("\n2. Expanding across scenarios...")
    scenarios = ["BASE", "UP", "DOWN"]
    af = with_scenarios(af, scenarios)
    print(f"   Scenarios: {scenarios}")
    print(f"   Expanded to {len(af.collect())} rows ({len(mp)} policies x {len(scenarios)} scenarios)")

    # 3. Run model
    print("\n3. Running projection...")
    result = run_model(af)
    result_df = result.collect()
    print(f"   Projection complete")

    # 4. Aggregate by scenario
    print("\n4. Aggregating results by scenario...")
    summary = (
        result_df
        .group_by("scenario_id")
        .agg([
            pl.col("pv_premiums").sum().alias("total_pv_premiums"),
            pl.col("pv_claims").sum().alias("total_pv_claims"),
            pl.col("pv_expenses").sum().alias("total_pv_expenses"),
            pl.col("pv_commissions").sum().alias("total_pv_commissions"),
            pl.col("pv_net_cf").sum().alias("total_pv_net_cf"),
        ])
        .sort("scenario_id")
    )

    # 5. Display results
    print("\n" + "=" * 70)
    print("RESULTS BY SCENARIO")
    print("=" * 70)
    print(summary)

    # 6. Calculate impact vs BASE
    print("\n" + "-" * 70)
    print("SCENARIO IMPACT vs BASE")
    print("-" * 70)

    base_pv = summary.filter(pl.col("scenario_id") == "BASE")["total_pv_net_cf"][0]

    for row in summary.iter_rows(named=True):
        scenario = row["scenario_id"]
        pv = row["total_pv_net_cf"]
        diff = pv - base_pv
        pct = (diff / abs(base_pv)) * 100 if base_pv != 0 else 0

        direction = "Higher rates = lower PV" if scenario == "UP" else "Lower rates = higher PV" if scenario == "DOWN" else ""
        print(f"  {scenario:6}: PV = {pv:>14,.2f}  ({diff:>+12,.2f} / {pct:>+6.2f}%)  {direction}")

    print("\n" + "=" * 70)
    return summary


if __name__ == "__main__":
    main()
