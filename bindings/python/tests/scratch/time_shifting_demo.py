# ABOUTME: Integration test demonstrating time-shifting API with actuarial patterns.
# ABOUTME: Shows inforce rollforward, reserve calculations, and period comparisons.
# ruff: noqa: INP001, ANN201, S101, PLR2004, T201
"""Integration test for time-shifting methods in actuarial projections."""

from gaspatchio_core import ActuarialFrame


def test_inforce_rollforward_pattern():
    """Test complete inforce rollforward using previous_period."""
    data = {
        "policy_id": [1],
        "qx": [[0.001, 0.0011, 0.0012, 0.0013]],
        "lapse_rate": [[0.05, 0.05, 0.05, 0.05]],
    }
    af = ActuarialFrame(data)

    # Build survival and lapse decrements
    af.survival = af.qx.projection.cumulative_survival(start_at=1.0)
    af.pols_death = af.survival * af.qx

    # Calculate inforce using previous period pattern
    af.pols_if_prev = af.survival.projection.previous_period(fill_value=1.0)
    af.pols_lapse = af.pols_if_prev * af.lapse_rate

    result = af.collect()

    # Verify previous period shift worked correctly
    survival = result["survival"][0]
    pols_if_prev = result["pols_if_prev"][0]

    assert pols_if_prev[0] == 1.0  # Initial value
    assert pols_if_prev[1] == survival[0]  # Shifted from previous
    assert pols_if_prev[2] == survival[1]


def test_reserve_rollforward_formula():
    """Test reserve rollforward using at_period for t-1."""
    data = {
        "reserve": [[0, 950, 1900, 2850]],
        "premium": [[1000, 1000, 1000, 1000]],
        "interest_earned": [[50, 52, 55, 58]],
        "claims": [[100, 102, 105, 108]],
    }
    af = ActuarialFrame(data)

    # Reserve formula: Reserve(t) = Reserve(t-1) + Premium(t) + Interest(t) - Claims(t)
    af.reserve_t1 = af.reserve.projection.at_period(-1)
    af.reserve_calc = af.reserve_t1 + af.premium + af.interest_earned - af.claims

    result = af.collect()

    reserve_calc = result["reserve_calc"][0]
    reserve_actual = result["reserve"][0]

    # First period: Reserve_calc(0) = 0 + 1000 + 50 - 100 = 950
    assert reserve_calc[0] == 950
    assert reserve_actual[1] == 950

    # Second period: Reserve_calc(1) = 0 + 1000 + 52 - 102 = 950
    # (reserve_t1[1] = 0 because reserve[0] = 0)
    assert reserve_calc[1] == 950

    # Third period: Reserve_calc(2) = 950 + 1000 + 55 - 105 = 1900
    assert reserve_calc[2] == 1900
    assert reserve_actual[3] == 2850


def test_period_over_period_comparison():
    """Test using at_period for multiple offset comparisons."""
    data = {
        "cashflow": [[1000, 1100, 1050, 1200, 1250]],
    }
    af = ActuarialFrame(data)

    # Calculate growth vs previous period
    af.cf_prev = af.cashflow.projection.previous_period()
    af.growth_1 = af.cashflow - af.cf_prev

    # Calculate growth vs two periods back
    af.cf_2_ago = af.cashflow.projection.at_period(-2)
    af.growth_2 = af.cashflow - af.cf_2_ago

    result = af.collect()

    growth_1 = result["growth_1"][0]
    growth_2 = result["growth_2"][0]

    # Period 1: 1100 - 1000 = 100
    assert growth_1[1] == 100

    # Period 2: 1050 - 1000 = 50 (comparing to 2 periods back)
    assert growth_2[2] == 50


if __name__ == "__main__":
    test_inforce_rollforward_pattern()
    test_reserve_rollforward_formula()
    test_period_over_period_comparison()
    print("All integration tests passed!")
