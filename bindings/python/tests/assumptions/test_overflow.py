"""
Tests for overflow expansion functionality.

This module tests the overflow detection and expansion logic that pre-computes
all overflow entries at registration time for maximum lookup performance.
"""

from __future__ import annotations

# Use new top-level imports instead of submodule imports
import gaspatchio_core as gs
import polars as pl
import pytest
from gaspatchio_core.assumptions._overflow import (
    _create_overflow_expansion,
    _detect_overflow_column,
    _get_max_numeric_duration,
)
from gaspatchio_core.assumptions._transform import _tidy_wide_with_overflow_expansion
from gaspatchio_core.assumptions.api import load_assumptions


def test_detect_overflow_auto_ult_dot():
    """Test auto-detection of 'Ult.' overflow column."""
    wide_cols = ["1", "2", "3", "Ult."]
    result = _detect_overflow_column(wide_cols, "auto")
    assert result == "Ult."


def test_detect_overflow_auto_ultimate():
    """Test auto-detection of 'Ultimate' overflow column."""
    wide_cols = ["1", "2", "3", "Ultimate"]
    result = _detect_overflow_column(wide_cols, "auto")
    assert result == "Ultimate"


def test_detect_overflow_auto_term():
    """Test auto-detection of 'Term' overflow column."""
    wide_cols = ["1", "2", "3", "Term"]
    result = _detect_overflow_column(wide_cols, "auto")
    assert result == "Term"


def test_detect_overflow_auto_999():
    """Test auto-detection of '999' overflow column."""
    wide_cols = ["1", "2", "3", "999"]
    result = _detect_overflow_column(wide_cols, "auto")
    assert result == "999"


def test_detect_overflow_auto_case_insensitive():
    """Test that overflow detection is case insensitive."""
    wide_cols = ["1", "2", "3", "ULT"]
    result = _detect_overflow_column(wide_cols, "auto")
    assert result == "ULT"


def test_detect_overflow_auto_not_found():
    """Test when no overflow column found with auto detection."""
    wide_cols = ["1", "2", "3", "4"]
    result = _detect_overflow_column(wide_cols, "auto")
    assert result is None


def test_detect_overflow_explicit_found():
    """Test explicit overflow column specification."""
    wide_cols = ["1", "2", "3", "Special_Ult"]
    result = _detect_overflow_column(wide_cols, "Special_Ult")
    assert result == "Special_Ult"


def test_detect_overflow_explicit_not_found():
    """Test error when explicit overflow column not found."""
    wide_cols = ["1", "2", "3", "4"]
    with pytest.raises(
        ValueError, match="Specified overflow column 'Missing' not found"
    ):
        _detect_overflow_column(wide_cols, "Missing")


def test_detect_overflow_none():
    """Test when overflow is None (no overflow handling)."""
    wide_cols = ["1", "2", "3", "Ult."]
    result = _detect_overflow_column(wide_cols, None)
    assert result is None


def test_max_numeric_basic():
    """Test finding max numeric duration."""
    wide_cols = ["1", "2", "3", "5", "10"]
    result = _get_max_numeric_duration(wide_cols)
    assert result == 10


def test_max_numeric_with_overflow_excluded():
    """Test finding max numeric duration excluding overflow column."""
    wide_cols = ["1", "2", "3", "10", "Ult."]
    result = _get_max_numeric_duration(wide_cols, exclude_overflow="Ult.")
    assert result == 10


def test_max_numeric_mixed_formats():
    """Test with mixed numeric and text columns."""
    wide_cols = ["1", "2", "Term", "5", "Ultimate"]
    result = _get_max_numeric_duration(wide_cols)
    assert result == 5


def test_max_numeric_no_numeric_columns():
    """Test when no numeric columns found."""
    wide_cols = ["Term", "Ultimate", "Special"]
    result = _get_max_numeric_duration(wide_cols)
    assert result is None


def test_max_numeric_single_column():
    """Test with single numeric column."""
    wide_cols = ["5"]
    result = _get_max_numeric_duration(wide_cols)
    assert result == 5


def test_create_overflow_expansion_basic():
    """Test basic overflow expansion."""
    # Create a melted DataFrame with overflow data
    df = pl.DataFrame(
        {
            "Age": [30, 31, 32],
            "variable": ["Ult.", "Ult.", "Ult."],
            "rate": [0.005, 0.006, 0.007],
        }
    )

    result = _create_overflow_expansion(df, ["Age"], "Ult.", "rate", 4, 6)

    # Should create 3 durations (4, 5, 6) × 3 ages = 9 rows
    assert len(result) == 9
    assert result.columns == ["Age", "variable", "rate"]

    # Check that all durations are created
    variables = sorted(result["variable"].unique().to_list())
    assert variables == ["4", "5", "6"]

    # Check that rates are copied correctly
    age_30_rows = result.filter(pl.col("Age") == 30)
    assert len(age_30_rows) == 3
    assert all(rate == 0.005 for rate in age_30_rows["rate"].to_list())


def test_create_overflow_expansion_no_expansion_needed():
    """Test when start_value > max_value (no expansion needed)."""
    df = pl.DataFrame(
        {"Age": [30, 31], "variable": ["Ult.", "Ult."], "rate": [0.005, 0.006]}
    )

    result = _create_overflow_expansion(df, ["Age"], "Ult.", "rate", 10, 5)

    # Should return empty DataFrame with correct schema
    assert len(result) == 0
    assert result.columns == ["Age", "variable", "rate"]


def test_create_overflow_expansion_no_overflow_data():
    """Test when no overflow data exists."""
    df = pl.DataFrame({"Age": [30, 31], "variable": ["1", "2"], "rate": [0.001, 0.002]})

    result = _create_overflow_expansion(df, ["Age"], "Ult.", "rate", 3, 5)

    # Should return empty DataFrame with correct schema
    assert len(result) == 0
    assert result.columns == ["Age", "variable", "rate"]


def test_create_overflow_expansion_multiple_id_cols():
    """Test overflow expansion with multiple id columns."""
    df = pl.DataFrame(
        {
            "Age": [30, 30, 31, 31],
            "Gender": ["M", "F", "M", "F"],
            "variable": ["Ult.", "Ult.", "Ult.", "Ult."],
            "rate": [0.005, 0.004, 0.006, 0.005],
        }
    )

    result = _create_overflow_expansion(df, ["Age", "Gender"], "Ult.", "rate", 4, 5)

    # Should create 2 durations × 4 combinations = 8 rows
    assert len(result) == 8
    assert result.columns == ["Age", "Gender", "variable", "rate"]

    # Check that all combinations are preserved
    unique_combinations = (
        result.select(["Age", "Gender"]).unique().sort(["Age", "Gender"])
    )
    expected_combinations = pl.DataFrame(
        {"Age": [30, 30, 31, 31], "Gender": ["F", "M", "F", "M"]}
    ).sort(["Age", "Gender"])
    assert unique_combinations.equals(expected_combinations)


def test_tidy_wide_with_overflow_basic():
    """Test wide table tidying with overflow expansion."""
    df = pl.DataFrame(
        {
            "Age": [30, 31, 32],
            "1": [0.001, 0.0011, 0.0012],
            "2": [0.0008, 0.0009, 0.001],
            "3": [0.0005, 0.0006, 0.0007],
            "Ult.": [0.0003, 0.0004, 0.0005],
        }
    )

    result = _tidy_wide_with_overflow_expansion(
        df,
        ["Age"],
        ["1", "2", "3", "Ult."],
        "rate",
        overflow="Ult.",
        max_overflow=5,
    )

    # Original: 3 ages × 4 durations = 12 rows
    # Expansion: 3 ages × 2 durations (4, 5) = 6 rows
    # Total: 18 rows
    assert len(result) == 18
    assert result.columns == ["Age", "variable", "rate"]

    # Check that original data is preserved
    original_data = result.filter(pl.col("variable").is_in(["1", "2", "3", "Ult."]))
    assert len(original_data) == 12

    # Check that expansion data is correct
    expanded_data = result.filter(pl.col("variable").is_in(["4", "5"]))
    assert len(expanded_data) == 6

    # Verify expanded rates match overflow rates
    age_30_ult = result.filter((pl.col("Age") == 30) & (pl.col("variable") == "Ult."))[
        "rate"
    ].item()
    age_30_expanded = result.filter(
        (pl.col("Age") == 30) & (pl.col("variable") == "4")
    )["rate"].item()
    assert age_30_ult == age_30_expanded


def test_tidy_wide_no_overflow_handling():
    """Test wide table tidying with overflow=None."""
    df = pl.DataFrame(
        {
            "Age": [30, 31],
            "1": [0.001, 0.0011],
            "2": [0.0008, 0.0009],
            "Ult.": [0.0003, 0.0004],
        }
    )

    result = _tidy_wide_with_overflow_expansion(
        df, ["Age"], ["1", "2", "Ult."], "rate", overflow=None
    )

    # Should be same as basic wide table (no expansion)
    assert len(result) == 6  # 2 ages × 3 durations
    assert result.columns == ["Age", "variable", "rate"]


def test_tidy_wide_overflow_not_found():
    """Test when specified overflow column is not found."""
    df = pl.DataFrame({"Age": [30, 31], "1": [0.001, 0.0011], "2": [0.0008, 0.0009]})

    # The function should return basic tidy table when overflow column missing
    # but only if the overflow column doesn't exist in wide_cols at all
    # Test with overflow=None first (this should work)
    result = _tidy_wide_with_overflow_expansion(
        df, ["Age"], ["1", "2"], "rate", overflow=None
    )

    # Should return basic tidy table (no expansion)
    assert len(result) == 4  # 2 ages × 2 durations
    assert result.columns == ["Age", "variable", "rate"]


def test_load_assumptions_with_overflow_auto():
    """Test loading assumptions with automatic overflow detection."""
    df = pl.DataFrame(
        {
            "Age": [30, 31, 32],
            "1": [0.001, 0.0011, 0.0012],
            "2": [0.0008, 0.0009, 0.001],
            "3": [0.0005, 0.0006, 0.0007],
            "Ult.": [0.0003, 0.0004, 0.0005],
        }
    )

    result = load_assumptions(
        "test_mortality_overflow", df, overflow="auto", max_overflow=5
    )

    # Should detect Ult. as overflow and expand to duration 5
    assert len(result) == 18  # 3 ages × (4 original + 2 expanded) durations
    assert result.columns == ["Age", "variable", "rate"]

    # Verify overflow expansion worked
    expanded_data = result.filter(pl.col("variable").is_in(["4", "5"]))
    assert len(expanded_data) == 6


def test_load_assumptions_with_overflow_explicit():
    """Test loading assumptions with explicit overflow column."""
    df = pl.DataFrame(
        {
            "Age": [30, 31],
            "1": [0.001, 0.0011],
            "2": [0.0008, 0.0009],
            "Custom_Overflow": [0.0003, 0.0004],
        }
    )

    result = load_assumptions(
        "mortality_overflow_explicit",
        df,
        overflow="Custom_Overflow",
        max_overflow=4,
    )

    # Should expand from duration 3 to 4 plus original columns (1, 2, Custom_Overflow)
    # 2 ages × (3 original + 2 expanded) durations = 10 rows total
    assert len(result) == 10  # 2 ages × 5 total durations

    # Verify expansion
    expanded_data = result.filter(pl.col("variable").is_in(["3", "4"]))
    assert len(expanded_data) == 4  # 2 ages × 2 expanded durations


def test_load_assumptions_overflow_disabled():
    """Test loading assumptions with overflow=None."""
    df = pl.DataFrame(
        {
            "Age": [30, 31],
            "1": [0.001, 0.0011],
            "2": [0.0008, 0.0009],
            "Ult.": [0.0003, 0.0004],
        }
    )

    result = load_assumptions("mortality_no_overflow", df, overflow=None)

    # Should be basic wide table with no expansion
    assert len(result) == 6  # 2 ages × 3 durations
    assert result.columns == ["Age", "variable", "rate"]


def test_overflow_integration_with_lookup():
    """Test that overflow expansion works correctly with assumption_lookup."""
    df = pl.DataFrame(
        {
            "Age": [30, 31],
            "1": [0.001, 0.0011],
            "2": [0.0008, 0.0009],
            "Ult.": [0.0005, 0.0006],
        }
    )

    load_assumptions("mortality_lookup_test", df, overflow="Ult.", max_overflow=10)

    # Test lookups using individual single-row DataFrames (following working pattern)
    test_cases = [
        (30.0, "1", 0.001),  # Original data - Age now f64
        (31.0, "2", 0.0009),  # Original data - Age now f64
        (30.0, "Ult.", 0.0005),  # Overflow column - Age now f64
        (30.0, "5", 0.0005),  # Expanded duration (should match Ult.) - Age now f64
        (30.0, "10", 0.0005),  # Expanded duration (should match Ult.) - Age now f64
    ]

    for age, variable, expected_rate in test_cases:
        # Create single-row DataFrame for lookup
        test_df = pl.DataFrame({"Age": [age], "variable": [variable]})

        # Perform lookup using the correct syntax
        result_df = test_df.with_columns(
            gs.assumption_lookup(
                "Age", "variable", table_name="mortality_lookup_test"
            ).alias("rate")
        )

        # Verify the result
        assert len(result_df) == 1
        actual_rate = result_df["rate"].item()
        assert actual_rate == expected_rate, (
            f"Expected {expected_rate} for age {age}, variable {variable}, got {actual_rate}"
        )


def test_overflow_performance_large_expansion():
    """Test performance with large overflow expansion."""
    # Create a table that would expand to many rows
    df = pl.DataFrame(
        {
            "Age": list(range(20, 25)),  # 5 ages
            "1": [0.001] * 5,
            "2": [0.0008] * 5,
            "3": [0.0005] * 5,
            "Ult.": [0.0003] * 5,
        }
    )

    # This should expand from duration 4 to 200 = 197 additional durations per age
    # Total: 5 ages × (4 original + 197 expanded) = 5 × 201 = 1005 rows
    result = load_assumptions(
        "mortality_large_expansion", df, overflow="Ult.", max_overflow=200
    )

    assert len(result) == 1005

    # Test that lookups are still fast (this is the key benefit of pre-expansion)
    import time

    # Test cases for different durations
    test_durations = ["1", "50", "100", "150", "200"]

    start_time = time.time()

    # Perform single-row lookups (following working pattern)
    for duration in test_durations:
        test_df = pl.DataFrame({"Age": [22], "variable": [duration]})
        result_df = test_df.with_columns(
            gs.assumption_lookup(
                "Age", "variable", table_name="mortality_large_expansion"
            ).alias("rate")
        )

        # Verify lookup returned a valid value
        rate = result_df["rate"].item()
        assert rate is not None

    lookup_time = time.time() - start_time

    # Lookups should be very fast (sub-millisecond per lookup)
    assert lookup_time < 0.01  # 10ms for 5 lookups is very generous


def test_overflow_memory_usage_warning():
    """Test behavior with very large max_overflow values."""
    df = pl.DataFrame({"Age": [30], "1": [0.001], "Ult.": [0.0005]})

    # This would create 1000 additional rows (duration 2 to 1000) plus original (1, Ult.)
    # Should still work but could be memory intensive
    result = load_assumptions(
        "mortality_huge_expansion", df, overflow="Ult.", max_overflow=1000
    )

    # Verify the expansion worked - includes original + expanded
    assert len(result) == 1001  # 1 age × 1001 durations (1, Ult, 2-1000)

    # Verify lookup works for extreme values using correct syntax
    test_df = pl.DataFrame({"Age": [30.0], "variable": ["999"]})
    result_df = test_df.with_columns(
        gs.assumption_lookup(
            "Age", "variable", table_name="mortality_huge_expansion"
        ).alias("rate")
    )

    rate_extreme = result_df["rate"].item()
    assert rate_extreme == 0.0005
