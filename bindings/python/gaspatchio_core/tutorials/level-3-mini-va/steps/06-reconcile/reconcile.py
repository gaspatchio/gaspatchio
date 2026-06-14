# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Reconcile Step 06 model output against lifelib IntegratedLife reference data.

Runs either the gapped starting model or the fixed reference model, then
compares present-value variables for all 8 model points against lifelib's
known-good output.

Usage:
    # Run with gapped model (default) — expect failures
    uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py

    # Run with fixed model — expect all pass
    uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py --model fixed

    # Compare pre-computed output
    uv run python tutorial/level-3-mini-va/steps/06-reconcile/reconcile.py --gaspatchio-output /tmp/result.parquet

Exit code 0 if all points pass, 1 if any fail.
"""

import sys
from pathlib import Path

import polars as pl

STEP_DIR = Path(__file__).resolve().parent
L4_DIR = STEP_DIR.parent.parent.parent / "level-4-lifelib"
REFERENCE_PATH = L4_DIR / "reference" / "lifelib_reference.parquet"
MODEL_POINTS_PATH = L4_DIR / "base" / "model_points.parquet"

# Tolerance: percentage difference threshold
# Machine precision is ~10^-12%; we use 0.0001% to allow for
# minor floating-point path differences between implementations.
TOLERANCE_PCT = 0.0001

# PV variables to compare (gaspatchio name, lifelib name, display label)
PV_VARIABLES = [
    ("pv_claims", "pv_claims", "PV Total Claims"),
    ("pv_claims_death", "pv_claims_death", "PV Death Claims"),
    ("pv_claims_lapse", "pv_claims_lapse", "PV Lapse Claims"),
    ("pv_claims_maturity", "pv_claims_maturity", "PV Maturity Claims"),
    ("pv_expenses", "pv_expenses", "PV Expenses"),
    ("pv_commissions", "pv_commissions", "PV Commissions"),
    ("pv_premiums", "pv_premiums", "PV Premiums"),
    ("pv_inv_income", "pv_inv_income", "PV Investment Income"),
    ("pv_av_change", "pv_av_change", "PV AV Change"),
    ("pv_net_cf", "pv_net_cf", "PV Net Cashflow"),
]


def run_model(model_name: str) -> pl.DataFrame:
    """Import and run the selected model, returning collected results."""
    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415

    # Make the step directory importable so we can import model files
    sys.path.insert(0, str(STEP_DIR))

    if model_name == "gaps":
        import model_with_gaps as mod  # noqa: PLC0415
    else:
        import model as mod  # noqa: PLC0415

    mp = pl.read_parquet(MODEL_POINTS_PATH)
    af = ActuarialFrame(mp)
    result_af = mod.main(af)
    return result_af.collect()


def load_reference() -> pl.DataFrame:
    """Load lifelib reference output, filtered to PV values (t=0)."""
    if not REFERENCE_PATH.exists():
        print(f"ERROR: Reference file not found: {REFERENCE_PATH}")
        print("This file should be checked into the repository.")
        sys.exit(1)

    ref = pl.read_parquet(REFERENCE_PATH)
    # PV values are the same at every t; filter to t=0 for one row per point
    return ref.filter(pl.col("t") == 0)


def compare(gaspatchio_df: pl.DataFrame, lifelib_df: pl.DataFrame) -> bool:
    """Compare gaspatchio output against lifelib reference.

    Returns True if all points pass within tolerance.
    """
    print(
        f"\n{'Point':<8} {'Product':<8} {'Plan':<8} "
        f"{'Max Diff %':<18} {'Worst Variable':<20} {'Status'}"
    )
    print("-" * 80)

    all_pass = True
    max_diff_overall = 0.0
    pass_count = 0
    total_count = 0

    for i in range(len(gaspatchio_df)):
        point_id = gaspatchio_df["point_id"][i]

        # Match by point_id
        lifelib_row = lifelib_df.filter(pl.col("point_id") == point_id)
        if len(lifelib_row) == 0:
            print(
                f"{point_id:<8} {'?':<8} {'?':<8} "
                f"{'N/A':<18} {'':<20} SKIP"
            )
            continue

        total_count += 1
        product_id = gaspatchio_df["product_id"][i]
        plan_id = gaspatchio_df["plan_id"][i]

        # Find worst variable for this point
        max_diff = 0.0
        worst_var = ""
        for g_col, l_col, _desc in PV_VARIABLES:
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

            if diff_pct > max_diff:
                max_diff = diff_pct
                worst_var = g_col

        max_diff_overall = max(max_diff_overall, max_diff)
        status = "PASS" if max_diff < TOLERANCE_PCT else "FAIL"
        if status == "FAIL":
            all_pass = False
        else:
            pass_count += 1

        diff_str = f"{max_diff:.4f}%"

        print(
            f"{point_id:<8} {product_id:<8} {plan_id:<8} "
            f"{diff_str:<18} {worst_var:<20} {status}"
        )

    print("-" * 80)
    print(f"\nMax difference: {max_diff_overall:.4f}%")
    print(f"Tolerance:      {TOLERANCE_PCT}%")
    print(f"Points passed:  {pass_count}/{total_count}")

    return all_pass


def print_debugging_hints() -> None:
    """Print gap-specific debugging hints for the gapped model."""
    print(
        """
Debugging hints (for the gapped model):
  GMAB points failing with large differences?
    -> Check dynamic lapse formula: GMAB uses DL002, not DL001 (Gap 3)
  All points off by a small amount in PV variables?
    -> Check discount factor formula: cum_prod vs closed-form (Gap 4)
  Intermediate variables don't match?
    -> Check AV decomposition: cum_prod vs accumulate (Gap 1)
    -> Check decrement ordering: simple vs BEF_DECR (Gap 2)"""
    )


def main() -> int:
    """Run reconciliation and return exit code."""
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description="Reconcile L3 Step 06 model against lifelib reference"
    )
    parser.add_argument(
        "--model",
        choices=["gaps", "fixed"],
        default="gaps",
        help='Which model to run: "gaps" (default) or "fixed"',
    )
    parser.add_argument(
        "--gaspatchio-output",
        type=str,
        help="Path to pre-computed gaspatchio output parquet (skips model run)",
    )
    args = parser.parse_args()

    model_label = args.model if not args.gaspatchio_output else "pre-computed"

    print("=" * 80)
    print("L3 STEP 06 RECONCILIATION: Gaspatchio vs Lifelib IntegratedLife")
    print(f"  Model: {model_label}")
    print("=" * 80)

    # Load or run gaspatchio
    if args.gaspatchio_output:
        print(f"\nLoading gaspatchio output: {args.gaspatchio_output}")
        gaspatchio_df = pl.read_parquet(args.gaspatchio_output)
    else:
        print(f"\nRunning {args.model} model...")
        gaspatchio_df = run_model(args.model)

    print(f"  Model points: {len(gaspatchio_df)}")

    # Load reference
    print("Loading lifelib reference...")
    lifelib_df = load_reference()
    print(f"  Reference points: {len(lifelib_df)}")

    # Compare
    print("\nComparing present values:")
    all_pass = compare(gaspatchio_df, lifelib_df)

    # Debugging hints for the gapped model
    if args.model == "gaps" and not args.gaspatchio_output:
        print_debugging_hints()

    print("\n" + "=" * 80)
    if all_pass:
        print("RESULT: ALL POINTS PASS")
    else:
        print("RESULT: RECONCILIATION FAILED")
        print("Investigate mismatches using gspio run-single-policy:")
        print(
            "  uv run gspio run-single-policy "
            "tutorial/level-3-mini-va/steps/06-reconcile/model_with_gaps.py "
            "tutorial/level-4-lifelib/base/model_points.parquet 1 "
            "--output-file /tmp/debug.parquet"
        )
    print("=" * 80)

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
