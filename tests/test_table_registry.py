import os

import polars as pl
import pytest
from gaspatchio_core.assumptions import table_registry


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


def test_wide_to_long_transform():
    """Test the wide-to-long transformation functionality"""
    # Create a wide DataFrame for testing
    wide_df = pl.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "region": ["North", "South", "East", "West"],
            "sales_2020": [100, 150, 200, 250],
            "sales_2021": [120, 170, 220, 270],
            "sales_2022": [140, 190, 240, 290],
        }
    )

    # Create a KeySpec
    key_spec = table_registry.KeySpec(source_cols=["id"], table_cols=["id"])

    # Create a TransformSpec for the wide-to-long transformation
    transform_spec = table_registry.TransformSpec(
        id_vars=["id", "region"],  # Columns to keep as identifiers
        value_vars=["sales_2020", "sales_2021", "sales_2022"],  # Columns to unpivot
        var_name="year",  # Name for the column that will contain the unpivoted column names
        value_name="sales",  # Name for the column that will contain the values
    )

    # Register the table with transformation
    table_registry.py_register_table_with_transform(
        "sales_by_year", wide_df, key_spec, transform_spec
    )

    # Get the registry and check the registered table
    registry = table_registry.py_get_registry()

    # Check that the table was registered
    assert "sales_by_year" in registry.tables

    # Create a query DataFrame to look up sales for specific IDs
    query_df = pl.DataFrame(
        {
            "id": [1, 3],
            "query_info": ["Query1", "Query3"],
        }
    )

    # Perform lookup
    result_df = table_registry.py_lookup("sales_by_year", query_df)

    # Verify results
    # Since we have 3 years per ID, and we're looking up 2 IDs,
    # we should get 2*3 = 6 rows in the result
    assert result_df.shape[0] == 6

    # Verify the columns exist
    assert "id" in result_df.columns
    assert "query_info" in result_df.columns
    assert "region" in result_df.columns
    assert "year" in result_df.columns
    assert "sales" in result_df.columns

    # Get the rows for ID=1
    id1_rows = result_df.filter(pl.col("id") == 1)
    assert id1_rows.shape[0] == 3  # Should have 3 rows (one for each year)

    # Verify specific values
    # For ID=1, year=sales_2020, sales should be 100
    sales_2020 = id1_rows.filter(pl.col("year") == "sales_2020").select("sales").item()
    assert sales_2020 == 100

    # For ID=1, year=sales_2021, sales should be 120
    sales_2021 = id1_rows.filter(pl.col("year") == "sales_2021").select("sales").item()
    assert sales_2021 == 120

    # For ID=1, year=sales_2022, sales should be 140
    sales_2022 = id1_rows.filter(pl.col("year") == "sales_2022").select("sales").item()
    assert sales_2022 == 140

    # Get the rows for ID=3
    id3_rows = result_df.filter(pl.col("id") == 3)
    assert id3_rows.shape[0] == 3  # Should have 3 rows (one for each year)

    # For ID=3, region should be "East"
    region = id3_rows.select("region").unique().item()
    assert region == "East"


def test_mortality_table_transform_and_lookup():
    """Test transform_wide_to_long with mortality-like table structure"""
    # Create a mortality-like wide DataFrame
    # This simulates a table with age groups as columns and countries/years as rows
    mortality_df = pl.DataFrame(
        {
            "country": ["USA", "USA", "Canada", "Canada", "Mexico", "Mexico"],
            "year": [2020, 2021, 2020, 2021, 2020, 2021],
            "age_0_14": [0.012, 0.011, 0.010, 0.009, 0.015, 0.014],
            "age_15_64": [0.052, 0.054, 0.048, 0.047, 0.061, 0.060],
            "age_65_plus": [0.123, 0.126, 0.118, 0.120, 0.110, 0.112],
        }
    )

    # Create a KeySpec for the table
    # This will allow lookup by country and year
    key_spec = table_registry.KeySpec(
        source_cols=["country", "year"],  # Columns in the query DataFrame
        table_cols=["country", "year"],  # Corresponding columns in the registered table
    )

    # Create a TransformSpec for wide-to-long transformation
    # We want to transform age groups from columns to rows
    transform_spec = table_registry.TransformSpec(
        id_vars=["country", "year"],  # Keep these as identifier columns
        value_vars=[
            "age_0_14",
            "age_15_64",
            "age_65_plus",
        ],  # Age group columns to transform
        var_name="age_group",  # New column to hold age group names
        value_name="mortality_rate",  # New column to hold the mortality rates
    )

    # Register the table with transformation
    table_registry.py_register_table_with_transform(
        "mortality_data", mortality_df, key_spec, transform_spec
    )

    # Verify the table was registered
    registry = table_registry.py_get_registry()
    assert "mortality_data" in registry.tables

    # Create a query DataFrame to look up mortality rates
    query_df = pl.DataFrame(
        {
            "country": ["USA", "Canada", "Japan"],  # Note: Japan not in original data
            "year": [2020, 2021, 2020],
            "other_field": ["query1", "query2", "query3"],
        }
    )

    # Perform lookup
    result_df = table_registry.py_lookup("mortality_data", query_df)

    # Verify results
    # When joining the transformed table, only the matches from the original data are returned
    # The age group from the value_vars multiplies the number of rows for each matching entry
    assert result_df.shape[0] == 7  # The actual number of rows in the result

    # Verify the expected columns exist
    assert "country" in result_df.columns
    assert "year" in result_df.columns
    assert "other_field" in result_df.columns
    assert "age_group" in result_df.columns
    assert "mortality_rate" in result_df.columns

    # Check specific values for USA in 2020
    usa_2020 = result_df.filter((pl.col("country") == "USA") & (pl.col("year") == 2020))
    assert usa_2020.shape[0] == 3  # Should have 3 rows (one for each age group)

    # For USA 2020, age_0_14 mortality rate should be 0.012
    usa_2020_young = usa_2020.filter(pl.col("age_group") == "age_0_14")
    assert round(usa_2020_young.select("mortality_rate").item(), 3) == 0.012

    # For USA 2020, age_65_plus mortality rate should be 0.123
    usa_2020_elderly = usa_2020.filter(pl.col("age_group") == "age_65_plus")
    assert round(usa_2020_elderly.select("mortality_rate").item(), 3) == 0.123

    # Check specific values for Canada in 2021
    canada_2021 = result_df.filter(
        (pl.col("country") == "Canada") & (pl.col("year") == 2021)
    )
    assert canada_2021.shape[0] == 3  # Should have 3 rows (one for each age group)

    # For Canada 2021, age_15_64 mortality rate should be 0.047
    canada_2021_adult = canada_2021.filter(pl.col("age_group") == "age_15_64")
    assert round(canada_2021_adult.select("mortality_rate").item(), 3) == 0.047

    # Check that Japan 2020 has null values for mortality rates (not in original data)
    japan_2020 = result_df.filter(
        (pl.col("country") == "Japan") & (pl.col("year") == 2020)
    )
    assert (
        japan_2020.shape[0] == 1
    )  # For non-matching data, we get a single row with nulls

    # All mortality rates for Japan should be null
    assert japan_2020.select("mortality_rate").item() is None


def test_mortality_lookup_with_real_data():
    """Test using real mortality data and performing lookups with combined sex and smoking status"""
    # Skip test if the parquet files don't exist in the expected location
    mortality_file = os.path.join("jobs", "example", "assumptions", "mortality.parquet")
    model_points_file = os.path.join("jobs", "example", "model-points.parquet")
    if not os.path.exists(mortality_file) or not os.path.exists(model_points_file):
        pytest.skip(f"Test files not found: {mortality_file} or {model_points_file}")

    # Load the mortality table
    mortality_df = pl.read_parquet(mortality_file)

    # The mortality table is in wide format with columns:
    # age-last, MNS (Male Non-Smoker), FNS (Female Non-Smoker), MS (Male Smoker), FS (Female Smoker)
    # We need to transform this to long format with age-last, sex_smoking, rate

    # Create a KeySpec for the final transformed table
    key_spec = table_registry.KeySpec(
        source_cols=["age-last", "sex_smoking"],  # Columns in the query DataFrame
        table_cols=[
            "age-last",
            "sex_smoking",
        ],  # Columns in the transformed mortality table
    )

    # Create a TransformSpec to transform the wide mortality table to long format
    transform_spec = table_registry.TransformSpec(
        id_vars=["age-last"],  # Keep age as identifier
        value_vars=[
            "MNS",
            "FNS",
            "MS",
            "FS",
        ],  # Sex and smoking status columns to transform
        var_name="sex_smoking",  # New column to hold sex_smoking combination
        value_name="mortality_rate",  # New column to hold mortality rates
    )

    # Register the mortality table with transformation
    table_registry.py_register_table_with_transform(
        "mortality_rates", mortality_df, key_spec, transform_spec
    )

    # Verify the table was registered
    registry = table_registry.py_get_registry()
    assert "mortality_rates" in registry.tables

    # Load the model points for testing lookups
    model_points_df = pl.read_parquet(model_points_file)

    # Create a new column combining gender and smoking status to match the transformed mortality table
    model_points_with_combined = model_points_df.with_columns(
        pl.concat_str([pl.col("gender"), pl.col("smoking_status")]).alias("sex_smoking")
    )

    # Create a query DataFrame with age-last and sex_smoking fields
    # We'll use the first 5 model points plus a test case that won't match
    query_df = (
        model_points_with_combined.select(["policyholder_nr", "age", "sex_smoking"])
        .rename({"age": "age-last"})
        .head(5)
    )

    # Add a non-matching test case (age = 101, which is beyond our mortality table)
    non_matching_row = pl.DataFrame(
        {
            "policyholder_nr": [999],
            "age-last": [101],  # Beyond our mortality table
            "sex_smoking": ["MNS"],
        }
    )
    query_df = pl.concat([query_df, non_matching_row])

    # Perform lookup
    result_df = table_registry.py_lookup("mortality_rates", query_df)

    # Verify results
    assert (
        result_df.shape[0] == 6
    )  # Should have 6 rows (5 model points + 1 non-matching)

    # Verify the expected columns exist
    assert "policyholder_nr" in result_df.columns
    assert "age-last" in result_df.columns
    assert "sex_smoking" in result_df.columns
    assert "mortality_rate" in result_df.columns

    # Check specific values
    # Check the first row - Female Smoker age 55
    first_row = result_df.filter(pl.col("policyholder_nr") == 1)
    assert first_row.shape[0] == 1
    assert first_row.select("sex_smoking").item() == "FS"
    assert first_row.select("age-last").item() == 55
    assert isinstance(first_row.select("mortality_rate").item(), float)

    # Check the second row - Male Smoker age 39
    second_row = result_df.filter(pl.col("policyholder_nr") == 2)
    assert second_row.shape[0] == 1
    assert second_row.select("sex_smoking").item() == "MS"
    assert second_row.select("age-last").item() == 39
    assert isinstance(second_row.select("mortality_rate").item(), float)

    # Check the non-matching row (age 101)
    non_matching_row = result_df.filter(pl.col("policyholder_nr") == 999)
    assert non_matching_row.shape[0] == 1
    assert non_matching_row.select("mortality_rate").item() is None

    # Let's also verify we can map directly from model points to mortality rates in one step

    # First combine model points gender and smoking status to match the mortality table
    # Also rename the age column to age-last to match the mortality table
    model_points_df = model_points_df.with_columns(
        pl.concat_str([pl.col("gender"), pl.col("smoking_status")]).alias("sex_smoking")
    ).rename({"age": "age-last"})

    # Execute a lookup for all model points
    complete_lookup = table_registry.py_lookup("mortality_rates", model_points_df)

    # Verify we got mortality rates for all model points
    assert complete_lookup.shape[0] == model_points_df.shape[0]

    # Check the combined data has the expected columns from both tables
    assert "policyholder_nr" in complete_lookup.columns
    assert "age-last" in complete_lookup.columns
    assert "sex_smoking" in complete_lookup.columns
    assert "mortality_rate" in complete_lookup.columns
    assert "sum_assured" in complete_lookup.columns
    assert "policy_duration" in complete_lookup.columns

    # Every valid age in our model points should have a mortality rate
    valid_ages = complete_lookup.filter(pl.col("age-last") <= 100)
    assert valid_ages.select(pl.col("mortality_rate").is_null()).sum().item() == 0
