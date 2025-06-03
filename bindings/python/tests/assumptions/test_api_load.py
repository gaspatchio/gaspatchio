"""
Unit tests for enhanced load_assumptions function with additional_keys support.

Tests cover:
- additional_keys parameter validation and processing
- Configuration storage for append operations
- Integration with existing transformation pipeline
- Backward compatibility with existing functionality
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
from gaspatchio_core.assumptions.api import load_assumptions


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


class TestLoadAssumptionsAdditionalKeys:
    """Test additional_keys parameter functionality."""

    def test_load_with_additional_keys_basic(self):
        """Test load_assumptions with basic additional_keys."""
        df = pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.002, 0.003]})

        result = load_assumptions(
            "test_table", df, additional_keys={"sex": "M", "smoking": "NS"}
        )

        # Check that additional keys were added as columns
        assert "sex" in result.columns
        assert "smoking" in result.columns

        # Check that all rows have the correct values
        assert result["sex"].unique().to_list() == ["M"]
        assert result["smoking"].unique().to_list() == ["NS"]

        # Check table structure - should be wide format with melted columns
        assert "variable" in result.columns  # Variable column from melting
        assert "rate" in result.columns  # Value column (default name)

        # Check that original columns were melted into variable/value pairs
        variables = result["variable"].unique().to_list()
        assert set(variables) == {"age", "rate"}

        # Check we have the right number of rows (original_rows * original_columns)
        assert len(result) == 6  # 3 rows * 2 columns (age + rate)

    def test_load_with_additional_keys_multiple_types(self):
        """Test additional_keys with different value types."""
        df = pl.DataFrame({"duration": [1, 2, 3], "factor": [1.0, 0.9, 0.8]})

        result = load_assumptions(
            "test_table",
            df,
            value="factor",  # Use 'factor' as value column to avoid conflict
            additional_keys={
                "product": "Term Life",
                "year": 2024,
                "active": True,
                "rate": 0.05,  # This can now be an additional key
            },
        )

        # After wide table transformation, we expect:
        # - additional keys: product, year, active, rate
        # - id columns become: product, year, active, rate, variable
        # - value column: factor
        expected_columns = {"product", "year", "active", "rate", "variable", "factor"}
        assert set(result.columns) == expected_columns

        # Check values
        assert result["product"].unique().to_list() == ["Term Life"]
        assert result["year"].unique().to_list() == [2024]
        assert result["active"].unique().to_list() == [True]
        assert result["rate"].unique().to_list() == [0.05]

        # Check that we have the melted structure (duration becomes variable)
        variables = result["variable"].unique().to_list()
        assert "duration" in variables

    def test_load_with_additional_keys_none(self):
        """Test load_assumptions with additional_keys=None (backward compatibility)."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        result = load_assumptions("test_table", df, additional_keys=None)

        # Should work as before
        assert "age" in result.columns
        assert "rate" in result.columns
        assert len(result) == 2

        # No additional columns should be added
        assert set(result.columns) == {"age", "rate"}

    def test_load_with_additional_keys_empty_dict(self):
        """Test load_assumptions with empty additional_keys dictionary."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        result = load_assumptions("test_table", df, additional_keys={})

        # Should work as before
        assert "age" in result.columns
        assert "rate" in result.columns
        assert len(result) == 2

        # No additional columns should be added
        assert set(result.columns) == {"age", "rate"}

    def test_load_with_additional_keys_wide_table(self):
        """Test additional_keys with wide table format."""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "male": [0.001, 0.002, 0.003],
                "female": [0.0008, 0.0016, 0.0024],
            }
        )

        result = load_assumptions(
            "test_table", df, additional_keys={"product": "Life", "basis": "2017_CSO"}
        )

        # Check additional keys were added
        assert "product" in result.columns
        assert "basis" in result.columns

        # Check all rows have the additional key values
        unique_products = result["product"].unique().to_list()
        unique_basis = result["basis"].unique().to_list()
        assert unique_products == ["Life"]
        assert unique_basis == ["2017_CSO"]

        # Check wide table transformation still works
        assert "variable" in result.columns
        assert "rate" in result.columns  # Default value column name


class TestLoadAssumptionsConfigurationStorage:
    """Test configuration storage for append operations."""

    def test_configuration_stored_basic(self):
        """Test that configuration is stored after successful load."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        load_assumptions("test_table", df, additional_keys={"sex": "M"})

        # Check table exists in configuration
        assert _table_exists("test_table")

        # Check configuration content
        config = _get_table_config("test_table")
        assert config["additional_keys"] == {"sex": "M"}
        assert config["value"] == "rate"  # Default value
        assert config["overflow"] == "auto"  # Default overflow

    def test_configuration_stored_with_all_parameters(self):
        """Test configuration storage with all parameters specified."""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, 0.002],
                "2": [0.0008, 0.0016],
                "Ultimate": [0.0005, 0.001],
            }
        )

        load_assumptions(
            "test_table",
            df,
            id=["age"],
            value="mortality_rate",
            overflow="Ultimate",
            max_overflow=150,
            lookup_keys=[
                "issue_age",
                "sex",
                "smoking",
                "duration",
            ],  # 4 keys: age + 2 additional + variable
            additional_keys={"sex": "F", "smoking": "SM"},
            metadata={"source": "test"},
        )

        config = _get_table_config("test_table")
        assert config["id"] == ["age"]
        assert config["value"] == "mortality_rate"
        assert config["overflow"] == "Ultimate"
        assert config["max_overflow"] == 150
        assert config["lookup_keys"] == ["issue_age", "sex", "smoking", "duration"]
        assert config["additional_keys"] == {"sex": "F", "smoking": "SM"}

    def test_configuration_stored_with_none_values(self):
        """Test configuration storage with None values."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        load_assumptions(
            "test_table",
            df,
            id=None,
            value_vars=None,
            lookup_keys=None,
            additional_keys=None,
            metadata=None,
        )

        config = _get_table_config("test_table")
        assert config["id"] is None
        assert config["value_vars"] is None
        assert config["lookup_keys"] is None
        assert config["additional_keys"] is None


class TestLoadAssumptionsValidation:
    """Test validation integration with additional_keys."""

    def test_additional_keys_validation_invalid_type(self):
        """Test validation error for invalid additional_keys type."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        with pytest.raises(ValueError, match="additional_keys must be a dictionary"):
            load_assumptions("test_table", df, additional_keys="invalid")

    def test_additional_keys_validation_non_string_keys(self):
        """Test validation error for non-string keys."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        with pytest.raises(
            ValueError, match="All additional_keys must have string keys"
        ):
            load_assumptions("test_table", df, additional_keys={123: "value"})

    def test_additional_keys_validation_empty_keys(self):
        """Test validation error for empty string keys."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        with pytest.raises(ValueError, match="non-empty string keys"):
            load_assumptions("test_table", df, additional_keys={"": "value"})

    def test_additional_keys_validation_whitespace_keys(self):
        """Test validation error for whitespace-only keys."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        with pytest.raises(ValueError, match="non-empty string keys"):
            load_assumptions("test_table", df, additional_keys={"   ": "value"})


class TestLoadAssumptionsBackwardCompatibility:
    """Test that existing functionality remains unchanged."""

    def test_backward_compatibility_curve_table(self):
        """Test that curve tables work exactly as before."""
        df = pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.002, 0.003]})

        result = load_assumptions("test_table", df)

        # Should work exactly as before
        assert set(result.columns) == {"age", "rate"}
        assert len(result) == 3
        assert result["age"].to_list() == [30.0, 31.0, 32.0]  # Converted to f64
        assert result["rate"].to_list() == [0.001, 0.002, 0.003]

    def test_backward_compatibility_wide_table(self):
        """Test that wide tables work exactly as before."""
        df = pl.DataFrame(
            {"age": [30, 31], "male": [0.001, 0.002], "female": [0.0008, 0.0016]}
        )

        result = load_assumptions("test_table", df)

        # Should work exactly as before
        expected_columns = {"age", "variable", "rate"}
        assert set(result.columns) == expected_columns
        assert len(result) == 4  # 2 ages * 2 variables

        # Check melted structure
        variables = result["variable"].unique().to_list()
        assert set(variables) == {"male", "female"}

    def test_backward_compatibility_all_parameters(self):
        """Test that all existing parameters still work."""
        df = pl.DataFrame(
            {"age": [30, 31], "1": [0.001, 0.002], "Ultimate": [0.0005, 0.001]}
        )

        result = load_assumptions(
            "test_table",
            df,
            id=["age"],
            value="mortality_rate",
            overflow="Ultimate",
            max_overflow=100,
            lookup_keys=["issue_age", "duration"],
            metadata={"source": "test_data"},
        )

        # Should work as before with all existing functionality
        assert "issue_age" in result.columns  # Renamed from age
        assert "duration" in result.columns  # Variable column renamed
        assert "mortality_rate" in result.columns  # Custom value column name


class TestLoadAssumptionsIntegration:
    """Test integration with transformation pipeline."""

    def test_additional_keys_with_overflow_expansion(self):
        """Test additional_keys works with overflow expansion."""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, 0.002],
                "2": [0.0008, 0.0016],
                "Ultimate": [0.0005, 0.001],
            }
        )

        result = load_assumptions(
            "test_table",
            df,
            overflow="Ultimate",
            max_overflow=5,
            additional_keys={"sex": "M", "product": "Term"},
        )

        # Check additional keys are present
        assert "sex" in result.columns
        assert "product" in result.columns

        # Check all rows have the additional key values
        assert result["sex"].unique().to_list() == ["M"]
        assert result["product"].unique().to_list() == ["Term"]

        # Check overflow expansion worked
        variables = result["variable"].unique().to_list()
        assert "5" in variables  # Should be expanded to max_overflow

    def test_additional_keys_with_custom_lookup_keys(self):
        """Test additional_keys works with custom lookup keys."""
        df = pl.DataFrame(
            {"age": [30, 31], "male": [0.001, 0.002], "female": [0.0008, 0.0016]}
        )

        result = load_assumptions(
            "test_table",
            df,
            id=["age"],  # Explicitly include age as id column
            lookup_keys=[
                "issue_age",
                "basis",
                "version",
                "gender",
            ],  # 4 keys: age + 2 additional + variable
            additional_keys={"basis": "2017_CSO", "version": "v1.0"},
        )

        # Check columns were renamed correctly
        assert "issue_age" in result.columns
        assert "gender" in result.columns

        # Check additional keys are present
        assert "basis" in result.columns
        assert "version" in result.columns

        # Check values
        assert result["basis"].unique().to_list() == ["2017_CSO"]
        assert result["version"].unique().to_list() == ["v1.0"]

    def test_additional_keys_column_order(self):
        """Test that additional keys appear in the correct position."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        result = load_assumptions(
            "test_table", df, additional_keys={"sex": "M", "smoking": "NS"}
        )

        # Additional keys should be added after original columns during materialization
        # For wide tables, the structure becomes: additional_keys + variable + value
        assert "sex" in result.columns
        assert "smoking" in result.columns
        assert "variable" in result.columns  # Original 'age' column becomes this
        assert "rate" in result.columns  # Value column

        # Check the variable column contains the original column names
        variables = result["variable"].unique().to_list()
        assert "age" in variables


class TestLoadAssumptionsFileIntegration:
    """Test additional_keys with file sources."""

    def test_additional_keys_with_csv_file(self):
        """Test additional_keys works with CSV file source."""
        # Create temporary CSV file
        csv_content = "age,rate\n30,0.001\n31,0.002\n32,0.003"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = f.name

        try:
            result = load_assumptions(
                "test_table", csv_path, additional_keys={"sex": "F", "smoking": "SM"}
            )

            # Check additional keys were added
            assert "sex" in result.columns
            assert "smoking" in result.columns
            assert result["sex"].unique().to_list() == ["F"]
            assert result["smoking"].unique().to_list() == ["SM"]

            # Check CSV data was loaded correctly - wide table transformation
            assert "variable" in result.columns  # Original 'age' column becomes this
            assert "rate" in result.columns  # Value column
            assert len(result) == 6  # 3 rows * 2 original columns (age, rate)

            # Check the variable column contains the original column names
            variables = result["variable"].unique().to_list()
            assert "age" in variables

        finally:
            # Clean up temporary file
            Path(csv_path).unlink(missing_ok=True)

    def test_additional_keys_with_path_object(self):
        """Test additional_keys works with Path object source."""
        # Create temporary CSV file
        csv_content = "duration,factor\n1,1.0\n2,0.9\n3,0.8"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            csv_path = Path(f.name)

        try:
            result = load_assumptions(
                "test_table",
                csv_path,
                additional_keys={"product": "Whole Life", "year": 2024},
            )

            # Check additional keys were added
            assert "product" in result.columns
            assert "year" in result.columns
            assert result["product"].unique().to_list() == ["Whole Life"]
            assert result["year"].unique().to_list() == [2024]

        finally:
            # Clean up temporary file
            csv_path.unlink(missing_ok=True)


class TestLoadAssumptionsEdgeCases:
    """Test edge cases and important scenarios."""

    def test_additional_keys_column_conflict_detected(self):
        """Test that column name conflicts are properly detected and reported."""
        df = pl.DataFrame({"age": [30, 31], "sex": [0.001, 0.002]})

        with pytest.raises(
            ValueError, match="additional_keys contain column names that already exist"
        ):
            load_assumptions(
                "test_table",
                df,
                additional_keys={
                    "sex": "M",
                    "smoking": "NS",
                },  # 'sex' conflicts with existing column
            )

    def test_additional_keys_with_curve_table_detection(self):
        """Test additional_keys behavior with curve tables (non-wide tables)."""
        # Curve table: single value column, explicit id to prevent melting
        df = pl.DataFrame({"age": [30, 31, 32], "rate": [0.001, 0.002, 0.003]})

        result = load_assumptions(
            "test_table",
            df,
            id=["age"],  # Explicitly specify id to maintain curve table structure
            additional_keys={"sex": "M", "product": "Term"},
        )

        # For curve tables, we should get: additional_keys + original columns
        expected_columns = {"age", "rate", "sex", "product"}
        assert set(result.columns) == expected_columns

        # All rows should have the additional key values
        assert result["sex"].unique().to_list() == ["M"]
        assert result["product"].unique().to_list() == ["Term"]
        assert len(result) == 3  # Original row count preserved

    def test_additional_keys_ordering_with_explicit_id(self):
        """Test that additional_keys are properly added to explicitly provided id columns."""
        df = pl.DataFrame({"age": [30, 31], "duration": [1, 2], "rate": [0.001, 0.002]})

        result = load_assumptions(
            "test_table",
            df,
            id=["age"],  # Explicitly specify only age as id
            additional_keys={"sex": "F", "smoking": "NS"},
        )

        # Result should have: age (id) + additional_keys + variable (duration) + value (rate)
        expected_columns = {"age", "sex", "smoking", "variable", "rate"}
        assert set(result.columns) == expected_columns

        # Check that duration became a variable
        variables = result["variable"].unique().to_list()
        assert "duration" in variables

    def test_additional_keys_complex_value_types(self):
        """Test additional_keys with various Python types."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        result = load_assumptions(
            "test_table",
            df,
            additional_keys={
                "string_key": "text_value",
                "int_key": 42,
                "float_key": 3.14159,
                "bool_key": False,
                "none_key": None,
            },
        )

        # Check all types are preserved
        assert result["string_key"].unique().to_list() == ["text_value"]
        assert result["int_key"].unique().to_list() == [42]
        assert result["float_key"].unique().to_list() == [3.14159]
        assert result["bool_key"].unique().to_list() == [False]
        assert result["none_key"].unique().to_list() == [None]

    def test_additional_keys_with_empty_dataframe(self):
        """Test additional_keys behavior with empty DataFrame (should fail appropriately)."""
        df = pl.DataFrame(
            {"age": [], "rate": []}, schema={"age": pl.Int64, "rate": pl.Float64}
        )

        # Empty DataFrames should be rejected
        with pytest.raises(ValueError, match="DataFrame is empty"):
            load_assumptions(
                "test_table", df, additional_keys={"sex": "M", "product": "Life"}
            )

    def test_additional_keys_with_single_row(self):
        """Test additional_keys with single row DataFrame."""
        df = pl.DataFrame({"age": [65], "male": [0.05], "female": [0.03]})

        result = load_assumptions(
            "test_table", df, additional_keys={"basis": "mortality", "year": 2024}
        )

        # When id=None, all original columns (age, male, female) become value columns
        # So we get: 1 row * 3 original columns = 3 rows
        assert len(result) == 3  # 1 row * 3 value columns (age, male, female)
        assert result["basis"].unique().to_list() == ["mortality"]
        assert result["year"].unique().to_list() == [2024]

        # Check that all original columns became variables
        variables = result["variable"].unique().to_list()
        assert set(variables) == {"age", "male", "female"}

    def test_additional_keys_configuration_storage_integration(self):
        """Test that additional_keys integrate properly with configuration storage."""
        df = pl.DataFrame({"age": [30, 31], "rate": [0.001, 0.002]})

        # Load with complex additional_keys
        load_assumptions(
            "test_table",
            df,
            id=["age"],
            value="custom_rate",
            overflow="auto",
            additional_keys={"sex": "M", "smoking": "NS", "basis": "2017_CSO"},
        )

        # Verify configuration was stored correctly
        config = _get_table_config("test_table")
        assert config["additional_keys"] == {
            "sex": "M",
            "smoking": "NS",
            "basis": "2017_CSO",
        }
        assert config["id"] == ["age"]
        assert config["value"] == "custom_rate"

        # Verify table exists for future append operations
        assert _table_exists("test_table")
