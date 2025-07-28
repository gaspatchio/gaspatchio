"""Tests for US NASD 30/360 basis - focuses on Python API, not Excel calculation correctness."""

import datetime

import polars as pl
import pytest

from gaspatchio_core import ActuarialFrame


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


def test_yearfrac_us_nasd_30_360_executes():
    """Test that US NASD 30/360 basis executes without error."""
    # Test a variety of date combinations to ensure the Python layer handles them
    test_cases = [
        # Regular cases
        (datetime.date(2020, 1, 1), datetime.date(2021, 1, 1)),
        (datetime.date(2020, 1, 1), datetime.date(2020, 7, 1)),
        
        # End of month cases
        (datetime.date(2020, 1, 31), datetime.date(2020, 2, 29)),
        (datetime.date(2021, 1, 31), datetime.date(2021, 2, 28)),
        (datetime.date(2021, 2, 28), datetime.date(2021, 3, 30)),
        (datetime.date(2020, 2, 29), datetime.date(2020, 3, 30)),
        
        # 31st to 31st
        (datetime.date(2020, 1, 31), datetime.date(2020, 3, 31)),
        (datetime.date(2020, 3, 31), datetime.date(2020, 4, 1)),
        (datetime.date(2020, 4, 30), datetime.date(2020, 5, 31)),
        
        # Special cases
        (datetime.date(2016, 2, 29), datetime.date(2016, 3, 1)),
        
        # Negative duration
        (datetime.date(2020, 3, 15), datetime.date(2020, 2, 15)),
    ]

    for start_date, end_date in test_cases:
        af = ActuarialFrame({"start": [start_date], "end": [end_date]})
        
        # Test with basis 0 (US NASD 30/360)
        result_af = af.with_columns(
            af["start"].excel.yearfrac(af["end"], basis=0).alias("year_frac")
        )
        result = result_af.collect()["year_frac"][0]
        
        # Just verify it executes and returns a float
        assert isinstance(result, float)


def test_yearfrac_vector_us_nasd_30_360():
    """Test US NASD 30/360 with vector inputs."""
    start_dates = [
        datetime.date(2020, 1, 1),
        datetime.date(2020, 1, 31),
        datetime.date(2021, 2, 28),
    ]
    end_dates = [
        datetime.date(2020, 7, 1),
        datetime.date(2020, 2, 29),
        datetime.date(2021, 3, 30),
    ]
    
    af = ActuarialFrame({"start": start_dates, "end": end_dates})
    
    result_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis=0).alias("year_frac")
    )
    results = result_af.collect()["year_frac"]
    
    # Should have same length as input and all be floats
    assert len(results) == len(start_dates)
    assert all(isinstance(r, float) for r in results)


def test_yearfrac_us_nasd_with_nulls():
    """Test US NASD 30/360 handles nulls properly."""
    af = ActuarialFrame({
        "start": [datetime.date(2020, 1, 1), None, datetime.date(2020, 3, 1)],
        "end": [datetime.date(2020, 2, 1), datetime.date(2020, 4, 1), None]
    })
    
    result_af = af.with_columns(
        af["start"].excel.yearfrac(af["end"], basis=0).alias("year_frac")
    )
    results = result_af.collect()["year_frac"]
    
    # First should be float, others should be null
    assert isinstance(results[0], float)
    assert results[1] is None
    assert results[2] is None


def test_yearfrac_invalid_basis():
    """Test that an invalid basis value raises an appropriate error."""
    af = ActuarialFrame({"start": [datetime.date(2020, 1, 1)]})

    with pytest.raises(ValueError, match="Invalid basis"):
        af.with_columns(
            af["start"]
            .excel.yearfrac(datetime.date(2021, 1, 1), basis="invalid_basis")
            .alias("year_frac")
        ).collect()


def test_yearfrac_us_nasd_different_types():
    """Test US NASD 30/360 with different date column types."""
    # Create frame with string dates that get converted
    df = pl.DataFrame({
        "start_str": ["2020-01-31", "2020-02-29"],
        "end_str": ["2020-02-29", "2020-03-31"]
    }).with_columns([
        pl.col("start_str").str.to_date().alias("start_date"),
        pl.col("end_str").str.to_date().alias("end_date")
    ])
    
    af = ActuarialFrame(df)
    
    result_af = af.with_columns(
        af["start_date"].excel.yearfrac(af["end_date"], basis=0).alias("year_frac")
    )
    results = result_af.collect()["year_frac"]
    
    assert len(results) == 2
    assert all(isinstance(r, float) for r in results)


def test_yearfrac_us_nasd_scalar_literal():
    """Test US NASD 30/360 with scalar and literal combinations."""
    af = ActuarialFrame({
        "start": [datetime.date(2020, 1, 31)]
    })
    
    # Test column with literal
    result1 = af.with_columns(
        af["start"].excel.yearfrac(datetime.date(2020, 2, 29), basis=0).alias("year_frac")
    ).collect()["year_frac"][0]
    
    assert isinstance(result1, float)
    
    # Test literal with column (need to create the literal as a column)
    af2 = ActuarialFrame({
        "start": [datetime.date(2020, 1, 31)],
        "end": [datetime.date(2020, 2, 29)]
    })
    
    result2 = af2.with_columns(
        af2["start"].excel.yearfrac(af2["end"], basis=0).alias("year_frac")
    ).collect()["year_frac"][0]
    
    # Should get same result
    assert result1 == result2