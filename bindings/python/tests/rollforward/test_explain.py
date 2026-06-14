# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""explain() rendering tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._explain import explain
from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor, Grow
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def whole_life_ir() -> IR:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=240,
        frequency="1M",
    )
    return IR(
        states=(State(name="av", init=pl.col("cv_init")),),
        points=("bop", "eop"),
        transitions=(
            Add(
                target=StateRef(state="av", point="eop"),
                expr=pl.col("premium"),
                label="Premium",
            ),
            Grow(
                target=StateRef(state="av", point="eop"),
                rate=pl.col("interest"),
                label="Interest",
            ),
            Floor(target=StateRef(state="av", point="eop"), value=0.0),
        ),
        schedule=sched,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=None,
    )


class TestExplain:
    def test_includes_spec_fingerprint(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "spec_fingerprint = sha256:" in out

    def test_lists_states_with_init(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "States:" in out
        assert "av:" in out
        assert "init=" in out

    def test_lists_points(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "Points:  bop, eop" in out

    def test_includes_schedule_summary(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "Schedule:" in out
        assert "from_calendar_grid" in out

    def test_lists_transitions_in_order(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        prem_pos = out.find("Premium")
        int_pos = out.find("Interest")
        floor_pos = out.find("Floor")
        assert 0 < prem_pos < int_pos < floor_pos

    def test_includes_engine_binding(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "engine_binding:" in out
        assert ("portable" in out) or ("polars" in out)

    def test_includes_batch_axes(self, whole_life_ir: IR) -> None:
        out = explain(whole_life_ir)
        assert "batch_axes:" in out
