# ABOUTME: Tests for finance accessor methods (rate conversion, discounting)
# ABOUTME: Covers to_monthly() column accessor and discount_factor() frame accessor
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

    def test_simple_conversion_scalar(self) -> None:
        """Test simple conversion on scalar column.

        Formula: annual / 12
        0.05 / 12 ≈ 0.004166667
        0.06 / 12 = 0.005
        0.04 / 12 ≈ 0.003333333
        """
        af = ActuarialFrame({"annual_rate": [0.05, 0.06, 0.04]})

        af["monthly_rate"] = af["annual_rate"].finance.to_monthly(method="simple")  # type: ignore[attr-defined]

        result = af.collect()
        monthly_rates = result["monthly_rate"].to_list()

        assert monthly_rates[0] == pytest.approx(0.004166667, rel=1e-6)  # noqa: S101
        assert monthly_rates[1] == pytest.approx(0.005, rel=1e-6)  # noqa: S101
        assert monthly_rates[2] == pytest.approx(0.003333333, rel=1e-6)  # noqa: S101


class TestToMonthlyList:
    """Tests for to_monthly() rate conversion on list columns."""

    def test_compound_conversion_list(self) -> None:
        """Test compound conversion on list column.

        Formula: (1 + annual)^(1/12) - 1
        Each element should be converted independently.
        0.05 -> (1.05)^(1/12) - 1 ≈ 0.0040741238
        0.06 -> (1.06)^(1/12) - 1 ≈ 0.0048675506
        """
        af = ActuarialFrame({"annual_rates": [[0.05, 0.05, 0.06, 0.06]]})

        af["monthly_rates"] = af["annual_rates"].finance.to_monthly()  # type: ignore[attr-defined]

        result = af.collect()
        monthly_rates = result["monthly_rates"][0]

        # Each element should be converted independently
        assert monthly_rates[0] == pytest.approx(0.0040741238, rel=1e-6)  # noqa: S101
        assert monthly_rates[1] == pytest.approx(0.0040741238, rel=1e-6)  # noqa: S101
        assert monthly_rates[2] == pytest.approx(0.0048675506, rel=1e-6)  # noqa: S101
        assert monthly_rates[3] == pytest.approx(0.0048675506, rel=1e-6)  # noqa: S101


class TestFrameDiscountFactor:
    """Tests for frame-level discount_factor() using native Polars explode/implode."""

    def test_spot_discounting_list_columns(self) -> None:
        """Test spot method on list columns using frame accessor.

        Formula: (1 + rate)^(-period)
        Uses native Polars explode/implode pattern (no map_elements).
        (1.05)^(-1) ≈ 0.952380952
        (1.06)^(-2) ≈ 0.889996441
        (1.04)^(-3) ≈ 0.888996359
        """
        af = ActuarialFrame(
            {
                "policy_id": [1, 2],
                "rates": [[0.05, 0.06, 0.04], [0.03, 0.03]],
                "periods": [[1.0, 2.0, 3.0], [1.0, 2.0]],
            }
        )

        af = af.finance.discount_factor(
            rate_col="rates",
            periods_col="periods",
            output_col="disc_factors",
            method="spot",
        )

        result = af.collect()

        # Check first policy
        factors_1 = result["disc_factors"][0]
        assert factors_1[0] == pytest.approx(0.952380952, rel=1e-6)  # noqa: S101
        assert factors_1[1] == pytest.approx(0.889996441, rel=1e-6)  # noqa: S101
        assert factors_1[2] == pytest.approx(0.888996359, rel=1e-6)  # noqa: S101

        # Check second policy
        factors_2 = result["disc_factors"][1]
        assert factors_2[0] == pytest.approx(0.970873786, rel=1e-6)  # noqa: S101
        assert factors_2[1] == pytest.approx(0.942595909, rel=1e-6)  # noqa: S101

    def test_spot_with_period_zero(self) -> None:
        """Test that period 0 always returns v=1.0.

        (1 + rate)^(-0) = 1.0 for any rate
        """
        af = ActuarialFrame(
            {
                "policy_id": [1],
                "rates": [[0.004, 0.004, 0.004, 0.004]],
                "periods": [[0, 1, 2, 3]],
            }
        )

        af = af.finance.discount_factor(
            rate_col="rates", periods_col="periods", output_col="v", method="spot"
        )

        result = af.collect()
        factors = result["v"][0]

        assert factors[0] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
        assert factors[1] == pytest.approx(0.996015936, rel=1e-6)  # noqa: S101
        assert factors[2] == pytest.approx(0.992047748, rel=1e-6)  # noqa: S101
        assert factors[3] == pytest.approx(0.988095425, rel=1e-6)  # noqa: S101

    def test_forward_discounting_list_columns(self) -> None:
        """Test forward method with period-specific rates.

        Formula: v[0]=1, v[t]=v[t-1]*(1+r[t-1])^(-1)
        Uses native Polars cumulative product (no map_elements).
        v[0] = 1.0
        v[1] = 1.0 * (1.003)^(-1) ≈ 0.997009
        v[2] = 0.997009 * (1.004)^(-1) ≈ 0.993036
        v[3] = 0.993036 * (1.005)^(-1) ≈ 0.988095
        """
        af = ActuarialFrame(
            {
                "policy_id": [1],
                "forward_rates": [[0.003, 0.004, 0.005, 0.006]],
                "month": [[0, 1, 2, 3]],
            }
        )

        af = af.finance.discount_factor(
            rate_col="forward_rates",
            periods_col="month",
            output_col="v",
            method="forward",
        )

        result = af.collect()
        factors = result["v"][0]

        assert factors[0] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
        assert factors[1] == pytest.approx(0.997009, rel=1e-4)  # noqa: S101
        assert factors[2] == pytest.approx(0.993036, rel=1e-4)  # noqa: S101
        assert factors[3] == pytest.approx(0.988095, rel=1e-4)  # noqa: S101

    def test_multiple_policies_different_lengths(self) -> None:
        """Test that different list lengths per policy work correctly."""
        af = ActuarialFrame(
            {
                "policy_id": [1, 2, 3],
                "rates": [
                    [0.05, 0.05, 0.05],  # 3 periods
                    [0.04, 0.04],  # 2 periods
                    [0.06],  # 1 period
                ],
                "periods": [[1.0, 2.0, 3.0], [1.0, 2.0], [1.0]],
            }
        )

        af = af.finance.discount_factor(
            rate_col="rates",
            periods_col="periods",
            output_col="disc_factors",
            method="spot",
        )

        result = af.collect()

        # Verify lengths are preserved
        expected_lengths = [3, 2, 1]
        assert len(result["disc_factors"][0]) == expected_lengths[0]  # noqa: S101
        assert len(result["disc_factors"][1]) == expected_lengths[1]  # noqa: S101
        assert len(result["disc_factors"][2]) == expected_lengths[2]  # noqa: S101

        # Verify calculations
        assert result["disc_factors"][0][0] == pytest.approx(0.952380952, rel=1e-6)  # noqa: S101
        assert result["disc_factors"][1][0] == pytest.approx(0.961538462, rel=1e-6)  # noqa: S101
        assert result["disc_factors"][2][0] == pytest.approx(0.943396226, rel=1e-6)  # noqa: S101
