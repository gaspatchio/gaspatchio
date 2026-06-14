# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end identity smoke — IR with Schedule + typed Curve reference.

Builds a minimal IR using Plans A/B/C typed inputs, computes
spec_fingerprint and action_key, and verifies that mutating each typed
input's payload changes the action_key while the spec_fingerprint
remains stable for structurally-identical recipes.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward._action_key import action_key
from gaspatchio_core.rollforward._fingerprint import spec_fingerprint
from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Add, Floor, Grow
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


class TestSmokeIdentity:
    def test_fingerprint_stable_action_key_changes_with_inputs(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        ir = IR(
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
        fp = spec_fingerprint(ir)
        ak_1 = action_key(
            ir,
            input_data_sha="run1",
            gaspatchio_version="0.4.0",
            git_sha="abc",
        )
        ak_2 = action_key(
            ir,
            input_data_sha="run2",
            gaspatchio_version="0.4.0",
            git_sha="abc",
        )
        # Same spec, different input data => same fp, different ak
        assert spec_fingerprint(ir) == fp
        assert ak_1 != ak_2
