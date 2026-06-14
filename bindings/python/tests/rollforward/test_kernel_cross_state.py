# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Kernel-side cross-state read via ``pl.col("state@point")``.

End-to-end test: a Ratchet whose ``to`` argument is a state-ref of another
state at a specific point. The kernel resolves the ref against the live
per-row state vector — no precomputed input column required.

Reference shape: GMxB ratchet (Bauer/Kling/Russ 2008) — the GMDB rider
ratchets to the fund's high-water mark on each policy anniversary.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestCrossStateRatchet:
    def test_gmdb_ratchets_to_fund_eop(self) -> None:
        # 12-period schedule. Anniversary at t=11 (the last period). Fund
        # grows 1%/period from 100; GMDB starts at 100 and ratchets to fund@eop
        # only when the anniversary mask fires. So GMDB stays at 100 for
        # t=0..10, then ratchets at t=11 to fund's eop value (~112.68).
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=12,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={
                "fund": pl.col("init"),
                "gmdb": pl.col("init"),
            },
            schedule=sched,
        )
        # Fund: simple 1%/period growth
        b["fund"].grow(pl.col("rate"))
        # GMDB: ratchet to fund@eop on anniversary. The to= reference uses
        # the cross-state syntax — pl.col("fund@eop") resolves at runtime
        # to the kernel's state vector, not to a precomputed input.
        b["gmdb"].ratchet(
            to=pl.col("fund@eop"),
            when=pl.col("anniv"),
            label="GMDB",
        )
        compiled = compile_rollforward(b)

        # All 12 periods at 1% growth. Anniversary fires only at t=11.
        df = pl.DataFrame(
            {
                "init": [100.0],
                "rate": [[0.01] * 12],
                "anniv": [[False] * 11 + [True]],
            }
        )
        collector = RollforwardCollector(compiled)
        result = df.with_columns(
            fund=collector.expr_for("fund"),
            gmdb=collector.expr_for("gmdb"),
        )

        fund = result.get_column("fund").to_list()[0]
        gmdb = result.get_column("gmdb").to_list()[0]

        # Fund grows geometrically
        for t in range(12):
            assert fund[t] == pytest.approx(100.0 * (1.01 ** (t + 1)), rel=1e-12)

        # GMDB stays at 100 until anniversary, then ratchets to fund[11]
        for t in range(11):
            assert gmdb[t] == pytest.approx(100.0, rel=1e-12)
        assert gmdb[11] == pytest.approx(fund[11], rel=1e-12)

    def test_state_ref_does_not_register_as_input_column(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={
                "fund": pl.col("init"),
                "gmdb": pl.col("init"),
            },
            schedule=sched,
        )
        b["fund"].grow(pl.col("rate"))
        b["gmdb"].ratchet(to=pl.col("fund@eop"), when=pl.col("anniv"))
        compiled = compile_rollforward(b)

        # The kwargs sent to the Polars plugin should list ``rate`` and
        # ``anniv`` as input columns, but NOT ``fund@eop`` (that's a state
        # ref, not a frame column).
        assert compiled.plugin_kwargs["input_columns"] == ["rate", "anniv"]
