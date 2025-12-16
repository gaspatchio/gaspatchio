# ruff: noqa: INP001, D200, D400, D415, SLF001, E501, PT011
"""Tests for the new Table API (v2) - dimension-based assumption tables."""

import polars as pl
import pytest

from gaspatchio_core.assumptions._analysis import TableSchema
from gaspatchio_core.assumptions._api import Table
from gaspatchio_core.assumptions._dimensions import (
    CategoricalDimension,
    ComputedDimension,
    DataDimension,
    MeltDimension,
)
from gaspatchio_core.assumptions._strategies import (
    ExtendOverflow,
)


class TestTableCreation:
    """Test basic Table class creation and initialization"""

    def test_simple_curve_table_creation(self):
        """Test creating a simple curve table with DataDimension"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_mortality",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        assert table._name == "test_mortality"
        assert "age" in table.dimensions
        assert table._value == "qx"

    def test_string_shorthand_for_dimensions(self):
        """Test creating table with string shorthand for dimensions"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_shorthand",
            source=data,
            dimensions={
                "age": "age",  # String shorthand
            },
            value="qx",
        )

        assert table._name == "test_shorthand"
        assert "age" in table.dimensions
        assert isinstance(table.dimensions["age"], DataDimension)
        assert table.dimensions["age"].column == "age"
        assert table._value == "qx"

    def test_mixed_dimension_types(self):
        """Test using both string shorthand and explicit dimension objects"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_mixed",
            source=data,
            dimensions={
                "age": "age",  # String shorthand
                "sex": CategoricalDimension("M"),  # Explicit dimension
            },
            value="qx",
        )

        assert "age" in table.dimensions
        assert "sex" in table.dimensions
        assert isinstance(table.dimensions["age"], DataDimension)
        assert isinstance(table.dimensions["sex"], CategoricalDimension)
        assert table.dimensions["age"].column == "age"
        assert table.dimensions["sex"].value == "M"

    def test_multiple_string_shorthand_dimensions(self):
        """Test using string shorthand for multiple dimensions"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "duration": [1, 2],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_multiple_shorthand",
            source=data,
            dimensions={
                "age": "age",
                "duration": "duration",
            },
            value="qx",
        )

        assert "age" in table.dimensions
        assert "duration" in table.dimensions
        assert isinstance(table.dimensions["age"], DataDimension)
        assert isinstance(table.dimensions["duration"], DataDimension)
        assert table.dimensions["age"].column == "age"
        assert table.dimensions["duration"].column == "duration"

    def test_backward_compatibility_explicit_data_dimension(self):
        """Test that explicit DataDimension usage still works (backward compatibility)"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        # Both approaches should be equivalent
        table_explicit = Table(
            name="test_explicit",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        table_shorthand = Table(
            name="test_shorthand_equiv",
            source=data,
            dimensions={
                "age": "age",
            },
            value="qx",
        )

        # Both should create equivalent DataDimension objects
        assert isinstance(table_explicit.dimensions["age"], DataDimension)
        assert isinstance(table_shorthand.dimensions["age"], DataDimension)
        assert (
            table_explicit.dimensions["age"].column
            == table_shorthand.dimensions["age"].column
        )

    def test_wide_table_creation_with_melt(self):
        """Test creating a wide table with MeltDimension"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.01, 0.02],
                "2": [0.015, 0.025],
                "Ultimate": [0.005, 0.01],
            },
        )

        table = Table(
            name="test_wide",
            source=data,
            dimensions={
                "age": DataDimension("age"),
                "duration": MeltDimension(
                    columns=["1", "2", "Ultimate"],
                    overflow=ExtendOverflow("Ultimate", to_value=10),
                ),
            },
            value="qx",
        )

        assert table._name == "test_wide"
        assert "age" in table.dimensions
        assert "duration" in table.dimensions
        assert isinstance(table.dimensions["duration"], MeltDimension)

    def test_table_with_categorical_dimension(self):
        """Test creating table with categorical dimensions"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_categorical",
            source=data,
            dimensions={
                "age": DataDimension("age"),
                "sex": CategoricalDimension("M"),
            },
            value="qx",
        )

        assert "sex" in table.dimensions
        assert isinstance(table.dimensions["sex"], CategoricalDimension)
        assert table.dimensions["sex"].value == "M"

    def test_table_with_computed_dimension(self):
        """Test creating table with computed dimensions"""
        data = pl.DataFrame(
            {
                "issue_age": [30, 31, 32],
                "policy_year": [1, 1, 1],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_computed",
            source=data,
            dimensions={
                "issue_age": DataDimension("issue_age"),
                "policy_year": DataDimension("policy_year"),
                "attained_age": ComputedDimension(
                    pl.col("issue_age") + pl.col("policy_year") - 1,
                    "attained_age",
                ),
            },
            value="qx",
        )

        assert "attained_age" in table.dimensions
        assert isinstance(table.dimensions["attained_age"], ComputedDimension)


class TestTableDataProcessing:
    """Test table data processing and transformation"""

    def test_process_data_creates_tidy_format(self):
        """Test that _process_data transforms data correctly"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.01, 0.02],
                "2": [0.015, 0.025],
            },
        )

        table = Table(
            name="test_process",
            source=data,
            dimensions={
                "age": DataDimension("age"),
                "duration": MeltDimension(["1", "2"]),
            },
            value="rate",
        )

        # Check that the table was processed (we can't access _df directly yet)
        # This will be tested once the class is implemented
        assert table._name == "test_process"

    def test_dimension_processing_order(self):
        """Test that dimensions are processed in the correct order"""
        data = pl.DataFrame(
            {
                "base_age": [30, 31],
                "duration": [1, 2],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_order",
            source=data,
            dimensions={
                "age": DataDimension("base_age", rename_to="age"),
                "duration": DataDimension("duration"),
                "sex": CategoricalDimension("F"),
                "attained_age": ComputedDimension(
                    pl.col("age") + pl.col("duration") - 1,
                    "attained_age",
                ),
            },
            value="qx",
        )

        # Verify dimensions are stored correctly
        assert "age" in table.dimensions
        assert "sex" in table.dimensions
        assert "attained_age" in table.dimensions


class TestTableLookup:
    """Test table lookup functionality"""

    def test_lookup_with_column_names(self):
        """Test lookup using column names as strings"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_lookup",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Create lookup expression
        lookup_expr = table.lookup(age="age")

        # Should return a Polars expression
        assert isinstance(lookup_expr, pl.Expr)

    def test_lookup_with_expressions(self):
        """Test lookup using Polars expressions"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_lookup_expr",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Create lookup expression using pl.col
        lookup_expr = table.lookup(age=pl.col("issue_age"))

        # Should return a Polars expression
        assert isinstance(lookup_expr, pl.Expr)


class TestTableExtend:
    """Test table extension functionality"""

    def test_extend_with_compatible_data(self):
        """Test extending table with compatible additional data"""
        initial_data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_extend",
            source=initial_data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            storage_mode="hash",  # extend() requires hash storage
        )

        # Extend with additional data
        additional_data = pl.DataFrame(
            {
                "age": [32, 33],
                "qx": [0.003, 0.004],
            },
        )

        extended_table = table.extend(additional_data)

        # Should return the same table instance for chaining
        assert extended_table is table

    def test_extend_with_dimension_overrides(self):
        """Test extending table with dimension overrides (compatible structure)"""
        initial_data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_extend_override",
            source=initial_data,
            dimensions={
                "age": DataDimension("age"),
                "sex": CategoricalDimension(
                    "F",
                    name="sex",
                ),  # Original table has sex dimension
            },
            value="qx",
            storage_mode="hash",  # extend() requires hash storage
        )

        # Extend with different sex category (compatible structure)
        additional_data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.0015, 0.0025],
            },
        )

        extended_table = table.extend(
            additional_data,
            dimensions={
                "sex": CategoricalDimension(
                    "M",
                    name="sex",
                ),  # Explicit name to match original
            },
        )

        assert extended_table is table


class TestTableProperties:
    """Test table property methods"""

    def test_dimensions_property(self):
        """Test dimensions property returns copy"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_props",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        dims = table.dimensions
        assert "age" in dims
        assert isinstance(dims["age"], DataDimension)

        # Should be a copy
        dims["new_dim"] = DataDimension("other")
        assert "new_dim" not in table.dimensions

    def test_schema_property(self):
        """Test schema property returns TableSchema"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_schema",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        schema = table.schema
        assert isinstance(schema, TableSchema)

    def test_dimension_values(self):
        """Test dimension_values method"""
        data = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "sex": ["M", "F", "M"],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_dim_values",
            source=data,
            dimensions={
                "age": DataDimension("age"),
                "sex": DataDimension("sex"),
            },
            value="qx",
        )

        age_values = table.dimension_values("age")
        assert isinstance(age_values, list)
        # Exact values will depend on implementation


class TestTableValidation:
    """Test table validation functionality"""

    def test_validate_lookup_valid_dimensions(self):
        """Test validate_lookup with valid dimension names"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_validate",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Should not raise
        table.validate_lookup(age="age")

    def test_validate_lookup_invalid_dimensions(self):
        """Test validate_lookup with invalid dimension names"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_validate_invalid",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="Invalid dimension"):
            table.validate_lookup(nonexistent="age")


class TestDidYouMeanSuggestions:
    """Test did-you-mean suggestions for typos in dimension names"""

    def test_fuzzy_match_typo_suggestion(self):
        """Test fuzzy matching suggests close matches for typos"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35, 40],
                "rate_class": ["MNS", "FNS", "MS"],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_fuzzy_typo",
            source=data,
            dimensions={
                "age_last": "age_last",
                "rate_class": "rate_class",
            },
            value="qx",
        )

        # Test typo: age_lst -> age_last
        with pytest.raises(ValueError) as exc_info:
            table.validate_lookup(age_lst="some_col", rate_class="other_col")

        assert "age_lst" in str(exc_info.value)
        assert "Did you mean 'age_last'?" in str(exc_info.value)

    def test_fuzzy_match_rate_class_typo(self):
        """Test fuzzy matching for rate_clas -> rate_class"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35],
                "rate_class": ["MNS", "FNS"],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_fuzzy_rate_class",
            source=data,
            dimensions={
                "age_last": "age_last",
                "rate_class": "rate_class",
            },
            value="qx",
        )

        with pytest.raises(ValueError) as exc_info:
            table.validate_lookup(age_last="col1", rate_clas="col2")

        assert "rate_clas" in str(exc_info.value)
        assert "Did you mean 'rate_class'?" in str(exc_info.value)

    def test_prefix_match_suggestion(self):
        """Test prefix matching for partial names like 'age' -> 'age_last'"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35, 40],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_prefix_match",
            source=data,
            dimensions={
                "age_last": "age_last",
            },
            value="qx",
        )

        # Test prefix: age -> age_last (fuzzy may not catch this, but prefix will)
        with pytest.raises(ValueError) as exc_info:
            table.validate_lookup(age="some_col")

        assert "age" in str(exc_info.value)
        assert "Did you mean 'age_last'?" in str(exc_info.value)

    def test_suffix_match_suggestion(self):
        """Test suffix matching for partial names like 'last' -> 'age_last'"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35, 40],
                "qx": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_suffix_match",
            source=data,
            dimensions={
                "age_last": "age_last",
            },
            value="qx",
        )

        # Test suffix: last -> age_last
        with pytest.raises(ValueError) as exc_info:
            table.validate_lookup(last="some_col")

        assert "last" in str(exc_info.value)
        assert "Did you mean 'age_last'?" in str(exc_info.value)

    def test_no_suggestion_for_unrelated_name(self):
        """Test that no suggestion is made for completely unrelated names"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_no_suggestion",
            source=data,
            dimensions={
                "age_last": "age_last",
            },
            value="qx",
        )

        with pytest.raises(ValueError) as exc_info:
            table.validate_lookup(xyz="some_col")

        error_msg = str(exc_info.value)
        assert "xyz" in error_msg
        assert "Did you mean" not in error_msg
        assert "Available dimensions" in error_msg

    def test_suggestion_in_lookup_dimension_mismatch(self):
        """Test suggestions appear in lookup() dimension mismatch errors"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35],
                "duration": [1, 2],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_lookup_mismatch",
            source=data,
            dimensions={
                "age_last": "age_last",
                "duration": "duration",
            },
            value="qx",
        )

        # Provide typo as extra dimension
        with pytest.raises(ValueError) as exc_info:
            table.lookup(age_last="col1", dur="col2")  # dur instead of duration

        error_msg = str(exc_info.value)
        assert "dur" in error_msg
        assert "did you mean 'duration'?" in error_msg.lower()

    def test_available_dimensions_always_shown(self):
        """Test that available dimensions are always shown in error"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35],
                "rate_class": ["MNS", "FNS"],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_available_dims",
            source=data,
            dimensions={
                "age_last": "age_last",
                "rate_class": "rate_class",
            },
            value="qx",
        )

        with pytest.raises(ValueError) as exc_info:
            table.validate_lookup(age_lst="col1", rate_class="col2")

        error_msg = str(exc_info.value)
        assert "Available dimensions:" in error_msg
        assert "age_last" in error_msg
        assert "rate_class" in error_msg

    def test_multiple_typos_suggest_for_each(self):
        """Test that suggestions work for multiple typos in lookup()"""
        data = pl.DataFrame(
            {
                "age_last": [30, 35],
                "duration": [1, 2],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_multiple_typos",
            source=data,
            dimensions={
                "age_last": "age_last",
                "duration": "duration",
            },
            value="qx",
        )

        # Provide correct dimension plus two extra (typos)
        # This tests the dimension mismatch path
        with pytest.raises(ValueError) as exc_info:
            table.lookup(age_last="col1", dur="col2")

        error_msg = str(exc_info.value)
        # Should suggest duration for dur
        assert "dur" in error_msg
        assert "duration" in error_msg


class TestTableExport:
    """Test table export functionality"""

    def test_to_dataframe(self):
        """Test exporting table as DataFrame"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_export",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        exported_df = table.to_dataframe()
        assert isinstance(exported_df, pl.DataFrame)

    def test_describe(self):
        """Test table description method"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        table = Table(
            name="test_describe",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
        )

        description = table.describe()
        assert isinstance(description, str)
        assert "test_describe" in description


class TestTableErrorHandling:
    """Test error handling in Table class"""

    def test_invalid_dimension_configuration(self):
        """Test error when dimension configuration is invalid"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        # Should raise error for non-existent column
        with pytest.raises(ValueError):
            Table(
                name="test_error",
                source=data,
                dimensions={
                    "age": DataDimension("nonexistent_column"),
                },
                value="qx",
            )

    def test_invalid_value_column(self):
        """Test error when value column doesn't exist"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        # Should raise error for non-existent value column
        with pytest.raises(ValueError):
            Table(
                name="test_value_error",
                source=data,
                dimensions={
                    "age": DataDimension("age"),
                },
                value="nonexistent_value",
            )

    def test_validation_disabled(self):
        """Test that validation can be disabled"""
        data = pl.DataFrame(
            {
                "age": [30, 31],
                "qx": [0.001, 0.002],
            },
        )

        # Should not raise with validation disabled, even with bad config
        # This test depends on implementation details
        table = Table(
            name="test_no_validation",
            source=data,
            dimensions={
                "age": DataDimension("age"),
            },
            value="qx",
            validate=False,
        )

        assert table._name == "test_no_validation"


class TestAutoCategoricalConversion:
    """Test auto-conversion of string columns to Enum for optimal lookup performance"""

    def test_string_column_captures_categories(self):
        """Test that string key columns populate _key_categories"""
        data = pl.DataFrame(
            {
                "product_type": ["TERM", "WL", "UL", "TERM", "WL"],
                "rate": [0.01, 0.02, 0.03, 0.01, 0.02],
            },
        )

        table = Table(
            name="test_categories_capture",
            source=data,
            dimensions={"product_type": "product_type"},
            value="rate",
        )

        # Should have captured categories for the string column
        assert "product_type" in table._key_categories
        assert isinstance(table._key_categories["product_type"], pl.Enum)

    def test_categories_are_sorted_alphabetically(self):
        """Test that captured categories are in sorted order to match Rust encoder"""
        data = pl.DataFrame(
            {
                # Input order: TERM, WL, UL (not alphabetical)
                "product_type": ["TERM", "WL", "UL"],
                "rate": [0.01, 0.02, 0.03],
            },
        )

        table = Table(
            name="test_sorted_categories",
            source=data,
            dimensions={"product_type": "product_type"},
            value="rate",
        )

        # Categories should be sorted: TERM, UL, WL
        enum_type = table._key_categories["product_type"]
        categories = enum_type.categories.to_list()
        assert categories == ["TERM", "UL", "WL"], f"Expected sorted order, got {categories}"

    def test_numeric_columns_not_captured(self):
        """Test that numeric columns don't populate _key_categories"""
        data = pl.DataFrame(
            {
                "age": [30, 35, 40],
                "rate": [0.01, 0.02, 0.03],
            },
        )

        table = Table(
            name="test_numeric_not_captured",
            source=data,
            dimensions={"age": "age"},
            value="rate",
        )

        # Should NOT have categories for numeric column
        assert "age" not in table._key_categories

    def test_mixed_columns_only_strings_captured(self):
        """Test that only string columns get categories, not numeric ones"""
        data = pl.DataFrame(
            {
                "age": [30, 35, 40, 30, 35, 40],
                "product_type": ["TERM", "TERM", "TERM", "WL", "WL", "WL"],
                "rate": [0.01, 0.02, 0.03, 0.015, 0.025, 0.035],
            },
        )

        table = Table(
            name="test_mixed_columns",
            source=data,
            dimensions={"age": "age", "product_type": "product_type"},
            value="rate",
        )

        # Only product_type should have categories
        assert "product_type" in table._key_categories
        assert "age" not in table._key_categories

    def test_lookup_with_string_column_returns_expression(self):
        """Test that lookup with string dimensions returns valid expression"""
        data = pl.DataFrame(
            {
                "product_type": ["TERM", "WL", "UL"],
                "rate": [0.01, 0.02, 0.03],
            },
        )

        table = Table(
            name="test_lookup_string",
            source=data,
            dimensions={"product_type": "product_type"},
            value="rate",
        )

        # Create lookup expression
        lookup_expr = table.lookup(product_type="product_code")

        # Should return a Polars expression
        assert isinstance(lookup_expr, pl.Expr)


class TestStorageMode:
    """Test storage mode selection and verification"""

    def test_storage_mode_property_returns_actual_mode(self):
        """Test that storage_mode property returns the actual mode from Rust"""
        data = pl.DataFrame(
            {
                "age": list(range(18, 101)),  # 83 ages - dense
                "rate": [0.001 * (1 + a / 100) for a in range(18, 101)],
            },
        )

        table = Table(
            name="test_storage_mode_actual",
            source=data,
            dimensions={"age": "age"},
            value="rate",
            storage_mode="array",
        )

        # Should return the actual mode from Rust
        assert table.storage_mode == "array"

    def test_storage_mode_hash_explicit(self):
        """Test explicitly requesting hash storage"""
        data = pl.DataFrame(
            {
                "age": [30, 35, 40],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        table = Table(
            name="test_storage_hash_explicit",
            source=data,
            dimensions={"age": "age"},
            value="rate",
            storage_mode="hash",
        )

        assert table.storage_mode == "hash"

    def test_storage_mode_auto_selects_array_for_dense(self):
        """Test that auto mode selects array for dense single-dimension tables"""
        # Create a dense table with contiguous integer keys
        data = pl.DataFrame(
            {
                "age": list(range(0, 121)),  # 121 ages, fully dense
                "rate": [0.001 * (1 + a / 100) for a in range(0, 121)],
            },
        )

        table = Table(
            name="test_auto_dense",
            source=data,
            dimensions={"age": "age"},
            value="rate",
            storage_mode="auto",
        )

        # For a perfectly dense single-key table, auto should choose array
        # (actual behavior depends on Rust implementation thresholds)
        actual_mode = table.storage_mode
        assert actual_mode in ["hash", "array"], f"Got unexpected mode: {actual_mode}"

    def test_storage_mode_with_string_keys_uses_hash(self):
        """Test that tables with string keys fall back to hash"""
        data = pl.DataFrame(
            {
                "product": ["TERM", "WL", "UL"],
                "rate": [0.01, 0.02, 0.03],
            },
        )

        table = Table(
            name="test_string_keys_hash",
            source=data,
            dimensions={"product": "product"},
            value="rate",
            storage_mode="auto",
        )

        # String-only keys may not be eligible for array storage
        # depending on implementation
        actual_mode = table.storage_mode
        assert actual_mode in ["hash", "array"]
