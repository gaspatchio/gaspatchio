# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end lapse_when_all_non_positive — periods after lapse are zeroed.

Tests the stop-condition: when every state named in
``lapse_when_all_non_positive`` has eop ≤ 0 at the end of a period, all
subsequent periods write zero across every state.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestLapseAllNonPositive:
    def test_zeroes_remaining_periods_after_lapse(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=5,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=sched,
            lapse_when_all_non_positive=["av"],
        )
        b["av"].subtract(pl.col("withdrawal"))
        compiled = compile_rollforward(b)

        # av starts at 100, withdraw 30 each period:
        # t=0: 100-30=70  (alive)
        # t=1: 70-30=40   (alive)
        # t=2: 40-30=10   (alive)
        # t=3: 10-30=-20  (lapse fires at end-of-period 3)
        # t=4: 0          (post-lapse zero)
        df = pl.DataFrame({"init": [100.0], "withdrawal": [[30.0] * 5]})
        collector = RollforwardCollector(compiled)
        av = df.with_columns(av=collector.expr_for("av")).get_column("av").to_list()[0]
        assert av[0] == pytest.approx(70.0, rel=1e-9)
        assert av[1] == pytest.approx(40.0, rel=1e-9)
        assert av[2] == pytest.approx(10.0, rel=1e-9)
        assert av[3] == pytest.approx(-20.0, rel=1e-9)
        assert av[4] == 0.0

    def test_no_lapse_when_state_stays_positive(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            schedule=sched,
            lapse_when_all_non_positive=["av"],
        )
        b["av"].add(pl.col("premium"))
        compiled = compile_rollforward(b)

        df = pl.DataFrame({"init": [100.0], "premium": [[10.0, 10.0, 10.0]]})
        collector = RollforwardCollector(compiled)
        av = df.with_columns(av=collector.expr_for("av")).get_column("av").to_list()[0]
        assert av == pytest.approx([110.0, 120.0, 130.0], rel=1e-9)
