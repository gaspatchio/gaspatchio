# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""compile_rollforward end-to-end orchestration."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.rollforward._compiled import CompiledRollforward
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def sched() -> Schedule:
    return Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )


class TestCompile:
    def test_returns_compiled_rollforward(self, sched: Schedule) -> None:
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"].add(pl.col("p"), label="P").floor(0.0)
        compiled = compile_rollforward(b)
        assert isinstance(compiled, CompiledRollforward)
        assert compiled.ir.states[0].name == "av"
        assert "ir" in compiled.plugin_kwargs

    def test_passes_run_in_declared_order(self, sched: Schedule) -> None:
        from loguru import logger

        captured: list[str] = []
        sink_id = logger.add(
            lambda msg: captured.append(msg.record["message"]),
            level="TRACE",
        )
        try:
            b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
            b["av"].floor(0.0)
            compile_rollforward(b)
        finally:
            logger.remove(sink_id)
        log_text = "\n".join(captured)
        for pass_name in (
            "validate",
            "resolve_state_refs",
            "fold_constants",
            "assign_capture_slots",
            "lower_polars",
        ):
            assert pass_name in log_text

    def test_validate_failure_short_circuits(self, sched: Schedule) -> None:
        from gaspatchio_core.rollforward._ir import IR, State
        from gaspatchio_core.rollforward._ops import Add
        from gaspatchio_core.rollforward._refs import StateRef

        ir = IR(
            states=(State(name="av", init=pl.col("init")),),
            points=("bop", "eop"),
            transitions=(
                Add(
                    target=StateRef(state="ghost", point="eop"),
                    expr=pl.col("x"),
                    label="X",
                ),
            ),
            schedule=sched,
            batch_axes=("policy",),
            track_increments=False,
            lapse_when_all_non_positive=(),
            contract_boundary=None,
        )
        with pytest.raises(ValueError, match="targets unknown state 'ghost'"):
            compile_rollforward(ir)
