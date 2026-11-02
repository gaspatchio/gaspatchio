# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Shared IR-construction fixtures, and the standalone-emission helper."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.rollforward._ir import IR, State
from gaspatchio.rollforward._ops import Add, Floor, Grow
from gaspatchio.rollforward._refs import StateRef
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from gaspatchio.rollforward._compiled import CompiledRollforward


def _standalone_state_expr(
    compiled: CompiledRollforward,
    state: str,
    *,
    point: str = "eop",
) -> pl.Expr:
    """Return the self-contained per-period expression for ``(state, point)``.

    A kernel test runs on a raw Polars frame, where there is no
    ``ActuarialFrame`` to materialise the hidden struct column that
    ``compiled.expr_for`` reads: the expression has to carry its own kernel
    call. That emission is not a door the package publishes --
    ``expr_for`` and ``increment_for`` are the two extractions, and on a
    frame both share one kernel call -- so it is asked for here, where the
    kernel is being tested, rather than from a name a model could import.
    Nothing under ``gaspatchio/`` refers to this helper.
    """
    return compiled._emit(
        "rollforward.state",
        (("state", state), ("point", point), ("shared", False)),
    )


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
