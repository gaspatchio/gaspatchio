# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

# Assuming ActuarialFrame and ExpressionProxy are part of the public API
from gaspatchio_core import ActuarialFrame, ExpressionProxy
from gaspatchio_core.polars_backend.plugins import _get_lib


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


# Patch the register_plugin_function within the plugins module's scope.
# The wrappers were relocated to polars_backend.plugins in Task 3.2;
# functions/vector.py is now a re-export shim, so the patch target must
# follow the implementation.
@patch("gaspatchio_core.polars_backend.plugins.register_plugin_function")
def test_frame_fill_series(mock_register_plugin: MagicMock, mock_frame: ActuarialFrame):
    """Test ActuarialFrame.fill_series method by mocking register_plugin_function."""
    # Configure the mock register_plugin_function to return a predictable pl.Expr
    expected_expr = pl.lit("mocked_fill_series_result")
    mock_register_plugin.return_value = expected_expr

    # Call the method on the ActuarialFrame (which should call the wrapper in vector.py)
    result_proxy = mock_frame.fill_series("col_a", start=1, increment=2)

    # Assert register_plugin_function was called once
    mock_register_plugin.assert_called_once()
    call_args, call_kwargs = mock_register_plugin.call_args

    # Check the keyword arguments passed to register_plugin_function
    assert call_kwargs["plugin_path"] == _get_lib()
    assert call_kwargs["function_name"] == "fill_series"
    assert call_kwargs["is_elementwise"] is True
    assert call_kwargs["kwargs"] == {"start": 1, "increment": 2}

    # Check the positional arguments (the expression list)
    assert len(call_kwargs["args"]) == 1
    # Compare string representation or type, avoid direct pl.Expr == pl.Expr
    assert str(call_kwargs["args"][0]) == str(pl.col("col_a"))

    # Assert the result is an ExpressionProxy containing the expected expression
    assert isinstance(result_proxy, ExpressionProxy)
    assert str(result_proxy._expr) == str(expected_expr)
    assert result_proxy._parent is mock_frame
