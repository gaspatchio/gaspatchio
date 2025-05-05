from unittest.mock import MagicMock, patch

import polars as pl
import pytest

# Import the functions and classes to be tested
from gaspatchio_core.errors.formatting_errors import (
    _extract_missing_column_robust,
    _find_similar_columns,
    _format_column_error,
    _handle_execution_error,  # If PerformanceWarning needs testing, import it too
)


# Mock the ActuarialFrame class minimally for type hinting and instantiation
# We will mock its attributes (_df, _column_order, _verbose) directly in tests
class MockActuarialFrame:
    def __init__(self):
        self._df = MagicMock(spec=pl.LazyFrame)
        self._column_order = []
        self._verbose = False
        # Add other attributes if needed by the tested functions


# --- Test _extract_missing_column_robust ---


@pytest.mark.parametrize(
    "error_str, expected_col",
    [
        (
            "invalid_start\\n\\nResolved plan:\\nWITH COLUMNS...",
            "invalid_start",
        ),  # Pattern 1
        (
            'Error: column "missing_col" not found\\nSome other info',
            "missing_col",
        ),  # Pattern 3
        (
            'Computation error: unable to find column \\"another_col\\" in schema...',
            "another_col",
        ),  # Pattern 3 variation
        (
            "ColumnNotFoundError: my_column\\nDetails...",
            "my_column",
        ),  # Pattern 4
        (
            "Error: column 'fancy-col' not found",
            "fancy-col",
        ),  # Pattern 2
        ("Some generic error without column name", None),  # No match
        (
            "\\nError starting with newline",
            None,
        ),  # No match (Pattern 1 needs name first)
        ("ColumnNotFoundError: ", None),  # Pattern 4 needs name
    ],
)
def test_extract_missing_column_robust(error_str, expected_col):
    assert _extract_missing_column_robust(error_str) == expected_col


# --- Test _find_similar_columns ---


@pytest.mark.parametrize(
    "missing, available, expected",
    [
        (
            "policy_term",
            ["policy_id", "policy_amount", "pol_term", "term"],
            ["pol_term"],  # Assuming score_cutoff=60 makes pol_term the only match
        ),
        (
            "start_date",
            ["end_date", "start_dt", "commencement_date", "date_start"],
            ["start_dt", "date_start"],  # Expecting multiple good matches
        ),
        ("non_existent", ["col_a", "col_b"], []),  # No similar columns
        ("col_a", ["col_a", "col_b"], ["col_a"]),  # Exact match
        (
            "amount",
            ["total_amount", "amt", "Amount", "principle_amount"],
            ["Amount", "amt", "total_amount"],  # Case insensitive and substring
        ),
        ("a", ["b", "c", "d"], []),  # Too dissimilar
        ("col", ["column1", "column2", "col3"], ["col3"]),  # Prefix match
        ("missing", [], []),  # No available columns
        ("", ["a", "b"], []),  # Empty missing column
    ],
)
def test_find_similar_columns(missing, available, expected):
    # Sort expected results for consistent comparison
    assert sorted(_find_similar_columns(missing, available)) == sorted(expected)


# --- Test _format_column_error ---


def test_format_column_error_with_suggestions():
    mock_frame = MockActuarialFrame()
    mock_frame._df.columns = ["policy_id", "pol_term", "amount"]
    mock_frame._column_order = mock_frame._df.columns  # Keep consistent

    original_exc = pl.ColumnNotFoundError("Original Polars message about polcy_term")
    missing_col = "polcy_term"

    formatted_exc = _format_column_error(
        mock_frame, original_exc, missing_col, str(original_exc)
    )

    assert isinstance(formatted_exc, pl.ColumnNotFoundError)
    error_msg = str(formatted_exc)

    assert f"Column '{missing_col}' not found" in error_msg
    assert "Did you mean one of these?" in error_msg
    assert "- pol_term" in error_msg  # Expecting suggestion
    assert "Available columns are:" in error_msg
    assert "- policy_id" in error_msg
    assert "- pol_term" in error_msg
    assert "- amount" in error_msg
    assert f"Original Polars Error: {str(original_exc)}" in error_msg


def test_format_column_error_no_suggestions():
    mock_frame = MockActuarialFrame()
    mock_frame._df.columns = ["col_a", "col_b"]
    mock_frame._column_order = mock_frame._df.columns

    original_exc = ValueError("Some other error")
    missing_col = "non_existent_col"

    formatted_exc = _format_column_error(
        mock_frame, original_exc, missing_col, str(original_exc)
    )

    assert isinstance(formatted_exc, ValueError)  # Preserves original type
    error_msg = str(formatted_exc)

    assert f"Column '{missing_col}' not found" in error_msg
    assert "Did you mean one of these?" not in error_msg
    assert "Available columns are:" in error_msg
    assert "- col_a" in error_msg
    assert "- col_b" in error_msg
    assert f"Original Polars Error: {str(original_exc)}" in error_msg


# --- Test _handle_execution_error ---


def test_handle_execution_error_raises_formatted_error():
    mock_frame = MockActuarialFrame()
    mock_frame._df.columns = ["policy_id", "pol_term"]
    mock_frame._column_order = [
        "policy_id",
        "pol_term",
        "polcy_term",
    ]  # Simulate assigned but missing
    mock_frame._verbose = False

    # Simulate a Polars error where the missing column name is extractable
    original_exc = pl.ColumnNotFoundError(
        "polcy_term\\n\\nContext: error during aggregation..."
    )

    with pytest.raises(pl.ColumnNotFoundError) as exc_info:
        _handle_execution_error(mock_frame, original_exc)

    # Check that the raised exception is the formatted one
    error_msg = str(exc_info.value)
    assert "Column 'polcy_term' not found" in error_msg
    assert "Did you mean one of these?" in error_msg
    assert "- pol_term" in error_msg
    assert "Original Polars Error:" in error_msg


def test_handle_execution_error_pattern5_fallback():
    mock_frame = MockActuarialFrame()
    mock_frame._df.columns = ["policy_id", "amount"]
    # Simulate a column was assigned ('interest_rate') but not in the final df columns
    mock_frame._column_order = ["policy_id", "amount", "interest_rate"]
    mock_frame._verbose = False

    # Simulate an error message that *contains* the missing column name but not in standard patterns
    original_exc = Exception(
        "Generic computation error involving interest_rate column."
    )

    with pytest.raises(Exception) as exc_info:
        _handle_execution_error(mock_frame, original_exc)

    # Check that pattern 5 worked and formatted the error
    error_msg = str(exc_info.value)
    assert "Column 'interest_rate' not found" in error_msg
    assert (
        "Did you mean one of these?" not in error_msg
    )  # No similar columns found likely
    assert "Available columns are:" in error_msg
    assert "- policy_id" in error_msg
    assert "- amount" in error_msg
    assert "Original Polars Error:" in error_msg


def test_handle_execution_error_raises_original_error_if_no_column_found():
    mock_frame = MockActuarialFrame()
    mock_frame._df.columns = ["a", "b"]
    mock_frame._column_order = ["a", "b"]
    mock_frame._verbose = False

    # Simulate an error where the missing column cannot be extracted
    original_exc = TypeError("An unrelated type error during execution")

    with pytest.raises(
        TypeError, match="An unrelated type error during execution"
    ) as exc_info:
        _handle_execution_error(mock_frame, original_exc)

    # Ensure the original exception is re-raised
    assert exc_info.value is original_exc


@patch("gaspatchio_core.errors.formatting_errors.log")  # Patch the logger
def test_handle_execution_error_logs_when_verbose(mock_log):
    mock_frame = MockActuarialFrame()
    mock_frame._df.columns = ["a", "b"]
    mock_frame._column_order = ["a", "b"]
    mock_frame._verbose = True  # Enable verbose logging

    # Test case 1: Formatted error is raised
    original_exc_formatted = pl.ColumnNotFoundError("missing_col\\nError")
    with pytest.raises(pl.ColumnNotFoundError):
        _handle_execution_error(mock_frame, original_exc_formatted)
    # Check log.error was called with a message containing the formatted error info
    assert mock_log.error.call_count == 1
    log_arg = mock_log.error.call_args[0][0]  # Get the first arg passed to log.error
    assert "Execution failed: Column 'missing_col' not found" in log_arg

    mock_log.error.reset_mock()  # Reset mock for next case

    # Test case 2: Original error is raised
    original_exc_unformatted = TypeError("Unrelated error")
    with pytest.raises(TypeError):
        _handle_execution_error(mock_frame, original_exc_unformatted)
    # Check log.error was called with the original unformatted error message
    assert mock_log.error.call_count == 1
    log_arg = mock_log.error.call_args[0][0]
    assert "Execution failed: Unrelated error" in log_arg
