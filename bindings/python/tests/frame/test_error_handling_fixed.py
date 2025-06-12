"""
Integration tests for enhanced error handling in ActuarialFrame.

Tests the complete error handling pipeline including:
- Metadata capture during operations
- Binary search for failing operations
- Error suggestions and formatting
- Feature flag behavior
- End-to-end error flow
"""

import os
from unittest.mock import patch

import polars as pl
import pytest

from gaspatchio_core.frame import ActuarialFrame
from gaspatchio_core.util import get_error_mode, set_error_mode


class TestErrorHandlingIntegration:
    """Integration tests for the complete error handling system."""

    def setup_method(self):
        """Set up test data for each test."""
        # Create test data
        self.test_data = pl.DataFrame(
            {
                "policy_id": [1, 2, 3, 4, 5],
                "premium": [100.0, 200.0, 300.0, 400.0, 500.0],
                "sum_assured": [10000.0, 20000.0, 30000.0, 40000.0, 50000.0],
                "age": [25, 35, 45, 55, 65],
                "duration": [1, 2, 3, 4, 5],
            },
        )

        # Reset error mode to default
        set_error_mode("basic")

    def test_enhanced_error_mode_end_to_end(self):
        """Test complete enhanced error handling flow."""
        # Set enhanced error mode
        set_error_mode("enhanced")

        # Create ActuarialFrame with tracing enabled
        af = ActuarialFrame(self.test_data, verbose=True)
        af._tracing = True

        # Add some valid operations first
        af["premium_adjusted"] = af["premium"] * 1.1
        af["age_group"] = af["age"] // 10

        # Now add a failing operation (column doesn't exist)
        with pytest.raises(Exception) as exc_info:
            af["invalid_calc"] = af["nonexistent_column"] * 2
            result = af.collect()

        # Verify enhanced error information is present
        exception = exc_info.value
        assert hasattr(exception, "llm_context"), (
            "Enhanced exception should have LLM context"
        )

        # Check LLM context structure
        llm_context = exception.llm_context
        assert isinstance(llm_context, dict), "LLM context should be a dictionary"
        assert "error_type" in llm_context
        assert "suggestions" in llm_context
        # Context info is flattened in llm_context
        assert "available_columns" in llm_context
        assert "dataframe_shape" in llm_context

    def test_debug_mode_error_handling(self):
        """Test error handling when frame is in debug mode."""
        # Create ActuarialFrame in debug mode
        af = ActuarialFrame(self.test_data, mode="debug", verbose=True)

        # Set basic error mode but frame should still get enhanced handling due to debug mode
        set_error_mode("basic")

        # Add failing operation
        with pytest.raises(Exception) as exc_info:
            result = af.with_columns(
                (pl.col("missing_column") + 1).alias("bad_calc"),
            ).collect()

        # Should still get enhanced error due to debug mode
        exception = exc_info.value
        error_msg = str(exception)

        # Basic check that error contains useful information
        assert len(error_msg) > 50, "Error message should be detailed in debug mode"

    def test_tracing_mode_error_handling(self):
        """Test error handling when tracing is enabled."""
        # Create ActuarialFrame with tracing enabled
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Add operations to build up the computation graph
        af = af.with_columns(
            (pl.col("premium") / pl.col("sum_assured")).alias("calculated_field"),
        ).select("policy_id", "calculated_field")

        # Add failing operation
        with pytest.raises(Exception) as exc_info:
            result = af.with_columns(
                (pl.col("nonexistent") * 100).alias("another_calc"),
            ).collect()

        # Error should be caught and handled
        exception = exc_info.value
        assert exception is not None

    def test_production_mode_fast_path(self):
        """Test that production mode uses fast path without overhead."""
        # Set basic error mode and no tracing/debug
        set_error_mode("basic")
        af = ActuarialFrame(self.test_data, mode="optimize")
        af._tracing = False

        # Add failing operation
        with pytest.raises(Exception) as exc_info:
            result = af.with_columns(
                (pl.col("missing_column") + 1).alias("bad_calc"),
            ).collect()

        # Should get basic error without enhancement
        exception = exc_info.value
        assert not hasattr(exception, "llm_context"), (
            "Basic mode should not add LLM context"
        )

    def test_error_mode_off_disables_enhancement(self):
        """Test that 'off' error mode completely disables enhancement."""
        set_error_mode("off")

        # Even with tracing enabled, should not enhance errors
        af = ActuarialFrame(self.test_data, verbose=True)
        af._tracing = True

        with pytest.raises(Exception) as exc_info:
            result = af.with_columns(
                (pl.col("missing_column") + 1).alias("bad_calc"),
            ).collect()

        exception = exc_info.value
        assert not hasattr(exception, "llm_context"), (
            "'off' mode should disable all enhancement"
        )

    def test_column_not_found_suggestions(self):
        """Test that column not found errors provide helpful suggestions."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Try to use a column with a typo
        with pytest.raises(Exception) as exc_info:
            result = af.with_columns(
                (pl.col("premim") * 2).alias("calc"),  # typo: should be "premium"
            ).collect()

        exception = exc_info.value
        error_msg = str(exception).lower()

        # Should suggest the correct column name
        assert "premium" in error_msg or "similar" in error_msg

    def test_multiple_operations_error_boundary(self):
        """Test that binary search correctly identifies failing operation."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data, verbose=True)
        af._tracing = True

        # Add multiple valid operations
        af = (
            af.with_columns((pl.col("premium") * 1.1).alias("calc1"))
            .with_columns((pl.col("age") + 5).alias("calc2"))
            .with_columns((pl.col("duration") * 12).alias("calc3"))
            # This one will fail
            .with_columns((pl.col("nonexistent") * 2).alias("calc4"))
            .with_columns(
                (pl.col("premium") / 2).alias("calc5"),
            )  # This would work if calc4 didn't fail
        )

        with pytest.raises(Exception) as exc_info:
            result = af.collect()

        exception = exc_info.value
        if hasattr(exception, "llm_context"):
            llm_context = exception.llm_context
            # Should identify that the error is in the calc4 operation
            assert "nonexistent" in str(llm_context).lower()

    def test_environment_variable_configuration(self):
        """Test that AF_ERROR_MODE environment variable works."""
        # Test with environment variable
        with patch.dict(os.environ, {"AF_ERROR_MODE": "enhanced"}):
            # The runtime setting takes precedence over env var
            set_error_mode("basic")

            mode = get_error_mode()
            # Runtime setting should win
            assert mode == "basic", "Runtime setting should take precedence"


class TestErrorModeConfiguration:
    """Tests for error mode configuration and feature flags."""

    def setup_method(self):
        """Reset configuration before each test."""
        set_error_mode("basic")

    def test_set_get_error_mode(self):
        """Test setting and getting error modes."""
        # Test all valid modes
        valid_modes = ["basic", "enhanced", "debug", "off"]

        for mode in valid_modes:
            set_error_mode(mode)
            assert get_error_mode() == mode

    def test_invalid_error_mode_raises_error(self):
        """Test that invalid error modes raise ValueError."""
        with pytest.raises(ValueError):
            set_error_mode("invalid_mode")

    def test_environment_variable_override(self):
        """Test that environment variables work correctly."""
        with patch.dict(os.environ, {"AF_ERROR_MODE": "debug"}):
            # Even after setting runtime mode, env var should take precedence
            mode = get_error_mode()
            assert mode == "debug"

    def test_case_insensitive_environment_variable(self):
        """Test that environment variables are case insensitive."""
        with patch.dict(os.environ, {"AF_ERROR_MODE": "ENHANCED"}):
            mode = get_error_mode()
            assert mode == "enhanced"  # Should be normalized to lowercase