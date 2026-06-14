# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""RollforwardBuilder construction + state declaration tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def monthly_sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestBuilderConstruction:
    def test_single_state_no_points(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("cv_init")},
            schedule=monthly_sched,
        )
        assert list(b._state_inits.keys()) == ["av"]
        assert b._points == ("bop", "eop")
        assert b._schedule is monthly_sched
        assert b._track_increments is False
        assert b._lapse_when_all_non_positive == ()
        assert b._contract_boundary is None

    def test_multi_state_with_explicit_points(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("av_init"), "guarantee": pl.col("g_init")},
            points=["bop", "after_growth", "eop"],
            schedule=monthly_sched,
        )
        assert list(b._state_inits.keys()) == ["av", "guarantee"]
        assert b._points == ("bop", "after_growth", "eop")

    def test_track_increments_flag(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=monthly_sched,
            track_increments=True,
        )
        assert b._track_increments is True

    def test_lapse_kwarg(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init"), "g": pl.col("g_init")},
            schedule=monthly_sched,
            lapse_when_all_non_positive=["av", "g"],
        )
        assert b._lapse_when_all_non_positive == ("av", "g")

    def test_contract_boundary_kwarg(self, monthly_sched: Schedule) -> None:
        b = RollforwardBuilder(
            states={"reserve": pl.col("init")},
            schedule=monthly_sched,
            contract_boundary=pl.col("is_repriceable"),
        )
        assert b._contract_boundary is not None

    def test_user_supplied_points_must_include_bop_and_eop(
        self,
        monthly_sched: Schedule,
    ) -> None:
        with pytest.raises(ValueError, match="points must include 'bop' and 'eop'"):
            RollforwardBuilder(
                states={"av": pl.col("init")},
                points=["pre_event", "post_event"],
                schedule=monthly_sched,
            )

    def test_lapse_state_must_exist(self, monthly_sched: Schedule) -> None:
        with pytest.raises(ValueError, match="lapse_when_all_non_positive.*unknown"):
            RollforwardBuilder(
                states={"av": pl.col("init")},
                schedule=monthly_sched,
                lapse_when_all_non_positive=["does_not_exist"],
            )


class TestBuild:
    def test_build_returns_ir(self, monthly_sched: Schedule) -> None:
        from gaspatchio_core.rollforward._ir import IR

        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=monthly_sched,
        )
        b["av"].add(pl.col("premium"), label="P").floor(0.0)
        ir = b._build()
        assert isinstance(ir, IR)
        assert len(ir.transitions) == 2
        assert ir.points == ("bop", "eop")
        assert ir.batch_axes == ("policy",)

    def test_build_carries_lapse_and_contract_boundary(
        self,
        monthly_sched: Schedule,
    ) -> None:
        b = RollforwardBuilder(
            states={"av": pl.col("init"), "g": pl.col("init2")},
            schedule=monthly_sched,
            lapse_when_all_non_positive=["av"],
            contract_boundary=pl.col("breach"),
        )
        b["av"].add(pl.col("p"), label="P")
        ir = b._build()
        assert ir.lapse_when_all_non_positive == ("av",)
        assert ir.contract_boundary is not None
