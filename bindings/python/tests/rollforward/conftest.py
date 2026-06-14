# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared IR-construction fixtures."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor, Grow
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def monthly_schedule() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


@pytest.fixture
def single_state_ir(monthly_schedule: Schedule) -> IR:
    """Whole-life-style: one state, three transitions."""
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
        schedule=monthly_schedule,
        batch_axes=("policy",),
        track_increments=False,
        lapse_when_all_non_positive=(),
        contract_boundary=None,
    )
