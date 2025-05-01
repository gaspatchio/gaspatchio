"""Tests for the FinanceColumnAccessor."""

import polars as pl
from gaspatchio_core.dsl.core import ActuarialFrame
from polars.testing import assert_frame_equal


def test_discount_column_vs_scalar():
    """Test discount with scalar rate and period."""
    data = {"Value": [1000.0, 2000.0, 1500.0]}
    af = ActuarialFrame(data)
    rate = 0.10
    periods = 2

    # Discount using the accessor
    discount_expr = af["Value"].finance.discount(rate, periods)
    af_result = ActuarialFrame(
        af._df.with_columns(discount_expr._expr.alias("Discounted"))
    )

    # Expected calculation: Value / (1 + rate)^periods
    expected_data = {
        "Value": [1000.0, 2000.0, 1500.0],
        "Discounted": [
            1000.0 / (1 + rate) ** periods,  # 1000 / 1.21 = 826.446
            2000.0 / (1 + rate) ** periods,  # 2000 / 1.21 = 1652.893
            1500.0 / (1 + rate) ** periods,  # 1500 / 1.21 = 1239.669
        ],
    }
    expected_lf = pl.LazyFrame(expected_data)

    assert_frame_equal(
        af_result.collect(),
        expected_lf.collect(),
        check_dtype=False,
        check_exact=False,
        rtol=1e-4,
    )


def test_discount_column_vs_column():
    """Test discount with rate and period from other columns."""
    data = {
        "Value": [1000.0, 2000.0, 1500.0],
        "DiscRate": [0.05, 0.10, 0.08],
        "Periods": [1, 2, 3],
    }
    af = ActuarialFrame(data)

    # Discount using the accessor with column names
    discount_expr = af["Value"].finance.discount("DiscRate", "Periods")
    af_result = ActuarialFrame(
        af._df.with_columns(discount_expr._expr.alias("Discounted"))
    )

    # Expected calculation: Value / (1 + DiscRate)^Periods
    expected_data = {
        "Value": [1000.0, 2000.0, 1500.0],
        "DiscRate": [0.05, 0.10, 0.08],
        "Periods": [1, 2, 3],
        "Discounted": [
            1000.0 / (1 + 0.05) ** 1,  # 952.381
            2000.0 / (1 + 0.10) ** 2,  # 1652.893
            1500.0 / (1 + 0.08) ** 3,  # 1190.748
        ],
    }
    expected_lf = pl.LazyFrame(expected_data)

    assert_frame_equal(
        af_result.collect(),
        expected_lf.collect(),
        check_dtype=False,
        check_exact=False,
        rtol=1e-4,
    )


def test_discount_expression_vs_expression():
    """Test discount on an expression with rate/period as expressions."""
    data = {
        "BaseVal": [500.0, 1000.0, 750.0],
        "RateCol": [0.05, 0.10, 0.08],
        "PeriodCol": [1, 2, 3],
    }
    af = ActuarialFrame(data)

    # Create initial expression (e.g., BaseVal * 2)
    initial_expr = af["BaseVal"] * 2

    # Discount the expression using other expressions
    rate_expr = af["RateCol"] + 0.01  # Example: RateCol + 1%
    period_expr = af["PeriodCol"] - 1  # Example: PeriodCol - 1

    discount_expr = initial_expr.finance.discount(rate_expr, period_expr)
    af_result = ActuarialFrame(
        af._df.with_columns(discount_expr._expr.alias("DiscountedExpr"))
    )

    # Expected calculation: (BaseVal * 2) / (1 + RateCol + 0.01)^(PeriodCol - 1)
    # Note: PeriodCol - 1 gives 0, 1, 2. Discount for 0 periods is factor 1.
    expected_data = {
        "BaseVal": [500.0, 1000.0, 750.0],
        "RateCol": [0.05, 0.10, 0.08],
        "PeriodCol": [1, 2, 3],
        "DiscountedExpr": [
            (500.0 * 2) / (1 + 0.05 + 0.01) ** (1 - 1),  # 1000 / (1.06)^0 = 1000.0
            (1000.0 * 2) / (1 + 0.10 + 0.01) ** (2 - 1),  # 2000 / (1.11)^1 = 1801.801
            (750.0 * 2) / (1 + 0.08 + 0.01) ** (3 - 1),  # 1500 / (1.09)^2 = 1262.539
        ],
    }
    expected_lf = pl.LazyFrame(expected_data)

    assert_frame_equal(
        af_result.collect(),
        expected_lf.collect(),
        check_dtype=False,
        check_exact=False,
        rtol=1e-4,
    )


# Add more tests for edge cases:
# - Rate = -1 (division by zero potential)
# - Periods = 0 or negative
# - Missing values in inputs
# - Different data types
