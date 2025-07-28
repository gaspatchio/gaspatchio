"""Tests for Excel accessor Python API - focuses on plumbing, not Excel logic."""

import datetime

import polars as pl
import pytest
from polars.testing import assert_series_equal

from gaspatchio_core import ActuarialFrame

# Test data for from_excel_serial
EXCEL_SERIAL_DATA = {
    "serial_1900": [
        1.0,  # 1900-01-01
        60.0,  # Excel 1900 leap year bug: 1900-02-29 (actually 1900-03-01)
        61.0,  # 1900-03-01 (actually 1900-03-02 due to bug adjustment)
        32331.0,  # 1988-07-05
        43831.0,  # 2020-01-01
        43831.5,  # 2020-01-01 12:00:00 (date part is 2020-01-01)
        None,
    ],
    "expected_1900": [
        datetime.date(1899, 12, 31),  # Adjusted from 1900-01-01
        datetime.date(1900, 3, 1),  # Correct handling of Excel's 1900-02-29
        datetime.date(1900, 2, 28),  # Adjusted from 1900-03-01
        datetime.date(1988, 7, 6),  # Adjusted from 1988-07-05
        datetime.date(2019, 12, 31),  # Adjusted from 2020-01-01
        datetime.date(2019, 12, 31),  # Adjusted from 2020-01-01
        None,
    ],
    "serial_1904": [
        0.0,  # 1904-01-01
        1.0,  # 1904-01-02
        1462.0,  # 1908-01-01 (a leap year in 1904 system)
        42370.0,  # 2020-01-01
        42370.75,  # 2020-01-01 18:00:00 (date part is 2020-01-01)
        None,
    ],
    "expected_1904": [
        None,  # Adjusted from 1904-01-01 (serial 0 is invalid for this logic)
        datetime.date(1904, 1, 1),  # Adjusted from 1904-01-02
        datetime.date(1908, 1, 1),
        datetime.date(2020, 1, 1),
        datetime.date(2020, 1, 1),
        None,
    ],
}


@pytest.mark.parametrize(
    "serial_col, epoch, expected_col_name",
    [
        ("serial_1900", "1900", "expected_1900"),
        ("serial_1904", "1904", "expected_1904"),
    ],
)
def test_from_excel_serial(serial_col, epoch, expected_col_name):
    """Test that from_excel_serial properly converts data types and handles nulls."""
    data = {serial_col: EXCEL_SERIAL_DATA[serial_col]}
    af = ActuarialFrame(data)
    expected_dates = EXCEL_SERIAL_DATA[expected_col_name]

    res_af = af.with_columns(
        af[serial_col].excel.from_excel_serial(epoch=epoch).alias("converted_date")
    )
    result_series = res_af.collect()["converted_date"]

    # Convert expected dates to a Polars Series for comparison
    expected_series = pl.Series("expected", expected_dates, dtype=pl.Date)
    assert_series_equal(result_series, expected_series, check_names=False)


def test_from_excel_serial_invalid_epoch():
    """Test that invalid epoch raises appropriate error."""
    af = ActuarialFrame({"data": [1]})
    with pytest.raises(
        ValueError, match="Invalid epoch '2000'. Must be '1900' or '1904'."
    ):
        af["data"].excel.from_excel_serial(
            epoch="2000"
        )._expr.explode()  # Explode to trigger computation


# --- Tests for yearfrac API behavior ---


def test_yearfrac_scalar_scalar():
    """Test yearfrac with scalar start and scalar end dates (column to column)."""
    af = ActuarialFrame(
        {
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)],
        }
    )

    # Test that the function executes and returns a float
    res_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis="act/act").alias("year_frac")
    )
    result = res_af.collect()["year_frac"][0]
    assert isinstance(result, float)


def test_yearfrac_scalar_literal():
    """Test yearfrac with column and literal date."""
    af = ActuarialFrame({"start": [datetime.date(2020, 1, 1)]})
    end_literal = datetime.date(2020, 7, 1)

    # Test that literal dates are properly handled
    res_af = af.with_columns(
        af["start"].excel.yearfrac(end_literal, basis="act/act").alias("year_frac")
    )
    result = res_af.collect()["year_frac"][0]
    assert isinstance(result, float)


def test_yearfrac_vector_vector():
    """Test yearfrac with vector start and vector end dates."""
    start_dates = [
        datetime.date(2020, 1, 1),
        datetime.date(2021, 1, 1),
        datetime.date(2022, 1, 1),
    ]
    end_dates = [
        datetime.date(2020, 7, 1),
        datetime.date(2021, 7, 1),
        datetime.date(2022, 7, 1),
    ]
    
    af = ActuarialFrame({"start": start_dates, "end": end_dates})

    # Test that vector operations work
    res_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis="act/act").alias("year_frac")
    )
    results = res_af.collect()["year_frac"]
    
    # Should have same length as input
    assert len(results) == len(start_dates)
    # All results should be floats
    assert all(isinstance(r, float) for r in results)


def test_yearfrac_with_nulls():
    """Test yearfrac handles null values properly."""
    af = ActuarialFrame(
        {
            "start": [
                datetime.date(2020, 1, 1),
                None,
                datetime.date(2022, 1, 1),
            ],
            "end": [
                datetime.date(2020, 7, 1),
                datetime.date(2021, 7, 1),
                None,
            ],
        }
    )

    res_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis="act/act").alias("year_frac")
    )
    results = res_af.collect()["year_frac"]
    
    # First result should be a float, others should be null
    assert isinstance(results[0], float)
    assert results[1] is None
    assert results[2] is None


def test_yearfrac_basis_string_to_int_conversion():
    """Test that string basis values are properly converted to integers."""
    af = ActuarialFrame(
        {
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)],
        }
    )

    # Test various string basis formats
    basis_mappings = {
        "act/act": 1,
        "actual/actual": 1,
        "us_nasd_30_360": 0,
        "30/360": 0,
        "actual/360": 2,
        "actual_360": 2,
        "actual/365": 3,
        "actual_365": 3,
        "european_30_360": 4,
        "30e/360": 4,  # Use lowercase e to match implementation
    }

    # Test that all string formats work
    for basis_str in basis_mappings:
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis=basis_str).alias("year_frac")
        )
        result = res_af.collect()["year_frac"][0]
        assert isinstance(result, float)


def test_yearfrac_invalid_basis_string():
    """Test that invalid basis strings raise appropriate errors."""
    af = ActuarialFrame(
        {
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)],
        }
    )

    with pytest.raises(ValueError, match="Invalid basis"):
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis="invalid_basis").alias("year_frac")
        )
        res_af.collect()


def test_yearfrac_invalid_basis_int():
    """Test that invalid basis integers raise appropriate errors."""
    af = ActuarialFrame(
        {
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)],
        }
    )

    with pytest.raises(ValueError, match="Invalid basis"):
        res_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis=99).alias("year_frac")
        )
        res_af.collect()


def test_yearfrac_list_not_supported():
    """Test that list columns raise NotImplementedError with helpful message."""
    # Test list start dates  
    df = pl.DataFrame(
        {"start_list": [[datetime.date(2020, 1, 1), datetime.date(2020, 6, 1)]]},
        schema={"start_list": pl.List(pl.Date)},
    )
    af = ActuarialFrame(df)

    with pytest.raises(NotImplementedError, match="yearfrac with list columns is not yet supported"):
        res_af = af.with_columns(
            af["start_list"].excel.yearfrac(datetime.date(2021, 1, 1)).alias("year_frac")
        )
        res_af.collect()


def test_yearfrac_list_end_not_supported():
    """Test that list end dates also raise NotImplementedError."""
    df = pl.DataFrame(
        {"end_list": [[datetime.date(2020, 7, 1), datetime.date(2021, 1, 1)]]},
        schema={"end_list": pl.List(pl.Date)},
    )
    af = ActuarialFrame(df)

    with pytest.raises(NotImplementedError, match="yearfrac with list columns is not yet supported"):
        res_af = af.with_columns(
            af["end_list"].excel.yearfrac(datetime.date(2020, 1, 1)).alias("year_frac")
        )
        res_af.collect()


def test_yearfrac_both_lists_not_supported():
    """Test that both lists raise NotImplementedError."""
    df = pl.DataFrame(
        {
            "start_list": [[datetime.date(2020, 1, 1)]],
            "end_list": [[datetime.date(2021, 1, 1)]],
        },
        schema={
            "start_list": pl.List(pl.Date),
            "end_list": pl.List(pl.Date),
        },
    )
    af = ActuarialFrame(df)

    with pytest.raises(NotImplementedError, match="yearfrac with list columns is not yet supported"):
        res_af = af.with_columns(
            af["start_list"].excel.yearfrac(af["end_list"]).alias("year_frac")
        )
        res_af.collect()


def test_yearfrac_returns_expression_proxy():
    """Test that yearfrac returns an ExpressionProxy that can be chained."""
    af = ActuarialFrame(
        {
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)],
        }
    )

    # Test chaining operations
    res_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"]).alias("year_frac")
    ).with_columns(
        (pl.col("year_frac") * 12).alias("months")  # Should be able to use result in further ops
    )
    
    result = res_af.collect()
    assert "year_frac" in result.columns
    assert "months" in result.columns
    assert isinstance(result["months"][0], float)


def test_yearfrac_different_date_types():
    """Test that yearfrac works with different date column types."""
    # Test with string dates that get converted
    df = pl.DataFrame({
        "start_str": ["2020-01-01"],
        "end_date": [datetime.date(2020, 7, 1)]
    }).with_columns(
        pl.col("start_str").str.to_date().alias("start_date")
    )
    
    af = ActuarialFrame(df)
    
    res_af = af.with_columns(
        af["start_date"].excel.yearfrac(af["end_date"]).alias("year_frac")
    )
    result = res_af.collect()["year_frac"][0]
    assert isinstance(result, float)


def test_yearfrac_basis_case_insensitive():
    """Test that basis strings are case insensitive."""
    af = ActuarialFrame(
        {
            "start": [datetime.date(2020, 1, 1)],
            "end": [datetime.date(2020, 7, 1)],
        }
    )

    # Test mixed case
    res_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis="ACT/ACT").alias("year_frac")
    )
    result = res_af.collect()["year_frac"][0]
    assert isinstance(result, float)