"""
Test comprehensive error handling for assumption loading.

This module tests all error conditions and edge cases for the assumption
loading system, ensuring proper error messages and handling of various
failure modes.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest
from gaspatchio_core.assumptions._loader import load_assumptions


class TestFileIOErrors:
    """Test file I/O error handling with helpful messages."""

    def test_file_not_found_error(self):
        """Test file not found with helpful suggestions."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_assumptions("test", "nonexistent_file.csv")

        error_msg = str(exc_info.value)
        assert "Source file not found: nonexistent_file.csv" in error_msg
        assert "Check the file path is correct" in error_msg
        assert "current working directory" in error_msg
        assert "Use absolute path" in error_msg
        assert "Check file permissions" in error_msg

    def test_unsupported_file_format(self):
        """Test unsupported file format with suggestions."""
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(b"fake excel data")
            tmp_path = tmp.name

        try:
            with pytest.raises(ValueError) as exc_info:
                load_assumptions("test", tmp_path)

            error_msg = str(exc_info.value)
            assert "Unsupported file format: .xlsx" in error_msg
            assert "Supported formats: .csv, .parquet" in error_msg
            assert "Convert your data to CSV or Parquet format" in error_msg
            assert "Use pl.DataFrame() to create data programmatically" in error_msg
        finally:
            Path(tmp_path).unlink()

    def test_corrupted_csv_file(self):
        """Test corrupted CSV file with suggestions."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp:
            tmp.write("invalid,csv\ndata,with,too,many,columns\n")
            tmp_path = tmp.name

        try:
            with pytest.raises(ValueError) as exc_info:
                load_assumptions("test", tmp_path)

            error_msg = str(exc_info.value)
            assert "Failed to read CSV file" in error_msg
            assert "Check the CSV format is valid" in error_msg
            assert "Ensure text encoding is UTF-8" in error_msg
            assert "Try opening the file in a text editor" in error_msg
        finally:
            Path(tmp_path).unlink()

    def test_corrupted_parquet_file(self):
        """Test corrupted Parquet file with suggestions."""
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
            tmp.write(b"not a parquet file")
            tmp_path = tmp.name

        try:
            with pytest.raises(ValueError) as exc_info:
                load_assumptions("test", tmp_path)

            error_msg = str(exc_info.value)
            assert "Failed to read Parquet file" in error_msg
            assert "Check the Parquet file is not corrupted" in error_msg
            assert "compatible Parquet version" in error_msg
            assert "different Parquet reader" in error_msg
        finally:
            Path(tmp_path).unlink()


class TestParameterValidation:
    """Test parameter validation with helpful error messages."""

    def test_empty_table_name(self):
        """Test empty table name validation."""
        df = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.002]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("", df)

        error_msg = str(exc_info.value)
        assert "name must be a non-empty string" in error_msg
        assert "Use descriptive names like 'mortality_2012'" in error_msg
        assert "Avoid empty strings" in error_msg

    def test_whitespace_only_table_name(self):
        """Test whitespace-only table name validation."""
        df = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.002]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("   ", df)

        error_msg = str(exc_info.value)
        assert "name must be a non-empty string" in error_msg

    def test_empty_value_column_name(self):
        """Test empty value column name validation."""
        df = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.002]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, value="")

        error_msg = str(exc_info.value)
        assert "value must be a non-empty string" in error_msg
        assert "Use descriptive names like 'rate', 'qx'" in error_msg

    def test_invalid_value_vars_type(self):
        """Test invalid value_vars type validation."""
        df = pl.DataFrame(
            {"age": [20, 21], "male": [0.001, 0.002], "female": [0.0008, 0.0015]}
        )

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, value_vars="male")  # Should be list

        error_msg = str(exc_info.value)
        assert "value_vars must be a list of column names or None" in error_msg
        assert "value_vars=['Male', 'Female']" in error_msg

    def test_invalid_max_overflow_range(self):
        """Test max_overflow validation."""
        df = pl.DataFrame({"age": [20, 21], "1": [0.001, 0.002], "2": [0.0008, 0.0015]})

        # Test too small
        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, max_overflow=0)

        error_msg = str(exc_info.value)
        assert "max_overflow must be an integer between 1 and 1000" in error_msg
        assert "Use 200 for typical actuarial projections" in error_msg

        # Test too large
        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, max_overflow=1001)

        assert "max_overflow must be an integer between 1 and 1000" in str(
            exc_info.value
        )

    def test_invalid_overflow_parameter(self):
        """Test invalid overflow parameter validation."""
        df = pl.DataFrame(
            {"age": [20, 21], "1": [0.001, 0.002], "Ultimate": [0.0008, 0.0015]}
        )

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, overflow=123)  # Should be string or None

        error_msg = str(exc_info.value)
        assert "overflow must be 'auto', a column name string, or None" in error_msg
        assert "overflow='auto' for automatic detection" in error_msg
        assert "overflow='Ultimate' for explicit overflow column" in error_msg

    def test_invalid_metadata_type(self):
        """Test invalid metadata type validation."""
        df = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.002]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, metadata="should be dict")

        error_msg = str(exc_info.value)
        assert "metadata must be a dictionary or None" in error_msg
        assert "metadata={'source': '2012 IAM Tables'" in error_msg


class TestDataFrameValidation:
    """Test DataFrame validation errors with specific column information."""

    def test_empty_dataframe(self):
        """Test empty DataFrame with suggestions."""
        df = pl.DataFrame({"age": [], "qx": []})  # Empty DataFrame

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df)

        error_msg = str(exc_info.value)
        assert "DataFrame is empty - no rows to process" in error_msg
        assert "Check your data source contains data" in error_msg
        assert "Verify any filtering hasn't removed all rows" in error_msg
        assert "Ensure the file was read correctly" in error_msg

    def test_missing_id_columns(self):
        """Test missing ID columns with detailed information."""
        df = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.002]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, id="nonexistent_column")

        error_msg = str(exc_info.value)
        assert (
            "Specified id columns not found in DataFrame: ['nonexistent_column']"
            in error_msg
        )
        assert "Available columns: age, qx" in error_msg
        assert "Column types:" in error_msg
        assert "Check column name spelling and case sensitivity" in error_msg
        assert "Use df.columns to see available column names" in error_msg
        assert "Consider auto-detection by setting id=None" in error_msg

    def test_missing_value_vars_columns(self):
        """Test missing value_vars columns."""
        df = pl.DataFrame(
            {"age": [20, 21], "male": [0.001, 0.002], "female": [0.0008, 0.0015]}
        )

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, value_vars=["male", "nonexistent"])

        error_msg = str(exc_info.value)
        assert (
            "Specified value_vars columns not found in DataFrame: ['nonexistent']"
            in error_msg
        )

    def test_no_value_columns_found(self):
        """Test when no value columns are available."""
        df = pl.DataFrame(
            {"name": ["A", "B"], "description": ["desc1", "desc2"]}
        )  # All text columns

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, id="name")

        error_msg = str(exc_info.value)
        assert "No columns found to use as values" in error_msg
        assert "Specify value_vars or ensure there are numeric columns" in error_msg

    def test_multiple_numeric_columns_curve_error(self):
        """Test error when curve table has multiple numeric columns."""
        df = pl.DataFrame(
            {"age": [20, 21], "male_qx": [0.001, 0.002], "female_qx": [0.0008, 0.0015]}
        )

        # This should trigger wide table processing, but if we somehow force curve processing,
        # it should give a helpful error. Let's test the _tidy_curve function directly.
        from gaspatchio_core.assumptions._loader import _tidy_curve

        with pytest.raises(ValueError) as exc_info:
            _tidy_curve(df, ["age"], "rate")

        error_msg = str(exc_info.value)
        assert "Multiple numeric columns found for curve table" in error_msg
        assert "This appears to be a wide table" in error_msg

    def test_no_numeric_columns_curve_error(self):
        """Test error when curve table has no numeric columns."""
        df = pl.DataFrame({"age": ["20", "21"], "description": ["desc1", "desc2"]})

        from gaspatchio_core.assumptions._loader import _tidy_curve

        with pytest.raises(ValueError) as exc_info:
            _tidy_curve(df, ["age"], "rate")

        error_msg = str(exc_info.value)
        assert "No numeric columns found for curve table" in error_msg
        assert "Curve tables must have exactly one numeric column" in error_msg

    def test_explicit_overflow_column_not_found(self):
        """Test error when explicit overflow column doesn't exist."""
        df = pl.DataFrame({"age": [20, 21], "1": [0.001, 0.002], "2": [0.0008, 0.0015]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, overflow="Ultimate")  # Doesn't exist

        error_msg = str(exc_info.value)
        assert (
            "Specified overflow column 'Ultimate' not found in wide columns"
            in error_msg
        )


class TestMemoryWarnings:
    """Test memory warnings for large overflow expansions."""

    @patch("gaspatchio_core.assumptions._loader.logger")
    def test_large_overflow_expansion_warning(self, mock_logger):
        """Test warning for very large overflow expansions (>1M rows)."""
        # Create a dataset that will trigger large expansion
        # 10,000 rows * 500 expansion range = 5M rows (> 1M threshold)
        df_data = {
            "age": list(range(20, 30)) * 1000,  # 10,000 rows
            "1": [0.001] * 10000,
            "Ultimate": [0.002] * 10000,
        }
        df = pl.DataFrame(df_data)

        # This should trigger the warning
        load_assumptions("test_large", df, overflow="Ultimate", max_overflow=500)

        # Verify warning was logged
        mock_logger.warning.assert_called()
        warning_call = mock_logger.warning.call_args[0][0]
        assert "Large overflow expansion detected" in warning_call
        assert "may consume significant memory" in warning_call
        assert "Consider reducing max_overflow parameter" in warning_call

    @patch("gaspatchio_core.assumptions._loader.logger")
    def test_medium_overflow_expansion_info(self, mock_logger):
        """Test info logging for medium overflow expansions (>100K rows)."""
        # Create a dataset that will trigger info logging
        # 1,000 rows * 149 expansion range = 149K rows (> 100K threshold)
        # The expansion goes from max_numeric + 1 (which is 2) to max_overflow (150)
        # So expansion range is 150 - 2 = 148 + 1 = 149
        df_data = {
            "age": list(range(20, 30)) * 100,  # 1,000 rows
            "1": [0.001] * 1000,
            "Ultimate": [0.002] * 1000,
        }
        df = pl.DataFrame(df_data)

        load_assumptions("test_medium", df, overflow="Ultimate", max_overflow=150)

        # Verify info was logged
        mock_logger.info.assert_called()
        # Find the overflow expansion info call
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        overflow_info = [
            call for call in info_calls if "Overflow expansion creating" in call
        ]
        assert len(overflow_info) > 0
        assert (
            "149,000 rows" in overflow_info[0]
        )  # 1,000 overflow rows × 149 duration values


class TestDataTypeHandling:
    """Test handling of various data types and edge cases."""

    def test_mixed_column_types(self):
        """Test handling of mixed column types."""
        df = pl.DataFrame(
            {
                "age": [20, 21, 22],
                "duration": ["1", "2", "3"],  # String duration
                "rate": [0.001, 0.002, 0.003],
                "description": ["desc1", "desc2", "desc3"],
            }
        )

        # Auto-detects 'duration' as id column (first non-numeric), creates wide table with 'age' and 'rate' as values
        # This results in 6 rows: 3 for age values + 3 for rate values
        result = load_assumptions("test_mixed", df)
        assert len(result) == 6  # 3 rows * 2 value columns = 6 rows
        assert "duration" in result.columns
        assert "variable" in result.columns  # Wide table format
        assert "rate" in result.columns  # Value column name

        # Check that both 'age' and 'rate' appear as variables
        variables = result["variable"].unique().sort()
        assert "age" in variables
        assert "rate" in variables

    def test_unicode_column_names(self):
        """Test handling of Unicode column names."""
        df = pl.DataFrame(
            {
                "åge": [20, 21],  # Unicode characters
                "råte": [0.001, 0.002],
            }
        )

        result = load_assumptions("test_unicode", df, id="åge", value="råte")
        assert len(result) == 2
        assert "åge" in result.columns
        assert "råte" in result.columns

    def test_column_names_with_spaces(self):
        """Test handling of column names with spaces."""
        df = pl.DataFrame({"Age Group": [20, 21], "Mortality Rate": [0.001, 0.002]})

        result = load_assumptions(
            "test_spaces", df, id="Age Group", value="Mortality Rate"
        )
        assert len(result) == 2
        assert "Age Group" in result.columns
        assert "Mortality Rate" in result.columns

    def test_very_small_dataframe(self):
        """Test handling of single-row DataFrame."""
        df = pl.DataFrame({"age": [20], "qx": [0.001]})

        result = load_assumptions("test_tiny", df)
        assert len(result) == 1
        assert result["age"][0] == 20
        assert result["rate"][0] == 0.001


class TestErrorMessageQuality:
    """Test that error messages are actionable and informative."""

    def test_error_messages_include_context(self):
        """Test that error messages include relevant context."""
        df = pl.DataFrame({"wrong_col": [1, 2], "another_col": [3, 4]})

        with pytest.raises(ValueError) as exc_info:
            load_assumptions("test", df, id="expected_col")

        error_msg = str(exc_info.value)
        # Should include available columns, types, and suggestions
        assert "Available columns:" in error_msg
        assert "Column types:" in error_msg
        assert "Suggestions:" in error_msg
        assert "wrong_col" in error_msg
        assert "another_col" in error_msg

    def test_suggestions_are_actionable(self):
        """Test that suggestions in error messages are actionable."""
        # Test file not found
        with pytest.raises(FileNotFoundError) as exc_info:
            load_assumptions("test", "missing.csv")

        error_msg = str(exc_info.value)
        suggestions = error_msg.split("Suggestions:")[1]
        assert "Check the file path is correct" in suggestions
        assert "current working directory" in suggestions
        assert "Use absolute path" in suggestions
        assert "Check file permissions" in suggestions

    @patch("gaspatchio_core.assumptions._loader.logger")
    def test_successful_loading_logged(self, mock_logger):
        """Test that successful loading operations are logged."""
        df = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.002]})

        load_assumptions("test_success", df)

        # Verify success was logged
        mock_logger.info.assert_called()
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]

        # Should have loading start and success messages
        loading_calls = [
            call for call in info_calls if "Loading assumption table" in call
        ]
        success_calls = [
            call for call in info_calls if "Successfully loaded curve table" in call
        ]

        assert len(loading_calls) > 0
        assert len(success_calls) > 0
        assert "test_success" in success_calls[0]
        assert "2 rows" in success_calls[0]
        assert "1 id columns" in success_calls[0]
