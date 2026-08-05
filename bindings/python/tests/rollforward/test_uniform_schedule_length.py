# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""F12a: a uniform schedule means full-length inputs — checked per row.

A `from_calendar_grid` / `from_inception` schedule declares a uniform book:
every policy's input lists must have exactly ``n_periods`` elements, and any
row that disagrees is stale/short/over-long inputs — the projection would
silently run the wrong horizon, so it raises instead.

The check is per ROW by design. An earlier version fired only when EVERY
row in the batch shared one wrong length, inferring "jagged" from
within-batch variance — but batch boundaries are an engine choice
(streaming chunks), so identical books passed or failed depending on chunk
width (GSP-112 audit finding). Jagged horizons are now declared, not
inferred: use ``Schedule.from_per_policy_grid`` (or
``af.projection.set(..., per_policy=True)``), which supplies authoritative
per-row lengths.
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


def _per_policy_av_collector(n_periods: int) -> RollforwardCollector:
    sched = Schedule.from_per_policy_grid(
        start_date=date(2025, 1, 31),
        n_periods=n_periods,
        frequency="1M",
        until_kind="term_months",
        until_value_column="term",
    )
    b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
    b["av"].add(pl.col("premium"))
    return RollforwardCollector(compile_rollforward(b))


def test_uniform_book_inputs_all_mismatch_n_periods_raises() -> None:
    """Both policies length 2 under n_periods=3 -> raise on the first row."""
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame(
        {"init": [100.0, 100.0], "premium": [[10.0, 10.0], [10.0, 10.0]]},
    )
    with pytest.raises(pl.exceptions.ComputeError, match="n_periods"):
        df.with_columns(av=collector.expr_for("av"))


def test_uniform_book_mixed_lengths_raises() -> None:
    """Varying lengths on a UNIFORM schedule are equally stale inputs.

    The old variance heuristic waved this book through as "jagged"; under
    declared intent a uniform schedule rejects every short row.
    """
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame(
        {"init": [100.0, 100.0], "premium": [[10.0, 10.0], [10.0, 10.0, 10.0]]},
    )
    with pytest.raises(pl.exceptions.ComputeError, match="uniform"):
        df.with_columns(av=collector.expr_for("av"))


def test_uniform_book_single_short_row_raises() -> None:
    """One-row frame (the smallest possible streaming chunk) still raises.

    This is the chunk-stability property itself: the guard's verdict on a
    row cannot depend on which batchmates the engine happened to give it.
    """
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame({"init": [100.0], "premium": [[10.0, 10.0]]})
    with pytest.raises(pl.exceptions.ComputeError, match="uniform"):
        df.with_columns(av=collector.expr_for("av"))


def test_off_by_one_advice_names_the_point_indexed_trap() -> None:
    """Length n_periods + 1 is the axis-derived-input trap (gh#73).

    Every projection axis carries one value per period boundary, so a column
    built from one arrives one element long. The error must state the point-
    vs period-indexed rule and the ``.list.head(n)`` fix — the earlier advice
    ("build the inputs on the schedule's axis") described exactly what fails.
    """
    collector = _uniform_av_collector(n_periods=3)
    df = pl.DataFrame({"init": [100.0], "premium": [[10.0, 10.0, 10.0, 10.0]]})
    with pytest.raises(pl.exceptions.ComputeError) as exc_info:
        df.with_columns(av=collector.expr_for("av"))
    msg = str(exc_info.value)
    assert "point-indexed" in msg
    assert ".list.head(3)" in msg
    assert "build the inputs on the schedule's axis" not in msg


def test_jagged_via_per_policy_grid_allowed() -> None:
    """Declared jagged: per-policy grid supplies each policy's own horizon."""
    collector = _per_policy_av_collector(n_periods=3)
    df = pl.DataFrame(
        {
            "init": [100.0, 100.0],
            "term": [2, 3],
            "premium": [[10.0, 10.0], [10.0, 10.0, 10.0]],
        },
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
