# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""LowerToPolarsPlugin — emits plugin_kwargs dict for the kernel."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor
from gaspatchio_core.rollforward._passes import (
    AssignCaptureSlots,
    LowerToPolarsPlugin,
)
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestLowerToPolarsPlugin:
    def test_pass_name(self) -> None:
        assert LowerToPolarsPlugin().name() == "lower_polars"

    def test_emits_plugin_kwargs_with_canonical_keys(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("p"),
                    label="P",
                ),
                Floor(target=StateRef(state="av", point="eop"), value=0.0),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, _ = LowerToPolarsPlugin().lower(ir, slots)
        assert "ir" in kwargs
        assert "captures" in kwargs
        assert "track_increments" in kwargs
        assert "lapse_when_all_non_positive" in kwargs
        assert "contract_boundary" in kwargs

    def test_kwargs_ir_field_is_canonical_form(self, sched: Schedule) -> None:
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
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, _ = LowerToPolarsPlugin().lower(ir, slots)
        assert isinstance(kwargs["ir"], dict)  # canonical form
        assert "transitions" in kwargs["ir"]

    def test_captures_serialised_as_state_point_pairs(self, sched: Schedule) -> None:
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
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, _ = LowerToPolarsPlugin().lower(ir, slots)
        assert kwargs["captures"] == [["av", "eop"]]
