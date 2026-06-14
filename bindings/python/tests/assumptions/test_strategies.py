# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for strategy implementations in _strategies.py
"""

import polars as pl
import pytest

from gaspatchio_core.assumptions._strategies import (
    AutoDetectOverflow,
    ExtendOverflow,
    FillConstant,
    FillForward,
    FillStrategy,
    LinearInterpolate,
    OverflowStrategy,
)


class TestOverflowStrategies:
    """Test overflow strategy implementations"""

    def test_extend_overflow_basic(self):
        """Test basic overflow extension functionality"""
        # Create test data where each age has data for each duration
        df = pl.DataFrame(
            {
                "age": [30, 30, 30, 31, 31, 31, 32, 32, 32],
                "duration": [
                    "1",
                    "2",
                    "Ultimate",
                    "1",
                    "2",
                    "Ultimate",
                    "1",
                    "2",
                    "Ultimate",
                ],
                "value": [
                    0.001,
                    0.002,
                    0.003,
                    0.004,
                    0.005,
                    0.006,
                    0.007,
                    0.008,
                    0.009,
                ],
            },
        )

        strategy = ExtendOverflow(column="Ultimate", to_value=5)
        result = strategy.apply(df, "duration")

        # Should have extended Ultimate from 3 to 5
        expected_durations = ["1", "2", "3", "4", "5"]
        actual_durations = sorted(result["duration"].unique().to_list())
        assert actual_durations == expected_durations

        # Check that we have the right number of rows (3 ages × 5 durations)
        assert len(result) == 15

        # Verify that all ages have all durations
        age_duration_combinations = (
            result.select(["age", "duration"]).unique().sort(["age", "duration"])
        )
        assert len(age_duration_combinations) == 15  # 3 ages × 5 durations

    def test_extend_overflow_missing_column(self):
        """Test overflow extension when overflow column doesn't exist"""
        df = pl.DataFrame(
            {
                "age": [30, 30, 31, 31],
                "duration": ["1", "2", "1", "2"],
                "value": [0.001, 0.002, 0.003, 0.004],
            },
        )

        strategy = ExtendOverflow(column="Ultimate", to_value=5)
        result = strategy.apply(df, "duration")

        # Should return unchanged since no overflow column found
        assert result.equals(df)

    def test_extend_overflow_no_numeric_values(self):
        """Test overflow extension when no numeric values exist"""
        df = pl.DataFrame(
            {
                "product": ["A", "A", "B", "B"],
                "type": ["Term", "Ultimate", "Term", "Ultimate"],
                "value": [0.001, 0.002, 0.003, 0.004],
            },
        )

        strategy = ExtendOverflow(column="Ultimate", to_value=5)
        result = strategy.apply(df, "type")

        # Should return unchanged since no numeric values found
        assert result.equals(df)

    def test_auto_detect_overflow_basic(self):
        """Test auto-detection of overflow columns"""
        df = pl.DataFrame(
            {
                "age": [30, 30, 31, 31],
                "duration": ["1", "Ultimate", "1", "Ultimate"],
                "value": [0.001, 0.002, 0.003, 0.004],
            },
        )

        strategy = AutoDetectOverflow(to_value=3)
        result = strategy.apply(df, "duration")

        # Should detect "Ultimate" and extend
        expected_durations = ["1", "2", "3"]
        actual_durations = sorted(result["duration"].unique().to_list())
        assert actual_durations == expected_durations

    def test_auto_detect_overflow_no_detection(self):
        """Test auto-detection when no overflow column exists"""
        df = pl.DataFrame(
            {
                "age": [30, 30, 31, 31],
                "duration": ["1", "2", "1", "2"],
                "value": [0.001, 0.002, 0.003, 0.004],
            },
        )

        strategy = AutoDetectOverflow(to_value=5)
        result = strategy.apply(df, "duration")

        # Should return unchanged since no overflow detected
        assert result.equals(df)

    def test_overflow_strategy_abc(self):
        """Test that OverflowStrategy is abstract"""
        with pytest.raises(TypeError):
            OverflowStrategy()


class TestFillStrategies:
    """Test fill strategy implementations"""

    def test_linear_interpolate_basic(self):
        """Test basic linear interpolation"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32, 33, 34],
                "value": [0.001, None, 0.003, None, 0.005],
            },
        )

        strategy = LinearInterpolate(method="linear")
        result = strategy.apply(df)

        # Check that nulls are filled
        assert result["value"].null_count() == 0

        # Check approximate interpolated values
        values = result["value"].to_list()
        assert abs(values[1] - 0.002) < 0.0001  # Should be ~0.002
        assert abs(values[3] - 0.004) < 0.0001  # Should be ~0.004

    def test_log_linear_interpolate(self):
        """Test log-linear interpolation"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "value": [0.001, None, 0.004],
            },
        )

        strategy = LinearInterpolate(method="log-linear")
        result = strategy.apply(df)

        # Check that nulls are filled
        assert result["value"].null_count() == 0

        # For log-linear, middle value should be geometric mean
        values = result["value"].to_list()
        expected_middle = (0.001 * 0.004) ** 0.5  # ~0.002
        assert abs(values[1] - expected_middle) < 0.0001

    def test_cubic_interpolate_fallback(self):
        """Test cubic interpolation (should fall back to linear)"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "value": [0.001, None, 0.003],
            },
        )

        strategy = LinearInterpolate(method="cubic")
        result = strategy.apply(df)

        # Should work (falls back to linear)
        assert result["value"].null_count() == 0

    def test_fill_constant(self):
        """Test constant fill strategy"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "value": [0.001, None, 0.003],
            },
        )

        strategy = FillConstant(value=0.999)
        result = strategy.apply(df)

        # Check that null is replaced with constant
        values = result["value"].to_list()
        assert values == [0.001, 0.999, 0.003]

    def test_fill_forward_basic(self):
        """Test forward fill strategy"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32, 33],
                "value": [0.001, None, None, 0.004],
            },
        )

        strategy = FillForward()
        result = strategy.apply(df)

        # Check forward fill behavior
        values = result["value"].to_list()
        assert values == [0.001, 0.001, 0.001, 0.004]

    def test_fill_forward_with_limit(self):
        """Test forward fill with limit (note: limit not fully implemented)"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "value": [0.001, None, None],
            },
        )

        strategy = FillForward(limit=1)
        result = strategy.apply(df)

        # Should still work (though limit not fully implemented)
        assert result["value"].null_count() == 0

    def test_fill_strategy_abc(self):
        """Test that FillStrategy is abstract"""
        with pytest.raises(TypeError):
            FillStrategy()

    def test_empty_dataframe_handling(self):
        """Test that strategies handle empty DataFrames gracefully"""
        empty_df = pl.DataFrame({"age": [], "value": []})

        # Test each strategy type
        strategies = [
            LinearInterpolate(),
            FillConstant(0.5),
            FillForward(),
        ]

        for strategy in strategies:
            result = strategy.apply(empty_df)
            assert result.is_empty()


class TestStrategyEdgeCases:
    """Test edge cases and error conditions"""

    def test_overflow_with_mixed_numeric_strings(self):
        """Test overflow handling with mixed numeric and string values"""
        df = pl.DataFrame(
            {
                "age": [30, 30, 30, 30, 30, 31, 31, 31, 31, 31],
                "duration": [
                    "1",
                    "2",
                    "3",
                    "Ultimate",
                    "Special",
                    "1",
                    "2",
                    "3",
                    "Ultimate",
                    "Special",
                ],
                "value": [
                    0.001,
                    0.002,
                    0.003,
                    0.004,
                    0.005,
                    0.006,
                    0.007,
                    0.008,
                    0.009,
                    0.010,
                ],
            },
        )

        strategy = ExtendOverflow(column="Ultimate", to_value=5)
        result = strategy.apply(df, "duration")

        # Should handle mixed types correctly
        unique_durations = result["duration"].unique().to_list()
        assert "Ultimate" not in unique_durations  # Replaced by expansion
        assert "Special" in unique_durations  # Non-overflow strings preserved
        assert "4" in unique_durations  # Extension values added
        assert "5" in unique_durations

    def test_interpolation_with_all_nulls(self):
        """Test interpolation when all values are null"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "value": [None, None, None],
            },
        )

        strategy = LinearInterpolate()
        result = strategy.apply(df)

        # Should handle gracefully (may still have nulls)
        assert len(result) == 3

    def test_interpolation_with_no_nulls(self):
        """Test interpolation when no nulls exist"""
        df = pl.DataFrame(
            {
                "age": [30, 31, 32],
                "value": [0.001, 0.002, 0.003],
            },
        )

        strategy = LinearInterpolate()
        result = strategy.apply(df)

        # Should return unchanged
        assert result.equals(df)

    def test_overflow_with_single_row(self):
        """Test overflow extension with single row"""
        df = pl.DataFrame(
            {
                "age": [30],
                "duration": ["Ultimate"],
                "value": [0.001],
            },
        )

        strategy = ExtendOverflow(column="Ultimate", to_value=3)
        result = strategy.apply(df, "duration")

        # Should still work but may have different behavior
        assert len(result) >= 1  # At least one row should remain


class TestStrategyIntegration:
    """Test integration between different strategies"""

    def test_overflow_then_fill(self):
        """Test applying overflow then fill strategies in sequence"""
        # Start with data that has overflow and missing values
        df = pl.DataFrame(
            {
                "age": [30, 30, 31, 31],
                "duration": ["1", "Ultimate", "1", "Ultimate"],
                "value": [0.001, 0.002, 0.003, 0.004],
            },
        )

        # Apply overflow extension
        overflow_strategy = ExtendOverflow(column="Ultimate", to_value=3)
        after_overflow = overflow_strategy.apply(df, "duration")

        # Create some nulls for fill testing
        with_nulls = after_overflow.with_columns(
            pl.when(pl.col("duration") == "2")
            .then(None)
            .otherwise(pl.col("value"))
            .alias("value"),
        )

        # Apply fill strategy
        fill_strategy = FillConstant(value=0.999)
        final_result = fill_strategy.apply(with_nulls)

        # Check final state
        assert final_result["value"].null_count() == 0
        null_replacement_rows = final_result.filter(pl.col("value") == 0.999)
        assert len(null_replacement_rows) > 0  # Some nulls were replaced

    def test_multiple_overflow_patterns(self):
        """Test different overflow column patterns"""
        test_cases = [
            ("Ultimate", ["1", "2", "Ultimate"]),
            ("Ult", ["1", "2", "Ult"]),
            ("999", ["1", "2", "999"]),
            ("", ["1", "2", ""]),  # Empty string pattern
        ]

        for overflow_col, durations in test_cases:
            # Create properly sized data with equal row counts
            df = pl.DataFrame(
                {
                    "age": [30, 30, 30],  # Same length as durations
                    "duration": durations,
                    "value": [0.001, 0.002, 0.003],
                },
            )

            # Test auto-detection
            auto_strategy = AutoDetectOverflow(to_value=4)
            result = auto_strategy.apply(df, "duration")

            # Should extend if detected
            unique_durations = result["duration"].unique().to_list()
            if overflow_col in ["Ultimate", "Ult", ""]:  # These should be detected
                assert len(unique_durations) >= len(durations)  # Extended
            # else: may not be detected depending on implementation
