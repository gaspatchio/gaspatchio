from typing import Any

import polars as pl
import pytest

# from gaspatchio_core.column.proxy import ColumnProxy, ExpressionProxy # OLD
from gaspatchio_core.column.column_proxy import ColumnProxy  # NEW
from gaspatchio_core.column.expression_proxy import ExpressionProxy  # NEW

# Import the core components and the registry/decorator
from gaspatchio_core.frame.base import ActuarialFrame
from gaspatchio_core.frame.registry import _ACCESSOR_REGISTRY, register_accessor


# Dummy accessor classes for testing - now decorated
# Use distinct names to avoid conflicts if run concurrently or reused
@register_accessor("dummy_col_wiring", kind="column")
class DummyColumnAccessorWiring:
    def __init__(self, parent: Any):
        self._parent = parent

    def col_method(self) -> str:
        return "col_ok"


@register_accessor("another_col_wiring", kind="column")
class AnotherColumnAccessorWiring:
    def __init__(self, parent: Any):
        self._parent = parent


# A dummy frame accessor to ensure kind filtering works
@register_accessor("dummy_frame_wiring", kind="frame")
class DummyFrameAccessorWiring:
    def __init__(self, parent: ActuarialFrame):
        self._parent = parent


@pytest.fixture(autouse=True)
def mock_registry_for_wiring_tests(monkeypatch):
    """Fixture to isolate registry state for these specific wiring tests."""
    # Store original registry
    import copy

    original_registry = copy.deepcopy(_ACCESSOR_REGISTRY)
    # Clear the registry for the duration of the test
    _ACCESSOR_REGISTRY.clear()

    # Register our test-specific accessors manually into the now-empty registry
    # This simulates the state after import but uses only our test doubles
    _ACCESSOR_REGISTRY["dummy_col_wiring"] = {"column": DummyColumnAccessorWiring}
    _ACCESSOR_REGISTRY["another_col_wiring"] = {"column": AnotherColumnAccessorWiring}
    _ACCESSOR_REGISTRY["dummy_frame_wiring"] = {"frame": DummyFrameAccessorWiring}

    yield  # Run the test

    # Restore original registry
    _ACCESSOR_REGISTRY.clear()
    _ACCESSOR_REGISTRY.update(original_registry)


@pytest.fixture
def sample_proxies_wiring() -> tuple[ColumnProxy, ExpressionProxy]:
    """Provides simple ColumnProxy and ExpressionProxy instances for wiring tests."""
    # No need to patch registry here, mock_registry_for_wiring_tests handles it
    parent_frame = ActuarialFrame({"a": [1], "b": [2]})  # Need a parent frame
    col_proxy = ColumnProxy("a", parent=parent_frame)
    expr_proxy = ExpressionProxy(pl.col("a") * 2, parent=parent_frame)
    return col_proxy, expr_proxy


# Tests for ColumnProxy


def test_colproxy_accessor_dynamic_access(sample_proxies_wiring):
    """Test dynamic access for ColumnProxy based on mocked registry."""
    col_proxy, _ = sample_proxies_wiring
    assert hasattr(col_proxy, "dummy_col_wiring")
    accessor_instance = col_proxy.dummy_col_wiring
    assert isinstance(accessor_instance, DummyColumnAccessorWiring)
    assert accessor_instance._parent is col_proxy
    assert accessor_instance.col_method() == "col_ok"

    assert hasattr(col_proxy, "another_col_wiring")
    another_instance = col_proxy.another_col_wiring
    assert isinstance(another_instance, AnotherColumnAccessorWiring)


def test_colproxy_accessor_caching(sample_proxies_wiring):
    """Test accessor caching for ColumnProxy."""
    col_proxy, _ = sample_proxies_wiring
    # Access the property to trigger instantiation and caching via __getattr__ in proxy
    accessor1 = col_proxy.dummy_col_wiring
    accessor2 = col_proxy.dummy_col_wiring  # Should retrieve from cache
    assert accessor1 is accessor2  # Verify same instance


def test_colproxy_accessor_kind_filtering(sample_proxies_wiring):
    """Test kind filtering for ColumnProxy."""
    col_proxy, _ = sample_proxies_wiring
    assert hasattr(col_proxy, "dummy_col_wiring")  # Should exist (kind=column)
    # Should not exist (kind=frame)
    assert not hasattr(col_proxy, "dummy_frame_wiring")
    with pytest.raises(
        AttributeError,
        # Updated match for the actual error from ColumnProxy.__getattr__
        match=r"No 'dummy_frame_wiring' column accessor registered or attribute found.",
    ):
        _ = col_proxy.dummy_frame_wiring


def test_colproxy_accessor_attribute_error(sample_proxies_wiring):
    """Test AttributeError for unregistered names on ColumnProxy."""
    col_proxy, _ = sample_proxies_wiring
    with pytest.raises(
        AttributeError,
        # Updated match for the error raised by ColumnProxy.__getattr__
        match=r"No 'non_existent' column accessor registered or attribute found.",
    ):
        _ = col_proxy.non_existent


def test_colproxy_dir_includes_accessors(sample_proxies_wiring):
    """Test dir() output for ColumnProxy includes registered column accessors."""
    col_proxy, _ = sample_proxies_wiring
    proxy_dir = dir(col_proxy)
    assert "dummy_col_wiring" in proxy_dir
    assert "another_col_wiring" in proxy_dir
    assert "dummy_frame_wiring" not in proxy_dir  # Frame accessor should not be listed
    # Check a standard method still exists
    # Check a Polars method still exists (via autopatch)
    assert "alias" in proxy_dir
    assert "sum" in proxy_dir


# --- Tests for ExpressionProxy --- (Similar structure)


def test_exprproxy_accessor_dynamic_access(sample_proxies_wiring):
    """Test dynamic access for ExpressionProxy."""
    _, expr_proxy = sample_proxies_wiring
    assert hasattr(expr_proxy, "dummy_col_wiring")
    accessor_instance = expr_proxy.dummy_col_wiring
    assert isinstance(accessor_instance, DummyColumnAccessorWiring)
    assert accessor_instance._parent is expr_proxy
    assert accessor_instance.col_method() == "col_ok"

    assert hasattr(expr_proxy, "another_col_wiring")
    another_instance = expr_proxy.another_col_wiring
    assert isinstance(another_instance, AnotherColumnAccessorWiring)


def test_exprproxy_accessor_caching(sample_proxies_wiring):
    """Test accessor caching for ExpressionProxy."""
    _, expr_proxy = sample_proxies_wiring
    accessor1 = expr_proxy.dummy_col_wiring
    accessor2 = expr_proxy.dummy_col_wiring
    assert accessor1 is accessor2


def test_exprproxy_accessor_kind_filtering(sample_proxies_wiring):
    """Test kind filtering for ExpressionProxy."""
    _, expr_proxy = sample_proxies_wiring
    assert hasattr(expr_proxy, "dummy_col_wiring")
    assert not hasattr(expr_proxy, "dummy_frame_wiring")
    with pytest.raises(
        AttributeError,
        # Updated match for the actual error from ExpressionProxy.__getattr__
        match=r"No 'dummy_frame_wiring' column accessor registered, and attribute not found on proxied Expr.",
    ):
        _ = expr_proxy.dummy_frame_wiring


def test_exprproxy_accessor_attribute_error(sample_proxies_wiring):
    """Test AttributeError for unregistered names on ExpressionProxy."""
    _, expr_proxy = sample_proxies_wiring
    with pytest.raises(
        AttributeError,
        # Updated match for the actual error from ExpressionProxy.__getattr__
        match=r"No 'non_existent' column accessor registered, and attribute not found on proxied Expr.",
    ):
        _ = expr_proxy.non_existent


def test_exprproxy_dir_includes_accessors(sample_proxies_wiring):
    """Test dir() output for ExpressionProxy."""
    _, expr_proxy = sample_proxies_wiring
    proxy_dir = dir(expr_proxy)
    assert "dummy_col_wiring" in proxy_dir
    assert "another_col_wiring" in proxy_dir
    assert "dummy_frame_wiring" not in proxy_dir
    assert "alias" in proxy_dir  # Standard method
    assert "sum" in proxy_dir  # Polars method
