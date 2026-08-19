# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""expr_for capture-slot errors name the real rule (gh#93).

A point declared in ``points=(...)`` is not a capture slot unless an Op
targets it. The old error said "declare the point" — advice that is a no-op
when the point is already declared. These tests pin the truthful messages.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.rollforward._compile import compile_rollforward
from gaspatchio.schedule import Schedule

if TYPE_CHECKING:
    from gaspatchio.rollforward._compiled import CompiledRollforward


def _compiled_with_untargeted_bop() -> CompiledRollforward:
    """One state, 'bop' declared but targeted by no Op."""
    sched = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
    )
    b = RollforwardBuilder(
        states={"av": pl.col("av_init")},
        points=["bop", "eop"],
        schedule=sched,
    )
    b["av"].add(pl.col("prem"), label="premium")
    return compile_rollforward(b)


class TestDeclaredButUntargetedPoint:
    def test_error_names_the_real_rule(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError, match="no Op targets it"):
            compiled.expr_for("av", point="bop")

    def test_error_does_not_advise_declaring_a_declared_point(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError) as excinfo:
            compiled.expr_for("av", point="bop")
        message = str(excinfo.value)
        assert "declare the point" not in message
        assert "'bop' is declared" in message

    def test_error_offers_the_opening_balance_next_move(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError, match="previous_period"):
            compiled.expr_for("av", point="bop")

    def test_error_lists_captured_points_for_the_state(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError, match="eop"):
            compiled.expr_for("av", point="bop")


class TestUndeclaredPoint:
    def test_error_says_point_is_not_declared(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError, match="not declared"):
            compiled.expr_for("av", point="post_coi")

    def test_error_lists_declared_points(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError, match="bop"):
            compiled.expr_for("av", point="post_coi")


class TestUnknownState:
    def test_error_names_the_known_states(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        with pytest.raises(KeyError, match="Unknown state"):
            compiled.expr_for("fund")

    def test_eop_still_resolves(self) -> None:
        compiled = _compiled_with_untargeted_bop()
        expr = compiled.expr_for("av")
        assert isinstance(expr, pl.Expr)
