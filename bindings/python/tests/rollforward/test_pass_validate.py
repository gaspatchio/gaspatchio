# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Validate pass — per-Op verify, point/state consistency."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor
from gaspatchio_core.rollforward._passes import Validate
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def base_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


def _ir_with(transitions: tuple, sched: Schedule, points=("bop", "eop")) -> IR:
    return IR(
        states=(State(name="av", init=pl.col("init")),),
        points=points,
        transitions=transitions,
        schedule=sched,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=None,
    )


class TestValidate:
    def test_passes_through_valid_ir(self, base_schedule: Schedule) -> None:
        ir = _ir_with(
            (
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("p"),
                    label="P",
                ),
                Floor(target=StateRef(state="av", point="eop"), value=0.0),
            ),
            base_schedule,
        )
        out = Validate().apply(ir)
        # Validate is a no-op transform — returns the same IR
        assert out is ir

    def test_op_targeting_unknown_state_raises(self, base_schedule: Schedule) -> None:
        ir = _ir_with(
            (
                Add(
                    target=StateRef(state="ghost", point="eop"),
                    expr=pl.col("p"),
                    label="P",
                ),
            ),
            base_schedule,
        )
        with pytest.raises(ValueError, match="targets unknown state 'ghost'"):
            Validate().apply(ir)

    def test_op_targeting_unknown_point_raises(self, base_schedule: Schedule) -> None:
        ir = _ir_with(
            (
                Add(
                    target=StateRef(state="av", point="ghost"),
                    expr=pl.col("p"),
                    label="P",
                ),
            ),
            base_schedule,
        )
        with pytest.raises(ValueError, match="targets unknown point 'ghost'"):
            Validate().apply(ir)

    def test_track_increments_requires_label_on_every_op(
        self,
        base_schedule: Schedule,
    ) -> None:
        # Floor doesn't take a label — but Add etc. with label=None should fail
        # when track_increments=True.
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("p"),
                    label=None,
                ),
            ),
            schedule=base_schedule,
            batch_axes=("policy",),
            track_increments=True,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        with pytest.raises(ValueError, match="track_increments=True.*requires.*label"):
            Validate().apply(ir)

    def test_pass_name(self) -> None:
        assert Validate().name() == "validate"
