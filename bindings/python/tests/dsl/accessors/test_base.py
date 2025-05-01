"""Tests for the base accessor classes."""

import pytest
from gaspatchio_core.dsl.accessors.base import BaseColumnAccessor, BaseFrameAccessor

# Define dummy concrete subclasses for testing


class DummyFrameAccessor(BaseFrameAccessor):
    """A minimal concrete implementation for testing BaseFrameAccessor."""

    def __init__(self, frame):
        super().__init__(frame)

    def some_frame_method(self):
        return self._frame  # Example method accessing the frame


class DummyColumnAccessor(BaseColumnAccessor):
    """A minimal concrete implementation for testing BaseColumnAccessor."""

    def __init__(self, proxy):
        super().__init__(proxy)

    def some_column_method(self):
        return self._proxy  # Example method accessing the proxy


# Define dummy parent objects for testing
class MockActuarialFrame:
    pass


class MockColumnProxy:
    pass


# --- Test Cases ---


def test_base_frame_accessor_instantiation():
    """Verify BaseFrameAccessor cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseFrameAccessor(None)  # type: ignore


def test_base_column_accessor_instantiation():
    """Verify BaseColumnAccessor cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseColumnAccessor(None)  # type: ignore


def test_dummy_frame_accessor_stores_parent():
    """Verify concrete Frame accessor stores the parent frame."""
    mock_frame = MockActuarialFrame()
    accessor = DummyFrameAccessor(mock_frame)  # type: ignore
    assert accessor._frame is mock_frame
    assert accessor.some_frame_method() is mock_frame


def test_dummy_column_accessor_stores_parent():
    """Verify concrete Column accessor stores the parent proxy."""
    mock_proxy = MockColumnProxy()
    accessor = DummyColumnAccessor(mock_proxy)
    assert accessor._proxy is mock_proxy
    assert accessor.some_column_method() is mock_proxy
