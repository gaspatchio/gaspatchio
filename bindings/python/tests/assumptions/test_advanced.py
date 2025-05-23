"""
Tests for advanced features and comprehensive parameter validation.

This module tests value_vars selective melting, metadata storage and retrieval,
comprehensive parameter validation, edge cases, and performance with large tables.
"""

import time

import polars as pl
import pytest
from gaspatchio_core.assumptions import (
    assumption_lookup,
    get_table_metadata,
    list_tables_with_metadata,
    load_assumptions,
)


class TestValueVarsSelectiveMelting:
    """Test value_vars parameter for selective column melting."""

    def test_value_vars_basic_selective_melting(self):
        """Test basic selective melting with value_vars."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "Male": [0.001, 0.0011, 0.0012],
                "Female": [0.0008, 0.0009, 0.001],
                "NonSmoker": [0.0005, 0.0006, 0.0007],
                "Smoker": [0.002, 0.0021, 0.0022],
            }
        )

        # Only melt gender columns
        result = load_assumptions(
            "selective_gender_test",
            df,
            id="Age",
            value_vars=["Male", "Female"],
            value="rate",
        )

        assert len(result) == 6  # 3 ages × 2 genders
        assert result.columns == ["Age", "variable", "rate"]

        # Check that only specified variables are present
        variables = sorted(result["variable"].unique().to_list())
        assert variables == ["Female", "Male"]

        # Verify lookup works
        test_df = pl.DataFrame({"Age": [30], "variable": ["Male"]})
        lookup_result = test_df.with_columns(
            assumption_lookup(
                "Age", "variable", table_name="selective_gender_test"
            ).alias("rate")
        )
        assert lookup_result["rate"].item() == 0.001

    def test_value_vars_with_mixed_column_types(self):
        """Test value_vars with mixed numeric and text columns."""
        df = pl.DataFrame(
            {
                "Product": ["Term", "Whole", "Universal"],
                "Age": [30, 31, 32],
                "Male": [0.001, 0.0011, 0.0012],
                "Female": [0.0008, 0.0009, 0.001],
                "Description": ["Standard", "Preferred", "Super Preferred"],
                "Smoker": [0.002, 0.0021, 0.0022],
            }
        )

        # Select only specific numeric columns, ignoring others
        result = load_assumptions(
            "mixed_types_selective",
            df,
            id=["Product", "Age"],
            value_vars=["Male", "Female"],
            value="mortality_rate",
        )

        assert len(result) == 6  # 3 products × 2 genders
        assert result.columns == ["Product", "Age", "variable", "mortality_rate"]

        # Verify lookup with multiple id columns
        test_df = pl.DataFrame(
            {"Product": ["Term"], "Age": [30], "variable": ["Female"]}
        )
        lookup_result = test_df.with_columns(
            assumption_lookup(
                "Product", "Age", "variable", table_name="mixed_types_selective"
            ).alias("mortality_rate")
        )
        assert lookup_result["mortality_rate"].item() == 0.0008

    def test_value_vars_single_column_forces_wide_table(self):
        """Test that value_vars with single column forces wide table treatment."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "Rate": [0.001, 0.0011, 0.0012],
                "Description": ["A", "B", "C"],  # Text column, ignored
            }
        )

        # Force wide table treatment by specifying value_vars (even with single column)
        result = load_assumptions(
            "forced_wide_single", df, id="Age", value_vars=["Rate"], value="qx"
        )

        # Should create wide table format (not curve)
        assert result.columns == ["Age", "variable", "qx"]
        assert len(result) == 3

        # All variable values should be "Rate"
        assert result["variable"].unique().to_list() == ["Rate"]

    def test_value_vars_with_overflow_expansion(self):
        """Test value_vars combined with overflow expansion."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "Duration_1": [0.001, 0.0011],
                "Duration_2": [0.0008, 0.0009],
                "Duration_3": [0.0005, 0.0006],
                "Ultimate": [0.0003, 0.0004],
                "Extra_Column": [0.999, 0.998],  # Should be ignored
            }
        )

        # Selective melting with overflow
        result = load_assumptions(
            "selective_with_overflow",
            df,
            id="Age",
            value_vars=["Duration_1", "Duration_2", "Duration_3", "Ultimate"],
            overflow="Ultimate",
            max_overflow=5,
            value="mortality",
        )

        # Original: 2 ages × 4 durations = 8 rows
        # Expansion: 2 ages × 2 durations (4, 5) = 4 rows
        # Total: 12 rows
        assert len(result) == 12

        # Verify expansion worked
        expanded_data = result.filter(pl.col("variable").is_in(["4", "5"]))
        assert len(expanded_data) == 4

    def test_value_vars_error_missing_columns(self):
        """Test error when value_vars contains non-existent columns."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "Male": [0.001, 0.0011],
                "Female": [0.0008, 0.0009],
            }
        )

        with pytest.raises(
            ValueError,
            match="Specified value_vars columns not found in DataFrame: \\['Missing', 'AlsoMissing'\\]",
        ):
            load_assumptions(
                "missing_columns_test",
                df,
                value_vars=["Male", "Missing", "AlsoMissing"],
            )

    def test_value_vars_empty_list_error(self):
        """Test error when value_vars is an empty list."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "Male": [0.001, 0.0011],
                "Female": [0.0008, 0.0009],
            }
        )

        with pytest.raises(ValueError, match="No columns found to use as values"):
            load_assumptions("empty_value_vars_test", df, value_vars=[])


class TestMetadataSupport:
    """Test metadata storage and retrieval functionality."""

    def test_metadata_storage_basic(self):
        """Test basic metadata storage and retrieval."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        metadata = {
            "source": "SOA Mortality Table 2020",
            "version": "1.0",
            "description": "Standard mortality rates for life insurance",
            "date_created": "2024-01-15",
        }

        load_assumptions("metadata_test_basic", df, metadata=metadata, value="qx")

        # Retrieve metadata
        retrieved_metadata = get_table_metadata("metadata_test_basic")
        assert retrieved_metadata == metadata

        # Verify it's a copy, not the original
        retrieved_metadata["modified"] = True
        original_retrieved = get_table_metadata("metadata_test_basic")
        assert "modified" not in original_retrieved

    def test_metadata_storage_wide_table(self):
        """Test metadata storage with wide tables."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "1": [0.001, 0.0011],
                "2": [0.0008, 0.0009],
                "Ult.": [0.0005, 0.0006],
            }
        )

        metadata = {
            "type": "Select & Ultimate Mortality",
            "select_period": 2,
            "overflow_handling": "expanded_to_200",
            "source_file": "mortality_2020.csv",
        }

        load_assumptions(
            "metadata_wide_test",
            df,
            metadata=metadata,
            overflow="Ult.",
            max_overflow=200,
        )

        retrieved_metadata = get_table_metadata("metadata_wide_test")
        assert retrieved_metadata == metadata

    def test_metadata_none_handling(self):
        """Test tables without metadata."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        load_assumptions("no_metadata_test", df, value="qx")

        # Should return None for tables without metadata
        retrieved_metadata = get_table_metadata("no_metadata_test")
        assert retrieved_metadata is None

    def test_metadata_missing_table(self):
        """Test metadata retrieval for non-existent table."""
        # Should return None for missing tables
        retrieved_metadata = get_table_metadata("table_that_does_not_exist")
        assert retrieved_metadata is None

    def test_metadata_complex_nested_data(self):
        """Test metadata with complex nested data structures."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        complex_metadata = {
            "source_info": {
                "provider": "SOA",
                "table_name": "2012 IAM Basic Table",
                "basis": {
                    "smoker_status": "Combined",
                    "gender": "Unisex",
                },
            },
            "adjustments": [
                {"factor": 0.95, "reason": "Company experience"},
                {"factor": 1.02, "reason": "Margin"},
            ],
            "validation": {
                "checked_by": "John Doe",
                "date": "2024-01-15",
                "status": "approved",
            },
        }

        load_assumptions(
            "complex_metadata_test", df, metadata=complex_metadata, value="qx"
        )

        retrieved_metadata = get_table_metadata("complex_metadata_test")
        assert retrieved_metadata == complex_metadata

    def test_list_tables_with_metadata(self):
        """Test listing all tables with metadata."""
        # Create multiple tables with metadata
        df1 = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})
        df2 = pl.DataFrame({"Duration": [1, 2], "rate": [0.03, 0.035]})

        metadata1 = {"type": "mortality", "version": "1.0"}
        metadata2 = {"type": "interest", "version": "2.0"}

        load_assumptions("table_list_1", df1, metadata=metadata1, value="qx")
        load_assumptions("table_list_2", df2, metadata=metadata2, value="rate")
        load_assumptions("table_list_no_meta", df1, value="qx")  # No metadata

        # List all tables with metadata
        all_metadata = list_tables_with_metadata()

        # Should include tables with metadata, but not the one without
        assert "table_list_1" in all_metadata
        assert "table_list_2" in all_metadata
        assert "table_list_no_meta" not in all_metadata

        assert all_metadata["table_list_1"] == metadata1
        assert all_metadata["table_list_2"] == metadata2


class TestComprehensiveParameterValidation:
    """Test comprehensive parameter validation with various invalid inputs."""

    def test_value_parameter_validation(self):
        """Test value parameter validation."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Invalid value types
        with pytest.raises(ValueError, match="value must be a non-empty string"):
            load_assumptions("value_test_1", df, value="")

        with pytest.raises(ValueError, match="value must be a non-empty string"):
            load_assumptions("value_test_2", df, value="   ")

        with pytest.raises(ValueError, match="value must be a non-empty string"):
            load_assumptions("value_test_3", df, value=123)

        with pytest.raises(ValueError, match="value must be a non-empty string"):
            load_assumptions("value_test_4", df, value=None)

    def test_value_vars_parameter_validation(self):
        """Test value_vars parameter validation."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Invalid value_vars types
        with pytest.raises(
            ValueError, match="value_vars must be a list of column names or None"
        ):
            load_assumptions("value_vars_test_1", df, value_vars="Male")

        with pytest.raises(
            ValueError, match="value_vars must be a list of column names or None"
        ):
            load_assumptions("value_vars_test_2", df, value_vars=123)

        with pytest.raises(
            ValueError, match="value_vars must be a list of column names or None"
        ):
            load_assumptions("value_vars_test_3", df, value_vars={"Male", "Female"})

    def test_max_overflow_parameter_validation(self):
        """Test max_overflow parameter validation."""
        df = pl.DataFrame(
            {"Age": [30, 31], "1": [0.001, 0.0011], "Ult.": [0.0005, 0.0006]}
        )

        # Invalid max_overflow values
        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("max_overflow_test_1", df, max_overflow=0)

        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("max_overflow_test_2", df, max_overflow=-5)

        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("max_overflow_test_3", df, max_overflow=1001)

        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("max_overflow_test_4", df, max_overflow="100")

        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("max_overflow_test_5", df, max_overflow=100.5)

    def test_overflow_parameter_validation(self):
        """Test overflow parameter validation."""
        df = pl.DataFrame(
            {"Age": [30, 31], "1": [0.001, 0.0011], "Ult.": [0.0005, 0.0006]}
        )

        # Invalid overflow types
        with pytest.raises(
            ValueError, match="overflow must be 'auto', a column name string, or None"
        ):
            load_assumptions("overflow_test_1", df, overflow=123)

        with pytest.raises(
            ValueError, match="overflow must be 'auto', a column name string, or None"
        ):
            load_assumptions("overflow_test_2", df, overflow=["Ult."])

        # Valid overflow values should work
        load_assumptions("overflow_test_valid_1", df, overflow="auto")
        load_assumptions("overflow_test_valid_2", df, overflow="Ult.")
        load_assumptions("overflow_test_valid_3", df, overflow=None)

    def test_metadata_parameter_validation(self):
        """Test metadata parameter validation."""
        df = pl.DataFrame({"Age": [30, 31], "qx": [0.001, 0.0011]})

        # Invalid metadata types
        with pytest.raises(ValueError, match="metadata must be a dictionary or None"):
            load_assumptions("metadata_test_1", df, metadata="invalid")

        with pytest.raises(ValueError, match="metadata must be a dictionary or None"):
            load_assumptions("metadata_test_2", df, metadata=123)

        with pytest.raises(ValueError, match="metadata must be a dictionary or None"):
            load_assumptions("metadata_test_3", df, metadata=["item1", "item2"])

        # Valid metadata should work
        load_assumptions("metadata_test_valid", df, metadata={"key": "value"})


class TestEdgeCases:
    """Test edge cases: empty DataFrames, single-row tables, Unicode column names."""

    def test_empty_dataframe_error(self):
        """Test error handling with empty DataFrames."""
        empty_df = pl.DataFrame(schema={"Age": pl.Int32, "qx": pl.Float64})

        with pytest.raises(ValueError, match="DataFrame is empty"):
            load_assumptions("empty_df_test", empty_df)

    def test_single_row_table_curve(self):
        """Test loading single-row curve table."""
        df = pl.DataFrame({"Age": [30], "qx": [0.001]})

        result = load_assumptions("single_row_curve", df, value="qx")

        assert len(result) == 1
        assert result.columns == ["Age", "qx"]

        # Test lookup
        test_df = pl.DataFrame({"Age": [30]})
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", table_name="single_row_curve").alias("qx")
        )
        assert lookup_result["qx"].item() == 0.001

    def test_single_row_table_wide(self):
        """Test loading single-row wide table."""
        df = pl.DataFrame({"Age": [30], "1": [0.001], "2": [0.0008], "Ult.": [0.0005]})

        result = load_assumptions(
            "single_row_wide", df, overflow="Ult.", max_overflow=5
        )

        # Should have expanded data
        assert len(result) > 3  # Original 3 + expansions

        # Test lookup for expanded duration
        test_df = pl.DataFrame({"Age": [30], "variable": ["4"]})
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", "variable", table_name="single_row_wide").alias(
                "rate"
            )
        )
        assert lookup_result["rate"].item() == 0.0005  # Should match Ult. value

    def test_unicode_column_names(self):
        """Test tables with Unicode column names."""
        df = pl.DataFrame(
            {
                "年齢": [30, 31, 32],  # "Age" in Japanese
                "男性": [0.001, 0.0011, 0.0012],  # "Male" in Japanese
                "女性": [0.0008, 0.0009, 0.001],  # "Female" in Japanese
                "Ültimate": [0.0005, 0.0006, 0.0007],  # With diacritic
            }
        )

        result = load_assumptions(
            "unicode_test",
            df,
            id="年齢",
            value_vars=["男性", "女性", "Ültimate"],
            value="死亡率",  # "Mortality rate" in Japanese
        )

        assert len(result) == 9  # 3 ages × 3 variables
        assert result.columns == ["年齢", "variable", "死亡率"]

        # Test lookup with Unicode
        test_df = pl.DataFrame({"年齢": [30], "variable": ["男性"]})
        lookup_result = test_df.with_columns(
            assumption_lookup("年齢", "variable", table_name="unicode_test").alias(
                "死亡率"
            )
        )
        assert lookup_result["死亡率"].item() == 0.001

    def test_special_column_names(self):
        """Test tables with special characters in column names."""
        df = pl.DataFrame(
            {
                "Age (Years)": [30, 31],
                "Rate-Male": [0.001, 0.0011],
                "Rate/Female": [0.0008, 0.0009],
                "Rate@Unisex": [0.0009, 0.001],
                "Rate#Ultimate": [0.0005, 0.0006],
            }
        )

        result = load_assumptions(
            "special_chars_test",
            df,
            id="Age (Years)",
            value_vars=["Rate-Male", "Rate/Female", "Rate@Unisex", "Rate#Ultimate"],
            value="mortality_rate",
        )

        assert len(result) == 8  # 2 ages × 4 variables

        # Test lookup with special characters
        test_df = pl.DataFrame({"Age (Years)": [30], "variable": ["Rate-Male"]})
        lookup_result = test_df.with_columns(
            assumption_lookup(
                "Age (Years)", "variable", table_name="special_chars_test"
            ).alias("mortality_rate")
        )
        assert lookup_result["mortality_rate"].item() == 0.001

    def test_very_large_values(self):
        """Test with very large numeric values."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "1": [1e10, 1.1e10],
                "2": [2e10, 2.1e10],
                "Ult.": [5e10, 5.1e10],
            }
        )

        result = load_assumptions(
            "large_values_test", df, overflow="Ult.", max_overflow=5
        )

        # Should handle large values correctly
        test_df = pl.DataFrame({"Age": [30], "variable": ["1"]})
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", "variable", table_name="large_values_test").alias(
                "rate"
            )
        )
        assert lookup_result["rate"].item() == 1e10

    def test_very_small_values(self):
        """Test with very small numeric values."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "qx": [1e-10, 1.1e-10],
            }
        )

        result = load_assumptions("small_values_test", df, value="qx")

        # Should handle small values correctly
        test_df = pl.DataFrame({"Age": [30]})
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", table_name="small_values_test").alias("qx")
        )
        assert lookup_result["qx"].item() == 1e-10


class TestPerformanceWithLargeTables:
    """Test performance with large tables (1M+ rows)."""

    def test_large_curve_table_performance(self):
        """Test performance with large curve table."""
        # Create a large curve table (100K rows)
        n_rows = 100_000
        df = pl.DataFrame(
            {
                "Age": list(range(0, n_rows)),
                "qx": [0.001 + i * 1e-8 for i in range(n_rows)],
            }
        )

        start_time = time.time()
        result = load_assumptions("large_curve_test", df, value="qx")
        load_time = time.time() - start_time

        assert len(result) == n_rows
        # Should complete in reasonable time (under 5 seconds for 100K rows)
        assert load_time < 5.0

        # Test lookup performance
        start_time = time.time()
        test_df = pl.DataFrame({"Age": [50000]})
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", table_name="large_curve_test").alias("qx")
        )
        lookup_time = time.time() - start_time

        # Lookup should be very fast (under 10ms)
        assert lookup_time < 0.01
        assert lookup_result["qx"].item() == pytest.approx(0.001 + 50000 * 1e-8)

    def test_large_wide_table_performance(self):
        """Test performance with large wide table."""
        # Create a moderately large wide table (10K ages × 5 durations = 50K final rows)
        n_ages = 10_000
        df = pl.DataFrame(
            {
                "Age": list(range(0, n_ages)),
                "1": [0.001] * n_ages,
                "2": [0.0008] * n_ages,
                "3": [0.0005] * n_ages,
                "4": [0.0003] * n_ages,
                "5": [0.0002] * n_ages,
            }
        )

        start_time = time.time()
        result = load_assumptions("large_wide_test", df)
        load_time = time.time() - start_time

        assert len(result) == n_ages * 5  # 50K rows
        # Should complete in reasonable time
        assert load_time < 10.0

        # Test lookup performance
        start_time = time.time()
        test_df = pl.DataFrame({"Age": [5000], "variable": ["3"]})
        lookup_result = test_df.with_columns(
            assumption_lookup("Age", "variable", table_name="large_wide_test").alias(
                "rate"
            )
        )
        lookup_time = time.time() - start_time

        # Lookup should be very fast
        assert lookup_time < 0.01
        assert lookup_result["rate"].item() == 0.0005

    def test_overflow_expansion_memory_efficiency(self):
        """Test memory efficiency with large overflow expansion."""
        # Create table that expands significantly
        df = pl.DataFrame(
            {
                "Age": list(range(20, 30)),  # 10 ages
                "1": [0.001] * 10,
                "2": [0.0008] * 10,
                "Ult.": [0.0005] * 10,
            }
        )

        # Expand to 100 durations
        start_time = time.time()
        result = load_assumptions(
            "memory_efficiency_test", df, overflow="Ult.", max_overflow=100
        )
        load_time = time.time() - start_time

        # Should create: 10 ages × (3 original + 98 expanded) = 1010 rows
        assert len(result) == 1010

        # Should complete in reasonable time
        assert load_time < 2.0

        # Verify expansion worked correctly
        test_df = pl.DataFrame({"Age": [25], "variable": ["99"]})
        lookup_result = test_df.with_columns(
            assumption_lookup(
                "Age", "variable", table_name="memory_efficiency_test"
            ).alias("rate")
        )
        assert lookup_result["rate"].item() == 0.0005  # Should match Ult. value

    def test_concurrent_large_table_loading(self):
        """Test loading multiple large tables sequentially."""
        # This tests that registry can handle multiple large tables without issues

        tables_data = []
        for i in range(3):
            n_rows = 20_000
            df = pl.DataFrame(
                {
                    "Age": list(range(0, n_rows)),
                    "rate": [0.001 + i * 0.0001] * n_rows,
                }
            )
            tables_data.append((f"concurrent_large_{i}", df))

        start_time = time.time()
        for name, df in tables_data:
            load_assumptions(name, df, value="rate")
        total_load_time = time.time() - start_time

        # Should handle all tables in reasonable time
        assert total_load_time < 15.0

        # Verify all tables are accessible
        for i, (name, _) in enumerate(tables_data):
            test_df = pl.DataFrame({"Age": [10000]})
            lookup_result = test_df.with_columns(
                assumption_lookup("Age", table_name=name).alias("rate")
            )
            expected_rate = 0.001 + i * 0.0001
            assert lookup_result["rate"].item() == pytest.approx(expected_rate)
