# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import polars as pl
import pytest

# Test imports - Keep these as they might be needed for remaining tests or future ones
from gaspatchio_core import ColumnProxy, ExpressionProxy


# Mock ActuarialFrame - Keep fixture definitions here for now
# Consider moving to conftest.py if shared across more test files
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


# Fixture for ColumnProxy
@pytest.fixture
def col_proxy(mock_parent):
    # Instantiate directly now that __new__ check is removed
    return ColumnProxy("test_col", mock_parent)


# Fixture for ExpressionProxy
@pytest.fixture
def expr_proxy(mock_parent):
    # Instantiate directly now that __new__ check is removed
    return ExpressionProxy(pl.lit(10), mock_parent)


# --- ColumnProxy Tests ---
# MOVED TO test_column_proxy.py

# def test_column_proxy_init(col_proxy):
#     ...
#
# def test_column_proxy_repr(col_proxy):
#     ...
#
# def test_column_proxy_to_expr(col_proxy):
#     ...
#
# def test_column_proxy_alias(col_proxy):
#     ...
#
# def test_column_proxy_cast(col_proxy):
#     ...
#
# def test_column_proxy_add(col_proxy):
#     ...
#
# def test_column_proxy_eq(col_proxy):
#     ...


# --- ExpressionProxy Tests ---
# MOVED TO test_expression_proxy.py

# def test_expression_proxy_init(expr_proxy):
#     ...
#
# def test_expression_proxy_repr(expr_proxy):
#     ...
#
# def test_expression_proxy_to_expr(expr_proxy):
#     ...
#
# def test_expression_proxy_alias(expr_proxy):
#     ...
#
# def test_expression_proxy_cast(expr_proxy):
#     ...
#
# def test_expression_proxy_add(expr_proxy, mock_parent):
#     ...
#
# def test_expression_proxy_gt(expr_proxy):
#     ...

# This file can now contain tests that involve interactions
# between ColumnProxy and ExpressionProxy, or other shared concerns,
# or it can be removed if all tests are covered elsewhere.
