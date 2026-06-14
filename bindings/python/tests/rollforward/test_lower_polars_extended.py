# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""LowerToPolarsPlugin — extended kwargs schema."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor, Grow
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
        n_periods=3,
        frequency="1M",
    )


def _build_whole_life_ir(sched: Schedule) -> IR:
    return IR(
        states=(State(name="av", init=pl.col("init")),),
        points=("bop", "eop"),
        transitions=(
            Add(
                target=StateRef(state="av", point="eop"),
                expr=pl.col("premium"),
                label="P",
            ),
            Grow(
                target=StateRef(state="av", point="eop"),
                rate=pl.col("rate"),
                label="G",
            ),
            Floor(target=StateRef(state="av", point="eop"), value=0.0),
        ),
        schedule=sched,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=None,
    )


class TestExtendedKwargs:
    def test_extended_keys_present(self, sched: Schedule) -> None:
        ir = _build_whole_life_ir(sched)
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, args = LowerToPolarsPlugin().lower(ir, slots)
        for key in (
            "n_states",
            "n_points",
            "n_periods",
            "bop_idx",
            "eop_idx",
            "input_columns",
            "ops",
            "captures_resolved",
        ):
            assert key in kwargs
        assert kwargs["n_states"] == 1
        assert kwargs["n_points"] == 2
        assert kwargs["n_periods"] == 3
        assert kwargs["bop_idx"] == 0
        assert kwargs["eop_idx"] == 1
        assert kwargs["input_columns"] == ["premium", "rate"]
        # args = state_init + input columns
        assert len(args) == 3

    def test_ops_resolved_to_indices(self, sched: Schedule) -> None:
        ir = _build_whole_life_ir(sched)
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, _ = LowerToPolarsPlugin().lower(ir, slots)
        ops = kwargs["ops"]
        assert ops == [
            {
                "op": "Add",
                "target_state": 0,
                "target_point": 1,
                "expr_arg": {"kind": "input", "idx": 0},
                "label": "P",
            },
            {
                "op": "Grow",
                "target_state": 0,
                "target_point": 1,
                "rate_arg": {"kind": "input", "idx": 1},
                "label": "G",
            },
            {
                "op": "Floor",
                "target_state": 0,
                "target_point": 1,
                "value": 0.0,
            },
        ]

    def test_captures_resolved_state_point_indices(self, sched: Schedule) -> None:
        ir = _build_whole_life_ir(sched)
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, _ = LowerToPolarsPlugin().lower(ir, slots)
        assert kwargs["captures_resolved"] == [{"state": 0, "point": 1}]

    def test_compound_expr_raises_not_implemented(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("a") + pl.col("b"),
                    label="X",
                ),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        with pytest.raises(NotImplementedError, match="Op exprs must be"):
            LowerToPolarsPlugin().lower(ir, slots)

    def test_input_columns_deduplicated(self, sched: Schedule) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("premium"),
                    label="P1",
                ),
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("premium"),
                    label="P2",
                ),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        _, slots = AssignCaptureSlots().apply_with_slots(ir)
        kwargs, _ = LowerToPolarsPlugin().lower(ir, slots)
        assert kwargs["input_columns"] == ["premium"]
        ops = kwargs["ops"]
        assert ops[0]["expr_arg"] == {"kind": "input", "idx": 0}
        assert ops[1]["expr_arg"] == {"kind": "input", "idx": 0}
