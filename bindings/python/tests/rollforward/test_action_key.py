# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""action_key — 5-component closure with typed-input SHA gathering."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward._action_key import (
    HermeticContext,
    action_key,
    gather_typed_input_shas,
)
from gaspatchio_core.rollforward._ir import IR, State
from gaspatchio_core.rollforward._ops import Floor
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


class TestActionKeyFormat:
    def test_returns_sha256_hex(self, single_state_ir: IR) -> None:
        ak = action_key(
            single_state_ir,
            input_data_sha="sha256:" + "a" * 64,
            gaspatchio_version="0.4.0",
            git_sha="b" * 40,
        )
        assert ak.startswith("sha256:")
        assert len(ak) == len("sha256:") + 64


class TestActionKeySensitivity:
    def test_changes_when_spec_fingerprint_changes(self, single_state_ir: IR) -> None:
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
        kw = {"input_data_sha": "x", "gaspatchio_version": "0.4.0", "git_sha": "g"}
        assert action_key(single_state_ir, **kw) != action_key(ir_tracked, **kw)

    def test_changes_when_input_data_sha_changes(self, single_state_ir: IR) -> None:
        kw = {"gaspatchio_version": "0.4.0", "git_sha": "g"}
        a = action_key(single_state_ir, input_data_sha="A", **kw)
        b = action_key(single_state_ir, input_data_sha="B", **kw)
        assert a != b

    def test_changes_when_version_changes(self, single_state_ir: IR) -> None:
        kw = {"input_data_sha": "x", "git_sha": "g"}
        a = action_key(single_state_ir, gaspatchio_version="0.4.0", **kw)
        b = action_key(single_state_ir, gaspatchio_version="0.4.1", **kw)
        assert a != b

    def test_changes_when_git_sha_changes(self, single_state_ir: IR) -> None:
        kw = {"input_data_sha": "x", "gaspatchio_version": "0.4.0"}
        a = action_key(single_state_ir, git_sha="aaaa", **kw)
        b = action_key(single_state_ir, git_sha="bbbb", **kw)
        assert a != b


class TestTypedInputShaGathering:
    def test_gathers_schedule_sha(self, single_state_ir: IR) -> None:
        shas = gather_typed_input_shas(single_state_ir)
        sched_sha = single_state_ir.schedule.source_sha()
        assert sched_sha in shas

    def test_two_runs_with_different_schedule_have_different_action_keys(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        sched_b = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="3M",
        )
        ir_a = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(Floor(target=StateRef(state="av", point="eop"), value=0.0),),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        ir_b = IR(
            states=ir_a.states,
            points=ir_a.points,
            transitions=ir_a.transitions,
            schedule=sched_b,
            batch_axes=ir_a.batch_axes,
            track_increments=ir_a.track_increments,
            lapse_when_all_non_positive=ir_a.lapse_when_all_non_positive,
            contract_boundary=ir_a.contract_boundary,
        )
        kw = {"input_data_sha": "x", "gaspatchio_version": "0.4.0", "git_sha": "g"}
        assert action_key(ir_a, **kw) != action_key(ir_b, **kw)


class TestHermeticContext:
    def test_stub_constructible(self) -> None:
        ctx = HermeticContext(
            engine_id="polars_backend",
            engine_version="0.4.0",
            kernel_artifact_sha256="x" * 64,
            polars_version="1.38.1",
            rust_target_triple="aarch64-apple-darwin",
            fp_mode="ieee-strict",
            lc_numeric="C",
        )
        assert ctx.engine_id == "polars_backend"

    def test_action_key_accepts_context_no_op(self, single_state_ir: IR) -> None:
        ctx = HermeticContext(
            engine_id="polars_backend",
            engine_version="0.4.0",
            kernel_artifact_sha256="x" * 64,
            polars_version="1.38.1",
            rust_target_triple="aarch64-apple-darwin",
            fp_mode="ieee-strict",
            lc_numeric="C",
        )
        # context is *accepted* but currently a documented no-op — see
        # HermeticContext docstring for the forward-compat envelope it
        # describes.
        kw = {"input_data_sha": "x", "gaspatchio_version": "0.4.0", "git_sha": "g"}
        a = action_key(single_state_ir, **kw)
        b = action_key(single_state_ir, context=ctx, **kw)
        assert a == b  # context is a no-op
