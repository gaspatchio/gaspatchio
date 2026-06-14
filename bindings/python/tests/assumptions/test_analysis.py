# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the enhanced analysis module with analyze_table function.
"""

import polars as pl

from gaspatchio_core.assumptions._analysis import (
    DimensionInfo,
    InterpolationHint,
    TableSchema,
    _analyze_numeric_pattern,
    _is_likely_id_column,
    analyze_table,
)


class TestDimensionInfo:
    """Test DimensionInfo dataclass"""

    def test_dimension_info_creation(self):
        """Test basic DimensionInfo creation"""
        dim = DimensionInfo(
            name="age",
            dtype="Int64",
            unique_count=10,
            sample_values=[30, 31, 32, 33, 34],
            suggested_type="key",
            numeric_pattern="30-39",
        )

        assert dim.name == "age"
        assert dim.dtype == "Int64"
        assert dim.unique_count == 10
        assert dim.sample_values == [30, 31, 32, 33, 34]
        assert dim.suggested_type == "key"
        assert dim.numeric_pattern == "30-39"


class TestInterpolationHint:
    """Test InterpolationHint dataclass"""

    def test_interpolation_hint_creation(self):
        """Test basic InterpolationHint creation"""
        hint = InterpolationHint(
            dimension="age",
            detected_values=[30, 32, 35],
            missing_values=[31, 33, 34],
            suggested_method="linear",
        )

        assert hint.dimension == "age"
        assert hint.detected_values == [30, 32, 35]
        assert hint.missing_values == [31, 33, 34]
        assert hint.suggested_method == "linear"


class TestTableSchema:
    """Test TableSchema dataclass and methods"""

    def test_curve_table_config_generation(self):
        """Test code generation for curve tables"""
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key"),
            DimensionInfo("rate", "Float64", 10, [0.001, 0.002], "key"),
        ]

        schema = TableSchema(
            data_dimensions=dimensions,
            value_columns=["rate"],
            format="curve",
        )

        config = schema.suggest_table_config()

        assert "gs.Table(" in config
        assert "curve table" in config
        assert "'age': gs.DataDimension('age')" in config
        assert 'value="rate"' in config
        # Should not include the value column in dimensions
        assert "'rate': gs.DataDimension('rate')" not in config

    def test_wide_table_config_generation(self):
        """Test code generation for wide tables"""
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key"),
            DimensionInfo("1", "Float64", 10, [0.001, 0.002], "melt"),
            DimensionInfo("2", "Float64", 10, [0.002, 0.003], "melt"),
        ]

        schema = TableSchema(
            data_dimensions=dimensions,
            value_columns=["value"],
            format="wide",
            overflow_candidate="Ultimate",
        )

        config = schema.suggest_table_config()

        assert "gs.Table(" in config
        assert "wide table" in config
        assert "'age': gs.DataDimension('age')" in config
        assert "gs.MeltDimension(['1', '2'])" in config
        assert "gs.ExtendOverflow('Ultimate'" in config

    def test_to_dict_serialization(self):
        """Test dictionary serialization"""
        dimensions = [
            DimensionInfo("age", "Int64", 10, [30, 31], "key", "30-39"),
        ]

        hint = InterpolationHint("age", [30, 32], [31], "linear")

        schema = TableSchema(
            data_dimensions=dimensions,
            value_columns=["rate"],
            format="curve",
            overflow_candidate=None,
            interpolation_opportunities=[hint],
            row_count=100,
        )

        result = schema.to_dict()

        assert result["format"] == "curve"
        assert result["row_count"] == 100
        assert len(result["data_dimensions"]) == 1
        assert result["data_dimensions"][0]["name"] == "age"
        assert result["data_dimensions"][0]["numeric_pattern"] == "30-39"
        assert len(result["interpolation_opportunities"]) == 1
        assert result["interpolation_opportunities"][0]["dimension"] == "age"


class TestAnalyzeTable:
    """Test the main analyze_table function"""

    def test_curve_table_analysis(self):
        """Test analysis of a simple curve table"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32, 33, 34],
                "rate": [0.001, 0.002, 0.003, 0.004, 0.005],
            },
        )

        schema = analyze_table(df)

        assert schema.format == "curve"
        assert schema.row_count == 5
        assert len(schema.data_dimensions) == 2
        assert schema.value_columns == ["rate"]

        # Check dimension analysis
        age_dim = next(d for d in schema.data_dimensions if d.name == "age")
        assert age_dim.suggested_type == "key"
        assert age_dim.unique_count == 5

        rate_dim = next(d for d in schema.data_dimensions if d.name == "rate")
        # Rate column should be detected as value column in curve table
        assert rate_dim.suggested_type == "value"

    def test_wide_table_analysis(self):
        """Test analysis of a wide table"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "1": [0.001, 0.002, 0.003],
                "2": [0.002, 0.003, 0.004],
                "3": [0.003, 0.004, 0.005],
                "Ultimate": [0.004, 0.005, 0.006],
            },
        )

        schema = analyze_table(df, detect_overflow=True)

        assert schema.format == "wide"
        assert schema.row_count == 3
        assert len(schema.data_dimensions) == 5
        assert schema.value_columns == [
            "value",
        ]  # Wide tables use "value" after melting

        # Check overflow detection
        assert schema.overflow_candidate == "Ultimate"

        # Check dimension analysis
        age_dim = next(d for d in schema.data_dimensions if d.name == "age")
        assert age_dim.suggested_type == "key"

        # Duration columns should be marked as melt type
        duration_dims = [
            d for d in schema.data_dimensions if d.name in ["1", "2", "3", "Ultimate"]
        ]
        for dim in duration_dims:
            assert dim.suggested_type == "melt"

    def test_overflow_detection_disabled(self):
        """Test that overflow detection can be disabled"""
        df = pl.DataFrame(
            {
                "age": [30, 31],
                "1": [0.001, 0.002],
                "Ultimate": [0.004, 0.005],
            },
        )

        schema = analyze_table(df, detect_overflow=False)

        assert schema.overflow_candidate is None

    def test_interpolation_detection(self):
        """Test interpolation opportunity detection"""
        df = pl.DataFrame(
            {
                "age": [30, 32, 35, 40],  # Gaps at 31, 33, 34, 36-39
                "rate": [0.001, 0.002, 0.003, 0.004],
            },
        )

        schema = analyze_table(df, detect_interpolation=True)

        # Should detect interpolation opportunities
        assert len(schema.interpolation_opportunities) > 0

        age_hint = next(
            (h for h in schema.interpolation_opportunities if h.dimension == "age"),
            None,
        )
        if age_hint:
            assert age_hint.suggested_method in ["linear", "log-linear", "cubic"]

    def test_interpolation_detection_disabled(self):
        """Test that interpolation detection can be disabled"""
        df = pl.DataFrame(
            {
                "age": [30, 32, 35],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        schema = analyze_table(df, detect_interpolation=False)

        assert len(schema.interpolation_opportunities) == 0

    def test_sampling_for_large_data(self):
        """Test that large datasets are sampled"""
        # Create large dataset
        large_df = pl.DataFrame(
            {
                "age": list(range(30, 2030)),  # 2000 rows
                "rate": [0.001 + i * 0.0001 for i in range(2000)],
            },
        )

        schema = analyze_table(large_df, sample_rows=100)

        # Should still analyze correctly despite sampling
        assert schema.format == "curve"
        assert schema.row_count == 100  # Sampled size
        assert len(schema.data_dimensions) == 2

    def test_mixed_data_types(self):
        """Test analysis with mixed data types"""
        df = pl.DataFrame(
            {
                "product": ["Term", "WL", "UL"],
                "sex": ["M", "F", "M"],
                "age": [30, 31, 32],
                "rate": [0.001, 0.002, 0.003],
            },
        )

        schema = analyze_table(df)

        assert schema.format == "curve"
        assert len(schema.data_dimensions) == 4

        # Check that string columns are detected as keys
        product_dim = next(d for d in schema.data_dimensions if d.name == "product")
        assert product_dim.suggested_type == "key"
        assert "String" in product_dim.dtype

        sex_dim = next(d for d in schema.data_dimensions if d.name == "sex")
        assert sex_dim.suggested_type == "key"


class TestUtilityFunctions:
    """Test utility functions"""

    def test_is_likely_id_column(self):
        """Test ID column detection"""
        assert _is_likely_id_column("age") == True
        assert _is_likely_id_column("Age") == True
        assert _is_likely_id_column("duration") == True
        assert _is_likely_id_column("product_code") == True
        assert _is_likely_id_column("rate") == False
        assert _is_likely_id_column("value") == False
        assert _is_likely_id_column("qx") == False

    def test_analyze_numeric_pattern(self):
        """Test numeric pattern analysis"""
        # Sequential pattern
        sequential = pl.Series([1, 2, 3, 4, 5])
        pattern = _analyze_numeric_pattern(sequential)
        assert pattern == "1-5"

        # Continuous data
        continuous = pl.Series([1.1, 1.15, 1.2, 1.8, 2.3])
        pattern = _analyze_numeric_pattern(continuous)
        assert pattern == "continuous"

        # Empty series
        empty = pl.Series([], dtype=pl.Int64)
        pattern = _analyze_numeric_pattern(empty)
        assert pattern is None


class TestErrorCases:
    """Test error handling and edge cases"""

    def test_empty_dataframe(self):
        """Test analysis of empty DataFrame"""
        df = pl.DataFrame({"age": [], "rate": []})

        schema = analyze_table(df)

        assert schema.row_count == 0
        assert len(schema.data_dimensions) == 2
        assert schema.format in ["curve", "wide"]  # Should handle gracefully

    def test_single_column_dataframe(self):
        """Test analysis of single column DataFrame"""
        df = pl.DataFrame({"rate": [0.001, 0.002, 0.003]})

        schema = analyze_table(df)

        assert schema.row_count == 3
        assert len(schema.data_dimensions) == 1
        assert schema.format == "curve"
        assert schema.value_columns == ["rate"]

    def test_all_string_columns(self):
        """Test analysis with only string columns"""
        df = pl.DataFrame(
            {
                "product": ["Term", "WL"],
                "description": ["Term Life", "Whole Life"],
            },
        )

        schema = analyze_table(df)

        assert schema.row_count == 2
        assert len(schema.data_dimensions) == 2
        # Should default to first column as value
        assert len(schema.value_columns) == 1
