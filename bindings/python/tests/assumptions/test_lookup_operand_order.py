# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``lookup(...)`` works with proxies on either side of an operator.

``pl.Expr`` raises on a proxy operand instead of returning ``NotImplemented``,
so Python never offers the proxy its reflected method — ``lookup(...) * af.v``
raised while ``af.v * lookup(...)`` worked (gh#67). ``lookup()`` now returns a
``ProxyAwareExpr`` that hands a proxy operand the whole operation (the proxy
layer owns the list-column operator shims), and keeps interop through operator
chains. The shape matrix at the bottom is the tripwire for the two dispatch
routes ever disagreeing.
"""

from __future__ import annotations

import operator
from typing import TYPE_CHECKING

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr

if TYPE_CHECKING:
    from collections.abc import Callable


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


def test_result_type_contract() -> None:
    """Proxy operand -> ExpressionProxy (frame currency); plain -> pl.Expr."""
    table = _surrender_table("operand_order_types")
    af = _frame()
    with_proxy = table.lookup(policy_year=af["policy_year"]) * af.v
    plain = table.lookup(policy_year=af["policy_year"]) * 2.0
    assert isinstance(with_proxy, ExpressionProxy)
    assert isinstance(plain, ProxyAwareExpr)
    assert isinstance(plain, pl.Expr)


# --- operator x shape x operand-order matrix --------------------------------
#
# Every cell is checked against a pure-Python reference, so the two dispatch
# routes (ProxyAwareExpr delegating to the proxy layer vs the proxy's own
# operator) can never silently diverge — from each other or from the maths.

_MATRIX_RATES = {1: 0.9, 2: 0.8, 3: 0.7}

_MATRIX_OPS: dict[str, Callable[[object, object], object]] = {
    "add": operator.add,
    "sub": operator.sub,
    "mul": operator.mul,
    "truediv": operator.truediv,
    "pow": operator.pow,
}

_MATRIX_SHAPES: dict[str, dict[str, list[object]]] = {
    "scalar_x_scalar": {"y": [1, 2], "w": [2.0, 3.0]},
    "scalar_x_list": {"y": [1, 2], "w": [[2.0, 3.0], [4.0, 5.0]]},
    "list_x_list": {"y": [[1, 2], [2, 3]], "w": [[2.0, 3.0], [4.0, 5.0]]},
    "list_x_scalar": {"y": [[1, 2], [2, 3]], "w": [2.0, 3.0]},
}


def _rates_for(y: object) -> object:
    if isinstance(y, list):
        return [_MATRIX_RATES[k] for k in y]
    return _MATRIX_RATES[y]


def _elementwise(
    op: Callable[[object, object], object], a: object, b: object
) -> object:
    if isinstance(a, list) and isinstance(b, list):
        return [op(x, z) for x, z in zip(a, b, strict=True)]
    if isinstance(a, list):
        return [op(x, b) for x in a]
    if isinstance(b, list):
        return [op(a, z) for z in b]
    return op(a, b)


def _flatten(values: object) -> list[float]:
    if isinstance(values, list):
        return [x for v in values for x in _flatten(v)]
    return [float(values)]  # type: ignore[arg-type]


@pytest.mark.parametrize("direction", ["lookup_first", "proxy_first"])
@pytest.mark.parametrize("op_name", sorted(_MATRIX_OPS))
@pytest.mark.parametrize("shape_name", sorted(_MATRIX_SHAPES))
def test_operator_shape_matrix(
    shape_name: str,
    op_name: str,
    direction: str,
) -> None:
    """Both operand orders match the scalar-python reference in every shape.

    ``pow`` on list shapes is the cell that caught the earlier design: raw
    polars has no list ``pow``, only the proxy layer's shim does — so the
    wrapper must delegate to the proxy, not to polars.
    """
    op = _MATRIX_OPS[op_name]
    data = _MATRIX_SHAPES[shape_name]
    table = Table(
        name=f"matrix_{shape_name}_{op_name}_{direction}",
        source=pl.DataFrame({"y": [1, 2, 3], "rate": [0.9, 0.8, 0.7]}),
        dimensions={"y": "y"},
        value="rate",
    )
    af = ActuarialFrame(pl.DataFrame(data))
    lk = table.lookup(y=af["y"])
    af.result = op(lk, af.w) if direction == "lookup_first" else op(af.w, lk)
    got = af.collect().get_column("result").to_list()

    expected = []
    for y_row, w_row in zip(data["y"], data["w"], strict=True):
        r = _rates_for(y_row)
        args = (r, w_row) if direction == "lookup_first" else (w_row, r)
        expected.append(_elementwise(op, *args))

    assert _flatten(got) == pytest.approx(_flatten(expected))
