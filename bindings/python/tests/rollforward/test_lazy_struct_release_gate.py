# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Release-gate: exactly ONE rollforward kernel call per compiled rollforward.

Per spec §8.3, multiple extractions from the same compiled rollforward must
share a single kernel call. Polars 1.42 stopped deduplicating plugin calls in
its CSE pass, so the guarantee is now structural: ``CompiledRollforward
.expr_for`` references one hidden struct column that ``ActuarialFrame``
materialises on first use, and every extraction reads fields from it. These
tests assert the contract via ``explain()`` on the REAL usage pattern —
stacked worksheet-style assignments — which the old CSE-based design never
actually covered (each ``af.x = ...`` is its own ``with_columns``; CSE only
ever folded within one).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._compiled import CompiledRollforward


def _compile_two_point_av() -> CompiledRollforward:
    """One state, two capture points — the minimal multi-extraction model."""
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
    return compile_rollforward(b)


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame(
            {
                "init": [100.0],
                "p": [[10.0, 10.0, 10.0]],
                "rate": [[0.01, 0.01, 0.01]],
            }
        )
    )


EXPECTED_EOP = [111.1, 122.31099999999999, 133.63411]
EXPECTED_POST_COI = [110.0, 121.1, 132.31099999999998]


class TestOneKernelCallByConstruction:
    def test_stacked_assignments_share_one_kernel_call(self) -> None:
        """The release gate: worksheet-style stacked assignments, ONE kernel call."""
        compiled = _compile_two_point_av()
        af = _frame()
        # Two SEPARATE assignments — two with_columns nodes. The old CSE-based
        # design ran the kernel twice here on every polars version.
        af.av_eop = compiled.expr_for("av")
        af.av_post_coi = compiled.expr_for("av", point="post_coi")

        plan = af._df.explain()
        plugin_count = plan.lower().count("rollforward([")
        assert plugin_count == 1, (
            f"Expected 1 plugin call; got {plugin_count}\nPlan:\n{plan}"
        )

        out = af.collect()
        assert out["av_eop"].to_list()[0] == EXPECTED_EOP
        assert out["av_post_coi"].to_list()[0] == EXPECTED_POST_COI
        # The shared struct is plumbing, not output.
        assert not [c for c in out.columns if c.startswith("__rollforward_")]

    def test_composed_expression_materialises_and_shares(self) -> None:
        """expr_for composes like any Expr; the hidden source still materialises."""
        compiled = _compile_two_point_av()
        af = _frame()
        af.av_eop = compiled.expr_for("av")
        # Composition inside another expression — list concat, as level-3 does.
        af.padded = pl.concat_list(
            [
                pl.lit([1.0], dtype=pl.List(pl.Float64)),
                compiled.expr_for("av", point="post_coi"),
            ]
        )

        plan = af._df.explain()
        assert plan.lower().count("rollforward([") == 1

        out = af.collect()
        assert out["padded"].to_list()[0] == [1.0, *EXPECTED_POST_COI]

    def test_two_frames_each_materialise_their_own(self) -> None:
        """One compiled rollforward used on two frames: one kernel call in each."""
        compiled = _compile_two_point_av()
        af1, af2 = _frame(), _frame()
        af1.av_eop = compiled.expr_for("av")
        af2.av_eop = compiled.expr_for("av")
        af2.av_post_coi = compiled.expr_for("av", point="post_coi")

        assert af1._df.explain().lower().count("rollforward([") == 1
        assert af2._df.explain().lower().count("rollforward([") == 1
        assert af1.collect()["av_eop"].to_list()[0] == EXPECTED_EOP

    def test_raw_polars_escape_hatch(self) -> None:
        """Outside ActuarialFrame, plugin_expr() + manual alias gives one call."""
        compiled = _compile_two_point_av()
        df = pl.LazyFrame(
            {
                "init": [100.0],
                "p": [[10.0, 10.0, 10.0]],
                "rate": [[0.01, 0.01, 0.01]],
            }
        )
        lf = (
            df.with_columns(compiled.plugin_expr().alias("rf"))
            .with_columns(
                av_eop=pl.col("rf").struct.field("av@eop"),
                av_post_coi=pl.col("rf").struct.field("av@post_coi"),
            )
            .drop("rf")
        )
        assert lf.explain().lower().count("rollforward([") == 1
        out = lf.collect()
        assert out["av_eop"].to_list()[0] == EXPECTED_EOP
        assert out["av_post_coi"].to_list()[0] == EXPECTED_POST_COI


class TestDeprecatedCollectorShim:
    def test_collector_keeps_self_contained_semantics(self) -> None:
        """The shim still works everywhere a plain Expr does (raw Polars frames)."""
        compiled = _compile_two_point_av()
        collector = RollforwardCollector(compiled)
        df = pl.DataFrame(
            {
                "init": [100.0],
                "p": [[10.0, 10.0, 10.0]],
                "rate": [[0.01, 0.01, 0.01]],
            }
        )
        out = df.with_columns(av=collector.expr_for("av"))
        assert out["av"].to_list()[0] == EXPECTED_EOP

    def test_repeated_calls_to_collector_share_expr(self) -> None:
        """Same collector, same accessor twice — same serialized expression."""
        compiled = _compile_two_point_av()
        collector = RollforwardCollector(compiled)
        e1 = collector.expr_for("av")
        e2 = collector.expr_for("av")
        assert collector._cached_plugin_expr is not None
        assert e1.meta.serialize() == e2.meta.serialize()
