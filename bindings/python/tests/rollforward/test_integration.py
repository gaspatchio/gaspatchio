"""End-to-end integration tests for the rollforward API."""

from __future__ import annotations

import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward import Step


class TestULRollforward:
    """Full Universal Life product rollforward."""

    def test_ul_basic(self) -> None:
        """UL: add, deduct_nar, charge, grow, floor — verify against manual calculation."""
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0, 100.0]],
            "coi_rate": [[0.001, 0.001]],
            "sum_assured": [[5000.0, 5000.0]],
            "admin_rate": [[0.01, 0.01]],
            "interest_rate": [[0.05, 0.05]],
        })
        af.av = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .deduct_nar(af.coi_rate, death_benefit=af.sum_assured, label="COI")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
            .floor(0)
        )
        result = af.collect()
        av = result["av"].to_list()[0]

        # Manual t0: 1000+100=1100, COI=0.001*max(0,5000-1100)=3.9 → 1096.1
        # Admin: 1096.1*0.99=1085.139, Interest: 1085.139*1.05=1139.39595
        assert abs(av[0] - 1139.39595) < 0.01

    def test_ul_multi_policy(self) -> None:
        """Multiple policies with different data."""
        af = ActuarialFrame({
            "av_init": [1000.0, 5000.0],
            "premium": [[100.0], [500.0]],
            "interest_rate": [[0.05], [0.03]],
        })
        af.av = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .grow(af.interest_rate, "Interest")
        )
        result = af.collect()
        av = result["av"].to_list()

        # Policy 0: (1000+100)*1.05 = 1155
        assert abs(av[0][0] - 1155.0) < 1e-10
        # Policy 1: (5000+500)*1.03 = 5665
        assert abs(av[1][0] - 5665.0) < 1e-10


class TestCompositionVariants:
    """Test creating multiple variants from a base builder."""

    def test_base_and_rider(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
            "admin_rate": [[0.01]],
            "interest_rate": [[0.05]],
            "rider_rate": [[0.005]],
        })
        base = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
            .floor(0)
        )
        with_rider = base.insert_before(
            "Interest", Step.charge(af.rider_rate, "Rider Fee"),
        )

        af.av_base = base
        af.av_rider = with_rider
        result = af.collect()

        # Base: (1000+100)*0.99*1.05 = 1089*1.05 = 1143.45
        assert abs(result["av_base"].to_list()[0][0] - 1143.45) < 0.01
        # Rider: (1000+100)*0.99*0.995*1.05 < base (extra charge)
        assert result["av_rider"].to_list()[0][0] < result["av_base"].to_list()[0][0]

    def test_remove_step(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
            "admin_rate": [[0.01]],
            "interest_rate": [[0.05]],
        })
        base = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
        )
        no_admin = base.remove("Admin")

        af.av_base = base
        af.av_no_admin = no_admin
        result = af.collect()

        # Without admin charge, AV should be higher
        assert result["av_no_admin"].to_list()[0][0] > result["av_base"].to_list()[0][0]


class TestIncrementReconciliation:
    """Verify increments sum to total change."""

    def test_increments_sum(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
            "admin_rate": [[0.01]],
            "interest_rate": [[0.05]],
        })
        af.av = (
            af.projection.rollforward(initial=af.av_init, track_increments=True)
            .add(af.premium, "Premium")
            .charge(af.admin_rate, "Admin")
            .grow(af.interest_rate, "Interest")
        )
        af.prem_inc = af.av.increments["Premium"]
        af.admin_inc = af.av.increments["Admin"]
        af.int_inc = af.av.increments["Interest"]

        result = af.collect()
        av_final = result["av"].to_list()[0][0]
        total_change = av_final - 1000.0
        inc_sum = (
            result["prem_inc"].to_list()[0][0]
            + result["admin_inc"].to_list()[0][0]
            + result["int_inc"].to_list()[0][0]
        )
        assert abs(total_change - inc_sum) < 1e-10


class TestMultiStateIntegration:
    """Multi-state rollforward via the full API."""

    def test_va_gmdb_two_periods(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "g_init": [1000.0],
            "premium": [[100.0, 100.0]],
            "fund_return": [[0.10, -0.15]],
            "roll_up_rate": [[0.03, 0.03]],
        })
        rf = (
            af.projection.rollforward(av=af.av_init, guarantee=af.g_init)
            .on("av").add(af.premium, "Premium")
            .grow(af.fund_return, "Fund Return")
            .floor(0)
            .on("guarantee").ratchet_to("av", "GMDB Ratchet")
            .grow(af.roll_up_rate, "Roll-up")
        )
        af.av = rf["av"]
        af.guarantee = rf["guarantee"]
        result = af.collect()

        av = result["av"].to_list()[0]
        g = result["guarantee"].to_list()[0]

        # t0: av=(1000+100)*1.10=1210, g=max(1000,1210)*1.03=1246.3
        assert abs(av[0] - 1210.0) < 1e-8
        assert abs(g[0] - 1246.3) < 1e-8


class TestExplainOutput:
    def test_explain_prints_cleanly(self) -> None:
        """explain() on a string-based builder produces well-formed output."""
        from gaspatchio_core.rollforward._builder import RollforwardBuilder

        b = RollforwardBuilder(frame=None, initial="av_init").add("p", "Premium")
        output = b.explain()
        assert "Rollforward:" in output
        assert "Premium" in output


class TestFingerprintStability:
    def test_same_structure_same_fingerprint(self) -> None:
        from gaspatchio_core.rollforward._builder import RollforwardBuilder

        b1 = RollforwardBuilder(frame=None, initial="a").add("b", "P")
        b2 = RollforwardBuilder(frame=None, initial="x").add("y", "Q")
        assert b1.fingerprint() == b2.fingerprint()

    def test_different_structure_different_fingerprint(self) -> None:
        from gaspatchio_core.rollforward._builder import RollforwardBuilder

        b1 = RollforwardBuilder(frame=None, initial="a").add("b", "P")
        b2 = RollforwardBuilder(frame=None, initial="a").add("b", "P").grow("c", "G")
        assert b1.fingerprint() != b2.fingerprint()


class TestGrowCapped:
    def test_iul_rollforward(self) -> None:
        """Indexed UL with floor and cap on crediting."""
        af = ActuarialFrame({
            "av_init": [1000.0],
            "premium": [[100.0]],
            "index_return": [[0.15]],  # will be capped at 0.12
            "admin_rate": [[0.01]],
        })
        af.av = (
            af.projection.rollforward(initial=af.av_init)
            .add(af.premium, "Premium")
            .charge(af.admin_rate, "Admin")
            .grow_capped(af.index_return, floor=0.0, cap=0.12, label="Index Credit")
            .floor(0)
        )
        result = af.collect()
        av = result["av"].to_list()[0]

        # (1000+100)*0.99 = 1089, * 1.12 (capped) = 1219.68
        assert abs(av[0] - 1219.68) < 0.01


class TestConditionalSteps:
    def test_add_if(self) -> None:
        af = ActuarialFrame({
            "av_init": [1000.0],
            "is_premium_month": [[1.0, 0.0, 1.0]],
            "premium": [[100.0, 100.0, 100.0]],
        })
        af.av = (
            af.projection.rollforward(initial=af.av_init)
            .add_if(af.is_premium_month, af.premium, "Conditional Premium")
        )
        result = af.collect()
        av = result["av"].to_list()[0]

        assert abs(av[0] - 1100.0) < 1e-10  # condition=1: add
        assert abs(av[1] - 1100.0) < 1e-10  # condition=0: no add
        assert abs(av[2] - 1200.0) < 1e-10  # condition=1: add
