import unittest.mock
from typing import Any

import polars as pl
import pytest
from gaspatchio_core.column.proxy import ColumnProxy, ExpressionProxy

# Import the core components and the registry directly for patching
from gaspatchio_core.frame.base import ActuarialFrame
from gaspatchio_core.frame.registry import _ACCESSOR_REGISTRY


# Dummy accessor classes for testing
class DummyColumnAccessor:
    def __init__(self, parent: Any):
        self._parent = parent

    def col_method(self) -> str:
        return "col_ok"


class AnotherColumnAccessor:
    def __init__(self, parent: Any):
        self._parent = parent


# A dummy frame accessor to ensure kind filtering works
class DummyFrameAccessor:
    def __init__(self, parent: ActuarialFrame):
        self._parent = parent


# Define the registry entries for the dummy accessors
DUMMY_REGISTRY = {
    "dummy_col": (DummyColumnAccessor, "column"),
    "another_col": (AnotherColumnAccessor, "column"),
    "dummy_frame": (DummyFrameAccessor, "frame"),  # Should be ignored by proxies
}


@pytest.fixture
def mock_registry():
    """Fixture to temporarily patch the global accessor registry."""
    with unittest.mock.patch.dict(_ACCESSOR_REGISTRY, DUMMY_REGISTRY, clear=True):
        yield


@pytest.fixture
def sample_proxies(mock_registry: None) -> tuple[ColumnProxy, ExpressionProxy]:
    """Provides simple ColumnProxy and ExpressionProxy instances."""
    parent_frame = ActuarialFrame({"a": [1], "b": [2]})  # Need a parent frame
    col_proxy = ColumnProxy("a", parent=parent_frame)
    expr_proxy = ExpressionProxy(pl.col("a") * 2, parent=parent_frame)
    return col_proxy, expr_proxy


# Tests for ColumnProxy


def test_colproxy_accessor_dynamic_access(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test dynamic access for ColumnProxy."""
    col_proxy, _ = sample_proxies
    assert hasattr(col_proxy, "dummy_col")
    accessor_instance = col_proxy.dummy_col
    assert isinstance(accessor_instance, DummyColumnAccessor)
    assert accessor_instance._parent is col_proxy
    assert accessor_instance.col_method() == "col_ok"

    assert hasattr(col_proxy, "another_col")
    another_instance = col_proxy.another_col
    assert isinstance(another_instance, AnotherColumnAccessor)


def test_colproxy_accessor_caching(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test accessor caching for ColumnProxy."""
    col_proxy, _ = sample_proxies
    accessor1 = col_proxy.dummy_col
    accessor2 = col_proxy.dummy_col
    assert accessor1 is accessor2


def test_colproxy_accessor_kind_filtering(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test kind filtering for ColumnProxy."""
    col_proxy, _ = sample_proxies
    assert hasattr(col_proxy, "dummy_col")
    assert not hasattr(col_proxy, "dummy_frame")


def test_colproxy_accessor_attribute_error(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test AttributeError for unregistered names on ColumnProxy."""
    col_proxy, _ = sample_proxies
    with pytest.raises(
        AttributeError,
        match=r"'ColumnProxy' object has no attribute 'non_existent' and no matching column accessor was found.",
    ):
        _ = col_proxy.non_existent


def test_colproxy_dir_includes_accessors(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test dir() output for ColumnProxy."""
    col_proxy, _ = sample_proxies
    proxy_dir = dir(col_proxy)
    assert "dummy_col" in proxy_dir
    assert "another_col" in proxy_dir
    assert "dummy_frame" not in proxy_dir
    assert "alias" in proxy_dir  # Standard method
    assert "sum" in proxy_dir  # Polars method


# --- Tests for ExpressionProxy --- (Similar structure)


def test_exprproxy_accessor_dynamic_access(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test dynamic access for ExpressionProxy."""
    _, expr_proxy = sample_proxies
    assert hasattr(expr_proxy, "dummy_col")
    accessor_instance = expr_proxy.dummy_col
    assert isinstance(accessor_instance, DummyColumnAccessor)
    assert accessor_instance._parent is expr_proxy
    assert accessor_instance.col_method() == "col_ok"

    assert hasattr(expr_proxy, "another_col")
    another_instance = expr_proxy.another_col
    assert isinstance(another_instance, AnotherColumnAccessor)


def test_exprproxy_accessor_caching(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test accessor caching for ExpressionProxy."""
    _, expr_proxy = sample_proxies
    accessor1 = expr_proxy.dummy_col
    accessor2 = expr_proxy.dummy_col
    assert accessor1 is accessor2


def test_exprproxy_accessor_kind_filtering(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test kind filtering for ExpressionProxy."""
    _, expr_proxy = sample_proxies
    assert hasattr(expr_proxy, "dummy_col")
    assert not hasattr(expr_proxy, "dummy_frame")


def test_exprproxy_accessor_attribute_error(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test AttributeError for unregistered names on ExpressionProxy."""
    _, expr_proxy = sample_proxies
    with pytest.raises(
        AttributeError,
        match=r"'ExpressionProxy' object has no attribute 'non_existent' and no matching column accessor was found.",
    ):
        _ = expr_proxy.non_existent


def test_exprproxy_dir_includes_accessors(
    sample_proxies: tuple[ColumnProxy, ExpressionProxy], mock_registry: None
):
    """Test dir() output for ExpressionProxy."""
    _, expr_proxy = sample_proxies
    proxy_dir = dir(expr_proxy)
    assert "dummy_col" in proxy_dir
    assert "another_col" in proxy_dir
    assert "dummy_frame" not in proxy_dir
    assert "alias" in proxy_dir  # Standard method
    assert "sum" in proxy_dir  # Polars method
