# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""LowerToPolarsPlugin classifies pl.col("state@point") as a state ref.

The compiler emits ``{"kind": "input", "idx": int}`` for precomputed list
columns and ``{"kind": "state", "state": int, "point": int}`` for cross-state
reads. State refs are detected by parsing the column name as ``"state@point"``
and matching against the IR's declared states and points.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Grow, Ratchet
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


class TestStateRefClassification:
    def test_state_ref_emits_state_kind(self, sched: Schedule) -> None:
        # Two states (av, gmdb). gmdb ratchets to av's eop value when an
        # anniversary mask fires. The ratchet target ``pl.col("av@eop")``
        # must classify as a state ref, not an input column.
        ir = IR(
            states=(
                State(name="av", init=pl.col("init")),
                State(name="gmdb", init=pl.col("init")),
            ),
            points=("bop", "eop"),
            transitions=(
                Grow(
                    target=StateRef(state="av", point="eop"),
                    rate=pl.col("rate"),
                    label="Growth",
                ),
                Ratchet(
                    target=StateRef(state="gmdb", point="eop"),
                    to=pl.col("av@eop"),
                    when=pl.col("anniv"),
                    label="GMDB",
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

        ops = kwargs["ops"]
        # Grow uses an input column "rate"
        assert ops[0]["rate_arg"] == {"kind": "input", "idx": 0}
        # Ratchet's `to` is a cross-state read of (av, eop)
        assert ops[1]["to_arg"] == {"kind": "state", "state": 0, "point": 1}
        # Ratchet's `when` is still an input column
        assert ops[1]["when_arg"] == {"kind": "input", "idx": 1}
        # The state ref name "av@eop" must NOT appear in input_columns
        assert "av@eop" not in kwargs["input_columns"]
        assert kwargs["input_columns"] == ["rate", "anniv"]

    def test_at_in_name_but_not_a_state_falls_back_to_input(
        self,
        sched: Schedule,
    ) -> None:
        # A column literally named "extra@info" that is NOT a state@point
        # match (because "extra" isn't a declared state) stays as an input
        # column. This keeps the @ heuristic safe for user-named columns.
        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Grow(
                    target=StateRef(state="av", point="eop"),
                    rate=pl.col("extra@info"),
                    label="G",
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

        ops = kwargs["ops"]
        assert ops[0]["rate_arg"] == {"kind": "input", "idx": 0}
        assert kwargs["input_columns"] == ["extra@info"]
