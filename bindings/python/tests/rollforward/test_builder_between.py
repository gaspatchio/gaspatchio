# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""`.between(p1, p2)` scope marker tests."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.schedule import Schedule


@pytest.fixture
def builder_with_points() -> RollforwardBuilder:
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


class TestBetween:
    def test_between_targets_subsequent_op_to_named_point(
        self,
        builder_with_points: RollforwardBuilder,
    ) -> None:
        builder_with_points["av"].between("bop", "post_coi").add(
            pl.col("premium"),
            label="Premium",
        )
        op = builder_with_points._transitions[0]
        assert op.target.point == "post_coi"

    def test_two_between_calls_apply_to_their_own_ops(
        self,
        builder_with_points: RollforwardBuilder,
    ) -> None:
        b = builder_with_points
        b["av"].between("bop", "post_coi").add(pl.col("a"), label="A")
        b["av"].between("post_coi", "eop").charge(pl.col("e"), label="E")

        assert b._transitions[0].target.point == "post_coi"
        assert b._transitions[1].target.point == "eop"

    def test_unknown_point_raises(
        self,
        builder_with_points: RollforwardBuilder,
    ) -> None:
        with pytest.raises(ValueError, match="unknown point 'mystery'"):
            builder_with_points["av"].between("bop", "mystery")

    def test_between_endpoint_preceding_startpoint_raises(
        self,
        builder_with_points: RollforwardBuilder,
    ) -> None:
        with pytest.raises(ValueError, match="must precede"):
            builder_with_points["av"].between("eop", "bop")
