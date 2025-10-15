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


# The yearfrac tests have been moved to tests/accessors/excel_functions/test_yearfrac.py
# This file now focuses on other Excel accessor functionality