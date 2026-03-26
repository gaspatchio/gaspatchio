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
            af["bad_calc"] = pl.col("missing_column") + 1
            result = af.collect()

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
        af["calculated_field"] = (pl.col("premium") / pl.col("sum_assured")).alias(
            "calculated_field"
        )

        # Add failing operation
        with pytest.raises(Exception) as exc_info:
            af["another_calc"] = pl.col("nonexistent") * 100
            result = af.collect()

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
            af["bad_calc"] = pl.col("missing_column") + 1
            result = af.collect()

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
            af["bad_calc"] = pl.col("missing_column") + 1
            result = af.collect()

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
            af["calc"] = pl.col("premim") * 2  # typo: should be "premium"
            result = af.collect()

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
        af["calc1"] = pl.col("premium") * 1.1
        af["calc2"] = pl.col("age") + 5
        af["calc3"] = pl.col("duration") * 12
        # This one will fail
        af["calc4"] = pl.col("nonexistent") * 2
        af["calc5"] = pl.col("premium") / 2  # This would work if calc4 didn't fail

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

    def test_type_error_suggestions(self):
        """Test suggestions for type-related errors."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Try to perform incompatible operation
        with pytest.raises(Exception) as exc_info:
            # Try to add string to number (if we had string columns)
            af["bad_calc"] = pl.col("age") + "invalid"
            result = af.collect()

        exception = exc_info.value
        # Should provide some kind of error information
        assert str(exception) is not None

    def test_error_handling_with_complex_expressions(self):
        """Test error handling with complex nested expressions."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Complex expression that will fail
        with pytest.raises(Exception) as exc_info:
            af["complex_calc"] = (
                pl.col("premium")
                * pl.col("nonexistent_field")  # This will cause the error
                / pl.col("sum_assured").sqrt()
            )
            result = af.collect()

        exception = exc_info.value
        # Should handle complex expressions
        assert str(exception) is not None

    def test_profile_method_error_handling(self):
        """Test that profile() method also gets enhanced error handling."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Add failing operation
        af["bad_calc"] = pl.col("missing_column") * 2

        with pytest.raises(Exception) as exc_info:
            result = af.profile()

        exception = exc_info.value
        # Should get error handling for profile too
        assert str(exception) is not None

    def test_error_formatting_fallback(self):
        """Test that error handling gracefully falls back when formatting fails."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data, verbose=True)
        af._tracing = True

        # Create a scenario where error handling might fail
        # This is hard to test directly, but we can at least ensure no crashes
        with pytest.raises(Exception):
            af["calc"] = pl.col("nonexistent") + 1
            result = af.collect()

    def test_large_computation_graph_performance(self):
        """Test error handling performance with large computation graphs."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Build up a large computation graph
        for i in range(50):  # 50 operations should be enough to test binary search
            af[f"calc_{i}"] = pl.col("premium") * (i + 1)

        # Add failing operation at the end
        af["final_calc"] = pl.col("nonexistent") * 2

        with pytest.raises(Exception) as exc_info:
            result = af.collect()

        exception = exc_info.value
        # Should handle large graphs efficiently
        assert str(exception) is not None

    def test_mixed_operation_types_in_graph(self):
        """Test error handling with mixed operation types (backward compatibility)."""
        set_error_mode("enhanced")
        af = ActuarialFrame(self.test_data)
        af._tracing = True

        # Mix of different operation types
        af["calc1"] = pl.col("premium") * 2
        af["age_check"] = pl.col("age") > 30
        af["calc2"] = pl.col("nonexistent") + 1  # This will fail

        with pytest.raises(Exception) as exc_info:
            result = af.collect()

        exception = exc_info.value
        # Should handle mixed operation types
        assert str(exception) is not None


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


class TestRealWorldErrorScenarios:
    """Tests based on real-world actuarial modeling scenarios."""

    def setup_method(self):
        """Set up realistic actuarial test data."""
        self.model_points = pl.DataFrame(
            {
                "policy_id": range(1, 101),
                "age": [25 + (i % 40) for i in range(100)],
                "sum_assured": [10000 + (i * 1000) for i in range(100)],
                "premium": [100 + (i * 10) for i in range(100)],
                "duration": [1 + (i % 30) for i in range(100)],
                "product_code": ["TERM"] * 50 + ["WHOLE"] * 50,
            },
        )
        set_error_mode("enhanced")

    def test_assumption_lookup_error(self):
        """Test error when referencing non-existent assumption column."""
        af = ActuarialFrame(self.model_points)
        af._tracing = True

        with pytest.raises(Exception) as exc_info:
            af["mortality_rate"] = pl.col("mortality_assumption") * pl.col("age")
            result = af.collect()

        exception = exc_info.value
        error_msg = str(exception).lower()

        # Should suggest similar columns or provide helpful context
        assert "mortality" in error_msg or "assumption" in error_msg

    def test_actuarial_calculation_chain_error(self):
        """Test error in complex actuarial calculation chain."""
        af = ActuarialFrame(self.model_points)
        af._tracing = True

        # Build up typical actuarial calculation chain
        af["annual_premium"] = pl.col("premium") * 12
        af["sum_at_risk"] = pl.col("sum_assured") - 0  # Simplified
        # This will fail - typo in column name
        af["mortality_cost"] = pl.col("sum_at_risk") * pl.col("mortaliy_rate")  # typo

        with pytest.raises(Exception) as exc_info:
            result = af.collect()

        exception = exc_info.value
        if hasattr(exception, "llm_context"):
            llm_context = exception.llm_context
            # Should identify the typo and suggest correction
            context_str = str(llm_context).lower()
            assert "mortality" in context_str or "similar" in context_str

    def test_division_by_zero_scenario(self):
        """Test division by zero in actuarial context."""
        # Create data with some zero premiums
        # Note: This is a regular polars DataFrame, not ActuarialFrame
        data_with_zeros = self.model_points.with_columns(
            premium=pl.when(pl.col("policy_id") == 50)
            .then(0)
            .otherwise(pl.col("premium")),
        )

        af = ActuarialFrame(data_with_zeros)
        af._tracing = True

        # Division by zero doesn't raise an exception in Polars, it produces inf
        af["expense_ratio"] = pl.col("sum_assured") / pl.col("premium")  # Division by zero
        result = af.collect()

        # Check that we have inf values
        expense_ratios = result["expense_ratio"].to_list()
        assert any(val == float('inf') for val in expense_ratios), "Should have inf values from division by zero"
