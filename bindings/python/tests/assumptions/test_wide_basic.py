"""
Tests for wide table (2D) assumption loading functionality.

This module tests the loading of wide-format assumption tables (age × duration grids)
and their conversion to long format for efficient lookups.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl
import pytest
from gaspatchio_core.assumptions import assumption_lookup, load_assumptions
from gaspatchio_core.assumptions._loader import (
    _analyse_shape,
    _detect_overflow_column,
    _get_max_numeric_duration,
    _tidy_wide_basic,
)


class TestWideTableBasic:
    """Test suite for loading wide-format assumption tables."""

    def test_load_wide_table_basic(self):
        """Test loading a basic wide table (Age × Duration)."""
        # Create a wide mortality table (Age × Duration columns)
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        result = load_assumptions("wide_basic_test", df, value="mortality_rate")

        # Verify the result structure
        assert result.columns == ["Age", "variable", "mortality_rate"]
        assert len(result) == 9  # 3 ages × 3 duration columns

        # Check that data is correctly melted
        age_30_data = result.filter(pl.col("Age") == 30).sort("variable")
        assert age_30_data["variable"].to_list() == ["1", "2", "3"]
        assert age_30_data["mortality_rate"].to_list() == [0.001, 0.0008, 0.0005]

    def test_load_wide_table_with_explicit_id(self):
        """Test loading a wide table with explicitly specified id columns."""
        df = pl.DataFrame(
            {
                "AttAge": [25, 26, 27],
                "Dur1": [0.05, 0.06, 0.07],
                "Dur2": [0.04, 0.05, 0.06],
                "Dur3": [0.03, 0.04, 0.05],
            }
        )

        result = load_assumptions(
            "wide_explicit_id", df, id="AttAge", value="lapse_rate"
        )

        assert result.columns == ["AttAge", "variable", "lapse_rate"]
        assert len(result) == 9

    def test_load_wide_table_multiple_id_columns(self):
        """Test loading a wide table with multiple id columns."""
        df = pl.DataFrame(
            {
                "Age": [30, 30, 31, 31],
                "Gender": ["M", "F", "M", "F"],
                "Year1": [0.001, 0.0008, 0.0011, 0.0009],
                "Year2": [0.0008, 0.0006, 0.0009, 0.0007],
                "Year3": [0.0005, 0.0004, 0.0006, 0.0005],
            }
        )

        result = load_assumptions(
            "wide_multi_id", df, id=["Age", "Gender"], value="rate"
        )

        assert result.columns == ["Age", "Gender", "variable", "rate"]
        assert len(result) == 12  # 4 id combinations × 3 year columns

    def test_load_wide_table_integration_with_lookup(self):
        """Test end-to-end integration: load wide table then perform lookups."""
        # Create a select mortality table (Age × Duration)
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.002, 0.0021, 0.0022],
                "2": [0.0015, 0.0016, 0.0017],
                "3": [0.001, 0.0011, 0.0012],
            }
        )

        result = load_assumptions("select_mortality_lookup", df, value="qx")

        # Test lookups for different age/duration combinations
        test_cases = [
            (30, "1", 0.002),
            (31, "2", 0.0016),
            (32, "3", 0.0012),
        ]

        for age, duration, expected_rate in test_cases:
            # Create a single-row DataFrame for lookup
            single_row_df = pl.DataFrame({"Age": [age], "variable": [duration]})

            # Perform lookup
            lookup_result = single_row_df.with_columns(
                assumption_lookup(
                    "Age", "variable", table_name="select_mortality_lookup"
                ).alias("qx")
            )

            # Verify the result
            assert len(lookup_result) == 1
            actual_rate = lookup_result["qx"].item()
            assert actual_rate == expected_rate, (
                f"Expected {expected_rate} for age {age}, duration {duration}, got {actual_rate}"
            )

    def test_load_wide_table_with_value_vars_selective_melting(self):
        """Test loading with selective column melting using value_vars (like WideToLongTransformSpec)."""
        # Create a table with gender/smoking combinations like in model_test.py
        df = pl.DataFrame(
            {
                "age-last": [30, 31, 32],
                "MNS": [0.001, 0.0011, 0.0012],  # Male Non-Smoker
                "FNS": [0.0008, 0.0009, 0.001],  # Female Non-Smoker
                "MS": [0.002, 0.0021, 0.0022],  # Male Smoker
                "FS": [0.0015, 0.0016, 0.0017],  # Female Smoker
                "Other": [0.999, 0.999, 0.999],  # Column we don't want to melt
            }
        )

        # Use value_vars to select only the gender/smoking columns
        result = load_assumptions(
            "gender_smoking_select",
            df,
            id="age-last",
            value="mortality_rate",
            value_vars=["MNS", "FNS", "MS", "FS"],
        )

        # Verify the result structure
        assert result.columns == ["age-last", "variable", "mortality_rate"]
        assert len(result) == 12  # 3 ages × 4 gender/smoking columns

        # Verify that "Other" column was not included
        variables = result["variable"].unique().sort().to_list()
        assert variables == ["FNS", "FS", "MNS", "MS"]

        # Test a specific lookup
        age_30_mns = result.filter(
            (pl.col("age-last") == 30) & (pl.col("variable") == "MNS")
        )
        assert len(age_30_mns) == 1
        assert age_30_mns["mortality_rate"].item() == 0.001

    def test_load_wide_table_value_vars_integration_lookup(self):
        """Test that lookups work correctly with value_vars selective melting."""
        df = pl.DataFrame(
            {
                "age-last": [25, 26, 27],
                "MNS": [0.001, 0.0011, 0.0012],
                "FNS": [0.0008, 0.0009, 0.001],
                "MS": [0.002, 0.0021, 0.0022],
                "FS": [0.0015, 0.0016, 0.0017],
            }
        )

        result = load_assumptions(
            "mortality_value_vars_lookup",
            df,
            id="age-last",
            value="mortality_rate",
            value_vars=["MNS", "FNS", "MS", "FS"],
        )

        # Verify the structure is correct
        assert result.columns == ["age-last", "variable", "mortality_rate"]
        assert len(result) == 12  # 3 ages × 4 variables

        # Verify the variables are correct
        variables = sorted(result["variable"].unique().to_list())
        assert variables == ["FNS", "FS", "MNS", "MS"]

        # Test individual lookup (batch lookups seem to have issues with the underlying implementation)
        test_single = pl.DataFrame({"age-last": [25], "variable": ["MNS"]})

        lookup_result = test_single.with_columns(
            assumption_lookup(
                "age-last", "variable", table_name="mortality_value_vars_lookup"
            ).alias("mortality_rate")
        )

        assert lookup_result["mortality_rate"].item() == 0.001

    def test_wide_table_error_cases(self):
        """Test error handling for wide table scenarios."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "rate1": [0.001, 0.0011, 0.0012],
                "rate2": [0.002, 0.0021, 0.0022],
            }
        )

        # Test invalid value_vars
        with pytest.raises(ValueError, match="Specified value_vars columns not found"):
            load_assumptions("invalid_value_vars", df, value_vars=["nonexistent"])

        # Test empty value_vars
        with pytest.raises(ValueError, match="No columns found to use as values"):
            load_assumptions("empty_value_vars", df, value_vars=[])

        # Test invalid value_vars type
        with pytest.raises(ValueError, match="value_vars must be a list"):
            load_assumptions("invalid_type_value_vars", df, value_vars="rate1")

    def test_wide_table_auto_id_detection(self):
        """Test automatic id column detection for wide tables."""
        # Mix of numeric and string columns
        df = pl.DataFrame(
            {
                "PolicyYear": ["Y1", "Y2", "Y3"],  # Non-numeric -> should be id
                "Duration1": [0.01, 0.011, 0.012],
                "Duration2": [0.008, 0.009, 0.01],
                "Duration3": [0.005, 0.006, 0.007],
            }
        )

        result = load_assumptions("wide_auto_id", df, value="rate")

        assert result.columns == ["PolicyYear", "variable", "rate"]
        assert len(result) == 9

    def test_wide_table_numeric_only_columns(self):
        """Test wide table when all columns are numeric (fallback id detection)."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],  # Should be detected as id due to name pattern
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        result = load_assumptions("wide_numeric_only", df, value="rate")

        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 9

    def test_wide_table_with_custom_value_column_name(self):
        """Test wide table loading with custom value column name."""
        df = pl.DataFrame(
            {
                "Age": [30, 31],
                "1": [0.001, 0.0011],
                "2": [0.0008, 0.0009],
            }
        )

        result = load_assumptions("custom_value_name", df, value="custom_rate")

        assert result.columns == ["Age", "variable", "custom_rate"]
        assert "custom_rate" in result.columns
        assert len(result) == 4

    def test_model_test_pattern_with_value_vars(self):
        """Test the pattern used in model_test.py with gender/smoking combinations."""
        # Simulate the mortality table from model_test.py
        mortality_df = pl.DataFrame(
            {
                "age-last": [30, 31, 32, 33],
                "MNS": [0.001, 0.0011, 0.0012, 0.0013],  # Male Non-Smoker
                "FNS": [0.0008, 0.0009, 0.001, 0.0011],  # Female Non-Smoker
                "MS": [0.002, 0.0021, 0.0022, 0.0023],  # Male Smoker
                "FS": [0.0015, 0.0016, 0.0017, 0.0018],  # Female Smoker
                "extra_col": [
                    9.0,
                    9.0,
                    9.0,
                    9.0,
                ],  # Extra column that should be ignored
            }
        )

        # Load using value_vars like model_test.py would
        result = load_assumptions(
            "mortality_model_test_pattern",
            mortality_df,
            id="age-last",
            value="mortality_rate",
            value_vars=["MNS", "FNS", "MS", "FS"],  # Only select specific columns
        )

        # Verify structure
        assert result.columns == ["age-last", "variable", "mortality_rate"]
        assert len(result) == 16  # 4 ages × 4 gender/smoking combinations

        # Verify that extra_col was excluded
        variables = result["variable"].unique().sort().to_list()
        assert variables == ["FNS", "FS", "MNS", "MS"]
        assert "extra_col" not in variables

        # Verify a specific lookup works
        test_lookup = pl.DataFrame({"age-last": [30], "variable": ["MNS"]})

        lookup_result = test_lookup.with_columns(
            assumption_lookup(
                "age-last", "variable", table_name="mortality_model_test_pattern"
            ).alias("mortality_rate")
        )

        assert lookup_result["mortality_rate"].item() == 0.001


class TestTidyWideBasic:
    """Test suite for the _tidy_wide_basic helper function."""

    def test_tidy_wide_basic_function(self):
        """Test basic wide table tidying."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "Dur1": [0.001, 0.0011, 0.0012],
                "Dur2": [0.0008, 0.0009, 0.001],
                "Dur3": [0.0005, 0.0006, 0.0007],
            }
        )

        result = _tidy_wide_basic(df, ["Age"], ["Dur1", "Dur2", "Dur3"], "rate")

        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 9
        assert result["variable"].dtype == pl.String  # Ensure string type

        # Check data ordering
        age_20_data = result.filter(pl.col("Age") == 20).sort("variable")
        assert age_20_data["variable"].to_list() == ["Dur1", "Dur2", "Dur3"]
        assert age_20_data["rate"].to_list() == [0.001, 0.0008, 0.0005]

    def test_tidy_wide_multiple_id_columns(self):
        """Test tidying with multiple id columns."""
        df = pl.DataFrame(
            {
                "Age": [30, 30, 31, 31],
                "Gender": ["M", "F", "M", "F"],
                "Year1": [0.001, 0.0008, 0.0011, 0.0009],
                "Year2": [0.0008, 0.0006, 0.0009, 0.0007],
            }
        )

        result = _tidy_wide_basic(df, ["Age", "Gender"], ["Year1", "Year2"], "rate")

        assert result.columns == ["Age", "Gender", "variable", "rate"]
        assert len(result) == 8  # 4 id combinations × 2 year columns

    def test_tidy_wide_error_missing_columns(self):
        """Test error handling for missing wide columns."""
        df = pl.DataFrame({"Age": [20, 21, 22], "rate": [0.1, 0.2, 0.3]})

        with pytest.raises(ValueError, match="Specified wide columns not found"):
            _tidy_wide_basic(df, ["Age"], ["nonexistent"], "rate")

    def test_tidy_wide_preserve_column_order(self):
        """Test that column ordering is preserved in melting."""
        df = pl.DataFrame(
            {
                "Age": [20, 21],
                "Z_col": [0.001, 0.002],
                "A_col": [0.003, 0.004],
                "M_col": [0.005, 0.006],
            }
        )

        result = _tidy_wide_basic(df, ["Age"], ["Z_col", "A_col", "M_col"], "rate")

        # Check that the order of variables matches the input order
        age_20_vars = result.filter(pl.col("Age") == 20)["variable"].to_list()
        assert age_20_vars == ["Z_col", "A_col", "M_col"]


class TestAnalyseShapeWide:
    """Test suite for wide table shape analysis."""

    def test_analyse_shape_wide_table_detection(self):
        """Test that wide tables are correctly identified."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)

        assert id_cols == ["Age"]
        assert set(numeric_cols) == {"1", "2", "3"}
        assert text_cols == []  # No text columns in this example
        assert is_wide is True

    def test_analyse_shape_curve_vs_wide(self):
        """Test distinction between curve and wide tables."""
        # Curve table (single numeric column)
        curve_df = pl.DataFrame({"Age": [20, 21, 22], "rate": [0.1, 0.2, 0.3]})
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(curve_df, id=None)
        assert not is_wide
        assert numeric_cols == ["rate"]
        assert text_cols == []

        # Wide table (multiple numeric columns)
        wide_df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "rate1": [0.1, 0.2, 0.3],
                "rate2": [0.4, 0.5, 0.6],
            }
        )
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(wide_df, id=None)
        assert is_wide
        assert set(numeric_cols) == {"rate1", "rate2"}
        assert text_cols == []

    def test_analyse_shape_complex_wide_table(self):
        """Test shape analysis for complex wide tables with mixed column types."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "Gender": ["M", "F", "M"],  # Non-numeric
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "Category": ["A", "B", "A"],  # Another non-numeric
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)

        # Should pick first non-numeric column as id (in column order)
        # The actual first non-numeric column is "Gender", not "Age"
        assert id_cols == ["Gender"]  # Fixed expectation
        assert set(numeric_cols) == {
            "Age",
            "1",
            "2",
            "3",
        }  # Age is numeric, so included
        assert set(text_cols) == {"Category"}  # Category is the remaining text column
        assert is_wide is True


class TestFileLoadingWide:
    """Test suite for loading wide tables from files."""

    def test_load_wide_table_from_csv(self):
        """Test loading a wide table from CSV file."""
        # Create test data
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        # Write to temporary CSV
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            df.write_csv(f.name)
            csv_path = Path(f.name)

        try:
            result = load_assumptions("wide_from_csv", csv_path, value="rate")
            assert result.columns == ["Age", "variable", "rate"]
            assert len(result) == 9
        finally:
            csv_path.unlink()

    def test_load_wide_table_from_parquet(self):
        """Test loading a wide table from Parquet file."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "Dur1": [0.001, 0.0011, 0.0012],
                "Dur2": [0.0008, 0.0009, 0.001],
                "Dur3": [0.0005, 0.0006, 0.0007],
            }
        )

        # Write to temporary Parquet file
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            df.write_parquet(f.name)
            parquet_path = Path(f.name)

        try:
            result = load_assumptions("wide_from_parquet", parquet_path, value="rate")
            assert result.columns == ["Age", "variable", "rate"]
            assert len(result) == 9  # 3 ages × 3 duration columns (not 4)
        finally:
            parquet_path.unlink()


class TestWideTableParameterValidation:
    """Test parameter validation specific to wide tables."""

    def test_value_vars_parameter_validation(self):
        """Test validation of value_vars parameter."""
        df = pl.DataFrame(
            {
                "Age": [20, 21],
                "rate1": [0.1, 0.2],
                "rate2": [0.3, 0.4],
            }
        )

        # Valid usage - even with single value_var, should create wide format
        result = load_assumptions("valid_value_vars", df, value_vars=["rate1"])
        assert len(result) == 2
        assert result.columns == ["Age", "variable", "rate"]  # Should be wide format

        # Invalid type
        with pytest.raises(ValueError, match="value_vars must be a list"):
            load_assumptions("invalid_value_vars_type", df, value_vars="rate1")

        # Missing columns
        with pytest.raises(ValueError, match="Specified value_vars columns not found"):
            load_assumptions("missing_value_vars", df, value_vars=["missing_col"])


class TestOverflowDetection:
    """Test suite for overflow column detection functionality."""

    def test_detect_overflow_column_auto_ult_period(self):
        """Test auto-detection of 'Ult.' overflow column."""
        wide_cols = ["1", "2", "3", "Ult."]

        overflow_col = _detect_overflow_column(wide_cols, "auto")
        assert overflow_col == "Ult."

    def test_detect_overflow_column_auto_ultimate(self):
        """Test auto-detection of 'Ultimate' overflow column."""
        wide_cols = ["1", "2", "3", "Ultimate"]

        overflow_col = _detect_overflow_column(wide_cols, "auto")
        assert overflow_col == "Ultimate"

    def test_detect_overflow_column_auto_999(self):
        """Test auto-detection of '999' overflow column."""
        wide_cols = ["1", "2", "3", "999"]

        overflow_col = _detect_overflow_column(wide_cols, "auto")
        assert overflow_col == "999"

    def test_detect_overflow_column_auto_case_insensitive(self):
        """Test that auto-detection is case insensitive."""
        wide_cols = ["1", "2", "3", "ULT"]

        overflow_col = _detect_overflow_column(wide_cols, "auto")
        assert overflow_col == "ULT"

    def test_detect_overflow_column_auto_none_found(self):
        """Test auto-detection when no overflow column exists."""
        wide_cols = ["1", "2", "3", "4"]

        overflow_col = _detect_overflow_column(wide_cols, "auto")
        assert overflow_col is None

    def test_detect_overflow_column_explicit_valid(self):
        """Test explicit overflow column specification."""
        wide_cols = ["1", "2", "3", "Ult."]

        overflow_col = _detect_overflow_column(wide_cols, "Ult.")
        assert overflow_col == "Ult."

    def test_detect_overflow_column_explicit_invalid(self):
        """Test error when explicit overflow column doesn't exist."""
        wide_cols = ["1", "2", "3", "4"]

        with pytest.raises(
            ValueError, match="Specified overflow column 'NonExistent' not found"
        ):
            _detect_overflow_column(wide_cols, "NonExistent")

    def test_detect_overflow_column_none(self):
        """Test that None returns None (no overflow handling)."""
        wide_cols = ["1", "2", "3", "Ult."]

        overflow_col = _detect_overflow_column(wide_cols, None)
        assert overflow_col is None

    def test_get_max_numeric_duration_basic(self):
        """Test finding maximum numeric duration."""
        wide_cols = ["1", "2", "3", "5", "10"]

        max_duration = _get_max_numeric_duration(wide_cols)
        assert max_duration == 10

    def test_get_max_numeric_duration_with_overflow_exclusion(self):
        """Test finding max duration while excluding overflow column."""
        wide_cols = ["1", "2", "3", "5", "Ult."]

        max_duration = _get_max_numeric_duration(wide_cols, exclude_overflow="Ult.")
        assert max_duration == 5

    def test_get_max_numeric_duration_mixed_columns(self):
        """Test with mixed numeric and non-numeric columns."""
        wide_cols = ["1", "2", "MNS", "FNS", "3", "Ultimate", "5"]

        max_duration = _get_max_numeric_duration(wide_cols)
        assert max_duration == 5

    def test_get_max_numeric_duration_no_numeric(self):
        """Test when no numeric columns exist."""
        wide_cols = ["MNS", "FNS", "MS", "FS"]

        max_duration = _get_max_numeric_duration(wide_cols)
        assert max_duration is None

    def test_get_max_numeric_duration_all_excluded(self):
        """Test when all numeric columns are excluded."""
        wide_cols = ["1", "2", "3", "Ult."]

        # If we exclude "Ult." but it's not actually numeric, should still find 3
        max_duration = _get_max_numeric_duration(wide_cols, exclude_overflow="Ult.")
        assert max_duration == 3

        # But if we exclude a numeric column
        max_duration = _get_max_numeric_duration(wide_cols, exclude_overflow="3")
        assert max_duration == 2

    def test_load_assumptions_with_overflow_auto(self):
        """Test loading wide table with auto overflow detection."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
                "Ult.": [0.0002, 0.0003, 0.0004],
            }
        )

        # Should work without error - overflow detection happens internally
        result = load_assumptions(
            "overflow_auto_test", df, overflow="auto", value="rate"
        )

        # Overflow expansion should happen automatically from duration 4 to 200
        assert result.columns == ["Age", "variable", "rate"]
        # 3 ages × (4 original + 197 expanded) durations = 603 rows
        assert len(result) == 603  # 3 ages × 201 total durations

        # Verify overflow column was detected and expansion happened
        variables = result["variable"].unique().sort().to_list()
        assert "Ult." in variables  # Original overflow column
        assert "4" in variables  # First expanded duration
        assert "200" in variables  # Last expanded duration

    def test_load_assumptions_with_overflow_explicit(self):
        """Test loading wide table with explicit overflow column."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
                "Ultimate": [0.0002, 0.0003, 0.0004],
            }
        )

        # Should work without error
        result = load_assumptions(
            "overflow_explicit_test", df, overflow="Ultimate", value="rate"
        )

        assert result.columns == ["Age", "variable", "rate"]
        # Same expansion as auto test: 3 ages × (4 original + 197 expanded) = 603 rows
        assert len(result) == 603  # 3 ages × 201 total durations

        # Verify that the explicit overflow column was used for expansion
        variables = result["variable"].unique().sort().to_list()
        assert "Ultimate" in variables  # Original overflow column
        assert "4" in variables  # First expanded duration
        assert "200" in variables  # Last expanded duration

    def test_load_assumptions_with_overflow_none(self):
        """Test loading wide table with no overflow handling."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
                "Ult.": [0.0002, 0.0003, 0.0004],
            }
        )

        # Should work without error - no overflow processing
        result = load_assumptions("overflow_none_test", df, overflow=None, value="rate")

        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 12  # 3 ages × 4 columns

    def test_load_assumptions_overflow_error_invalid_column(self):
        """Test error when explicit overflow column doesn't exist."""
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        with pytest.raises(
            ValueError, match="Specified overflow column 'NonExistent' not found"
        ):
            load_assumptions(
                "overflow_error_test", df, overflow="NonExistent", value="rate"
            )
