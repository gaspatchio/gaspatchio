# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``lookup(...)`` works with proxies on either side of an operator.

``pl.Expr`` raises on a proxy operand instead of returning ``NotImplemented``,
so Python never offers the proxy its reflected method — ``lookup(...) * af.v``
raised while ``af.v * lookup(...)`` worked (gh#67). ``lookup()`` now returns a
``ProxyAwareExpr`` that unwraps proxy operands itself, in every operator, and
keeps that property through operator chains.
"""

from __future__ import annotations

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.assumptions import Table
from gaspatchio_core.column.proxy_aware_expr import ProxyAwareExpr


def _surrender_table(name: str) -> Table:
    return Table(
        name=name,
        source=pl.DataFrame({"year": [1, 2, 3], "pct": [1.0, 0.9, 0.8]}),
        dimensions={"policy_year": "year"},
        value="pct",
    )


def _frame() -> ActuarialFrame:
    return ActuarialFrame(
        pl.DataFrame({"p": [1], "policy_year": [2], "v": [100.0], "w": [2.0]}),
    )


def test_lookup_times_column_proxy_matches_reflected_order() -> None:
    """The gh#67 repro: both operand orders work and agree."""
    table = _surrender_table("operand_order_mul")
    af = _frame()
    af.left = table.lookup(policy_year=af["policy_year"]) * af.v
    af.right = af.v * table.lookup(policy_year=af["policy_year"])
    out = af.collect()
    assert out.get_column("left").to_list() == [90.0]
    assert out.get_column("right").to_list() == [90.0]


def test_every_arithmetic_operator_accepts_a_proxy() -> None:
    """+, -, /, ** all unwrap a ColumnProxy operand."""
    table = _surrender_table("operand_order_ops")
    af = _frame()
    looked_up = table.lookup(policy_year=af["policy_year"])  # 0.9
    af.add = looked_up + af.v
    af.sub = looked_up - af.v
    af.div = looked_up / af.v
    af.pow = looked_up**af.w
    out = af.collect()
    assert out.get_column("add").to_list() == [100.9]
    assert out.get_column("sub").to_list() == [-99.1]
    assert out.get_column("div").to_list() == pytest.approx([0.009])
    assert out.get_column("pow").to_list() == [0.81]


def test_property_survives_an_operator_chain() -> None:
    """`lookup * proxy * proxy` — the first result must stay proxy-aware."""
    table = _surrender_table("operand_order_chain")
    af = _frame()
    af.chained = table.lookup(policy_year=af["policy_year"]) * af.v * af.w
    out = af.collect()
    assert out.get_column("chained").to_list() == [180.0]


def test_comparison_with_a_proxy() -> None:
    """Comparisons unwrap proxies too — they feed when/then conditions."""
    table = _surrender_table("operand_order_cmp")
    af = _frame()
    af.cheap = table.lookup(policy_year=af["policy_year"]) < af.w
    out = af.collect()
    assert out.get_column("cheap").to_list() == [True]


def test_expression_proxy_operand() -> None:
    """An ExpressionProxy (result of proxy arithmetic) unwraps the same way."""
    table = _surrender_table("operand_order_exprproxy")
    af = _frame()
    af.scaled = table.lookup(policy_year=af["policy_year"]) * (af.v * af.w)
    out = af.collect()
    assert out.get_column("scaled").to_list() == [180.0]


def test_lookup_is_still_a_polars_expr() -> None:
    """No new type for callers to know about — isinstance(pl.Expr) holds."""
    table = _surrender_table("operand_order_isinstance")
    expr = table.lookup(policy_year=pl.col("policy_year"))
    assert isinstance(expr, pl.Expr)
    assert isinstance(expr, ProxyAwareExpr)
    result = pl.DataFrame({"policy_year": [3]}).with_columns(rate=expr.alias("rate"))
    assert result.get_column("rate").to_list() == [0.8]
