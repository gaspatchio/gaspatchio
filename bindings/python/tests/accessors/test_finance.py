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


class TestDiscountFactorScalar:
    """Tests for discount_factor() calculation on scalar columns."""

    def test_spot_discounting_scalar(self) -> None:
        """Test spot method on scalar columns.

        Formula: (1 + rate)^(-periods)
        (1.05)^(-1) ≈ 0.952380952
        (1.06)^(-2) ≈ 0.889996441
        (1.04)^(-3) ≈ 0.888996359
        """
        af = ActuarialFrame({"rate": [0.05, 0.06, 0.04], "years": [1, 2, 3]})

        af["discount_factor"] = af["rate"].finance.discount_factor(  # type: ignore[attr-defined]
            periods=af["years"], method="spot"
        )

        result = af.collect()
        factors = result["discount_factor"].to_list()

        assert factors[0] == pytest.approx(0.952380952, rel=1e-6)  # noqa: S101
        assert factors[1] == pytest.approx(0.889996441, rel=1e-6)  # noqa: S101
        assert factors[2] == pytest.approx(0.888996359, rel=1e-6)  # noqa: S101


class TestDiscountFactorList:
    """Tests for discount_factor() calculation on list columns."""

    def test_spot_discounting_list(self) -> None:
        """Test spot method on list columns.

        Formula: (1 + 0.004)^(-t)
        t=0: (1.004)^0 = 1.0
        t=1: (1.004)^(-1) ≈ 0.996015936
        t=2: (1.004)^(-2) ≈ 0.992047748
        t=3: (1.004)^(-3) ≈ 0.988095425
        """
        af = ActuarialFrame(
            {"monthly_rate": [[0.004, 0.004, 0.004, 0.004]], "month": [[0, 1, 2, 3]]}
        )

        af["v"] = af["monthly_rate"].finance.discount_factor(  # type: ignore[attr-defined]
            periods=af["month"], method="spot"
        )

        result = af.collect()
        factors = result["v"][0]

        assert factors[0] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
        assert factors[1] == pytest.approx(0.996015936, rel=1e-6)  # noqa: S101
        assert factors[2] == pytest.approx(0.992047748, rel=1e-6)  # noqa: S101
        assert factors[3] == pytest.approx(0.988095425, rel=1e-6)  # noqa: S101

    def test_forward_discounting_list(self) -> None:
        """Test forward method with period-specific rates.

        Formula: v[0]=1, v[t]=v[t-1]*(1+r[t-1])^(-1)
        v[0] = 1.0
        v[1] = 1.0 * (1.003)^(-1) ≈ 0.997009
        v[2] = 0.997009 * (1.004)^(-1) ≈ 0.993036
        v[3] = 0.993036 * (1.005)^(-1) ≈ 0.988095
        """
        af = ActuarialFrame(
            {"forward_rates": [[0.003, 0.004, 0.005, 0.006]], "month": [[0, 1, 2, 3]]}
        )

        af["v"] = af["forward_rates"].finance.discount_factor(  # type: ignore[attr-defined]
            periods=af["month"], method="forward"
        )

        result = af.collect()
        factors = result["v"][0]

        assert factors[0] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
        assert factors[1] == pytest.approx(0.997009, rel=1e-4)  # noqa: S101
        assert factors[2] == pytest.approx(0.993036, rel=1e-4)  # noqa: S101
        assert factors[3] == pytest.approx(0.988095, rel=1e-4)  # noqa: S101

    def test_period_zero_returns_one(self) -> None:
        """Test that period 0 always returns v=1.0.

        (1 + rate)^(-0) = 1.0 for any rate
        """
        af = ActuarialFrame({"rate": [[0.05, 0.06, 0.04]], "period": [[0, 0, 0]]})

        af["v"] = af["rate"].finance.discount_factor(  # type: ignore[attr-defined]
            periods=af["period"], method="spot"
        )

        result = af.collect()
        factors = result["v"][0]

        assert factors[0] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
        assert factors[1] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
        assert factors[2] == pytest.approx(1.0, rel=1e-6)  # noqa: S101
