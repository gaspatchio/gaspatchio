# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""spec_fingerprint stability and sensitivity."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import polars as pl

from gaspatchio.rollforward._fingerprint import spec_fingerprint
from gaspatchio.rollforward._ir import IR
from gaspatchio.rollforward._ops import Charge, Floor, Grow
from gaspatchio.schedule import Schedule


class TestSpecFingerprint:
    def test_format(self, single_state_ir: IR) -> None:
        fp = spec_fingerprint(single_state_ir)
        assert fp.startswith("sha256:")
        assert len(fp) == len("sha256:") + 64

    def test_stable_across_calls(self, single_state_ir: IR) -> None:
        a = spec_fingerprint(single_state_ir)
        b = spec_fingerprint(single_state_ir)
        assert a == b

    def test_insensitive_to_a_schedule_change(self, single_state_ir: IR) -> None:
        """The fingerprint is the machine; the schedule it runs on is data.

        Another cadence, another start, and an axis of fixed steps with no
        calendar under it all leave it where it was.
        """
        for schedule in (
            Schedule.from_calendar_grid(
                start_date=date(2025, 1, 31), n_periods=12, frequency="3M"
            ),
            Schedule.from_calendar_grid(
                start_date=date(2025, 4, 30), n_periods=24, frequency="1M"
            ),
            Schedule.fixed_step(n_periods=12, step_years=0.1),
        ):
            moved = replace(single_state_ir, schedule=schedule)
            assert spec_fingerprint(moved) == spec_fingerprint(single_state_ir)

    def test_sensitive_to_an_operation_an_operand_and_a_rounding(
        self, single_state_ir: IR
    ) -> None:
        """Every edit to what the machine computes moves it."""
        add, grow, floor = single_state_ir.transitions
        target = grow.target
        for transitions in (
            # an operation: the growth becomes a charge at the same rate
            (
                add,
                Charge(target=target, rate=pl.col("interest"), label="Interest"),
                floor,
            ),
            # an operand: the growth reads another column
            (add, Grow(target=target, rate=pl.col("bonus"), label="Interest"), floor),
            # a rounding: the growth is struck to the cent
            (
                add,
                Grow(
                    target=target,
                    rate=pl.col("interest"),
                    label="Interest",
                    round_charge=2,
                ),
                floor,
            ),
            # a floor at another value
            (add, grow, Floor(target=target, value=1.0)),
        ):
            moved = replace(single_state_ir, transitions=transitions)
            assert spec_fingerprint(moved) != spec_fingerprint(single_state_ir)

    def test_sensitive_to_track_increments_flag(self, single_state_ir: IR) -> None:
        ir_tracked = IR(
            states=single_state_ir.states,
            points=single_state_ir.points,
            transitions=single_state_ir.transitions,
            schedule=single_state_ir.schedule,
            batch_axes=single_state_ir.batch_axes,
            track_increments=True,
            lapse_when_all_non_positive=single_state_ir.lapse_when_all_non_positive,
            contract_boundary=single_state_ir.contract_boundary,
        )
        assert spec_fingerprint(single_state_ir) != spec_fingerprint(ir_tracked)
