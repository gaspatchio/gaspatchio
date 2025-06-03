"""
Internal module for table configuration management.

This module manages table configurations for assumption tables, providing
storage and retrieval functionality needed for append compatibility validation.
"""

from __future__ import annotations

import copy
from typing import Any, Dict

from loguru import logger

# Global storage for table configurations (for append compatibility validation)
_TABLE_CONFIGS: Dict[str, Dict[str, Any]] = {}


def _store_table_config(name: str, config: dict) -> None:
    """Store table configuration for compatibility validation.

    Args:
        name: The table name to store configuration for
        config: Dictionary containing table configuration parameters

    The configuration is copied to prevent external mutation.
    """
    _TABLE_CONFIGS[name] = copy.deepcopy(config)
    logger.debug(
        f"Stored configuration for table '{name}' with keys: {list(config.keys())}"
    )


def _get_table_config(name: str) -> dict:
    """Get stored configuration for a table.

    Args:
        name: The table name to retrieve configuration for

    Returns:
        A copy of the stored configuration dictionary

    Raises:
        ValueError: If no configuration is found for the table
    """
    if name not in _TABLE_CONFIGS:
        available_tables = list(_TABLE_CONFIGS.keys())
        raise ValueError(
            f"No configuration found for table '{name}'. "
            f"Available configured tables: {available_tables}"
        )

    config = copy.deepcopy(_TABLE_CONFIGS[name])
    logger.debug(f"Retrieved configuration for table '{name}'")
    return config


def _table_exists(name: str) -> bool:
    """Check if a table exists in the configuration storage.

    Args:
        name: The table name to check

    Returns:
        True if the table has a stored configuration, False otherwise
    """
    exists = name in _TABLE_CONFIGS
    logger.debug(f"Table existence check for '{name}': {exists}")
    return exists


def _list_configured_tables() -> list[str]:
    """List all tables that have stored configurations.

    Returns:
        A list of table names that have stored configurations
    """
    tables = list(_TABLE_CONFIGS.keys())
    logger.debug(f"Listed {len(tables)} configured tables: {tables}")
    return tables


def _clear_table_configs() -> None:
    """Clear all stored table configurations.

    This function is primarily intended for testing purposes.
    """
    global _TABLE_CONFIGS
    cleared_count = len(_TABLE_CONFIGS)
    _TABLE_CONFIGS.clear()
    logger.debug(f"Cleared {cleared_count} table configurations")
