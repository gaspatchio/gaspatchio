# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""engine_binding static walk — closed-subset whitelist."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._engine_binding import derive_engine_binding
from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Apply, Floor, Grow
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def base_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


def _ir_with_transitions(
    transitions: tuple,
    schedule: Schedule,
    contract_boundary: pl.Expr | None = None,
) -> IR:
    return IR(
        states=(State(name="av", init=pl.col("init")),),
        points=("bop", "eop"),
        transitions=transitions,
        schedule=schedule,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=contract_boundary,
    )


class TestEngineBinding:
    def test_closed_subset_only_is_portable(self, base_schedule: Schedule) -> None:
        ir = _ir_with_transitions(
            (
                Add(
                    target=StateRef(state="av", point="eop"),
                    expr=pl.col("premium"),
                    label="P",
                ),
                Floor(target=StateRef(state="av", point="eop"), value=0.0),
            ),
            base_schedule,
        )
        assert derive_engine_binding(ir) == "portable"

    def test_pl_max_horizontal_in_apply_body_flips_to_polars(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = _ir_with_transitions(
            (
                Apply(
                    target=StateRef(state="av", point="eop"),
                    body=pl.max_horizontal(pl.col("a"), pl.col("b")),
                    label="Custom",
                ),
            ),
            base_schedule,
        )
        assert derive_engine_binding(ir) == "polars"

    def test_pl_max_horizontal_in_contract_boundary_flips_to_polars(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = _ir_with_transitions(
            (Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            base_schedule,
            contract_boundary=pl.max_horizontal(pl.col("a"), pl.col("b")) > 0,
        )
        assert derive_engine_binding(ir) == "polars"

    def test_simple_arithmetic_in_transition_body_is_portable(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = _ir_with_transitions(
            (
                Grow(
                    target=StateRef(state="av", point="eop"),
                    rate=pl.col("base") - pl.col("fee"),
                    label="Net growth",
                ),
            ),
            base_schedule,
        )
        assert derive_engine_binding(ir) == "portable"
