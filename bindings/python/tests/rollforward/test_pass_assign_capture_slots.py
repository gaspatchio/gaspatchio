# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""AssignCaptureSlots — collects (state, point) reads into Struct slots."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor, Ratchet
from gaspatchio_core.rollforward._passes import AssignCaptureSlots
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestAssignCaptureSlots:
    def test_pass_name(self) -> None:
        assert AssignCaptureSlots().name() == "assign_capture_slots"

    def test_eop_is_always_a_capture_slot(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("p"),
                    label="P",
                ),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        # Every state's eop is implicitly captured (so af.av = rf['av'] works)
        assert StateRef(state="av", point="eop") in slots

    def test_distinct_at_reads_get_distinct_slots(self, sched: Schedule) -> None:
        ir = IR(
            states=(
                State(name="av", init=pl.col("init")),
                State(name="g", init=pl.col("g_init")),
            ),
            points=("bop", "after_growth", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="after_growth"),
                    expr=pl.col("growth"),
                    label="G",
                ),
                Ratchet(
                    target=StateRef(state="g", point="eop"),
                    to=pl.col("av_post"),  # cross-state read
                    when=pl.col("anniv"),
                    label="R",
                ),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        # eop slots for both states are implicit
        assert StateRef(state="av", point="eop") in slots
        assert StateRef(state="g", point="eop") in slots

    def test_apply_returns_ir_unchanged(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        out = AssignCaptureSlots().apply(ir)
        assert out is ir
