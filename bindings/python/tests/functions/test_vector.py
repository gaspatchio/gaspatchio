from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

# Assuming ActuarialFrame and ExpressionProxy are part of the public API
from gaspatchio_core import ActuarialFrame, ExpressionProxy


@pytest.fixture
def mock_frame() -> ActuarialFrame:
    """Create a mock ActuarialFrame for testing."""
    # Mock the underlying Polars LazyFrame and core functions if needed
    mock_lf = MagicMock(spec=pl.LazyFrame)
    mock_lf.schema = {"col_a": pl.Int64, "col_b": pl.Float64}
    mock_lf.columns = ["col_a", "col_b"]

    frame = ActuarialFrame(mock_lf)

    # Mock the _convert_to_expr to return a basic pl.col or pl.lit
    def simple_convert(val):
        if isinstance(val, (str, ExpressionProxy)):
            # Assume val.name or str(val) gives column name
            name = getattr(val, "name", str(val))
            return pl.col(name)
        return pl.lit(val)

    frame._convert_to_expr = MagicMock(side_effect=simple_convert)
    return frame


# Patch the actual Rust function imports within the functions.vector module
@patch("gaspatchio_core.functions.vector.core_fill_series")
def test_frame_fill_series(
    mock_core_fill_series: MagicMock, mock_frame: ActuarialFrame
):
    """Test ActuarialFrame.fill_series method."""
    # Configure the mock core function to return a predictable pl.Expr
    expected_expr = pl.lit("mocked_fill_series_result")
    mock_core_fill_series.return_value = expected_expr

    result_proxy = mock_frame.fill_series("col_a", limit=5)

    # Assert the core function was called correctly
    mock_core_fill_series.assert_called_once_with(pl.col("col_a"), limit=5)

    # Assert the result is an ExpressionProxy containing the expected expression
    assert isinstance(result_proxy, ExpressionProxy)
    assert result_proxy._expr == expected_expr
    assert result_proxy._parent is mock_frame


@patch("gaspatchio_core.functions.vector.core_floor")
def test_frame_floor(mock_core_floor: MagicMock, mock_frame: ActuarialFrame):
    """Test ActuarialFrame.floor method."""
    expected_expr = pl.lit("mocked_floor_result")
    mock_core_floor.return_value = expected_expr

    result_proxy = mock_frame.floor("col_b", divisor=10.0)

    mock_core_floor.assert_called_once_with(pl.col("col_b"), divisor=10.0)
    assert isinstance(result_proxy, ExpressionProxy)
    assert result_proxy._expr == expected_expr


@patch("gaspatchio_core.functions.vector.core_round")
def test_frame_round(mock_core_round: MagicMock, mock_frame: ActuarialFrame):
    """Test ActuarialFrame.round method."""
    expected_expr = pl.lit("mocked_round_result")
    mock_core_round.return_value = expected_expr

    result_proxy = mock_frame.round("col_b", decimals=2)

    mock_core_round.assert_called_once_with(pl.col("col_b"), decimals=2)
    assert isinstance(result_proxy, ExpressionProxy)
    assert result_proxy._expr == expected_expr


@patch("gaspatchio_core.functions.vector.core_round_to_int")
def test_frame_round_to_int(
    mock_core_round_to_int: MagicMock, mock_frame: ActuarialFrame
):
    """Test ActuarialFrame.round_to_int method."""
    expected_expr = pl.lit("mocked_round_to_int_result")
    mock_core_round_to_int.return_value = expected_expr

    result_proxy = mock_frame.round_to_int("col_b", strategy="floor")

    mock_core_round_to_int.assert_called_once_with(pl.col("col_b"), strategy="floor")
    assert isinstance(result_proxy, ExpressionProxy)
    assert result_proxy._expr == expected_expr
