# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""rf['s'].at('p') typed reference + rf.increment(label) accessor."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._refs import StateRef
from gaspatchio_core.schedule import Schedule


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
        track_increments=True,
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
    def test_increment_records_label_request(self, b: RollforwardBuilder) -> None:
        b["av"].add(pl.col("p"), label="Premium")
        ref = b.increment("Premium")
        # Returns an opaque IncrementRef that the compiler resolves to a Struct field
        assert ref.label == "Premium"

    def test_increment_unknown_label_raises_at_lookup_time(
        self,
        b: RollforwardBuilder,
    ) -> None:
        # ``increment(label)`` construction is permissive — the compiler
        # validates that the label was emitted by some op. At builder time
        # this is a deferred check.
        ref = b.increment("DoesNotExist")
        assert ref.label == "DoesNotExist"

    def test_increment_requires_track_increments_flag(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        b_no_track = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=sched,
            track_increments=False,
        )
        with pytest.raises(ValueError, match="track_increments=True"):
            b_no_track.increment("Anything")
