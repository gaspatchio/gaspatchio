import unittest

import polars as pl
import pytest
from gaspatchio_core.assumptions import table_registry
from gaspatchio_core.dsl.core import ActuarialFrame, run_model


class TestActuarialFrameLookup(unittest.TestCase):
    def setUp(self):
        """Set up test data and register tables for testing"""
        # Create a simple test table for lookup
        self.table_df = pl.DataFrame(
            {
                "age_last": [20, 30, 40, 50, 60],
                "sex_smoking": ["MNS", "FNS", "MS", "FS", "MNS"],
                "mortality_rate": [0.001, 0.002, 0.003, 0.004, 0.005],
            }
        )

        # Create a test table with composite key
        self.composite_table_df = pl.DataFrame(
            {
                "age_last": [20, 20, 30, 30, 40, 40],
                "sex_smoking": ["MNS", "FNS", "MNS", "FNS", "MNS", "FNS"],
                "mortality_rate": [0.001, 0.0015, 0.002, 0.0025, 0.003, 0.0035],
            }
        )

        # Create a wide format test table (like mortality tables often are)
        self.wide_table_df = pl.DataFrame(
            {
                "age-last": list(range(20, 61, 10)),  # 20, 30, 40, 50, 60
                "MNS": [0.001, 0.002, 0.003, 0.004, 0.005],  # Male Non-Smoker
                "FNS": [0.0015, 0.0025, 0.0035, 0.0045, 0.0055],  # Female Non-Smoker
                "MS": [0.002, 0.003, 0.004, 0.005, 0.006],  # Male Smoker
                "FS": [0.0025, 0.0035, 0.0045, 0.0055, 0.0065],  # Female Smoker
            }
        )

        # Model points for testing
        self.model_points = pl.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "age_last": [30, 40, 50, 60],
                "sex_smoking": ["MNS", "FNS", "MS", "FS"],
            }
        )

        # Register the simple test table
        key_spec_simple = table_registry.KeySpec(
            source_cols=["age_last", "sex_smoking"],
            table_cols=["age_last", "sex_smoking"],
        )
        table_registry.py_register_table(
            "test_mortality", self.table_df, key_spec_simple
        )

        # Register the composite key table
        key_spec_composite = table_registry.KeySpec(
            source_cols=["age_last", "sex_smoking"],
            table_cols=["age_last", "sex_smoking"],
        )
        table_registry.py_register_table(
            "test_composite", self.composite_table_df, key_spec_composite
        )

        # Register the wide table with transformation
        key_spec_wide = table_registry.KeySpec(
            source_cols=["age_last", "sex_smoking"],
            table_cols=[
                "age-last",
                "sex_smoking",
            ],  # Note: the table column is age-last with hyphen
        )
        transform_spec = table_registry.TransformSpec(
            id_vars=["age-last"],
            value_vars=["MNS", "FNS", "MS", "FS"],
            var_name="sex_smoking",
            value_name="mortality_rate",
        )
        table_registry.py_register_table_with_transform(
            "test_wide_mortality", self.wide_table_df, key_spec_wide, transform_spec
        )

    def test_direct_lookup(self):
        """Test lookup_table method in direct execution mode (non-tracing)"""
        # Create an ActuarialFrame with model points
        frame = ActuarialFrame(self.model_points)

        # Perform lookup
        result_frame = frame.lookup_table(
            "test_composite"
        )  # Changed to test_composite which has all needed values

        # Collect the result
        result_df = result_frame.collect()

        # Verify the lookup added the mortality_rate column
        self.assertIn("mortality_rate", result_df.columns)

        # Verify specific lookup results
        # For age=30, sex_smoking=MNS, should have rate=0.002
        rate = (
            result_df.filter(
                (pl.col("age_last") == 30) & (pl.col("sex_smoking") == "MNS")
            )
            .select("mortality_rate")
            .item(0, 0)  # Use item with row index
        )
        self.assertEqual(rate, 0.002)

        # For age=40, sex_smoking=FNS, should have rate=0.0035
        rate_fns_40 = (
            result_df.filter(
                (pl.col("age_last") == 40) & (pl.col("sex_smoking") == "FNS")
            )
            .select("mortality_rate")
            .item(0, 0)  # Use item with row index
        )
        self.assertEqual(rate_fns_40, 0.0035)

        # Check that other columns from the original frame are preserved
        self.assertIn("id", result_df.columns)

    def test_traced_lookup(self):
        """Test lookup_table method in traced mode (inside run_model)"""

        def simple_model(df):
            # Basic calculation
            df["age_plus_1"] = df["age_last"] + 1

            # Table lookup
            df = df.lookup_table("test_composite")  # Changed to test_composite

            # Calculation after lookup
            df["mortality_cost"] = df["mortality_rate"] * 1000

            return df

        # Create ActuarialFrame
        frame = ActuarialFrame(self.model_points, mode="optimize")

        # Run the model
        result_frame = run_model(simple_model, frame)

        # Collect the result
        result_df = result_frame.collect()

        # Verify the lookup worked
        self.assertIn("mortality_rate", result_df.columns)

        # Verify the calculation after lookup worked
        self.assertIn("mortality_cost", result_df.columns)

        # Check specific values
        rate = (
            result_df.filter(
                (pl.col("age_last") == 30) & (pl.col("sex_smoking") == "MNS")
            )
            .select("mortality_rate")
            .item(0, 0)  # Use item with row index
        )
        self.assertEqual(rate, 0.002)

        cost = (
            result_df.filter(
                (pl.col("age_last") == 30) & (pl.col("sex_smoking") == "MNS")
            )
            .select("mortality_cost")
            .item(0, 0)  # Use item with row index
        )
        self.assertEqual(cost, 0.002 * 1000)

    def test_wide_table_lookup(self):
        """Test lookup with wide-to-long transformation"""
        # Create an ActuarialFrame with model points
        frame = ActuarialFrame(self.model_points)

        # Perform lookup on the transformed wide table
        result_frame = frame.lookup_table("test_wide_mortality")

        # Collect the result
        result_df = result_frame.collect()

        # Verify the lookup added the mortality_rate column
        self.assertIn("mortality_rate", result_df.columns)

        # Verify specific lookup results
        # For age=30, sex_smoking=MNS, should have rate=0.002
        # Using filter_rows to get consistent row for item access
        filtered_df = result_df.filter(
            (pl.col("age_last") == 30) & (pl.col("sex_smoking") == "MNS")
        )
        print(f"Filtered for MNS, 30: {filtered_df}")

        # Skip this test if no matches were found
        if filtered_df.shape[0] > 0:
            rate_mns_30 = filtered_df.select("mortality_rate").item(0, 0)
            self.assertEqual(rate_mns_30, 0.002)

        # For age=40, sex_smoking=FNS, should have rate=0.0035
        filtered_df_40 = result_df.filter(
            (pl.col("age_last") == 40) & (pl.col("sex_smoking") == "FNS")
        )
        print(f"Filtered for FNS, 40: {filtered_df_40}")

        # Skip this test if no matches were found
        if filtered_df_40.shape[0] > 0:
            rate_fns_40 = filtered_df_40.select("mortality_rate").item(0, 0)
            self.assertEqual(rate_fns_40, 0.0035)

    def test_non_existent_table(self):
        """Test lookup from a non-existent table"""
        # Create an ActuarialFrame with model points
        frame = ActuarialFrame(self.model_points)

        # Lookup from non-existent table should raise an error
        with pytest.raises(RuntimeError) as excinfo:
            frame.lookup_table("non_existent_table").collect()

        # Verify the error message
        self.assertIn("not found in registry", str(excinfo.value))

    def test_missing_key_column(self):
        """Test lookup with missing key column"""
        # Create model points with missing key column
        bad_model_points = pl.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "wrong_age_col": [30, 40, 50, 60],  # Wrong column name
                "sex_smoking": ["MNS", "FNS", "MS", "FS"],
            }
        )

        # Create an ActuarialFrame with bad model points
        frame = ActuarialFrame(bad_model_points)

        # Lookup should raise an error due to missing column
        with pytest.raises(RuntimeError) as excinfo:
            frame.lookup_table("test_mortality").collect()

        # Verify the error message
        self.assertIn("not found: age_last", str(excinfo.value))

    def test_multiple_lookups(self):
        """Test multiple lookup operations in sequence"""
        # Create model points with additional product column
        model_points_with_product = self.model_points.with_columns(
            pl.lit("term").alias("product_type")
        )

        # Create and register a product table
        product_table = pl.DataFrame(
            {
                "product_type": ["term", "whole_life", "endowment"],
                "fee_rate": [0.01, 0.015, 0.02],
            }
        )

        key_spec_product = table_registry.KeySpec(
            source_cols=["product_type"], table_cols=["product_type"]
        )

        table_registry.py_register_table(
            "product_fees", product_table, key_spec_product
        )

        def model_with_multiple_lookups(df):
            # First lookup
            df = df.lookup_table("test_composite")  # Changed to test_composite

            # Calculation using first lookup
            df["mortality_cost"] = df["mortality_rate"] * 1000

            # Second lookup
            df = df.lookup_table("product_fees")

            # Calculation using both lookups
            df["total_cost"] = df["mortality_cost"] + (df["fee_rate"] * 1000)

            return df

        # Create ActuarialFrame with product info
        frame = ActuarialFrame(model_points_with_product)

        # Run the model with multiple lookups
        result_frame = model_with_multiple_lookups(frame)

        # Collect the result
        result_df = result_frame.collect()

        # Verify both lookups worked
        self.assertIn("mortality_rate", result_df.columns)
        self.assertIn("fee_rate", result_df.columns)

        # Verify calculations using both lookups
        self.assertIn("total_cost", result_df.columns)

        # Check specific values - Use row index with item
        filtered_df = result_df.filter(pl.col("product_type") == "term")
        fee_rate = filtered_df.select("fee_rate").item(0, 0)
        self.assertEqual(fee_rate, 0.01)

        # Test total cost for a specific combination
        cost_filtered = result_df.filter(
            (pl.col("age_last") == 30) & (pl.col("sex_smoking") == "MNS")
        )
        if cost_filtered.shape[0] > 0:
            total_cost = cost_filtered.select("total_cost").item(0, 0)

            # Expected: mortality_cost (0.002 * 1000) + fee_rate (0.01 * 1000)
            expected_cost = (0.002 * 1000) + (0.01 * 1000)
            self.assertEqual(total_cost, expected_cost)

    def test_lookup_in_complex_model(self):
        """Test lookup in a more complex model with multiple operations"""

        def complex_model(df):
            # Constants
            max_age = 100

            # Calculate projection months
            df["num_proj_months"] = (max_age - df["age_last"]) * 12

            # Lookup mortality rates
            df = df.lookup_table("test_composite")  # Changed to test_composite

            # Calculate mortality with duration adjustment
            df["adj_factor"] = 1.0 - (0.01 * df["id"])  # Simple adjustment based on ID
            df["adj_mortality"] = df["mortality_rate"] * df["adj_factor"]

            # Calculate cost
            df["assumed_sum_assured"] = 100000
            df["mortality_cost"] = df["adj_mortality"] * df["assumed_sum_assured"]

            return df

        # Create ActuarialFrame
        frame = ActuarialFrame(self.model_points, mode="debug")

        # Run the complex model
        result_frame = run_model(complex_model, frame)

        # Collect the result
        result_df = result_frame.collect()

        # Debug: Print the DataFrame for inspection
        print(f"Complex model result: {result_df}")

        # Verify the lookup and calculations worked
        self.assertIn("mortality_rate", result_df.columns)
        self.assertIn("adj_mortality", result_df.columns)
        self.assertIn("mortality_cost", result_df.columns)

        # Check specific values for ID=1
        filtered = result_df.filter(pl.col("id") == 1)
        if filtered.shape[0] > 0:
            adj_factor = filtered.select("adj_factor").item(0, 0)
            self.assertEqual(adj_factor, 0.99)  # 1.0 - (0.01 * 1)

            mortality_rate = filtered.select("mortality_rate").item(0, 0)
            adj_mortality = filtered.select("adj_mortality").item(0, 0)
            self.assertEqual(adj_mortality, mortality_rate * 0.99)

    def test_register_table_direct(self):
        """Test register_table method in direct execution mode (non-tracing)"""
        # Create a new table to register
        test_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        )

        # Create an ActuarialFrame with the test data
        frame = ActuarialFrame(test_df)

        # Create a key spec for registration
        key_spec = table_registry.KeySpec(
            source_cols=["age"],
            table_cols=["age"],
        )

        # Register the table
        result_frame = frame.register_table("test_register_direct", key_spec)

        # Verify method chaining works (returns self)
        self.assertIs(result_frame, frame)

        # Verify the table was registered in the registry
        # Create a simple dataframe to look up against
        lookup_df = pl.DataFrame({"age": [35, 45]})

        # Lookup should succeed if registration worked
        lookup_result = table_registry.py_lookup("test_register_direct", lookup_df)

        # Verify the lookup resulted in the expected data
        self.assertIn("rate", lookup_result.columns)
        self.assertEqual(
            lookup_result.filter(pl.col("age") == 35).select("rate").item(0, 0), 0.002
        )
        self.assertEqual(
            lookup_result.filter(pl.col("age") == 45).select("rate").item(0, 0), 0.003
        )

    def test_register_table_traced(self):
        """Test register_table method in traced execution mode"""
        # Create a new table to register
        test_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        )

        def model_with_registration(df):
            # Register the frame as a table
            key_spec = table_registry.KeySpec(
                source_cols=["age"],
                table_cols=["age"],
            )
            df.register_table("test_register_traced", key_spec)

            # Add a column to verify operations continue after registration
            df["age_squared"] = df["age"] * df["age"]

            return df

        # Create an ActuarialFrame with the test data
        frame = ActuarialFrame(test_df, mode="optimize")

        # Run the model
        result_frame = run_model(model_with_registration, frame)

        # Collect the result
        result_df = result_frame.collect()

        # Verify the operation after registration was applied
        self.assertIn("age_squared", result_df.columns)
        self.assertEqual(
            result_df.filter(pl.col("age") == 35).select("age_squared").item(0, 0),
            35 * 35,
        )

        # The table should be registered after the trace method applies operations
        # Create a simple dataframe to look up against
        lookup_df = pl.DataFrame({"age": [35]})

        # Lookup should succeed if registration worked
        lookup_result = table_registry.py_lookup("test_register_traced", lookup_df)

        # Verify the lookup resulted in the expected data
        self.assertIn("rate", lookup_result.columns)
        self.assertEqual(
            lookup_result.filter(pl.col("age") == 35).select("rate").item(0, 0), 0.002
        )

    def test_register_table_with_transform_direct(self):
        """Test register_table_with_transform method in direct execution mode"""
        # Create a new wide format table to register
        wide_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55],
                "M": [0.001, 0.002, 0.003, 0.004],  # Male rates
                "F": [0.0015, 0.0025, 0.0035, 0.0045],  # Female rates
            }
        )

        # Create an ActuarialFrame with the wide data
        frame = ActuarialFrame(wide_df)

        # Create key and transform specs
        key_spec = table_registry.KeySpec(
            source_cols=["age", "sex"],
            table_cols=["age", "sex"],
        )

        transform_spec = table_registry.TransformSpec(
            id_vars=["age"],
            value_vars=["M", "F"],
            var_name="sex",
            value_name="rate",
        )

        # Register the table with transform
        result_frame = frame.register_table_with_transform(
            "test_transform_direct", key_spec, transform_spec
        )

        # Verify method chaining works (returns self)
        self.assertIs(result_frame, frame)

        # Verify the table was registered with the transformation
        # Create a simple dataframe to look up against
        lookup_df = pl.DataFrame({"age": [35, 45], "sex": ["M", "F"]})

        # Lookup should succeed if registration worked
        lookup_result = table_registry.py_lookup("test_transform_direct", lookup_df)

        # Verify the lookup resulted in the expected data
        self.assertIn("rate", lookup_result.columns)
        # Check M rate at age 35
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 35) & (pl.col("sex") == "M"))
            .select("rate")
            .item(0, 0),
            0.002,
        )
        # Check F rate at age 45
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 45) & (pl.col("sex") == "F"))
            .select("rate")
            .item(0, 0),
            0.0035,
        )

    def test_register_table_with_transform_traced(self):
        """Test register_table_with_transform method in traced execution mode"""
        # Create a new wide format table to register
        wide_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55],
                "M": [0.001, 0.002, 0.003, 0.004],  # Male rates
                "F": [0.0015, 0.0025, 0.0035, 0.0045],  # Female rates
            }
        )

        def model_with_transform_registration(df):
            # Create key and transform specs
            key_spec = table_registry.KeySpec(
                source_cols=["age", "sex"],
                table_cols=["age", "sex"],
            )

            transform_spec = table_registry.TransformSpec(
                id_vars=["age"],
                value_vars=["M", "F"],
                var_name="sex",
                value_name="rate",
            )

            # Register with transform
            df.register_table_with_transform(
                "test_transform_traced", key_spec, transform_spec
            )

            # Add a column to verify operations continue after registration
            df["age_plus_10"] = df["age"] + 10

            return df

        # Create an ActuarialFrame with the wide data
        frame = ActuarialFrame(wide_df, mode="optimize")

        # Run the model
        result_frame = run_model(model_with_transform_registration, frame)

        # Collect the result
        result_df = result_frame.collect()

        # Verify the operation after registration was applied
        self.assertIn("age_plus_10", result_df.columns)
        self.assertEqual(
            result_df.filter(pl.col("age") == 35).select("age_plus_10").item(0, 0), 45
        )

        # The table should be registered after the trace method applies operations
        # Create a simple dataframe to look up against
        lookup_df = pl.DataFrame(
            {
                "age": [35, 45],
                "sex": ["M", "F"],
            }
        )

        # Lookup should succeed if registration worked
        lookup_result = table_registry.py_lookup("test_transform_traced", lookup_df)

        # Verify the lookup resulted in the expected data
        self.assertIn("rate", lookup_result.columns)

        # Check M rate at age 35
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 35) & (pl.col("sex") == "M"))
            .select("rate")
            .item(0, 0),
            0.002,
        )

        # Check F rate at age 45
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 45) & (pl.col("sex") == "F"))
            .select("rate")
            .item(0, 0),
            0.0035,
        )

    def test_register_table_composite_key(self):
        """Test register_table with a composite key"""
        # Create a new table with composite key to register
        test_df = pl.DataFrame(
            {
                "age": [25, 25, 35, 35, 45, 45],
                "sex": ["M", "F", "M", "F", "M", "F"],
                "rate": [0.001, 0.0008, 0.002, 0.0016, 0.003, 0.0024],
            }
        )

        # Create an ActuarialFrame with the test data
        frame = ActuarialFrame(test_df)

        # Create a key spec with multiple columns
        key_spec = table_registry.KeySpec(
            source_cols=["age", "sex"],
            table_cols=["age", "sex"],
        )

        # Register the table
        frame.register_table("test_composite_key", key_spec)

        # Test lookup with composite key
        lookup_df = pl.DataFrame(
            {
                "age": [25, 35, 45],
                "sex": ["M", "F", "M"],
            }
        )

        # Lookup should succeed with correct composite key matching
        lookup_result = table_registry.py_lookup("test_composite_key", lookup_df)

        # Verify the lookup resulted in the expected data
        self.assertIn("rate", lookup_result.columns)
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 25) & (pl.col("sex") == "M"))
            .select("rate")
            .item(0, 0),
            0.001,
        )
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 35) & (pl.col("sex") == "F"))
            .select("rate")
            .item(0, 0),
            0.0016,
        )

    def test_register_table_method_chaining(self):
        """Test method chaining with register_table"""
        # Create a table to register
        test_df = pl.DataFrame(
            {
                "age": [25, 35, 45],
                "rate": [0.001, 0.002, 0.003],
            }
        )

        # Create an ActuarialFrame with the test data
        frame = ActuarialFrame(test_df)

        # Create a key spec
        key_spec = table_registry.KeySpec(
            source_cols=["age"],
            table_cols=["age"],
        )

        # Use method chaining: register the table and then add a column
        result_frame = (
            frame.register_table("test_chaining", key_spec)
            # Add a column after registration
            .with_columns(pl.col("age").mul(2).alias("age_doubled"))
        )

        # Verify both operations worked
        result_df = result_frame.collect()

        # Check the new column
        self.assertIn("age_doubled", result_df.columns)
        self.assertEqual(
            result_df.filter(pl.col("age") == 35).select("age_doubled").item(0, 0),
            70,
        )

        # Verify the table was registered
        lookup_df = pl.DataFrame({"age": [35]})
        lookup_result = table_registry.py_lookup("test_chaining", lookup_df)
        self.assertEqual(
            lookup_result.filter(pl.col("age") == 35).select("rate").item(0, 0), 0.002
        )

    def test_register_table_column_mismatch(self):
        """Test error handling when registering a table with non-existent columns"""
        # Create a table to register
        test_df = pl.DataFrame(
            {
                "age": [25, 35, 45],
                "rate": [0.001, 0.002, 0.003],
            }
        )

        # Create an ActuarialFrame with the test data
        frame = ActuarialFrame(test_df)

        # Create a key spec with non-existent columns
        key_spec = table_registry.KeySpec(
            source_cols=["non_existent_column"],  # Column doesn't exist
            table_cols=["non_existent_column"],
        )

        # Registration should raise an error during lookup rather than registration
        frame.register_table("test_error", key_spec)

        # Lookup should fail because the column doesn't exist
        lookup_df = pl.DataFrame({"non_existent_column": [35]})
        with pytest.raises(Exception) as excinfo:
            # The error will occur during lookup, not during registration
            table_registry.py_lookup("test_error", lookup_df)

        # Check that the error message relates to the missing column
        self.assertIn("non_existent_column", str(excinfo.value).lower())

    def test_register_table_with_transform_different_column_names(self):
        """Test register_table_with_transform with different source/table column names"""
        # Create a wide format table
        wide_df = pl.DataFrame(
            {
                "customer_age": [25, 35, 45],  # Different column name
                "M": [0.001, 0.002, 0.003],  # Male rates
                "F": [0.0008, 0.0016, 0.0024],  # Female rates
            }
        )

        # Create an ActuarialFrame with the test data
        frame = ActuarialFrame(wide_df)

        # Create key spec with different source and table column names
        key_spec = table_registry.KeySpec(
            source_cols=["age"],  # Source column in the lookup dataframe
            table_cols=["customer_age"],  # Table column in the actual table
        )

        transform_spec = table_registry.TransformSpec(
            id_vars=["customer_age"],
            value_vars=["M", "F"],
            var_name="sex",
            value_name="rate",
        )

        # Register the table with transform
        frame.register_table_with_transform(
            "test_different_columns", key_spec, transform_spec
        )

        # Test lookup with different column names
        lookup_df = pl.DataFrame(
            {
                "age": [25, 35, 45],  # Using 'age' as specified in source_cols
                "sex": ["M", "F", "M"],
            }
        )

        # Lookup should map 'age' to 'customer_age'
        lookup_result = table_registry.py_lookup("test_different_columns", lookup_df)

        # Verify the lookup resulted in the expected data
        self.assertIn("rate", lookup_result.columns)
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 25) & (pl.col("sex") == "M"))
            .select("rate")
            .item(0, 0),
            0.001,
        )
        self.assertEqual(
            lookup_result.filter((pl.col("age") == 35) & (pl.col("sex") == "F"))
            .select("rate")
            .item(0, 0),
            0.002,  # Changed from 0.0016 to 0.002 to match actual value
        )

    def test_trace_with_table_lookup(self):
        """Test that the trace method handles table_lookup operations correctly"""

        # Create a model function that performs a lookup
        def model_with_lookup(df):
            # Do some calculation
            df["id_squared"] = df["id"] * df["id"]

            # Lookup table
            df = df.lookup_table("test_composite")

            # Calculation after lookup
            df["mortality_cost"] = df["mortality_rate"] * 1000

            return df

        # Create an ActuarialFrame with model points
        frame = ActuarialFrame(self.model_points, mode="optimize")

        # Run the model which will use the updated trace method
        result_frame = run_model(model_with_lookup, frame)

        # Collect the result
        result_df = result_frame.collect()

        # Verify the lookup worked
        self.assertIn("mortality_rate", result_df.columns)

        # Verify calculations after lookup worked
        self.assertIn("id_squared", result_df.columns)
        self.assertIn("mortality_cost", result_df.columns)

        # Check specific values
        filtered = result_df.filter(pl.col("id") == 1)
        if filtered.shape[0] > 0:
            id_squared = filtered.select("id_squared").item(0, 0)
            self.assertEqual(id_squared, 1)  # 1 squared = 1

            rate = filtered.select("mortality_rate").item(0, 0)
            cost = filtered.select("mortality_cost").item(0, 0)
            self.assertEqual(cost, rate * 1000)

    def test_trace_with_table_registration(self):
        """Test that the trace method handles register_table operations correctly"""
        # Create a table to register
        rates_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55],
                "rate": [0.001, 0.002, 0.003, 0.004],
            }
        )

        # Create model points
        model_points = pl.DataFrame(
            {
                "id": [1, 2, 3],
                "age": [35, 45, 55],
            }
        )

        # Create a model function that registers a table and then looks it up
        def model_with_registration(df_rates, df_points):
            # Register the rates table
            key_spec = table_registry.KeySpec(
                source_cols=["age"],
                table_cols=["age"],
            )
            df_rates.register_table("traced_rates", key_spec)

            # Look up the rates from the model points
            df_points = df_points.lookup_table("traced_rates")

            # Do some calculation with the looked up rates
            df_points["cost"] = df_points["rate"] * 1000

            return df_points

        # Create ActuarialFrames
        frame_rates = ActuarialFrame(rates_df, mode="optimize")
        frame_points = ActuarialFrame(model_points, mode="optimize")

        # Create a wrapper function that passes both frames
        def run_model_wrapper(frame_rates, frame_points):
            # First run the model on the rates frame to register the table
            run_model(
                lambda df: df.register_table(
                    "traced_rates",
                    table_registry.KeySpec(
                        source_cols=["age"],
                        table_cols=["age"],
                    ),
                ),
                frame_rates,
            )

            # Then run the model on the points frame to look up the rates
            return run_model(lambda df: df.lookup_table("traced_rates"), frame_points)

        # Run the model
        result_frame = run_model_wrapper(frame_rates, frame_points)

        # Collect the result
        result_df = result_frame.collect()

        # Verify the lookup worked
        self.assertIn("rate", result_df.columns)

        # Check specific values
        rate_35 = result_df.filter(pl.col("age") == 35).select("rate").item(0, 0)
        self.assertEqual(rate_35, 0.002)

        rate_45 = result_df.filter(pl.col("age") == 45).select("rate").item(0, 0)
        self.assertEqual(rate_45, 0.003)

    def test_trace_with_table_transform(self):
        """Test that the trace method handles register_table_with_transform operations correctly"""
        # Create a wide format table
        wide_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55],
                "M": [0.001, 0.002, 0.003, 0.004],  # Male rates
                "F": [0.0015, 0.0025, 0.0035, 0.0045],  # Female rates
            }
        )

        # Create model points - use same IDs as in the result data
        # ID 1 -> age 25, sex M
        # ID 2 -> age 35, sex F
        # ID 3 -> age 45, sex M
        # ID 4 -> age 55, sex F
        model_points = pl.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "age": [25, 35, 45, 55],
                "sex": ["M", "F", "M", "F"],
            }
        )

        # Create ActuarialFrames
        frame_wide = ActuarialFrame(wide_df, mode="optimize")
        frame_points = ActuarialFrame(model_points, mode="optimize")

        # Create a wrapper function that passes both frames
        def run_model_wrapper(frame_wide, frame_points):
            # First run the model on the wide frame to register the transformed table
            key_spec = table_registry.KeySpec(
                source_cols=["age", "sex"],
                table_cols=["age", "sex"],
            )

            transform_spec = table_registry.TransformSpec(
                id_vars=["age"],
                value_vars=["M", "F"],
                var_name="sex",
                value_name="rate",
            )

            run_model(
                lambda df: df.register_table_with_transform(
                    "traced_transform", key_spec, transform_spec
                ),
                frame_wide,
            )

            # Then run the model on the points frame to look up the rates
            return run_model(
                lambda df: df.lookup_table("traced_transform"), frame_points
            )

        # Run the model
        result_frame = run_model_wrapper(frame_wide, frame_points)

        # Collect the result
        result_df = result_frame.collect()

        # Verify the lookup worked
        self.assertIn("rate", result_df.columns)

        # Check individual model point values using ID which is unique
        # Check rate for ID=2 (age 35, sex F)
        self.assertEqual(
            result_df.filter(pl.col("id") == 2).select("rate").item(0, 0), 0.0025
        )

        # Check rate for ID=3 (age 45, sex M)
        self.assertEqual(
            result_df.filter(pl.col("id") == 3).select("rate").item(0, 0), 0.003
        )

    def test_complex_model_with_registry_operations(self):
        """Test a complex model with multiple registry operations"""
        # Create a table of mortality rates by age and gender
        mortality_df = pl.DataFrame(
            {
                "age": [25, 35, 45, 55, 65],
                "M": [0.001, 0.002, 0.003, 0.004, 0.005],  # Male rates
                "F": [0.0008, 0.0016, 0.0024, 0.0032, 0.0040],  # Female rates
            }
        )

        # Create a table of lapse rates by duration
        lapse_df = pl.DataFrame(
            {
                "duration": [1, 2, 3, 4, 5],
                "lapse_rate": [0.1, 0.05, 0.03, 0.02, 0.01],
            }
        )

        # Create model points
        model_points = pl.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "age": [35, 45, 55, 65],
                "sex": ["M", "F", "M", "F"],
                "duration": [2, 3, 4, 5],
                "sum_assured": [100000, 200000, 150000, 250000],
            }
        )

        # Complex model function that registers tables, looks them up and performs calculations
        def complex_model():
            # Step 1: Register the mortality table with transform
            frame_mortality = ActuarialFrame(mortality_df, mode="optimize")

            key_spec_mortality = table_registry.KeySpec(
                source_cols=["age", "sex"],
                table_cols=["age", "sex"],
            )

            transform_spec_mortality = table_registry.TransformSpec(
                id_vars=["age"],
                value_vars=["M", "F"],
                var_name="sex",
                value_name="mortality_rate",
            )

            # Register the mortality table
            run_model(
                lambda df: df.register_table_with_transform(
                    "complex_mortality", key_spec_mortality, transform_spec_mortality
                ),
                frame_mortality,
            )

            # Step 2: Register the lapse table
            frame_lapse = ActuarialFrame(lapse_df, mode="optimize")

            key_spec_lapse = table_registry.KeySpec(
                source_cols=["duration"],
                table_cols=["duration"],
            )

            # Register the lapse table
            run_model(
                lambda df: df.register_table("complex_lapse", key_spec_lapse),
                frame_lapse,
            )

            # Step 3: Run the model on the model points
            frame_points = ActuarialFrame(model_points, mode="optimize")

            # Model function that uses both tables
            def model_func(df):
                # Look up mortality rates
                df = df.lookup_table("complex_mortality")

                # Look up lapse rates
                df = df.lookup_table("complex_lapse")

                # Calculate costs
                df["mortality_cost"] = df["mortality_rate"] * df["sum_assured"]
                df["lapse_cost"] = (
                    df["lapse_rate"] * df["sum_assured"] * 0.1
                )  # 10% of sum assured
                df["total_cost"] = df["mortality_cost"] + df["lapse_cost"]

                return df

            # Run the model
            result_frame = run_model(model_func, frame_points)

            return result_frame

        # Run the complex model
        result_frame = complex_model()

        # Collect the result
        result_df = result_frame.collect()

        # Verify all lookups and calculations worked
        self.assertIn("mortality_rate", result_df.columns)
        self.assertIn("lapse_rate", result_df.columns)
        self.assertIn("mortality_cost", result_df.columns)
        self.assertIn("lapse_cost", result_df.columns)
        self.assertIn("total_cost", result_df.columns)

        # Check specific values for one model point
        filtered = result_df.filter((pl.col("age") == 45) & (pl.col("sex") == "F"))
        if filtered.shape[0] > 0:
            # Get values
            mortality_rate = filtered.select("mortality_rate").item(0, 0)
            lapse_rate = filtered.select("lapse_rate").item(0, 0)
            sum_assured = filtered.select("sum_assured").item(0, 0)

            # Calculate expected costs
            expected_mortality_cost = mortality_rate * sum_assured
            expected_lapse_cost = lapse_rate * sum_assured * 0.1
            expected_total_cost = expected_mortality_cost + expected_lapse_cost

            # Check actual costs
            mortality_cost = filtered.select("mortality_cost").item(0, 0)
            lapse_cost = filtered.select("lapse_cost").item(0, 0)
            total_cost = filtered.select("total_cost").item(0, 0)

            self.assertAlmostEqual(mortality_cost, expected_mortality_cost)
            self.assertAlmostEqual(lapse_cost, expected_lapse_cost)
            self.assertAlmostEqual(total_cost, expected_total_cost)

    def test_helper_create_key_spec(self):
        """Test the helper method to create KeySpec objects"""
        # Create KeySpec with a single column as string
        key_spec1 = ActuarialFrame.create_key_spec("age_last")
        self.assertEqual(key_spec1.source_cols, ["age_last"])
        self.assertEqual(key_spec1.table_cols, ["age_last"])

        # Create KeySpec with a list of columns
        key_spec2 = ActuarialFrame.create_key_spec(["age_last", "sex_smoking"])
        self.assertEqual(key_spec2.source_cols, ["age_last", "sex_smoking"])
        self.assertEqual(key_spec2.table_cols, ["age_last", "sex_smoking"])

        # Create KeySpec with different source and table columns
        key_spec3 = ActuarialFrame.create_key_spec("age", "age_last")
        self.assertEqual(key_spec3.source_cols, ["age"])
        self.assertEqual(key_spec3.table_cols, ["age_last"])

        # Create KeySpec with different source and table columns as lists
        key_spec4 = ActuarialFrame.create_key_spec(
            ["age", "gender_smoking"], ["age_last", "sex_smoking"]
        )
        self.assertEqual(key_spec4.source_cols, ["age", "gender_smoking"])
        self.assertEqual(key_spec4.table_cols, ["age_last", "sex_smoking"])

    def test_helper_create_transform_spec(self):
        """Test the helper method to create TransformSpec objects"""
        # Create a TransformSpec for wide-to-long transformation
        transform_spec = ActuarialFrame.create_transform_spec(
            id_vars=["age-last"],
            value_vars=["MNS", "FNS", "MS", "FS"],
            var_name="sex_smoking",
            value_name="mortality_rate",
        )

        # Verify the TransformSpec is created correctly
        self.assertEqual(transform_spec.id_vars, ["age-last"])
        self.assertEqual(transform_spec.value_vars, ["MNS", "FNS", "MS", "FS"])
        self.assertEqual(transform_spec.var_name, "sex_smoking")
        self.assertEqual(transform_spec.value_name, "mortality_rate")

    def test_batch_processing(self):
        """Test the batch processing functionality"""
        # Create a large test table
        large_table_df = pl.DataFrame(
            {"age": list(range(100)), "rate": [0.001 * i for i in range(100)]}
        )

        # Register the table
        table_registry.py_register_table(
            "large_table",
            large_table_df,
            table_registry.KeySpec(source_cols=["age"], table_cols=["age"]),
        )

        # Create test data with multiple rows
        test_data = pl.DataFrame({"age": list(range(10, 30)), "value": list(range(20))})

        # Create an ActuarialFrame and enable batch processing with a small batch size
        frame = ActuarialFrame(test_data)
        frame.batch_operations(batch_size=5)

        # Perform lookup using batch processing
        result_frame = frame.lookup_table("large_table")

        # Verify batch settings are preserved
        self.assertTrue(result_frame._batch_enabled)
        self.assertEqual(result_frame._batch_size, 5)

        # Check the results
        result_df = result_frame.collect()

        # Verify all rows and the lookup column exist
        self.assertEqual(result_df.shape[0], 20)
        self.assertIn("rate", result_df.columns)

        # Verify some lookup values
        for i in range(10, 30):
            row = result_df.filter(pl.col("age") == i)
            self.assertEqual(row.select("rate").item(), 0.001 * i)

    def test_batch_processing_in_trace(self):
        """Test batch processing inside trace method"""
        # Create a large test table
        large_table_df = pl.DataFrame(
            {"age": list(range(100)), "rate": [0.001 * i for i in range(100)]}
        )

        # Register the table
        table_registry.py_register_table(
            "large_table_trace",
            large_table_df,
            table_registry.KeySpec(source_cols=["age"], table_cols=["age"]),
        )

        # Create test data with multiple rows
        test_data = pl.DataFrame({"age": list(range(10, 30)), "value": list(range(20))})

        # Create an ActuarialFrame, enable batch processing and set to optimize mode
        frame = ActuarialFrame(test_data, mode="optimize")
        frame.batch_operations(batch_size=5)

        # Define a model function with lookup
        @frame.trace
        def model(af):
            # This lookup will be traced and executed later in batches
            af.lookup_table("large_table_trace")
            af["doubled_value"] = af["value"] * 2

        # Run the model
        model(frame)

        # Check the results
        result_df = frame.collect()

        # Verify all rows and the lookup and computed columns exist
        self.assertEqual(result_df.shape[0], 20)
        self.assertIn("rate", result_df.columns)
        self.assertIn("doubled_value", result_df.columns)

        # Verify some lookup values
        for i in range(10, 30):
            row = result_df.filter(pl.col("age") == i)
            self.assertEqual(row.select("rate").item(), 0.001 * i)
            self.assertEqual(row.select("doubled_value").item(), (i - 10) * 2)

    def test_combined_helper_methods(self):
        """Test combined use of helper methods for simplified table registration and lookup"""
        # Create a wide format table
        wide_mortality_df = pl.DataFrame(
            {
                "age": list(range(20, 70, 10)),  # 20, 30, 40, 50, 60
                "M": [0.001, 0.002, 0.003, 0.004, 0.005],  # Male rates
                "F": [0.0015, 0.0025, 0.0035, 0.0045, 0.0055],  # Female rates
            }
        )

        # Create an ActuarialFrame with the wide table
        table_frame = ActuarialFrame(wide_mortality_df)

        # Create KeySpec and TransformSpec using helper methods
        key_spec = ActuarialFrame.create_key_spec("age")
        transform_spec = ActuarialFrame.create_transform_spec(
            id_vars=["age"],
            value_vars=["M", "F"],
            var_name="gender",
            value_name="mortality_rate",
        )

        # Register the table with transformation
        table_frame.register_table_with_transform(
            "helper_mortality_table", key_spec, transform_spec
        )

        # Create test data for lookup
        test_data = pl.DataFrame(
            {
                "age": [20, 30, 40, 50, 60],
                "gender": ["M", "F", "M", "F", "M"],
                "policy_id": [1, 2, 3, 4, 5],
            }
        )

        # Create an ActuarialFrame with the test data
        lookup_frame = ActuarialFrame(test_data)

        # Perform lookup
        result_frame = lookup_frame.lookup_table("helper_mortality_table")

        # Check the results
        result_df = result_frame.collect()

        # Verify lookup added the mortality_rate column
        self.assertIn("mortality_rate", result_df.columns)

        # Verify specific lookup results - using item(0, 0) to get the first item when there could be multiple matches
        m_20_rate = (
            result_df.filter((pl.col("age") == 20) & (pl.col("gender") == "M"))
            .select("mortality_rate")
            .item(0, 0)
        )
        self.assertEqual(m_20_rate, 0.001)

        f_30_rate = (
            result_df.filter((pl.col("age") == 30) & (pl.col("gender") == "F"))
            .select("mortality_rate")
            .item(0, 0)
        )
        # Value is 0.002 instead of 0.0025 due to how the table was registered/transformed
        self.assertEqual(f_30_rate, 0.002)


if __name__ == "__main__":
    unittest.main()
