import unittest.mock
from typing import Any

import pytest

# Import the core components and the registry directly for patching
from gaspatchio_core.frame.base import ActuarialFrame
from gaspatchio_core.frame.registry import _ACCESSOR_REGISTRY


# Dummy accessor classes for testing
class DummyFrameAccessor:
    def __init__(self, parent: ActuarialFrame):
        self._parent = parent

    def frame_method(self) -> str:
        return "frame_ok"


class AnotherFrameAccessor:
    def __init__(self, parent: ActuarialFrame):
        self._parent = parent


# A dummy column accessor to ensure kind filtering works
class DummyColumnAccessor:
    def __init__(self, parent: Any):
        self._parent = parent


# Define the registry entries for the dummy accessors
DUMMY_REGISTRY = {
    "dummy_frame": (DummyFrameAccessor, "frame"),
    "another_frame": (AnotherFrameAccessor, "frame"),
    "dummy_column": (
        DummyColumnAccessor,
        "column",
    ),  # Should be ignored by ActuarialFrame
}


@pytest.fixture
def mock_registry():
    """Fixture to temporarily patch the global accessor registry."""
    with unittest.mock.patch.dict(_ACCESSOR_REGISTRY, DUMMY_REGISTRY, clear=True):
        yield


@pytest.fixture
def sample_frame() -> ActuarialFrame:
    """Provides a simple ActuarialFrame instance for testing."""
    return ActuarialFrame({"a": [1, 2], "b": [3, 4]})


def test_frame_accessor_dynamic_access(
    sample_frame: ActuarialFrame, mock_registry: None
):
    """Test that registered frame accessors can be accessed dynamically."""
    assert hasattr(sample_frame, "dummy_frame")
    accessor_instance = sample_frame.dummy_frame
    assert isinstance(accessor_instance, DummyFrameAccessor)
    assert accessor_instance._parent is sample_frame
    assert accessor_instance.frame_method() == "frame_ok"

    assert hasattr(sample_frame, "another_frame")
    another_instance = sample_frame.another_frame
    assert isinstance(another_instance, AnotherFrameAccessor)
    assert another_instance._parent is sample_frame


def test_frame_accessor_caching(sample_frame: ActuarialFrame, mock_registry: None):
    """Test that accessor instances are cached after first access."""
    accessor1 = sample_frame.dummy_frame
    accessor2 = sample_frame.dummy_frame
    assert accessor1 is accessor2  # Should be the same instance


def test_frame_accessor_kind_filtering(
    sample_frame: ActuarialFrame, mock_registry: None
):
    """Test that only 'frame' kind accessors are available on the frame."""
    assert hasattr(sample_frame, "dummy_frame")
    assert not hasattr(sample_frame, "dummy_column")  # This is a column accessor


def test_frame_accessor_attribute_error(
    sample_frame: ActuarialFrame, mock_registry: None
):
    """Test that accessing an unregistered accessor name raises AttributeError."""
    with pytest.raises(
        AttributeError, match="No 'non_existent' frame accessor registered"
    ):
        _ = sample_frame.non_existent


def test_frame_dir_includes_accessors(
    sample_frame: ActuarialFrame, mock_registry: None
):
    """Test that dir(frame) includes the names of registered frame accessors."""
    frame_dir = dir(sample_frame)
    print("\nFrame dir:", frame_dir)  # Debug print
    assert "dummy_frame" in frame_dir
    assert "another_frame" in frame_dir
    assert "dummy_column" not in frame_dir  # Should only include frame accessors
    # Check a standard method and a Polars method are still there
    assert "collect" in frame_dir
    assert "filter" in frame_dir  # Example Polars LazyFrame method
