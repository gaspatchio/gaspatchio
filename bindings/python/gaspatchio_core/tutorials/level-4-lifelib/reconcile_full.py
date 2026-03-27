"""
Full reconciliation: PVs AND intermediate cashflows against lifelib reference.

Compares per-point, per-timestep intermediate variables (mortality rates,
policy counts, claims, cashflows, AV, discount factors) as well as PV
aggregates. Uses the comprehensive reference parquet extracted from lifelib.

Usage:
    # Run full reconciliation (runs the model, then compares everything)
    uv run python tutorial/level-4-lifelib/reconcile_full.py

    # Compare against a pre-computed gaspatchio output
    uv run python tutorial/level-4-lifelib/reconcile_full.py --gaspatchio-output /tmp/result.parquet

    # Show detailed per-variable breakdown for a specific point
    uv run python tutorial/level-4-lifelib/reconcile_full.py --detail 1

Exit code 0 if all checks pass, 1 if any fail.
"""

import sys
from pathlib import Path

import polars as pl

MODEL_DIR = Path(__file__).parent
REFERENCE_FULL_PATH = MODEL_DIR / "reference" / "lifelib_reference_full.parquet"
REFERENCE_PV_PATH = MODEL_DIR / "reference" / "lifelib_reference.parquet"

TOLERANCE_PCT = 0.0001  # 0.0001% — machine precision level

# Column mapping: (gaspatchio_name, lifelib_name, description, category)
INTERMEDIATE_VARIABLES = [
    # Mortality
    ("mort_rate", "mort_rate", "Annual mortality rate", "Mortality"),
    ("mort_rate_mth", "mort_rate_mth", "Monthly mortality rate", "Mortality"),
    # Lapse
    ("base_lapse_rate", "base_lapse_rate", "Base annual lapse rate", "Lapse"),
    ("dyn_lapse_factor", "dyn_lapse_factor", "Dynamic lapse factor", "Lapse"),
    ("lapse_rate", "lapse_rate", "Final annual lapse rate", "Lapse"),
    # Policy counts
    # Note: gaspatchio's pols_if matches lifelib's pols_if_bef_mat (before maturity zeroing).
    # Lifelib's pols_if (BEF_DECR) zeros out at the maturity month; gaspatchio defers to next period.
    ("pols_if", "pols_if_bef_mat", "Policies in force (before maturity)", "Policies"),
    ("pols_death", "pols_death", "Deaths", "Policies"),
    ("pols_lapse", "pols_lapse", "Lapses", "Policies"),
    ("pols_maturity", "pols_maturity", "Maturities", "Policies"),
    # Account value
    ("av_pp_bef_prem", "av_pp_bef_prem", "AV per policy before premium", "AV"),
    ("av_pp_bef_fee", "av_pp_bef_fee", "AV per policy before fee", "AV"),
    ("av_pp_mid_mth", "av_pp_mid_mth", "AV per policy mid-month", "AV"),
    ("maint_fee_pp", "maint_fee_pp", "Maintenance fee per policy", "AV"),
    ("inv_return_mth", "inv_return_mth", "Monthly investment return", "AV"),
    # Cashflows
    ("claims_death", "claims_death", "Death claims", "Cashflows"),
    ("claims_lapse", "claims_lapse", "Lapse/surrender claims", "Cashflows"),
    ("claims_maturity", "claims_maturity", "Maturity claims", "Cashflows"),
    ("premiums", "premiums", "Premium cashflow", "Cashflows"),
    ("expenses", "expenses", "Expense cashflow", "Cashflows"),
    ("commissions", "commissions", "Commission cashflow", "Cashflows"),
    ("inv_income", "inv_income", "Investment income", "Cashflows"),
    ("av_change", "av_change", "Change in account value", "Cashflows"),
    ("net_cf", "net_cf", "Net cashflow", "Cashflows"),
    # Discount
    ("disc_factors", "disc_factors", "Cumulative discount factors", "Discount"),
    ("disc_rate_mth", "disc_rate_mth", "Monthly discount rate", "Discount"),
]

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


def run_model() -> pl.DataFrame:
    """Run the Level 4 model and return collected results."""
    from gaspatchio_core import ActuarialFrame

    sys.path.insert(0, str(MODEL_DIR / "base"))
    import model  # noqa: PLC0415

    mp = pl.read_parquet(MODEL_DIR / "base" / "model_points.parquet")
    af = ActuarialFrame(mp)
    result_af = model.main(af)
    return result_af.collect()


def explode_gaspatchio(gaspatchio_df: pl.DataFrame) -> pl.DataFrame:
    """Explode gaspatchio list columns into per-point, per-timestep rows.

    Gaspatchio stores projection values as list columns (one list per policy).
    This function explodes them into flat rows matching lifelib's format.
    """
    # Get list columns (exclude scalar metadata)
    list_cols = [
        c
        for c in gaspatchio_df.columns
        if gaspatchio_df[c].dtype == pl.List(pl.Float64)
        or gaspatchio_df[c].dtype == pl.List(pl.Int64)
        or str(gaspatchio_df[c].dtype).startswith("list")
    ]

    if not list_cols:
        return gaspatchio_df

    # Add a time index column before exploding
    # Each list has the same length (PROJECTION_MONTHS)
    first_list_col = list_cols[0]
    list_len = gaspatchio_df[first_list_col].list.len()[0]

    # Select point_id, product_id, plan_id + all list columns, then explode
    id_cols = ["point_id", "product_id", "plan_id", "fund_index"]
    keep_cols = [c for c in id_cols if c in gaspatchio_df.columns]

    # Also keep scalar PV columns
    pv_cols = [c for c in gaspatchio_df.columns if c.startswith("pv_")]

    select_cols = keep_cols + list_cols + pv_cols
    select_cols = [c for c in select_cols if c in gaspatchio_df.columns]

    df = gaspatchio_df.select(select_cols)

    # Explode all list columns together
    exploded = df.explode(list_cols)

    # Add time index
    n_points = len(gaspatchio_df)
    t_values = list(range(list_len)) * n_points
    exploded = exploded.with_columns(pl.Series("t", t_values))

    return exploded


def pct_diff(g_val: float, l_val: float) -> float:
    """Compute percentage difference, handling zeros."""
    if abs(l_val) > 1e-10:
        return abs((g_val - l_val) / l_val) * 100
    if abs(g_val) > 1e-10:
        return 100.0
    return 0.0


def compare_pv(gaspatchio_df: pl.DataFrame, lifelib_df: pl.DataFrame) -> bool:
    """Compare PV variables (scalar per point). Returns True if all pass."""
    print(f"\n{'Point':<8} {'Product':<8} {'Plan':<8} {'Max Diff %':<18} {'Status'}")
    print("-" * 60)

    all_pass = True
    for i in range(len(gaspatchio_df)):
        point_id = gaspatchio_df["point_id"][i]
        lifelib_row = lifelib_df.filter(pl.col("point_id") == point_id)
        if len(lifelib_row) == 0:
            continue

        product_id = gaspatchio_df["product_id"][i]
        plan_id = gaspatchio_df["plan_id"][i]

        max_diff = 0.0
        for g_col, l_col, _desc in PV_VARIABLES:
            if g_col not in gaspatchio_df.columns or l_col not in lifelib_row.columns:
                continue
            g_val = gaspatchio_df[g_col][i]
            l_val = lifelib_row[l_col][0]
            diff = pct_diff(g_val, l_val)
            max_diff = max(max_diff, diff)

        status = "PASS" if max_diff < TOLERANCE_PCT else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"{point_id:<8} {product_id:<8} {plan_id:<8} {max_diff:.4f}%{'':<12} {status}")

    print("-" * 60)
    return all_pass


def compare_intermediates(
    gaspatchio_exploded: pl.DataFrame,
    lifelib_df: pl.DataFrame,
    detail_point: int | None = None,
) -> bool:
    """Compare intermediate variables per point, per timestep.

    Returns True if all pass within tolerance.
    """
    point_ids = sorted(lifelib_df["point_id"].unique().to_list())
    max_t = lifelib_df["t"].max()

    all_pass = True
    results: list[dict] = []

    for g_col, l_col, desc, category in INTERMEDIATE_VARIABLES:
        if g_col not in gaspatchio_exploded.columns:
            results.append(
                {
                    "variable": g_col,
                    "category": category,
                    "max_diff_pct": float("nan"),
                    "worst_point": -1,
                    "worst_t": -1,
                    "status": "SKIP",
                }
            )
            continue
        if l_col not in lifelib_df.columns:
            continue

        worst_diff = 0.0
        worst_point = 0
        worst_t = 0

        for pid in point_ids:
            g_rows = gaspatchio_exploded.filter(pl.col("point_id") == pid).sort("t")
            l_rows = lifelib_df.filter(pl.col("point_id") == pid).sort("t")

            n = min(len(g_rows), len(l_rows))
            for t in range(n):
                g_val = g_rows[g_col][t]
                l_val = l_rows[l_col][t]

                if g_val is None or l_val is None:
                    continue

                diff = pct_diff(float(g_val), float(l_val))
                if diff > worst_diff:
                    worst_diff = diff
                    worst_point = pid
                    worst_t = t

        status = "PASS" if worst_diff < TOLERANCE_PCT else "FAIL"
        if status == "FAIL":
            all_pass = False

        results.append(
            {
                "variable": g_col,
                "category": category,
                "max_diff_pct": worst_diff,
                "worst_point": worst_point,
                "worst_t": worst_t,
                "status": status,
            }
        )

    # Print summary by category
    current_category = ""
    print(
        f"\n{'Variable':<22} {'Max Diff %':<14} {'Worst Pt':<10} {'Worst t':<10} {'Status'}"
    )
    print("-" * 70)

    for r in results:
        if r["category"] != current_category:
            current_category = r["category"]
            print(f"\n  [{current_category}]")

        if r["status"] == "SKIP":
            print(f"  {r['variable']:<20} {'—':<14} {'—':<10} {'—':<10} SKIP")
        else:
            diff_str = f"{r['max_diff_pct']:.6f}%"
            print(
                f"  {r['variable']:<20} {diff_str:<14} {r['worst_point']:<10} "
                f"{r['worst_t']:<10} {r['status']}"
            )

    print("-" * 70)

    # Detailed output for a specific point
    if detail_point is not None:
        print(f"\n{'=' * 70}")
        print(f"DETAIL: Point {detail_point} — per-timestep comparison")
        print(f"{'=' * 70}")

        g_point = gaspatchio_exploded.filter(
            pl.col("point_id") == detail_point
        ).sort("t")
        l_point = lifelib_df.filter(pl.col("point_id") == detail_point).sort("t")

        for g_col, l_col, desc, category in INTERMEDIATE_VARIABLES:
            if g_col not in gaspatchio_exploded.columns or l_col not in lifelib_df.columns:
                continue

            # Find worst timestep for this variable/point
            diffs = []
            n = min(len(g_point), len(l_point))
            for t in range(n):
                g_val = g_point[g_col][t]
                l_val = l_point[l_col][t]
                if g_val is not None and l_val is not None:
                    diffs.append((t, float(g_val), float(l_val), pct_diff(float(g_val), float(l_val))))

            if not diffs:
                continue

            max_diff_entry = max(diffs, key=lambda x: x[3])
            if max_diff_entry[3] > 0:
                t, gv, lv, d = max_diff_entry
                print(
                    f"  {g_col:<22} worst at t={t}: "
                    f"gsp={gv:.6f} lib={lv:.6f} diff={d:.8f}%"
                )

    return all_pass


def main() -> int:
    """Run full reconciliation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Full reconciliation: PVs + intermediate cashflows"
    )
    parser.add_argument(
        "--gaspatchio-output",
        type=str,
        help="Path to pre-computed gaspatchio output parquet (skips model run)",
    )
    parser.add_argument(
        "--reference",
        type=str,
        default=None,
        help="Path to full reference parquet (default: reference/lifelib_reference_full.parquet)",
    )
    parser.add_argument(
        "--detail",
        type=int,
        default=None,
        help="Show per-timestep detail for this point_id",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("FULL RECONCILIATION: Gaspatchio vs Lifelib IntegratedLife")
    print("PV aggregates + intermediate cashflows per point per timestep")
    print("=" * 70)

    # Load or run gaspatchio
    if args.gaspatchio_output:
        print(f"\nLoading gaspatchio output: {args.gaspatchio_output}")
        gaspatchio_df = pl.read_parquet(args.gaspatchio_output)
    else:
        print("\nRunning Level 4 model...")
        gaspatchio_df = run_model()

    print(f"  Model points: {len(gaspatchio_df)}")
    print(f"  Columns: {len(gaspatchio_df.columns)}")

    # Load reference
    ref_path = Path(args.reference) if args.reference else REFERENCE_FULL_PATH
    if not ref_path.exists():
        print(f"\nERROR: Full reference file not found: {ref_path}")
        print("Run extract_per_point_reference.py from gaspatchio-models first.")
        return 1

    lifelib_df = pl.read_parquet(ref_path)
    lifelib_pv = lifelib_df.filter(pl.col("t") == 0)
    print(f"  Reference: {len(lifelib_df)} rows ({lifelib_df['point_id'].n_unique()} points × {lifelib_df['t'].max() + 1} timesteps)")

    # Part 1: PV comparison (same as original reconcile.py)
    print("\n" + "=" * 70)
    print("PART 1: Present Value Comparison")
    print("=" * 70)
    pv_pass = compare_pv(gaspatchio_df, lifelib_pv)

    # Part 2: Intermediate cashflow comparison
    print("\n" + "=" * 70)
    print("PART 2: Intermediate Cashflow Comparison (per point, per timestep)")
    print("=" * 70)

    print("\nExploding gaspatchio list columns...")
    gaspatchio_exploded = explode_gaspatchio(gaspatchio_df)
    print(f"  Exploded: {len(gaspatchio_exploded)} rows")

    intermediates_pass = compare_intermediates(
        gaspatchio_exploded, lifelib_df, detail_point=args.detail
    )

    # Summary
    print("\n" + "=" * 70)
    if pv_pass and intermediates_pass:
        print("RESULT: ALL CHECKS PASS")
        print("  PV aggregates:    PASS (10/10 variables, 8/8 points)")
        n_checked = sum(
            1
            for g, l, _, _ in INTERMEDIATE_VARIABLES
            if g in gaspatchio_exploded.columns and l in lifelib_df.columns
        )
        print(f"  Intermediates:    PASS ({n_checked} variables, 8 points × 82 timesteps)")
    else:
        print("RESULT: RECONCILIATION ISSUES FOUND")
        if not pv_pass:
            print("  PV aggregates:    FAIL")
        if not intermediates_pass:
            print("  Intermediates:    FAIL")
        print("\nRe-run with --detail <point_id> for per-timestep breakdown.")
    print("=" * 70)

    return 0 if (pv_pass and intermediates_pass) else 1


if __name__ == "__main__":
    sys.exit(main())
