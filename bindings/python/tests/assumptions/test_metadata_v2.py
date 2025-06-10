"""
Tests for metadata functionality in the new Table API (v2).
"""

import polars as pl

from gaspatchio_core.assumptions import (
    Table,
    get_table_metadata,
    list_tables,
    list_tables_with_metadata,
)
from gaspatchio_core.assumptions._dimensions import DataDimension


class TestTableMetadata:
    """Test metadata functionality in Table class"""

    def test_table_with_metadata(self):
        """Test creating a table with metadata"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        metadata = {
            "source": "2015 VBT",
            "effective_date": "2015-01-01",
            "basis": "select_ultimate",
        }

        table = Table(
            name="test_metadata",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata=metadata,
        )

        # Test metadata property
        retrieved_metadata = table.metadata
        assert retrieved_metadata is not None
        assert retrieved_metadata == metadata
        assert retrieved_metadata is not metadata  # Should be a copy

    def test_table_without_metadata(self):
        """Test creating a table without metadata"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_no_metadata",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Test metadata property returns None
        assert table.metadata is None

    def test_metadata_immutability(self):
        """Test that metadata property returns a copy"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        original_metadata = {"source": "test", "version": 1}

        table = Table(
            name="test_immutable_metadata",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata=original_metadata,
        )

        # Modify the returned metadata
        retrieved = table.metadata
        assert retrieved is not None
        retrieved["modified"] = True

        # Original should be unchanged
        assert table.metadata == original_metadata
        assert "modified" not in table.metadata


class TestGlobalMetadataFunctions:
    """Test global metadata functions"""

    def test_get_table_metadata_existing(self):
        """Test getting metadata for an existing table"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        metadata = {"source": "global_test", "type": "mortality"}

        table = Table(
            name="global_metadata_test",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata=metadata,
        )

        # Test global function
        retrieved = get_table_metadata("global_metadata_test")
        assert retrieved == metadata
        assert retrieved is not metadata  # Should be a copy

    def test_get_table_metadata_nonexistent(self):
        """Test getting metadata for a nonexistent table"""
        result = get_table_metadata("nonexistent_table")
        assert result is None

    def test_list_tables_with_metadata(self):
        """Test listing all tables with metadata"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        # Create tables with metadata
        metadata1 = {"source": "table1", "type": "mortality"}
        metadata2 = {"source": "table2", "type": "lapse"}

        table1 = Table(
            name="metadata_list_test1",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata=metadata1,
        )

        table2 = Table(
            name="metadata_list_test2",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata=metadata2,
        )

        # Create table without metadata
        table3 = Table(
            name="metadata_list_test3",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Test global function
        all_metadata = list_tables_with_metadata()

        # Should include tables with metadata
        assert "metadata_list_test1" in all_metadata
        assert "metadata_list_test2" in all_metadata
        assert all_metadata["metadata_list_test1"] == metadata1
        assert all_metadata["metadata_list_test2"] == metadata2

        # Should not include table without metadata
        assert "metadata_list_test3" not in all_metadata

    def test_list_tables(self):
        """Test listing all registered tables"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        # Create a table
        table = Table(
            name="list_tables_test",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Test global function
        all_tables = list_tables()

        # Should include our table
        assert "list_tables_test" in all_tables


class TestMetadataTypes:
    """Test different metadata value types"""

    def test_complex_metadata_types(self):
        """Test various metadata value types"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        complex_metadata = {
            "string_value": "test",
            "int_value": 42,
            "float_value": 3.14,
            "bool_value": True,
            "list_value": [1, 2, 3],
            "dict_value": {"nested": "value"},
            "none_value": None,
        }

        table = Table(
            name="complex_metadata_test",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata=complex_metadata,
        )

        retrieved = table.metadata
        assert retrieved == complex_metadata

    def test_metadata_validation(self):
        """Test that metadata must be a dictionary"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        # This should work fine since we don't validate metadata type yet
        # In the future, we might add validation
        table = Table(
            name="validation_test",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            metadata={"valid": "metadata"},
        )

        assert table.metadata == {"valid": "metadata"}
