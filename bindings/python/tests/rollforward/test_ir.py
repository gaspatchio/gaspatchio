# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""IR data class tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Floor
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


class TestStateDeclaration:
    def test_basic_construction(self) -> None:
        s = State(name="av", init=pl.col("cv_init"))
        assert s.name == "av"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="state name"):
            State(name="", init=pl.col("init"))


class TestIR:
    def test_basic_construction(self, single_state_ir: IR) -> None:
        assert len(single_state_ir.states) == 1
        assert single_state_ir.states[0].name == "av"
        assert single_state_ir.points == ("bop", "eop")
        assert len(single_state_ir.transitions) == 3
        assert single_state_ir.batch_axes == ("policy",)
        assert single_state_ir.track_increments is False
        assert single_state_ir.lapse_when_all_non_positive == ()
        assert single_state_ir.contract_boundary is None

    def test_is_frozen(self, single_state_ir: IR) -> None:
        with pytest.raises(Exception):
            single_state_ir.batch_axes = ("scenario", "policy")  # type: ignore[misc]

    def test_points_must_include_bop_and_eop(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        with pytest.raises(ValueError, match="points must include 'bop' and 'eop'"):
            IR(
                states=(State(name="av", init=pl.col("cv_init")),),
                points=("post_coi",),  # missing bop and eop
                transitions=(
                    Floor(target=StateRef(state="av", point="post_coi"), value=0.0),
                ),
                schedule=sched,
                batch_axes=("policy",),
                track_increments=False,
                lapse_when_all_non_positive=(),
                contract_boundary=None,
            )

    def test_default_batch_axes_is_policy(self, single_state_ir: IR) -> None:
        # batch_axes default lives at the IR layer — not at the constructor signature
        # since IR is dataclass-frozen with no defaults there. Builder defaults it.
        # Direct IR construction requires explicit value; this test pins behavior.
        assert single_state_ir.batch_axes == ("policy",)

    def test_state_name_uniqueness_required(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=12, frequency="1M"
        )
        with pytest.raises(ValueError, match="duplicate state name"):
            IR(
                states=(
                    State(name="av", init=pl.col("init1")),
                    State(name="av", init=pl.col("init2")),
                ),
                points=("bop", "eop"),
                transitions=(
                    Floor(target=StateRef(state="av", point="eop"), value=0.0),
                ),
                schedule=sched,
                batch_axes=("policy",),
                track_increments=False,
                lapse_when_all_non_positive=(),
                contract_boundary=None,
            )
