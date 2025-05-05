from unittest.mock import MagicMock

import polars as pl
import pytest

# Assuming the proxies are exported from the column package
from gaspatchio_core.column import ColumnProxy, ExpressionProxy


# Mock ActuarialFrame for testing proxy parent interactions
class MockActuarialFrame:
    def __init__(self):
        self._convert_to_expr_mock = MagicMock()

    def _convert_to_expr(self, value):
        # If it's already a proxy, return its expr or a col expr
        if isinstance(value, ExpressionProxy):
            return value._expr
        if isinstance(value, ColumnProxy):
            return pl.col(value.name)
        # Otherwise, call the mock or return a literal
        self._convert_to_expr_mock(value)
        return pl.lit(value)  # Simple mock behavior


# Fixture for mock parent
@pytest.fixture
def mock_parent():
    return MockActuarialFrame()


# Fixture for ColumnProxy (cannot be instantiated directly)
# We need a way to get an instance for testing operators/methods
# Let's create a helper or subclass for tests
class TestColumnProxy(ColumnProxy):
    def __new__(cls, *args, **kwargs):
        # Bypass the direct instantiation check for testing
        return object.__new__(cls)


@pytest.fixture
def col_proxy(mock_parent):
    return TestColumnProxy("test_col", mock_parent)


# Fixture for ExpressionProxy (cannot be instantiated directly)
class TestExpressionProxy(ExpressionProxy):
    def __new__(cls, *args, **kwargs):
        # Bypass the direct instantiation check for testing
        return object.__new__(cls)


@pytest.fixture
def expr_proxy(mock_parent):
    return TestExpressionProxy(pl.lit(10), mock_parent)


# --- ColumnProxy Tests ---


def test_column_proxy_init(col_proxy):
    assert col_proxy.name == "test_col"
    assert isinstance(col_proxy._parent, MockActuarialFrame)


def test_column_proxy_repr(col_proxy):
    assert repr(col_proxy) == "ColumnProxy(name='test_col')"


def test_column_proxy_to_expr(col_proxy):
    expr = col_proxy._to_expr()
    assert isinstance(expr, pl.Expr)
    # Check if the expression represents selecting the column
    # This comparison is tricky, checking type and name is usually enough
    assert str(expr) == 'col("test_col")'


def test_column_proxy_alias(col_proxy):
    new_proxy = col_proxy.alias("new_name")
    assert isinstance(new_proxy, ExpressionProxy)
    assert str(new_proxy._expr) == 'col("test_col").alias("new_name")'


def test_column_proxy_cast(col_proxy):
    new_proxy = col_proxy.cast(pl.Int32)
    assert isinstance(new_proxy, ExpressionProxy)
    # Representation might vary slightly depending on Polars version
    assert "Int32" in str(new_proxy._expr)
    assert "test_col" in str(new_proxy._expr)


def test_column_proxy_add(col_proxy):
    result_proxy = col_proxy + 5
    assert isinstance(result_proxy, ExpressionProxy)
    # Example check - Polars expression string representation
    assert str(result_proxy._expr) == '[col("test_col") + 5]'


def test_column_proxy_eq(col_proxy):
    result_proxy = col_proxy == "abc"
    assert isinstance(result_proxy, ExpressionProxy)
    assert str(result_proxy._expr) == '[col("test_col") == String(abc)]'


# --- ExpressionProxy Tests ---


def test_expression_proxy_init(expr_proxy):
    assert isinstance(expr_proxy._expr, pl.Expr)
    assert isinstance(expr_proxy._parent, MockActuarialFrame)


def test_expression_proxy_repr(expr_proxy):
    assert repr(expr_proxy).startswith("ExpressionProxy(expr=")


def test_expression_proxy_to_expr(expr_proxy):
    assert isinstance(expr_proxy._to_expr(), pl.Expr)
    assert str(expr_proxy._to_expr()) == "10"


def test_expression_proxy_alias(expr_proxy):
    new_proxy = expr_proxy.alias("result")
    assert isinstance(new_proxy, ExpressionProxy)
    assert str(new_proxy._expr) == 'lit(10).alias("result")'


def test_expression_proxy_cast(expr_proxy):
    new_proxy = expr_proxy.cast(pl.Float64)
    assert isinstance(new_proxy, ExpressionProxy)
    assert "Float64" in str(new_proxy._expr)


def test_expression_proxy_add(expr_proxy, mock_parent):
    # Test adding another expression proxy
    other_proxy = TestExpressionProxy(pl.col("another_col"), mock_parent)
    result_proxy = expr_proxy + other_proxy
    assert isinstance(result_proxy, ExpressionProxy)
    assert str(result_proxy._expr) == '[lit(10) + col("another_col")]'


def test_expression_proxy_gt(expr_proxy):
    result_proxy = expr_proxy > 0
    assert isinstance(result_proxy, ExpressionProxy)
    assert str(result_proxy._expr) == "[lit(10) > 0]"


def test_proxy_instantiation_error():
    with pytest.raises(TypeError, match="Cannot directly instantiate Proxy classes"):
        ColumnProxy("a", MagicMock())  # type: ignore
    with pytest.raises(TypeError, match="Cannot directly instantiate Proxy classes"):
        ExpressionProxy(pl.lit(1), MagicMock())  # type: ignore
