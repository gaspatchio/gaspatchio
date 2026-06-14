# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201, PD901, ANN201, E501
# pyright: reportAttributeAccessIssue=false
"""
ABOUTME: Example showing how to integrate list vs scalar conditionals.

ABOUTME: Demonstrates clean API design using the explode/re-aggregate pattern.
"""

import polars as pl


class ProjectionAccessor:
    """
    Accessor for actuarial projection operations on DataFrames.

    Handles conditional operations on list columns vs scalar columns.
    """

    def __init__(self, df: pl.DataFrame) -> None:
        """Initialize the accessor with a DataFrame."""
        self._df = df

    def when_list_eq_scalar(
        self,
        list_col: str,
        scalar_col: str,
        multiplier: int = 1,
    ) -> "ConditionalBuilder":
        """
        Start a conditional expression comparing list column to scalar column.

        Args:
            list_col: Name of list column (e.g., "month")
            scalar_col: Name of scalar column (e.g., "policy_term")
            multiplier: Multiply scalar by this before comparing (e.g., 12 for months)

        Returns:
            ConditionalBuilder for chaining .then() and .otherwise()

        Example:
            df.proj.when_list_eq_scalar("month", "policy_term", multiplier=12)
              .then("pols_if")
              .otherwise(0)
              .alias("pols_maturity")

        """
        return ConditionalBuilder(
            df=self._df,
            list_col=list_col,
            scalar_col=scalar_col,
            multiplier=multiplier,
        )


class ConditionalBuilder:
    """Builder for conditional expressions on list vs scalar columns."""

    def __init__(
        self,
        df: pl.DataFrame,
        list_col: str,
        scalar_col: str,
        multiplier: int = 1,
    ) -> None:
        """Initialize the conditional builder."""
        self._df = df
        self._list_col = list_col
        self._scalar_col = scalar_col
        self._multiplier = multiplier
        self._then_col: str | None = None
        self._otherwise_value: int | float | None = None

    def then(self, col: str) -> "ConditionalBuilder":
        """
        Specify the column to use when condition is True.

        Args:
            col: Name of column to use (must be a list column)

        Returns:
            Self for chaining

        """
        self._then_col = col
        return self

    def otherwise(self, value: float) -> "ConditionalBuilder":
        """
        Specify the value to use when condition is False.

        Args:
            value: Scalar value to use

        Returns:
            Self for chaining

        """
        self._otherwise_value = value
        return self

    def alias(self, name: str) -> pl.DataFrame:
        """
        Execute the conditional and create a new column.

        Args:
            name: Name of the new column to create

        Returns:
            DataFrame with new column added

        Raises:
            ValueError: If then() or otherwise() were not called

        """
        if self._then_col is None:
            msg = "Must call .then() before .alias()"
            raise ValueError(msg)
        if self._otherwise_value is None:
            msg = "Must call .otherwise() before .alias()"
            raise ValueError(msg)

        return self._apply_conditional(name)

    def _apply_conditional(self, result_col: str) -> pl.DataFrame:
        """
        Apply the conditional using explode/re-aggregate pattern.

        Args:
            result_col: Name of the result column

        Returns:
            DataFrame with conditional applied

        """
        # Get all columns to re-aggregate properly
        all_cols = self._df.columns
        list_cols = [col for col in all_cols if self._df[col].dtype == pl.List]

        # Build aggregation list
        agg_list = []
        for col in all_cols:
            if col in list_cols:
                agg_list.append(pl.col(col))
            else:
                agg_list.append(pl.col(col).first())

        return (
            self._df.with_row_index("_row_id")
            .explode([self._list_col, self._then_col])
            .with_columns(
                **{
                    result_col: pl.when(
                        pl.col(self._list_col)
                        == pl.col(self._scalar_col) * self._multiplier
                    )
                    .then(pl.col(self._then_col))
                    .otherwise(self._otherwise_value)
                }
            )
            .group_by("_row_id", maintain_order=True)
            .agg([*agg_list, pl.col(result_col)])
            .drop("_row_id")
        )


def demo_accessor_api():
    """Demonstrate the projection accessor API."""
    print("\n" + "=" * 80)
    print("DEMO: Projection Accessor API")
    print("=" * 80 + "\n")

    # Sample data
    df = pl.DataFrame(
        {
            "month": [
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
            ],
            "policy_term": [1, 2, 0],
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

    # Create accessor and use clean API
    proj = ProjectionAccessor(df)
    result = (
        proj.when_list_eq_scalar("month", "policy_term", multiplier=12)
        .then("pols_if")
        .otherwise(0)
        .alias("pols_maturity")
    )

    print("Result with pols_maturity:")
    print(result)
    print()

    # Show exploded views
    for i in range(3):
        print(f"Policy {i} (term={result['policy_term'][i]}y):")
        exploded = (
            result.filter(pl.int_range(pl.len()) == i)
            .select(pl.col("pols_maturity").list.explode().alias("maturity"))
            .with_row_index("month")
        )
        print(exploded)
        print()


def demo_multiple_conditions():
    """Demonstrate applying conditionals in a single pass."""
    print("\n" + "=" * 80)
    print("DEMO: Note on Multiple Conditionals")
    print("=" * 80 + "\n")

    print(
        """
NOTE: For multiple conditionals on the same DataFrame, apply them in separate
operations from the original DataFrame rather than chaining:

    # GOOD - Apply from original DF
    df_with_mat = proj1.when_list_eq_scalar(...).alias("pols_maturity")
    df_with_death = proj2.when_list_eq_scalar(...).alias("pols_death")

    # Then join/merge results if needed

    # AVOID - Chaining can cause schema issues
    df = df.proj.when(...).alias("col1")
    df = df.proj.when(...).alias("col2")  # May fail!

The explode/re-aggregate pattern works best when applying one conditional
at a time. For multiple conditionals, consider using the original solution
script's conditional_list_vs_scalar_explode() function multiple times.
"""
    )


def main():
    """Run demonstrations."""
    print("\n" + "#" * 80)
    print("# PROJECTION ACCESSOR API EXAMPLE")
    print(f"# Polars version: {pl.__version__}")
    print("#" * 80)

    demo_accessor_api()
    demo_multiple_conditions()

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80 + "\n")
    print(
        """
The projection accessor provides a clean, readable API for conditional operations:

    df.proj.when_list_eq_scalar("month", "policy_term", multiplier=12)
      .then("pols_if")
      .otherwise(0)
      .alias("pols_maturity")

Benefits:
- Clean, readable syntax
- Type-safe builder pattern
- Hides complexity of explode/re-aggregate
- Consistent with Polars when/then/otherwise API
- Can be extended with more condition types

This can be integrated into the gaspatchio_core.accessors.projection module.
"""
    )


if __name__ == "__main__":
    main()
