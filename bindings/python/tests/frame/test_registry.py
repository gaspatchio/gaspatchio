# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the accessor registry."""

import copy

import pytest

from gaspatchio_core.accessors.base import BaseColumnAccessor, BaseFrameAccessor

# Import the items to test
from gaspatchio_core.frame.registry import (
    _ACCESSOR_REGISTRY,
    list_registered_accessors,
    register_accessor,
)

# Save the real registry state once at import time
_ORIGINAL_REGISTRY = copy.deepcopy(_ACCESSOR_REGISTRY)


# --- Test Setup ---
def setup_function(function):
    """Reset the registry to a clean state before each test."""
    _ACCESSOR_REGISTRY.clear()


def teardown_function(function):
    """Restore the original registry after each test."""
    _ACCESSOR_REGISTRY.clear()
    _ACCESSOR_REGISTRY.update(copy.deepcopy(_ORIGINAL_REGISTRY))


# --- Base Dummy Accessor Classes ---
# These inherit from the real base classes so they pass the new validation.


class DummyFrameAccessor(BaseFrameAccessor):
    def __init__(self, parent):
        self._frame = parent


class DummyColumnAccessor(BaseColumnAccessor):
    def __init__(self, parent):
        self._proxy = parent


# --- Test Cases: original registration behaviour ---


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


def test_register_invalid_kind():
    """Test that registering with an invalid kind raises ValueError."""
    with pytest.raises(ValueError, match="Accessor kind must be 'frame' or 'column'"):

        @register_accessor("invalid_kind_acc", kind="invalid")
        class InvalidKindAcc:
            pass

    assert "invalid_kind_acc" not in _ACCESSOR_REGISTRY


# --- Task 1: Idempotent Same-Class Registration ---


def test_register_same_class_is_idempotent():
    """Re-registering the exact same class object with same name+kind succeeds silently."""

    class MyFrameAcc(DummyFrameAccessor):
        pass

    # Register the first time.
    register_accessor("idempotent_frame", kind="frame")(MyFrameAcc)
    # Register the same class object a second time — must not raise.
    register_accessor("idempotent_frame", kind="frame")(MyFrameAcc)

    assert _ACCESSOR_REGISTRY["idempotent_frame"]["frame"] is MyFrameAcc


def test_register_different_class_same_name_raises():
    """Registering a different class with the same name+kind raises ValueError naming both."""

    @register_accessor("conflict_col", kind="column")
    class FirstAcc(DummyColumnAccessor):
        pass

    with pytest.raises(ValueError) as exc_info:

        @register_accessor("conflict_col", kind="column")
        class SecondAcc(DummyColumnAccessor):
            pass

    message = str(exc_info.value)
    assert "FirstAcc" in message
    assert "SecondAcc" in message
    # Original class is preserved
    assert _ACCESSOR_REGISTRY["conflict_col"]["column"] is FirstAcc


def test_register_duplicate_name():
    """Test that registering a duplicate name and kind raises ValueError."""

    @register_accessor("duplicate_name", kind="frame")
    class FirstAcc(DummyFrameAccessor):
        pass

    # Attempt to register a DIFFERENT class with the SAME name+kind
    with pytest.raises(ValueError) as exc_info:

        @register_accessor("duplicate_name", kind="frame")
        class SecondAcc(DummyFrameAccessor):
            pass

    message = str(exc_info.value)
    assert "FirstAcc" in message
    assert "SecondAcc" in message

    # Ensure only the first one is actually registered and kind is correct
    assert len(_ACCESSOR_REGISTRY) == 1
    assert "duplicate_name" in _ACCESSOR_REGISTRY
    assert len(_ACCESSOR_REGISTRY["duplicate_name"]) == 1
    assert "frame" in _ACCESSOR_REGISTRY["duplicate_name"]
    assert _ACCESSOR_REGISTRY["duplicate_name"]["frame"] is FirstAcc


# --- Task 2: Registration Validation ---


def test_register_frame_accessor_without_base_raises():
    """Registering kind='frame' without BaseFrameAccessor raises TypeError."""

    class NotAFrameAccessor:
        def __init__(self, parent):
            pass

    with pytest.raises(TypeError) as exc_info:
        register_accessor("bad_frame", kind="frame")(NotAFrameAccessor)

    message = str(exc_info.value)
    assert "BaseFrameAccessor" in message
    assert "NotAFrameAccessor" in message


def test_register_column_accessor_without_base_raises():
    """Registering kind='column' without BaseColumnAccessor raises TypeError."""

    class NotAColumnAccessor:
        def __init__(self, parent):
            pass

    with pytest.raises(TypeError) as exc_info:
        register_accessor("bad_column", kind="column")(NotAColumnAccessor)

    message = str(exc_info.value)
    assert "BaseColumnAccessor" in message
    assert "NotAColumnAccessor" in message


def test_register_valid_frame_accessor_subclass():
    """A class that inherits BaseFrameAccessor registers successfully."""

    @register_accessor("valid_frame", kind="frame")
    class ValidFrameAcc(BaseFrameAccessor):
        def __init__(self, frame):
            super().__init__(frame)

    assert _ACCESSOR_REGISTRY["valid_frame"]["frame"] is ValidFrameAcc


def test_register_valid_column_accessor_subclass():
    """A class that inherits BaseColumnAccessor registers successfully."""

    @register_accessor("valid_column", kind="column")
    class ValidColumnAcc(BaseColumnAccessor):
        def __init__(self, proxy):
            super().__init__(proxy)

    assert _ACCESSOR_REGISTRY["valid_column"]["column"] is ValidColumnAcc


# --- Task 3: list_registered_accessors() ---


def test_list_registered_accessors_returns_copy():
    """list_registered_accessors returns a shallow copy, not the real dict."""

    @register_accessor("listed_frame", kind="frame")
    class ListedFrameAcc(BaseFrameAccessor):
        def __init__(self, frame):
            super().__init__(frame)

    result = list_registered_accessors()
    assert "listed_frame" in result
    assert result["listed_frame"]["frame"] is ListedFrameAcc

    # Mutations to the returned dict must not affect the real registry.
    result["listed_frame"]["frame"] = None
    assert _ACCESSOR_REGISTRY["listed_frame"]["frame"] is ListedFrameAcc


def test_list_registered_accessors_empty():
    """list_registered_accessors returns an empty dict when registry is empty."""
    result = list_registered_accessors()
    assert result == {}


def test_list_registered_accessors_multiple_entries():
    """list_registered_accessors reflects all currently registered accessors."""

    @register_accessor("multi_frame", kind="frame")
    class MultiFrameAcc(BaseFrameAccessor):
        def __init__(self, frame):
            super().__init__(frame)

    @register_accessor("multi_col", kind="column")
    class MultiColAcc(BaseColumnAccessor):
        def __init__(self, proxy):
            super().__init__(proxy)

    result = list_registered_accessors()
    assert "multi_frame" in result
    assert "multi_col" in result
    assert result["multi_frame"]["frame"] is MultiFrameAcc
    assert result["multi_col"]["column"] is MultiColAcc


# --- Tests that require the real (uncleared) registry state ---


class TestBuiltinAccessors:
    """Tests that rely on built-in accessors being imported and registered."""

    def test_contains_builtin_accessors(self):
        """Should include built-in accessors like finance and projection."""
        result = list_registered_accessors()
        assert "finance" in result
        assert "projection" in result
        assert "column" in result["finance"]
        assert "frame" in result["finance"]
