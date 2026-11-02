# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the FriendlyErrorFormatter class and related functionality."""

import polars as pl
import pytest

from gaspatchio._semantic.ir import Col

# Import the new FriendlyErrorFormatter
from gaspatchio.errors.formatter import (
    AttributeErrorFormatter,
    FriendlyErrorFormatter,
    ValidationErrorFormatter,
)

# For backward compatibility, also test the existing functions
from gaspatchio.errors.formatting_errors import (
    _extract_missing_column_robust,
    _find_similar_columns,
)
from gaspatchio.errors.models import SourceLocation
from gaspatchio.errors.validation import ValidationError
from gaspatchio.frame.calculations import CalculationRecord, SourceSpan


def _calculation(
    column: str,
    expression: object,
    source: SourceSpan | None,
) -> CalculationRecord:
    """Build one recorded calculation, as the frame's log would hold it."""
    return CalculationRecord(
        column=column,
        ordinal=1,
        operation_id=0,
        node=Col(column),
        expr=expression,
        dtype=None,
        source=source,
        origin="assignment",
    )


def _span(
    file: str,
    line: int,
    statement: str,
    function: str | None = None,
) -> SourceSpan:
    """Build the source span capture would have resolved for a statement.

    ``function`` defaults to ``None`` -- the module-level case, where capture
    has no enclosing scope to report.
    """
    return SourceSpan(
        file=file,
        line=line,
        end_line=line,
        function=function,
        statement=statement,
        rhs=None,
        target_literal=True,
    )


# --- Test FriendlyErrorFormatter ---


class TestFriendlyErrorFormatter:
    """Test the main FriendlyErrorFormatter class."""

    def test_format_error_basic(self):
        """Test basic error formatting without suggestions."""
        record = _calculation(
            "premium_total",
            "col('premium') * 12",
            _span(
                "model_calculation.py",
                27,
                'af["premium_total"] = af["premium"] * 12',
            ),
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
            record=record,
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

    def test_format_error_names_the_function_the_calculation_was_written_in(self):
        """A span that knows its enclosing scope reports it under the location."""
        record = _calculation(
            "premium_total",
            "col('premium') * 12",
            _span(
                "model_calculation.py",
                27,
                'af["premium_total"] = af["premium"] * 12',
                function="build_cashflows",
            ),
        )

        error_msg = FriendlyErrorFormatter(
            record=record,
            exception=ValueError("Test error message"),
            last_good_df=pl.DataFrame({"premium": [100.0]}),
        ).format_error()

        assert "   Function: build_cashflows" in error_msg

    def test_format_error_omits_the_function_line_at_module_level(self):
        """No enclosing scope means no line, not a "module level" claim."""
        record = _calculation(
            "premium_total",
            "col('premium') * 12",
            _span(
                "model_calculation.py",
                27,
                'af["premium_total"] = af["premium"] * 12',
            ),
        )

        error_msg = FriendlyErrorFormatter(
            record=record,
            exception=ValueError("Test error message"),
            last_good_df=pl.DataFrame({"premium": [100.0]}),
        ).format_error()

        assert "Function:" not in error_msg
        assert "module level" not in error_msg

    def test_format_error_omits_the_function_line_when_no_span_resolved(self):
        """A calculation with no span at all reports no scope either."""
        record = _calculation("premium_total", "col('premium') * 12", None)

        error_msg = FriendlyErrorFormatter(
            record=record,
            exception=ValueError("Test error message"),
            last_good_df=pl.DataFrame({"premium": [100.0]}),
        ).format_error()

        assert "Function:" not in error_msg

    def test_format_error_with_suggestions(self):
        """Test error formatting with suggestions."""
        record = _calculation(
            "annual_premium",
            "col('test')",
            _span("test.py", 1, "af.annual_premium = af.premium * 12"),
        )

        exception = pl.exceptions.ColumnNotFoundError("Column not found")
        test_df = pl.DataFrame({"col1": [1], "col2": [2]})
        suggestions = ["Check column name", "Use .columns to see available columns"]

        formatter = FriendlyErrorFormatter(
            record=record,
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
        record = _calculation(
            "result",
            "col('input') * 2",
            _span("model.py", 42, "af['result'] = af['input'] * 2"),
        )

        exception = RuntimeError("Division by zero")
        test_df = pl.DataFrame({"input": [1, 2, 0]})
        suggestions = ["Handle zero values", "Add null checks"]

        formatter = FriendlyErrorFormatter(
            record=record,
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
        assert llm_format["error_location"]["function"] is None
        assert llm_format["error_location"]["code"] == "af['result'] = af['input'] * 2"

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

    def test_format_for_llm_carries_the_function_scope(self):
        """The LLM payload names the enclosing scope whenever capture knew it."""
        record = _calculation(
            "result",
            "col('input') * 2",
            _span(
                "model.py",
                42,
                "af['result'] = af['input'] * 2",
                function="project_reserves",
            ),
        )

        llm_format = FriendlyErrorFormatter(
            record=record,
            exception=RuntimeError("Division by zero"),
            last_good_df=pl.DataFrame({"input": [1]}),
        ).format_for_llm()

        assert llm_format["error_location"]["function"] == "project_reserves"

    def test_format_dataframe_preview(self):
        """Test DataFrame preview formatting."""
        record = _calculation("reserves", "test", _span("test.py", 1, "test"))

        # Create test DataFrame with multiple rows
        test_df = pl.DataFrame(
            {
                "id": list(range(10)),
                "value": [f"item_{i}" for i in range(10)],
            },
        )

        formatter = FriendlyErrorFormatter(
            record=record,
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
        record = _calculation("reserves", "test", _span("test.py", 1, "test"))

        # Create wide DataFrame
        wide_df = pl.DataFrame({f"col_{i}": [1, 2, 3] for i in range(15)})

        formatter = FriendlyErrorFormatter(
            record=record,
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
        record = _calculation("reserves", "test", _span("test.py", 1, "test"))

        # Create LazyFrame
        lazy_df = pl.LazyFrame(
            {
                "a": [1, 2, 3, 4, 5],
                "b": ["x", "y", "z", "w", "v"],
            },
        )

        formatter = FriendlyErrorFormatter(
            record=record,
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


# --- Test ValidationErrorFormatter ---


class TestValidationErrorFormatter:
    """Test the ValidationErrorFormatter class."""

    def _rendered(self, function_name: str | None) -> str:
        """Render a validation error whose location names ``function_name``."""
        error = ValidationError("Invalid option: 'bogus'")
        error.source_location = SourceLocation(
            file_path="model_calculation.py",
            line_number=42,
            function_name=function_name,
            source_line="af.foo = bar.lookup(option='bogus')",
        )
        return ValidationErrorFormatter(error).format_error()

    def test_omits_the_function_line_at_module_level(self):
        """No enclosing scope means no line, not a "module level" claim."""
        message = self._rendered(None)

        assert "Function:" not in message
        assert "<module>" not in message
        assert "module level" not in message

    def test_names_the_function_the_error_was_raised_in(self):
        """A location that knows its enclosing scope reports it."""
        message = self._rendered("validate_lookup_key")

        assert "Function: validate_lookup_key" in message


# --- Test AttributeErrorFormatter ---


class TestAttributeErrorFormatter:
    """Test the AttributeErrorFormatter class."""

    def _rendered(self, function_name: str | None) -> str:
        """Render an attribute error whose location names ``function_name``."""
        location = SourceLocation(
            file_path="model_calculation.py",
            line_number=17,
            function_name=function_name,
            source_line="af.foo = bar.split(',')",
        )
        error = AttributeError("'NoneType' object has no attribute 'split'")
        return AttributeErrorFormatter(error, source_location=location).format_error()

    def test_omits_the_function_line_at_module_level(self):
        """No enclosing scope means no line, not a "module level" claim."""
        message = self._rendered(None)

        assert "Function:" not in message
        assert "<module>" not in message
        assert "module level" not in message

    def test_names_the_function_the_error_was_raised_in(self):
        """A location that knows its enclosing scope reports it."""
        message = self._rendered("compute_reserve")

        assert "Function: compute_reserve" in message


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
