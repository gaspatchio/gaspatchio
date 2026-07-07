# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""F12a: a uniform book fed inputs that all disagree with n_periods fails loud.

The rollforward kernel is intentionally input-length-driven (n_periods is a
portfolio-max capacity hint), which is how jagged/variable-horizon books work.
But when EVERY policy's inputs share one length that disagrees with n_periods,
that is a uniform book fed stale/short inputs — the projection would silently
truncate to the wrong horizon. That case now raises. Genuinely jagged books,
whose input lengths VARY across policies, are unaffected.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


def _uniform_av_collector(n_periods: int) -> RollforwardCollector:
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=n_periods,
        frequency="1M",
    )
    b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
    b["av"].add(pl.col("premium"))
    return RollforwardCollector(compile_rollforward(b))


def test_uniform_book_inputs_all_mismatch_n_periods_raises() -> None:
    """Both policies length 2 under n_periods=3 -> uniform mismatch -> raise."""
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame(
        {"init": [100.0, 100.0], "premium": [[10.0, 10.0], [10.0, 10.0]]},
    )
    with pytest.raises(pl.exceptions.ComputeError, match="n_periods"):
        df.with_columns(av=collector.expr_for("av"))


def test_jagged_varying_lengths_still_allowed() -> None:
    """Varying input lengths (2 and 3) -> genuine jagged -> each own horizon."""
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame(
        {"init": [100.0, 100.0], "premium": [[10.0, 10.0], [10.0, 10.0, 10.0]]},
    )
    av = df.with_columns(av=collector.expr_for("av")).get_column("av").to_list()
    assert len(av[0]) == 2
    assert len(av[1]) == 3


def test_uniform_matching_n_periods_ok() -> None:
    """Both policies length 3 == n_periods=3 -> uniform, correct result."""
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame(
        {
            "init": [100.0, 100.0],
            "premium": [[10.0, 10.0, 10.0], [10.0, 10.0, 10.0]],
        },
    )
    av = df.with_columns(av=collector.expr_for("av")).get_column("av").to_list()
    assert av[0] == pytest.approx([110.0, 120.0, 130.0])