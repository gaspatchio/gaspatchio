"""
Unit tests for the assumptions validation module.

Tests cover parameter validation, compatibility checking, and error handling
for assumption table append operations.
"""

import pytest
from gaspatchio_core.assumptions._config import (
    _clear_table_configs,
    _store_table_config,
)
from gaspatchio_core.assumptions._validation import (
    _validate_additional_keys,
    _validate_append_compatibility,
    _validate_configuration_completeness,
    _validate_parameter_types,
    _validate_table_exists_for_append,
)


class TestValidateAdditionalKeys:
    """Test additional_keys parameter validation."""

    def test_none_additional_keys(self):
        """Test that None additional_keys is valid."""
        _validate_additional_keys(None)  # Should not raise

    def test_empty_dict_additional_keys(self):
        """Test that empty dictionary is valid."""
        _validate_additional_keys({})  # Should not raise

    def test_valid_additional_keys(self):
        """Test valid additional_keys formats."""
        valid_keys = [
            {"sex": "M"},
            {"sex": "F", "smoking": "NS"},
            {"region": "US", "product": "Term", "version": 1},
            {"key_with_underscores": "value", "key-with-dashes": "value"},
        ]

        for keys in valid_keys:
            _validate_additional_keys(keys)  # Should not raise

    def test_non_dict_additional_keys(self):
        """Test that non-dictionary additional_keys raise errors."""
        invalid_keys = [
            "string",
            ["list"],
            123,
            ("tuple",),
            {"set"},
        ]

        for keys in invalid_keys:
            with pytest.raises(
                ValueError, match="additional_keys must be a dictionary"
            ):
                _validate_additional_keys(keys)

    def test_non_string_keys(self):
        """Test that non-string keys raise errors."""
        invalid_keys = [
            {123: "value"},
            {("tuple", "key"): "value"},
            {None: "value"},
            {1.5: "value"},
        ]

        for keys in invalid_keys:
            with pytest.raises(
                ValueError, match="All additional_keys must have string keys"
            ):
                _validate_additional_keys(keys)

    def test_empty_string_keys(self):
        """Test that empty or whitespace-only keys raise errors."""
        invalid_keys = [
            {"": "value"},
            {" ": "value"},
            {"\t": "value"},
            {"\n": "value"},
            {"  \t\n  ": "value"},
        ]

        for keys in invalid_keys:
            with pytest.raises(ValueError, match="non-empty string keys"):
                _validate_additional_keys(keys)

    def test_mixed_valid_invalid_keys(self):
        """Test that validation fails if any key is invalid."""
        with pytest.raises(ValueError, match="non-empty string keys"):
            _validate_additional_keys({"valid": "value", "": "invalid"})

        with pytest.raises(ValueError, match="string keys"):
            _validate_additional_keys({"valid": "value", 123: "invalid"})


class TestValidateAppendCompatibility:
    """Test append compatibility validation."""

    def test_identical_configs(self):
        """Test that identical configurations are compatible."""
        config = {
            "value": "rate",
            "overflow": "Ult.",
            "max_overflow": 200,
            "additional_keys": {"sex": "M", "smoking": "NS"},
        }

        with pytest.raises(ValueError, match="identical additional_keys values"):
            _validate_append_compatibility(config, config)

    def test_compatible_configs_different_additional_keys(self):
        """Test that configs with same structure but different additional_keys are compatible."""
        original_config = {
            "value": "rate",
            "overflow": "Ult.",
            "max_overflow": 200,
            "additional_keys": {"sex": "M", "smoking": "NS"},
        }

        new_config = {
            "value": "rate",
            "overflow": "Ult.",
            "max_overflow": 200,
            "additional_keys": {"sex": "F", "smoking": "NS"},
        }

        _validate_append_compatibility(original_config, new_config)  # Should not raise

    def test_mismatched_value_parameter(self):
        """Test that mismatched value parameter raises error."""
        original_config = {"value": "rate", "overflow": "Ult.", "max_overflow": 200}
        new_config = {"value": "factor", "overflow": "Ult.", "max_overflow": 200}

        with pytest.raises(
            ValueError, match="'value' setting must match existing table"
        ):
            _validate_append_compatibility(original_config, new_config)

    def test_mismatched_overflow_parameter(self):
        """Test that mismatched overflow parameter raises error."""
        original_config = {"value": "rate", "overflow": "Ult.", "max_overflow": 200}
        new_config = {"value": "rate", "overflow": "auto", "max_overflow": 200}

        with pytest.raises(
            ValueError, match="'overflow' setting must match existing table"
        ):
            _validate_append_compatibility(original_config, new_config)

    def test_mismatched_max_overflow_parameter(self):
        """Test that mismatched max_overflow parameter raises error."""
        original_config = {"value": "rate", "overflow": "Ult.", "max_overflow": 200}
        new_config = {"value": "rate", "overflow": "Ult.", "max_overflow": 150}

        with pytest.raises(
            ValueError, match="'max_overflow' setting must match existing table"
        ):
            _validate_append_compatibility(original_config, new_config)

    def test_mismatched_additional_keys_structure(self):
        """Test that different additional_keys structures raise error."""
        original_config = {
            "value": "rate",
            "additional_keys": {"sex": "M", "smoking": "NS"},
        }

        new_config = {
            "value": "rate",
            "additional_keys": {"sex": "F", "region": "US"},  # Different keys
        }

        with pytest.raises(
            ValueError, match="Additional keys must match existing table structure"
        ):
            _validate_append_compatibility(original_config, new_config)

    def test_none_vs_empty_additional_keys(self):
        """Test handling of None vs empty dict for additional_keys."""
        original_config = {"value": "rate", "additional_keys": None}
        new_config = {"value": "rate", "additional_keys": {}}

        with pytest.raises(ValueError, match="identical additional_keys values"):
            _validate_append_compatibility(original_config, new_config)

    def test_missing_additional_keys(self):
        """Test handling when additional_keys is missing from one config."""
        original_config = {"value": "rate"}  # No additional_keys
        new_config = {"value": "rate", "additional_keys": {"sex": "M"}}

        with pytest.raises(
            ValueError, match="Additional keys must match existing table structure"
        ):
            _validate_append_compatibility(original_config, new_config)

    def test_detailed_error_messages(self):
        """Test that error messages contain helpful details."""
        original_config = {"value": "rate", "overflow": "Ult."}
        new_config = {"value": "factor", "overflow": "auto"}

        with pytest.raises(ValueError) as exc_info:
            _validate_append_compatibility(original_config, new_config)

        error_message = str(exc_info.value)
        assert "value" in error_message
        assert "rate" in error_message
        assert "factor" in error_message
        assert "critical parameters" in error_message


class TestValidateTableExistsForAppend:
    """Test table existence validation for append operations."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_existing_table(self):
        """Test that validation passes for existing table."""
        _store_table_config("test_table", {"value": "rate"})
        _validate_table_exists_for_append("test_table")  # Should not raise

    def test_nonexistent_table_no_tables(self):
        """Test error when no tables exist at all."""
        with pytest.raises(ValueError) as exc_info:
            _validate_table_exists_for_append("missing_table")

        error_message = str(exc_info.value)
        assert "does not exist and no tables are currently configured" in error_message
        assert "load_assumptions()" in error_message

    def test_nonexistent_table_with_available_tables(self):
        """Test error when table doesn't exist but others do."""
        _store_table_config("table1", {"value": "rate"})
        _store_table_config("table2", {"value": "factor"})

        with pytest.raises(ValueError) as exc_info:
            _validate_table_exists_for_append("missing_table")

        error_message = str(exc_info.value)
        assert "does not exist" in error_message
        assert "Available tables: ['table1', 'table2']" in error_message
        assert "load_assumptions()" in error_message


class TestValidateConfigurationCompleteness:
    """Test configuration completeness validation."""

    def test_complete_configuration(self):
        """Test that complete configuration passes validation."""
        config = {"value": "rate", "overflow": "Ult.", "additional_keys": {"sex": "M"}}
        _validate_configuration_completeness(
            config, "test_operation"
        )  # Should not raise

    def test_missing_required_field(self):
        """Test that missing required fields raise error."""
        config = {
            "overflow": "Ult.",
            "additional_keys": {"sex": "M"},
        }  # Missing 'value'

        with pytest.raises(ValueError, match="missing required fields"):
            _validate_configuration_completeness(config, "test_operation")

    def test_error_message_includes_operation_name(self):
        """Test that error message includes operation name."""
        config = {"overflow": "Ult."}  # Missing 'value'

        with pytest.raises(ValueError) as exc_info:
            _validate_configuration_completeness(config, "append_operation")

        error_message = str(exc_info.value)
        assert "append_operation" in error_message
        assert "missing required fields" in error_message


class TestValidateParameterTypes:
    """Test parameter type validation."""

    def test_valid_parameter_types(self):
        """Test that valid parameter types pass validation."""
        valid_configs = [
            {"value": "rate"},
            {"value": "rate", "overflow": "Ult.", "max_overflow": 200},
            {"value": "rate", "id": "age"},
            {"value": "rate", "id": ["age", "year"]},
            {"value": "rate", "additional_keys": {"sex": "M"}},
            {"value": "rate", "overflow": None, "additional_keys": None},
        ]

        for config in valid_configs:
            _validate_parameter_types(config)  # Should not raise

    def test_invalid_value_type(self):
        """Test that invalid value type raises error."""
        config = {"value": 123}  # Should be string

        with pytest.raises(
            ValueError, match="Parameter 'value' must be one of types: \\['str'\\]"
        ):
            _validate_parameter_types(config)

    def test_invalid_max_overflow_type(self):
        """Test that invalid max_overflow type raises error."""
        config = {"value": "rate", "max_overflow": "200"}  # Should be int

        with pytest.raises(
            ValueError,
            match="Parameter 'max_overflow' must be one of types: \\['int'\\]",
        ):
            _validate_parameter_types(config)

    def test_invalid_additional_keys_type(self):
        """Test that invalid additional_keys type raises error."""
        config = {
            "value": "rate",
            "additional_keys": ["not", "a", "dict"],
        }  # Should be dict or None

        with pytest.raises(
            ValueError, match="Parameter 'additional_keys' must be one of types"
        ):
            _validate_parameter_types(config)

    def test_id_parameter_multiple_valid_types(self):
        """Test that id parameter accepts multiple valid types."""
        valid_configs = [
            {"value": "rate", "id": "age"},  # string
            {"value": "rate", "id": ["age", "year"]},  # list
            {"value": "rate", "id": None},  # None
        ]

        for config in valid_configs:
            _validate_parameter_types(config)  # Should not raise

    def test_detailed_type_error_messages(self):
        """Test that type error messages are detailed and helpful."""
        config = {"value": 123, "max_overflow": "not_int"}

        with pytest.raises(ValueError) as exc_info:
            _validate_parameter_types(config)

        error_message = str(exc_info.value)
        # Should mention the parameter name, expected types, and actual value
        assert "value" in error_message
        assert "str" in error_message
        assert "123" in error_message or "int" in error_message


class TestIntegrationValidation:
    """Test integration between validation functions."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_complete_append_validation_workflow(self):
        """Test a complete validation workflow for append operations."""
        # Setup original table
        original_config = {
            "value": "rate",
            "overflow": "Ult.",
            "max_overflow": 200,
            "additional_keys": {"sex": "M", "smoking": "NS"},
        }
        _store_table_config("mortality_table", original_config)

        # Valid append configuration
        new_config = {
            "value": "rate",
            "overflow": "Ult.",
            "max_overflow": 200,
            "additional_keys": {"sex": "F", "smoking": "NS"},
        }

        # All validations should pass
        _validate_table_exists_for_append("mortality_table")
        _validate_additional_keys(new_config["additional_keys"])
        _validate_configuration_completeness(new_config, "append_operation")
        _validate_parameter_types(new_config)
        _validate_append_compatibility(original_config, new_config)

    def test_validation_chain_failure_points(self):
        """Test that validation chain fails at expected points."""
        original_config = {"value": "rate", "additional_keys": {"sex": "M"}}
        _store_table_config("test_table", original_config)

        # Test each validation failure point

        # 1. Invalid additional_keys format
        with pytest.raises(ValueError, match="additional_keys must be a dictionary"):
            _validate_additional_keys("not_a_dict")

        # 2. Missing required fields
        incomplete_config = {"overflow": "Ult."}  # Missing 'value'
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_configuration_completeness(incomplete_config, "test")

        # 3. Invalid parameter types
        bad_types_config = {"value": 123}  # Wrong type
        with pytest.raises(ValueError, match="Parameter 'value'"):
            _validate_parameter_types(bad_types_config)

        # 4. Incompatible configs
        incompatible_config = {"value": "factor", "additional_keys": {"sex": "F"}}
        with pytest.raises(ValueError, match="'value' setting must match"):
            _validate_append_compatibility(original_config, incompatible_config)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_empty_configurations(self):
        """Test validation with empty configurations."""
        # Empty configs should fail completeness check
        with pytest.raises(ValueError, match="missing required fields"):
            _validate_configuration_completeness({}, "test_operation")

        # But type validation should pass (no invalid types)
        _validate_parameter_types({})  # Should not raise

    def test_large_additional_keys(self):
        """Test validation with large additional_keys dictionaries."""
        large_additional_keys = {f"key_{i}": f"value_{i}" for i in range(100)}
        _validate_additional_keys(large_additional_keys)  # Should not raise

    def test_unicode_and_special_characters(self):
        """Test validation with Unicode and special characters."""
        special_keys = {
            "unicode_key_🔑": "value",
            "key_with_spaces": "value with spaces",
            "key-with-dashes": "value-with-dashes",
            "key_with_números": "value_with_símbolos",
        }
        _validate_additional_keys(special_keys)  # Should not raise

    def test_none_values_in_configs(self):
        """Test handling of None values in configurations."""
        config_with_nones = {
            "value": "rate",
            "overflow": None,
            "max_overflow": 200,
            "additional_keys": None,
        }

        _validate_parameter_types(config_with_nones)  # Should not raise
        _validate_configuration_completeness(
            config_with_nones, "test"
        )  # Should not raise
