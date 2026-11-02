# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Test enhanced dispatch system features.

This module tests that the dispatch system keeps working while the enhanced
error handling is in place: normal operations, namespace proxying, and the
shape of the errors raised for an attribute no proxy has.

Where the enrichment reports a failing call **from** is pinned end to end in
``tests/errors/test_method_error_enrichment.py`` -- against a real failure on
the path ``ErrorEnhancer`` actually wraps, since the enrichment resolves a
live call stack and nothing that stands in for one can prove anything about
it.
"""

import polars as pl
import pytest

from gaspatchio.frame.base import ActuarialFrame


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
    af._traced_run = True
    return af


class TestDispatchBasicFunctionality:
    """Test that dispatch enhancements don't break basic functionality."""

    def test_successful_operations_work(self, sample_frame):
        """Test that normal operations continue to work."""
        # Using the ActuarialFrame assignment pattern
        sample_frame["total_premium"] = sample_frame["premium"].polars_native().sum()
        result = sample_frame.collect()
        assert "total_premium" in result.columns

    def test_namespace_operations_work(self, sample_frame):
        """Test that namespace operations work normally."""
        # Add a string column and test string namespace
        sample_frame["text_col"] = pl.lit("test_string")
        sample_frame["text_length"] = (
            sample_frame["text_col"].polars_native().str.len_bytes()
        )
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
        sample_frame._traced_run = False

        # Create an operation that will fail at collect time
        try:
            sample_frame["test"] = (
                sample_frame["nonexistent_column"].polars_native().sum()
            )
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


class TestDispatchPerformance:
    """Test performance characteristics of dispatch enhancements."""

    def test_tracing_mode_toggle(self, sample_frame):
        """Test that tracing can be toggled without affecting results."""
        # Test with tracing off
        sample_frame._traced_run = False
        sample_frame["result1"] = sample_frame["premium"].polars_native().sum()

        # Test with tracing on
        sample_frame._traced_run = True
        sample_frame["result2"] = sample_frame["premium"].polars_native().sum()

        # Test with tracing off again
        sample_frame._traced_run = False
        sample_frame["result3"] = sample_frame["premium"].polars_native().sum()

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

    def test_mixed_proxy_types(self, sample_frame):
        """Test that both ColumnProxy and ExpressionProxy work with enhancements."""
        sample_frame._traced_run = True

        # Test ColumnProxy and ExpressionProxy together
        sample_frame["col_sum"] = sample_frame["premium"].polars_native().sum()
        sample_frame["expr_mean"] = (
            (sample_frame["premium"] + sample_frame["claims"]).polars_native().mean()
        )

        result = sample_frame.collect()
        assert "col_sum" in result.columns
        assert "expr_mean" in result.columns

    def test_namespace_proxy_functionality(self, sample_frame):
        """Test that namespace proxies work with enhancements."""
        sample_frame._traced_run = True

        # Test different namespace operations
        sample_frame["str_length"] = (
            sample_frame["policy_id"].polars_native().str.len_bytes()
        )

        # Add a date column for dt namespace testing
        sample_frame["date_col"] = pl.lit("2023-01-01").str.strptime(pl.Date)
        sample_frame["year"] = sample_frame["date_col"].polars_native().dt.year()

        result = sample_frame.collect()
        assert "str_length" in result.columns
        assert "year" in result.columns


class TestDispatchErrorCapture:
    """Test specific error capture scenarios."""

    def test_a_traced_run_leaves_a_successful_operation_alone(self, tracing_frame):
        """The enrichment sits on the error path only -- success is untouched."""
        tracing_frame["test"] = tracing_frame["premium"].polars_native().sum()
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
