"""Integration tests for accessor properties and delegation."""

import datetime

import polars as pl
import pytest
from gaspatchio_core.dsl.accessors.date import DateColumnAccessor, DateFrameAccessor
from gaspatchio_core.dsl.core import ActuarialFrame, ColumnProxy, ExpressionProxy
from polars.testing import assert_frame_equal


@pytest.fixture
def integration_af() -> ActuarialFrame:
    """Provides a sample ActuarialFrame for integration testing."""
    data = {
        "excel_date": [44927, 45000, None],  # 2023-01-01, 2023-03-15
        "string_col": ["abc", "def", "ghi"],
        "numeric_col": [10, -20, 30],
        "date_col": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 2, 1),
            None,
        ],
    }
    return ActuarialFrame(data)


def test_date_accessor_type_on_column(integration_af):
    """Verify accessing .date on a ColumnProxy returns DateColumnAccessor."""
    proxy = integration_af["excel_date"]
    assert isinstance(proxy, ColumnProxy)
    assert isinstance(proxy.date, DateColumnAccessor)
    assert proxy.date._proxy is proxy  # Check it's bound correctly


def test_date_accessor_type_on_expression(integration_af):
    """Verify accessing .date on an ExpressionProxy returns DateColumnAccessor."""
    proxy = integration_af["numeric_col"] + 5
    assert isinstance(proxy, ExpressionProxy)
    assert isinstance(proxy.date, DateColumnAccessor)
    assert proxy.date._proxy is proxy  # Check it's bound correctly


def test_date_accessor_method_call(integration_af):
    """Verify calling a method via the integrated .date accessor works."""
    integration_af["converted_date"] = integration_af[
        "excel_date"
    ].date.from_excel_serial()

    expected = pl.LazyFrame(
        {
            "excel_date": [44927, 45000, None],
            "string_col": ["abc", "def", "ghi"],
            "numeric_col": [10, -20, 30],
            "date_col": [
                datetime.date(2024, 1, 1),
                datetime.date(2024, 2, 1),
                None,
            ],
            "converted_date": [
                datetime.date(2023, 1, 1),
                datetime.date(2023, 3, 15),
                None,
            ],
        }
    ).select(integration_af._df.columns)  # Ensure same column order

    # Cast date_col explicitly if needed, depending on Polars inference
    expected = expected.with_columns(pl.col("date_col").cast(pl.Date))

    assert_frame_equal(integration_af.collect(), expected.collect())
    # Also check the return type of the method call itself
    result_proxy = integration_af["excel_date"].date.from_excel_serial()
    assert isinstance(result_proxy, ExpressionProxy)


def test_date_frame_accessor_property(integration_af: ActuarialFrame):
    """Verify the af.date property returns the correct accessor type."""
    assert hasattr(integration_af, "date")
    accessor = integration_af.date
    assert isinstance(accessor, DateFrameAccessor)
    assert accessor._frame is integration_af  # Check it's bound correctly


def test_date_frame_accessor_method_call(integration_af: ActuarialFrame):
    """Verify calling a method via the frame accessor works."""
    # Call the placeholder method
    new_af = integration_af.date.create_timeline(
        "date_col", "date_col"
    )  # Use valid cols

    assert isinstance(new_af, ActuarialFrame)
    # Verify it's a new instance
    assert id(new_af) != id(integration_af)


def test_dir_on_actuarial_frame(integration_af: ActuarialFrame):
    """Verify dir() on ActuarialFrame includes columns and accessors."""
    dir_result = dir(integration_af)

    # Check for core methods/properties
    assert "collect" in dir_result
    assert "profile" in dir_result
    assert "with_columns" in dir_result
    assert "date" in dir_result  # Check our custom accessor

    # Check for column names
    assert "excel_date" in dir_result
    assert "string_col" in dir_result
    assert "numeric_col" in dir_result
    assert "date_col" in dir_result


def test_dir_on_column_proxy(integration_af: ActuarialFrame):
    """Verify dir() on ColumnProxy includes standard methods and accessors."""
    proxy = integration_af["date_col"]
    dir_result = dir(proxy)

    # Check for our custom accessor
    assert "date" in dir_result

    # Check for delegated Polars methods/namespaces
    assert "dt" in dir_result  # Delegated namespace
    assert "year" not in dir_result  # Methods within namespace shouldn't be top-level
    assert "is_null" in dir_result  # Delegated method
    assert "alias" in dir_result  # Delegated method


def test_dir_on_expression_proxy(integration_af: ActuarialFrame):
    """Verify dir() on ExpressionProxy includes standard methods and accessors."""
    proxy = integration_af["numeric_col"] + 5
    dir_result = dir(proxy)

    # Check for our custom accessor
    assert "date" in dir_result

    # Check for delegated Polars methods/namespaces
    assert "abs" in dir_result  # Delegated method
    assert "cast" in dir_result  # Delegated method
    assert "alias" in dir_result  # Delegated method
    assert "dt" in dir_result
    assert "str" in dir_result


def test_standard_polars_delegation_still_works(integration_af):
    """Verify non-accessor methods/namespaces are still delegated."""
    # Test a non-namespace method
    integration_af["is_null"] = integration_af["excel_date"].is_null()
    # Test a Polars namespace method (.dt)
    integration_af["date_year"] = integration_af["date_col"].dt.year()
    # Test another Polars namespace method (.str)
    integration_af["str_contains"] = integration_af["string_col"].str.contains("a")

    expected_data = {
        "excel_date": [44927, 45000, None],
        "string_col": ["abc", "def", "ghi"],
        "numeric_col": [10, -20, 30],
        "date_col": [
            datetime.date(2024, 1, 1),
            datetime.date(2024, 2, 1),
            None,
        ],
        "is_null": [False, False, True],
        "date_year": [2024, 2024, None],
        "str_contains": [True, False, False],  # 'a' in 'abc', not in 'def' or 'ghi'
    }
    expected_lf = pl.LazyFrame(expected_data).select(
        integration_af._df.columns
    )  # Ensure order

    # Explicit casts in expected frame for comparison safety
    expected_lf = expected_lf.with_columns(
        pl.col("date_col").cast(pl.Date),
        pl.col("date_year").cast(pl.Int32),  # Polars year() returns Int32
        pl.col("is_null").cast(pl.Boolean),
        pl.col("str_contains").cast(pl.Boolean),
    )

    assert_frame_equal(integration_af.collect(), expected_lf.collect())
