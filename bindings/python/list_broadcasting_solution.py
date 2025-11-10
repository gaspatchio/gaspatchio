# ruff: noqa: T201, PD901, ANN201, ANN401, PLR0913, E501, PLR2004
"""
ABOUTME: Demonstration of working solution for list vs scalar conditionals.

ABOUTME: Shows explode/re-aggregate pattern as the recommended approach.
"""

from datetime import datetime
from typing import Any

import polars as pl


def conditional_list_vs_scalar_explode(
    df: pl.DataFrame,
    list_col: str,
    scalar_col: str,
    result_col: str,
    then_col: str,
    otherwise_value: Any,
    comparison_multiplier: int = 12,
) -> pl.DataFrame:
    """
    Apply element-wise conditional comparing list elements to scalar values.

    Uses explode/re-aggregate pattern with pure Polars operations.

    Args:
        df: Input DataFrame
        list_col: Name of list column to iterate over (e.g., "month")
        scalar_col: Name of scalar column to broadcast (e.g., "policy_term")
        result_col: Name of output column (e.g., "pols_maturity")
        then_col: Column to use when condition is True (e.g., "pols_if")
        otherwise_value: Value when condition is False (e.g., 0)
        comparison_multiplier: Multiply scalar by this before comparing (e.g., 12 for months)

    Returns:
        DataFrame with result_col added as a list column

    """
    return (
        df.with_row_index("_row_id")
        .explode([list_col, then_col])
        .with_columns(
            **{
                result_col: pl.when(
                    pl.col(list_col) == pl.col(scalar_col) * comparison_multiplier
                )
                .then(pl.col(then_col))
                .otherwise(otherwise_value)
            }
        )
        .group_by("_row_id", maintain_order=True)
        .agg(
            [
                pl.col(list_col),
                pl.col(scalar_col).first(),
                pl.col(then_col),
                pl.col(result_col),
            ]
        )
        .drop("_row_id")
    )


def demo_single_row():
    """Demonstrate the solution with a single row."""
    print("\n" + "=" * 80)
    print("DEMO 1: Single Row - Policy Term = 1 year")
    print("=" * 80 + "\n")

    df = pl.DataFrame(
        {
            "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
            "policy_term": [1],  # 1 year = 12 months
            "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88]],
        }
    )

    print("Input DataFrame:")
    print(df)
    print()

    result = conditional_list_vs_scalar_explode(
        df=df,
        list_col="month",
        scalar_col="policy_term",
        result_col="pols_maturity",
        then_col="pols_if",
        otherwise_value=0,
        comparison_multiplier=12,
    )

    print("Result DataFrame:")
    print(result)
    print()

    print("Exploded view of pols_maturity:")
    print(result.select(pl.col("pols_maturity").list.explode()).head(15))
    print()

    print("Expected: All zeros except at month 12 which should be 88")


def demo_multiple_rows():
    """Demonstrate with multiple rows."""
    print("\n" + "=" * 80)
    print("DEMO 2: Multiple Rows - Different Policy Terms")
    print("=" * 80 + "\n")

    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term": [1, 2, 0],  # 1 year, 2 years, 0 years (immediate)
            "pols_if": [
                [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                [200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176],
                [300, 297, 294, 291, 288, 285, 282, 279, 276, 273, 270, 267, 264],
            ],
        }
    )

    print("Input DataFrame:")
    print(df)
    print()

    result = conditional_list_vs_scalar_explode(
        df=df,
        list_col="month",
        scalar_col="policy_term",
        result_col="pols_maturity",
        then_col="pols_if",
        otherwise_value=0,
        comparison_multiplier=12,
    )

    print("Result DataFrame:")
    print(result)
    print()

    print("Row 0 (term=1y, maturity at month 12):")
    exploded = (
        result.filter(pl.int_range(pl.len()) == 0)
        .select(pl.col("pols_maturity").list.explode().alias("value"))
        .with_row_index("month")
    )
    print(exploded)
    print()

    print("Row 1 (term=2y, maturity at month 24 - out of range):")
    exploded = (
        result.filter(pl.int_range(pl.len()) == 1)
        .select(pl.col("pols_maturity").list.explode().alias("value"))
        .with_row_index("month")
    )
    print(exploded)
    print()

    print("Row 2 (term=0y, maturity at month 0):")
    exploded = (
        result.filter(pl.int_range(pl.len()) == 2)
        .select(pl.col("pols_maturity").list.explode().alias("value"))
        .with_row_index("month")
    )
    print(exploded)
    print()


def benchmark_performance():
    """Benchmark the performance of the solution."""
    print("\n" + "=" * 80)
    print("BENCHMARK: Performance with Large Dataset")
    print("=" * 80 + "\n")

    import time

    # Create larger dataset
    n_rows = 10000
    list_len = 120  # 10 years monthly

    df = pl.DataFrame(
        {
            "month": [list(range(list_len))] * n_rows,
            "policy_term": list(range(1, n_rows + 1)),  # varying terms
            "pols_if": [[100 - i for i in range(list_len)]] * n_rows,
        }
    )

    print(f"Dataset: {n_rows:,} rows, {list_len} elements per list")
    print(f"Total operations: {n_rows * list_len:,}")
    print()

    # Warm-up run
    _ = conditional_list_vs_scalar_explode(
        df=df,
        list_col="month",
        scalar_col="policy_term",
        result_col="pols_maturity",
        then_col="pols_if",
        otherwise_value=0,
        comparison_multiplier=12,
    )

    # Timed run
    start = time.perf_counter()
    result = conditional_list_vs_scalar_explode(
        df=df,
        list_col="month",
        scalar_col="policy_term",
        result_col="pols_maturity",
        then_col="pols_if",
        otherwise_value=0,
        comparison_multiplier=12,
    )
    end = time.perf_counter()

    elapsed_ms = (end - start) * 1000
    ops_per_sec = (n_rows * list_len) / (end - start)

    print(f"Time: {elapsed_ms:.2f}ms")
    print(f"Throughput: {ops_per_sec:,.0f} operations/second")
    print()

    # Verify correctness for a few rows
    print("Spot check - First 3 rows:")
    for i in range(3):
        policy_term = i + 1
        maturity_month = policy_term * 12
        row_result = result.filter(pl.int_range(pl.len()) == i)
        maturity_values = row_result.select(
            pl.col("pols_maturity").list.explode()
        ).to_series()
        non_zero = maturity_values.filter(maturity_values != 0)
        if len(non_zero) > 0:
            print(
                f"  Row {i}: term={policy_term}y, maturity_month={maturity_month}, "
                f"non-zero values={len(non_zero)}"
            )
        else:
            print(
                f"  Row {i}: term={policy_term}y, maturity_month={maturity_month} "
                "(out of range)"
            )


def main():
    """Run all demonstrations."""
    print("\n" + "#" * 80)
    print("# POLARS LIST VS SCALAR CONDITIONAL - WORKING SOLUTION")
    print(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")  # noqa: DTZ005
    print(f"# Polars version: {pl.__version__}")
    print("#" * 80)

    demo_single_row()
    demo_multiple_rows()
    benchmark_performance()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80 + "\n")
    print(
        """
The explode/re-aggregate pattern successfully handles list vs scalar conditionals:

1. ✅ Works with pure Polars operations (no Python lambdas)
2. ✅ Maintains row order with maintain_order=True
3. ✅ Handles multiple rows correctly with independent comparisons
4. ✅ Good performance for typical actuarial projection sizes
5. ✅ Clean API that can be wrapped in a reusable function

RECOMMENDATION: Use this pattern for conditional operations on list columns.

For the actuarial projection accessor, implement a helper method:

    def when_maturity(self, ...) -> Self:
        # Use explode/re-aggregate pattern internally
        return self._apply_conditional_list_scalar(...)
"""
    )


if __name__ == "__main__":
    main()
