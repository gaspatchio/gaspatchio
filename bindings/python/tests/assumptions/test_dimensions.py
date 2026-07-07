# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for dimension implementations in _dimensions.py
"""

import polars as pl
import pytest

from gaspatchio_core.assumptions._dimensions import (
    CategoricalDimension,
    ComputedDimension,
    DataDimension,
    Dimension,
    MeltDimension,
)
from gaspatchio_core.assumptions._strategies import (
    ExtendOverflow,
    FillConstant,
    FillForward,
    LinearInterpolate,
)


class TestDataDimension:
    """Test DataDimension implementation"""

    def test_basic_data_dimension(self):
        """Test basic data dimension without transformations"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="age")
        result = dimension.process(df)

        # Should be unchanged
        assert result.equals(df)

    def test_data_dimension_with_rename(self):
        """Test data dimension with column rename"""
        df = pl.DataFrame(
            {
                "issue_age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="issue_age", rename_to="age")
        result = dimension.process(df)

        # Should rename column
        assert "age" in result.columns
        assert "issue_age" not in result.columns
        assert result["age"].to_list() == [30, 31, 32]
        assert result["rate"].to_list() == [0.001, 0.002, 0.003]

    def test_data_dimension_with_dtype_conversion(self):
        """Test data dimension with dtype conversion"""
        df = pl.DataFrame(
            {
                "age": ["30", "31", "32"],  # String values
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="age", dtype=pl.Int32)
        result = dimension.process(df)

        # Should convert to integer
        assert result["age"].dtype == pl.Int32
        assert result["age"].to_list() == [30, 31, 32]

    def test_data_dimension_rename_and_convert(self):
        """Test data dimension with both rename and dtype conversion"""
        df = pl.DataFrame(
            {
                "issue_age": ["30.0", "31.0", "32.0"],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(
            column="issue_age",
            rename_to="age",
            dtype=pl.Int32,
        )
        result = dimension.process(df)

        assert "age" in result.columns
        assert "issue_age" not in result.columns
        assert result["age"].dtype == pl.Int32
        assert result["age"].to_list() == [30, 31, 32]

    def test_data_dimension_validation_missing_column(self):
        """Test validation error when column doesn't exist"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="missing_column")

        with pytest.raises(ValueError, match="Column 'missing_column' not found"):
            dimension.validate(df)

    def test_data_dimension_invalid_dtype_conversion(self):
        """Test error when dtype conversion fails"""
        df = pl.DataFrame(
            {
                "age": ["thirty", "thirty-one", "thirty-two"],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="age", dtype=pl.Int32)

        with pytest.raises(ValueError, match="Failed to convert column 'age'"):
            dimension.process(df)

    def test_data_dimension_no_rename_when_same(self):
        """Test that no rename occurs when rename_to equals column name"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="age", rename_to="age")
        result = dimension.process(df)

        # Should be unchanged
        assert result.equals(df)


class TestMeltDimension:
    """Test MeltDimension implementation"""

    def test_basic_melt_dimension(self):
        """Test basic melt operation without strategies"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "1": [0.001, 0.004, 0.007],
                "2": [0.002, 0.005, 0.008],
                "3": [0.003, 0.006, 0.009],
            },
        )

        dimension = MeltDimension(columns=["1", "2", "3"], name="duration")
        result = dimension.process(df)

        # Should have 9 rows (3 ages × 3 durations)
        assert len(result) == 9
        assert "duration" in result.columns
        assert "value" in result.columns
        assert set(result["duration"].unique().to_list()) == {"1", "2", "3"}
        assert set(result["age"].unique().to_list()) == {30, 31, 32}

    def test_melt_dimension_with_overflow(self):
        """Test melt with overflow strategy"""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, 0.003],
                "2": [0.002, 0.004],
                "Ultimate": [0.005, 0.006],
            },
        )

        overflow_strategy = ExtendOverflow(column="Ultimate", to_value=4)
        dimension = MeltDimension(
            columns=["1", "2", "Ultimate"],
            name="duration",
            overflow=overflow_strategy,
        )
        result = dimension.process(df)

        # Should have extended Ultimate to duration 3 and 4
        expected_durations = {"1", "2", "3", "4"}
        actual_durations = set(result["duration"].unique().to_list())
        assert actual_durations == expected_durations

        # Should have 8 rows (2 ages × 4 durations)
        assert len(result) == 8

    def test_melt_dimension_with_fill(self):
        """Test melt with fill strategy"""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, 0.003],
                "2": [None, 0.004],
                "3": [0.005, None],
            },
        )

        fill_strategy = FillConstant(value=0.0)
        dimension = MeltDimension(
            columns=["1", "2", "3"],
            name="duration",
            fill=fill_strategy,
        )
        result = dimension.process(df)

        # Should have no null values
        assert result["value"].null_count() == 0
        # Null values should be replaced with 0.0
        assert 0.0 in result["value"].to_list()

    def test_melt_dimension_fillforward_is_within_group(self):
        """FillForward must carry a group's OWN prior value, not a neighbour's.

        Regression for F11: the per-group fill fell back to a single GLOBAL
        forward-fill over the melted column, so age 31's null d1 was filled
        from age 30's d1 (0.11) instead of carrying age 31's own d0 (0.20).
        """
        wide = pl.DataFrame(
            {
                "age": [30, 31],
                "d0": [0.10, 0.20],
                "d1": [0.11, None],
                "d2": [0.12, None],
                "d3": [0.13, 0.23],
            },
        )
        md = MeltDimension(
            columns=["d0", "d1", "d2", "d3"],
            name="duration",
            fill=FillForward(),
        )
        res = md.process(wide)

        def val(age: int, dur: str) -> float:
            return res.filter(
                (pl.col("age") == age) & (pl.col("duration") == dur),
            )["value"][0]

        # Within-group ffill carries age 31's own d0 (0.20), NOT age 30's rates.
        assert val(31, "d1") == 0.20
        assert val(31, "d2") == 0.20
        # Age 30 is untouched.
        assert val(30, "d1") == 0.11

    def test_melt_dimension_interpolate_is_within_group(self):
        """LinearInterpolate must interpolate within each group only.

        Regression for F11: age 31 (own rates d0=0.20, d3=0.23) must give
        d1=0.21, d2=0.22 — interpolated between age 31's OWN endpoints — not
        0.115/0.125 (interpolations of age 30's neighbouring rates).
        """
        wide = pl.DataFrame(
            {
                "age": [30, 31],
                "d0": [0.10, 0.20],
                "d1": [0.11, None],
                "d2": [0.12, None],
                "d3": [0.13, 0.23],
            },
        )
        md = MeltDimension(
            columns=["d0", "d1", "d2", "d3"],
            name="duration",
            fill=LinearInterpolate(method="linear"),
        )
        res = md.process(wide)

        def val(age: int, dur: str) -> float:
            return res.filter(
                (pl.col("age") == age) & (pl.col("duration") == dur),
            )["value"][0]

        assert val(31, "d1") == pytest.approx(0.21)
        assert val(31, "d2") == pytest.approx(0.22)

    def test_melt_dimension_validation_missing_columns(self):
        """Test validation error when melt columns don't exist"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "1": [0.001, 0.004, 0.007],
                "2": [0.002, 0.005, 0.008],
            },
        )

        dimension = MeltDimension(columns=["1", "2", "3", "4"], name="duration")

        with pytest.raises(ValueError, match="Columns \\['3', '4'\\] not found"):
            dimension.validate(df)

    def test_melt_dimension_validation_name_conflict(self):
        """Test validation error when dimension name conflicts with existing column"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "duration": [10, 11, 12],  # Conflicts with dimension name
                "1": [0.001, 0.004, 0.007],
                "2": [0.002, 0.005, 0.008],
            },
        )

        dimension = MeltDimension(columns=["1", "2"], name="duration")

        with pytest.raises(ValueError, match="Dimension name 'duration' conflicts"):
            dimension.validate(df)

    def test_melt_dimension_name_conflict_allowed_when_included(self):
        """Test that name conflict is allowed when the conflicting column is included in melt"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "duration": [0.010, 0.011, 0.012],
                "1": [0.001, 0.004, 0.007],
                "2": [0.002, 0.005, 0.008],
            },
        )

        # This should work since "duration" is included in columns to melt
        dimension = MeltDimension(columns=["1", "2", "duration"], name="duration")
        result = dimension.process(df)

        # Should not raise an error
        assert "duration" in result.columns
        assert len(result) == 9  # 3 ages × 3 melted columns

    def test_melt_dimension_empty_dataframe(self):
        """Test melt dimension with empty DataFrame"""
        df = pl.DataFrame(schema={"age": pl.Int32, "1": pl.Float64, "2": pl.Float64})

        dimension = MeltDimension(columns=["1", "2"], name="duration")
        result = dimension.process(df)

        assert result.is_empty()
        assert "duration" in result.columns
        assert "value" in result.columns


class TestCategoricalDimension:
    """Test CategoricalDimension implementation"""

    def test_categorical_dimension_with_explicit_name(self):
        """Test categorical dimension with explicit name"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = CategoricalDimension(value="Male", name="gender")
        result = dimension.process(df)

        assert "gender" in result.columns
        assert result["gender"].to_list() == ["Male", "Male", "Male"]
        assert len(result) == 3

    def test_categorical_dimension_auto_name_string(self):
        """Test categorical dimension with auto-generated name from string value"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = CategoricalDimension(value="Non-Smoker")
        result = dimension.process(df)

        # Should auto-generate name
        assert dimension.name == "non_smoker"
        assert "non_smoker" in result.columns
        assert result["non_smoker"].to_list() == [
            "Non-Smoker",
            "Non-Smoker",
            "Non-Smoker",
        ]

    def test_categorical_dimension_auto_name_numeric(self):
        """Test categorical dimension with auto-generated name from numeric value"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = CategoricalDimension(value=2023)
        result = dimension.process(df)

        # Should auto-generate name
        assert dimension.name == "category_2023"
        assert "category_2023" in result.columns
        assert result["category_2023"].to_list() == [2023, 2023, 2023]

    def test_categorical_dimension_validation_name_conflict(self):
        """Test validation error when categorical name conflicts with existing column"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "gender": ["F", "M", "F"],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = CategoricalDimension(value="Male", name="gender")

        with pytest.raises(ValueError, match="Column 'gender' already exists"):
            dimension.validate(df)

    def test_categorical_dimension_various_value_types(self):
        """Test categorical dimension with various value types"""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "rate": [0.001, 0.002],
            },
        )

        # Test with different value types
        test_cases = [
            ("string_value", "product"),
            (42, "answer"),
            (3.14, "pi"),
            (True, "flag"),
        ]

        for value, name in test_cases:
            dimension = CategoricalDimension(value=value, name=name)
            result = dimension.process(df)

            assert name in result.columns
            assert result[name].to_list() == [value, value]


class TestComputedDimension:
    """Test ComputedDimension implementation"""

    def test_computed_dimension_basic(self):
        """Test basic computed dimension"""
        df = pl.DataFrame(
            {
                "birth_year": [1990, 1985, 1995],
                "current_year": [2023, 2023, 2023],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = ComputedDimension(
            expression=pl.col("current_year") - pl.col("birth_year"),
            name="age",
        )
        result = dimension.process(df)

        assert "age" in result.columns
        assert result["age"].to_list() == [33, 38, 28]

    def test_computed_dimension_complex_expression(self):
        """Test computed dimension with complex expression"""
        df = pl.DataFrame(
            {
                "base_rate": [0.001, 0.002, 0.003],
                "adjustment": [1.1, 1.2, 1.3],
                "duration": [1, 2, 3],
            },
        )

        dimension = ComputedDimension(
            expression=(
                pl.col("base_rate") * pl.col("adjustment") * pl.col("duration")
            ),
            name="adjusted_rate",
        )
        result = dimension.process(df)

        assert "adjusted_rate" in result.columns
        expected = [0.001 * 1.1 * 1, 0.002 * 1.2 * 2, 0.003 * 1.3 * 3]
        actual = result["adjusted_rate"].to_list()
        for i in range(len(expected)):
            assert abs(actual[i] - expected[i]) < 1e-10

    def test_computed_dimension_overwrite_existing(self):
        """Test computed dimension that overwrites existing column"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = ComputedDimension(
            expression=pl.col("age") + 10,
            name="age",  # Overwrites existing column
        )
        result = dimension.process(df)

        # Should overwrite the age column
        assert result["age"].to_list() == [40, 41, 42]

    def test_computed_dimension_validation_invalid_expression(self):
        """Test validation error when expression is invalid"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = ComputedDimension(
            expression=pl.col("nonexistent_column"),
            name="computed",
        )

        with pytest.raises(ValueError, match="Invalid expression"):
            dimension.validate(df)

    def test_computed_dimension_with_string_operations(self):
        """Test computed dimension with string operations"""
        df = pl.DataFrame(
            {
                "first_name": ["John", "Jane", "Bob"],
                "last_name": ["Doe", "Smith", "Johnson"],
            },
        )

        dimension = ComputedDimension(
            expression=pl.col("first_name") + " " + pl.col("last_name"),
            name="full_name",
        )
        result = dimension.process(df)

        assert "full_name" in result.columns
        assert result["full_name"].to_list() == [
            "John Doe",
            "Jane Smith",
            "Bob Johnson",
        ]


class TestDimensionAbstraction:
    """Test dimension abstract base class"""

    def test_dimension_abc(self):
        """Test that Dimension is abstract and cannot be instantiated"""
        with pytest.raises(TypeError):
            Dimension()


class TestDimensionEdgeCases:
    """Test edge cases and error conditions for dimensions"""

    def test_data_dimension_empty_dataframe(self):
        """Test data dimension with empty DataFrame"""
        df = pl.DataFrame(schema={"age": pl.Int32, "rate": pl.Float64})

        dimension = DataDimension(column="age", rename_to="new_age")
        result = dimension.process(df)

        assert result.is_empty()
        assert "new_age" in result.columns
        assert "age" not in result.columns

    def test_categorical_dimension_empty_dataframe(self):
        """Test categorical dimension with empty DataFrame"""
        df = pl.DataFrame(schema={"age": pl.Int32, "rate": pl.Float64})

        dimension = CategoricalDimension(value="Test", name="category")
        result = dimension.process(df)

        assert result.is_empty()
        assert "category" in result.columns

    def test_computed_dimension_empty_dataframe(self):
        """Test computed dimension with empty DataFrame"""
        df = pl.DataFrame(schema={"age": pl.Int32, "rate": pl.Float64})

        dimension = ComputedDimension(
            expression=pl.col("age") * 2,
            name="double_age",
        )
        result = dimension.process(df)

        assert result.is_empty()
        assert "double_age" in result.columns

    def test_melt_dimension_with_overflow_and_fill(self):
        """Test melt dimension with both overflow and fill strategies"""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, None],
                "Ultimate": [0.002, 0.004],
            },
        )

        overflow_strategy = ExtendOverflow(column="Ultimate", to_value=3)
        fill_strategy = LinearInterpolate(method="linear")

        dimension = MeltDimension(
            columns=["1", "Ultimate"],
            name="duration",
            overflow=overflow_strategy,
            fill=fill_strategy,
        )
        result = dimension.process(df)

        # Should have extended Ultimate and filled nulls
        expected_durations = {"1", "2", "3"}
        actual_durations = set(result["duration"].unique().to_list())
        assert actual_durations == expected_durations

        # Fill is now applied per-group (F11). Age 30 has all its own rates, so
        # it is fully filled.
        age30 = result.filter(pl.col("age") == 30)
        assert age30["value"].null_count() == 0
        # Age 31's only null is its LEADING duration "1"; within its own group
        # there is no left anchor to interpolate from, so it correctly stays
        # null rather than bleeding age 30's 0.001 (the old global fallback
        # produced 0.0015 here by interpolating across groups).
        age31_d1 = result.filter(
            (pl.col("age") == 31) & (pl.col("duration") == "1"),
        )["value"][0]
        assert age31_d1 is None

    def test_dimensions_preserve_other_columns(self):
        """Test that dimensions preserve other columns in the DataFrame"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "gender": ["M", "F", "M"],
                "product": ["Term", "Whole", "Term"],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        dimension = DataDimension(column="age", rename_to="issue_age")
        result = dimension.process(df)

        # All other columns should be preserved
        assert "gender" in result.columns
        assert "product" in result.columns
        assert "rate" in result.columns
        assert result["gender"].to_list() == ["M", "F", "M"]
        assert result["product"].to_list() == ["Term", "Whole", "Term"]

    def test_categorical_dimension_name_cleanup(self):
        """Test that categorical dimension names are properly cleaned up"""
        test_cases = [
            ("Product Name", "product_name"),
            ("Non-Smoker", "non_smoker"),
            ("MALE", "male"),
            ("2023-Model", "2023_model"),
            ("  Spaced  ", "spaced"),
        ]

        df = pl.DataFrame({"col": [1]})

        for input_value, expected_name in test_cases:
            dimension = CategoricalDimension(value=input_value)
            # The __post_init__ should clean up the name
            assert dimension.name == expected_name


class TestDimensionIntegration:
    """Test integration between multiple dimensions"""

    def test_multiple_dimensions_sequential(self):
        """Test applying multiple dimensions in sequence"""
        df = pl.DataFrame(
            {
                "issue_age": [30, 31],
                "1": [0.001, 0.003],
                "2": [0.002, 0.004],
            },
        )

        # Apply data dimension first
        data_dim = DataDimension(column="issue_age", rename_to="age")
        result1 = data_dim.process(df)

        # Then apply melt dimension
        melt_dim = MeltDimension(columns=["1", "2"], name="duration")
        result2 = melt_dim.process(result1)

        # Finally add categorical dimension
        cat_dim = CategoricalDimension(value="2023", name="year")
        final_result = cat_dim.process(result2)

        # Check final structure
        assert "age" in final_result.columns
        assert "duration" in final_result.columns
        assert "year" in final_result.columns
        assert "value" in final_result.columns
        assert len(final_result) == 4  # 2 ages × 2 durations
        assert set(final_result["year"].unique().to_list()) == {"2023"}
