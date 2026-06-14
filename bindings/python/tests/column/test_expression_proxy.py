# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import polars as pl
import pytest

from gaspatchio_core.column import ColumnProxy, ExpressionProxy
from gaspatchio_core.column.condition_expression import ConditionExpression


# Mock ActuarialFrame specific to ExpressionProxy tests
class MockActuarialFrameForExpr:
    def __init__(self):
        self._convert_to_expr_mock = MagicMock()
        # Mock a _df with a simple schema for dispatch logic
        mock_df = pl.LazyFrame({"some_col": [1, 2, 3], "test_col": [1, 2, 3]})
        self._df = mock_df
        self._tracing = False  # Add _tracing attribute required by ErrorEnhancer

    def _convert_to_expr(self, value):
        if isinstance(value, ExpressionProxy):
            return value._expr
        if isinstance(value, ColumnProxy):
            return pl.col(value.name)
        self._convert_to_expr_mock(value)
        return pl.lit(value)


@pytest.fixture
def mock_parent_expr():
    return MockActuarialFrameForExpr()


@pytest.fixture
def expr_proxy(mock_parent_expr):
    # Base expression for tests
    return ExpressionProxy(pl.lit(10).alias("base_expr"), mock_parent_expr)


@pytest.fixture
def col_expr_proxy(mock_parent_expr):
    # Proxy based on a column
    return ExpressionProxy(pl.col("some_col").alias("col_expr"), mock_parent_expr)


# --- ExpressionProxy Basic Tests ---


def test_expression_proxy_init(expr_proxy):
    assert isinstance(expr_proxy._expr, pl.Expr)
    assert isinstance(expr_proxy._parent, MockActuarialFrameForExpr)
    assert expr_proxy._expr.meta.output_name() == "base_expr"


def test_expression_proxy_repr(expr_proxy):
    repr_str = repr(expr_proxy)
    assert repr_str.startswith("ExpressionProxy(expr=")
    # Check if the expression repr is included (might be complex)
    assert "base_expr" in repr_str or "dyn int: 10" in repr_str


def test_expression_proxy_to_expr(expr_proxy):
    assert isinstance(expr_proxy._to_expr(), pl.Expr)
    assert str(expr_proxy._to_expr()) == 'dyn int: 10.alias("base_expr")'


# --- ExpressionProxy Operator Tests ---
# These tests combine the proxy with various other types


@pytest.mark.parametrize(
    "op, op_symbol",
    [
        (lambda a, b: a + b, "+"),
        (lambda a, b: a - b, "-"),
        (lambda a, b: a * b, "*"),
        (lambda a, b: a / b, "/"),
        (lambda a, b: a // b, "//"),
        (lambda a, b: a % b, "%"),
    ],
)
def test_expression_proxy_binary_operators(expr_proxy, col_expr_proxy, op, op_symbol):
    # Test op with literal
    result_lit = op(expr_proxy, 5)
    assert isinstance(result_lit, ExpressionProxy)
    assert (
        str(result_lit._expr)
        == f'[(dyn int: 10.alias("base_expr")) {op_symbol} (dyn int: 5)]'
    )

    # Test op with another expression proxy
    result_expr = op(expr_proxy, col_expr_proxy)
    assert isinstance(result_expr, ExpressionProxy)
    assert (
        str(result_expr._expr)
        == f'[(dyn int: 10.alias("base_expr")) {op_symbol} (col("some_col").alias("col_expr"))]'
    )


def test_expression_proxy_pow_operator(expr_proxy):
    # Test op with literal
    result_lit = expr_proxy**2
    assert isinstance(result_lit, ExpressionProxy)
    assert str(result_lit._expr) == 'dyn int: 10.alias("base_expr").pow([dyn int: 2])'


@pytest.mark.parametrize(
    "op, op_symbol, operator_name",
    [
        (lambda a, b: a == b, "==", "eq"),
        (lambda a, b: a != b, "!=", "ne"),
        (lambda a, b: a < b, "<", "lt"),
        (lambda a, b: a <= b, "<=", "lte"),
        (lambda a, b: a > b, ">", "gt"),
        (lambda a, b: a >= b, ">=", "gte"),
    ],
)
def test_expression_proxy_comparison_operators(
    expr_proxy, col_expr_proxy, op, op_symbol, operator_name
):
    # Test op with literal - now returns ConditionExpression
    result_lit = op(expr_proxy, 0)
    assert isinstance(result_lit, ConditionExpression)
    assert result_lit.operator == operator_name
    assert result_lit._parent is expr_proxy._parent
    assert (
        str(result_lit._expr)
        == f'[(dyn int: 10.alias("base_expr")) {op_symbol} (dyn int: 0)]'
    )

    # Test op with another expression proxy
    result_expr = op(expr_proxy, col_expr_proxy)
    assert isinstance(result_expr, ConditionExpression)
    assert result_expr.operator == operator_name
    assert result_expr._parent is expr_proxy._parent
    assert (
        str(result_expr._expr)
        == f'[(dyn int: 10.alias("base_expr")) {op_symbol} (col("some_col").alias("col_expr"))]'
    )


@pytest.mark.parametrize(
    "op, op_symbol",
    [
        (lambda a, b: a + b, "+"),
        (lambda a, b: a - b, "-"),
        (lambda a, b: a * b, "*"),
        (lambda a, b: a / b, "/"),
        (lambda a, b: a // b, "//"),
        (lambda a, b: a % b, "%"),
    ],
)
def test_expression_proxy_reverse_binary_operators(expr_proxy, op, op_symbol):
    other = 5
    result_proxy = op(other, expr_proxy)  # Reverse order
    assert isinstance(result_proxy, ExpressionProxy)
    expected_expr_str = (
        f'[(dyn int: {other}) {op_symbol} (dyn int: 10.alias("base_expr"))]'
    )
    assert str(result_proxy._expr) == expected_expr_str


def test_expression_proxy_reverse_pow_operator(expr_proxy):
    other = 2
    result_proxy = other**expr_proxy
    assert isinstance(result_proxy, ExpressionProxy)
    assert str(result_proxy._expr) == 'dyn int: 2.pow([dyn int: 10.alias("base_expr")])'


# --- ExpressionProxy Accessor Tests (Wiring) ---


def test_expression_proxy_date_accessor_wiring(expr_proxy):
    """Test that the .date accessor exists and returns the correct type."""
    # Test against the actual registered accessor
    from gaspatchio_core.accessors.date import DateColumnAccessor  # Assuming actual
    # from gaspatchio_core.accessors.base import BaseColumnAccessor # No longer needed for mock
    # from gaspatchio_core.frame.registry import _ACCESSOR_REGISTRY # No longer needed for mock registration

    # REMOVED Mock Class definition and registration
    # class MockDateAccessorExpr(BaseColumnAccessor): ...
    # _ACCESSOR_REGISTRY.register(MockDateAccessorExpr) # REMOVED

    try:
        date_accessor = expr_proxy.date
        assert isinstance(date_accessor, DateColumnAccessor)
        assert date_accessor._proxy is expr_proxy
        # Test caching (within the instance)
        assert expr_proxy.date is date_accessor
        # Ensure different instances have different caches
        expr_proxy_2 = ExpressionProxy(pl.lit(20), expr_proxy._parent)
        assert expr_proxy_2.date is not date_accessor
    finally:
        # No cleanup needed
        pass
        # _ACCESSOR_REGISTRY.unregister("date", "column") # REMOVED


def test_expression_proxy_finance_accessor_wiring(expr_proxy):
    """Test that the .finance accessor exists and returns the correct type."""
    from gaspatchio_core.accessors.finance import (
        FinanceColumnAccessor,  # Assuming actual
    )
    # from gaspatchio_core.accessors.base import BaseColumnAccessor # No longer needed for mock
    # from gaspatchio_core.frame.registry import _ACCESSOR_REGISTRY # No longer needed for mock registration

    # REMOVED Mock class definition and registration
    # class MockFinanceAccessorExpr(BaseColumnAccessor): ...
    # _ACCESSOR_REGISTRY.register(MockFinanceAccessorExpr) # REMOVED

    try:
        finance_accessor = expr_proxy.finance
        assert isinstance(finance_accessor, FinanceColumnAccessor)
        assert finance_accessor._proxy is expr_proxy
        assert expr_proxy.finance is finance_accessor
    finally:
        # No cleanup needed
        pass
        # _ACCESSOR_REGISTRY.unregister("finance", "column") # REMOVED


# --- ExpressionProxy Chaining (Handled by Autopatch tests in test_dispatch.py) ---
# Tests like expr_proxy.alias("new").cast(pl.Float64) are implicitly covered
# by the autopatch mechanism tested in test_dispatch.py, ensuring methods
# return new ExpressionProxy instances.
