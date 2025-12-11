# ABOUTME: Performance benchmarking script for assumption lookups.
# ABOUTME: Runs model with .profile() and categorizes timing by LOOKUP vs CALC.
# ruff: noqa: INP001, T201, D400, D415, E402, PGH003
# type: ignore
"""
Assumption Lookup Performance Benchmark.

Runs the applied_life model with profiling enabled to measure
lookup vs calculation time. This provides the detailed breakdown
needed for RFC 29 optimization planning.

Usage:
    # Default: 100k x 3 scenarios
    uv run python tests/scratch/scenarios/scripts/benchmarks.py

    # Custom scale
    uv run python tests/scratch/scenarios/scripts/benchmarks.py \
        --policies 10k --scenarios 3

    # Quick test
    uv run python tests/scratch/scenarios/scripts/benchmarks.py \
        --policies 1k --scenarios 1

    # With debug logging (shows Rust lookup details)
    uv run python tests/scratch/scenarios/scripts/benchmarks.py \
        --policies 1k --scenarios 1 --debug
"""

# Configure logging BEFORE any gaspatchio imports to capture Rust debug logs
import logging
import os
import sys

if "--debug" in sys.argv:
    # Enable Python logging for Rust bridge (pyo3_log)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(name)s | %(levelname)s | %(message)s",
    )
    # Also enable loguru debug for Python-side logs
    os.environ["LOGURU_LEVEL"] = "DEBUG"

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

# Add parent directory to path for imports
SCRIPT_DIR = Path(__file__).parent
SCENARIOS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCENARIOS_DIR))

from model_applied_life import (
    main as run_model,
)
from stochastic_scenarios import (
    generate_stochastic_returns,
)

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.scenarios import with_scenarios


def load_model_points(size: str) -> pl.DataFrame:
    """Load model points of specified size."""
    size_map = {
        "small": "model_points.parquet",  # 8 policies
        "1k": "model_points_1k.parquet",
        "10k": "model_points_10k.parquet",
        "100k": "model_points_100k.parquet",
    }
    filename = size_map.get(size.lower(), size_map["100k"])
    path = SCENARIOS_DIR / filename
    if not path.exists():
        msg = f"Model points file not found: {path}"
        raise FileNotFoundError(msg)
    return pl.read_parquet(path)


def categorize_operation(node_name: str) -> str:
    """Categorize a profile node as LOOKUP, CALCULATION, or OTHER.

    Lookups are identified by the column names that come from Table.lookup().
    These are specific to the applied_life model's assumption table lookups.
    """
    node_lower = node_name.lower()

    # Lookup columns - these are outputs from Table.lookup() in applied_life model
    # Each corresponds to an assumption table lookup
    lookup_columns = [
        "base_mort_rate",  # mortality_select.lookup
        "mort_scalar",  # mortality_scalars.lookup
        "base_lapse_rate",  # lapse_rates.lookup
        "inv_return_mth",  # inv_returns_table.lookup
        "surr_charge_rate",  # surrender_charges.lookup
        "disc_rate",  # risk_free_rates.lookup
    ]

    # Check if this is a with_column containing a lookup column
    for col in lookup_columns:
        if col in node_lower:
            return "LOOKUP"

    # These are overhead/setup, not calculations
    other_patterns = [
        "simple-projection",
        "select",
        "project",
        "cache",
        "sink",
        "source",
        "scan",
        "filter",
    ]

    for pattern in other_patterns:
        if pattern in node_lower:
            return "OTHER"

    return "CALCULATION"


def analyze_profile(profile_df: pl.DataFrame) -> dict:
    """Analyze profile DataFrame and categorize timing.

    Args:
        profile_df: DataFrame from ActuarialFrame.profile() with columns:
                   node, start, end (nanoseconds)

    Returns:
        Dictionary with timing breakdown by category

    """
    if profile_df.is_empty():
        return {
            "total_time_s": 0.0,
            "categories": {},
            "top_operations": [],
        }

    # Calculate duration for each operation
    profile_df = profile_df.with_columns(
        ((pl.col("end") - pl.col("start")) / 1e9).alias("duration_s")
    )

    # Categorize each operation
    profile_df = profile_df.with_columns(
        pl.col("node")
        .map_elements(categorize_operation, return_dtype=pl.Utf8)
        .alias("category")
    )

    total_time = profile_df["duration_s"].sum()

    # Aggregate by category
    category_times = (
        profile_df.group_by("category")
        .agg(pl.col("duration_s").sum().alias("time_s"))
        .sort("time_s", descending=True)
    )

    categories = {}
    for row in category_times.iter_rows(named=True):
        cat = row["category"]
        time_s = row["time_s"]
        pct = (time_s / total_time * 100) if total_time > 0 else 0
        categories[cat] = {"time_s": time_s, "pct": pct}

    # Get top operations by time
    top_ops = (
        profile_df.sort("duration_s", descending=True)
        .head(10)
        .select(["node", "category", "duration_s"])
    )

    top_operations = []
    for row in top_ops.iter_rows(named=True):
        pct = (row["duration_s"] / total_time * 100) if total_time > 0 else 0
        top_operations.append(
            {
                "node": row["node"][:60],  # Truncate long names
                "category": row["category"],
                "time_s": row["duration_s"],
                "pct": pct,
            }
        )

    return {
        "total_time_s": total_time,
        "categories": categories,
        "top_operations": top_operations,
        "profile_df": profile_df,
    }


def run_benchmark(
    n_policies: str = "100k",
    n_scenarios: int = 3,
    seed: int = 12345,
) -> dict:
    """Run the benchmark and return timing analysis.

    Args:
        n_policies: Size of model points ("small", "1k", "10k", "100k")
        n_scenarios: Number of scenarios to expand
        seed: Random seed for stochastic returns

    Returns:
        Dictionary with benchmark results

    """
    print("\n" + "=" * 70)
    print("ASSUMPTION LOOKUP PERFORMANCE BENCHMARK")
    print("=" * 70)

    # Load model points
    print(f"\n1. Loading model points ({n_policies})...")
    mp = load_model_points(n_policies)
    print(f"   Loaded {len(mp):,} policies")

    # Generate stochastic returns
    print(f"\n2. Generating stochastic returns ({n_scenarios} scenarios)...")
    stochastic_returns = generate_stochastic_returns(
        n_scenarios=n_scenarios,
        n_months=180,
        seed=seed,
    )

    # Create ActuarialFrame and expand with scenarios
    print("\n3. Expanding with scenarios...")
    af = ActuarialFrame(mp, mode="debug")  # Debug mode for tracing
    af = with_scenarios(af, list(range(1, n_scenarios + 1)))
    total_rows = len(mp) * n_scenarios
    print(f"   Total rows: {total_rows:,}")

    # Run the model
    print("\n4. Running model...")
    model_start = time.time()
    result_af = run_model(af, scenario_returns_override=stochastic_returns)
    model_elapsed = time.time() - model_start
    print(f"   Model execution: {model_elapsed:.2f}s")

    # Profile the collection
    print("\n5. Profiling collection...")
    profile_start = time.time()
    result_df, profile_df = result_af.profile()
    profile_elapsed = time.time() - profile_start
    print(f"   Collection + profiling: {profile_elapsed:.2f}s")

    # Analyze the profile
    print("\n6. Analyzing profile...")
    analysis = analyze_profile(profile_df)

    # Calculate lookup count estimate
    # From RFC: 6 main lookups x rows x timesteps
    n_timesteps = 180
    estimated_lookups = 6 * total_rows * n_timesteps
    throughput = (
        estimated_lookups / analysis["total_time_s"]
        if analysis["total_time_s"] > 0
        else 0
    )

    return {
        "n_policies": n_policies,
        "n_scenarios": n_scenarios,
        "total_rows": total_rows,
        "model_time_s": model_elapsed,
        "profile_time_s": profile_elapsed,
        "estimated_lookups": estimated_lookups,
        "throughput_per_sec": throughput,
        **analysis,
    }


def print_results(results: dict) -> None:
    """Print benchmark results in RFC-style format."""
    print("\n" + "=" * 70)
    print("BENCHMARK RESULTS")
    print("=" * 70)

    print("\nConfiguration:")
    print(f"  Policies:    {results['n_policies']}")
    print(f"  Scenarios:   {results['n_scenarios']}")
    print(f"  Total rows:  {results['total_rows']:,}")

    # Use wall time (profile_time_s) with profile percentages for realistic breakdown
    wall_time = results["profile_time_s"]
    ms_per_row = (wall_time / results["total_rows"]) * 1000

    ns_per_row = ms_per_row * 1_000_000

    print("\nTiming Summary:")
    print(f"  Model execution:  {results['model_time_s']:.2f}s")
    print(f"  Collection time:  {results['profile_time_s']:.2f}s")
    print(f"  Time per row:     {ms_per_row:.4f} ms/row")
    print(f"  Time per row:     {ns_per_row:,.0f} ns/row")

    print("\nTiming by Category (extrapolated from profile ratios):")
    print("-" * 55)
    print(f"{'Category':<15} {'Time (s)':<12} {'% of Total':<12}")
    print("-" * 55)
    for cat, data in sorted(
        results["categories"].items(), key=lambda x: -x[1]["time_s"]
    ):
        # Extrapolate: apply profile percentage to wall time
        extrapolated_time = wall_time * (data["pct"] / 100.0)
        print(f"{cat:<15} {extrapolated_time:<12.2f} {data['pct']:<12.1f}%")
    print("-" * 55)
    print(f"{'TOTAL':<15} {wall_time:<12.2f} {'100.0':<12}%")

    print("\nTop Operations by Time:")
    print("-" * 70)
    print(f"{'Operation':<45} {'Category':<12} {'Time':<8} {'%':<6}")
    print("-" * 70)
    for op in results["top_operations"]:
        print(
            f"{op['node']:<45} {op['category']:<12} "
            f"{op['time_s']:<8.2f} {op['pct']:<6.1f}%"
        )

    print("\nLookup Throughput:")
    print(f"  Estimated lookups: {results['estimated_lookups']:,}")
    print(f"  Throughput:        {results['throughput_per_sec']:,.0f} lookups/sec")

    print("\n" + "=" * 70)


def get_git_info() -> dict:
    """Get current git commit and branch info."""
    try:
        commit = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        branch = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return {"commit": "unknown", "branch": "unknown"}
    else:
        return {"commit": commit, "branch": branch}


def save_results(results: dict, output_path: Path) -> None:
    """Save benchmark results to JSON file."""
    wall_time = results["profile_time_s"]
    ms_per_row = (wall_time / results["total_rows"]) * 1000
    ns_per_row = ms_per_row * 1_000_000

    # Build serializable output
    output = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git": get_git_info(),
        "config": {
            "policies": results["n_policies"],
            "scenarios": results["n_scenarios"],
            "total_rows": results["total_rows"],
            "seed": results.get("seed", 12345),
        },
        "timing": {
            "model_execution_s": results["model_time_s"],
            "collection_s": results["profile_time_s"],
            "ms_per_row": round(ms_per_row, 4),
            "ns_per_row": round(ns_per_row),
        },
        "categories": {
            cat: {
                "time_s": round(wall_time * (data["pct"] / 100.0), 2),
                "pct": round(data["pct"], 1),
            }
            for cat, data in results["categories"].items()
        },
        "top_operations": [
            {
                "name": op["node"],
                "category": op["category"],
                "pct": round(op["pct"], 1),
            }
            for op in results["top_operations"][:10]
        ],
        "throughput": {
            "estimated_lookups": results["estimated_lookups"],
            "lookups_per_sec": round(results["throughput_per_sec"]),
        },
    }

    # Append to file if it exists (JSONL format), otherwise create new
    with output_path.open("a") as f:
        f.write(json.dumps(output) + "\n")

    print(f"\nResults appended to: {output_path}")


def main() -> None:
    """Run the benchmark with command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Assumption Lookup Performance Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--policies",
        type=str,
        default="100k",
        choices=["small", "1k", "10k", "100k"],
        help="Model points size (default: 100k)",
    )
    parser.add_argument(
        "--scenarios",
        type=int,
        default=3,
        help="Number of scenarios (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=12345,
        help="Random seed for stochastic returns (default: 12345)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output file for results (JSONL format, appends to existing)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (shows Rust lookup details)",
    )

    args = parser.parse_args()

    results = run_benchmark(
        n_policies=args.policies,
        n_scenarios=args.scenarios,
        seed=args.seed,
    )

    print_results(results)

    if args.output:
        save_results(results, args.output)


if __name__ == "__main__":
    main()
