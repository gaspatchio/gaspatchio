#!/usr/bin/env python3
# ruff: noqa: T201
"""Generate scaled model point sets from tutorial data.

Takes the tutorial's 8 model points, samples with replacement, and adds
random variation to numeric fields to create realistic synthetic populations.

Usage:
    uv run python evals/benchmarks/generate_model_points.py          # generate all
    uv run python evals/benchmarks/generate_model_points.py --level 4 --size 1000
"""

import argparse
from pathlib import Path

import numpy as np
import polars as pl

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TUTORIAL_DIR = REPO_ROOT / "tutorial"

# Source model point files
SOURCES = {
    "l4": TUTORIAL_DIR / "level-4-lifelib" / "base" / "model_points.parquet",
    "l5": TUTORIAL_DIR / "level-5-scenarios" / "base" / "model_points.parquet",
}

SIZES = [1_000, 10_000, 100_000]

# Fields to vary and their variation ranges
NUMERIC_VARIATIONS = {
    "age_at_entry": {"min": 20, "max": 75, "dtype": "int"},
    "policy_term": {"min": 60, "max": 360, "dtype": "int"},  # months
    "sum_assured": {"min": 50_000, "max": 2_000_000, "dtype": "int"},
    "premium_pp": {"min": 500, "max": 50_000, "dtype": "int"},
    "av_pp_init": {"min": 10_000, "max": 500_000, "dtype": "int"},
    "accum_prem_init_pp": {"min": 5_000, "max": 200_000, "dtype": "int"},
    "duration_mth": {"min": 1, "max": 180, "dtype": "int"},
}


def generate_model_points(
    source_mp: pl.DataFrame,
    n: int,
    seed: int = 42,
) -> pl.DataFrame:
    """Scale tutorial model points to N rows with realistic variation.

    Strategy:
    1. Sample from source rows with replacement (preserves product/plan mix)
    2. Add random variation to numeric fields (within realistic ranges)
    3. Assign new sequential point_ids
    """
    rng = np.random.default_rng(seed)
    n_source = len(source_mp)

    # Sample row indices with replacement
    indices = rng.integers(0, n_source, size=n)
    sampled = source_mp[indices.tolist()]

    # Add variation to numeric columns
    for col_name, spec in NUMERIC_VARIATIONS.items():
        if col_name not in sampled.columns:
            continue

        original = sampled[col_name].to_numpy()
        # ±30% variation, clipped to valid range
        noise = rng.normal(1.0, 0.3, size=n)
        varied = (original * noise).clip(spec["min"], spec["max"])

        if spec["dtype"] == "int":
            varied = varied.astype(int)

        sampled = sampled.with_columns(
            pl.Series(col_name, varied).cast(sampled[col_name].dtype)
        )

    # New sequential point_ids
    sampled = sampled.with_columns(
        pl.Series("point_id", list(range(1, n + 1))).cast(pl.Int64)
    )

    return sampled


def write_lifelib_csv(df: pl.DataFrame, output_path: Path) -> None:
    """Write model points in lifelib CSV format."""
    df.write_csv(output_path)


def main() -> None:
    """Generate all model point sets."""
    parser = argparse.ArgumentParser(description="Generate scaled model points")
    parser.add_argument("--level", type=int, help="Single level (4 or 5)")
    parser.add_argument("--size", type=int, help="Single size (1000, 10000, 100000)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: evals/benchmarks/model_points/)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else (
        Path(__file__).resolve().parent / "model_points"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    levels = {f"l{args.level}": SOURCES[f"l{args.level}"]} if args.level else SOURCES
    sizes = [args.size] if args.size else SIZES

    for level_key, source_path in levels.items():
        print(f"Loading source: {source_path}")
        source_mp = pl.read_parquet(source_path)
        print(f"  Source rows: {len(source_mp)}, columns: {source_mp.columns}")

        for size in sizes:
            out_path = output_dir / f"{level_key}_{size // 1000}k.parquet"
            print(f"  Generating {size:,} points → {out_path}")
            scaled = generate_model_points(source_mp, size)
            scaled.write_parquet(out_path)
            print(f"    Written: {out_path.stat().st_size / 1024:.0f} KB")
            # Also write lifelib-format CSV
            csv_path = out_path.with_suffix(".csv")
            print(f"    Writing lifelib CSV → {csv_path}")
            write_lifelib_csv(scaled, csv_path)

    print("Done.")


if __name__ == "__main__":
    main()
