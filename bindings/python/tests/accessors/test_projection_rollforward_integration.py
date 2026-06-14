# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for af.projection.rollforward() reading schedule from the frame."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame, RollforwardCollector, compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestRollforwardReadsFromFrame:
    def test_basic_single_state(self) -> None:
        af = ActuarialFrame(
            {
                "id": ["P1"],
                "av_init": [1000.0],
                "fund_return": [[0.01] * 12],
            }
        )
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        b = af.projection.rollforward(states={"av": pl.col("av_init")})
        b["av"].grow(pl.col("fund_return"))
        compiled = compile_rollforward(b)
        collector = RollforwardCollector(compiled)
        af.av = collector.expr_for("av")
        result = af.collect()
        assert "av" in result.columns


class TestRollforwardErrorPaths:
    def test_schedule_kwarg_raises_typeerror(self) -> None:
        af = ActuarialFrame({"id": ["P1"], "av_init": [1000.0]})
        af = af.projection.set(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="monthly",
        )
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        with pytest.raises(TypeError, match="schedule= is no longer accepted"):
            af.projection.rollforward(
                states={"av": pl.col("av_init")},
                schedule=sched,
            )

    def test_no_projection_raises_valueerror(self) -> None:
        af = ActuarialFrame({"id": ["P1"], "av_init": [1000.0]})
        with pytest.raises(ValueError, match="no projection"):
            af.projection.rollforward(states={"av": pl.col("av_init")})
