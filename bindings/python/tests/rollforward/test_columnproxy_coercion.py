# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""ColumnProxy (``af['col']``) accepted across the rollforward builder API.

Background: rollforward Ops require bare ``pl.col(...)`` exprs internally,
but the user-facing builder coerces ``ColumnProxy`` / ``ExpressionProxy``
at the boundary so actuary-friendly ``af['premium']`` syntax works.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core import (
    ActuarialFrame,
    RollforwardCollector,
    Schedule,
    compile_rollforward,
)


def _make_frame() -> ActuarialFrame:
    af = ActuarialFrame(
        pl.DataFrame(
            {
                "av_init": [1_000.0, 5_000.0],
                "premium": [[100.0] * 12, [500.0] * 12],
                "coi_rate": [[0.001] * 12, [0.002] * 12],
                "sum_assured": [[50_000.0] * 12, [100_000.0] * 12],
                "admin_rate": [[0.01] * 12, [0.01] * 12],
                "interest_rate": [[0.004] * 12, [0.003] * 12],
            },
        ),
    )
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )
    return af.projection.set(schedule=sched)


def test_af_indexing_matches_pl_col() -> None:
    """``af['x']`` and ``pl.col('x')`` produce bit-identical output across the API."""
    af_proxy = _make_frame()
    b = af_proxy.projection.rollforward(states={"av": af_proxy["av_init"]})
    (
        b["av"]
        .add(af_proxy["premium"], label="Premium")
        .deduct_nar(
            af_proxy["coi_rate"],
            death_benefit=af_proxy["sum_assured"],
            label="COI",
        )
        .charge(af_proxy["admin_rate"], label="Admin")
        .grow(af_proxy["interest_rate"], label="Interest")
        .floor(value=0.0)
    )
    compiled = compile_rollforward(b)
    af_proxy.av = RollforwardCollector(compiled).expr_for("av")
    proxy_result = af_proxy.collect()

    af_col = _make_frame()
    b2 = af_col.projection.rollforward(states={"av": pl.col("av_init")})
    (
        b2["av"]
        .add(pl.col("premium"), label="Premium")
        .deduct_nar(
            pl.col("coi_rate"),
            death_benefit=pl.col("sum_assured"),
            label="COI",
        )
        .charge(pl.col("admin_rate"), label="Admin")
        .grow(pl.col("interest_rate"), label="Interest")
        .floor(value=0.0)
    )
    compiled2 = compile_rollforward(b2)
    af_col.av = RollforwardCollector(compiled2).expr_for("av")
    col_result = af_col.collect()

    assert proxy_result.equals(col_result)
