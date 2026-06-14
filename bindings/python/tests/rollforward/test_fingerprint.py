# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""spec_fingerprint stability and sensitivity."""

from __future__ import annotations

from datetime import date

from gaspatchio_core.rollforward._fingerprint import spec_fingerprint
from gaspatchio_core.rollforward._ir import IR
from gaspatchio_core.schedule import Schedule


class TestSpecFingerprint:
    def test_format(self, single_state_ir: IR) -> None:
        fp = spec_fingerprint(single_state_ir)
        assert fp.startswith("sha256:")
        assert len(fp) == len("sha256:") + 64

    def test_stable_across_calls(self, single_state_ir: IR) -> None:
        a = spec_fingerprint(single_state_ir)
        b = spec_fingerprint(single_state_ir)
        assert a == b

    def test_sensitive_to_schedule_change(self, single_state_ir: IR) -> None:
        # Build an otherwise-identical IR with a different Schedule frequency
        sched_q = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="3M",
        )
        ir_q = IR(
            states=single_state_ir.states,
            points=single_state_ir.points,
            transitions=single_state_ir.transitions,
            schedule=sched_q,
            batch_axes=single_state_ir.batch_axes,
            track_increments=single_state_ir.track_increments,
            lapse_when_all_non_positive=single_state_ir.lapse_when_all_non_positive,
            contract_boundary=single_state_ir.contract_boundary,
        )
        assert spec_fingerprint(single_state_ir) != spec_fingerprint(ir_q)

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
