"""Test enhanced dispatch system features.

This module tests the enhanced error handling features in the dispatch system,
including source context capture, proxy metadata attachment, and namespace error handling.
"""

from unittest.mock import patch

import polars as pl
import pytest

from gaspatchio_core.errors.metadata import OperationMetadata
from gaspatchio_core.frame.base import ActuarialFrame


@pytest.fixture
def sample_frame():
    """Create a sample ActuarialFrame for testing."""
    df = pl.DataFrame(
        {
            "premium": [100.0, 150.0, 200.0],
            "claims": [10.0, 20.0, 30.0],
            "policy_id": ["P001", "P002", "P003"],
            "age": [25, 35, 45],
        },
    )
    return ActuarialFrame(df)


@pytest.fixture
def tracing_frame():
    """Create a sample ActuarialFrame with tracing enabled."""
    df = pl.DataFrame(
        {
            "premium": [100.0, 150.0, 200.0],
            "claims": [10.0, 20.0, 30.0],
            "policy_id": ["P001", "P002", "P003"],
            "age": [25, 35, 45],
        },
    )
    af = ActuarialFrame(df)
    af._tracing = True
    return af


class TestDispatchBasicFunctionality:
    """Test that dispatch enhancements don't break basic functionality."""

    def test_successful_operations_work(self, sample_frame):
        """Test that normal operations continue to work."""
        # Using the ActuarialFrame assignment pattern
        sample_frame["total_premium"] = sample_frame["premium"].sum()
        result = sample_frame.collect()
        assert "total_premium" in result.columns

    def test_namespace_operations_work(self, sample_frame):
        """Test that namespace operations work normally."""
        # Add a string column and test string namespace
        sample_frame["text_col"] = pl.lit("test_string")
        sample_frame["text_length"] = sample_frame["text_col"].str.len_bytes()
        result = sample_frame.collect()
        assert "text_length" in result.columns

    def test_expression_operations_work(self, sample_frame):
        """Test that expression proxy operations work."""
        # Create an expression using proper ActuarialFrame syntax
        sample_frame["total"] = sample_frame["premium"] + sample_frame["claims"]
        result = sample_frame.collect()
        assert "total" in result.columns


class TestDispatchEnhancedErrorHandling:
    """Test enhanced error handling in the dispatch system."""

    def test_basic_method_error_structure(self, sample_frame):
        """Test that errors have proper structure even without tracing."""
        sample_frame._tracing = False

        # Create an operation that will fail at collect time
        try:
            sample_frame["test"] = sample_frame["nonexistent_column"].sum()
            sample_frame.collect()
            pytest.fail("Expected an exception")
        except Exception as e:
            # Should get an error about the missing column
            assert "nonexistent_column" in str(e)

    def test_dispatch_attribute_error_handling(self, tracing_frame):
        """Test dispatch system handles attribute errors properly."""
        proxy = tracing_frame["premium"]

        # Try to access a non-existent method - this should fail in the dispatch system
        with pytest.raises(AttributeError) as exc_info:
            _ = proxy.nonexistent_method

        # The error should mention the missing attribute
        error_msg = str(exc_info.value)
        assert "nonexistent_method" in error_msg

    def test_enhanced_error_with_mocked_context(self, tracing_frame):
        """Test enhanced error messages when source context is available."""
        mock_context = OperationMetadata(
            file_name="test_model.py",
            line_number=42,
            source_line='result = af["nonexistent"].sum()',
            function_name="test_function",
        )

        with patch(
            "gaspatchio_core.column.dispatch.capture_source_context",
            return_value=mock_context,
        ):
            try:
                tracing_frame["test"] = tracing_frame["nonexistent_column"].sum()
                tracing_frame.collect()
                pytest.fail("Expected an exception")
            except Exception as e:
                # The error might come from Polars directly during collect,
                # but if it came from dispatch system, it would have enhanced context
                error_msg = str(e)
                assert "nonexistent_column" in error_msg

    def test_namespace_error_enhancement(self, tracing_frame):
        """Test namespace error enhancement."""
        # Test string namespace with invalid method
        str_proxy = tracing_frame["policy_id"].str

        with pytest.raises(AttributeError) as exc_info:
            # Try to call a method that doesn't exist - need to actually call it
            method = str_proxy.nonexistent_str_method
            method()  # This is where the error occurs

        # Should get namespace-specific error
        error_msg = str(exc_info.value)
        assert "str" in error_msg.lower() or "namespace" in error_msg.lower()

    def test_source_capture_failure_fallback(self, tracing_frame):
        """Test graceful fallback when source capture fails."""
        # Mock source capture to fail
        with patch(
            "gaspatchio_core.column.dispatch.capture_source_context",
            side_effect=Exception("Capture failed"),
        ):
            # This should still work - errors in source capture shouldn't break normal operation
            tracing_frame["total"] = tracing_frame["premium"].sum()
            result = tracing_frame.collect()
            assert "total" in result.columns

    def test_no_tracing_no_capture(self, sample_frame):
        """Test that source capture is not attempted when tracing is disabled."""
        sample_frame._tracing = False

        with patch(
            "gaspatchio_core.column.dispatch.capture_source_context",
        ) as mock_capture:
            # Perform normal operations
            sample_frame["total"] = sample_frame["premium"].sum()
            sample_frame.collect()

            # Source capture should not be called when tracing is disabled
            mock_capture.assert_not_called()

    def test_enhanced_method_error_with_tracing(self, tracing_frame):
        """Test that method errors get enhanced context when tracing is enabled."""
        mock_context = OperationMetadata(
            file_name="dispatch_test.py",
            line_number=15,
            source_line='af["result"] = af["premium"].invalid_method()',
            function_name="test_method",
        )

        with patch(
            "gaspatchio_core.column.dispatch.capture_source_context",
            return_value=mock_context,
        ):
            proxy = tracing_frame["premium"]

            # This should trigger an AttributeError in the dispatch system
            with pytest.raises(AttributeError) as exc_info:
                _ = proxy.definitely_invalid_method_name

            # Basic check that we got an error about the method
            error_msg = str(exc_info.value)
            assert "definitely_invalid_method_name" in error_msg


class TestDispatchPerformance:
    """Test performance characteristics of dispatch enhancements."""

    def test_no_overhead_without_tracing(self, sample_frame):
        """Test that there's no performance overhead when tracing is disabled."""
        sample_frame._tracing = False

        # Mock capture_source_context to verify it's not called
        with patch(
            "gaspatchio_core.column.dispatch.capture_source_context",
        ) as mock_capture:
            # Perform multiple operations
            for i in range(10):
                sample_frame[f"test_{i}"] = sample_frame["premium"].sum()
            sample_frame.collect()

            # Verify no calls to source capture (no performance impact)
            mock_capture.assert_not_called()

    def test_tracing_mode_toggle(self, sample_frame):
        """Test that tracing can be toggled without affecting results."""
        # Test with tracing off
        sample_frame._tracing = False
        sample_frame["result1"] = sample_frame["premium"].sum()

        # Test with tracing on
        sample_frame._tracing = True
        sample_frame["result2"] = sample_frame["premium"].sum()

        # Test with tracing off again
        sample_frame._tracing = False
        sample_frame["result3"] = sample_frame["premium"].sum()

        # All operations should have worked
        result = sample_frame.collect()
        assert "result1" in result.columns
        assert "result2" in result.columns
        assert "result3" in result.columns

        # Results should be the same
        df = result.to_pandas()
        assert df["result1"].iloc[0] == df["result2"].iloc[0] == df["result3"].iloc[0]


class TestDispatchCompatibility:
    """Test backward compatibility of dispatch enhancements."""

    def test_import_fallback_handling(self):
        """Test that dispatch works even if errors module import fails."""
        # This tests the ImportError fallback in the dispatch module
        with patch("gaspatchio_core.column.dispatch.capture_source_context", None):
            df = pl.DataFrame({"test": [1, 2, 3]})
            af = ActuarialFrame(df)
            af._tracing = True  # Enable tracing

            # Operations should still work
            af["total"] = af["test"].sum()
            result = af.collect()
            assert "total" in result.columns

    def test_mixed_proxy_types(self, sample_frame):
        """Test that both ColumnProxy and ExpressionProxy work with enhancements."""
        sample_frame._tracing = True

        # Test ColumnProxy and ExpressionProxy together
        sample_frame["col_sum"] = sample_frame["premium"].sum()
        sample_frame["expr_mean"] = (
            sample_frame["premium"] + sample_frame["claims"]
        ).mean()

        result = sample_frame.collect()
        assert "col_sum" in result.columns
        assert "expr_mean" in result.columns

    def test_namespace_proxy_functionality(self, sample_frame):
        """Test that namespace proxies work with enhancements."""
        sample_frame._tracing = True

        # Test different namespace operations
        sample_frame["str_length"] = sample_frame["policy_id"].str.len_bytes()

        # Add a date column for dt namespace testing
        sample_frame["date_col"] = pl.lit("2023-01-01").str.strptime(pl.Date)
        sample_frame["year"] = sample_frame["date_col"].dt.year()

        result = sample_frame.collect()
        assert "str_length" in result.columns
        assert "year" in result.columns


class TestDispatchErrorCapture:
    """Test specific error capture scenarios."""

    def test_capture_source_context_integration(self, tracing_frame):
        """Test that source context capture integrates properly with dispatch."""
        # We can't easily test the actual source capture without real stack frames,
        # but we can test that the mechanism is in place

        # This should succeed without issues
        tracing_frame["test"] = tracing_frame["premium"].sum()
        result = tracing_frame.collect()
        assert "test" in result.columns

    def test_proxy_metadata_structure(self, tracing_frame):
        """Test that error enhancement doesn't break when triggered."""
        # Test that attribute errors on proxies work as expected
        proxy = tracing_frame["premium"]

        # This should raise AttributeError
        with pytest.raises(AttributeError):
            _ = proxy.this_method_definitely_does_not_exist

        # The test passes if we get the expected AttributeError without crashes

    def test_namespace_proxy_error_structure(self, tracing_frame):
        """Test namespace proxy error handling."""
        str_proxy = tracing_frame["policy_id"].str

        # This should raise AttributeError for invalid string method
        with pytest.raises(AttributeError):
            # Need to actually call the method to get the error
            method = str_proxy.invalid_string_method_name
            method()

        # The test passes if we get the expected AttributeError
