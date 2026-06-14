# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Smoke test for the af.projection.rollforward accessor → builder."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


class TestProjectionAccessor:
    def test_returns_v2_builder(self) -> None:
        af = ActuarialFrame(pl.DataFrame({"av_init": [100.0]}))
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        af = af.projection.set(schedule=sched)
        rf = af.projection.rollforward(
            states={"av": pl.col("av_init")},
        )
        assert isinstance(rf, RollforwardBuilder)

    def test_accepts_all_v2_kwargs(self) -> None:
        af = ActuarialFrame(pl.DataFrame({"init": [100.0]}))
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        af = af.projection.set(schedule=sched)
        rf = af.projection.rollforward(
            states={"av": pl.col("init")},
            points=("bop", "after", "eop"),
            track_increments=True,
            lapse_when_all_non_positive=["av"],
            contract_boundary=pl.col("breach"),
            batch_axes=("policy",),
        )
        assert isinstance(rf, RollforwardBuilder)
