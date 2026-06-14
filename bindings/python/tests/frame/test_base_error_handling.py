# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Integration tests for Section 1.4: Update Base Frame with error handling and mixed graph formats.

Tests:
- Mixed graph formats (tuples and TracedOperations)
- Error handling in collect()
- Error handling in profile()
- Error mode configuration
- Backward compatibility
"""

import os

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame
from gaspatchio_core.errors.metadata import OperationMetadata, TracedOperation
from gaspatchio_core.util import get_error_mode, set_error_mode


class TestMixedGraphFormats:
    """Test backward compatibility with mixed tuple and TracedOperation formats."""

    def test_collect_with_tuple_format_only(self):
        """Test collect() works with legacy tuple format."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        # Manually add tuple format operations to graph
        af._tracing = True
        af._computation_graph.append(("c", pl.col("a") + pl.col("b")))
        af._computation_graph.append(("d", pl.col("c") * 2))

        result = af.collect()

        assert "c" in result.columns
        assert "d" in result.columns
        assert result["c"].to_list() == [5, 7, 9]
        assert result["d"].to_list() == [10, 14, 18]

    def test_collect_with_traced_operation_format_only(self):
        """Test collect() works with new TracedOperation format."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        # Manually add TracedOperation format operations to graph
        af._tracing = True
        metadata1 = OperationMetadata("test.py", 10, "af['c'] = af['a'] + af['b']")
        metadata2 = OperationMetadata("test.py", 11, "af['d'] = af['c'] * 2")

        af._computation_graph.append(
            TracedOperation("c", pl.col("a") + pl.col("b"), metadata1),
        )
        af._computation_graph.append(TracedOperation("d", pl.col("c") * 2, metadata2))

        result = af.collect()

        assert "c" in result.columns
        assert "d" in result.columns
        assert result["c"].to_list() == [5, 7, 9]
        assert result["d"].to_list() == [10, 14, 18]

    def test_collect_with_mixed_formats(self):
        """Test collect() works with both tuple and TracedOperation formats mixed."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        # Mix tuple and TracedOperation formats
        af._tracing = True
        af._computation_graph.append(("c", pl.col("a") + pl.col("b")))  # Tuple format

        metadata = OperationMetadata("test.py", 11, "af['d'] = af['c'] * 2")
        af._computation_graph.append(
            TracedOperation("d", pl.col("c") * 2, metadata),
        )  # TracedOperation format

        result = af.collect()

        assert "c" in result.columns
        assert "d" in result.columns
        assert result["c"].to_list() == [5, 7, 9]
        assert result["d"].to_list() == [10, 14, 18]

    def test_profile_with_mixed_formats(self):
        """Test profile() works with mixed formats and returns both result and profile."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})

        # Mix formats
        af._tracing = True
        af._computation_graph.append(("c", pl.col("a") + pl.col("b")))

        metadata = OperationMetadata("test.py", 11, "af['d'] = af['c'] * 2")
        af._computation_graph.append(TracedOperation("d", pl.col("c") * 2, metadata))

        result_df, profile_df = af.profile()

        # Check result
        assert "c" in result_df.columns
        assert "d" in result_df.columns
        assert result_df["c"].to_list() == [5, 7, 9]
        assert result_df["d"].to_list() == [10, 14, 18]

        # Check profile is returned (structure may vary by Polars version)
        assert isinstance(profile_df, pl.DataFrame)


class TestErrorModeConfiguration:
    """Test error mode configuration and its effects."""

    def setup_method(self):
        """Reset error mode before each test."""
        set_error_mode("standard")

    def teardown_method(self):
        """Reset error mode after each test."""
        set_error_mode("standard")

    def test_error_mode_standard_fast_path(self):
        """Test that standard error mode uses fast path (just re-raises)."""
        set_error_mode("standard")
        af = ActuarialFrame({"a": [1, 2, 3]})
        af._tracing = False
        af._mode = "run"

        # This should trigger an error and use fast path
        af["b"] = pl.col("nonexistent_column")

        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.collect()

    def test_error_mode_enhanced_triggers_enhanced_handling(self):
        """Test that enhanced error mode attempts to use enhanced error handling."""
        set_error_mode("enhanced")
        af = ActuarialFrame({"a": [1, 2, 3]})

        # Add a TracedOperation that will fail
        metadata = OperationMetadata("test.py", 10, "af['b'] = af['nonexistent']")
        af._computation_graph.append(
            TracedOperation("b", pl.col("nonexistent"), metadata),
        )

        # Since ErrorBoundaryFinder isn't implemented yet, this should fall back to basic error handling
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.collect()

    def test_error_mode_debug_enables_enhanced_handling(self):
        """Test that debug error mode enables enhanced error handling."""
        set_error_mode("debug")
        af = ActuarialFrame({"a": [1, 2, 3]})

        # Add a TracedOperation that will fail
        metadata = OperationMetadata("test.py", 10, "af['b'] = af['nonexistent']")
        af._computation_graph.append(
            TracedOperation("b", pl.col("nonexistent"), metadata),
        )

        # Since ErrorBoundaryFinder isn't implemented yet, this should fall back to basic error handling
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.collect()

    def test_get_set_error_mode_functions(self):
        """Test error mode getter and setter functions."""
        # Test initial state (default is now "basic")
        assert get_error_mode() == "basic"

        # Test valid modes (standard is mapped to basic internally)
        for mode_input, expected_output in [("basic", "basic"), ("enhanced", "enhanced"), ("debug", "debug"), ("standard", "basic")]:
            set_error_mode(mode_input)
            assert get_error_mode() == expected_output
            # Environment variable stores the normalized value
            assert os.environ.get("AF_ERROR_MODE") == expected_output

        # Test invalid mode
        with pytest.raises(ValueError, match="Invalid error mode"):
            set_error_mode("invalid")

    def test_error_mode_environment_variable(self):
        """Test that error mode respects environment variable."""
        # Save current state
        original_mode = get_error_mode()

        # Set environment variable
        os.environ["AF_ERROR_MODE"] = "debug"

        # Force reload of the module to pick up environment variable
        import importlib

        import gaspatchio_core.util

        importlib.reload(gaspatchio_core.util)

        # Re-import after reload
        from gaspatchio_core.util import get_error_mode as get_error_mode_reloaded

        assert get_error_mode_reloaded() == "debug"

        # Clean up
        if "AF_ERROR_MODE" in os.environ:
            del os.environ["AF_ERROR_MODE"]

        # Restore original state
        set_error_mode(original_mode)


class TestErrorHandlingIntegration:
    """Test error handling integration in collect() and profile()."""

    def setup_method(self):
        """Reset error mode before each test."""
        set_error_mode("standard")

    def teardown_method(self):
        """Reset error mode after each test."""
        set_error_mode("standard")

    def test_collect_error_with_tracing_enabled(self):
        """Test that collect() calls enhanced error handling when tracing is enabled."""
        af = ActuarialFrame({"a": [1, 2, 3]})
        af._tracing = True

        # Add operation that will fail
        af["b"] = pl.col("nonexistent_column")

        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.collect()

    def test_collect_error_with_debug_mode(self):
        """Test that collect() calls enhanced error handling in debug mode."""
        af = ActuarialFrame({"a": [1, 2, 3]}, mode="debug")

        # Add operation that will fail
        af["b"] = pl.col("nonexistent_column")

        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.collect()

    def test_profile_error_handling(self):
        """Test that profile() also calls error handling on exceptions."""
        af = ActuarialFrame({"a": [1, 2, 3]})
        af._tracing = True

        # Add operation that will fail
        af["b"] = pl.col("nonexistent_column")

        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.profile()

    def test_error_handling_fallback_on_component_failure(self):
        """Test that error handling falls back gracefully when components fail."""
        set_error_mode("enhanced")
        af = ActuarialFrame({"a": [1, 2, 3]})

        # Add a TracedOperation
        metadata = OperationMetadata("test.py", 10, "af['b'] = af['nonexistent']")
        af._computation_graph.append(
            TracedOperation("b", pl.col("nonexistent"), metadata),
        )

        # Since ErrorBoundaryFinder isn't implemented yet, this should fall back to basic error handling
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            af.collect()


class TestBackwardCompatibility:
    """Test that existing functionality continues to work."""

    def test_setitem_without_tracing(self):
        """Test that __setitem__ works normally when tracing is disabled."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        af._tracing = False  # Explicitly disable

        af["c"] = af["a"] + af["b"]
        result = af.collect()

        assert "c" in result.columns
        assert result["c"].to_list() == [5, 7, 9]
        assert len(af._computation_graph) == 0  # No operations added to graph

    def test_setitem_with_tracing(self):
        """Test that __setitem__ adds to graph when tracing is enabled."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        af._tracing = True

        af["c"] = af["a"] + af["b"]

        # Should add to graph, not execute immediately
        assert len(af._computation_graph) == 1

        # Execute via collect
        result = af.collect()
        assert "c" in result.columns
        assert result["c"].to_list() == [5, 7, 9]

    def test_with_columns_mixed_formats(self):
        """Test that with_columns works with mixed graph formats."""
        af = ActuarialFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        af._tracing = True

        # Add some operations manually to create mixed format
        af._computation_graph.append(("c", pl.col("a") + pl.col("b")))

        # Use with_columns (should add TracedOperation if tracing is on)
        af = af.with_columns(pl.col("c").alias("d") * 2)

        result = af.collect()
        assert "c" in result.columns
        assert "d" in result.columns
        assert result["d"].to_list() == [10, 14, 18]

    def test_empty_frame_collect(self):
        """Test that collect() works on empty frame."""
        af = ActuarialFrame()
        result = af.collect()
        assert isinstance(result, pl.DataFrame)
        assert len(result.columns) == 0

    def test_empty_frame_profile(self):
        """Test that profile() works on empty frame."""
        af = ActuarialFrame()
        result_df, profile_df = af.profile()
        assert isinstance(result_df, pl.DataFrame)
        assert isinstance(profile_df, pl.DataFrame)
        assert len(result_df.columns) == 0


if __name__ == "__main__":
    pytest.main([__file__])
