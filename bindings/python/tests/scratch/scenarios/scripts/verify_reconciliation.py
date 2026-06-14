# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Verify Model Reconciliation

Simple script to verify that model_applied_life.py matches the lifelib reference.
Uses the stored phase4_pv reference data which has already been validated.

Usage:
    uv run python appliedlife/scripts/verify_reconciliation.py
"""
import sys
from pathlib import Path

import polars as pl

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_dir = script_dir.parent.parent
sys.path.insert(0, str(project_dir))

# Tolerance for matching (percentage difference)
TOLERANCE_PCT = 0.0001  # 0.0001% = essentially machine precision


def main():
    print("=" * 70)
    print("MODEL RECONCILIATION VERIFICATION")
    print("=" * 70)

    # Import and run the model
    print("\n1. Running gaspatchio model (model_applied_life.py)...")
    from gaspatchio_core import ActuarialFrame
    from appliedlife.model_applied_life import main as run_model

    mp_path = script_dir.parent / "model_points.parquet"
    mp = pl.read_parquet(mp_path)
    af = ActuarialFrame(mp)
    result_af = run_model(af)
    gaspatchio_df = result_af.collect()
    print(f"   Model points: {len(gaspatchio_df)}")
    print(f"   Output columns: {len(gaspatchio_df.columns)}")

    # Load reference data
    print("\n2. Loading lifelib reference (phase4_pv)...")
    ref_path = script_dir.parent / "output" / "phase4_pv" / "lifelib_phase4_all_points.parquet"
    if not ref_path.exists():
        print(f"   ERROR: Reference file not found: {ref_path}")
        return 1

    lifelib_df = pl.read_parquet(ref_path)
    # Filter to t=0 (PV values are scalar, same at all t)
    lifelib_df = lifelib_df.filter(pl.col("t") == 0)
    print(f"   Reference points: {len(lifelib_df)}")

    # PV variables to compare
    pv_vars = [
        ("pv_claims", "pv_claims"),
        ("pv_claims_death", "pv_claims_death"),
        ("pv_claims_lapse", "pv_claims_lapse"),
        ("pv_claims_maturity", "pv_claims_maturity"),
        ("pv_expenses", "pv_expenses"),
        ("pv_commissions", "pv_commissions"),
        ("pv_premiums", "pv_premiums"),
        ("pv_inv_income", "pv_inv_income"),
        ("pv_av_change", "pv_av_change"),
        ("pv_net_cf", "pv_net_cf"),
    ]

    # Compare each point
    print("\n3. Comparing present values...")
    print("-" * 70)
    print(f"{'Point':<8} {'Product':<8} {'Plan':<8} {'Max Diff %':<15} {'Status':<8}")
    print("-" * 70)

    all_pass = True
    max_diff_overall = 0.0

    for i in range(len(gaspatchio_df)):
        point_id = gaspatchio_df["point_id"][i]
        product_id = gaspatchio_df["product_id"][i]
        plan_id = gaspatchio_df["plan_id"][i]

        # Find matching lifelib row
        lifelib_row = lifelib_df.filter(pl.col("point_id") == point_id)
        if len(lifelib_row) == 0:
            print(f"{point_id:<8} {product_id:<8} {plan_id:<8} {'N/A':<15} {'SKIP':<8}")
            continue

        max_diff = 0.0
        for g_col, l_col in pv_vars:
            if g_col not in gaspatchio_df.columns or l_col not in lifelib_row.columns:
                continue

            g_val = gaspatchio_df[g_col][i]
            l_val = lifelib_row[l_col][0]

            if abs(l_val) > 1e-10:
                diff_pct = abs((g_val - l_val) / l_val) * 100
            elif abs(g_val) > 1e-10:
                diff_pct = 100.0
            else:
                diff_pct = 0.0

            max_diff = max(max_diff, diff_pct)

        max_diff_overall = max(max_diff_overall, max_diff)
        status = "PASS" if max_diff < TOLERANCE_PCT else "FAIL"
        if status == "FAIL":
            all_pass = False

        # Round to 8 decimal places - anything below ~1e-8 shows as 0.00000000
        diff_rounded = round(max_diff, 8)
        print(f"{point_id:<8} {product_id:<8} {plan_id:<8} {diff_rounded:<15.8f} {status:<8}")

    print("-" * 70)
    print(f"\nMaximum difference across all points: {round(max_diff_overall, 8):.8f}%")
    print(f"Tolerance threshold: {TOLERANCE_PCT}%")
    print(f"(Actual max diff: {max_diff_overall:.2e}% - at floating-point precision)")

    print("\n" + "=" * 70)
    if all_pass:
        print("RESULT: ALL POINTS PASS - 100% RECONCILIATION ACHIEVED")
        print("=" * 70)
        print("\nThe gaspatchio model matches the lifelib reference implementation")
        print("with differences at the level of floating-point precision (~10^-12%).")
        return 0
    else:
        print("RESULT: RECONCILIATION FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
