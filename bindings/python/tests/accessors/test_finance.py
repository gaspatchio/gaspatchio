# ABOUTME: Tests for finance accessor methods (rate conversion, discounting)
# ABOUTME: Covers to_monthly() and discount_factor() with scalar and list columns
"""Tests for finance accessor methods (rate conversion, discounting)."""

import pytest

from gaspatchio_core import ActuarialFrame


class TestToMonthlyScalar:
    """Tests for to_monthly() rate conversion on scalar columns."""

    def test_compound_conversion_scalar(self) -> None:
        """Test compound conversion on scalar column.

        Formula: (1 + annual)^(1/12) - 1
        0.05 -> (1.05)^(1/12) - 1 ≈ 0.0040741238
        0.06 -> (1.06)^(1/12) - 1 ≈ 0.0048675506
        0.04 -> (1.04)^(1/12) - 1 ≈ 0.0032737398
        """
        af = ActuarialFrame({"annual_rate": [0.05, 0.06, 0.04]})

        af["monthly_rate"] = af["annual_rate"].finance.to_monthly()  # type: ignore[attr-defined]

        result = af.collect()
        monthly_rates = result["monthly_rate"].to_list()

        assert monthly_rates[0] == pytest.approx(0.0040741238, rel=1e-6)  # noqa: S101
        assert monthly_rates[1] == pytest.approx(0.0048675506, rel=1e-6)  # noqa: S101
        assert monthly_rates[2] == pytest.approx(0.0032737398, rel=1e-6)  # noqa: S101
