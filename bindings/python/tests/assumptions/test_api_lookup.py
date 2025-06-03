"""
Tests for assumption lookup validation functionality.

This module tests the enhanced assumption_lookup function with comprehensive
validation capabilities, including table existence validation, key validation,
and error handling scenarios.
"""

from unittest.mock import Mock, patch

import polars as pl
import pytest
from gaspatchio_core.assumptions.api import (
    _validate_lookup_parameters,
    _validate_table_exists,
    _validate_table_keys,
    assumption_lookup,
    load_assumptions,
)


class TestAssumptionLookupValidation:
    """Test suite for assumption lookup validation functionality."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Clear any existing tables to ensure test isolation
        try:
            from gaspatchio_core._internal import PyAssumptionTableRegistry
            from gaspatchio_core.assumptions._config import _clear_table_configs

            registry = PyAssumptionTableRegistry()
            registry.reset()  # Clear the Rust registry
            _clear_table_configs()  # Clear the Python configuration storage
        except Exception:
            # If reset fails, we'll just have to live with potential conflicts
            pass

    def test_basic_lookup_with_validation_enabled(self):
        """Test that lookup with validation enabled works correctly."""
        # Load a test table
        test_data = pl.DataFrame({"age": [30, 31, 32], "qx": [0.001, 0.0011, 0.0012]})
        load_assumptions("test_table", test_data, value="qx")

        # Test basic lookup - should not raise an error
        # Note: This will currently return a placeholder expression
        expr = assumption_lookup("age", table_name="test_table", validate=True)
        assert expr is not None
        assert isinstance(expr, pl.Expr)

    def test_lookup_with_validation_disabled(self):
        """Test that lookup with validation disabled works correctly."""
        # Test lookup without any table loaded - should work when validation disabled
        expr = assumption_lookup(
            "any_key", table_name="nonexistent_table", validate=False
        )
        assert expr is not None
        assert isinstance(expr, pl.Expr)

    def test_table_not_found_error(self):
        """Test validation error when table doesn't exist."""
        with pytest.raises(
            ValueError, match="Assumption table 'missing_table' not found"
        ):
            assumption_lookup("age", table_name="missing_table", validate=True)

    def test_table_not_found_helpful_error_message(self):
        """Test that table not found error provides helpful suggestions."""
        # Load a table so we have available tables to suggest
        test_data = pl.DataFrame({"age": [30], "qx": [0.001]})
        load_assumptions("available_table", test_data)

        with pytest.raises(ValueError) as exc_info:
            assumption_lookup("age", table_name="missing_table", validate=True)

        error_message = str(exc_info.value)
        assert "missing_table" in error_message
        assert "Available tables:" in error_message
        assert "available_table" in error_message
        assert "Suggestion:" in error_message

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_key_count_mismatch_error(self, mock_registry_class):
        """Test validation error when key count doesn't match table schema."""
        # Mock the registry and table to simulate Rust metadata methods
        mock_registry = Mock()
        mock_table = Mock()
        mock_table.get_key_count.return_value = 3
        mock_table.get_key_columns.return_value = ["sex", "smoking", "age"]
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        with pytest.raises(ValueError) as exc_info:
            assumption_lookup("age", table_name="multi_key_table", validate=True)

        error_message = str(exc_info.value)
        assert "Key count mismatch" in error_message
        assert "Expected 3 keys" in error_message
        assert "got 1" in error_message
        assert "sex" in error_message
        assert "smoking" in error_message
        assert "age" in error_message

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_key_name_mismatch_error(self, mock_registry_class):
        """Test validation error when key names don't match table schema."""
        # Mock the registry and table
        mock_registry = Mock()
        mock_table = Mock()
        mock_table.get_key_count.return_value = 2
        mock_table.get_key_columns.return_value = ["issue_age", "duration"]
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        with pytest.raises(ValueError) as exc_info:
            assumption_lookup("age", "year", table_name="test_table", validate=True)

        error_message = str(exc_info.value)
        assert "Key name mismatch at position 0" in error_message
        assert "Expected 'issue_age', got 'age'" in error_message
        assert "Full expected order: ['issue_age', 'duration']" in error_message

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_rust_metadata_methods_not_implemented(self, mock_registry_class):
        """Test graceful handling when Rust metadata methods aren't implemented yet."""
        # Mock the registry and table without metadata methods
        mock_registry = Mock()
        mock_table = Mock()
        # Remove the metadata methods to simulate them not being implemented
        del mock_table.get_key_count
        del mock_table.get_key_columns
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        # This should not raise an error, just log a warning and skip validation
        expr = assumption_lookup("age", table_name="test_table", validate=True)
        assert expr is not None

    def test_complex_expression_validation_error(self):
        """Test that complex expressions that can't be validated raise appropriate errors."""
        # Load a test table first
        test_data = pl.DataFrame({"age": [30], "qx": [0.001]})
        load_assumptions("test_table", test_data)

        # Create a complex expression that can't be easily validated
        complex_expr = pl.col("age") + pl.col("offset")

        with pytest.raises(ValueError) as exc_info:
            assumption_lookup(complex_expr, table_name="test_table", validate=True)

        error_message = str(exc_info.value)
        assert "Cannot validate complex expression" in error_message
        assert "Use simple column names or set validate=False" in error_message

    def test_complex_expression_with_validation_disabled(self):
        """Test that complex expressions work when validation is disabled."""
        # Create a complex expression
        complex_expr = pl.col("age") + pl.col("offset")

        # Should work fine with validation disabled
        expr = assumption_lookup(complex_expr, table_name="any_table", validate=False)
        assert expr is not None

    def test_multi_key_validation_success(self):
        """Test successful validation with multiple keys."""
        # Load a multi-key table
        test_data = pl.DataFrame(
            {"sex": ["M", "F"], "age": [30, 30], "qx": [0.001, 0.0008]}
        )
        load_assumptions("multi_key_table", test_data, id=["sex", "age"])

        # This should work without raising an error
        expr = assumption_lookup(
            "sex", "age", table_name="multi_key_table", validate=True
        )
        assert expr is not None

    def test_empty_key_validation_error(self):
        """Test validation error with empty or None keys."""
        test_data = pl.DataFrame({"age": [30], "qx": [0.001]})
        load_assumptions("test_table", test_data)

        with pytest.raises(ValueError) as exc_info:
            assumption_lookup(None, table_name="test_table", validate=True)

        error_message = str(exc_info.value)
        assert "Cannot validate expression" in error_message

    def test_mixed_key_types(self):
        """Test validation with mixed key types (strings and expressions)."""
        test_data = pl.DataFrame(
            {"sex": ["M", "F"], "age": [30, 30], "qx": [0.001, 0.0008]}
        )
        load_assumptions("mixed_key_table", test_data, id=["sex", "age"])

        # Mix string and simple column expression
        expr = assumption_lookup(
            "sex", pl.col("age"), table_name="mixed_key_table", validate=True
        )
        assert expr is not None


class TestLookupValidationHelpers:
    """Test suite for lookup validation helper functions."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Clear any existing tables to ensure test isolation
        try:
            from gaspatchio_core._internal import PyAssumptionTableRegistry
            from gaspatchio_core.assumptions._config import _clear_table_configs

            registry = PyAssumptionTableRegistry()
            registry.reset()  # Clear the Rust registry
            _clear_table_configs()  # Clear the Python configuration storage
        except Exception:
            # If reset fails, we'll just have to live with potential conflicts
            pass

    def test_validate_table_exists_success(self):
        """Test successful table existence validation."""
        test_data = pl.DataFrame({"age": [30], "qx": [0.001]})
        load_assumptions("existing_table", test_data)

        # Should not raise an error
        _validate_table_exists("existing_table")

    def test_validate_table_exists_failure(self):
        """Test table existence validation failure."""
        with pytest.raises(
            ValueError, match="Assumption table 'nonexistent' not found"
        ):
            _validate_table_exists("nonexistent")

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_validate_table_keys_success(self, mock_registry_class):
        """Test successful table key validation."""
        mock_registry = Mock()
        mock_table = Mock()
        mock_table.get_key_count.return_value = 2
        mock_table.get_key_columns.return_value = ["age", "duration"]
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        # Should not raise an error
        _validate_table_keys("test_table", ["age", "duration"])

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_validate_table_keys_count_mismatch(self, mock_registry_class):
        """Test table key validation with count mismatch."""
        mock_registry = Mock()
        mock_table = Mock()
        mock_table.get_key_count.return_value = 2
        mock_table.get_key_columns.return_value = ["age", "duration"]
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        with pytest.raises(ValueError, match="Key count mismatch"):
            _validate_table_keys("test_table", ["age"])

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_validate_table_keys_name_mismatch(self, mock_registry_class):
        """Test table key validation with name mismatch."""
        mock_registry = Mock()
        mock_table = Mock()
        mock_table.get_key_count.return_value = 2
        mock_table.get_key_columns.return_value = ["age", "duration"]
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        with pytest.raises(ValueError, match="Key name mismatch at position 1"):
            _validate_table_keys("test_table", ["age", "year"])

    def test_validate_lookup_parameters_integration(self):
        """Test the complete lookup parameter validation flow."""
        test_data = pl.DataFrame(
            {"sex": ["M", "F"], "age": [30, 30], "qx": [0.001, 0.0008]}
        )
        load_assumptions("integration_table", test_data, id=["sex", "age"])

        # Should work without raising an error
        keys = ("sex", "age")
        _validate_lookup_parameters(keys, "integration_table")


class TestLookupErrorMessages:
    """Test suite for lookup error message quality and helpfulness."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Clear any existing tables to ensure test isolation
        try:
            from gaspatchio_core._internal import PyAssumptionTableRegistry
            from gaspatchio_core.assumptions._config import _clear_table_configs

            registry = PyAssumptionTableRegistry()
            registry.reset()  # Clear the Rust registry
            _clear_table_configs()  # Clear the Python configuration storage
        except Exception:
            # If reset fails, we'll just have to live with potential conflicts
            pass

    def test_error_messages_contain_suggestions(self):
        """Test that error messages contain helpful suggestions."""
        with pytest.raises(ValueError) as exc_info:
            assumption_lookup("age", table_name="missing_table", validate=True)

        error_message = str(exc_info.value)
        assert "Suggestion:" in error_message
        assert "load_assumptions()" in error_message

    @patch("gaspatchio_core.assumptions.api.PyAssumptionTableRegistry")
    def test_key_mismatch_error_messages_are_actionable(self, mock_registry_class):
        """Test that key mismatch error messages provide actionable guidance."""
        mock_registry = Mock()
        mock_table = Mock()
        mock_table.get_key_count.return_value = 3
        mock_table.get_key_columns.return_value = ["sex", "smoking", "age"]
        mock_registry.get_table.return_value = mock_table
        mock_registry_class.return_value = mock_registry

        with pytest.raises(ValueError) as exc_info:
            assumption_lookup("age", "sex", table_name="test_table", validate=True)

        error_message = str(exc_info.value)
        assert "Expected 3 keys" in error_message
        assert "got 2" in error_message
        assert "Suggestion:" in error_message
        assert "exactly 3 lookup keys" in error_message

    def test_backward_compatibility_note(self):
        """Test that validation works without breaking existing patterns."""
        # Test that the function signature is backward compatible
        # (accepting variable arguments and table_name)

        # Should be able to call with just table_name
        expr = assumption_lookup("age", table_name="any_table", validate=False)
        assert expr is not None

        # Should be able to call with multiple keys
        expr = assumption_lookup(
            "key1", "key2", "key3", table_name="any_table", validate=False
        )
        assert expr is not None


class TestPerformanceValidationToggle:
    """Test suite for validation performance characteristics."""

    def setup_method(self):
        """Set up test fixtures before each test method."""
        # Clear any existing tables to ensure test isolation
        try:
            from gaspatchio_core._internal import PyAssumptionTableRegistry
            from gaspatchio_core.assumptions._config import _clear_table_configs

            registry = PyAssumptionTableRegistry()
            registry.reset()  # Clear the Rust registry
            _clear_table_configs()  # Clear the Python configuration storage
        except Exception:
            # If reset fails, we'll just have to live with potential conflicts
            pass

    def test_validation_disabled_skips_checks(self):
        """Test that disabling validation actually skips validation logic."""
        # This should work even with invalid table name when validation is disabled
        expr = assumption_lookup(
            "any_key", table_name="definitely_not_a_table", validate=False
        )
        assert expr is not None

    def test_validation_enabled_performs_checks(self):
        """Test that enabling validation actually performs checks."""
        # This should fail when validation is enabled and table doesn't exist
        with pytest.raises(ValueError):
            assumption_lookup(
                "any_key", table_name="definitely_not_a_table", validate=True
            )

    @patch("gaspatchio_core.assumptions.api.logger")
    def test_validation_logging_behavior(self, mock_logger):
        """Test that validation logging works as expected."""
        # Test with validation enabled
        try:
            assumption_lookup("key", table_name="table", validate=True)
        except ValueError:
            pass  # Expected to fail

        # Check that debug logging occurred for validation
        assert any(
            "Validating lookup" in str(call)
            for call in mock_logger.debug.call_args_list
        )

        mock_logger.reset_mock()

        # Test with validation disabled
        assumption_lookup("key", table_name="table", validate=False)

        # Check that debug logging occurred for unvalidated lookup
        assert any(
            "unvalidated lookup" in str(call)
            for call in mock_logger.debug.call_args_list
        )
