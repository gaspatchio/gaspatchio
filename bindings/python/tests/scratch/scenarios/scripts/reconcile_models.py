"""
Variable-by-Variable Model Reconciliation

Compares Gaspatchio model output against lifelib IntegratedLife,
variable by variable, to support incremental model building.

Works with empty or partial models - only compares variables that exist in both.

Usage:
    # Run reconciliation (auto-finds valid lifelib output)
    uv run python appliedlife/scripts/reconcile_models.py

    # With specific lifelib output
    uv run python appliedlife/scripts/reconcile_models.py --lifelib-output appliedlife/output/...

    # First run lifelib with matching settings:
    uv run python appliedlife/scripts/run_integratedlife.py --run-id 2 --num-scenarios 1 --products gmxb --verbose
"""
import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_dir = script_dir.parent.parent
sys.path.insert(0, str(project_dir))

# Expected configuration for like-for-like comparison
LIFELIB_RUN_ID = 2
EXPECTED_MODEL_POINTS = 8
EXPECTED_SCENARIOS = 1
EXPECTED_PRODUCT = "GMXB"

# Tolerance for "matching" (relative difference)
TOLERANCE_PCT = 0.01  # 0.01% = essentially exact match


@dataclass
class VariableMapping:
    """Maps a Gaspatchio variable to its lifelib equivalent."""
    gaspatchio_name: str
    lifelib_name: str
    lifelib_file: str  # 'pols', 'cf', or 'pv'
    comparison_type: str  # 'time_series' or 'total_by_point'
    description: str


# Variable mappings between Gaspatchio and lifelib
# Note: model_applied_life.py uses these column names
VARIABLE_MAPPINGS = [
    # Policy counts (time series, aggregated across points)
    VariableMapping("pols_if", "pols_if", "pols", "time_series", "Policies in force"),
    VariableMapping("pols_death", "pols_death", "pols", "time_series", "Deaths"),
    VariableMapping("pols_lapse", "pols_lapse", "pols", "time_series", "Lapses"),
    VariableMapping("pols_maturity", "pols_maturity", "pols", "time_series", "Maturities"),
    VariableMapping("pols_new_biz", "pols_new_biz", "pols", "time_series", "New business"),

    # Cashflows (time series, aggregated across points)
    VariableMapping("premiums", "Premiums", "cf", "time_series", "Premium income"),
    VariableMapping("claims", "Claims", "cf", "time_series", "Total claims"),
    VariableMapping("expenses", "Expenses", "cf", "time_series", "Total expenses"),
    VariableMapping("commissions", "Commissions", "cf", "time_series", "Commissions"),
    VariableMapping("net_cf", "Net Cashflow", "cf", "time_series", "Net cashflow"),

    # Present values (total by model point)
    VariableMapping("pv_premiums", "Premiums", "pv", "total_by_point", "PV Premiums"),
    VariableMapping("pv_claims", "Death", "pv", "total_by_point", "PV Death claims"),
    VariableMapping("pv_expenses", "Expenses", "pv", "total_by_point", "PV Expenses"),
    VariableMapping("pv_commissions", "Commissions", "pv", "total_by_point", "PV Commissions"),
    VariableMapping("pv_net_cf", "Net Cashflow", "pv", "total_by_point", "PV Net cashflow"),
]


@dataclass
class ReconciliationResult:
    """Result of comparing a single variable."""
    variable: str
    description: str
    status: str  # 'MATCH', 'MISMATCH', 'GASPATCHIO_MISSING', 'LIFELIB_MISSING'
    max_abs_diff: float | None
    max_pct_diff: float | None
    worst_period: int | None
    gaspatchio_total: float | None
    lifelib_total: float | None
    details: str


def validate_lifelib_output(output_dir: Path) -> tuple[bool, str]:
    """Validate that lifelib output matches expected settings."""
    summary_path = output_dir / "run_summary.txt"
    if not summary_path.exists():
        return False, f"No run_summary.txt found in {output_dir}"

    content = summary_path.read_text()
    errors = []

    if f"Run ID: {LIFELIB_RUN_ID}" not in content:
        errors.append(f"Expected Run ID: {LIFELIB_RUN_ID}")
    if f"({EXPECTED_MODEL_POINTS} points)" not in content:
        errors.append(f"Expected {EXPECTED_MODEL_POINTS} model points")
    if f"({EXPECTED_SCENARIOS} scenario" not in content:
        errors.append(f"Expected {EXPECTED_SCENARIOS} scenario(s)")
    if EXPECTED_PRODUCT not in content:
        errors.append(f"Expected product: {EXPECTED_PRODUCT}")

    if errors:
        return False, f"Lifelib output mismatch: {'; '.join(errors)}"
    return True, "Lifelib output validated successfully"


def find_valid_lifelib_output(output_base: Path) -> Path | None:
    """Find the most recent lifelib output that matches expected settings."""
    if not output_base.exists():
        return None

    lifelib_dirs = sorted([
        d for d in output_base.iterdir()
        if d.is_dir() and not d.name.startswith("comparison_") and not d.name.startswith("reconcile_")
    ], reverse=True)

    for d in lifelib_dirs:
        is_valid, _ = validate_lifelib_output(d)
        if is_valid:
            return d
    return None


def run_gaspatchio_model(model_name: str = "model_applied_life") -> pl.DataFrame | None:
    """
    Run the Gaspatchio model and return results, or None if it fails.

    Args:
        model_name: Name of the model module (without .py), e.g., 'model_applied_life'
    """
    try:
        import importlib

        # Import the specified model
        model_module = importlib.import_module(f"appliedlife.{model_name}")

        from gaspatchio_core import ActuarialFrame

        mp_path = script_dir.parent / "model_points.parquet"
        if not mp_path.exists():
            print(f"  Model points file not found: {mp_path}")
            return None

        # model_applied_life is self-contained - it loads its own assumptions
        mp = pl.read_parquet(mp_path)
        af = ActuarialFrame(mp)
        result_af = model_module.main(af)
        return result_af.collect()

    except Exception as e:
        print(f"  Gaspatchio model error: {e}")
        import traceback
        traceback.print_exc()
        return None


def load_lifelib_data(lifelib_dir: Path) -> dict:
    """Load lifelib output files into a dictionary."""
    data = {}

    # Load policy counts (time series by month)
    pols_path = lifelib_dir / "gmxb_pols.csv"
    if pols_path.exists():
        df = pl.read_csv(pols_path)
        # First column is month index (unnamed)
        data["pols"] = df.rename({"": "month"}) if "" in df.columns else df

    # Load cashflows (time series by month)
    cf_path = lifelib_dir / "gmxb_cf.csv"
    if cf_path.exists():
        df = pl.read_csv(cf_path)
        data["cf"] = df.rename({"": "month"}) if "" in df.columns else df

    # Load present values (by model point)
    pv_path = lifelib_dir / "gmxb_pv.csv"
    if pv_path.exists():
        data["pv"] = pl.read_csv(pv_path)

    return data


def aggregate_gaspatchio_time_series(df: pl.DataFrame, column: str) -> pl.Series | None:
    """
    Aggregate a Gaspatchio time series column across all model points.

    Gaspatchio has list columns (one list per model point).
    We need to sum across model points at each time step.
    """
    if column not in df.columns:
        return None

    try:
        # Get the column
        col = df[column]

        # Check if it's a list column
        if not isinstance(col.dtype, pl.List):
            return None

        # Simple approach: extract lists and sum by time index
        lists = df[column].to_list()
        if not lists:
            return None

        # Find the max length
        max_len = max(len(lst) for lst in lists)

        # Sum at each time step
        result = []
        for t in range(max_len):
            total = 0.0
            for lst in lists:
                if t < len(lst):
                    total += lst[t]
            result.append(total)

        return pl.Series("value", result)

    except Exception as e:
        print(f"  Warning: Could not aggregate {column}: {e}")
        return None


def get_gaspatchio_pv_by_point(df: pl.DataFrame, column: str) -> pl.Series | None:
    """Get PV totals by model point from Gaspatchio output."""
    if column not in df.columns:
        return None

    try:
        col = df[column]
        if isinstance(col.dtype, pl.List):
            # Sum each list to get total per point
            return df.select(pl.col(column).list.sum())[column]
        else:
            return col
    except Exception as e:
        print(f"  Warning: Could not get PV for {column}: {e}")
        return None


def compare_time_series(
    gaspatchio_series: pl.Series,
    lifelib_series: pl.Series,
    variable_name: str
) -> ReconciliationResult:
    """Compare two time series and return reconciliation result."""

    # Align lengths (use shorter length)
    min_len = min(len(gaspatchio_series), len(lifelib_series))
    g_vals = gaspatchio_series[:min_len].to_list()
    l_vals = lifelib_series[:min_len].to_list()

    # Calculate differences
    max_abs_diff = 0.0
    max_pct_diff = 0.0
    worst_period = 0

    for t in range(min_len):
        g_val = g_vals[t] if g_vals[t] is not None else 0.0
        l_val = l_vals[t] if l_vals[t] is not None else 0.0

        abs_diff = abs(g_val - l_val)
        if abs(l_val) > 1e-10:
            pct_diff = abs(abs_diff / l_val) * 100
        elif abs(g_val) > 1e-10:
            pct_diff = 100.0  # lifelib is 0, gaspatchio is not
        else:
            pct_diff = 0.0

        if pct_diff > max_pct_diff:
            max_pct_diff = pct_diff
            max_abs_diff = abs_diff
            worst_period = t

    # Determine status
    if max_pct_diff <= TOLERANCE_PCT:
        status = "MATCH"
        details = f"Max diff {max_pct_diff:.4f}% at t={worst_period}"
    else:
        status = "MISMATCH"
        details = f"Max diff {max_pct_diff:.2f}% at t={worst_period}"

    g_total = sum(v for v in g_vals if v is not None)
    l_total = sum(v for v in l_vals if v is not None)

    return ReconciliationResult(
        variable=variable_name,
        description="",
        status=status,
        max_abs_diff=max_abs_diff,
        max_pct_diff=max_pct_diff,
        worst_period=worst_period,
        gaspatchio_total=g_total,
        lifelib_total=l_total,
        details=details
    )


def compare_totals_by_point(
    gaspatchio_series: pl.Series,
    lifelib_series: pl.Series,
    variable_name: str
) -> ReconciliationResult:
    """Compare PV totals by model point."""

    g_vals = gaspatchio_series.to_list()
    l_vals = lifelib_series.to_list()

    # Calculate differences
    max_abs_diff = 0.0
    max_pct_diff = 0.0
    worst_point = 0

    for i in range(min(len(g_vals), len(l_vals))):
        g_val = g_vals[i] if g_vals[i] is not None else 0.0
        l_val = l_vals[i] if l_vals[i] is not None else 0.0

        abs_diff = abs(g_val - l_val)
        if abs(l_val) > 1e-10:
            pct_diff = abs(abs_diff / l_val) * 100
        elif abs(g_val) > 1e-10:
            pct_diff = 100.0
        else:
            pct_diff = 0.0

        if pct_diff > max_pct_diff:
            max_pct_diff = pct_diff
            max_abs_diff = abs_diff
            worst_point = i + 1  # 1-indexed point_id

    if max_pct_diff <= TOLERANCE_PCT:
        status = "MATCH"
        details = f"Max diff {max_pct_diff:.4f}% at point {worst_point}"
    else:
        status = "MISMATCH"
        details = f"Max diff {max_pct_diff:.2f}% at point {worst_point}"

    g_total = sum(v for v in g_vals if v is not None)
    l_total = sum(v for v in l_vals if v is not None)

    return ReconciliationResult(
        variable=variable_name,
        description="",
        status=status,
        max_abs_diff=max_abs_diff,
        max_pct_diff=max_pct_diff,
        worst_period=worst_point,
        gaspatchio_total=g_total,
        lifelib_total=l_total,
        details=details
    )


def reconcile_variable(
    mapping: VariableMapping,
    gaspatchio_df: pl.DataFrame | None,
    lifelib_data: dict
) -> ReconciliationResult:
    """Reconcile a single variable between Gaspatchio and lifelib."""

    # Check if Gaspatchio has this variable
    if gaspatchio_df is None or mapping.gaspatchio_name not in gaspatchio_df.columns:
        return ReconciliationResult(
            variable=mapping.gaspatchio_name,
            description=mapping.description,
            status="GASPATCHIO_MISSING",
            max_abs_diff=None,
            max_pct_diff=None,
            worst_period=None,
            gaspatchio_total=None,
            lifelib_total=None,
            details="Variable not in Gaspatchio output"
        )

    # Check if lifelib has this variable
    lifelib_df = lifelib_data.get(mapping.lifelib_file)
    if lifelib_df is None or mapping.lifelib_name not in lifelib_df.columns:
        return ReconciliationResult(
            variable=mapping.gaspatchio_name,
            description=mapping.description,
            status="LIFELIB_MISSING",
            max_abs_diff=None,
            max_pct_diff=None,
            worst_period=None,
            gaspatchio_total=None,
            lifelib_total=None,
            details="Variable not in lifelib output"
        )

    # Get the data
    if mapping.comparison_type == "time_series":
        gaspatchio_series = aggregate_gaspatchio_time_series(gaspatchio_df, mapping.gaspatchio_name)
        lifelib_series = lifelib_df[mapping.lifelib_name]

        if gaspatchio_series is None:
            return ReconciliationResult(
                variable=mapping.gaspatchio_name,
                description=mapping.description,
                status="GASPATCHIO_MISSING",
                max_abs_diff=None,
                max_pct_diff=None,
                worst_period=None,
                gaspatchio_total=None,
                lifelib_total=None,
                details="Could not aggregate Gaspatchio time series"
            )

        result = compare_time_series(gaspatchio_series, lifelib_series, mapping.gaspatchio_name)

    else:  # total_by_point
        gaspatchio_series = get_gaspatchio_pv_by_point(gaspatchio_df, mapping.gaspatchio_name)
        lifelib_series = lifelib_df[mapping.lifelib_name]

        if gaspatchio_series is None:
            return ReconciliationResult(
                variable=mapping.gaspatchio_name,
                description=mapping.description,
                status="GASPATCHIO_MISSING",
                max_abs_diff=None,
                max_pct_diff=None,
                worst_period=None,
                gaspatchio_total=None,
                lifelib_total=None,
                details="Could not get Gaspatchio PV"
            )

        result = compare_totals_by_point(gaspatchio_series, lifelib_series, mapping.gaspatchio_name)

    result.description = mapping.description
    return result


def print_reconciliation_report(results: list[ReconciliationResult], gaspatchio_df: pl.DataFrame | None):
    """Print a formatted reconciliation report."""

    print("\n" + "=" * 90)
    print("VARIABLE-BY-VARIABLE RECONCILIATION REPORT")
    print("=" * 90)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if gaspatchio_df is not None:
        print(f"Gaspatchio model points: {len(gaspatchio_df)}")
        if "month" in gaspatchio_df.columns:
            try:
                max_months = gaspatchio_df["month"].list.len().max()
                print(f"Gaspatchio projection months: {max_months}")
            except:
                pass
        print(f"Gaspatchio columns: {len(gaspatchio_df.columns)}")
    else:
        print("Gaspatchio: No output (model not run or failed)")

    # Count by status
    matches = [r for r in results if r.status == "MATCH"]
    mismatches = [r for r in results if r.status == "MISMATCH"]
    g_missing = [r for r in results if r.status == "GASPATCHIO_MISSING"]
    l_missing = [r for r in results if r.status == "LIFELIB_MISSING"]

    print(f"\nSummary: {len(matches)} matched, {len(mismatches)} mismatched, "
          f"{len(g_missing)} not in Gaspatchio, {len(l_missing)} not in lifelib")

    # Print matches
    if matches:
        print("\n" + "-" * 90)
        print("MATCHED VARIABLES")
        print("-" * 90)
        print(f"{'Variable':<20} {'Description':<25} {'Gaspatchio':>15} {'Lifelib':>15} {'Details':<20}")
        print("-" * 90)
        for r in matches:
            g_str = f"{r.gaspatchio_total:,.0f}" if r.gaspatchio_total is not None else "N/A"
            l_str = f"{r.lifelib_total:,.0f}" if r.lifelib_total is not None else "N/A"
            print(f"{r.variable:<20} {r.description:<25} {g_str:>15} {l_str:>15} {r.details:<20}")

    # Print mismatches
    if mismatches:
        print("\n" + "-" * 90)
        print("MISMATCHED VARIABLES (need investigation)")
        print("-" * 90)
        print(f"{'Variable':<20} {'Description':<20} {'Gaspatchio':>15} {'Lifelib':>15} {'Max Diff %':>12} {'Details':<15}")
        print("-" * 90)
        for r in mismatches:
            g_str = f"{r.gaspatchio_total:,.0f}" if r.gaspatchio_total is not None else "N/A"
            l_str = f"{r.lifelib_total:,.0f}" if r.lifelib_total is not None else "N/A"
            pct_str = f"{r.max_pct_diff:.2f}%" if r.max_pct_diff is not None else "N/A"
            print(f"{r.variable:<20} {r.description:<20} {g_str:>15} {l_str:>15} {pct_str:>12} {r.details:<15}")

    # Print missing from Gaspatchio
    if g_missing:
        print("\n" + "-" * 90)
        print("NOT YET IN GASPATCHIO (to be implemented)")
        print("-" * 90)
        for r in g_missing:
            print(f"  - {r.variable}: {r.description}")

    # Print missing from lifelib
    if l_missing:
        print("\n" + "-" * 90)
        print("NOT IN LIFELIB OUTPUT")
        print("-" * 90)
        for r in l_missing:
            print(f"  - {r.variable}: {r.description}")

    # Overall status
    print("\n" + "=" * 90)
    if len(mismatches) == 0 and len(matches) > 0:
        print("STATUS: ALL IMPLEMENTED VARIABLES MATCH")
    elif len(mismatches) > 0:
        print(f"STATUS: {len(mismatches)} VARIABLES NEED INVESTIGATION")
    else:
        print("STATUS: NO VARIABLES COMPARED (model may be empty)")
    print("=" * 90)


def main():
    parser = argparse.ArgumentParser(
        description="Variable-by-variable reconciliation between Gaspatchio and lifelib"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="model_applied_life",
        help="Gaspatchio model module name (default: model_applied_life)."
    )
    parser.add_argument(
        "--lifelib-output",
        type=str,
        help="Path to lifelib output directory"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Directory to save reconciliation results"
    )

    args = parser.parse_args()

    # Set up output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = script_dir.parent / "output" / f"reconcile_{timestamp}"

    print("=" * 60)
    print("VARIABLE-BY-VARIABLE RECONCILIATION")
    print("=" * 60)
    print(f"Gaspatchio model: {args.model}")
    print(f"Expected configuration:")
    print(f"  - Run ID:       {LIFELIB_RUN_ID} (2023Q4IF in-force)")
    print(f"  - Model Points: {EXPECTED_MODEL_POINTS}")
    print(f"  - Scenarios:    {EXPECTED_SCENARIOS} (deterministic)")
    print(f"  - Product:      {EXPECTED_PRODUCT}")
    print(f"  - Tolerance:    {TOLERANCE_PCT}%")
    print("=" * 60)

    # Find/validate lifelib output
    if args.lifelib_output:
        lifelib_dir = Path(args.lifelib_output)
        if not lifelib_dir.exists():
            print(f"\nError: Lifelib output directory not found: {lifelib_dir}")
            return 1
        is_valid, msg = validate_lifelib_output(lifelib_dir)
        if not is_valid:
            print(f"\nError: {msg}")
            return 1
    else:
        output_base = script_dir.parent / "output"
        lifelib_dir = find_valid_lifelib_output(output_base)
        if lifelib_dir is None:
            print("\nNo valid lifelib output found. Run lifelib first:")
            print(f"  uv run python appliedlife/scripts/run_integratedlife.py "
                  f"--run-id {LIFELIB_RUN_ID} --num-scenarios 1 --products gmxb --verbose")
            return 1

    print(f"\nLifelib output: {lifelib_dir}")

    # Load lifelib data
    print("Loading lifelib data...")
    lifelib_data = load_lifelib_data(lifelib_dir)

    # Run Gaspatchio model
    print(f"\nRunning Gaspatchio model ({args.model})...")
    gaspatchio_df = run_gaspatchio_model(args.model)

    if gaspatchio_df is not None:
        print(f"  Output shape: {gaspatchio_df.shape}")
        output_dir.mkdir(parents=True, exist_ok=True)
        gaspatchio_df.write_parquet(output_dir / "gaspatchio_output.parquet")

    # Reconcile each variable
    print("\nReconciling variables...")
    results = []
    for mapping in VARIABLE_MAPPINGS:
        result = reconcile_variable(mapping, gaspatchio_df, lifelib_data)
        results.append(result)

    # Print report
    print_reconciliation_report(results, gaspatchio_df)

    # Save results
    if results:
        output_dir.mkdir(parents=True, exist_ok=True)
        results_df = pl.DataFrame([
            {
                "variable": r.variable,
                "description": r.description,
                "status": r.status,
                "max_pct_diff": r.max_pct_diff,
                "gaspatchio_total": r.gaspatchio_total,
                "lifelib_total": r.lifelib_total,
                "details": r.details
            }
            for r in results
        ])
        results_df.write_csv(output_dir / "reconciliation_results.csv")
        print(f"\nResults saved to: {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
