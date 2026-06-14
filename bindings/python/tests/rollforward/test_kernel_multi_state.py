# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end multi-state §4.7 VA + GMDB ratchet path.

Exercises the kernel's multi-point seeding and chain semantics:
- 3 declared points (bop, after_growth, eop)
- Two states (av, guarantee), each with its own Op chain
- between(p1, p2) scoping for av (grow during bop->after_growth, floor during
  after_growth->eop)
- Ratchet with when= conditional firing on the guarantee state
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestVaGmdbRatchet:
    def test_av_grows_guarantee_ratchets_at_anniversary(self) -> None:
        # 12-period schedule; anniversary fires only at period 11 (t=11)
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init"), "guarantee": pl.col("av_init")},
            points=["bop", "after_growth", "eop"],
            schedule=sched,
        )
        b["av"].between("bop", "after_growth").grow(pl.col("fund_return"), label="G")
        b["av"].between("after_growth", "eop").floor(0.0)
        b["guarantee"].grow(pl.col("roll_up"), label="RollUp")
        b["guarantee"].ratchet(
            to=pl.col("av_after_growth"),
            when=pl.col("anniv"),
            label="GMDB",
        )
        compiled = compile_rollforward(b)

        # Single policy; constant 1% fund return, 4%/12 monthly roll-up,
        # av-after-growth placeholder = 130.0 at anniversary.
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "fund_return": [[0.01] * 12],
                "roll_up": [[0.04 / 12] * 12],
                "av_after_growth": [[101.0] * 11 + [130.0]],
                "anniv": [[False] * 11 + [True]],
            }
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(
            av=collector.expr_for("av"),
            g=collector.expr_for("guarantee"),
        )
        # AV: 100 -> grow by 1% each period -> 100 * 1.01^12 ≈ 112.68
        av = result.get_column("av").to_list()[0]
        assert av[-1] == pytest.approx(100 * 1.01**12, rel=1e-9)
        # Guarantee rolls up at 4%/12 per month for 12 months → 100 * (1+0.04/12)^12
        # then ratchets to 130 at the final anniversary.
        g = result.get_column("g").to_list()[0]
        # Period 0: roll_up gives 100*(1+0.04/12) ≈ 100.333; anniv False → no ratchet
        assert g[0] == pytest.approx(100 * (1 + 0.04 / 12), rel=1e-9)
        # Period 11: rolled-up value is 100 * (1+0.04/12)^12 ≈ 104.07; anniv fires →
        # max(104.07, 130) = 130.0
        assert g[-1] == pytest.approx(130.0, rel=1e-9)


class TestDeductNAR:
    def test_coi_charged_against_net_amount_at_risk(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=2,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            schedule=sched,
        )
        b["av"].deduct_nar(pl.col("coi"), death_benefit=pl.col("db"), label="COI")
        compiled = compile_rollforward(b)

        # av=100, coi=0.01, db=200 → NAR=100 → charge=0.01*100=1.0 → av=99
        # Period 1: av=99, coi=0.01, db=200 → NAR=101 → charge=1.01 → av=97.99
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "coi": [[0.01, 0.01]],
                "db": [[200.0, 200.0]],
            }
        )
        collector = RollforwardCollector(compiled)
        av = df.with_columns(av=collector.expr_for("av")).get_column("av").to_list()[0]
        assert av[0] == pytest.approx(99.0, rel=1e-9)
        assert av[1] == pytest.approx(97.99, rel=1e-9)


class TestGrowCapped:
    def test_rate_clamped_to_floor_and_cap(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            schedule=sched,
        )
        b["av"].grow_capped(
            pl.col("rate"),
            floor=pl.col("floor"),
            cap=pl.col("cap"),
            label="G",
        )
        compiled = compile_rollforward(b)

        # rates [-0.5, 0.05, 1.0] clamped to [-0.10, 0.20]:
        # period 0: clamped=-0.10 → av *= 0.90 → 90
        # period 1: clamped= 0.05 → av *= 1.05 → 94.5
        # period 2: clamped= 0.20 → av *= 1.20 → 113.4
        df = pl.DataFrame(
            {
                "av_init": [100.0],
                "rate": [[-0.5, 0.05, 1.0]],
                "floor": [[-0.1, -0.1, -0.1]],
                "cap": [[0.2, 0.2, 0.2]],
            }
        )
        collector = RollforwardCollector(compiled)
        av = df.with_columns(av=collector.expr_for("av")).get_column("av").to_list()[0]
        assert av == pytest.approx([90.0, 94.5, 113.4], rel=1e-9)


class TestApplyEscapeHatch:
    def test_apply_raises_phase_1_pending(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=2,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            schedule=sched,
        )
        b["av"].apply(pl.col("override"))
        compiled = compile_rollforward(b)

        df = pl.DataFrame({"av_init": [100.0], "override": [[50.0, 60.0]]})
        collector = RollforwardCollector(compiled)
        with pytest.raises(
            pl.exceptions.ComputeError, match="Apply is an escape hatch"
        ):
            df.with_columns(av=collector.expr_for("av"))
