"""Tests for Excel accessor Python API - focuses on plumbing, not Excel logic."""

import datetime

import polars as pl
import pytest
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
# Comprehensive from_excel_serial tests with hardcoded expected values
# All expected values have been verified against openpyxl.utils.datetime.from_excel
# =============================================================================


class TestFromExcelSerialBoundaryDates:
    """Tests for critical boundary dates around Excel's 1900 leap year bug.

    All expected values verified against openpyxl.utils.datetime.from_excel.
    """

    @pytest.mark.parametrize(
        "serial,expected_date,description",
        [
            (1, datetime.date(1900, 1, 1), "First valid serial - 1900-01-01"),
            (2, datetime.date(1900, 1, 2), "Second day - 1900-01-02"),
            (59, datetime.date(1900, 2, 28), "Day before Excel's phantom leap day"),
            (60, datetime.date(1900, 2, 28), "Excel's phantom 1900-02-29 → 1900-02-28"),
            (61, datetime.date(1900, 3, 1), "Day after phantom leap day - 1900-03-01"),
            (62, datetime.date(1900, 3, 2), "Two days after phantom - 1900-03-02"),
        ],
    )
    def test_boundary_dates_around_excel_leap_year_bug(
        self, serial, expected_date, description
    ):
        """Test critical boundary dates around Excel's 1900 leap year bug."""
        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected_date, f"{description}: expected {expected_date}, got {result}"


class TestFromExcelSerialGSP78:
    """Tests for GSP-78 issue that exposed the off-by-one bug.

    All expected values verified against openpyxl.utils.datetime.from_excel.
    """

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
        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected_date, f"Serial {serial}: expected {expected_date}, got {result}"


class TestFromExcelSerialVariousDates:
    """Tests for various dates across different eras.

    All expected values verified against openpyxl.utils.datetime.from_excel.
    """

    @pytest.mark.parametrize(
        "serial,expected_date",
        [
            # Modern dates (post-2000)
            (36526, datetime.date(2000, 1, 1)),
            (40179, datetime.date(2010, 1, 1)),
            (43831, datetime.date(2020, 1, 1)),
            (45292, datetime.date(2024, 1, 1)),
            # Historical dates
            (1, datetime.date(1900, 1, 1)),
            (366, datetime.date(1900, 12, 31)),
            (367, datetime.date(1901, 1, 1)),
            (10000, datetime.date(1927, 5, 18)),
            (20000, datetime.date(1954, 10, 3)),
            (30000, datetime.date(1982, 2, 18)),
            # Random mid-year
            (693, datetime.date(1901, 11, 23)),
            # Large future dates
            (50000, datetime.date(2036, 11, 21)),
            (60000, datetime.date(2064, 4, 8)),
        ],
    )
    def test_various_dates(self, serial, expected_date):
        """Test that various dates across different eras are correct."""
        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected_date, f"Serial {serial}: expected {expected_date}, got {result}"


class TestFromExcelSerialBatchAndEdgeCases:
    """Tests for batch conversion and edge cases.

    All expected values verified against openpyxl.utils.datetime.from_excel.
    """

    def test_batch_conversion(self):
        """Test batch conversion of many serials."""
        # Pre-computed expected values (verified against openpyxl)
        test_data = [
            (1, datetime.date(1900, 1, 1)),
            (59, datetime.date(1900, 2, 28)),
            (60, datetime.date(1900, 2, 28)),
            (61, datetime.date(1900, 3, 1)),
            (100, datetime.date(1900, 4, 9)),
            (32331, datetime.date(1988, 7, 7)),
            (43831, datetime.date(2020, 1, 1)),
            (44197, datetime.date(2021, 1, 1)),
            (44562, datetime.date(2022, 1, 1)),
            (44927, datetime.date(2023, 1, 1)),
            (45777, datetime.date(2025, 4, 30)),
            (36526, datetime.date(2000, 1, 1)),
            (40179, datetime.date(2010, 1, 1)),
            (45292, datetime.date(2024, 1, 1)),
            (50000, datetime.date(2036, 11, 21)),
        ]

        serials = [s for s, _ in test_data]
        expected_dates = [d for _, d in test_data]

        af = ActuarialFrame({"serial": serials})
        af = af.with_columns(
            af["serial"].excel.from_excel_serial().alias("converted_date")
        )
        results = af.collect()["converted_date"].to_list()

        for serial, result, expected in zip(serials, results, expected_dates):
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

        All expected values verified against openpyxl.utils.datetime.from_excel.
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
            af = ActuarialFrame({"serial": [serial]})
            af = af.with_columns(
                af["serial"].excel.from_excel_serial().alias("converted_date")
            )
            result = af.collect()["converted_date"][0]
            assert result == expected, f"Serial {serial}: expected {expected}, got {result}"


class TestFromExcelSerial1904Epoch:
    """Tests for the 1904 epoch (Mac Excel).

    All expected values verified against openpyxl.utils.datetime.from_excel with MAC_EPOCH.
    """

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
        "serial,expected_date",
        [
            (1, datetime.date(1904, 1, 2)),
            (366, datetime.date(1905, 1, 1)),
            (1462, datetime.date(1908, 1, 2)),
            (10000, datetime.date(1931, 5, 19)),
            (42370, datetime.date(2020, 1, 2)),
        ],
    )
    def test_1904_epoch_various_dates(self, serial, expected_date):
        """Test various dates in 1904 epoch."""
        af = ActuarialFrame({"serial": [serial]})
        af = af.with_columns(
            af["serial"]
            .excel.from_excel_serial(epoch="1904")
            .alias("converted_date")
        )
        result = af.collect()["converted_date"][0]

        assert result == expected_date, f"Serial {serial}: expected {expected_date}, got {result}"
