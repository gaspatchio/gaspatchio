"""Tests for the FinanceFrameAccessor."""

import polars as pl
from gaspatchio_core.dsl.core import ActuarialFrame
from polars.testing import assert_frame_equal


def test_present_value():
    """Test the FinanceFrameAccessor.present_value method."""
    data = {
        "ID": [1, 1, 2, 2],
        "CashFlow": [100, 100, 200, 200],
        "Rate": [0.05, 0.05, 0.10, 0.10],
        "Period": [1, 2, 1, 2],
    }
    af = ActuarialFrame(data)

    # Calculate present value
    pv_expr = af.finance.present_value("CashFlow", "Rate", "Period")
    af_result = ActuarialFrame(af._df.with_columns(pv_expr._expr.alias("PV")))

    # Expected PV calculation: CF / (1 + Rate)^Period
    expected_data = {
        "ID": [1, 1, 2, 2],
        "CashFlow": [100, 100, 200, 200],
        "Rate": [0.05, 0.05, 0.10, 0.10],
        "Period": [1, 2, 1, 2],
        "PV": [
            100 / (1 + 0.05) ** 1,  # 95.238
            100 / (1 + 0.05) ** 2,  # 90.703
            200 / (1 + 0.10) ** 1,  # 181.818
            200 / (1 + 0.10) ** 2,  # 165.289
        ],
    }
    expected_lf = pl.LazyFrame(expected_data)

    # Use polars testing utilities for comparison, handling potential float differences
    assert_frame_equal(
        af_result.collect(),
        expected_lf.collect(),
        check_dtype=False,
        check_exact=False,
        rtol=1e-4,
    )


# Add more tests for edge cases:
# - Period = 0 or negative (should result in null or error based on implementation)
# - Missing values in inputs
# - Different data types for inputs
# - Using literals or complex expressions for arguments
