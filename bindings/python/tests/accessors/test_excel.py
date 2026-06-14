# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for Excel accessor Python API - focuses on plumbing, not Excel logic."""

import datetime

import polars as pl
import pytest
from openpyxl.utils.datetime import MAC_EPOCH, from_excel
from polars.testing import assert_series_equal

from gaspatchio_core import ActuarialFrame

# Test data for from_excel_serial
# Expected values verified against openpyxl.utils.datetime.from_excel (the reference implementation)
EXCEL_SERIAL_DATA = {
    "serial_1900": [
        1.0,  # 1900-01-01
        60.0,  # Excel's phantom 1900-02-29 → maps to 1900-02-28 (same as serial 59)
        61.0,  # 1900-03-01
        32331.0,  # 1988-07-07
        43831.0,  # 2020-01-01
        43831.5,  # 2020-01-01 12:00:00 (date part is 2020-01-01)
        None,
    ],
    "expected_1900": [
        datetime.date(1900, 1, 1),  # Serial 1 = 1900-01-01
        datetime.date(1900, 2, 28),  # Serial 60 = 1900-02-28 (Excel's phantom Feb 29)
        datetime.date(1900, 3, 1),  # Serial 61 = 1900-03-01
        datetime.date(1988, 7, 7),  # Serial 32331 = 1988-07-07
        datetime.date(2020, 1, 1),  # Serial 43831 = 2020-01-01
        datetime.date(2020, 1, 1),  # Serial 43831.5 = 2020-01-01 (fractional part is time)
        None,
    ],
    "serial_1904": [
        0.0,  # Serial 0 = time only (midnight), not a date → invalid
        1.0,  # 1904-01-02
        1462.0,  # 1908-01-02
        42370.0,  # 2020-01-02
        42370.75,  # 2020-01-02 18:00:00 (date part is 2020-01-02)
        None,
    ],
    "expected_1904": [
        None,  # Serial 0 is invalid (represents time only)
        datetime.date(1904, 1, 2),  # Serial 1 = 1904-01-02
        datetime.date(1908, 1, 2),
        datetime.date(2020, 1, 2),
        datetime.date(2020, 1, 2),
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


# =============================================================================
# Comprehensive from_excel_serial tests comparing with openpyxl reference
# =============================================================================


class TestFromExcelSerialAgainstOpenpyxl:
    """Tests that verify from_excel_serial matches openpyxl's from_excel function.

    openpyxl is the reference implementation for Excel serial date conversion.
    These tests ensure our implementation handles Excel's 1900 leap year bug correctly.
    """

    @pytest.mark.parametrize(
        "serial,description",
        [
            (1, "First valid serial - 1900-01-01"),
            (2, "Second day - 1900-01-02"),
            (59, "Day before Excel's phantom leap day - 1900-02-28"),
            (60, "Excel's phantom 1900-02-29 - should map to 1900-02-28"),
            (61, "Day after phantom leap day - 1900-03-01"),
            (62, "Two days after phantom - 1900-03-02"),
        ],
    )
    def test_boundary_dates_around_excel_leap_year_bug(self, serial, description):
        """Test critical boundary dates around Excel's 1900 leap year bug."""
        expected = from_excel(serial).date()

        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected, f"{description}: expected {expected}, got {result}"

    @pytest.mark.parametrize(
        "serial,expected_date",
        [
            # Issue GSP-78 specific test cases
            (45777, datetime.date(2025, 4, 30)),  # The policy effective date from GSP-78
            (44197, datetime.date(2021, 1, 1)),  # 2021-01-01 (was showing as 2020-12-31)
            (44562, datetime.date(2022, 1, 1)),  # 2022-01-01
            (44927, datetime.date(2023, 1, 1)),  # 2023-01-01
        ],
    )
    def test_gsp78_issue_test_cases(self, serial, expected_date):
        """Test specific cases from GSP-78 issue that exposed the off-by-one bug."""
        # Verify our expected values match openpyxl
        openpyxl_date = from_excel(serial).date()
        assert openpyxl_date == expected_date, "Sanity check: openpyxl disagrees"

        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected_date, f"Serial {serial}: expected {expected_date}, got {result}"

    @pytest.mark.parametrize(
        "serial",
        [
            # Modern dates (post-2000)
            36526,  # 2000-01-01
            40179,  # 2010-01-01
            43831,  # 2020-01-01
            45292,  # 2024-01-01
            # Historical dates
            1,      # 1900-01-01
            366,    # 1900-12-31
            367,    # 1901-01-01
            10000,  # 1927-05-18
            20000,  # 1954-10-03
            30000,  # 1982-02-18
            # Year boundaries
            693,    # 1901-11-23
            # Large future dates
            50000,  # 2036-11-21
            60000,  # 2064-04-08
        ],
    )
    def test_various_dates_match_openpyxl(self, serial):
        """Test that various dates across different eras match openpyxl."""
        expected = from_excel(serial).date()

        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected, f"Serial {serial}: expected {expected}, got {result}"

    def test_batch_conversion_matches_openpyxl(self):
        """Test batch conversion of many serials matches openpyxl."""
        # Generate a range of test serials
        test_serials = list(range(1, 100)) + list(range(55, 70)) + [
            32331, 43831, 44197, 44562, 44927, 45777,
            36526, 40179, 45292, 50000,
        ]

        af = ActuarialFrame({"serial": test_serials})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        results = af.collect()["converted_date"].to_list()

        for serial, result in zip(test_serials, results):
            expected = from_excel(serial).date()
            assert result == expected, f"Serial {serial}: expected {expected}, got {result}"

    def test_fractional_serials_extract_date_correctly(self):
        """Test that fractional serials (with time component) extract date correctly."""
        # Serial 44197 = 2021-01-01, fractional part is time
        test_cases = [
            (44197.0, datetime.date(2021, 1, 1)),    # Midnight
            (44197.25, datetime.date(2021, 1, 1)),   # 6:00 AM
            (44197.5, datetime.date(2021, 1, 1)),    # Noon
            (44197.75, datetime.date(2021, 1, 1)),   # 6:00 PM
            (44197.99, datetime.date(2021, 1, 1)),   # 11:45 PM
        ]

        for serial, expected in test_cases:
            af = ActuarialFrame({"serial": [serial]})
            af = af.with_columns(
                af["serial"].excel.from_excel_serial().alias("converted_date")
            )
            result = af.collect()["converted_date"][0]
            assert result == expected, f"Serial {serial}: expected {expected}, got {result}"

    def test_null_handling(self):
        """Test that null values are preserved correctly."""
        af = ActuarialFrame({"serial": [1.0, None, 44197.0, None, 45777.0]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        results = af.collect()["converted_date"].to_list()

        assert results[0] == datetime.date(1900, 1, 1)
        assert results[1] is None
        assert results[2] == datetime.date(2021, 1, 1)
        assert results[3] is None
        assert results[4] == datetime.date(2025, 4, 30)

    def test_invalid_serial_returns_null(self):
        """Test that invalid serials (< 1) return null."""
        af = ActuarialFrame({"serial": [0.0, -1.0, 0.5, 0.99]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        results = af.collect()["converted_date"].to_list()

        for result in results:
            assert result is None, f"Invalid serial should return None, got {result}"

    def test_month_end_dates_critical_for_actuarial_calculations(self):
        """Test month-end dates that are critical for actuarial anniversary calculations.

        GSP-78 was discovered because month-end dates (Apr 30, Aug 30, etc.) were
        being converted incorrectly, causing YEARFRAC and subsequent mortality
        calculations to be wrong.
        """
        # Month-end dates that are often used as policy effective dates
        month_end_serials = [
            (45412, datetime.date(2024, 4, 30)),   # Apr 30, 2024
            (45534, datetime.date(2024, 8, 30)),   # Aug 30, 2024
            (45626, datetime.date(2024, 11, 30)), # Nov 30, 2024
            (45657, datetime.date(2024, 12, 31)), # Dec 31, 2024
            (45777, datetime.date(2025, 4, 30)),   # Apr 30, 2025 (from GSP-78)
        ]

        for serial, expected in month_end_serials:
            # Verify against openpyxl
            openpyxl_date = from_excel(serial).date()
            assert openpyxl_date == expected, f"Sanity check failed for serial {serial}"

            af = ActuarialFrame({"serial": [serial]})
            af = af.with_columns(
                af["serial"].excel.from_excel_serial().alias("converted_date")
            )
            result = af.collect()["converted_date"][0]
            assert result == expected, f"Serial {serial}: expected {expected}, got {result}"


class TestFromExcelSerial1904Epoch:
    """Tests for the 1904 epoch (Mac Excel)."""

    def test_1904_epoch_serial_1(self):
        """Test that serial 1 in 1904 epoch is 1904-01-02."""
        expected = datetime.date(1904, 1, 2)

        af = ActuarialFrame({"serial": [1]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial(epoch="1904").alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected

    @pytest.mark.parametrize(
        "serial",
        [1, 366, 1462, 10000, 42370],
    )
    def test_1904_epoch_various_dates(self, serial):
        """Test various dates in 1904 epoch match openpyxl."""
        expected = from_excel(serial, epoch=MAC_EPOCH).date()

        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"]
            .excel.from_excel_serial(epoch="1904")
            .alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected, f"Serial {serial}: expected {expected}, got {result}"
