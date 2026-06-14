# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Jagged (per-policy variable-length) rollforward — each policy projects only
its own horizon. The rollforward recurrence value[t]=f(value[t-1], inputs[t])
has no cross-policy coupling, so the kernel derives each policy's period count
from its own input-list length; ``n_periods`` is a portfolio-max capacity hint.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.rollforward._builder import RollforwardBuilder
from gaspatchio_core.rollforward._collector import RollforwardCollector
from gaspatchio_core.rollforward._compile import compile_rollforward
from gaspatchio_core.schedule import Schedule


class TestJaggedRollforward:
    """The kernel + lowering compute correct per-policy results on jagged input."""

    def test_jagged_input_lists_project_own_horizon(self) -> None:
        # n_periods is the portfolio max (3); the two policies carry premium
        # lists of DIFFERENT lengths (2 and 3). Each must project only its own.
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=3, frequency="1M"
        )
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"].add(pl.col("premium"))
        compiled = compile_rollforward(b)

        df = pl.DataFrame(
            {"init": [100.0, 100.0], "premium": [[10.0, 20.0], [10.0, 20.0, 30.0]]}
        )
        av = (
            df.with_columns(av=RollforwardCollector(compiled).expr_for("av"))
            .get_column("av")
            .to_list()
        )
        # Policy A: 2 periods, 100 -> 110 -> 130 (no padded dead tail).
        assert len(av[0]) == 2
        assert av[0] == pytest.approx([110.0, 130.0])
        # Policy B: 3 periods, 100 -> 110 -> 130 -> 160.
        assert len(av[1]) == 3
        assert av[1] == pytest.approx([110.0, 130.0, 160.0])

    def test_uniform_unchanged(self) -> None:
        # Regression: equal-length policies still produce the identical answer.
        sched = Schedule.from_calendar_grid(
            start_date=date(2025, 1, 31), n_periods=3, frequency="1M"
        )
        b = RollforwardBuilder(states={"av": pl.col("init")}, schedule=sched)
        b["av"].add(pl.col("premium"))
        compiled = compile_rollforward(b)

        df = pl.DataFrame(
            {"init": [100.0, 100.0], "premium": [[10.0, 20.0, 30.0], [10.0, 20.0, 30.0]]}
        )
        av = (
            df.with_columns(av=RollforwardCollector(compiled).expr_for("av"))
            .get_column("av")
            .to_list()
        )
        assert av[0] == pytest.approx([110.0, 130.0, 160.0])
        assert av[1] == pytest.approx([110.0, 130.0, 160.0])


class TestPerPolicyProjectionRollforward:
    """The full af.projection.set(per_policy=True) -> rollforward() path works.

    Previously this raised ValueError ('rollforward() requires a uniform
    schedule'); the kernel now handles jagged timelines so the guard is gone.
    """

    def test_per_policy_frame_rollforward_projects_own_horizon(self) -> None:
        af = ActuarialFrame({"init": [100.0, 100.0], "term_months": [2, 3]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 31),
            until="term_months",
            until_value="term_months",
            frequency="monthly",
            per_policy=True,
        )
        # Constant premium of each policy's own period length (boundaries - 1).
        af.premium = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(10.0)
        )

        b = af.projection.rollforward(states={"av": af["init"]})
        b["av"].add(af["premium"])
        compiled = compile_rollforward(b)
        af.av = RollforwardCollector(compiled).expr_for("av")
        av = af.collect().get_column("av").to_list()

        # Policy A (term 2): 100 -> 110 -> 120, two periods only.
        assert av[0] == pytest.approx([110.0, 120.0])
        # Policy B (term 3): 100 -> 110 -> 120 -> 130, three periods.
        assert av[1] == pytest.approx([110.0, 120.0, 130.0])

    def test_per_policy_rollforward_does_not_raise(self) -> None:
        af = ActuarialFrame({"init": [100.0], "term_months": [4]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 31),
            until="term_months",
            until_value="term_months",
            frequency="monthly",
            per_policy=True,
        )
        # Must not raise the old "requires a uniform schedule" ValueError.
        builder = af.projection.rollforward(states={"av": af["init"]})
        assert builder is not None

    def test_zero_term_policy_emits_empty_list(self) -> None:
        """A matured / zero-term policy must produce an empty list, not panic."""
        af = ActuarialFrame({"init": [100.0, 100.0], "term_months": [0, 3]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 31),
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        af.premium = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(10.0)
        )
        b = af.projection.rollforward(states={"av": af["init"]})
        b["av"].add(af["premium"])
        af.av = RollforwardCollector(compile_rollforward(b)).expr_for("av")
        av = af.collect().get_column("av").to_list()
        assert av[0] == []  # zero-term policy: empty projection
        assert av[1] == pytest.approx([110.0, 120.0, 130.0])

    def test_no_input_rollforward_uses_per_policy_horizon(self) -> None:
        """A rollforward with no per-period input list still projects each
        policy's own horizon (the kernel reads the schedule-supplied length),
        not the portfolio maximum."""
        af = ActuarialFrame({"init": [100.0, 100.0], "term_months": [2, 4]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 31),
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        b = af.projection.rollforward(states={"av": af["init"]})
        b["av"].floor(value=50.0)  # no input list column referenced
        af.av = RollforwardCollector(compile_rollforward(b)).expr_for("av")
        lengths = [len(x) for x in af.collect().get_column("av").to_list()]
        assert lengths == [2, 4]  # per-policy, not the portfolio-max 4

    def test_null_term_rollforward_emits_empty(self) -> None:
        """A null term_months policy projects an empty list end-to-end — the
        num_proj_months feeder must stamp 0 (not null), else the kernel rejects
        the resulting null input list."""
        af = ActuarialFrame({"init": [100.0, 100.0], "term_months": [None, 3]})
        af = af.projection.set(
            valuation_date=date(2025, 1, 31),
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        af.premium = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(10.0)
        )
        b = af.projection.rollforward(states={"av": af["init"]})
        b["av"].add(af["premium"])
        af.av = RollforwardCollector(compile_rollforward(b)).expr_for("av")
        av = af.collect().get_column("av").to_list()
        assert av[0] == []  # null term -> empty projection, no crash
        assert av[1] == pytest.approx([110.0, 120.0, 130.0])

    def test_multistate_jagged_rollforward(self) -> None:
        """Two states with different ops project correct variable-length output
        per policy — exercises the per-row stride across multiple states."""
        af = ActuarialFrame(
            {"av0": [100.0, 100.0], "res0": [50.0, 50.0], "term_months": [2, 3]}
        )
        af = af.projection.set(
            valuation_date=date(2025, 1, 31),
            until="term_months",
            until_value="term_months",
            frequency="monthly",
        )
        af.prem = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(10.0)
        )
        af.draw = pl.int_ranges(0, pl.col("num_proj_months") - 1).list.eval(
            pl.lit(5.0)
        )
        b = af.projection.rollforward(states={"av": af["av0"], "res": af["res0"]})
        b["av"].add(af["prem"])
        b["res"].subtract(af["draw"])
        coll = RollforwardCollector(compile_rollforward(b))
        af.av = coll.expr_for("av")
        af.res = coll.expr_for("res")
        d = af.collect()
        av, res = d["av"].to_list(), d["res"].to_list()
        assert av[0] == pytest.approx([110.0, 120.0])  # +10/period
        assert av[1] == pytest.approx([110.0, 120.0, 130.0])
        assert res[0] == pytest.approx([45.0, 40.0])  # -5/period
        assert res[1] == pytest.approx([45.0, 40.0, 35.0])
