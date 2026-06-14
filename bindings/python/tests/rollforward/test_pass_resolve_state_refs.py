# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""ResolveStateRefs pass — verifies in-period state-read precedence."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Grow
from gaspatchio_core.rollforward._passes import ResolveStateRefs
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def base_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestResolveStateRefs:
    def test_pass_name(self) -> None:
        assert ResolveStateRefs().name() == "resolve_state_refs"

    def test_passes_through_when_all_refs_resolve(
        self,
        base_schedule: Schedule,
    ) -> None:
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "post_coi", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="av", point="post_coi"),
                    expr=pl.col("premium"),
                    label="P",
                ),
                Grow(
                    target=StateRef(state="av", point="eop"),
                    rate=pl.col("rate"),
                    label="G",
                ),
            ),
            schedule=base_schedule,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        out = ResolveStateRefs().apply(ir)
        assert out is ir
