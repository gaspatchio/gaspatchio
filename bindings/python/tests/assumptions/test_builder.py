"""Tests for TableBuilder fluent interface."""

from pathlib import Path

import polars as pl
import pytest

from gaspatchio_core.assumptions._api import Table
from gaspatchio_core.assumptions._builder import TableBuilder
from gaspatchio_core.assumptions._dimensions import (
    CategoricalDimension,
    ComputedDimension,
    DataDimension,
    MeltDimension,
)


class TestTableBuilderBasics:
    """Test basic TableBuilder functionality."""

    def test_builder_initialization(self):
        """Test TableBuilder initialization."""
        builder = TableBuilder("test_table")

        assert builder.name == "test_table"
        assert builder._dimensions == {}
        assert builder._source is None
        assert builder._value == "rate"

    def test_builder_repr(self):
        """Test TableBuilder string representation."""
        builder = TableBuilder("test_table")

        expected = (
            "TableBuilder(name='test_table', dimensions=0, source=unset, value='rate')"
        )
        assert repr(builder) == expected

        # Add a dimension and source
        builder.with_data_dimension("age", "age_col").from_source("test.csv")
        expected = (
            "TableBuilder(name='test_table', dimensions=1, source=set, value='rate')"
        )
        assert repr(builder) == expected


class TestTableBuilderFluentInterface:
    """Test fluent interface chaining."""

    def test_from_source_chaining(self):
        """Test from_source returns self for chaining."""
        builder = TableBuilder("test")
        result = builder.from_source("test.csv")

        assert result is builder
        assert builder._source == "test.csv"

    def test_data_dimension_chaining(self):
        """Test with_data_dimension returns self for chaining."""
        builder = TableBuilder("test")
        result = builder.with_data_dimension("age", "age_col")

        assert result is builder
        assert "age" in builder._dimensions
        assert isinstance(builder._dimensions["age"], DataDimension)

    def test_value_column_chaining(self):
        """Test with_value_column returns self for chaining."""
        builder = TableBuilder("test")
        result = builder.with_value_column("mortality_rate")

        assert result is builder
        assert builder._value == "mortality_rate"

    def test_full_fluent_chain(self):
        """Test complete fluent interface chain."""
        df = pl.DataFrame(
            {
                "age": [25, 30, 35],
                "rate": [0.01, 0.02, 0.03],
            },
        )

        table = (
            TableBuilder("test_table")
            .from_source(df)
            .with_data_dimension("age", "age")
            .with_categorical_dimension("product", "term_life")
            .with_value_column("rate")
            .build()
        )

        assert isinstance(table, Table)
        assert table._name == "test_table"


class TestTableBuilderDimensions:
    """Test dimension configuration methods."""

    def test_with_data_dimension(self):
        """Test adding data dimensions."""
        builder = TableBuilder("test")

        # Basic data dimension
        builder.with_data_dimension("age", "age_col")
        dim = builder._dimensions["age"]
        assert isinstance(dim, DataDimension)
        assert dim.column == "age_col"
        assert dim.rename_to is None
        assert dim.dtype is None

        # Data dimension with options
        builder.with_data_dimension(
            "duration",
            "dur",
            rename_to="policy_year",
            dtype=pl.Int32,
        )
        dim = builder._dimensions["duration"]
        assert dim.column == "dur"
        assert dim.rename_to == "policy_year"
        assert dim.dtype == pl.Int32

    def test_with_melt_dimension(self):
        """Test adding melt dimensions."""
        builder = TableBuilder("test")

        # Basic melt dimension
        builder.with_melt_dimension("year", ["2020", "2021", "2022"])
        dim = builder._dimensions["year"]
        assert isinstance(dim, MeltDimension)
        assert dim.columns == ["2020", "2021", "2022"]
        assert dim.name == "year"

        # Melt dimension with strategies
        builder.with_melt_dimension(
            "duration",
            ["1", "2", "3"],
            overflow="extend",
            fill="linear",
        )
        dim = builder._dimensions["duration"]
        assert dim.overflow == "extend"
        assert dim.fill == "linear"

    def test_with_categorical_dimension(self):
        """Test adding categorical dimensions."""
        builder = TableBuilder("test")

        # Basic categorical dimension
        builder.with_categorical_dimension("product", "term_life")
        dim = builder._dimensions["product"]
        assert isinstance(dim, CategoricalDimension)
        assert dim.value == "term_life"
        assert dim.name == "product"

        # Categorical with custom name
        builder.with_categorical_dimension(
            "type",
            "mortality",
            dimension_name="table_type",
        )
        dim = builder._dimensions["type"]
        assert dim.value == "mortality"
        assert dim.name == "table_type"

    def test_with_computed_dimension(self):
        """Test adding computed dimensions."""
        builder = TableBuilder("test")

        # Basic computed dimension
        expr = pl.col("birth_year") + pl.col("duration")
        builder.with_computed_dimension("attained_age", expr)
        dim = builder._dimensions["attained_age"]
        assert isinstance(dim, ComputedDimension)
        # Can't compare expressions directly, just check they're stored
        assert dim.expression is not None
        assert dim.name == "attained_age"

        # Computed with alias
        builder.with_computed_dimension("calc_age", expr, alias="final_age")
        dim = builder._dimensions["calc_age"]
        assert dim.name == "final_age"

    def test_with_dimension_object(self):
        """Test adding pre-configured dimension objects."""
        builder = TableBuilder("test")

        custom_dim = DataDimension("custom_col", rename_to="renamed")
        builder.with_dimension("custom", custom_dim)

        assert builder._dimensions["custom"] is custom_dim


class TestTableBuilderValidation:
    """Test builder validation and error handling."""

    def test_build_without_source_fails(self):
        """Test build fails without source."""
        builder = TableBuilder("test")
        builder.with_data_dimension("age", "age")

        with pytest.raises(ValueError, match="Source must be set"):
            builder.build()

    def test_build_without_dimensions_fails(self):
        """Test build fails without dimensions."""
        builder = TableBuilder("test")
        builder.from_source("test.csv")

        with pytest.raises(
            ValueError,
            match="At least one dimension must be configured",
        ):
            builder.build()

    def test_successful_build_with_minimal_config(self):
        """Test successful build with minimal configuration."""
        df = pl.DataFrame({"age": [25, 30], "rate": [0.01, 0.02]})

        builder = TableBuilder("test")
        table = builder.from_source(df).with_data_dimension("age", "age").build()

        assert isinstance(table, Table)
        assert table._name == "test"


class TestTableBuilderUtilities:
    """Test utility methods."""

    def test_reset_builder(self):
        """Test resetting builder to initial state."""
        builder = TableBuilder("test")
        builder.from_source("test.csv")
        builder.with_data_dimension("age", "age")
        builder.with_value_column("mortality")

        # Verify builder has config
        assert builder._source is not None
        assert len(builder._dimensions) > 0
        assert builder._value == "mortality"

        # Reset and verify
        result = builder.reset()
        assert result is builder  # Returns self
        assert builder._source is None
        assert len(builder._dimensions) == 0
        assert builder._value == "rate"
        assert builder.name == "test"  # Name preserved

    def test_copy_builder(self):
        """Test copying builder configuration."""
        builder = TableBuilder("original")
        builder.from_source("test.csv")
        builder.with_data_dimension("age", "age")
        builder.with_value_column("mortality")

        # Create copy
        copy_builder = builder.copy()

        # Verify copy has same config
        assert copy_builder.name == "original"
        assert copy_builder._source == "test.csv"
        assert len(copy_builder._dimensions) == 1
        assert copy_builder._value == "mortality"

        # Verify they're independent
        copy_builder.with_data_dimension("duration", "dur")
        assert len(builder._dimensions) == 1
        assert len(copy_builder._dimensions) == 2


class TestTableBuilderWithComplexScenarios:
    """Test complex builder scenarios."""

    def test_mortality_table_builder(self):
        """Test building a complex mortality table."""
        df = pl.DataFrame(
            {
                "issue_age": [25, 30, 35],
                "1": [0.001, 0.002, 0.003],
                "2": [0.002, 0.003, 0.004],
                "Ultimate": [0.010, 0.015, 0.020],
            },
        )

        table = (
            TableBuilder("mortality_2015")
            .from_source(df)
            .with_data_dimension("age", "issue_age", rename_to="issue_age")
            .with_melt_dimension("duration", ["1", "2", "Ultimate"])
            .with_categorical_dimension("table_type", "mortality")
            .with_value_column("qx")
            .build()
        )

        assert isinstance(table, Table)
        assert len(table._dimensions) == 3
        assert "age" in table._dimensions
        assert "duration" in table._dimensions
        assert "table_type" in table._dimensions

    def test_interest_rate_curve_builder(self):
        """Test building an interest rate curve."""
        df = pl.DataFrame(
            {
                "term": [1, 5, 10, 20, 30],
                "rate": [0.01, 0.02, 0.025, 0.03, 0.032],
            },
        )

        table = (
            TableBuilder("treasury_curve")
            .from_source(df)
            .with_data_dimension("term", "term", dtype=pl.Int32)
            .with_computed_dimension("term_group", pl.col("term") // 5, alias="bucket")
            .with_value_column("rate")
            .build()
        )

        assert isinstance(table, Table)
        assert table._value == "rate"

    def test_builder_reuse_pattern(self):
        """Test reusing builder for multiple similar tables."""
        base_builder = (
            TableBuilder("template")
            .with_data_dimension("age", "age")
            .with_categorical_dimension("gender", "male")
            .with_value_column("rate")
        )

        # Create male table with unique name
        male_df = pl.DataFrame({"age": [25, 30], "rate": [0.01, 0.02]})
        male_builder = base_builder.copy()
        male_builder.name = "male_template"  # Unique name
        male_table = male_builder.from_source(male_df).build()

        # Create female table with different categorical value and unique name
        female_df = pl.DataFrame({"age": [25, 30], "rate": [0.008, 0.018]})
        female_builder = base_builder.copy()
        female_builder.name = "female_template"  # Unique name
        female_table = (
            female_builder.from_source(female_df)
            .with_categorical_dimension("gender", "female")  # Override
            .build()
        )

        # Verify both tables created successfully
        assert isinstance(male_table, Table)
        assert isinstance(female_table, Table)

        # Verify they have different gender values
        male_gender = male_table._dimensions["gender"]
        female_gender = female_table._dimensions["gender"]
        assert male_gender.value == "male"
        assert female_gender.value == "female"


class TestTableBuilderEdgeCases:
    """Test edge cases and error conditions."""

    def test_overriding_dimensions(self):
        """Test overriding dimensions with same name."""
        builder = TableBuilder("test")

        # Add initial dimension
        builder.with_data_dimension("age", "age1")
        assert builder._dimensions["age"].column == "age1"

        # Override with different config
        builder.with_data_dimension("age", "age2", rename_to="final_age")
        assert builder._dimensions["age"].column == "age2"
        assert builder._dimensions["age"].rename_to == "final_age"

    def test_pathlib_source(self):
        """Test using pathlib.Path as source."""
        builder = TableBuilder("test")
        path = Path("test.csv")

        result = builder.from_source(path)
        assert result._source == path
        assert isinstance(result._source, Path)

    def test_dataframe_source(self):
        """Test using DataFrame as source."""
        df = pl.DataFrame({"col": [1, 2, 3]})
        builder = TableBuilder("test")

        result = builder.from_source(df)
        assert result._source is df

    def test_empty_name_builder(self):
        """Test builder with empty name."""
        builder = TableBuilder("")
        assert builder.name == ""

        # Should still work for building
        df = pl.DataFrame({"age": [25], "rate": [0.01]})
        table = builder.from_source(df).with_data_dimension("age", "age").build()

        assert table._name == ""
