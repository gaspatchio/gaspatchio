# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end contract_boundary — first-True period is the stop boundary.

When the closed-subset boolean mask Expr evaluates True at period t, this
period and every later period are zeroed across each (state, point) cell.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestContractBoundary:
    def test_zeroes_from_first_true(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=4,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"reserve": pl.col("init")},
            schedule=sched,
            contract_boundary=pl.col("breach"),
        )
        b["reserve"].add(pl.col("flow"))
        compiled = compile_rollforward(b)

        # breach mask True at periods 2 and 3 — boundary fires at period 2
        # so periods 2 and 3 are zeroed.
        df = pl.DataFrame(
            {
                "init": [100.0],
                "flow": [[10.0, 10.0, 10.0, 10.0]],
                "breach": [[False, False, True, True]],
            }
        )
        collector = RollforwardCollector(compiled)
        rsv = (
            df.with_columns(reserve=collector.expr_for("reserve"))
            .get_column("reserve")
            .to_list()[0]
        )
        assert rsv[0] == pytest.approx(110.0, rel=1e-9)
        assert rsv[1] == pytest.approx(120.0, rel=1e-9)
        assert rsv[2] == 0.0
        assert rsv[3] == 0.0

    def test_no_boundary_when_mask_stays_false(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"reserve": pl.col("init")},
            schedule=sched,
            contract_boundary=pl.col("breach"),
        )
        b["reserve"].add(pl.col("flow"))
        compiled = compile_rollforward(b)

        df = pl.DataFrame(
            {
                "init": [100.0],
                "flow": [[10.0, 10.0, 10.0]],
                "breach": [[False, False, False]],
            }
        )
        collector = RollforwardCollector(compiled)
        rsv = (
            df.with_columns(reserve=collector.expr_for("reserve"))
            .get_column("reserve")
            .to_list()[0]
        )
        assert rsv == pytest.approx([110.0, 120.0, 130.0], rel=1e-9)
