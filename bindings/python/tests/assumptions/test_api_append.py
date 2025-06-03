"""
Unit tests for append_assumptions function with full compatibility validation.

Tests cover:
- Basic append functionality with compatible data
- Compatibility validation errors (mismatched parameters)
- Duplicate additional_keys detection
- Data processing through same transformation pipeline
- Error handling for non-existent tables
- Various parameter combinations
- Integration with existing lookup mechanisms
"""

import tempfile
from pathlib import Path

import polars as pl
import pytest
from gaspatchio_core.assumptions._config import (
    _clear_table_configs,
    _get_table_config,
    _table_exists,
)
from gaspatchio_core.assumptions.api import append_assumptions, load_assumptions


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the global assumption registry before each test."""
    from gaspatchio_core._internal import PyAssumptionTableRegistry

    registry = PyAssumptionTableRegistry()
    registry.reset()
    _clear_table_configs()
    yield
    # Reset after test too for extra safety
    registry.reset()
    _clear_table_configs()


class TestAppendAssumptionsBasic:
    """Test basic append_assumptions functionality."""

    def test_append_basic_curve_table(self):
        """Test basic append to curve table."""
        # Load base table (explicit id to ensure curve format)
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, id=["age"], additional_keys={"sex": "M"}
        )

        # Append compatible data
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        result = append_assumptions(
            "test_table", append_df, id=["age"], additional_keys={"sex": "F"}
        )

        # Check result structure
        assert "age" in result.columns
        assert "rate" in result.columns
        assert "sex" in result.columns

        # Check data was processed correctly
        assert len(result) == 2  # New data rows
        assert result["sex"].unique().to_list() == ["F"]
        assert result["age"].to_list() == [30.0, 31.0]  # Converted to f64
        assert result["rate"].to_list() == [0.0008, 0.0016]

    def test_append_basic_wide_table(self):
        """Test basic append to wide table."""
        # Load base table (explicit id to ensure wide format)
        base_df = pl.DataFrame(
            {"age": [30, 31], "male": [0.001, 0.002], "female": [0.0008, 0.0016]}
        )
        load_assumptions(
            "test_table", base_df, id=["age"], additional_keys={"product": "A"}
        )

        # Append compatible data
        append_df = pl.DataFrame(
            {"age": [30, 31], "male": [0.0012, 0.0024], "female": [0.001, 0.002]}
        )
        result = append_assumptions(
            "test_table", append_df, id=["age"], additional_keys={"product": "B"}
        )

        # Check result structure (wide table is melted)
        expected_columns = {"age", "product", "variable", "rate"}
        assert set(result.columns) == expected_columns

        # Check data was processed correctly
        assert len(result) == 4  # 2 ages * 2 variables (male, female)
        assert result["product"].unique().to_list() == ["B"]

        # Check variables were melted correctly
        variables = result["variable"].unique().to_list()
        assert set(variables) == {"male", "female"}

    def test_append_with_overflow(self):
        """Test append with overflow handling."""
        # Load base table with overflow (explicit id to ensure correct structure)
        base_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.001, 0.002], "Ultimate": [0.0005, 0.001]}
        )
        load_assumptions(
            "test_table",
            base_df,
            id=["age"],
            overflow="Ultimate",
            max_overflow=5,
            additional_keys={"sex": "M"},
        )

        # Append with same overflow settings
        append_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.0008, 0.0016], "Ultimate": [0.0004, 0.0008]}
        )
        result = append_assumptions(
            "test_table", append_df, id=["age"], additional_keys={"sex": "F"}
        )

        # Check overflow expansion worked
        variables = result["variable"].unique().to_list()
        assert "5" in variables  # Should be expanded to max_overflow
        assert "Ultimate" in variables  # Ultimate overflow column should be preserved

        # Check additional keys
        assert result["sex"].unique().to_list() == ["F"]

    def test_append_multiple_additional_keys(self):
        """Test append with multiple additional keys."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table",
            base_df,
            additional_keys={"sex": "M", "smoking": "NS", "product": "Term"},
        )

        # Append with different values for same keys
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0012, 0.0024]})
        result = append_assumptions(
            "test_table",
            append_df,
            additional_keys={"sex": "F", "smoking": "SM", "product": "Whole"},
        )

        # Check all additional keys are present
        assert "sex" in result.columns
        assert "smoking" in result.columns
        assert "product" in result.columns

        # Check values
        assert result["sex"].unique().to_list() == ["F"]
        assert result["smoking"].unique().to_list() == ["SM"]
        assert result["product"].unique().to_list() == ["Whole"]


class TestAppendAssumptionsCompatibilityValidation:
    """Test compatibility validation between original and appended data."""

    def test_compatibility_validation_value_mismatch(self):
        """Test error when value column name doesn't match."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, value="rate", additional_keys={"sex": "M"}
        )

        # Try to append with different value column name
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        with pytest.raises(
            ValueError, match="'value' setting must match existing table"
        ):
            append_assumptions(
                "test_table",
                append_df,
                value="mortality_rate",
                additional_keys={"sex": "F"},
            )

    def test_compatibility_validation_overflow_mismatch(self):
        """Test error when overflow setting doesn't match."""
        # Load base table with overflow
        base_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.001, 0.002], "Ultimate": [0.0005, 0.001]}
        )
        load_assumptions(
            "test_table", base_df, overflow="Ultimate", additional_keys={"sex": "M"}
        )

        # Try to append with different overflow setting
        append_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.0008, 0.0016], "Ultimate": [0.0004, 0.0008]}
        )
        with pytest.raises(
            ValueError, match="'overflow' setting must match existing table"
        ):
            append_assumptions(
                "test_table", append_df, overflow=None, additional_keys={"sex": "F"}
            )

    def test_compatibility_validation_max_overflow_mismatch(self):
        """Test error when max_overflow doesn't match."""
        # Load base table
        base_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.001, 0.002], "Ultimate": [0.0005, 0.001]}
        )
        load_assumptions(
            "test_table",
            base_df,
            overflow="Ultimate",
            max_overflow=100,
            additional_keys={"sex": "M"},
        )

        # Try to append with different max_overflow
        append_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.0008, 0.0016], "Ultimate": [0.0004, 0.0008]}
        )
        with pytest.raises(
            ValueError, match="'max_overflow' setting must match existing table"
        ):
            append_assumptions(
                "test_table", append_df, max_overflow=150, additional_keys={"sex": "F"}
            )

    def test_compatibility_validation_additional_keys_structure_mismatch(self):
        """Test error when additional_keys structure doesn't match."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, additional_keys={"sex": "M", "smoking": "NS"}
        )

        # Try to append with different additional_keys structure
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        with pytest.raises(
            ValueError, match="Additional keys must match existing table structure"
        ):
            append_assumptions(
                "test_table", append_df, additional_keys={"sex": "F", "product": "Term"}
            )

    def test_compatibility_validation_duplicate_additional_keys(self):
        """Test error when additional_keys values are identical."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, additional_keys={"sex": "M", "smoking": "NS"}
        )

        # Try to append with identical additional_keys values
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        with pytest.raises(
            ValueError, match="Cannot append data with identical additional_keys values"
        ):
            append_assumptions(
                "test_table", append_df, additional_keys={"sex": "M", "smoking": "NS"}
            )


class TestAppendAssumptionsErrorHandling:
    """Test error handling for various scenarios."""

    def test_table_not_found_no_tables(self):
        """Test error when table doesn't exist and no tables configured."""
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        with pytest.raises(
            ValueError,
            match="Table 'missing_table' does not exist and no tables are currently configured",
        ):
            append_assumptions("missing_table", append_df, additional_keys={"sex": "M"})

    def test_table_not_found_with_available_tables(self):
        """Test error when table doesn't exist but other tables available."""
        # Load a different table first
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("existing_table", base_df, additional_keys={"sex": "M"})

        # Try to append to non-existent table
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        with pytest.raises(
            ValueError,
            match="Table 'missing_table' does not exist. Available tables: \\['existing_table'\\]",
        ):
            append_assumptions("missing_table", append_df, additional_keys={"sex": "F"})

    def test_additional_keys_required(self):
        """Test error when additional_keys is None."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={"sex": "M"})

        # Try to append without additional_keys
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        with pytest.raises(
            ValueError,
            match="additional_keys parameter is required for append_assumptions",
        ):
            append_assumptions("test_table", append_df, additional_keys=None)

    def test_additional_keys_invalid_format(self):
        """Test error when additional_keys has invalid format."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={"sex": "M"})

        # Try to append with invalid additional_keys format
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        with pytest.raises(ValueError, match="additional_keys must be a dictionary"):
            append_assumptions("test_table", append_df, additional_keys="invalid")

    def test_column_conflict_detection(self):
        """Test error when additional_keys conflict with existing columns."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={"sex": "M"})

        # Try to append with conflicting column name
        append_df = pl.DataFrame(
            {"age": [30, 31], "sex": [0.0008, 0.0016]}
        )  # 'sex' conflicts with additional_keys
        with pytest.raises(
            ValueError, match="additional_keys contain column names that already exist"
        ):
            append_assumptions(
                "test_table",
                append_df,
                additional_keys={"sex": "F"},  # Same structure but column conflict
            )

    def test_file_not_found(self):
        """Test error when source file doesn't exist."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={"sex": "M"})

        # Try to append from non-existent file
        with pytest.raises(FileNotFoundError):
            append_assumptions(
                "test_table", "non_existent_file.csv", additional_keys={"sex": "F"}
            )


class TestAppendAssumptionsParameterHandling:
    """Test parameter handling and defaults."""

    def test_append_uses_original_parameters_when_defaults(self):
        """Test that append uses original table parameters when defaults provided."""
        # Load base table with specific parameters
        base_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.001, 0.002], "Ultimate": [0.0005, 0.001]}
        )
        load_assumptions(
            "test_table",
            base_df,
            value="custom_rate",
            overflow="Ultimate",
            max_overflow=150,
            additional_keys={"sex": "M"},
        )

        # Append with default parameters (should use original table's parameters)
        append_df = pl.DataFrame(
            {"age": [30, 31], "1": [0.0008, 0.0016], "Ultimate": [0.0004, 0.0008]}
        )
        result = append_assumptions(
            "test_table",
            append_df,
            additional_keys={"sex": "F"},
            # Note: using defaults for value, overflow, max_overflow
        )

        # Check that original parameters were used effectively
        assert "custom_rate" in result.columns  # Original value column name
        variables = result["variable"].unique().to_list()
        assert "150" in variables  # Should expand to original max_overflow

    def test_append_explicit_parameters_validated(self):
        """Test that explicit parameters are validated against original."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, value="rate", additional_keys={"sex": "M"}
        )

        # Append with explicit matching parameters (should work)
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        result = append_assumptions(
            "test_table",
            append_df,
            value="rate",  # Explicit but matching
            additional_keys={"sex": "F"},
        )

        # Should work fine
        assert "rate" in result.columns
        assert result["sex"].unique().to_list() == ["F"]

    def test_append_with_custom_lookup_keys(self):
        """Test append with custom lookup keys that match original."""
        # Load base table with custom lookup keys (wide table with 2 keys: additional_key + variable)
        base_df = pl.DataFrame(
            {"age": [30, 31], "male": [0.001, 0.002], "female": [0.0008, 0.0016]}
        )
        load_assumptions(
            "test_table",
            base_df,
            lookup_keys=[
                "smoking_status",
                "duration",
            ],  # 2 keys: additional_key + variable
            additional_keys={"smoking_status": "smoker"},
        )

        # Append with same lookup keys
        append_df = pl.DataFrame(
            {"age": [30, 31], "male": [0.0012, 0.0024], "female": [0.001, 0.002]}
        )
        result = append_assumptions(
            "test_table",
            append_df,
            lookup_keys=["smoking_status", "duration"],
            additional_keys={"smoking_status": "non_smoker"},
        )

        # Check columns were renamed correctly
        assert "smoking_status" in result.columns
        assert "duration" in result.columns  # Variable column renamed


class TestAppendAssumptionsIntegration:
    """Test integration with existing functionality."""

    def test_append_with_file_sources(self):
        """Test append with CSV file source."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={"sex": "M"})

        # Create temporary CSV for append
        csv_content = "age,rate\n32,0.003\n33,0.004"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            result = append_assumptions(
                "test_table", csv_path, additional_keys={"sex": "F"}
            )

            # Check data was loaded from CSV and processed
            # CSV has 2 rows × 2 columns (age, rate) = 4 melted rows in wide format
            assert len(result) == 4  # 2 CSV rows melted into wide format
            assert result["sex"].unique().to_list() == ["F"]

            # Check that CSV columns became variables in wide processing
            # Since no explicit id is provided, all columns become value columns
            variables = result["variable"].unique().to_list()
            assert "age" in variables
            assert "rate" in variables

        finally:
            Path(csv_path).unlink(missing_ok=True)

    def test_append_with_path_object(self):
        """Test append with Path object source."""
        # Load base table
        base_df = pl.DataFrame({"duration": [1, 2], "factor": [1.0, 0.9]})
        load_assumptions("test_table", base_df, additional_keys={"product": "A"})

        # Create temporary CSV with Path object
        csv_content = "duration,factor\n3,0.8\n4,0.7"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = Path(f.name)

        try:
            result = append_assumptions(
                "test_table", csv_path, additional_keys={"product": "B"}
            )

            # Check data was processed correctly
            assert result["product"].unique().to_list() == ["B"]

        finally:
            csv_path.unlink(missing_ok=True)

    def test_append_metadata_handling(self):
        """Test metadata handling in append operations."""
        # Load base table with metadata
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table",
            base_df,
            metadata={"source": "original", "version": "1.0"},
            additional_keys={"sex": "M"},
        )

        # Append with different metadata
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        result = append_assumptions(
            "test_table",
            append_df,
            metadata={"source": "append", "version": "1.1"},
            additional_keys={"sex": "F"},
        )

        # Check that append worked (metadata doesn't affect compatibility)
        # 2 input rows × 2 columns (age, rate) = 4 melted rows in wide format
        assert len(result) == 4
        assert result["sex"].unique().to_list() == ["F"]


class TestAppendAssumptionsTransformationPipeline:
    """Test that appended data goes through same transformation pipeline."""

    def test_append_curve_to_curve(self):
        """Test appending curve data to curve table."""
        # Load base curve table (explicit id to ensure curve format)
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, id=["age"], additional_keys={"sex": "M"}
        )

        # Append curve data
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "test_table", append_df, id=["age"], additional_keys={"sex": "F"}
        )

        # Should maintain curve structure: age + sex + rate
        expected_columns = {"age", "sex", "rate"}
        assert set(result.columns) == expected_columns
        assert len(result) == 2  # New data rows
        assert result["age"].to_list() == [32.0, 33.0]  # Converted to f64

    def test_append_wide_to_wide(self):
        """Test appending wide data to wide table."""
        # Load base wide table
        base_df = pl.DataFrame(
            {"age": [30, 31], "male": [0.001, 0.002], "female": [0.0008, 0.0016]}
        )
        load_assumptions("test_table", base_df, additional_keys={"product": "A"})

        # Append wide data
        append_df = pl.DataFrame(
            {"age": [32, 33], "male": [0.003, 0.004], "female": [0.0024, 0.0032]}
        )
        result = append_assumptions(
            "test_table", append_df, additional_keys={"product": "B"}
        )

        # Should be melted: product + variable + rate (age becomes a melted variable)
        expected_columns = {"product", "variable", "rate"}
        assert set(result.columns) == expected_columns
        assert len(result) == 6  # 2 rows * 3 variables (age, male, female)

        # Check melted structure - age becomes a variable too
        variables = result["variable"].unique().to_list()
        assert set(variables) == {"age", "male", "female"}

    def test_append_data_type_conversion(self):
        """Test that appended data undergoes same type conversions."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, id=["age"], additional_keys={"sex": "M"}
        )

        # Append with integer age (should be converted to f64)
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "test_table", append_df, id=["age"], additional_keys={"sex": "F"}
        )

        # Check age column is f64
        assert result["age"].dtype == pl.Float64
        assert result["age"].to_list() == [32.0, 33.0]


class TestAppendAssumptionsEdgeCases:
    """Test edge cases and important scenarios."""

    def test_append_empty_additional_keys_original(self):
        """Test append when original table had no additional_keys."""
        # Load base table without additional_keys
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df)  # No additional_keys

        # Try to append with additional_keys - should fail
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        with pytest.raises(
            ValueError, match="Additional keys must match existing table structure"
        ):
            append_assumptions("test_table", append_df, additional_keys={"sex": "M"})

    def test_append_to_table_with_empty_additional_keys(self):
        """Test append when original table had empty additional_keys."""
        # Load base table with empty additional_keys
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={})

        # Try to append with non-empty additional_keys - should fail
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        with pytest.raises(
            ValueError, match="Additional keys must match existing table structure"
        ):
            append_assumptions("test_table", append_df, additional_keys={"sex": "M"})

    def test_append_single_row(self):
        """Test appending single row of data."""
        # Load base table
        base_df = pl.DataFrame({"age": [30], "rate": [0.001]})
        load_assumptions(
            "test_table", base_df, id=["age"], additional_keys={"sex": "M"}
        )

        # Append single row
        append_df = pl.DataFrame({"age": [31], "rate": [0.002]})
        result = append_assumptions(
            "test_table", append_df, id=["age"], additional_keys={"sex": "F"}
        )

        # Should work correctly
        assert len(result) == 1
        assert result["age"].to_list() == [31.0]
        assert result["sex"].unique().to_list() == ["F"]

    def test_append_complex_additional_keys_values(self):
        """Test append with complex additional_keys value types."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table",
            base_df,
            additional_keys={
                "text": "value1",
                "number": 42,
                "float": 3.14,
                "bool": True,
            },
        )

        # Append with different values but same structure
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "test_table",
            append_df,
            additional_keys={
                "text": "value2",
                "number": 84,
                "float": 2.71,
                "bool": False,
            },
        )

        # Check values were applied correctly
        assert result["text"].unique().to_list() == ["value2"]
        assert result["number"].unique().to_list() == [84]
        assert result["float"].unique().to_list() == [2.71]
        assert result["bool"].unique().to_list() == [False]

    def test_append_configuration_not_affected(self):
        """Test that append doesn't change original table configuration."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table",
            base_df,
            value="rate",
            max_overflow=100,
            additional_keys={"sex": "M"},
        )

        # Get original configuration
        original_config = _get_table_config("test_table")

        # Append data
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        append_assumptions("test_table", append_df, additional_keys={"sex": "F"})

        # Check configuration hasn't changed
        current_config = _get_table_config("test_table")
        assert current_config == original_config

    def test_append_table_still_exists_after_append(self):
        """Test that table configuration still exists after append."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("test_table", base_df, additional_keys={"sex": "M"})

        # Verify table exists
        assert _table_exists("test_table")

        # Append data
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        append_assumptions("test_table", append_df, additional_keys={"sex": "F"})

        # Table should still exist
        assert _table_exists("test_table")

        # Configuration should still be accessible
        config = _get_table_config("test_table")
        assert config["additional_keys"] == {"sex": "M"}  # Original config preserved


class TestAppendAssumptionsAdditionalCoverage:
    """Additional test cases to improve coverage of edge cases and important scenarios."""

    def test_append_curve_table_explicit_id(self):
        """Test appending to curve table with explicit ID to ensure curve behavior."""
        # Load base curve table with explicit ID
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "curve_table", base_df, id=["age"], additional_keys={"product": "A"}
        )

        # Append curve data with explicit ID
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "curve_table", append_df, id=["age"], additional_keys={"product": "B"}
        )

        # Should maintain curve structure
        expected_columns = {"age", "product", "rate"}
        assert set(result.columns) == expected_columns
        assert len(result) == 2  # Just the new rows
        assert result["product"].unique().to_list() == ["B"]

    def test_append_with_none_values_in_additional_keys(self):
        """Test append with None values in additional_keys."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "test_table", base_df, additional_keys={"region": "US", "status": None}
        )

        # Append with None value in same structure
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "test_table", append_df, additional_keys={"region": "EU", "status": None}
        )

        # Should work correctly
        assert result["region"].unique().to_list() == ["EU"]
        assert result["status"].unique().to_list() == [None]

    def test_append_large_dataset_performance_warning(self):
        """Test that large dataset appends work without issues."""
        # Load base table
        base_df = pl.DataFrame({"age": [30], "rate": [0.001]})
        load_assumptions("large_table", base_df, additional_keys={"batch": 1})

        # Append larger dataset (but not huge to avoid slow tests)
        large_ages = list(range(31, 131))  # 100 ages
        append_df = pl.DataFrame({"age": large_ages, "rate": [0.001] * 100})
        result = append_assumptions(
            "large_table", append_df, additional_keys={"batch": 2}
        )

        # Should handle large dataset correctly
        # This becomes a curve table: 100 rows with age, batch, rate columns
        assert len(result) == 100
        assert result["batch"].unique().to_list() == [2]

    def test_append_with_string_numeric_columns(self):
        """Test append with columns that look numeric but are strings."""
        # Load base table with string columns that look numeric
        base_df = pl.DataFrame({"policy": ["1", "2"], "rate": [0.001, 0.002]})
        load_assumptions("string_table", base_df, additional_keys={"version": "v1"})

        # Append similar data
        append_df = pl.DataFrame({"policy": ["3", "4"], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "string_table", append_df, additional_keys={"version": "v2"}
        )

        # Should process correctly as curve table
        assert result["version"].unique().to_list() == ["v2"]
        # Check that policy values are preserved and converted to f64
        expected_columns = {"policy", "version", "rate"}
        assert set(result.columns) == expected_columns
        # Policy values should be converted to f64 (3.0, 4.0)
        assert result["policy"].to_list() == [3.0, 4.0]

    def test_append_empty_dataframe(self):
        """Test append with empty DataFrame should raise appropriate error."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("empty_test", base_df, additional_keys={"source": "base"})

        # Try to append empty DataFrame - should raise ValueError
        empty_df = pl.DataFrame(
            {"age": [], "rate": []}, schema={"age": pl.Int64, "rate": pl.Float64}
        )
        with pytest.raises(ValueError, match="DataFrame is empty"):
            append_assumptions(
                "empty_test", empty_df, additional_keys={"source": "empty"}
            )

    def test_append_with_different_data_types(self):
        """Test append with different but compatible data types."""
        # Load base table with int ages
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("type_test", base_df, additional_keys={"batch": 1})

        # Append with float ages (should be compatible)
        append_df = pl.DataFrame({"age": [32.0, 33.0], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "type_test", append_df, additional_keys={"batch": 2}
        )

        # Should work and convert types appropriately
        assert result["batch"].unique().to_list() == [2]
        # This is a curve table, so age values are in the age column (not melted)
        age_values = result["age"].to_list()
        assert age_values == [32.0, 33.0]
        # Check that all columns are present
        expected_columns = {"age", "batch", "rate"}
        assert set(result.columns) == expected_columns

    def test_append_preserves_original_table_functionality(self):
        """Test that original table functionality is preserved after append."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions("preserve_test", base_df, additional_keys={"sex": "M"})

        # Append data
        append_df = pl.DataFrame({"age": [30, 31], "rate": [0.0008, 0.0016]})
        append_assumptions("preserve_test", append_df, additional_keys={"sex": "F"})

        # Original table configuration should be preserved
        config = _get_table_config("preserve_test")
        assert config["additional_keys"] == {"sex": "M"}  # Original config
        assert config["value"] == "rate"
        assert config["overflow"] == "auto"

    def test_append_multiple_sequential_appends(self):
        """Test multiple sequential appends to the same table."""
        # Load base table
        base_df = pl.DataFrame({"age": [30], "rate": [0.001]})
        load_assumptions("multi_append", base_df, additional_keys={"batch": 1})

        # First append
        append1_df = pl.DataFrame({"age": [31], "rate": [0.002]})
        result1 = append_assumptions(
            "multi_append", append1_df, additional_keys={"batch": 2}
        )
        assert result1["batch"].unique().to_list() == [2]

        # Second append
        append2_df = pl.DataFrame({"age": [32], "rate": [0.003]})
        result2 = append_assumptions(
            "multi_append", append2_df, additional_keys={"batch": 3}
        )
        assert result2["batch"].unique().to_list() == [3]

        # Table should still exist and be appendable
        assert _table_exists("multi_append")

    def test_append_with_special_characters_in_additional_keys(self):
        """Test append with special characters in additional_keys values."""
        # Load base table
        base_df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})
        load_assumptions(
            "special_chars",
            base_df,
            additional_keys={"region": "US-East", "type": "A&B"},
        )

        # Append with different special characters
        append_df = pl.DataFrame({"age": [32, 33], "rate": [0.003, 0.004]})
        result = append_assumptions(
            "special_chars",
            append_df,
            additional_keys={"region": "EU-West", "type": "C&D"},
        )

        # Should handle special characters correctly
        assert result["region"].unique().to_list() == ["EU-West"]
        assert result["type"].unique().to_list() == ["C&D"]
