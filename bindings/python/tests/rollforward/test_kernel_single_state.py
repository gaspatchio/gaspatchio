# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end §4.4 Whole Life single-state path."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestWholeLifeSingleState:
    def test_av_grows_then_floors(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"].add(pl.col("premium"), label="P").grow(
            pl.col("rate"),
            label="G",
        ).floor(0.0)
        compiled = compile_rollforward(b)

        df = pl.DataFrame(
            {
                "init": [100.0],
                "premium": [[10.0, 10.0, 10.0]],
                "rate": [[0.0, 0.0, 0.0]],
            },
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(av=collector.expr_for("av"))
        av = result.get_column("av").to_list()[0]
        # period 0: 100 + 10 = 110, * (1+0) = 110, max(110,0) = 110
        # period 1: 110 + 10 = 120, * (1+0) = 120, max(120,0) = 120
        # period 2: 120 + 10 = 130, * (1+0) = 130, max(130,0) = 130
        assert av == pytest.approx([110.0, 120.0, 130.0])
