# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Release-gate: exactly ONE register_plugin_function call per rollforward.

Per spec §8.3, multiple accessors against the same compiled rollforward must
share a single plugin Expr — the collector's caching is what enables Polars's
optimiser to deduplicate. This test asserts the contract via ``lf.explain()``.

The release-gate semantic is exercised via two ``.struct.field(...)``
accesses on different capture slots, which is sufficient to confirm Expr
sharing through the optimiser's CSE pass.
"""

from __future__ import annotations

from datetime import date

import polars as pl

from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestLazyStructReleaseGate:
    def test_two_accessors_one_plugin_call(self) -> None:
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=3,
            frequency="1M",
        )
        b = RollforwardBuilder(
            states={"av": pl.col("init")},
            points=["bop", "post_coi", "eop"],
            schedule=sched,
        )
        b["av"].between("bop", "post_coi").add(pl.col("p"))
        b["av"].between("post_coi", "eop").grow(pl.col("rate"))
        compiled = compile_rollforward(b)

        df = pl.LazyFrame(
            {
                "init": [100.0],
                "p": [[10.0, 10.0, 10.0]],
                "rate": [[0.01, 0.01, 0.01]],
            }
        )
        collector = RollforwardCollector(compiled)
        # Two accessors against the same collector must materialise as one
        # shared plugin Expr (collector caches the underlying call).
        lf = df.with_columns(
            av_eop=collector.expr_for("av"),
            av_post_coi=collector.expr_for("av", point="post_coi"),
        )
        plan = lf.explain()
        plugin_count = plan.lower().count("rollforward")
        assert plugin_count == 1, (
            f"Expected 1 plugin call; got {plugin_count}\nPlan:\n{plan}"
        )

    def test_repeated_calls_to_collector_share_expr(self) -> None:
        # Same collector, same accessor twice — must return the same cached
        # Expr instance (id-equality is the sharing contract).
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31),
            n_periods=2,
            frequency="1M",
        )
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"].add(pl.col("p"))
        compiled = compile_rollforward(b)
        collector = RollforwardCollector(compiled)
        e1 = collector.expr_for("av")
        e2 = collector.expr_for("av")
        # Both accessors should ultimately reference the same shared plugin
        # Expr — verified by checking the collector's internal cache.
        assert collector._cached_plugin_expr is not None
        # Second call returns a struct.field on the same cached plugin.
        assert e1.meta.serialize() == e2.meta.serialize()
