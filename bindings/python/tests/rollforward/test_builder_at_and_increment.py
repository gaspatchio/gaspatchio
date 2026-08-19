# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""rf['s'].at('p') typed reference + rf.increment(label) accessor."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._refs import StateRef
from gaspatchio.schedule import Schedule


@pytest.fixture
def b() -> RollforwardBuilder:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )
    return RollforwardBuilder(
        states={"av": pl.col("init")},
        points=["bop", "post_coi", "eop"],
        schedule=sched,
    )


class TestAt:
    def test_at_returns_state_ref(self, b: RollforwardBuilder) -> None:
        ref = b["av"].at("post_coi")
        assert isinstance(ref, StateRef)
        assert ref.state == "av"
        assert ref.point == "post_coi"

    def test_at_unknown_point_raises(self, b: RollforwardBuilder) -> None:
        with pytest.raises(ValueError, match="unknown point 'mystery'"):
            b["av"].at("mystery")


class TestIncrement:
    # ``increment()`` is unreachable until the kernel emits increment
    # fields: the builder refuses track_increments=True (gh#69), and
    # without the flag the gate below fires. The IncrementRef round-trip
    # tests return with the emission arc.

    def test_increment_gate_points_at_the_flag(
        self,
        b: RollforwardBuilder,
    ) -> None:
        with pytest.raises(ValueError, match="track_increments=True"):
            b.increment("Anything")
