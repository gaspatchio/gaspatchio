# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Tests for the ErrorSuggestionEngine.

This module tests the error suggestion system's ability to generate helpful
fix suggestions based on error types and context.
"""

from gaspatchio_core.errors.metadata import OperationMetadata, TracedOperation
from gaspatchio_core.errors.suggestions import ErrorSuggestionEngine


class TestErrorSuggestionEngine:
    """Test the ErrorSuggestionEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ErrorSuggestionEngine()
        self.metadata = OperationMetadata(
            file_name="test_model.py",
            line_number=42,
            source_line='af["result"] = af["premium"] * 12',
            function_name="calculate_annual_premium",
        )
        self.available_columns = [
            "policy_id",
            "premium",
            "claims",
            "age",
            "assumption_mortality",
            "assumption_lapse",
            "calc_present_value",
            "date_issued",
        ]

    def _create_operation(self, alias: str = "test_col") -> TracedOperation:
        """Helper to create a TracedOperation for testing."""
        return TracedOperation(
            alias=alias,
            expression="dummy_expr",  # Not used in suggestion logic
            metadata=self.metadata,
        )

    def test_column_not_found_typo_suggestions(self):
        """Test suggestions for column not found with typos."""
        # Test common actuarial typo
        error = Exception("column 'premiun' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert len(suggestions) >= 1
        assert "Did you mean 'premium'? (common actuarial typo)" in suggestions

    def test_column_not_found_similar_name(self):
        """Test suggestions for column not found with similar names."""
        error = Exception("column 'premiums' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should find 'premium' as similar
        assert any("Did you mean 'premium'?" in s for s in suggestions)

    def test_column_not_found_case_sensitivity(self):
        """Test suggestions handle case sensitivity."""
        error = Exception("column 'PREMIUM' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should find 'premium' despite case difference
        assert any("premium" in s.lower() for s in suggestions)

    def test_column_not_found_multiple_similar(self):
        """Test suggestions when multiple similar columns exist."""
        columns_with_similar = self.available_columns + [
            "premium_annual",
            "premium_monthly",
        ]
        error = Exception("column 'premiumz' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(error, operation, columns_with_similar)

        # Should suggest best match and mention others
        assert len(suggestions) >= 2
        assert any("Did you mean" in s for s in suggestions)
        assert any("Other similar columns" in s for s in suggestions)

    def test_column_not_found_id_pattern(self):
        """Test suggestions for missing ID columns."""
        error = Exception("column 'customer_id' does not exist")
        operation = self._create_operation()

        # Use columns without any ID columns
        columns_without_ids = ["premium", "claims", "age", "assumption_mortality"]

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            columns_without_ids,
        )

        # Should suggest joining additional data since no ID columns exist
        assert any("join additional data" in s for s in suggestions)

    def test_column_not_found_calc_pattern(self):
        """Test suggestions for missing calculated columns."""
        error = Exception("column 'calc_something' does not exist")
        operation = self._create_operation()

        # Use columns without any calc columns
        columns_without_calcs = ["premium", "claims", "age", "assumption_mortality"]

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            columns_without_calcs,
        )

        # Should suggest ensuring calculations are defined
        assert any("calculations are defined" in s for s in suggestions)

    def test_type_mismatch_general(self):
        """Test suggestions for general type mismatch errors."""
        error = Exception("could not determine output type")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert "Ensure all expressions have consistent types" in suggestions
        assert "Consider using .cast() to explicitly set types" in suggestions

    def test_type_mismatch_string_numeric(self):
        """Test suggestions for string/numeric type mismatches."""
        error = Exception("cannot convert string to numeric")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any(
            "cast(pl.Float64)" in s or "cast(pl.Int64)" in s for s in suggestions
        )

    def test_type_mismatch_float_int(self):
        """Test suggestions for float/int type mismatches."""
        error = Exception("incompatible dtypes: float and int")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("cast(pl.Float64)" in s for s in suggestions)

    def test_type_mismatch_boolean(self):
        """Test suggestions for boolean type mismatches."""
        error = Exception("boolean type mismatch in condition")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("True/False" in s for s in suggestions)

    def test_type_mismatch_datetime(self):
        """Test suggestions for datetime type mismatches."""
        error = Exception("datetime type mismatch")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any(
            "str.to_datetime()" in s or "cast(pl.Date)" in s for s in suggestions
        )

    def test_schema_mismatch_suggestions(self):
        """Test suggestions for schema mismatch errors."""
        error = Exception("schema mismatch between DataFrames")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        expected_suggestions = [
            "Check that join keys have matching types",
            "Use .cast() to align data types before joining",
            "Verify column names match exactly (case-sensitive)",
            "Use .select() to choose only needed columns before operations",
        ]

        for expected in expected_suggestions:
            assert expected in suggestions

    def test_division_by_zero_suggestions(self):
        """Test suggestions for division by zero errors."""
        error = Exception("division by zero error")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        expected_suggestions = [
            "Check for zero values in denominator before division",
            "Use .filter() to exclude zero values: .filter(pl.col('denominator') != 0)",
            "Handle nulls with .fill_null(1) or similar before division",
            "Consider using .map_elements() for custom division logic",
        ]

        for expected in expected_suggestions:
            assert expected in suggestions

    def test_index_out_of_bounds_suggestions(self):
        """Test suggestions for index out of bounds errors."""
        error = Exception("index out of bounds")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        expected_suggestions = [
            "Check data length before indexing operations",
            "Use .head() or .tail() with explicit limits",
            "Validate row count: use .height to check DataFrame size",
            "Consider using .slice() instead of direct indexing",
        ]

        for expected in expected_suggestions:
            assert expected in suggestions

    def test_date_parsing_suggestions(self):
        """Test suggestions for date parsing errors."""
        error = Exception("could not parse date format")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("date format" in s for s in suggestions)
        assert any("str.to_datetime()" in s for s in suggestions)

    def test_date_parsing_format_specific(self):
        """Test suggestions for specific date format errors."""
        error = Exception("date format does not match pattern")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("'%Y-%m-%d'" in s for s in suggestions)
        assert any("'%m/%d/%Y'" in s for s in suggestions)

    def test_date_parsing_excel(self):
        """Test suggestions for Excel date errors."""
        error = Exception("Excel date conversion error")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("Excel serial dates" in s for s in suggestions)

    def test_null_value_suggestions(self):
        """Test suggestions for null value errors."""
        error = Exception("null value encountered")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        expected_suggestions = [
            "Handle null values with .fill_null(value) or .drop_nulls()",
            "Check for missing data before calculations",
            "Use .is_null() to identify null values",
            "Consider default values for actuarial calculations",
        ]

        for expected in expected_suggestions:
            assert expected in suggestions

    def test_file_error_csv(self):
        """Test suggestions for CSV file errors."""
        error = Exception("csv file not found")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("file path is correct" in s for s in suggestions)
        assert any("CSV files: verify column names" in s for s in suggestions)

    def test_file_error_parquet(self):
        """Test suggestions for Parquet file errors."""
        error = Exception("parquet file error")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any(
            "Parquet files: check schema compatibility" in s for s in suggestions
        )

    def test_file_error_excel(self):
        """Test suggestions for Excel file errors."""
        error = Exception("excel file cannot be read")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("Excel files: specify sheet name" in s for s in suggestions)

    def test_assumption_lookup_suggestions(self):
        """Test suggestions for assumption lookup errors."""
        error = Exception("assumption key not found")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        assert any("assumption key matches exactly" in s for s in suggestions)
        assert any("assumption table is loaded" in s for s in suggestions)
        assert any(
            "assumption_mortality" in s for s in suggestions
        )  # Available assumption columns

    def test_extract_column_name_single_quotes(self):
        """Test extracting column names from error messages with single quotes."""
        error_msg = "column 'nonexistent_col' does not exist"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "nonexistent_col"

    def test_extract_column_name_double_quotes(self):
        """Test extracting column names from error messages with double quotes."""
        error_msg = 'column "nonexistent_col" not found'
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "nonexistent_col"

    def test_extract_column_name_no_quotes(self):
        """Test extracting column names from error messages without quotes."""
        error_msg = "columnnotfound: nonexistent_col"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "nonexistent_col"

    def test_extract_column_name_key_error(self):
        """Test extracting column names from key error messages."""
        error_msg = "key 'missing_key' not found"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name == "missing_key"

    def test_extract_column_name_not_found(self):
        """Test extracting column names when pattern doesn't match."""
        error_msg = "some generic error message"
        col_name = self.engine._extract_column_name(error_msg)
        assert col_name is None

    def test_find_similar_columns_exact_match(self):
        """Test finding similar columns with exact match."""
        similar = self.engine._find_similar_columns("premium", self.available_columns)
        assert similar[0] == "premium"

    def test_find_similar_columns_case_insensitive(self):
        """Test finding similar columns with case differences."""
        similar = self.engine._find_similar_columns("PREMIUM", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_substring(self):
        """Test finding similar columns with substring matches."""
        similar = self.engine._find_similar_columns("prem", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_edit_distance(self):
        """Test finding similar columns with edit distance."""
        similar = self.engine._find_similar_columns("premiums", self.available_columns)
        assert "premium" in similar

    def test_find_similar_columns_threshold(self):
        """Test finding similar columns respects threshold."""
        # Very dissimilar word should not match
        similar = self.engine._find_similar_columns("xyz", self.available_columns)
        assert len(similar) == 0

    def test_find_similar_columns_empty_list(self):
        """Test finding similar columns with empty available list."""
        similar = self.engine._find_similar_columns("premium", [])
        assert similar == []

    def test_find_similar_columns_prefix_boost(self):
        """Test finding similar columns gets boost for prefix matches."""
        columns = ["premium_annual", "premium_monthly", "other_column"]
        similar = self.engine._find_similar_columns("prem", columns)

        # Should find both premium columns
        assert "premium_annual" in similar
        assert "premium_monthly" in similar

    def test_actuarial_typos_comprehensive(self):
        """Test all defined actuarial typos."""
        for typo, correct in self.engine.ACTUARIAL_TYPOS.items():
            error_msg = f"column '{typo}' does not exist"
            extracted = self.engine._extract_column_name(error_msg)
            assert extracted == typo

            # If the correct column is available, should suggest it
            if correct in self.available_columns:
                error = Exception(error_msg)
                operation = self._create_operation()
                suggestions = self.engine.suggest_fixes(
                    error,
                    operation,
                    self.available_columns,
                )
                assert any(f"Did you mean '{correct}'?" in s for s in suggestions)

    def test_no_suggestions_for_unknown_error(self):
        """Test that unknown error types return empty suggestions."""
        error = Exception("completely unknown error type")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should return empty list for unknown error types
        assert suggestions == []

    def test_multiple_error_patterns_in_message(self):
        """Test handling messages with multiple error patterns."""
        # This message contains both "column not found" and "null" patterns
        # Use a typo that will generate suggestions
        error = Exception("column 'premiun' not found, null values present")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should trigger column not found suggestions (first match wins)
        assert len(suggestions) > 0
        # Should suggest the typo correction
        assert any("premium" in s for s in suggestions)
        # The first pattern matched should be used (column not found)
        assert not any("null" in s.lower() for s in suggestions)

    def test_case_insensitive_error_matching(self):
        """Test that error pattern matching is case insensitive."""
        # Use a typo that will generate suggestions
        error = Exception("COLUMN 'PREMIUN' NOT FOUND")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(
            error,
            operation,
            self.available_columns,
        )

        # Should still match despite uppercase and suggest correction
        assert len(suggestions) > 0
        assert any("premium" in s.lower() for s in suggestions)

    def test_suggestion_engine_with_no_available_columns(self):
        """Test suggestion engine with empty available columns list."""
        error = Exception("column 'test' does not exist")
        operation = self._create_operation()

        suggestions = self.engine.suggest_fixes(error, operation, [])

        # Should not crash, may return empty or generic suggestions
        assert isinstance(suggestions, list)
