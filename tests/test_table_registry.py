import polars as pl
import pytest
from gaspatchio_core._internal import table_registry


def test_create_registry():
    """Test that we can create a KeySpec and TableRegistry"""
    # Create a KeySpec
    key_spec = table_registry.KeySpec(source_cols=["id"], table_cols=["table_id"])

    # Create a TableRegistry
    registry = table_registry.TableRegistry()

    # Verify registry is empty
    assert len(registry.tables) == 0
    assert len(registry.keyspecs) == 0

    # Verify KeySpec fields
    assert len(key_spec.source_cols) == 1
    assert len(key_spec.table_cols) == 1
    assert key_spec.source_cols[0] == "id"
    assert key_spec.table_cols[0] == "table_id"


def test_global_registry():
    """Test that the global registry works with ArcSwap"""
    # Verify we can access the Python wrappers for our registry functions
    assert hasattr(table_registry, "py_get_registry")
    assert hasattr(table_registry, "py_register_keyspec")

    # Create a KeySpec
    key_spec = table_registry.KeySpec(
        source_cols=["source_id"], table_cols=["table_id"]
    )

    # Get initial registry
    initial_registry = table_registry.py_get_registry()
    initial_keyspec_count = len(initial_registry.keyspecs)

    # Register a keyspec
    table_registry.py_register_keyspec("test_table", key_spec)

    # Get updated registry
    updated_registry = table_registry.py_get_registry()

    # Verify keyspec was added
    assert len(updated_registry.keyspecs) == initial_keyspec_count + 1
    assert "test_table" in updated_registry.keyspecs

    # Verify keyspec properties
    test_keyspec = updated_registry.keyspecs["test_table"]
    assert test_keyspec.source_cols[0] == "source_id"
    assert test_keyspec.table_cols[0] == "table_id"


def test_register_and_lookup():
    """Test that we can register a table and lookup values from it"""
    # Create a test table DataFrame
    table_df = pl.DataFrame(
        {
            "table_id": [1, 2, 3, 4, 5],
            "value": ["a", "b", "c", "d", "e"],
            "extra_col": [10, 20, 30, 40, 50],
        }
    )

    # Create a KeySpec for the table
    key_spec = table_registry.KeySpec(
        source_cols=["id"],  # Column in the query DataFrame
        table_cols=["table_id"],  # Corresponding column in the registered table
    )

    # Register the table
    table_registry.py_register_table("test_lookup_table", table_df, key_spec)

    # Create a query DataFrame with keys to lookup
    query_df = pl.DataFrame(
        {
            "id": [1, 3, 5, 7],  # Note: 7 is not in the table
            "query_value": ["x", "y", "z", "w"],
        }
    )

    # Perform the lookup
    result_df = table_registry.py_lookup("test_lookup_table", query_df)

    # Verify the result
    assert result_df.shape[0] == 4  # Should have same number of rows as query

    # Check that all query columns are preserved
    assert "id" in result_df.columns
    assert "query_value" in result_df.columns

    # Check that table columns are included
    assert "value" in result_df.columns
    assert "extra_col" in result_df.columns

    # Check specific values
    # For id=1, should have value="a"
    assert result_df.filter(pl.col("id") == 1).select("value").item() == "a"
    # For id=3, should have value="c"
    assert result_df.filter(pl.col("id") == 3).select("value").item() == "c"
    # For id=5, should have value="e"
    assert result_df.filter(pl.col("id") == 5).select("value").item() == "e"
    # For id=7, should have null value (not in table)
    assert result_df.filter(pl.col("id") == 7).select("value").item() is None


def test_lookup_multiple_keys():
    """Test lookup with multiple key columns"""
    # Create a test table with composite key
    table_df = pl.DataFrame(
        {
            "category": ["A", "A", "B", "B", "C"],
            "subtype": [1, 2, 1, 2, 1],
            "value": ["a1", "a2", "b1", "b2", "c1"],
        }
    )

    # Create a KeySpec for the table with multiple columns
    key_spec = table_registry.KeySpec(
        source_cols=["cat", "sub"],  # Columns in the query DataFrame
        table_cols=[
            "category",
            "subtype",
        ],  # Corresponding columns in the registered table
    )

    # Register the table
    table_registry.py_register_table("composite_key_table", table_df, key_spec)

    # Create a query DataFrame with composite keys
    query_df = pl.DataFrame(
        {
            "cat": ["A", "B", "C", "D"],
            "sub": [1, 2, 1, 1],
            "query_value": ["query_a1", "query_b2", "query_c1", "query_d1"],
        }
    )

    # Perform the lookup
    result_df = table_registry.py_lookup("composite_key_table", query_df)

    # Verify the result
    assert result_df.shape[0] == 4  # Should have same number of rows as query

    # Check specific values based on composite keys
    # (A,1) should match to "a1"
    assert (
        result_df.filter((pl.col("cat") == "A") & (pl.col("sub") == 1))
        .select("value")
        .item()
        == "a1"
    )
    # (B,2) should match to "b2"
    assert (
        result_df.filter((pl.col("cat") == "B") & (pl.col("sub") == 2))
        .select("value")
        .item()
        == "b2"
    )
    # (C,1) should match to "c1"
    assert (
        result_df.filter((pl.col("cat") == "C") & (pl.col("sub") == 1))
        .select("value")
        .item()
        == "c1"
    )
    # (D,1) should have null value (not in table)
    assert (
        result_df.filter((pl.col("cat") == "D") & (pl.col("sub") == 1))
        .select("value")
        .item()
        is None
    )


def test_lookup_edge_cases():
    """Test edge cases for the lookup function"""
    # Test looking up from a non-existent table
    query_df = pl.DataFrame({"id": [1, 2, 3], "value": ["a", "b", "c"]})

    # Lookup from non-existent table should raise an error
    with pytest.raises(RuntimeError) as excinfo:
        table_registry.py_lookup("non_existent_table", query_df)
    assert "not found in registry" in str(excinfo.value)

    # Create a test table
    table_df = pl.DataFrame({"table_id": [1, 2, 3], "value": ["x", "y", "z"]})

    # Register with correct keyspec
    key_spec = table_registry.KeySpec(source_cols=["id"], table_cols=["table_id"])
    table_registry.py_register_table("edge_case_table", table_df, key_spec)

    # Create a query DataFrame with keys that won't match anything in the table
    non_matching_query_df = pl.DataFrame(
        {
            "id": [100, 200, 300],  # Key values that don't exist in the table
            "value": ["a", "b", "c"],
        }
    )

    # Lookup should work but won't find matches due to non-matching keys
    non_matching_result_df = table_registry.py_lookup(
        "edge_case_table", non_matching_query_df
    )

    # The result should have the same number of rows as the query
    assert non_matching_result_df.shape[0] == 3

    # Check if the query values are present
    assert "value" in non_matching_result_df.columns

    # Test with missing key column - this should raise an explicit error
    bad_query_df = pl.DataFrame(
        {
            "wrong_id_col": [1, 2, 3],  # Key column with wrong name
            "value": ["a", "b", "c"],
        }
    )

    # Lookup should raise an error due to missing column
    with pytest.raises(RuntimeError) as excinfo:
        table_registry.py_lookup("edge_case_table", bad_query_df)
    assert "not found: id" in str(excinfo.value)
