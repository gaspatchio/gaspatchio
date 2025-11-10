# ABOUTME: Tests for the ProjectionColumnAccessor.
# ABOUTME: Validates cumulative survival, discount, and period override methods.
# ruff: noqa: S101, PLR2004, ANN201, ERA001
# type: ignore[attr-defined]

"""Tests for projection accessor methods."""

import pytest

from gaspatchio_core import ActuarialFrame


class TestCumulativeSurvival:
    """Tests for cumulative_survival() method."""

    def test_list_column_basic(self):
        """Test cumulative survival with list column."""
        data = {"qx": [[0.001, 0.001, 0.001]]}
        af = ActuarialFrame(data)

        af.survival = af.qx.projection.cumulative_survival(start_at=None)

        result = af.collect()
        survival = result["survival"][0]

        # survival[0] = 1 - 0.001 = 0.999
        # survival[1] = 0.999 * (1 - 0.001) = 0.999 * 0.999 = 0.998001
        # survival[2] = 0.998001 * 0.999 = 0.997002999
        assert len(survival) == 3
        assert pytest.approx(survival[0], abs=1e-6) == 0.999
        assert pytest.approx(survival[1], abs=1e-6) == 0.998001
        assert pytest.approx(survival[2], abs=1e-6) == 0.997002999

    def test_list_column_multiple_policies(self):
        """Test cumulative survival with multiple policies."""
        data = {
            "policy_id": [1, 2],
            "qx": [[0.001, 0.002], [0.003, 0.004]],
        }
        af = ActuarialFrame(data)

        af.survival = af.qx.projection.cumulative_survival(start_at=None)

        result = af.collect()

        # Policy 1: survival = [0.999, 0.999 * 0.998]
        survival_1 = result["survival"][0]
        assert pytest.approx(survival_1[0], abs=1e-6) == 0.999
        assert pytest.approx(survival_1[1], abs=1e-6) == 0.999 * 0.998

        # Policy 2: survival = [0.997, 0.997 * 0.996]
        survival_2 = result["survival"][1]
        assert pytest.approx(survival_2[0], abs=1e-6) == 0.997
        assert pytest.approx(survival_2[1], abs=1e-6) == 0.997 * 0.996

    def test_use_in_cashflow_calculation(self):
        """Test survival in actuarial cashflow calculation."""
        data = {
            "face_amount": [100000],
            "qx": [[0.001, 0.002, 0.003]],
            "annual_premium": [500],
        }
        af = ActuarialFrame(data)

        # Calculate cumulative survival
        af.survival_to_t = af.qx.projection.cumulative_survival()

        # Calculate cashflows using formula IS code pattern
        af.death_benefit = af.face_amount * af.qx * af.survival_to_t
        af.premium = af.annual_premium * af.survival_to_t

        result = af.collect()

        # Verify death benefits calculated correctly
        death_benefits = result["death_benefit"][0]
        assert len(death_benefits) == 3

        # Premium should be annual_premium * survival
        premiums = result["premium"][0]
        survival = result["survival_to_t"][0]
        assert pytest.approx(premiums[0], abs=1e-2) == 500 * survival[0]

    def test_start_at_full_cohort(self):
        """Test start_at parameter with full cohort (1.0)."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        af.pols_if = af.qx.projection.cumulative_survival(start_at=1.0)

        result = af.collect()
        pols_if = result["pols_if"][0]

        # With start_at=1.0: [1.0, 0.999, 0.997002]
        assert len(pols_if) == 3
        assert pytest.approx(pols_if[0], abs=1e-6) == 1.0
        assert pytest.approx(pols_if[1], abs=1e-6) == 0.999
        assert pytest.approx(pols_if[2], abs=1e-6) == 0.999 * 0.998

    def test_start_at_partial_cohort(self):
        """Test start_at parameter with partial cohort."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        # Simulate 95% survived underwriting
        af.pols_if = af.qx.projection.cumulative_survival(start_at=0.95)

        result = af.collect()
        pols_if = result["pols_if"][0]

        # With start_at=0.95: [0.95, 0.999, 0.997002]
        assert len(pols_if) == 3
        assert pytest.approx(pols_if[0], abs=1e-6) == 0.95
        assert pytest.approx(pols_if[1], abs=1e-6) == 0.999
        assert pytest.approx(pols_if[2], abs=1e-6) == 0.999 * 0.998

    def test_start_at_vs_manual_shift(self):
        """Test that start_at matches manual shift behavior."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        # Manual shift approach (old way - get end-of-period, then shift)
        af.pols_if_manual = af.qx.projection.cumulative_survival(start_at=None).shift(
            1, fill_value=1.0
        )

        # start_at approach (new way - default is beginning-of-period)
        af.pols_if_auto = af.qx.projection.cumulative_survival(start_at=1.0)

        result = af.collect()

        manual = result["pols_if_manual"][0]
        auto = result["pols_if_auto"][0]

        # Should be identical
        assert len(manual) == len(auto)
        for m, a in zip(manual, auto, strict=False):
            assert pytest.approx(m, abs=1e-9) == a


class TestCumulativeDiscount:
    """Tests for cumulative_discount() method."""

    def test_compound_discount_basic(self):
        """Test compound discount with list column."""
        data = {"rate": [[0.05, 0.05, 0.05]]}
        af = ActuarialFrame(data)

        af.v = af.rate.projection.cumulative_discount(start_at=None)

        result = af.collect()
        v = result["v"][0]

        # v[0] = 1 / 1.05 = 0.952381
        # v[1] = 1 / (1.05 * 1.05) = 0.907029
        # v[2] = 1 / (1.05^3) = 0.863838
        assert len(v) == 3
        assert pytest.approx(v[0], abs=1e-6) == 1 / 1.05
        assert pytest.approx(v[1], abs=1e-6) == 1 / (1.05**2)
        assert pytest.approx(v[2], abs=1e-6) == 1 / (1.05**3)

    def test_simple_discount(self):
        """Test simple discount mode."""
        data = {"rate": [[0.05, 0.05, 0.05]]}
        af = ActuarialFrame(data)

        af.v = af.rate.projection.cumulative_discount(mode="simple", start_at=None)

        result = af.collect()
        v = result["v"][0]

        # Simple: v[t] = 1 / (1 + r * t)
        # v[0] = 1 / (1 + 0.05 * 0) = 1.0
        # v[1] = 1 / (1 + 0.05 * 1) = 0.952381
        # v[2] = 1 / (1 + 0.05 * 2) = 0.909091
        assert len(v) == 3
        assert pytest.approx(v[0], abs=1e-6) == 1.0
        assert pytest.approx(v[1], abs=1e-6) == 1 / 1.05
        assert pytest.approx(v[2], abs=1e-6) == 1 / 1.10

    def test_invalid_mode(self):
        """Test that invalid mode raises ValueError."""
        data = {"rate": [[0.05, 0.05]]}
        af = ActuarialFrame(data)

        with pytest.raises(ValueError, match="mode must be 'compound' or 'simple'"):
            af.v = af.rate.projection.cumulative_discount(mode="invalid")

    def test_use_in_present_value(self):
        """Test discount factors in present value calculation."""
        data = {
            "cashflow": [[1000, -500, 750]],
            "rate": [[0.05, 0.05, 0.05]],
        }
        af = ActuarialFrame(data)

        # Calculate discount factors
        af.v = af.rate.projection.cumulative_discount(start_at=None)

        # Calculate present value (formula IS code)
        af.pv = af.cashflow * af.v

        # Sum to get total PV
        af.total_pv = af.pv.list.sum()

        result = af.collect()
        pv = result["pv"][0]
        total_pv = result["total_pv"][0]

        # Verify individual PVs
        assert len(pv) == 3
        assert pytest.approx(pv[0], abs=1e-2) == 1000 / 1.05
        assert pytest.approx(pv[1], abs=1e-2) == -500 / (1.05**2)
        assert pytest.approx(pv[2], abs=1e-2) == 750 / (1.05**3)

        # Verify total
        expected_total = 1000 / 1.05 - 500 / (1.05**2) + 750 / (1.05**3)
        assert pytest.approx(total_pv, abs=1e-2) == expected_total


class TestWithPeriod:
    """Tests for with_period() method."""

    def test_override_single_period(self):
        """Test overriding a single period value."""
        data = {"premium": [[1000, 1000, 1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        # Premium holiday in period 2 (3rd element)
        af.premium_adj = af.premium.projection.with_period(2, value=0)

        result = af.collect()
        premium_adj = result["premium_adj"][0]

        assert premium_adj.to_list() == [1000, 1000, 0, 1000, 1000]

    def test_negative_index(self):
        """Test with_period using negative index."""
        data = {"benefit": [[1000, 1000, 1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        # Modify last period
        af.benefit_adj = af.benefit.projection.with_period(-1, value=5000)

        result = af.collect()
        benefit_adj = result["benefit_adj"][0]

        assert benefit_adj.to_list() == [1000, 1000, 1000, 1000, 5000]

    def test_first_period(self):
        """Test modifying first period (index 0)."""
        data = {"values": [[100, 200, 300]]}
        af = ActuarialFrame(data)

        af.values_adj = af.values.projection.with_period(0, value=999)

        result = af.collect()
        values_adj = result["values_adj"][0]

        assert values_adj.to_list() == [999, 200, 300]


class TestWithPeriods:
    """Tests for with_periods() method."""

    def test_multiple_overrides(self):
        """Test overriding multiple periods at once."""
        data = {"premium": [[1000, 1000, 1000, 1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        # Premium holidays in periods 2 and 4
        af.premium_adj = af.premium.projection.with_periods({2: 0, 4: 0})

        result = af.collect()
        premium_adj = result["premium_adj"][0]

        assert premium_adj.to_list() == [1000, 1000, 0, 1000, 0, 1000]

    def test_mixed_indices(self):
        """Test with_periods using both positive and negative indices."""
        data = {"benefit": [[1000, 1000, 1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        # Modify period 1 and last period
        af.benefit_adj = af.benefit.projection.with_periods({1: 1500, -1: 5000})

        result = af.collect()
        benefit_adj = result["benefit_adj"][0]

        assert benefit_adj.to_list() == [1000, 1500, 1000, 1000, 5000]

    def test_benefit_schedule(self):
        """Test creating a benefit schedule with multiple changes."""
        data = {"benefit": [[1000, 1000, 1000, 1000, 1000]]}
        af = ActuarialFrame(data)

        af.benefit_schedule = af.benefit.projection.with_periods(
            {
                2: 1500,
                4: 2000,
            }
        )

        result = af.collect()
        benefit_schedule = result["benefit_schedule"][0]

        assert benefit_schedule.to_list() == [1000, 1000, 1500, 1000, 2000]


class TestCompleteProjection:
    """Integration test for complete actuarial projection."""

    def test_full_projection_workflow(self):
        """Test complete projection with survival, discount, and cashflows."""
        data = {
            "face_amount": [100000],
            "qx": [[0.001, 0.002, 0.003]],
            "annual_premium": [500],
            "interest_rate": [[0.05, 0.05, 0.05]],
        }
        af = ActuarialFrame(data)

        # Calculate cumulative factors
        af.survival_to_t = af.qx.projection.cumulative_survival(start_at=None)
        af.v = af.interest_rate.projection.cumulative_discount(start_at=None)

        # Cashflows (formula IS the code)
        af.death_benefit = af.face_amount * af.qx * af.survival_to_t
        af.premium = af.annual_premium * af.survival_to_t
        af.net_cashflow = af.premium - af.death_benefit

        # Present value
        af.pv_cashflow = af.net_cashflow * af.v

        # Total present value
        af.total_pv = af.pv_cashflow.list.sum()

        result = af.collect()

        # Verify we got results
        assert "survival_to_t" in result.columns
        assert "v" in result.columns
        assert "death_benefit" in result.columns
        assert "premium" in result.columns
        assert "net_cashflow" in result.columns
        assert "pv_cashflow" in result.columns
        assert "total_pv" in result.columns

        # Verify calculations make sense
        survival = result["survival_to_t"][0]
        assert len(survival) == 3
        assert all(0 < s < 1 for s in survival)  # All survival probs between 0 and 1
        assert survival[0] > survival[1] > survival[2]  # Decreasing over time

        v = result["v"][0]
        assert len(v) == 3
        assert all(0 < discount < 1 for discount in v)  # All discount factors < 1
        assert v[0] > v[1] > v[2]  # Decreasing over time

        total_pv = result["total_pv"][0]
        assert isinstance(total_pv, float)


class TestPreviousPeriod:
    """Tests for previous_period() method."""

    def test_list_column_basic(self):
        """Test previous_period with list column and default fill."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_prev = af.value.projection.previous_period()

        result = af.collect()
        value_prev = result["value_prev"][0]

        # Should shift back one period with fill_value=0
        # [100, 110, 120] -> [0, 100, 110]
        assert len(value_prev) == 3
        assert value_prev[0] == 0
        assert value_prev[1] == 100
        assert value_prev[2] == 110

    def test_custom_fill_value(self):
        """Test previous_period with custom fill value."""
        data = {"reserve": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        af.reserve_prev = af.reserve.projection.previous_period(fill_value=500)

        result = af.collect()
        reserve_prev = result["reserve_prev"][0]

        # [1000, 1100, 1200] -> [500, 1000, 1100]
        assert reserve_prev[0] == 500
        assert reserve_prev[1] == 1000
        assert reserve_prev[2] == 1100

    def test_multiple_policies(self):
        """Test previous_period with multiple policies."""
        data = {
            "policy_id": [1, 2],
            "pols_death": [[10, 15, 20], [5, 8, 12]],
        }
        af = ActuarialFrame(data)

        af.pols_death_prev = af.pols_death.projection.previous_period()

        result = af.collect()

        # Policy 1: [10, 15, 20] -> [0, 10, 15]
        prev_1 = result["pols_death_prev"][0]
        assert prev_1[0] == 0
        assert prev_1[1] == 10
        assert prev_1[2] == 15

        # Policy 2: [5, 8, 12] -> [0, 5, 8]
        prev_2 = result["pols_death_prev"][1]
        assert prev_2[0] == 0
        assert prev_2[1] == 5
        assert prev_2[2] == 8


class TestNextPeriod:
    """Tests for next_period() method."""

    def test_list_column_basic(self):
        """Test next_period with list column and default fill."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_next = af.value.projection.next_period()

        result = af.collect()
        value_next = result["value_next"][0]

        # Should shift forward one period with fill_value=0
        # [100, 110, 120] -> [110, 120, 0]
        assert len(value_next) == 3
        assert value_next[0] == 110
        assert value_next[1] == 120
        assert value_next[2] == 0

    def test_custom_fill_value(self):
        """Test next_period with custom fill value."""
        data = {"projected": [[1000, 1100, 1200]]}
        af = ActuarialFrame(data)

        af.projected_next = af.projected.projection.next_period(fill_value=None)

        result = af.collect()
        projected_next = result["projected_next"][0]

        # [1000, 1100, 1200] -> [1100, 1200, None]
        assert projected_next[0] == 1100
        assert projected_next[1] == 1200
        assert projected_next[2] is None


class TestAtPeriod:
    """Tests for at_period() method."""

    def test_negative_offset_t_minus_1(self):
        """Test at_period(-1) equivalent to previous_period()."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_t1 = af.value.projection.at_period(-1)

        result = af.collect()
        value_t1 = result["value_t1"][0]

        # at_period(-1) should match previous_period()
        # [100, 110, 120] -> [0, 100, 110]
        assert value_t1[0] == 0
        assert value_t1[1] == 100
        assert value_t1[2] == 110

    def test_negative_offset_t_minus_2(self):
        """Test at_period(-2) for two periods back."""
        data = {"reserve": [[1000, 1100, 1200, 1300]]}
        af = ActuarialFrame(data)

        af.reserve_t2 = af.reserve.projection.at_period(-2)

        result = af.collect()
        reserve_t2 = result["reserve_t2"][0]

        # [1000, 1100, 1200, 1300] -> [0, 0, 1000, 1100]
        assert reserve_t2[0] == 0
        assert reserve_t2[1] == 0
        assert reserve_t2[2] == 1000
        assert reserve_t2[3] == 1100

    def test_positive_offset_t_plus_1(self):
        """Test at_period(1) equivalent to next_period()."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_tp1 = af.value.projection.at_period(1)

        result = af.collect()
        value_tp1 = result["value_tp1"][0]

        # at_period(1) should match next_period()
        # [100, 110, 120] -> [110, 120, 0]
        assert value_tp1[0] == 110
        assert value_tp1[1] == 120
        assert value_tp1[2] == 0

    def test_positive_offset_t_plus_2(self):
        """Test at_period(2) for two periods ahead."""
        data = {"cashflow": [[1000, 1100, 1200, 1300]]}
        af = ActuarialFrame(data)

        af.cf_tp2 = af.cashflow.projection.at_period(2)

        result = af.collect()
        cf_tp2 = result["cf_tp2"][0]

        # [1000, 1100, 1200, 1300] -> [1200, 1300, 0, 0]
        assert cf_tp2[0] == 1200
        assert cf_tp2[1] == 1300
        assert cf_tp2[2] == 0
        assert cf_tp2[3] == 0

    def test_custom_fill_value(self):
        """Test at_period with custom fill value."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_t1 = af.value.projection.at_period(-1, fill_value=999)

        result = af.collect()
        value_t1 = result["value_t1"][0]

        # [100, 110, 120] -> [999, 100, 110]
        assert value_t1[0] == 999
        assert value_t1[1] == 100
        assert value_t1[2] == 110
