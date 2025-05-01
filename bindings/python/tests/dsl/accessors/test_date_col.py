"""Tests for the DateColumnAccessor."""

import datetime

import polars as pl
import pytest

# Simulate the accessor being attached to the proxy (will happen in Prompt 3)
# For now, we manually create the accessor for testing.
from gaspatchio_core.dsl.accessors.date import DateColumnAccessor
from gaspatchio_core.dsl.core import ActuarialFrame, ExpressionProxy


@pytest.fixture
def sample_af() -> ActuarialFrame:
    """Provides a sample ActuarialFrame for testing."""
    data = {
        "serial_1900_int": [
            1,
            60,
            61,
            44927,
            45000,
            None,
        ],  # 1900-01-01, 1900-02-29 (invalid), 1900-03-01, 2023-01-01, 2023-03-15
        "serial_1900_float": [
            1.0,
            60.5,
            61.75,
            44927.25,
            45000.9,
            None,
        ],  # Includes time component
        "serial_1904_int": [
            0,
            1461,
            1462,
            42004,
            42369,
            None,
        ],  # 1904-01-01, 1908-01-01, 1908-01-02, 2019-01-01, 2020-01-01
        "not_numeric": ["a", "b", "c", "d", "e", "f"],
    }
    return ActuarialFrame(data)


# --- Test Cases for from_excel_serial ---


def test_from_excel_serial_1900_epoch_int(sample_af):
    """Test conversion from integer serials with 1900 epoch."""
    proxy = sample_af["serial_1900_int"]
    accessor = DateColumnAccessor(proxy)
    result_proxy = accessor.from_excel_serial(epoch="1900")

    assert isinstance(result_proxy, ExpressionProxy)

    sample_af["result"] = result_proxy
    result_series = sample_af.collect()["result"]

    expected_dates = [
        datetime.date(1900, 1, 1),
        datetime.date(1900, 3, 1),
        datetime.date(1900, 3, 1),
        datetime.date(2023, 1, 1),
        datetime.date(2023, 3, 15),
        None,
    ]
    assert result_series.to_list() == expected_dates
    assert result_series.dtype == pl.Date


def test_from_excel_serial_1900_epoch_float(sample_af):
    """Test conversion from float serials with 1900 epoch (ignores time)."""
    proxy = sample_af["serial_1900_float"]
    accessor = DateColumnAccessor(proxy)
    result_proxy = accessor.from_excel_serial(epoch="1900")

    assert isinstance(result_proxy, ExpressionProxy)

    sample_af["result"] = result_proxy
    result_series = sample_af.collect()["result"]

    # Expected dates are the same as int test, time component is truncated by cast to Date
    expected_dates = [
        datetime.date(1900, 1, 1),
        datetime.date(1900, 3, 1),
        datetime.date(1900, 3, 1),
        datetime.date(2023, 1, 1),
        datetime.date(2023, 3, 15),
        None,
    ]
    assert result_series.to_list() == expected_dates
    assert result_series.dtype == pl.Date


def test_from_excel_serial_1904_epoch_int(sample_af):
    """Test conversion from integer serials with 1904 epoch."""
    proxy = sample_af["serial_1904_int"]
    accessor = DateColumnAccessor(proxy)
    result_proxy = accessor.from_excel_serial(epoch="1904")

    assert isinstance(result_proxy, ExpressionProxy)

    sample_af["result"] = result_proxy
    result_series = sample_af.collect()["result"]

    # Expected dates based on corrected serials
    expected_dates = [
        datetime.date(1904, 1, 1),
        datetime.date(1908, 1, 1),
        datetime.date(1908, 1, 2),
        datetime.date(2019, 1, 1),
        datetime.date(2020, 1, 1),
        None,
    ]
    assert result_series.to_list() == expected_dates
    assert result_series.dtype == pl.Date


def test_from_excel_serial_invalid_epoch(sample_af):
    """Test that an invalid epoch raises ValueError."""
    proxy = sample_af["serial_1900_int"]
    accessor = DateColumnAccessor(proxy)
    with pytest.raises(
        ValueError, match="Invalid epoch 'invalid'. Must be '1900' or '1904'."
    ):
        accessor.from_excel_serial(epoch="invalid")


def test_from_excel_serial_non_numeric_input(sample_af):
    """Test conversion with non-numeric input (should result in nulls)."""
    proxy = sample_af["not_numeric"]
    accessor = DateColumnAccessor(proxy)
    result_proxy = accessor.from_excel_serial()

    assert isinstance(result_proxy, ExpressionProxy)

    sample_af["result"] = result_proxy
    result_series = sample_af.collect()["result"]

    # Casting non-numeric to Float64(strict=False) should produce nulls
    expected_dates = [None] * len(sample_af.collect())  # Check length dynamically
    assert result_series.to_list() == expected_dates
    assert result_series.dtype == pl.Date
