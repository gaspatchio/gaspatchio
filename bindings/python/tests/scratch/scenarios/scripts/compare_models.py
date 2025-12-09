"""
Compare Gaspatchio and Lifelib IntegratedLife Model Outputs

This script compares the outputs from:
1. Gaspatchio model (appliedlife/model_applied.py)
2. Lifelib IntegratedLife model (via run_integratedlife.py)

Uses in-force model points (8 points) for comparison.

Usage:
    # Run comparison (uses most recent lifelib output)
    uv run python appliedlife/scripts/compare_models.py

    # With specific lifelib output
    uv run python appliedlife/scripts/compare_models.py --lifelib-output appliedlife/output/...

    # First run lifelib with matching settings:
    uv run python appliedlife/scripts/run_integratedlife.py --run-id 2 --num-scenarios 1 --products gmxb --verbose
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import polars as pl

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_dir = script_dir.parent.parent
sys.path.insert(0, str(project_dir))


# In-force configuration (8 model points, lifelib run_id=2)
LIFELIB_RUN_ID = 2  # Uses 2023Q4IF model points
EXPECTED_MODEL_POINTS = 8
EXPECTED_SCENARIOS = 1
EXPECTED_PRODUCT = "GMXB"


def validate_lifelib_output(output_dir: Path) -> tuple[bool, str]:
    """
    Validate that lifelib output matches expected settings for comparison.

    Returns:
        (is_valid, message) tuple
    """
    summary_path = output_dir / "run_summary.txt"
    if not summary_path.exists():
        return False, f"No run_summary.txt found in {output_dir}"

    content = summary_path.read_text()

    errors = []

    # Check run_id
    if f"Run ID: {LIFELIB_RUN_ID}" not in content:
        errors.append(f"Expected Run ID: {LIFELIB_RUN_ID}")

    # Check model points count
    if f"({EXPECTED_MODEL_POINTS} points)" not in content:
        errors.append(f"Expected {EXPECTED_MODEL_POINTS} model points")

    # Check scenarios
    if f"({EXPECTED_SCENARIOS} scenario" not in content:
        errors.append(f"Expected {EXPECTED_SCENARIOS} scenario(s)")

    # Check product
    if EXPECTED_PRODUCT not in content:
        errors.append(f"Expected product: {EXPECTED_PRODUCT}")

    if errors:
        return False, f"Lifelib output mismatch: {'; '.join(errors)}"

    return True, "Lifelib output validated successfully"


def find_valid_lifelib_output(output_base: Path) -> Path | None:
    """
    Find the most recent lifelib output that matches expected settings.

    Returns:
        Path to valid output directory, or None if not found
    """
    if not output_base.exists():
        return None

    # Get all non-comparison directories, sorted by name (timestamp)
    lifelib_dirs = sorted([
        d for d in output_base.iterdir()
        if d.is_dir() and not d.name.startswith("comparison_")
    ], reverse=True)  # Most recent first

    for d in lifelib_dirs:
        is_valid, msg = validate_lifelib_output(d)
        if is_valid:
            return d

    return None


def run_gaspatchio_model() -> pl.DataFrame:
    """Run the Gaspatchio model and return results.

    Uses the gspio-compatible main(af) signature. Configuration (RUN_ID, SPACE)
    is controlled by constants in model_applied.py.
    """
    from appliedlife.model_applied import main
    from gaspatchio_core import ActuarialFrame

    mp_path = script_dir.parent / "model_points.parquet"

    if not mp_path.exists():
        raise FileNotFoundError(f"Model points file not found: {mp_path}")

    print(f"Loading model points: {mp_path.name}")
    mp = pl.read_parquet(mp_path)
    af = ActuarialFrame(mp)

    # Run model - main() handles tables, run_id, space internally
    result_af = main(af)

    return result_af.collect()


def aggregate_gaspatchio_results(df: pl.DataFrame) -> dict:
    """
    Aggregate Gaspatchio results to match lifelib output format.

    Gaspatchio outputs per-policy, per-month data. We need to:
    1. Sum across all policies
    2. Sum across all time periods for totals
    """
    # List columns need to be exploded for aggregation
    # First, get time-series columns
    time_series_cols = [
        "cf_premiums", "cf_death_claims", "cf_surrender",
        "cf_maint_fee", "cf_commissions", "cf_net",
        "pv_premiums", "pv_death_claims", "pv_surrender",
        "pv_maint_fee", "pv_commissions", "pv_net",
        "pols_if", "pols_death", "pols_lapse",
    ]

    results = {}

    # For each policy, we have list columns
    # We need to:
    # 1. Explode each policy's time series
    # 2. Sum across policies at each time step
    # 3. Then sum across all time steps for totals

    # Total Present Values (sum of all PVs across time and policies)
    for col in ["pv_premiums", "pv_death_claims", "pv_surrender", "pv_net"]:
        if col in df.columns:
            # Sum across time (within each policy's list), then sum across policies
            try:
                total = df.select(
                    pl.col(col).list.sum().sum()
                ).item()
                results[col] = total
            except Exception as e:
                print(f"Warning: Could not aggregate {col}: {e}")
                results[col] = None

    # Total Cashflows
    for col in ["cf_premiums", "cf_death_claims", "cf_surrender", "cf_net"]:
        if col in df.columns:
            try:
                total = df.select(
                    pl.col(col).list.sum().sum()
                ).item()
                results[col] = total
            except Exception as e:
                print(f"Warning: Could not aggregate {col}: {e}")
                results[col] = None

    # Policy counts at t=0
    if "pols_if" in df.columns:
        try:
            # Get first value of each policy's list (pols_if at t=0)
            initial_pols = df.select(
                pl.col("pols_if").list.first().sum()
            ).item()
            results["initial_pols_if"] = initial_pols
        except Exception as e:
            print(f"Warning: Could not get initial pols_if: {e}")
            results["initial_pols_if"] = None

    # Total deaths and lapses
    for col in ["pols_death", "pols_lapse"]:
        if col in df.columns:
            try:
                total = df.select(
                    pl.col(col).list.sum().sum()
                ).item()
                results[f"total_{col}"] = total
            except Exception as e:
                print(f"Warning: Could not aggregate {col}: {e}")
                results[f"total_{col}"] = None

    return results


def load_lifelib_results(output_dir: Path) -> dict:
    """Load lifelib results from CSV files."""
    results = {}

    # Load cashflows
    cf_path = output_dir / "gmxb_cf.csv"
    if cf_path.exists():
        cf_df = pl.read_csv(cf_path)
        # Row 0 often has totals in lifelib output
        if len(cf_df) > 0:
            results["lifelib_cf"] = cf_df
            # Get totals from first row (which is typically total/summary)
            first_row = cf_df.row(0, named=True)
            results["cf_premiums_lifelib"] = first_row.get("Premiums")
            results["cf_claims_lifelib"] = first_row.get("Claims")
            results["cf_expenses_lifelib"] = first_row.get("Expenses")
            results["cf_commissions_lifelib"] = first_row.get("Commissions")
            results["cf_net_lifelib"] = first_row.get("Net Cashflow")

    # Load policy counts
    pols_path = output_dir / "gmxb_pols.csv"
    if pols_path.exists():
        pols_df = pl.read_csv(pols_path, infer_schema_length=1000)
        results["lifelib_pols"] = pols_df
        # Sum across all time periods (handle string columns gracefully)
        if "pols_death" in pols_df.columns:
            try:
                col = pols_df["pols_death"].cast(pl.Float64, strict=False)
                results["total_pols_death_lifelib"] = col.sum()
            except Exception:
                results["total_pols_death_lifelib"] = None
        if "pols_lapse" in pols_df.columns:
            try:
                col = pols_df["pols_lapse"].cast(pl.Float64, strict=False)
                results["total_pols_lapse_lifelib"] = col.sum()
            except Exception:
                results["total_pols_lapse_lifelib"] = None
        if "pols_if" in pols_df.columns:
            try:
                col = pols_df["pols_if"].cast(pl.Float64, strict=False)
                pols_if_vals = col.drop_nulls()
                if len(pols_if_vals) > 0:
                    results["initial_pols_if_lifelib"] = pols_if_vals[0]
            except Exception:
                results["initial_pols_if_lifelib"] = None

    # Load present values
    pv_path = output_dir / "gmxb_pv.csv"
    if pv_path.exists():
        pv_df = pl.read_csv(pv_path, infer_schema_length=1000)
        results["lifelib_pv"] = pv_df
        # Sum across all scenarios and model points
        for col in ["Premiums", "Death", "Surrender", "Net Cashflow"]:
            if col in pv_df.columns:
                try:
                    col_data = pv_df[col].cast(pl.Float64, strict=False)
                    total = col_data.sum()
                    results[f"pv_{col.lower()}_lifelib"] = total
                except Exception:
                    results[f"pv_{col.lower()}_lifelib"] = None

    return results


def compare_metrics(gaspatchio: dict, lifelib: dict) -> list[dict]:
    """Compare key metrics between models."""
    comparisons = []

    # Map Gaspatchio names to Lifelib names
    metric_pairs = [
        ("cf_premiums", "cf_premiums_lifelib", "Total Premiums (Cashflow)"),
        ("cf_death_claims", "cf_claims_lifelib", "Total Death Claims (Cashflow)"),
        ("cf_net", "cf_net_lifelib", "Net Cashflow"),
        ("pv_premiums", "pv_premiums_lifelib", "PV Premiums"),
        ("pv_death_claims", "pv_death_lifelib", "PV Death Claims"),
        ("pv_net", "pv_net cashflow_lifelib", "PV Net Cashflow"),
        ("initial_pols_if", "initial_pols_if_lifelib", "Initial Policies In Force"),
        ("total_pols_death", "total_pols_death_lifelib", "Total Deaths"),
        ("total_pols_lapse", "total_pols_lapse_lifelib", "Total Lapses"),
    ]

    for gasp_key, life_key, label in metric_pairs:
        gasp_val = gaspatchio.get(gasp_key)
        life_val = lifelib.get(life_key)

        if gasp_val is not None and life_val is not None:
            if life_val != 0:
                pct_diff = (gasp_val - life_val) / life_val * 100
            else:
                pct_diff = float('inf') if gasp_val != 0 else 0

            comparisons.append({
                "metric": label,
                "gaspatchio": gasp_val,
                "lifelib": life_val,
                "difference": gasp_val - life_val,
                "pct_diff": pct_diff,
            })
        elif gasp_val is not None:
            comparisons.append({
                "metric": label,
                "gaspatchio": gasp_val,
                "lifelib": None,
                "difference": None,
                "pct_diff": None,
            })

    return comparisons


def format_number(val):
    """Format a number for display."""
    if val is None:
        return "N/A"
    if abs(val) >= 1_000_000:
        return f"{val:,.0f}"
    elif abs(val) >= 1:
        return f"{val:,.2f}"
    else:
        return f"{val:.6f}"


def print_comparison_report(comparisons: list[dict], gaspatchio_df: pl.DataFrame):
    """Print a formatted comparison report."""
    print("\n" + "=" * 80)
    print("MODEL COMPARISON REPORT: Gaspatchio vs Lifelib IntegratedLife")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Model points: {len(gaspatchio_df)}")

    # Get projection info
    if "month" in gaspatchio_df.columns:
        max_months = gaspatchio_df["month"].list.len().max()
        print(f"Projection periods: {max_months} months")

    print("\n" + "-" * 80)
    print("METRIC COMPARISON")
    print("-" * 80)
    print(f"{'Metric':<35} {'Gaspatchio':>18} {'Lifelib':>18} {'Diff %':>10}")
    print("-" * 80)

    for comp in comparisons:
        gasp_str = format_number(comp["gaspatchio"])
        life_str = format_number(comp["lifelib"])

        if comp["pct_diff"] is not None:
            pct_str = f"{comp['pct_diff']:+.2f}%"
        else:
            pct_str = "N/A"

        print(f"{comp['metric']:<35} {gasp_str:>18} {life_str:>18} {pct_str:>10}")

    print("-" * 80)

    # Summary statistics
    valid_comparisons = [c for c in comparisons if c["pct_diff"] is not None]
    if valid_comparisons:
        pct_diffs = [abs(c["pct_diff"]) for c in valid_comparisons]
        max_diff = max(pct_diffs)
        avg_diff = sum(pct_diffs) / len(pct_diffs)

        print("\nSUMMARY:")
        print(f"  Metrics compared: {len(valid_comparisons)}")
        print(f"  Average abs difference: {avg_diff:.2f}%")
        print(f"  Maximum abs difference: {max_diff:.2f}%")

        if max_diff < 0.1:
            print("  Status: EXCELLENT MATCH (< 0.1% difference)")
        elif max_diff < 1.0:
            print("  Status: GOOD MATCH (< 1% difference)")
        elif max_diff < 5.0:
            print("  Status: REASONABLE MATCH (< 5% difference)")
        else:
            print("  Status: SIGNIFICANT DIFFERENCES (> 5%)")

    print("=" * 80)


def save_gaspatchio_output(df: pl.DataFrame, output_dir: Path):
    """Save Gaspatchio output in a format comparable to lifelib."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save full results
    df.write_parquet(output_dir / "gaspatchio_results.parquet")

    # Create summary cashflows (aggregated across policies and time)
    summary = aggregate_gaspatchio_results(df)

    # Save summary as JSON-like CSV
    summary_df = pl.DataFrame([
        {"metric": k, "value": v} for k, v in summary.items()
    ])
    summary_df.write_csv(output_dir / "gaspatchio_summary.csv")

    print(f"Saved Gaspatchio output to: {output_dir}")
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Compare Gaspatchio and Lifelib IntegratedLife outputs (in-force, 8 model points)"
    )
    parser.add_argument(
        "--lifelib-output",
        type=str,
        help="Path to lifelib output directory (e.g., appliedlife/output/2025-11-25_...)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to save comparison results"
    )
    parser.add_argument(
        "--run-lifelib",
        action="store_true",
        help="Run lifelib model first (requires modelx)"
    )

    args = parser.parse_args()

    # Set up output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = script_dir.parent / "output" / f"comparison_{timestamp}"

    print("=" * 60)
    print("LIKE-FOR-LIKE MODEL COMPARISON")
    print("=" * 60)
    print(f"Expected configuration:")
    print(f"  - Run ID:       {LIFELIB_RUN_ID} (2023Q4IF in-force)")
    print(f"  - Model Points: {EXPECTED_MODEL_POINTS}")
    print(f"  - Scenarios:    {EXPECTED_SCENARIOS} (deterministic)")
    print(f"  - Product:      {EXPECTED_PRODUCT}")
    print("=" * 60)
    print("\nRunning Gaspatchio model...")

    # Run Gaspatchio model
    gaspatchio_df = run_gaspatchio_model()
    gaspatchio_summary = save_gaspatchio_output(gaspatchio_df, output_dir)

    # Load or run lifelib
    lifelib_results = {}

    lifelib_dir = None

    if args.lifelib_output:
        lifelib_dir = Path(args.lifelib_output)
        if not lifelib_dir.exists():
            print(f"Error: Lifelib output directory not found: {lifelib_dir}")
            return 1
        # Validate the specified output
        is_valid, msg = validate_lifelib_output(lifelib_dir)
        if not is_valid:
            print(f"Error: {msg}")
            print(f"\nTo generate matching lifelib output, run:")
            print(f"  uv run python appliedlife/scripts/run_integratedlife.py "
                  f"--run-id {LIFELIB_RUN_ID} --num-scenarios 1 --products gmxb --verbose")
            return 1
        print(f"\n{msg}")
    elif args.run_lifelib:
        print("\nRunning Lifelib model...")
        print("Note: Running lifelib requires modelx installation")
        print(f"Run manually with: uv run python appliedlife/scripts/run_integratedlife.py "
              f"--run-id {LIFELIB_RUN_ID} --num-scenarios 1 --products gmxb --verbose")
        return 1
    else:
        # Try to find most recent VALID lifelib output
        output_base = script_dir.parent / "output"
        lifelib_dir = find_valid_lifelib_output(output_base)

        if lifelib_dir is None:
            print("\nNo valid lifelib output found matching expected settings:")
            print(f"  - Run ID: {LIFELIB_RUN_ID}")
            print(f"  - Model Points: {EXPECTED_MODEL_POINTS}")
            print(f"  - Scenarios: {EXPECTED_SCENARIOS}")
            print(f"  - Product: {EXPECTED_PRODUCT}")
            print(f"\nRun lifelib first with matching settings:")
            print(f"  uv run python appliedlife/scripts/run_integratedlife.py "
                  f"--run-id {LIFELIB_RUN_ID} --num-scenarios 1 --products gmxb --verbose")
            return 1

    if lifelib_dir:
        print(f"\nLoading lifelib results from: {lifelib_dir}")
        is_valid, msg = validate_lifelib_output(lifelib_dir)
        print(f"Validation: {msg}")
        lifelib_results = load_lifelib_results(lifelib_dir)

    # Compare results
    comparisons = compare_metrics(gaspatchio_summary, lifelib_results)

    # Print report
    print_comparison_report(comparisons, gaspatchio_df)

    # Save comparison results
    if comparisons:
        comp_df = pl.DataFrame(comparisons)
        comp_df.write_csv(output_dir / "comparison_results.csv")
        print(f"\nComparison results saved to: {output_dir / 'comparison_results.csv'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
