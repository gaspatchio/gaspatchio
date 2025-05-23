"""
Tests for curve (1D) assumption loading functionality.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl
import pytest
from gaspatchio_core.assumptions import assumption_lookup, load_assumptions
from gaspatchio_core.assumptions._loader import (
    _analyse_shape,
    _materialise,
    _tidy_curve,
)


class TestCurveLoading:
    """Test suite for loading curve-style assumption tables."""

    def test_load_curve_basic(self):
        """Test loading a simple 2-column mortality curve."""
        # Create a simple mortality curve DataFrame
        df = pl.DataFrame(
            {"Age": [20, 21, 22, 23, 24], "qx": [0.001, 0.0011, 0.0012, 0.0013, 0.0014]}
        )

        # Load the curve with auto-detected id column
        result = load_assumptions("test_mortality_basic", df, value="qx")

        # Verify the result structure
        assert result.columns == ["Age", "qx"]
        assert len(result) == 5
        assert result["Age"].to_list() == [20, 21, 22, 23, 24]
        assert result["qx"].to_list() == [0.001, 0.0011, 0.0012, 0.0013, 0.0014]

    def test_load_curve_with_explicit_id(self):
        """Test loading a curve with explicitly specified id column."""
        df = pl.DataFrame(
            {"Duration": [1, 2, 3, 4, 5], "lapse_rate": [0.05, 0.04, 0.03, 0.03, 0.03]}
        )

        result = load_assumptions(
            "test_lapse_explicit", df, id="Duration", value="lapse_rate"
        )

        assert result.columns == ["Duration", "lapse_rate"]
        assert len(result) == 5

    def test_load_curve_rename_value_column(self):
        """Test that value column gets renamed to specified name."""
        df = pl.DataFrame(
            {"Age": [20, 21, 22], "mortality_rate": [0.001, 0.0011, 0.0012]}
        )

        result = load_assumptions("test_rename_col", df, value="qx")

        assert result.columns == ["Age", "qx"]
        assert result["qx"].to_list() == [0.001, 0.0011, 0.0012]

    def test_load_curve_integration_with_lookup(self):
        """Test end-to-end integration: load table then perform lookup."""
        # Load a mortality table
        df = pl.DataFrame(
            {"Age": [30, 31, 32, 33, 34], "qx": [0.002, 0.0021, 0.0022, 0.0023, 0.0024]}
        )

        result = load_assumptions("mortality_lookup_integration", df, value="qx")

        # Test individual scalar lookups
        test_ages = [30, 32, 34]
        expected_rates = [0.002, 0.0022, 0.0024]

        for age, expected_rate in zip(test_ages, expected_rates):
            # Create a single-row DataFrame for scalar lookup
            single_row_df = pl.DataFrame({"Age": [age]})

            # Perform lookup
            lookup_result = single_row_df.with_columns(
                assumption_lookup(
                    "Age", table_name="mortality_lookup_integration"
                ).alias("qx")
            )

            # The result should be a single-row DataFrame with the expected rate
            assert len(lookup_result) == 1
            actual_rate = lookup_result["qx"].item()
            assert actual_rate == expected_rate, (
                f"Expected {expected_rate} for age {age}, got {actual_rate}"
            )

    def test_load_curve_multiple_id_columns(self):
        """Test loading a curve with multiple id columns."""
        df = pl.DataFrame(
            {
                "Age": [30, 30, 31, 31, 32, 32],
                "Gender": ["M", "F", "M", "F", "M", "F"],
                "rate": [0.002, 0.0015, 0.0021, 0.0016, 0.0022, 0.0017],
            }
        )

        result = load_assumptions(
            "multi_id_curve", df, id=["Age", "Gender"], value="rate"
        )

        assert result.columns == ["Age", "Gender", "rate"]
        assert len(result) == 6

    def test_load_curve_error_multiple_numeric_columns(self):
        """Test error when multiple numeric columns present (should be wide table)."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "rate1": [0.001, 0.0011, 0.0012],
                "rate2": [0.002, 0.0021, 0.0022],
            }
        )

        # Should now work since we support wide tables
        result = load_assumptions("wide_table_test", df, value="rate")

        # Verify it's a wide table result
        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 6  # 3 ages × 2 rate columns

    def test_load_curve_error_no_numeric_columns(self):
        """Test error when no numeric columns present."""
        df = pl.DataFrame({"Age": ["20", "21", "22"], "Category": ["A", "B", "C"]})

        with pytest.raises(ValueError, match="No columns found to use as values"):
            load_assumptions("should_fail_no_numeric", df)

    def test_parameter_validation(self):
        """Test that parameter validation works correctly."""
        df = pl.DataFrame({"Age": [20, 21, 22], "rate": [0.001, 0.0011, 0.0012]})

        # Test invalid name
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            load_assumptions("", df)

        with pytest.raises(ValueError, match="name must be a non-empty string"):
            load_assumptions("   ", df)

        # Test invalid value column name
        with pytest.raises(ValueError, match="value must be a non-empty string"):
            load_assumptions("test", df, value="")

        # Test invalid max_overflow
        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("test", df, max_overflow=0)

        with pytest.raises(
            ValueError, match="max_overflow must be an integer between 1 and 1000"
        ):
            load_assumptions("test", df, max_overflow=1001)

        # Test invalid overflow parameter
        with pytest.raises(
            ValueError, match="overflow must be 'auto', a column name string, or None"
        ):
            load_assumptions("test", df, overflow=123)

        # Test invalid metadata
        with pytest.raises(ValueError, match="metadata must be a dictionary or None"):
            load_assumptions("test", df, metadata="invalid")

    def test_wide_table_detection_ready_for_step_4(self):
        """Test that we correctly detect wide tables and now support them."""
        # Create a wide table (Age × Duration columns)
        df = pl.DataFrame(
            {
                "Age": [30, 31, 32],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )

        # Should now work with wide table support
        result = load_assumptions("wide_table_step4_test", df, value="rate")

        # Verify the result structure
        assert result.columns == ["Age", "variable", "rate"]
        assert len(result) == 9  # 3 ages × 3 duration columns

        # Verify the shape analysis works correctly for wide tables
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)
        assert id_cols == ["Age"]
        assert set(numeric_cols) == {"1", "2", "3"}
        assert text_cols == []
        assert is_wide is True


class TestTidyCurve:
    """Test suite for the _tidy_curve helper function."""

    def test_tidy_curve_basic(self):
        """Test basic curve tidying."""
        df = pl.DataFrame({"Age": [20, 21, 22], "qx": [0.001, 0.0011, 0.0012]})

        result = _tidy_curve(df, ["Age"], "rate")
        assert result.columns == ["Age", "rate"]
        assert result["rate"].to_list() == [0.001, 0.0011, 0.0012]

    def test_tidy_curve_no_rename_needed(self):
        """Test when value column already has correct name."""
        df = pl.DataFrame({"Age": [20, 21, 22], "rate": [0.001, 0.0011, 0.0012]})

        result = _tidy_curve(df, ["Age"], "rate")
        assert result.columns == ["Age", "rate"]

    def test_tidy_curve_multiple_id_columns(self):
        """Test tidying with multiple id columns."""
        df = pl.DataFrame(
            {
                "Age": [30, 30, 31, 31],
                "Gender": ["M", "F", "M", "F"],
                "qx": [0.002, 0.0015, 0.0021, 0.0016],
            }
        )

        result = _tidy_curve(df, ["Age", "Gender"], "mortality_rate")
        assert result.columns == ["Age", "Gender", "mortality_rate"]
        assert len(result) == 4

    def test_tidy_curve_error_multiple_numeric_columns(self):
        """Test error when multiple numeric columns present."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "rate1": [0.001, 0.0011, 0.0012],
                "rate2": [0.002, 0.0021, 0.0022],
            }
        )

        with pytest.raises(
            ValueError,
            match="Multiple numeric columns found.*This appears to be a wide table",
        ):
            _tidy_curve(df, ["Age"], "rate")

    def test_tidy_curve_error_no_numeric_columns(self):
        """Test error when no numeric columns present."""
        df = pl.DataFrame(
            {
                "Age": ["20", "21", "22"],  # String, not numeric
                "Category": ["A", "B", "C"],
            }
        )

        with pytest.raises(
            ValueError,
            match="No numeric columns found.*Curve tables must have exactly one numeric column",
        ):
            _tidy_curve(df, ["Age"], "rate")


class TestMaterialise:
    """Test suite for the _materialise helper function."""

    def test_materialise_dataframe(self):
        """Test materializing from an existing DataFrame."""
        df = pl.DataFrame({"Age": [20, 21, 22], "qx": [0.001, 0.0011, 0.0012]})
        result = _materialise(df)
        assert result.equals(df)

    def test_materialise_csv_file(self):
        """Test materializing from a CSV file."""
        # Create a temporary CSV file
        df = pl.DataFrame({"Age": [20, 21, 22], "qx": [0.001, 0.0011, 0.0012]})

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            df.write_csv(f.name)
            csv_path = Path(f.name)

        try:
            result = _materialise(csv_path)
            assert result.columns == ["Age", "qx"]
            assert len(result) == 3
        finally:
            csv_path.unlink()  # Clean up

    def test_materialise_parquet_file(self):
        """Test materializing from a Parquet file."""
        # Create a temporary Parquet file
        df = pl.DataFrame({"Age": [20, 21, 22], "qx": [0.001, 0.0011, 0.0012]})

        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            df.write_parquet(f.name)
            parquet_path = Path(f.name)

        try:
            result = _materialise(parquet_path)
            assert result.columns == ["Age", "qx"]
            assert len(result) == 3
        finally:
            parquet_path.unlink()  # Clean up

    def test_materialise_file_not_found(self):
        """Test error handling for missing files."""
        with pytest.raises(FileNotFoundError, match="Source file not found"):
            _materialise("nonexistent.csv")

    def test_materialise_unsupported_format(self):
        """Test error handling for unsupported file formats."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"some content")
            txt_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Unsupported file format: .txt"):
                _materialise(txt_path)
        finally:
            txt_path.unlink()


class TestAnalyseShape:
    """Test suite for the _analyse_shape helper function."""

    def test_analyse_shape_auto_detect_id(self):
        """Test auto-detection of id columns."""
        df = pl.DataFrame(
            {
                "Category": ["A", "B", "C"],  # Non-numeric -> should be id
                "qx": [0.001, 0.0011, 0.0012],  # Numeric -> should be value
            }
        )
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)
        assert id_cols == [
            "Category"
        ]  # Category is non-numeric and should be auto-detected
        assert numeric_cols == ["qx"]
        assert text_cols == []
        assert not is_wide  # Single numeric column = curve table

    def test_analyse_shape_explicit_id_string(self):
        """Test explicit id column specification as string."""
        df = pl.DataFrame(
            {"Age": [20, 21, 22], "Sex": ["M", "F", "M"], "qx": [0.001, 0.0011, 0.0012]}
        )
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id="Age")
        assert id_cols == ["Age"]
        assert numeric_cols == ["qx"]
        assert text_cols == ["Sex"]
        assert not is_wide  # Single numeric column = curve table

    def test_analyse_shape_explicit_id_list(self):
        """Test explicit id column specification as list."""
        df = pl.DataFrame(
            {"Age": [20, 21, 22], "Sex": ["M", "F", "M"], "qx": [0.001, 0.0011, 0.0012]}
        )
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(
            df, id=["Age", "Sex"]
        )
        assert id_cols == ["Age", "Sex"]
        assert numeric_cols == ["qx"]
        assert text_cols == []
        assert not is_wide  # Single numeric column = curve table

    def test_analyse_shape_comma_separated_id(self):
        """Test comma-separated id column specification."""
        df = pl.DataFrame(
            {"Age": [20, 21, 22], "Sex": ["M", "F", "M"], "qx": [0.001, 0.0011, 0.0012]}
        )
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id="Age, Sex")
        assert id_cols == ["Age", "Sex"]
        assert numeric_cols == ["qx"]
        assert text_cols == []
        assert not is_wide  # Single numeric column = curve table

    def test_analyse_shape_wide_table(self):
        """Test analysis of wide table with multiple numeric columns."""
        df = pl.DataFrame(
            {
                "Age": [20, 21, 22],
                "1": [0.001, 0.0011, 0.0012],
                "2": [0.0008, 0.0009, 0.001],
                "3": [0.0005, 0.0006, 0.0007],
            }
        )
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)
        assert id_cols == ["Age"]  # Auto-detected
        assert set(numeric_cols) == {"1", "2", "3"}
        assert text_cols == []
        assert is_wide  # Multiple numeric columns = wide table

    def test_analyse_shape_empty_dataframe(self):
        """Test error handling for empty DataFrame."""
        df = pl.DataFrame()
        with pytest.raises(ValueError, match="DataFrame is empty"):
            _analyse_shape(df, id=None)

    def test_analyse_shape_missing_id_column(self):
        """Test error handling for non-existent id column."""
        df = pl.DataFrame({"Age": [20, 21, 22], "qx": [0.001, 0.0011, 0.0012]})
        with pytest.raises(ValueError, match="Specified id columns not found"):
            _analyse_shape(df, id="NonExistent")

    def test_analyse_shape_no_non_numeric_for_auto_detect(self):
        """Test behavior when all columns are numeric - should use fallback logic."""
        df = pl.DataFrame({"col1": [1, 2, 3], "col2": [0.1, 0.2, 0.3]})
        # Should not raise error - should use first column as fallback
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)
        # When all columns are numeric, first column becomes id by fallback
        assert id_cols == ["col1"]
        assert numeric_cols == ["col2"]
        assert text_cols == []
        assert not is_wide  # Single remaining numeric column

    def test_analyse_shape_age_pattern_detection(self):
        """Test that Age columns are correctly detected as id columns."""
        df = pl.DataFrame({"Age": [20, 21, 22], "rate": [0.1, 0.2, 0.3]})
        id_cols, numeric_cols, text_cols, is_wide = _analyse_shape(df, id=None)
        # Age should be detected as id column despite being numeric due to pattern matching
        assert id_cols == ["Age"]
        assert numeric_cols == ["rate"]
        assert text_cols == []
        assert not is_wide
