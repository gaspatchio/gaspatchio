# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Schedule expression surfaces carry the gh#67 proxy interop.

Every ``*_expr`` method a model can combine with ``af`` columns returns a
``ProxyAwareExpr`` — the same either-operand-order contract as
``Table.lookup`` and ``CompiledRollforward.expr_for``.
"""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from gaspatchio import ActuarialFrame, Schedule
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr


def _jagged() -> Schedule:
    return Schedule.from_per_policy_grid(
        start_date=date(2025, 1, 31),
        n_periods=12,
        frequency="1M",
        until_kind="term_months",
        until_value_column="tm",
    )


def test_schedule_exprs_are_proxy_aware() -> None:
    """The per-policy expression surface returns wrapped expressions."""
    sched = _jagged()
    for method in (
        sched.per_policy_period_dates_expr,
        sched.per_policy_period_count_expr,
        sched.year_fractions_expr,
    ):
        expr = method()
        assert isinstance(expr, ProxyAwareExpr)
        assert isinstance(expr, pl.Expr)


def test_count_expr_cooperates_with_proxies_in_either_order() -> None:
    """``count_expr * af.col`` and ``af.col * count_expr`` agree."""
    sched = _jagged()
    af = ActuarialFrame(pl.DataFrame({"tm": [3, 2], "w": [2.0, 3.0]}))
    af.lhs = sched.per_policy_period_count_expr() * af.w
    af.rhs = af.w * sched.per_policy_period_count_expr()
    out = af.collect()
    assert out.get_column("lhs").to_list() == out.get_column("rhs").to_list()
    assert out.get_column("lhs").to_list() == [6.0, 6.0]


def test_wrapping_preserves_the_kind_guards() -> None:
    """The wrap must not swallow a method's schedule-kind refusal."""
    calendar_grid = Schedule.from_calendar_grid(
        start_date=date(2025, 1, 31),
        n_periods=3,
        frequency="1M",
    )
    with pytest.raises(ValueError, match="from_inception or per_policy_grid"):
        calendar_grid.year_fractions_expr()
