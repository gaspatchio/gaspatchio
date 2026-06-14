# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end smoke — §4.6 UL example builds + compiles + explains."""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.rollforward._explain import explain
from gaspatchio_core.schedule import Schedule


class TestUlSmoke:
    def test_ul_with_post_coi_capture_compiles(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=240,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            points=["bop", "post_coi", "eop"],
            schedule=sched,
            track_increments=True,
        )

        b["av"].between("bop", "post_coi").add(
            pl.col("premium"),
            label="Premium",
        ).deduct_nar(
            pl.col("coi_rate"),
            death_benefit=pl.col("sum_assured"),
            label="COI",
        )

        b["av"].between("post_coi", "eop").charge(
            pl.col("admin_rate"),
            label="Admin",
        ).grow(
            pl.col("interest_rate"),
            label="Interest credit",
        ).floor(0.0)

        compiled = compile_rollforward(b)
        # 5 ops total (Add, DeductNAR, Charge, Grow, Floor)
        assert len(compiled.ir.transitions) == 5

        # Explain output is non-empty + names every label
        out = explain(compiled.ir)
        for label in ("Premium", "COI", "Admin", "Interest credit"):
            assert label in out

    def test_post_coi_capture_in_slots(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=240,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("av_init")},
            points=["bop", "post_coi", "eop"],
            schedule=sched,
        )
        b["av"].between("bop", "post_coi").add(pl.col("premium"), label="P")
        b["av"].between("post_coi", "eop").grow(pl.col("rate"), label="G")

        compiled = compile_rollforward(b)
        # post_coi appears as an Op target -> capture slot
        slot_points = {s.point for s in compiled.capture_slots}
        assert "post_coi" in slot_points
        assert "eop" in slot_points
