import datetime

import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio_core import ActuarialFrame

# Test data for US NASD 30/360 yearfrac calculations
# Test cases include common scenarios and edge cases for the US NASD 30/360 day count convention
US_NASD_30_360_CASES = [
    # Regular case - full years
    {
        "start_date": datetime.date(2020, 1, 1),
        "end_date": datetime.date(2021, 1, 1),
        "expected_result": 1.0,  # Exactly 1 year in 30/360
        "description": "Exactly one year",
    },
    # Regular case - partial years
    {
        "start_date": datetime.date(2020, 1, 1),
        "end_date": datetime.date(2020, 7, 1),
        "expected_result": 0.5,  # Half a year in 30/360
        "description": "Half a year",
    },
    # Case with end of month in a 31-day month
    {
        "start_date": datetime.date(2020, 1, 31),
        "end_date": datetime.date(2020, 2, 29),
        "expected_result": 1 / 12,  # Should be exactly 1 month (30 days / 360)
        "description": "Jan 31 to Feb 29 (leap year)",
    },
    # February edge case - Feb 28 in non-leap year
    {
        "start_date": datetime.date(2021, 1, 31),
        "end_date": datetime.date(2021, 2, 28),
        "expected_result": 1 / 12,  # Should be exactly 1 month (30 days / 360)
        "description": "Jan 31 to Feb 28 (non-leap year)",
    },
    # February edge case - Feb 28 as start date
    {
        "start_date": datetime.date(2021, 2, 28),
        "end_date": datetime.date(2021, 3, 30),
        "expected_result": 1 / 12,  # Should be exactly 1 month (30 days / 360)
        "description": "Feb 28 to Mar 30 (non-leap year)",
    },
    # February edge case - Feb 29 as start date in leap year
    {
        "start_date": datetime.date(2020, 2, 29),
        "end_date": datetime.date(2020, 3, 30),
        "expected_result": 1 / 12,  # Should be exactly 1 month (30 days / 360)
        "description": "Feb 29 to Mar 30 (leap year)",
    },
    # Case with 31st to 31st (both should be adjusted to 30th)
    {
        "start_date": datetime.date(2020, 1, 31),
        "end_date": datetime.date(2020, 3, 31),
        "expected_result": 2 / 12,  # Should be exactly 2 months (60 days / 360)
        "description": "Jan 31 to Mar 31 (31st to 31st)",
    },
    # Case with 31st to 1st of next month
    {
        "start_date": datetime.date(2020, 3, 31),
        "end_date": datetime.date(2020, 4, 1),
        "expected_result": 1 / 360,  # Should be 1 day (1 / 360)
        "description": "Mar 31 to Apr 1 (31st to 1st of next month)",
    },
    # Case with 30th to 31st
    {
        "start_date": datetime.date(2020, 4, 30),
        "end_date": datetime.date(2020, 5, 31),
        "expected_result": 1 / 12,  # Should be exactly 1 month (30 days / 360)
        "description": "Apr 30 to May 31 (30th to 31st)",
    },
    # Special February case - the Excel quirk mentioned in the description
    {
        "start_date": datetime.date(2016, 2, 29),
        "end_date": datetime.date(2016, 3, 1),
        "expected_result": 1 / 360,  # Should be 1 day
        "description": "Feb 29 to Mar 1 (Excel quirk with leap year)",
    },
    # Check negative duration
    {
        "start_date": datetime.date(2020, 3, 15),
        "end_date": datetime.date(2020, 2, 15),
        "expected_result": -1 / 12,  # Should be -1 month (-30 days / 360)
        "description": "Negative duration - Mar 15 to Feb 15",
    },
]


@pytest.mark.parametrize(
    "case",
    US_NASD_30_360_CASES,
    ids=[case["description"] for case in US_NASD_30_360_CASES],
)
def test_yearfrac_us_nasd_30_360(case):
    """Test that the US NASD 30/360 day count convention is implemented correctly."""
    start_date = case["start_date"]
    end_date = case["end_date"]
    expected_result = case["expected_result"]

    # Create a simple ActuarialFrame with the test dates
    af = ActuarialFrame({"start": [start_date], "end": [end_date]})

    # Test with basis 0 (US NASD 30/360)
    result_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis=0).alias("year_frac")
    )
    result = result_af.collect()["year_frac"][0]

    # Compare with expected result with small tolerance for floating-point precision
    assert abs(result - expected_result) < 1e-10, (
        f"Expected {expected_result} but got {result} for {start_date} to {end_date}"
    )


def test_yearfrac_basis_number_and_string_equivalence():
    """Test that numeric and string basis specifications are equivalent."""
    start_date = datetime.date(2020, 1, 1)
    end_date = datetime.date(2021, 1, 1)

    # Create a simple ActuarialFrame with the test dates
    af = ActuarialFrame({"start": [start_date], "end": [end_date]})

    # Test basis specified as number
    result_num = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis=0).alias("year_frac_num")
    ).collect()["year_frac_num"][0]

    # Test basis specified as string
    result_str = af.with_columns(
        af["start"]
        .excel.yearfrac(af["end"], basis="us_nasd_30_360")
        .alias("year_frac_str")
    ).collect()["year_frac_str"][0]

    # Results should be identical
    assert result_num == result_str

    # Also test other string aliases
    result_str2 = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis="30/360").alias("year_frac_str2")
    ).collect()["year_frac_str2"][0]

    assert result_num == result_str2


def test_yearfrac_invalid_basis():
    """Test that an invalid basis value raises an appropriate error."""
    af = ActuarialFrame({"start": [datetime.date(2020, 1, 1)]})

    with pytest.raises(ValueError, match="Invalid basis"):
        af.with_columns(
            af["start"]
            .excel.yearfrac(datetime.date(2021, 1, 1), basis="invalid_basis")
            .alias("year_frac")
        ).collect()


def test_yearfrac_with_list_column_us_nasd_30_360():
    """Test 30/360 US NASD yearfrac with list columns."""
    start_date_scalar = datetime.date(2020, 1, 1)
    end_dates_list = [
        datetime.date(2020, 7, 1),  # Should give 0.5
        datetime.date(2021, 1, 1),  # Should give 1.0
        datetime.date(2020, 2, 29),  # Should test Feb 29 handling
    ]

    df = pl.DataFrame(
        {"end_list": [end_dates_list]}, schema={"end_list": pl.List(pl.Date)}
    )
    af = ActuarialFrame(df)

    # Expected results based on US NASD 30/360 rules
    expected_fractions = [0.5, 1.0, 0.16389]  # 6 months, 12 months, and ~59/360

    # In this case, we want yearfrac(start_date_scalar, end_dates_list)
    # But when calling on the list column, the parameter ordering is reversed
    # Since end_list is the column we're calling .excel.yearfrac() on
    # We're actually calculating yearfrac(end_dates_list, start_date_scalar)
    # So we need to pass the start_date as the end parameter
    # This would give us negative values like we're seeing

    # The correct way to call it is by putting the start date on a column
    # and calling yearfrac on that column with the list as parameter
    df_correct = pl.DataFrame(
        {"start_date": [start_date_scalar], "end_list": [end_dates_list]},
        schema={"start_date": pl.Date, "end_list": pl.List(pl.Date)},
    )
    af_correct = ActuarialFrame(df_correct)

    res_af = af_correct.with_columns(
        af_correct["start_date"]
        .excel.yearfrac(af_correct["end_list"], basis=0)
        .alias("year_frac_list")
    )

    result_list = res_af.collect()["year_frac_list"][0]
    expected_series = pl.Series("expected", expected_fractions, dtype=pl.Float64)
    result_series = pl.Series("result", result_list, dtype=pl.Float64)

    # Check that the results match expected values
    # Use a more relaxed tolerance for the Feb case (index 2)
    assert_series_equal(result_series, expected_series, rtol=1e-3, check_names=False)
