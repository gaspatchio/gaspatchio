"""
Internal module for validation logic.

This module contains validation functions for append compatibility and parameter
validation, providing comprehensive error messages for assumption table operations.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ._config import _table_exists


def _validate_additional_keys(additional_keys: dict[str, Any] | None) -> None:
    """Validate additional_keys parameter format.

    Args:
        additional_keys: Dictionary of additional keys to validate, or None

    Raises:
        ValueError: If additional_keys format is invalid
    """
    if additional_keys is None:
        logger.debug("additional_keys is None, validation passed")
        return

    if not isinstance(additional_keys, dict):
        raise ValueError(
            f"additional_keys must be a dictionary, got {type(additional_keys).__name__}"
        )

    if len(additional_keys) == 0:
        logger.debug("additional_keys is empty dictionary, validation passed")
        return

    # Validate all keys are non-empty strings
    for key, value in additional_keys.items():
        if not isinstance(key, str):
            raise ValueError(
                f"All additional_keys must have string keys, got {type(key).__name__} for key: {repr(key)}"
            )

        if not key.strip():
            raise ValueError(
                "All additional_keys must have non-empty string keys. "
                f"Found empty or whitespace-only key: {repr(key)}"
            )

    logger.debug(
        f"additional_keys validation passed for keys: {list(additional_keys.keys())}"
    )


def _validate_append_compatibility(original_config: dict, new_config: dict) -> None:
    """Validate that new data is compatible with existing table.

    Args:
        original_config: Configuration of the existing table
        new_config: Configuration of the data being appended

    Raises:
        ValueError: If configurations are incompatible
    """
    logger.debug(
        f"Validating append compatibility between original config keys: {list(original_config.keys())} "
        f"and new config keys: {list(new_config.keys())}"
    )

    # Check that fundamental parameters match
    critical_params = ["value", "overflow", "max_overflow"]

    for param in critical_params:
        original_value = original_config.get(param)
        new_value = new_config.get(param)

        if original_value != new_value:
            raise ValueError(
                f"'{param}' setting must match existing table. "
                f"Original table has {param}={repr(original_value)}, "
                f"but new data has {param}={repr(new_value)}. "
                f"All critical parameters must be identical for append compatibility."
            )

    # Validate additional_keys structure matches
    original_additional_keys = original_config.get("additional_keys", {})
    new_additional_keys = new_config.get("additional_keys", {})

    # Handle None values by converting to empty dict for comparison
    if original_additional_keys is None:
        original_additional_keys = {}
    if new_additional_keys is None:
        new_additional_keys = {}

    original_keys = set(original_additional_keys.keys())
    new_keys = set(new_additional_keys.keys())

    if original_keys != new_keys:
        raise ValueError(
            f"Additional keys must match existing table structure. "
            f"Original table has additional_keys: {sorted(original_keys)}, "
            f"but new data has additional_keys: {sorted(new_keys)}. "
            f"All appended data must have the same additional_keys structure."
        )

    # Check for data conflicts (same additional_keys values)
    if original_additional_keys == new_additional_keys:
        raise ValueError(
            f"Cannot append data with identical additional_keys values: {original_additional_keys}. "
            f"This would create duplicate key combinations in the lookup table. "
            f"Each append must have unique additional_keys values to avoid conflicts."
        )

    logger.debug("Append compatibility validation passed")


def _validate_table_exists_for_append(table_name: str) -> None:
    """Validate that a table exists for append operations.

    Args:
        table_name: Name of the table to check

    Raises:
        ValueError: If table does not exist with helpful suggestions
    """
    if not _table_exists(table_name):
        from ._config import _list_configured_tables

        available_tables = _list_configured_tables()

        if not available_tables:
            raise ValueError(
                f"Table '{table_name}' does not exist and no tables are currently configured. "
                f"Use load_assumptions() to create the table first before calling append_assumptions()."
            )
        else:
            raise ValueError(
                f"Table '{table_name}' does not exist. "
                f"Available tables: {available_tables}. "
                f"Use load_assumptions() to create the table first, or check the table name spelling."
            )

    logger.debug(f"Table existence validation passed for '{table_name}'")


def _validate_configuration_completeness(config: dict, operation_name: str) -> None:
    """Validate that a configuration has all required fields.

    Args:
        config: Configuration dictionary to validate
        operation_name: Name of the operation for error messages

    Raises:
        ValueError: If configuration is missing required fields
    """
    required_fields = ["value"]  # Core fields that must be present
    missing_fields = [field for field in required_fields if field not in config]

    if missing_fields:
        raise ValueError(
            f"Configuration for {operation_name} is missing required fields: {missing_fields}. "
            f"Available fields: {list(config.keys())}"
        )

    logger.debug(f"Configuration completeness validation passed for {operation_name}")


def _validate_parameter_types(config: dict) -> None:
    """Validate that configuration parameters have correct types.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ValueError: If parameters have incorrect types
    """
    type_validators = {
        "value": str,
        "overflow": (str, type(None)),
        "max_overflow": int,
        "id": (str, list, type(None)),
        "value_vars": (list, type(None)),
        "lookup_keys": (list, type(None)),
        "additional_keys": (dict, type(None)),
    }

    for param_name, expected_types in type_validators.items():
        if param_name in config:
            param_value = config[param_name]

            # Handle single type or tuple of types
            if not isinstance(expected_types, tuple):
                expected_types = (expected_types,)

            if not isinstance(param_value, expected_types):
                type_names = [t.__name__ for t in expected_types]
                raise ValueError(
                    f"Parameter '{param_name}' must be one of types: {type_names}, "
                    f"got {type(param_value).__name__}: {repr(param_value)}"
                )

    logger.debug(
        f"Parameter type validation passed for config with keys: {list(config.keys())}"
    )
