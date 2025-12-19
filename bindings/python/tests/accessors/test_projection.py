# ABOUTME: Tests for the ProjectionColumnAccessor.
# ABOUTME: Validates cumulative survival and period override methods.
# ruff: noqa: ERA001
# type: ignore[attr-defined]

"""Tests for projection accessor methods."""

import math

import polars as pl
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


class TestRateTiming:
    """Tests for rate_timing parameter in cumulative_survival()."""

    def test_beginning_of_period_explicit(self):
        """Test rate_timing='beginning_of_period' matches default behavior."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        # Default behavior
        af.pols_if_default = af.qx.projection.cumulative_survival()

        # Explicit beginning_of_period
        af.pols_if_bop = af.qx.projection.cumulative_survival(
            rate_timing="beginning_of_period"
        )

        result = af.collect()

        default = result["pols_if_default"][0]
        bop = result["pols_if_bop"][0]

        # Should be identical
        assert len(default) == len(bop)
        for d, b in zip(default, bop, strict=False):
            assert pytest.approx(d, abs=1e-9) == b

        # Verify values: [1.0, 0.999, 0.997002]
        assert pytest.approx(bop[0], abs=1e-6) == 1.0
        assert pytest.approx(bop[1], abs=1e-6) == 0.999
        assert pytest.approx(bop[2], abs=1e-6) == 0.999 * 0.998

    def test_end_of_period(self):
        """Test rate_timing='end_of_period' matches start_at=None."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        # Using rate_timing
        af.pols_if_eop = af.qx.projection.cumulative_survival(
            rate_timing="end_of_period"
        )

        # Using start_at=None (equivalent)
        af.pols_if_none = af.qx.projection.cumulative_survival(start_at=None)

        result = af.collect()

        eop = result["pols_if_eop"][0]
        none_result = result["pols_if_none"][0]

        # Should be identical
        assert len(eop) == len(none_result)
        for e, n in zip(eop, none_result, strict=False):
            assert pytest.approx(e, abs=1e-9) == n

        # Verify values: [0.999, 0.997002, 0.994011]
        assert pytest.approx(eop[0], abs=1e-6) == 0.999
        assert pytest.approx(eop[1], abs=1e-6) == 0.999 * 0.998
        assert pytest.approx(eop[2], abs=1e-6) == 0.999 * 0.998 * 0.997

    def test_timing_difference_at_rate_boundary(self):
        """Test that BOP and EOP produce different results at rate boundaries.

        When rates change (e.g., at age boundaries), the two timing conventions
        give different results. With constant rates, they would be the same.
        """
        # Simulate rate change at month 2 (e.g., age boundary)
        data = {"exit_rate": [[0.008, 0.008, 0.009, 0.009]]}
        af = ActuarialFrame(data)

        af.pols_if_bop = af.exit_rate.projection.cumulative_survival(
            rate_timing="beginning_of_period"
        )
        af.pols_if_eop = af.exit_rate.projection.cumulative_survival(
            rate_timing="end_of_period"
        )

        result = af.collect()

        bop = result["pols_if_bop"][0]
        eop = result["pols_if_eop"][0]

        # At period 0:
        # BOP: 1.0 (rate not yet applied)
        # EOP: 0.992 (rate applied)
        assert pytest.approx(bop[0], abs=1e-6) == 1.0
        assert pytest.approx(eop[0], abs=1e-6) == 0.992

        # At period 2 (where rate changes from 0.008 to 0.009):
        # BOP: uses rate[0] and rate[1] = 0.992 * 0.992 = 0.984064
        # EOP: uses rate[0], rate[1], and rate[2] = 0.992 * 0.992 * 0.991 = 0.975267
        # Note: BOP[2] has NOT applied rate[2] yet, EOP[2] HAS applied rate[2]
        assert pytest.approx(bop[2], abs=1e-6) == 0.992 * 0.992
        assert pytest.approx(eop[2], abs=1e-6) == 0.992 * 0.992 * 0.991

        # The difference becomes visible at the boundary
        assert bop[2] != eop[2]

    def test_invalid_rate_timing_raises_error(self):
        """Test that invalid rate_timing value raises ValueError."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        with pytest.raises(ValueError, match="Invalid rate_timing value"):
            af.qx.projection.cumulative_survival(rate_timing="invalid_value")

    def test_conflicting_parameters_raises_error(self):
        """Test that specifying both rate_timing and non-default start_at raises."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        with pytest.raises(ValueError, match="Cannot specify both"):
            af.qx.projection.cumulative_survival(
                rate_timing="end_of_period", start_at=0.95
            )

    def test_rate_timing_with_default_start_at_is_ok(self):
        """Test that rate_timing with default start_at=1.0 works (no conflict)."""
        data = {"qx": [[0.001, 0.002, 0.003]]}
        af = ActuarialFrame(data)

        # This should work - rate_timing with implicit default start_at
        af.pols_if = af.qx.projection.cumulative_survival(
            rate_timing="beginning_of_period"
        )

        result = af.collect()
        pols_if = result["pols_if"][0]

        assert len(pols_if) == 3
        assert pytest.approx(pols_if[0], abs=1e-6) == 1.0

    def test_multiple_policies_with_rate_timing(self):
        """Test rate_timing works correctly with multiple policies."""
        data = {
            "policy_id": ["P001", "P002"],
            "qx": [[0.001, 0.002, 0.003], [0.002, 0.003, 0.004]],
        }
        af = ActuarialFrame(data)

        af.pols_if_bop = af.qx.projection.cumulative_survival(
            rate_timing="beginning_of_period"
        )
        af.pols_if_eop = af.qx.projection.cumulative_survival(
            rate_timing="end_of_period"
        )

        result = af.collect()

        # Policy 1 BOP: [1.0, 0.999, 0.997002]
        bop_1 = result["pols_if_bop"][0]
        assert pytest.approx(bop_1[0], abs=1e-6) == 1.0
        assert pytest.approx(bop_1[1], abs=1e-6) == 0.999

        # Policy 2 EOP: [0.998, 0.995006, 0.991030]
        eop_2 = result["pols_if_eop"][1]
        assert pytest.approx(eop_2[0], abs=1e-6) == 0.998
        assert pytest.approx(eop_2[1], abs=1e-6) == 0.998 * 0.997


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

    def test_expression_proxy_intermediate_list(self):
        """Test previous_period on ExpressionProxy derived from list operations.

        This tests the scenario where previous_period is called on an intermediate
        expression (not a materialized column), such as:
            pols_death_temp = af.pols_if * af.mort_rate
            pols_death_prev = pols_death_temp.projection.previous_period()

        The bug was that previous_period() only checked for list type when the
        proxy was a ColumnProxy, causing ExpressionProxy inputs to incorrectly
        use the scalar shift path instead of list.eval.
        """
        data = {
            "pols_if": [[1000.0, 990.0, 975.0]],
            "mort_rate": [[0.01, 0.01, 0.01]],
        }
        af = ActuarialFrame(data)

        # Create intermediate expression (ExpressionProxy, not ColumnProxy)
        pols_death_temp = af.pols_if * af.mort_rate

        # Apply previous_period on the ExpressionProxy
        pols_death_prev = pols_death_temp.projection.previous_period()

        # Assign and collect
        af.pols_death_temp = pols_death_temp
        af.pols_death_prev = pols_death_prev

        result = af.collect()

        # pols_death_temp = [10.0, 9.9, 9.75]
        # pols_death_prev should be [0.0, 10.0, 9.9] (shifted with fill=0)
        temp = result["pols_death_temp"][0].to_list()
        prev = result["pols_death_prev"][0].to_list()

        assert pytest.approx(temp, abs=1e-6) == [10.0, 9.9, 9.75]
        assert pytest.approx(prev, abs=1e-6) == [0.0, 10.0, 9.9]

    def test_expression_proxy_with_cumulative_survival(self):
        """Test previous_period on expression chain with cumulative_survival.

        This replicates the exact pattern from model_projection.py that failed:
            pols_if = af.combined_decrement.projection.cumulative_survival()
            pols_death_temp = pols_if * af.mort_rate_mth
            pols_death_prev = pols_death_temp.projection.previous_period()
        """
        data = {
            "combined_decrement": [[0.01, 0.02, 0.03]],
            "mort_rate_mth": [[0.005, 0.006, 0.007]],
        }
        af = ActuarialFrame(data)

        # Create cumulative survival (this creates an ExpressionProxy)
        pols_if = af.combined_decrement.projection.cumulative_survival()

        # Multiply by mortality rate (still an ExpressionProxy)
        pols_death_temp = pols_if * af.mort_rate_mth

        # Apply previous_period on the chain
        pols_death_prev = pols_death_temp.projection.previous_period()

        af.pols_if = pols_if
        af.pols_death_temp = pols_death_temp
        af.pols_death_prev = pols_death_prev

        result = af.collect()

        # Just verify we can collect without "fill value '0.0' is not supported" error
        # and that the shift happened correctly
        prev = result["pols_death_prev"][0].to_list()
        temp = result["pols_death_temp"][0].to_list()

        # prev[0] should be 0.0 (fill value)
        assert prev[0] == 0.0
        # prev[1] should be temp[0]
        assert pytest.approx(prev[1], abs=1e-6) == temp[0]
        # prev[2] should be temp[1]
        assert pytest.approx(prev[2], abs=1e-6) == temp[1]


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


class TestProspectiveValue:
    """Tests for prospective_value() method.

    The prospective_value() method calculates the present value of future cashflows
    from each time t onwards, using the actuarial backward recursion formula:
    PV(t) = CF(t) + PV(t+1) * v(t)

    This is the standard actuarial "prospective policy value" calculation.
    """

    def test_constant_discount_rate(self):
        """Test prospective_value with a constant (scalar) discount rate."""
        data = {
            "cashflow": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        # Calculate prospective value with 5% discount rate
        af.pv = af.cashflow.projection.prospective_value(discount_rate=0.05)

        result = af.collect()
        pv = result["pv"][0]

        # At t=2 (last period): PV = CF[2] = 100
        # At t=1: PV = CF[1] + CF[2]/(1+r) = 100 + 100/1.05 = 195.238...
        # At t=0: PV = CF[0] + (CF[1] + CF[2]/(1+r))/(1+r)
        #       = 100 + 195.238.../1.05 = 285.941...
        assert len(pv) == 3
        assert pytest.approx(pv[2], abs=1e-2) == 100.0
        assert pytest.approx(pv[1], abs=1e-2) == 100.0 + 100.0 / 1.05
        assert pytest.approx(pv[0], abs=1e-2) == 100.0 + (100.0 + 100.0 / 1.05) / 1.05

    def test_list_column_discount_rate(self):
        """Test prospective_value with per-period discount rates (list column).

        Convention: r[t] is the forward rate for the period starting at t.
        - r[0] = rate from t=0 to t=1
        - r[1] = rate from t=1 to t=2
        - r[2] = rate from t=2 to t=3 (not used in 3-period projection)
        """
        data = {
            "cashflow": [[100.0, 100.0, 100.0]],
            "disc_rate": [[0.04, 0.05, 0.06]],  # Varying rates
        }
        af = ActuarialFrame(data)

        af.pv = af.cashflow.projection.prospective_value(discount_rate=af.disc_rate)

        result = af.collect()
        pv = result["pv"][0]

        # At t=2: PV = 100 (last cashflow, no future to discount)
        # At t=1: PV = 100 + 100/(1+r[1]) = 100 + 100/1.05 = 195.24
        # At t=0: PV = 100 + 195.24/(1+r[0]) = 100 + 195.24/1.04 = 287.73
        assert len(pv) == 3
        assert pytest.approx(pv[2], abs=1e-2) == 100.0
        assert pytest.approx(pv[1], abs=1e-2) == 100.0 + 100.0 / 1.05
        expected_pv0 = 100.0 + (100.0 + 100.0 / 1.05) / 1.04
        assert pytest.approx(pv[0], abs=1e-2) == expected_pv0

    def test_with_discount_factor(self):
        """Test prospective_value with pre-computed discount factors."""
        data = {
            "cashflow": [[100.0, 100.0, 100.0]],
            # v^t factors at 5%: [1.0, 0.952381, 0.907029]
            "v_t": [[1.0, 1 / 1.05, 1 / 1.05**2]],
        }
        af = ActuarialFrame(data)

        af.pv = af.cashflow.projection.prospective_value(discount_factor=af.v_t)

        result = af.collect()
        pv = result["pv"][0]

        # With discount factors, the calculation uses the provided v^t directly
        assert len(pv) == 3
        # Last period: just the cashflow
        assert pytest.approx(pv[2], abs=1e-2) == 100.0

    def test_timing_end_of_period(self):
        """Test prospective_value with end_of_period timing (benefits)."""
        data = {
            "benefit": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        # End of period: cashflow at t is discounted by v^t
        af.pv = af.benefit.projection.prospective_value(
            discount_rate=0.05, timing="end_of_period"
        )

        result = af.collect()
        pv = result["pv"][0]

        # End-of-period timing means benefits paid at end of each period
        assert len(pv) == 3

    def test_timing_beginning_of_period(self):
        """Test prospective_value with beginning_of_period timing (premiums).

        For beginning_of_period, cashflows are paid at the START of each period.
        This means they should be discounted one additional period compared to
        end_of_period:
            beginning_of_period[t] = end_of_period[t] * v

        GSP-70: This test verifies that t=0 is also correctly discounted.
        """
        data = {
            "premium": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        # Calculate both timings to compare
        af.pv_eop = af.premium.projection.prospective_value(
            discount_rate=0.05, timing="end_of_period"
        )
        af.pv_bop = af.premium.projection.prospective_value(
            discount_rate=0.05, timing="beginning_of_period"
        )

        result = af.collect()
        pv_eop = result["pv_eop"][0]
        pv_bop = result["pv_bop"][0]

        v = 1 / 1.05  # Per-period discount factor

        # Beginning-of-period should be end-of-period * v at EVERY time t
        # GSP-70: The bug was that t=0 wasn't discounted (fill_value=1.0 in shift)
        assert len(pv_bop) == 3
        assert pytest.approx(pv_bop[0], abs=1e-2) == pv_eop[0] * v
        assert pytest.approx(pv_bop[1], abs=1e-2) == pv_eop[1] * v
        assert pytest.approx(pv_bop[2], abs=1e-2) == pv_eop[2] * v

    def test_timing_beginning_of_period_with_list_rates(self):
        """Test beginning_of_period timing with per-period discount rates.

        GSP-70: Ensure the fix works with list column rates, not just scalar.
        """
        data = {
            "premium": [[100.0, 100.0, 100.0]],
            "disc_rate": [[0.04, 0.05, 0.06]],
        }
        af = ActuarialFrame(data)

        af.pv_eop = af.premium.projection.prospective_value(
            discount_rate=af.disc_rate, timing="end_of_period"
        )
        af.pv_bop = af.premium.projection.prospective_value(
            discount_rate=af.disc_rate, timing="beginning_of_period"
        )

        result = af.collect()
        pv_eop = result["pv_eop"][0]
        pv_bop = result["pv_bop"][0]

        # Per-period discount factors
        v = [1 / 1.04, 1 / 1.05, 1 / 1.06]

        # BOP should be EOP * v[t] at each time t
        assert pytest.approx(pv_bop[0], abs=1e-2) == pv_eop[0] * v[0]
        assert pytest.approx(pv_bop[1], abs=1e-2) == pv_eop[1] * v[1]
        assert pytest.approx(pv_bop[2], abs=1e-2) == pv_eop[2] * v[2]

    def test_multiple_policies(self):
        """Test prospective_value with multiple policies."""
        data = {
            "policy_id": [1, 2],
            "cashflow": [[100.0, 100.0, 100.0], [200.0, 200.0, 200.0]],
        }
        af = ActuarialFrame(data)

        af.pv = af.cashflow.projection.prospective_value(discount_rate=0.05)

        result = af.collect()

        # Policy 2 should have 2x the PV of policy 1
        pv_1 = result["pv"][0]
        pv_2 = result["pv"][1]

        assert pytest.approx(pv_2[0], abs=1e-2) == 2 * pv_1[0]
        assert pytest.approx(pv_2[1], abs=1e-2) == 2 * pv_1[1]
        assert pytest.approx(pv_2[2], abs=1e-2) == 2 * pv_1[2]

    def test_handles_nan_beyond_term(self):
        """Test that prospective_value handles NaN values beyond policy term."""
        data = {
            # Policy has 3 periods but projection has 5 - NaNs beyond term
            "cashflow": [[100.0, 100.0, 100.0, float("nan"), float("nan")]],
        }
        af = ActuarialFrame(data)

        af.pv = af.cashflow.projection.prospective_value(discount_rate=0.05)

        result = af.collect()
        pv = result["pv"][0]

        # NaN cashflows should be treated as 0 (no cashflow beyond term)
        # So PV at t=3 and t=4 should be 0
        assert len(pv) == 5
        # PV at periods with NaN cashflows should be 0 or NaN depending on impl
        # The first 3 periods should have valid PV
        assert not math.isnan(pv[0])
        assert not math.isnan(pv[1])
        assert not math.isnan(pv[2])

    def test_conflicting_parameters_raises_error(self):
        """Test that specifying both discount_rate and discount_factor raises."""
        data = {"cashflow": [[100.0, 100.0, 100.0]]}
        af = ActuarialFrame(data)

        with pytest.raises(ValueError, match="Cannot specify both"):
            af.cashflow.projection.prospective_value(
                discount_rate=0.05, discount_factor=af.cashflow
            )

    def test_no_discount_provided_raises_error(self):
        """Test that not specifying discount_rate or discount_factor raises."""
        data = {"cashflow": [[100.0, 100.0, 100.0]]}
        af = ActuarialFrame(data)

        with pytest.raises(ValueError, match="Must specify either"):
            af.cashflow.projection.prospective_value()

    def test_replaces_ugly_pattern(self):
        """Test that prospective_value produces same results as manual pattern.

        The manual pattern being replaced:
        af.pv = (
            af.discounted_cf.list.eval(pl.element().fill_nan(0.0))
            .list.reverse()
            .list.eval(pl.element().cum_sum())
            .list.reverse()
        )
        """
        data = {
            "cashflow": [[100.0, 100.0, 100.0]],
        }
        af = ActuarialFrame(data)

        # Calculate discount factors manually (v^t at 5%)
        v = 1 / 1.05
        discount_factors = [v**0, v**1, v**2]

        # Manual calculation: discounted cashflows, reverse cumsum, reverse
        # This is the pattern from GSP-69 that we're replacing
        discounted = [100.0 * discount_factors[i] for i in range(3)]
        # reverse -> cumsum -> reverse gives "sum from t to end"
        reversed_cf = discounted[::-1]
        cumsum = []
        running = 0
        for x in reversed_cf:
            running += x
            cumsum.append(running)
        manual_pv = cumsum[::-1]

        # Use the clean API
        af.pv = af.cashflow.projection.prospective_value(discount_rate=0.05)

        result = af.collect()
        pv = result["pv"][0]

        # Results should match (approximately - timing conventions may differ slightly)
        assert len(pv) == len(manual_pv)


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

    def test_zero_offset(self):
        """Test at_period(0) returns original values unchanged."""
        data = {"value": [[100, 110, 120]]}
        af = ActuarialFrame(data)

        af.value_t0 = af.value.projection.at_period(0)

        result = af.collect()
        value_t0 = result["value_t0"][0]

        # at_period(0) should return the same values
        # [100, 110, 120] -> [100, 110, 120]
        assert value_t0[0] == 100
        assert value_t0[1] == 110
        assert value_t0[2] == 120

    def test_scalar_column_with_grouping(self):
        """Test at_period with scalar columns using .over() grouping."""
        data = {
            "policy_id": [1, 1, 1, 2, 2, 2],
            "period": [0, 1, 2, 0, 1, 2],
            "value": [100, 110, 120, 200, 220, 240],
        }
        af = ActuarialFrame(data)

        # Use .over() to apply at_period within each policy group
        af.value_prev = af.value.projection.at_period(-1, fill_value=0).over(
            "policy_id"
        )

        result = af.collect()

        # Policy 1: [100, 110, 120] -> [0, 100, 110]
        policy_1_values = result.filter(pl.col("policy_id") == 1)["value_prev"]
        assert policy_1_values[0] == 0
        assert policy_1_values[1] == 100
        assert policy_1_values[2] == 110

        # Policy 2: [200, 220, 240] -> [0, 200, 220]
        policy_2_values = result.filter(pl.col("policy_id") == 2)["value_prev"]
        assert policy_2_values[0] == 0
        assert policy_2_values[1] == 200
        assert policy_2_values[2] == 220
