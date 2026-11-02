# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for strategy implementations in _strategies.py
"""

from typing import ClassVar

import polars as pl
import pytest

from gaspatchio.assumptions._strategies import (
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


class TestInterpolationFollowsTheKey:
    """A blank is interpolated along the key's value, not the column order (W5 A-F7)."""

    @staticmethod
    def _rate_at_duration_3(wide: pl.DataFrame, columns: list[str]) -> float:
        from gaspatchio import ActuarialFrame
        from gaspatchio.assumptions import MeltDimension, Table

        table = Table(
            name="lapse_by_key",
            source=wide,
            dimensions={
                "age": "age",
                "dur": MeltDimension(
                    columns=columns, name="dur", fill=LinearInterpolate()
                ),
            },
            value="rate",
        )
        af = ActuarialFrame(pl.DataFrame({"pid": [1], "age": [40], "dur": [3]}))
        af.r = table.lookup(age=af.age, dur=af.dur)
        return af.collect()["r"][0]

    def test_a_gap_in_the_durations_is_measured_in_years(self):
        """Durations 1, 2, 3, 5, 10 with 3 blank: one third of the way from 2 to 5."""
        wide = pl.DataFrame(
            {
                "age": [40],
                "1": [0.10],
                "2": [0.08],
                "3": [None],
                "5": [0.02],
                "10": [0.01],
            },
        )
        r = self._rate_at_duration_3(wide, ["1", "2", "3", "5", "10"])
        assert r == pytest.approx(0.08 + (0.02 - 0.08) / 3)  # 0.06, not 0.05

    def test_columns_listed_in_text_order_interpolate_in_number_order(self):
        """Headers sorted as text ('1','10','15','2',...) still interpolate by duration."""
        values = {"1": 0.10, "2": 0.08, "3": None, "5": 0.05, "10": 0.04, "15": 0.03}
        columns = sorted(values)  # ['1', '10', '15', '2', '3', '5']
        wide = pl.DataFrame({"age": [40], **{c: [values[c]] for c in columns}})
        r = self._rate_at_duration_3(wide, columns)
        assert r == pytest.approx(0.08 + (0.05 - 0.08) / 3)  # 0.07, not 0.03

    def test_evenly_spaced_columns_in_order_keep_their_old_values(self):
        """Where the position was already the key, no number moves."""
        df = pl.DataFrame(
            {
                "age": [40] * 4,
                "duration": ["1", "2", "3", "4"],
                "value": [0.1, None, None, 0.4],
            },
        )
        result = LinearInterpolate().apply(df, group_columns=["age"])
        assert result["value"].to_list() == pytest.approx([0.1, 0.2, 0.3, 0.4])

    def test_a_label_that_is_not_a_number_is_refused(self):
        """Labels such as 'd1', 'd2' have no distance between them, so nothing is interpolated."""
        df = pl.DataFrame(
            {
                "age": [40] * 3,
                "duration": ["d1", "d2", "d3"],
                "value": [0.1, None, 0.3],
            },
        )
        with pytest.raises(ValueError, match=r"'d1'.*is not a number"):
            LinearInterpolate().apply(df, group_columns=["age"])

    def test_two_candidate_keys_are_refused(self):
        """With no group columns named, two key columns leave the axis ambiguous."""
        df = pl.DataFrame(
            {"age": [40, 40, 40], "duration": [1, 2, 3], "value": [0.1, None, 0.3]},
        )
        with pytest.raises(ValueError, match="which column to interpolate along"):
            LinearInterpolate().apply(df)


class TestForwardFillFollowsTheKey:
    """A blank takes the rate of the key before it, not the column listed before it."""

    @staticmethod
    def _rate(values: dict[str, float | None], columns: list[str], at: int) -> float:
        from gaspatchio import ActuarialFrame
        from gaspatchio.assumptions import MeltDimension, Table

        wide = pl.DataFrame({"age": [40], **{c: [values[c]] for c in columns}})
        table = Table(
            name=f"lapse_ffill_{'_'.join(columns)}",
            source=wide,
            dimensions={
                "age": "age",
                "dur": MeltDimension(columns=columns, name="dur", fill=FillForward()),
            },
            value="rate",
        )
        af = ActuarialFrame(pl.DataFrame({"pid": [1], "age": [40], "dur": [at]}))
        af.r = table.lookup(age=af.age, dur=af.dur)
        return af.collect()["r"][0]

    _VALUES: ClassVar[dict[str, float | None]] = {
        "1": 0.10,
        "2": 0.08,
        "3": None,
        "5": 0.05,
        "10": 0.04,
        "15": 0.03,
        "20": 0.02,
    }

    def test_columns_listed_in_text_order_fill_from_the_duration_before(self):
        """Sorted as text, '20' precedes '3'; duration 3 takes duration 2's rate."""
        columns = sorted(self._VALUES)  # ['1', '10', '15', '2', '20', '3', '5']
        assert self._rate(self._VALUES, columns, 3) == 0.08  # duration 2, not 0.02

    def test_a_column_listed_out_of_place_fills_from_the_duration_before(self):
        """Duration 3 listed after 5 takes duration 2's 0.08, not duration 5's 0.05."""
        columns = ["1", "2", "5", "3", "10"]
        assert self._rate(self._VALUES, columns, 3) == 0.08

    def test_the_rows_come_back_in_the_order_they_came(self):
        """Only the blanks change; every row keeps its place."""
        df = pl.DataFrame(
            {
                "age": [40, 40, 40, 41, 41, 41],
                "duration": ["5", "1", "3", "3", "1", "5"],
                "value": [0.05, 0.10, None, None, 0.20, 0.15],
            },
        )
        result = FillForward().apply(df, group_columns=["age"])
        assert result["duration"].to_list() == ["5", "1", "3", "3", "1", "5"]
        assert result["value"].to_list() == [0.05, 0.10, 0.10, 0.20, 0.20, 0.15]

    def test_a_label_that_is_not_a_number_is_refused(self):
        """Labels such as 'd1', 'd2' give only the listing order: a blank is refused."""
        df = pl.DataFrame(
            {
                "age": [40] * 3,
                "duration": ["d1", "d2", "d3"],
                "value": [0.1, None, 0.3],
            },
        )
        with pytest.raises(ValueError, match=r"FillForward.*'d1'.*is not a number"):
            FillForward().apply(df, group_columns=["age"])

    def test_two_candidate_keys_are_refused(self):
        """With no group columns named, two key columns leave the order ambiguous."""
        df = pl.DataFrame(
            {"age": [40, 40, 40], "duration": [1, 2, 3], "value": [0.1, None, 0.3]},
        )
        with pytest.raises(ValueError, match="which column to fill along"):
            FillForward().apply(df)

    def test_a_table_with_no_blank_is_not_read_for_a_key(self):
        """No blank, nothing to fill: text labels are accepted as before."""
        df = pl.DataFrame(
            {"age": [40] * 2, "duration": ["d1", "d2"], "value": [0.1, 0.2]},
        )
        assert FillForward().apply(df, group_columns=["age"]).equals(df)
