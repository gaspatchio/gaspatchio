# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the FriendlyErrorFormatter class and related functionality."""

import time
from dataclasses import dataclass

import polars as pl
import pytest

# Import the new FriendlyErrorFormatter
from gaspatchio_core.errors.formatter import FriendlyErrorFormatter

# For backward compatibility, also test the existing functions
from gaspatchio_core.errors.formatting_errors import (
    _extract_missing_column_robust,
    _find_similar_columns,
)


# Mock TracedOperation and OperationMetadata for testing
@dataclass
class MockOperationMetadata:
    file_name: str
    line_number: int
    source_line: str
    function_name: str | None = None
    timestamp: float | None = None


@dataclass
class MockTracedOperation:
    alias: str
    expression: str  # Simplified for testing
    metadata: MockOperationMetadata


# --- Test FriendlyErrorFormatter ---


class TestFriendlyErrorFormatter:
    """Test the main FriendlyErrorFormatter class."""

    def test_format_error_basic(self):
        """Test basic error formatting without suggestions."""
        # Create mock operation
        metadata = MockOperationMetadata(
            file_name="model_calculation.py",
            line_number=27,
            source_line='af["premium_total"] = af["premium"] * 12',
            function_name="calculate_premiums",
        )
        operation = MockTracedOperation(
            alias="premium_total",
            expression="col('premium') * 12",
            metadata=metadata,
        )

        # Create test exception
        exception = ValueError("Test error message")

        # Create test DataFrame
        test_df = pl.DataFrame(
            {
                "policy_id": [1, 2],
                "premium": [100.0, 150.0],
            },
        )

        # Create formatter
        formatter = FriendlyErrorFormatter(
            operation=operation,
            exception=exception,
            last_good_df=test_df,
        )

        # Test format_error
        error_msg = formatter.format_error()

        assert "❌ Calculation Error" in error_msg
        assert "📍 Location: model_calculation.py:27" in error_msg
        assert 'af["premium_total"] = af["premium"] * 12' in error_msg
        assert "Type: ValueError" in error_msg
        assert "Message: Test error message" in error_msg
        assert "📊 Calculation State Before Error:" in error_msg
        assert "policy_id" in error_msg
        assert "premium" in error_msg

    def test_format_error_with_suggestions(self):
        """Test error formatting with suggestions."""
        metadata = MockOperationMetadata(
            file_name="test.py",
            line_number=1,
            source_line="test_line",
        )
        operation = MockTracedOperation(
            alias="test_col",
            expression="col('test')",
            metadata=metadata,
        )

        exception = pl.exceptions.ColumnNotFoundError("Column not found")
        test_df = pl.DataFrame({"col1": [1], "col2": [2]})
        suggestions = ["Check column name", "Use .columns to see available columns"]

        formatter = FriendlyErrorFormatter(
            operation=operation,
            exception=exception,
            last_good_df=test_df,
            suggestions=suggestions,
        )

        error_msg = formatter.format_error()

        assert "💡 Suggestions:" in error_msg
        assert "• Check column name" in error_msg
        assert "• Use .columns to see available columns" in error_msg

    def test_format_for_llm(self):
        """Test LLM-friendly JSON format."""
        metadata = MockOperationMetadata(
            file_name="model.py",
            line_number=42,
            source_line="af['result'] = af['input'] * 2",
            function_name="process_data",
            timestamp=time.time(),
        )
        operation = MockTracedOperation(
            alias="result",
            expression="col('input') * 2",
            metadata=metadata,
        )

        exception = RuntimeError("Division by zero")
        test_df = pl.DataFrame({"input": [1, 2, 0]})
        suggestions = ["Handle zero values", "Add null checks"]

        formatter = FriendlyErrorFormatter(
            operation=operation,
            exception=exception,
            last_good_df=test_df,
            suggestions=suggestions,
        )

        llm_format = formatter.format_for_llm()

        # Check structure
        assert "error_location" in llm_format
        assert "error_details" in llm_format
        assert "suggestions" in llm_format
        assert "context" in llm_format

        # Check error_location
        assert llm_format["error_location"]["file"] == "model.py"
        assert llm_format["error_location"]["line"] == 42
        assert llm_format["error_location"]["code"] == "af['result'] = af['input'] * 2"
        assert llm_format["error_location"]["function"] == "process_data"

        # Check error_details
        assert llm_format["error_details"]["type"] == "RuntimeError"
        assert llm_format["error_details"]["message"] == "Division by zero"
        assert llm_format["error_details"]["column_alias"] == "result"
        assert llm_format["error_details"]["expression"] == "col('input') * 2"

        # Check suggestions
        assert llm_format["suggestions"] == ["Handle zero values", "Add null checks"]

        # Check context
        assert llm_format["context"]["available_columns"] == ["input"]
        assert llm_format["context"]["dataframe_shape"] == [3, 1]

    def test_format_dataframe_preview(self):
        """Test DataFrame preview formatting."""
        metadata = MockOperationMetadata("test.py", 1, "test")
        operation = MockTracedOperation("test", "test", metadata)

        # Create test DataFrame with multiple rows
        test_df = pl.DataFrame(
            {
                "id": list(range(10)),
                "value": [f"item_{i}" for i in range(10)],
            },
        )

        formatter = FriendlyErrorFormatter(
            operation=operation,
            exception=Exception("test"),
            last_good_df=test_df,
        )

        preview = formatter._format_dataframe_preview(test_df, max_rows=3)

        # Should be indented
        lines = preview.split("\n")
        assert all(line.startswith("  ") for line in lines if line.strip())

        # Should contain truncation notice
        assert "... (7 more rows)" in preview

    def test_truncate_wide_tables(self):
        """Test wide table truncation."""
        metadata = MockOperationMetadata("test.py", 1, "test")
        operation = MockTracedOperation("test", "test", metadata)

        # Create wide DataFrame
        wide_df = pl.DataFrame({f"col_{i}": [1, 2, 3] for i in range(15)})

        formatter = FriendlyErrorFormatter(
            operation=operation,
            exception=Exception("test"),
            last_good_df=wide_df,
        )

        truncated = formatter._truncate_wide_tables(wide_df)

        # Should have been truncated to 9 columns (4 + 1 ellipsis + 4)
        assert len(truncated.columns) == 9
        assert "..." in truncated.columns

        # Should have first 4 and last 4 original columns
        original_cols = wide_df.columns
        truncated_cols = truncated.columns

        assert all(col in truncated_cols for col in original_cols[:4])
        assert all(col in truncated_cols for col in original_cols[-4:])

    def test_with_lazy_dataframe(self):
        """Test formatter works with LazyFrame."""
        metadata = MockOperationMetadata("test.py", 1, "test")
        operation = MockTracedOperation("test", "test", metadata)

        # Create LazyFrame
        lazy_df = pl.LazyFrame(
            {
                "a": [1, 2, 3, 4, 5],
                "b": ["x", "y", "z", "w", "v"],
            },
        )

        formatter = FriendlyErrorFormatter(
            operation=operation,
            exception=Exception("test"),
            last_good_df=lazy_df,
        )

        # Should handle LazyFrame without error
        error_msg = formatter.format_error()
        assert "📊 Calculation State Before Error:" in error_msg

        # LLM format should work with LazyFrame
        llm_format = formatter.format_for_llm()
        assert "available_columns" in llm_format["context"]
        assert "dataframe_shape" in llm_format["context"]

        # For LazyFrame, shape should be ["unknown", num_columns]
        assert llm_format["context"]["dataframe_shape"] == ["unknown", 2]
        assert llm_format["context"]["available_columns"] == ["a", "b"]


# --- Test legacy helper functions for backward compatibility ---


@pytest.mark.parametrize(
    "error_str, expected_col",
    [
        (
            "invalid_start\n\nResolved plan:\nWITH COLUMNS...",
            "invalid_start",
        ),
        (
            'Computation error: unable to find column "another_col" in schema...',
            "another_col",
        ),
        (
            "ColumnNotFoundError: my_column\nDetails...",
            "my_column",
        ),
        (
            "Error: column 'fancy-col' not found",
            "fancy-col",
        ),
        ("Some generic error without column name", None),
        ("\nError starting with newline", None),
        ("ColumnNotFoundError: ", None),
    ],
)
def test_extract_missing_column_robust(error_str, expected_col):
    """Test column name extraction from error messages."""
    assert _extract_missing_column_robust(error_str) == expected_col


@pytest.mark.parametrize(
    "missing, available, expected",
    [
        (
            "policy_term",
            ["policy_id", "policy_amount", "pol_term", "term"],
            ["term"],
        ),
        (
            "start_date",
            ["end_date", "start_dt", "commencement_date", "date_start"],
            ["commencement_date", "date_start", "start_dt"],
        ),
        (
            "non_existent",
            ["col_a", "col_b"],
            [],
        ),
        (
            "col_a",
            ["col_a", "col_b"],
            ["col_a"],
        ),
        (
            "amount",
            ["total_amount", "amt", "Amount", "principle_amount"],
            ["Amount", "total_amount", "principle_amount"],
        ),
        ("a", ["b", "c", "d"], []),
        (
            "col",
            ["column1", "column2", "col3"],
            ["col3", "column1", "column2"],
        ),
        ("missing", [], []),
        ("", ["a", "b"], []),
    ],
)
def test_find_similar_columns(missing, available, expected):
    """Test column similarity detection."""
    actual = _find_similar_columns(missing, available)
    assert sorted(actual) == sorted(expected)
