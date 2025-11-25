# ABOUTME: Research script testing different methods for broadcasting
# ABOUTME: scalar columns to list columns in Polars with performance comparisons

"""Research script for scalar-to-list broadcasting in Polars.

This script compares different methods for converting scalar columns to list
columns to match the length of existing list columns, with performance testing.
"""

import time

import polars as pl


def test_repeat_by_method(test_data: pl.DataFrame) -> None:
    """Test Method 1: Using repeat_by to broadcast scalars to lists."""
    print("=" * 60)  # noqa: T201
    print("Method 1: Using repeat_by (recommended)")  # noqa: T201
    print("=" * 60)  # noqa: T201

    start = time.time()
    result = test_data.with_columns(
        pl.col("total_months")
        .repeat_by(pl.col("month").list.len())
        .alias("total_months_list")
    )
    elapsed = time.time() - start

    print(result)  # noqa: T201
    print(f"Time: {elapsed:.6f} seconds")  # noqa: T201
    print()  # noqa: T201


def test_list_eval_method(test_data: pl.DataFrame) -> None:
    """Test Method 2: Using list.eval with literal (expected to fail)."""
    print("=" * 60)  # noqa: T201
    print("Method 2: Using list.eval with literal")  # noqa: T201
    print("=" * 60)  # noqa: T201

    try:
        start = time.time()
        result = test_data.select(
            [
                pl.col("policy_term"),
                pl.col("month"),
                pl.col("total_months"),
                pl.col("month")
                .list.eval(pl.lit(pl.col("total_months")))
                .alias("total_months_list_v2"),
            ]
        )
        elapsed = time.time() - start
        print(result)  # noqa: T201
        print(f"Time: {elapsed:.6f} seconds")  # noqa: T201
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")  # noqa: T201
        print("Note: list.eval cannot reference named columns")  # noqa: T201
    print()  # noqa: T201


def test_direct_arithmetic_method(test_data: pl.DataFrame) -> None:
    """Test Method 3: Direct arithmetic with list broadcasting."""
    print("=" * 60)  # noqa: T201
    print("Method 3: Direct arithmetic with list broadcasting")  # noqa: T201
    print("=" * 60)  # noqa: T201

    try:
        start = time.time()
        result = test_data.with_columns(
            (pl.col("month") + pl.col("total_months")).alias("month_plus_total")
        )
        elapsed = time.time() - start
        print(result)  # noqa: T201
        print(f"Time: {elapsed:.6f} seconds")  # noqa: T201
        print("Note: Direct arithmetic between list and scalar works!")  # noqa: T201
    except Exception as e:  # noqa: BLE001
        print(f"Error: {e}")  # noqa: T201
    print()  # noqa: T201


def test_large_dataset_performance() -> None:
    """Test repeat_by performance with 100,000 rows."""
    print("=" * 60)  # noqa: T201
    print("Performance Test: 100,000 rows")  # noqa: T201
    print("=" * 60)  # noqa: T201

    large_data = pl.DataFrame(
        {
            "policy_term": [10] * 100_000,
            "month": [list(range(12))] * 100_000,
        }
    ).with_columns((pl.col("policy_term") * 12).alias("total_months"))

    start = time.time()
    result_large = large_data.with_columns(
        pl.col("total_months")
        .repeat_by(pl.col("month").list.len())
        .alias("total_months_list")
    )
    elapsed_large = time.time() - start

    print(f"repeat_by with 100k rows: {elapsed_large:.6f} seconds")  # noqa: T201
    print(f"Shape: {result_large.shape}")  # noqa: T201
    print()  # noqa: T201


def print_memory_efficiency_notes() -> None:
    """Print notes about memory efficiency considerations."""
    print("=" * 60)  # noqa: T201
    print("Memory Efficiency Notes")  # noqa: T201
    print("=" * 60)  # noqa: T201
    print("- repeat_by creates an actual list column with repeated values")  # noqa: T201
    print("- Polars uses ScalarColumn optimization where possible")  # noqa: T201
    print("- Direct arithmetic may be more memory efficient")  # noqa: T201
    print("  as it broadcasts the scalar at computation time")  # noqa: T201
    print("  rather than materializing the list")  # noqa: T201


def main() -> None:
    """Run scalar-to-list broadcasting research tests."""
    # Create test dataframe
    test_data = pl.DataFrame(
        {
            "policy_term": [10, 20, 15],
            "month": [
                list(range(12)),
                list(range(12)),
                list(range(12)),
            ],
        }
    )

    print("Original DataFrame:")  # noqa: T201
    print(test_data)  # noqa: T201
    print()  # noqa: T201

    # Calculate scalar column
    test_data = test_data.with_columns(
        (pl.col("policy_term") * 12).alias("total_months")
    )

    print("With scalar 'total_months' column:")  # noqa: T201
    print(test_data)  # noqa: T201
    print()  # noqa: T201

    # Run all test methods
    test_repeat_by_method(test_data)
    test_list_eval_method(test_data)
    test_direct_arithmetic_method(test_data)
    test_large_dataset_performance()
    print_memory_efficiency_notes()


if __name__ == "__main__":
    main()
