# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Error suggestion engine for generating helpful fix suggestions.

This module provides intelligent suggestions based on error types and context,
helping users quickly diagnose and fix common ActuarialFrame errors.
"""

import re
from difflib import SequenceMatcher

from .metadata import TracedOperation


class ErrorSuggestionEngine:
    """Generate helpful suggestions based on error type and context."""

    # Common actuarial typos and their corrections
    ACTUARIAL_TYPOS = {
        "premiun": "premium",
        "premiums": "premium",
        "premiuns": "premium",
        "assmuption": "assumption",
        "assumtion": "assumption",
        "benifits": "benefits",
        "benfit": "benefit",
        "poliy": "policy",
        "polciies": "policies",
        "poilcy": "policy",
        "cliam": "claim",
        "claimes": "claims",
        "cliams": "claims",
        "exposrue": "exposure",
        "experiance": "experience",
        "decrement": "decrements",
        "incrment": "increment",
        "mortaliy": "mortality",
        "morality": "mortality",  # Common confusion
        "lapses": "lapse",
        "laspse": "lapse",
        "intrest": "interest",
        "discout": "discount",
        "acturial": "actuarial",
        "data": "date",  # Very common typo
    }

    def suggest_fixes(
        self,
        exception: Exception,
        operation: TracedOperation,
        available_columns: list[str],
    ) -> list[str]:
        """
        Generate context-aware suggestions for fixing errors.

        Args:
            exception: The exception that was raised
            operation: The operation that failed
            available_columns: List of available column names

        Returns:
            List of suggestion strings

        """
        suggestions = []
        error_msg = str(exception).lower()
        error_type = type(exception).__name__

        # Column not found errors
        if "columnnotfound" in error_type.lower() or (
            "column" in error_msg
            and ("not found" in error_msg or "does not exist" in error_msg)
        ):
            suggestions.extend(self._suggest_column_fixes(error_msg, available_columns))

        # List-length mismatch — usually a jagged (per-policy) projection column
        # combined with a fixed-width / portfolio-max list.
        elif "list lengths differed" in error_msg or "lengths don't match" in error_msg:
            suggestions.extend(self._suggest_list_length_fixes())

        # Type mismatch errors
        elif any(
            phrase in error_msg
            for phrase in [
                "could not determine output type",
                "type mismatch",
                "cannot cast",
                "cannot convert",
                "incompatible dtypes",
            ]
        ):
            suggestions.extend(self._suggest_type_fixes(error_msg, operation))

        # Schema mismatch errors
        elif any(
            phrase in error_msg
            for phrase in [
                "schema mismatch",
                "columns don't match",
                "shape mismatch",
            ]
        ):
            suggestions.extend(self._suggest_schema_fixes(error_msg))

        # Division by zero errors
        elif any(
            phrase in error_msg
            for phrase in [
                "division by zero",
                "divide by zero",
                "divisionbyzero",
            ]
        ):
            suggestions.extend(self._suggest_division_fixes())

        # Index out of bounds errors
        elif any(
            phrase in error_msg
            for phrase in [
                "index out of bounds",
                "out of bounds",
                "index error",
            ]
        ):
            suggestions.extend(self._suggest_index_fixes())

        # Date/time parsing errors
        elif any(
            phrase in error_msg
            for phrase in [
                "date",
                "time",
                "timestamp",
                "datetime",
                "parse",
            ]
        ):
            suggestions.extend(self._suggest_date_fixes(error_msg))

        # Null/missing value errors
        elif any(
            phrase in error_msg
            for phrase in [
                "null",
                "missing",
                "nan",
            ]
        ):
            suggestions.extend(self._suggest_null_fixes())

        # File/path errors
        elif any(
            phrase in error_msg
            for phrase in [
                "no such file",
                "file not found",
                "file error",
                "cannot be read",
                "path",
            ]
        ):
            suggestions.extend(self._suggest_file_fixes(error_msg))

        # Assumption lookup errors (domain-specific)
        elif any(
            phrase in error_msg
            for phrase in [
                "assumption",
                "lookup",
                "key error",
            ]
        ):
            suggestions.extend(
                self._suggest_assumption_fixes(error_msg, available_columns),
            )

        return suggestions

    def _suggest_column_fixes(
        self,
        error_msg: str,
        available_columns: list[str],
    ) -> list[str]:
        """Suggest fixes for column not found errors."""
        suggestions = []

        # Extract the missing column name
        missing_col = self._extract_column_name(error_msg)
        if not missing_col:
            return suggestions

        # Check for common actuarial typos first
        if missing_col in self.ACTUARIAL_TYPOS:
            correct_col = self.ACTUARIAL_TYPOS[missing_col]
            if correct_col in available_columns:
                suggestions.append(
                    f"Did you mean '{correct_col}'? (common actuarial typo)",
                )
            else:
                suggestions.append(
                    f"'{missing_col}' is a common typo for '{correct_col}'",
                )

        # Find similar columns using edit distance
        similar_cols = self._find_similar_columns(missing_col, available_columns)
        if similar_cols:
            best_match = similar_cols[0]
            suggestions.append(f"Did you mean '{best_match}'? (similar column found)")

            # If there are multiple good matches, mention them
            if len(similar_cols) > 1:
                other_matches = similar_cols[1:3]  # Show up to 2 more
                others = ", ".join(f"'{col}'" for col in other_matches)
                suggestions.append(f"Other similar columns: {others}")

        # Check for common patterns
        if missing_col.endswith("_id") and not any(
            col.endswith("_id") for col in available_columns
        ):
            suggestions.append(
                "No ID columns found - check if you need to join additional data",
            )

        if missing_col.startswith("calc_") and not any(
            col.startswith("calc_") for col in available_columns
        ):
            suggestions.append(
                "No calculated columns found - ensure calculations are defined before use",
            )

        return suggestions

    def _suggest_type_fixes(
        self,
        error_msg: str,
        operation: TracedOperation,
    ) -> list[str]:
        """Suggest fixes for type mismatch errors."""
        suggestions = [
            "Ensure all expressions have consistent types",
            "Consider using .cast() to explicitly set types",
        ]

        # More specific suggestions based on error message
        if (
            "string" in error_msg and "numeric" in error_msg
        ) or "cannot convert string" in error_msg:
            suggestions.append(
                "Try converting strings to numbers with .cast(pl.Float64) or .cast(pl.Int64)",
            )

        elif "float" in error_msg and "int" in error_msg:
            suggestions.append(
                "Mix of integers and floats - consider using .cast(pl.Float64) for consistency",
            )

        elif "boolean" in error_msg:
            suggestions.append(
                "Boolean type mismatch - ensure conditions return True/False",
            )

        elif "date" in error_msg or "datetime" in error_msg:
            suggestions.append(
                "Date/time type issues - use .str.to_datetime() or .cast(pl.Date)",
            )

        return suggestions

    def _suggest_schema_fixes(self, error_msg: str) -> list[str]:
        """Suggest fixes for schema mismatch errors."""
        return [
            "Check that join keys have matching types",
            "Use .cast() to align data types before joining",
            "Verify column names match exactly (case-sensitive)",
            "Use .select() to choose only needed columns before operations",
        ]

    def _suggest_list_length_fixes(self) -> list[str]:
        """Suggest fixes for list-length mismatches.

        Almost always a jagged (per-policy) projection column combined with a
        fixed-width / portfolio-max list (yield curve, discount vector, or
        externally-built assumption vector).
        """
        return [
            "List lengths differ across rows — usually a jagged (per-policy) "
            "projection column combined with a fixed-width list (e.g. a "
            "portfolio-wide yield/discount curve or assumption vector).",
            "Trim the fixed-width list to each policy's own horizon before the "
            "arithmetic, e.g. `curve.list.head(af.month.list.len())`.",
            "Or build a rectangular grid: pass `per_policy=False` to "
            "`af.projection.set(...)` so every policy shares one period axis.",
        ]

    def _suggest_division_fixes(self) -> list[str]:
        """Suggest fixes for division by zero errors."""
        return [
            "Check for zero values in denominator before division",
            "Use .filter() to exclude zero values: .filter(pl.col('denominator') != 0)",
            "Handle nulls with .fill_null(1) or similar before division",
            "Consider using .map_elements() for custom division logic",
        ]

    def _suggest_index_fixes(self) -> list[str]:
        """Suggest fixes for index out of bounds errors."""
        return [
            "Check data length before indexing operations",
            "Use .head() or .tail() with explicit limits",
            "Validate row count: use .height to check DataFrame size",
            "Consider using .slice() instead of direct indexing",
        ]

    def _suggest_date_fixes(self, error_msg: str) -> list[str]:
        """Suggest fixes for date/time parsing errors."""
        suggestions = [
            "Check date format matches your data (e.g., '%Y-%m-%d', '%m/%d/%Y')",
            "Use .str.to_datetime() with format parameter",
        ]

        if "format" in error_msg:
            suggestions.append(
                "Common formats: '%Y-%m-%d' (2023-12-31), '%m/%d/%Y' (12/31/2023)",
            )

        if "excel" in error_msg.lower():
            suggestions.append(
                "Excel dates: use .map_elements() to convert Excel serial dates",
            )

        return suggestions

    def _suggest_null_fixes(self) -> list[str]:
        """Suggest fixes for null/missing value errors."""
        return [
            "Handle null values with .fill_null(value) or .drop_nulls()",
            "Check for missing data before calculations",
            "Use .is_null() to identify null values",
            "Consider default values for actuarial calculations",
        ]

    def _suggest_file_fixes(self, error_msg: str) -> list[str]:
        """Suggest fixes for file/path errors."""
        suggestions = [
            "Check file path is correct and file exists",
            "Use absolute paths to avoid directory issues",
        ]

        if "csv" in error_msg:
            suggestions.append("For CSV files: verify column names and data types")
        elif "parquet" in error_msg:
            suggestions.append("For Parquet files: check schema compatibility")
        elif "excel" in error_msg:
            suggestions.append("For Excel files: specify sheet name if needed")

        return suggestions

    def _suggest_assumption_fixes(
        self,
        error_msg: str,
        available_columns: list[str],
    ) -> list[str]:
        """Suggest fixes for assumption lookup errors."""
        suggestions = [
            "Check assumption key matches exactly (case-sensitive)",
            "Verify assumption table is loaded correctly",
        ]

        # Look for assumption-related columns
        assumption_cols = [
            col for col in available_columns if "assumption" in col.lower()
        ]
        if assumption_cols:
            cols_str = ", ".join(f"'{col}'" for col in assumption_cols[:3])
            suggestions.append(f"Available assumption columns: {cols_str}")

        return suggestions

    def _extract_column_name(self, error_msg: str) -> str | None:
        """
        Extract column name from error message.

        Args:
            error_msg: The error message to parse

        Returns:
            Extracted column name or None if not found

        """
        # Common patterns for column names in error messages
        patterns = [
            r"column '([^']+)' (?:does not exist|not found)",
            r"column \"([^\"]+)\" (?:does not exist|not found)",
            r"column ([a-zA-Z_][a-zA-Z0-9_]*) (?:does not exist|not found)",
            r"columnnotfound: ([a-zA-Z_][a-zA-Z0-9_]*)",
            r"key '([^']+)' not found",
            r"cannot find column '([^']+)'",
            r"unknown column: ([a-zA-Z_][a-zA-Z0-9_]*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, error_msg, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _find_similar_columns(
        self,
        target_col: str,
        available_columns: list[str],
        threshold: float = 0.6,
    ) -> list[str]:
        """
        Find columns similar to target using edit distance.

        Args:
            target_col: The target column name to match
            available_columns: List of available column names
            threshold: Minimum similarity ratio (0-1)

        Returns:
            List of similar column names, sorted by similarity (best first)

        """
        if not available_columns:
            return []

        similarities = []
        target_lower = target_col.lower()

        for col in available_columns:
            col_lower = col.lower()

            # Calculate similarity ratio
            ratio = SequenceMatcher(None, target_lower, col_lower).ratio()

            # Boost score for exact case-insensitive matches
            if target_lower == col_lower:
                ratio = 1.0
            # Boost score for substring matches
            elif target_lower in col_lower or col_lower in target_lower:
                ratio = max(ratio, 0.8)
            # Boost score for similar prefixes/suffixes
            elif (target_lower.startswith(col_lower[:3]) and len(col_lower) >= 3) or (
                col_lower.startswith(target_lower[:3]) and len(target_lower) >= 3
            ):
                ratio = max(ratio, 0.7)

            if ratio >= threshold:
                similarities.append((col, ratio))

        # Sort by similarity (highest first) and return column names
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [col for col, _ in similarities[:5]]  # Return top 5 matches
