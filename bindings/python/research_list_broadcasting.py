# ruff: noqa: T201, PD901, ANN201, E501, D205, BLE001, F841, DTZ005
"""
ABOUTME: Research script to test Polars list vs scalar broadcasting.

ABOUTME: Tests various conditional patterns with list and scalar columns to understand automatic broadcasting behavior.
"""

from datetime import datetime

import polars as pl


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


def test_basic_case():
    """Test the specific use case from the research request."""
    print_section("TEST 1: Basic Use Case - List Column vs Scalar Column")

    df = pl.DataFrame(
        {
            "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
            "policy_term": [1],  # 1 year = 12 months
            "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88]],
        }
    )

    print("Input DataFrame:")
    print(df)
    print("\nColumn types:")
    print(df.schema)

    try:
        result = df.with_columns(
            pols_maturity=pl.when(pl.col("month") == pl.col("policy_term") * 12)
            .then(pl.col("pols_if"))
            .otherwise(0)
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nResult schema:")
        print(result.schema)
        print("\nExploded view of pols_maturity:")
        print(result.select(pl.col("pols_maturity").list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_list_eval_approach():
    """Test using list.eval() for element-wise comparison."""
    print_section("TEST 2: Using list.eval() for Element-wise Comparison")

    df = pl.DataFrame(
        {
            "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
            "policy_term": [1],
            "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88]],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        # Try using list.eval() to do element-wise comparison
        result = df.with_columns(
            pols_maturity=pl.when(
                pl.col("month")
                .list.eval(pl.element() == pl.first("policy_term") * 12)
                .list.any()
            )
            .then(
                pl.col("pols_if").list.eval(
                    pl.when(
                        pl.element().rank()
                        == pl.first("month")
                        .list.eval(pl.element() == pl.first("policy_term") * 12)
                        .list.arg_max()
                        + 1
                    )
                    .then(pl.element())
                    .otherwise(0)
                )
            )
            .otherwise(pl.col("pols_if").list.eval(pl.lit(0)))
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nExploded view:")
        print(result.select(pl.col("pols_maturity").list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_simpler_list_eval():
    """Test a simpler list.eval() approach."""
    print_section("TEST 3: Simpler list.eval() - Direct Element-wise When/Then")

    df = pl.DataFrame(
        {
            "month": [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
            "policy_term": [1],
            "pols_if": [[100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88]],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        # Direct element-wise when/then using list.eval()
        result = df.with_columns(
            pols_maturity=pl.col("pols_if").list.eval(
                pl.when(
                    pl.element().rank()
                    == pl.first("month")
                    .list.eval(pl.element() == pl.first("policy_term") * 12)
                    .list.arg_max()
                    + 1
                )
                .then(pl.element())
                .otherwise(0)
            )
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nExploded view:")
        print(result.select(pl.col("pols_maturity").list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_multiple_rows():
    """Test with multiple rows to see broadcasting behavior."""
    print_section("TEST 4: Multiple Rows - Does Broadcasting Work Row-wise?")

    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term": [1, 2],  # 1 year and 2 years
            "pols_if": [
                [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                [200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176],
            ],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        result = df.with_columns(
            pols_maturity=pl.when(pl.col("month") == pl.col("policy_term") * 12)
            .then(pl.col("pols_if"))
            .otherwise(0)
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nRow 0 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(0).list.explode()))
        print("\nRow 1 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(1).list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_manual_repeat_by():
    """Test manual broadcasting using repeat_by()."""
    print_section("TEST 5: Manual Broadcasting with repeat_by()")

    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term": [1, 2],
            "pols_if": [
                [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                [200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176],
            ],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        # Manual approach: repeat scalars to match list lengths
        result = (
            df.with_columns(
                policy_term_repeated=pl.col("policy_term").repeat_by(
                    pl.col("month").list.len()
                )
            )
            .with_columns(
                pols_maturity=pl.struct(
                    ["month", "policy_term_repeated", "pols_if"]
                ).map_elements(
                    lambda row: [
                        pif if m == pt * 12 else 0
                        for m, pt, pif in zip(
                            row["month"],
                            row["policy_term_repeated"],
                            row["pols_if"],
                            strict=False,
                        )
                    ],
                    return_dtype=pl.List(pl.Int64),
                )
            )
            .drop("policy_term_repeated")
        )

        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nRow 0 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(0).list.explode()))
        print("\nRow 1 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(1).list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_list_eval_proper():
    """Test proper list.eval() with element-wise when/then."""
    print_section("TEST 6: Proper list.eval() with Element-wise Conditional")

    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term": [1, 2],
            "pols_if": [
                [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                [200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176],
            ],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        # Using list.eval() to access scalar column inside list context
        result = df.with_columns(
            pols_maturity=pl.col("month").list.eval(
                pl.when(pl.element() == pl.first("policy_term") * 12)
                .then(pl.first("pols_if").list.get(pl.element().rank() - 1))
                .otherwise(0)
            )
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nRow 0 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(0).list.explode()))
        print("\nRow 1 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(1).list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_zip_with():
    """Test using pl.zip_with() for element-wise operations."""
    print_section("TEST 7: Using zip_with() for Element-wise Conditional")

    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term": [1, 2],
            "pols_if": [
                [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                [200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176],
            ],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        # Create a list of the scalar repeated
        df_with_term_list = df.with_columns(policy_term_list=pl.col("policy_term") * 12)

        # Use zip_with to apply element-wise conditional
        result = df_with_term_list.with_columns(
            pols_maturity=pl.when(
                pl.col("month").list.eval(pl.element() == pl.first("policy_term_list"))
            )
            .then(pl.col("pols_if"))
            .otherwise(pl.lit(0))
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_list_eval_with_two_lists():
    """Test list.eval() comparing two list columns element-wise."""
    print_section("TEST 8: list.eval() with Two List Columns (Ground Truth)")

    # First create explicit list columns for both sides
    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term_months": [
                [12] * 13,  # All elements are 12
                [24] * 13,  # All elements are 24
            ],
            "pols_if": [
                [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88],
                [200, 198, 196, 194, 192, 190, 188, 186, 184, 182, 180, 178, 176],
            ],
        }
    )

    print("Input DataFrame (with explicit list columns):")
    print(df)

    try:
        # Now test when/then with two list columns
        result = df.with_columns(
            pols_maturity=pl.when(pl.col("month") == pl.col("policy_term_months"))
            .then(pl.col("pols_if"))
            .otherwise(0)
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nRow 0 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(0).list.explode()))
        print("\nRow 1 exploded:")
        print(result.select(pl.col("pols_maturity").list.get(1).list.explode()))
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def test_arithmetic_operations():
    """Test if arithmetic operations broadcast scalars into lists."""
    print_section("TEST 9: Do Arithmetic Operations Broadcast?")

    df = pl.DataFrame(
        {
            "list_col": [[1, 2, 3, 4, 5]],
            "scalar_col": [10],
        }
    )

    print("Input DataFrame:")
    print(df)

    try:
        # Test addition
        result = df.with_columns(
            add_result=pl.col("list_col") + pl.col("scalar_col"),
            mult_result=pl.col("list_col") * pl.col("scalar_col"),
            compare_result=pl.col("list_col") == pl.col("scalar_col"),
        )
        print("\n✓ SUCCESS - Result:")
        print(result)
        print("\nSchema:")
        print(result.schema)
    except Exception as e:
        print(f"\n✗ FAILED with error: {type(e).__name__}: {e}")


def benchmark_approaches():
    """Compare performance of different approaches."""
    print_section("BENCHMARK: Performance Comparison")

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

    print(f"Dataset: {n_rows} rows, {list_len} elements per list")

    # Approach 1: Try direct when/then (if it works)
    print("\nApproach 1: Direct when/then (if supported)...")
    try:
        start = time.perf_counter()
        result1 = df.with_columns(
            pols_maturity=pl.when(pl.col("month") == pl.col("policy_term") * 12)
            .then(pl.col("pols_if"))
            .otherwise(0)
        )
        end = time.perf_counter()
        print(f"✓ Time: {(end - start) * 1000:.2f}ms")
    except Exception as e:
        print(f"✗ Not supported: {type(e).__name__}")

    # Approach 2: list.eval() with proper element-wise logic
    print("\nApproach 2: list.eval() element-wise...")
    try:
        start = time.perf_counter()
        result2 = df.with_columns(
            pols_maturity=pl.col("month").list.eval(
                pl.when(pl.element() == pl.first("policy_term") * 12)
                .then(pl.first("pols_if").list.get(pl.element().rank() - 1))
                .otherwise(0)
            )
        )
        end = time.perf_counter()
        print(f"✓ Time: {(end - start) * 1000:.2f}ms")
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {e}")

    # Approach 3: Manual with map_elements
    print("\nApproach 3: Manual with map_elements...")
    try:
        start = time.perf_counter()
        result3 = (
            df.with_columns(
                policy_term_repeated=pl.col("policy_term").repeat_by(
                    pl.col("month").list.len()
                )
            )
            .with_columns(
                pols_maturity=pl.struct(
                    ["month", "policy_term_repeated", "pols_if"]
                ).map_elements(
                    lambda row: [
                        pif if m == pt * 12 else 0
                        for m, pt, pif in zip(
                            row["month"],
                            row["policy_term_repeated"],
                            row["pols_if"],
                            strict=False,
                        )
                    ],
                    return_dtype=pl.List(pl.Int64),
                )
            )
            .drop("policy_term_repeated")
        )
        end = time.perf_counter()
        print(f"✓ Time: {(end - start) * 1000:.2f}ms")
    except Exception as e:
        print(f"✗ Failed: {type(e).__name__}: {e}")


def main():
    """Run all tests."""
    print(f"\n{'#' * 80}")
    print("# POLARS LIST VS SCALAR BROADCASTING RESEARCH")
    print(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"# Polars version: {pl.__version__}")
    print(f"{'#' * 80}")

    test_basic_case()
    test_arithmetic_operations()
    test_multiple_rows()
    test_list_eval_with_two_lists()
    test_list_eval_proper()
    test_simpler_list_eval()
    test_manual_repeat_by()
    test_zip_with()
    benchmark_approaches()

    print_section("SUMMARY AND CONCLUSIONS")
    print("""
Based on the tests above, here are the key findings:

1. AUTOMATIC BROADCASTING:
   - Check if `pl.col("list") == pl.col("scalar")` works automatically
   - Check if when/then/otherwise propagates through list elements
   - Look at the actual output to see what happens

2. ARITHMETIC OPERATIONS:
   - Check if `pl.col("list") + pl.col("scalar")` broadcasts
   - This would indicate general broadcasting support

3. ELEMENT-WISE WITH list.eval():
   - `pl.col("list").list.eval(pl.element() == pl.first("scalar"))`
   - This is the explicit element-wise approach
   - Check if pl.first() can access scalar columns from parent context

4. PERFORMANCE:
   - Compare actual timing results from benchmark section
   - Identify fastest working approach

5. RECOMMENDATIONS:
   - Based on what works above, recommend best practice
   - Document any gotchas or limitations discovered
    """)


if __name__ == "__main__":
    main()
