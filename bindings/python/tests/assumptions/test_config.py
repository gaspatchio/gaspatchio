"""
Unit tests for the assumptions configuration management module.

Tests cover configuration storage, retrieval, validation, and error handling.
"""

import pytest
from gaspatchio_core.assumptions._config import (
    _clear_table_configs,
    _get_table_config,
    _list_configured_tables,
    _store_table_config,
    _table_exists,
)


class TestStoreTableConfig:
    """Test configuration storage functionality."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_store_basic_config(self):
        """Test storing a basic configuration."""
        config = {"value": "rate", "overflow": "Ult.", "id": ["age"]}
        _store_table_config("test_table", config)

        assert _table_exists("test_table")
        stored_config = _get_table_config("test_table")
        assert stored_config == config

    def test_store_empty_config(self):
        """Test storing an empty configuration."""
        config = {}
        _store_table_config("empty_table", config)

        assert _table_exists("empty_table")
        stored_config = _get_table_config("empty_table")
        assert stored_config == {}

    def test_store_complex_config(self):
        """Test storing a complex configuration with nested data."""
        config = {
            "value": "rate",
            "overflow": "Ult.",
            "additional_keys": {"sex": "M", "smoking": "NS"},
            "id": ["age", "year"],
            "max_overflow": 200,
            "metadata": {"source": "file.csv", "version": 1},
        }
        _store_table_config("complex_table", config)

        stored_config = _get_table_config("complex_table")
        assert stored_config == config

    def test_overwrite_existing_config(self):
        """Test that storing a configuration overwrites existing one."""
        original_config = {"value": "rate", "overflow": "Ult."}
        new_config = {"value": "factor", "overflow": "auto"}

        _store_table_config("test_table", original_config)
        _store_table_config("test_table", new_config)

        stored_config = _get_table_config("test_table")
        assert stored_config == new_config
        assert stored_config != original_config


class TestGetTableConfig:
    """Test configuration retrieval functionality."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_get_existing_config(self):
        """Test retrieving an existing configuration."""
        config = {"value": "rate", "id": ["age"]}
        _store_table_config("test_table", config)

        retrieved_config = _get_table_config("test_table")
        assert retrieved_config == config

    def test_get_nonexistent_config(self):
        """Test error when retrieving non-existent configuration."""
        with pytest.raises(
            ValueError, match="No configuration found for table 'missing_table'"
        ):
            _get_table_config("missing_table")

    def test_get_config_with_available_tables_message(self):
        """Test error message includes available tables."""
        _store_table_config("table1", {"value": "rate"})
        _store_table_config("table2", {"value": "factor"})

        with pytest.raises(ValueError) as exc_info:
            _get_table_config("missing_table")

        error_message = str(exc_info.value)
        assert "Available configured tables: ['table1', 'table2']" in error_message

    def test_config_immutability_on_retrieval(self):
        """Test that retrieved configurations are copies, not references."""
        original_config = {"value": "rate", "nested": {"key": "value"}}
        _store_table_config("test_table", original_config)

        retrieved_config = _get_table_config("test_table")

        # Modify the retrieved config
        retrieved_config["value"] = "modified"
        retrieved_config["nested"]["key"] = "modified"

        # Original stored config should be unchanged
        stored_again = _get_table_config("test_table")
        assert stored_again["value"] == "rate"
        assert stored_again["nested"]["key"] == "value"


class TestTableExists:
    """Test table existence checking functionality."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_exists_for_stored_table(self):
        """Test that existence check returns True for stored tables."""
        _store_table_config("test_table", {"value": "rate"})
        assert _table_exists("test_table") is True

    def test_not_exists_for_unstored_table(self):
        """Test that existence check returns False for unstored tables."""
        assert _table_exists("missing_table") is False

    def test_exists_after_multiple_stores(self):
        """Test existence checking with multiple stored tables."""
        _store_table_config("table1", {"value": "rate"})
        _store_table_config("table2", {"value": "factor"})

        assert _table_exists("table1") is True
        assert _table_exists("table2") is True
        assert _table_exists("table3") is False


class TestListConfiguredTables:
    """Test listing configured tables functionality."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_list_empty_tables(self):
        """Test listing when no tables are configured."""
        tables = _list_configured_tables()
        assert tables == []

    def test_list_single_table(self):
        """Test listing with a single configured table."""
        _store_table_config("test_table", {"value": "rate"})

        tables = _list_configured_tables()
        assert tables == ["test_table"]

    def test_list_multiple_tables(self):
        """Test listing with multiple configured tables."""
        _store_table_config("table1", {"value": "rate"})
        _store_table_config("table2", {"value": "factor"})
        _store_table_config("table3", {"value": "count"})

        tables = _list_configured_tables()
        # Sort both lists since dictionary order might vary
        assert sorted(tables) == ["table1", "table2", "table3"]

    def test_list_returns_copy(self):
        """Test that list returns a copy that can be safely modified."""
        _store_table_config("test_table", {"value": "rate"})

        tables = _list_configured_tables()
        tables.append("modified")

        # Original list should be unchanged
        tables_again = _list_configured_tables()
        assert tables_again == ["test_table"]


class TestConfigImmutability:
    """Test that configurations are properly isolated from external mutation."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_store_config_immutability(self):
        """Test that stored configurations are not affected by external changes."""
        config = {"value": "rate", "nested": {"key": "value"}}
        _store_table_config("test_table", config)

        # Modify the original config
        config["value"] = "modified"
        config["nested"]["key"] = "modified"
        config["new_key"] = "new_value"

        # Stored config should be unchanged
        stored_config = _get_table_config("test_table")
        assert stored_config["value"] == "rate"
        assert stored_config["nested"]["key"] == "value"
        assert "new_key" not in stored_config

    def test_nested_immutability(self):
        """Test that nested structures in configurations are properly isolated."""
        config = {
            "value": "rate",
            "additional_keys": {"sex": "M", "smoking": "NS"},
            "id_list": ["age", "year"],
        }
        _store_table_config("test_table", config)

        # Modify nested structures in original
        config["additional_keys"]["sex"] = "F"
        config["additional_keys"]["new_key"] = "new_value"
        config["id_list"].append("duration")

        # Stored config should be unchanged
        stored_config = _get_table_config("test_table")
        assert stored_config["additional_keys"]["sex"] == "M"
        assert "new_key" not in stored_config["additional_keys"]
        assert stored_config["id_list"] == ["age", "year"]


class TestClearTableConfigs:
    """Test clearing configurations functionality."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_clear_empty_configs(self):
        """Test clearing when no configurations exist."""
        _clear_table_configs()  # Should not raise an error
        assert _list_configured_tables() == []

    def test_clear_single_config(self):
        """Test clearing a single configuration."""
        _store_table_config("test_table", {"value": "rate"})
        assert _table_exists("test_table")

        _clear_table_configs()

        assert not _table_exists("test_table")
        assert _list_configured_tables() == []

    def test_clear_multiple_configs(self):
        """Test clearing multiple configurations."""
        _store_table_config("table1", {"value": "rate"})
        _store_table_config("table2", {"value": "factor"})
        _store_table_config("table3", {"value": "count"})

        assert len(_list_configured_tables()) == 3

        _clear_table_configs()

        assert _list_configured_tables() == []
        assert not _table_exists("table1")
        assert not _table_exists("table2")
        assert not _table_exists("table3")


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def setup_method(self):
        """Clear configurations before each test."""
        _clear_table_configs()

    def test_empty_table_name(self):
        """Test storing configuration with empty table name."""
        config = {"value": "rate"}
        _store_table_config("", config)

        assert _table_exists("")
        stored_config = _get_table_config("")
        assert stored_config == config

    def test_none_values_in_config(self):
        """Test storing configuration with None values."""
        config = {"value": None, "overflow": "Ult.", "id": None}
        _store_table_config("test_table", config)

        stored_config = _get_table_config("test_table")
        assert stored_config == config
        assert stored_config["value"] is None
        assert stored_config["id"] is None

    def test_special_characters_in_table_name(self):
        """Test storing configuration with special characters in table name."""
        table_name = "test-table_with.special@chars#123"
        config = {"value": "rate"}

        _store_table_config(table_name, config)

        assert _table_exists(table_name)
        stored_config = _get_table_config(table_name)
        assert stored_config == config
