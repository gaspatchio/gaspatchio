"""Tests for the accessor registry."""

import pytest

# Import the items to test
from gaspatchio_core.frame.registry import (
    _ACCESSOR_REGISTRY,
    register_accessor,
)


# --- Test Setup ---
def setup_function(function):
    """Clear the registry before each test function."""
    _ACCESSOR_REGISTRY.clear()


def teardown_function(function):
    """Clear the registry after each test function."""
    _ACCESSOR_REGISTRY.clear()


# --- Dummy Accessor Classes ---
class DummyFrameAccessor:
    def __init__(self, parent):
        self._parent = parent


class DummyColumnAccessor:
    def __init__(self, parent):
        self._parent = parent


# --- Test Cases ---


def test_register_frame_accessor():
    """Test registering a frame accessor."""

    @register_accessor("dummy_frame", kind="frame")
    class TestFrameAcc(DummyFrameAccessor):
        pass

    assert "dummy_frame" in _ACCESSOR_REGISTRY
    # Access nested dict
    assert "frame" in _ACCESSOR_REGISTRY["dummy_frame"]
    assert _ACCESSOR_REGISTRY["dummy_frame"]["frame"] is TestFrameAcc


def test_register_column_accessor():
    """Test registering a column accessor (default kind)."""

    @register_accessor("dummy_col")
    class TestColAcc(DummyColumnAccessor):
        pass

    assert "dummy_col" in _ACCESSOR_REGISTRY
    # Access nested dict
    assert "column" in _ACCESSOR_REGISTRY["dummy_col"]
    assert _ACCESSOR_REGISTRY["dummy_col"]["column"] is TestColAcc


def test_register_column_accessor_explicit():
    """Test registering a column accessor explicitly."""

    @register_accessor("dummy_col_explicit", kind="column")
    class TestColAccExplicit(DummyColumnAccessor):
        pass

    assert "dummy_col_explicit" in _ACCESSOR_REGISTRY
    # Access nested dict
    assert "column" in _ACCESSOR_REGISTRY["dummy_col_explicit"]
    assert _ACCESSOR_REGISTRY["dummy_col_explicit"]["column"] is TestColAccExplicit


def test_register_duplicate_name():
    """Test that registering a duplicate name and kind raises ValueError."""

    @register_accessor("duplicate_name", kind="frame")
    class FirstAcc:
        pass

    # Attempt to register the SAME name and SAME kind again
    with pytest.raises(
        ValueError,
        match=r"Accessor with name 'duplicate_name' and kind 'frame' already registered.",
    ):

        @register_accessor("duplicate_name", kind="frame")
        class SecondAcc:  # Same name, same kind
            pass

    # Ensure only the first one is actually registered and kind is correct
    assert len(_ACCESSOR_REGISTRY) == 1
    assert "duplicate_name" in _ACCESSOR_REGISTRY
    assert len(_ACCESSOR_REGISTRY["duplicate_name"]) == 1
    assert "frame" in _ACCESSOR_REGISTRY["duplicate_name"]
    assert _ACCESSOR_REGISTRY["duplicate_name"]["frame"] is FirstAcc


def test_register_invalid_kind():
    """Test that registering with an invalid kind raises ValueError."""
    with pytest.raises(ValueError, match="Accessor kind must be 'frame' or 'column'"):

        @register_accessor("invalid_kind_acc", kind="invalid")
        class InvalidKindAcc:
            pass

    assert "invalid_kind_acc" not in _ACCESSOR_REGISTRY
