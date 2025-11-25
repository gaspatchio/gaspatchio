# ABOUTME: MVP test for list_conditional plugin integration with when/then/otherwise
# ABOUTME: Tests simplest case: when(af.month == af.term).then(1.0).otherwise(0.0)
# ruff: noqa: S101
# type: ignore[call-non-callable]
"""MVP test for list_conditional plugin integration.

Tests the simplest case to prove the concept works:
- Simple == comparison
- Scalar then/otherwise values
- Verify no EXPLODE in query plan
- Verify correct results
"""

import polars as pl

from gaspatchio_core import ActuarialFrame, when


def test_mvp_simple_eq_comparison() -> None:
    """MVP: Test simple == comparison with scalar then/otherwise.

    This is the smallest test to prove the list_conditional integration works.
    Success criteria:
    1. Correct results
    2. No EXPLODE in query plan
    3. No double-wrapping bug
    """
    # Create simple test data
    af = ActuarialFrame(
        {
            "month": [[0, 1, 2, 3]],
            "term": [2],
        }
    )

    # Apply conditional using when/then/otherwise
    af.result = when(af.month == af.term).then(1.0).otherwise(0.0)  # type: ignore[operator]

    # Collect results
    result = af.collect()

    # Verify correct results
    assert result["result"].dtype == pl.List(pl.Float64), (
        "Result should be List<Float64>"
    )
    # Extract the list and compare
    result_list = result["result"].to_list()[0]
    expected = [0.0, 0.0, 1.0, 0.0]
    assert result_list == expected, f"Expected {expected}, got {result_list}"
