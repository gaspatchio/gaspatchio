# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Enhanced analysis module for assumption table structure analysis and configuration generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import polars as pl
from loguru import logger

from ._utils import _detect_overflow_column, _materialise


@dataclass
class DimensionInfo:
    """Information about a detected dimension in the data"""

    name: str
    dtype: str
    unique_count: int
    sample_values: list[Any]  # First 5 unique values
    suggested_type: Literal["key", "melt", "categorical", "value"]
    numeric_pattern: str | None = None  # e.g., "1-25", "continuous"


@dataclass
class InterpolationHint:
    """Suggestion for interpolation opportunities"""

    dimension: str
    detected_values: list[int | float]
    missing_values: list[int | float]
    suggested_method: Literal["linear", "log-linear", "cubic"]


@dataclass
class TableSchema:
    """Complete analysis result for a table"""

    data_dimensions: list[DimensionInfo]
    value_columns: list[str]
    format: Literal["curve", "wide"]
    overflow_candidate: str | None = None
    interpolation_opportunities: list[InterpolationHint] = field(default_factory=list)
    row_count: int = 0

    def suggest_table_config(self) -> str:
        """Generate example code for loading this table"""
        if self.format == "curve":
            # Simple curve table configuration
            dimensions_code = []
            for dim in self.data_dimensions:
                if dim.name in self.value_columns:
                    continue  # Skip value columns
                dimensions_code.append(
                    f"        '{dim.name}': gs.DataDimension('{dim.name}')",
                )

            dimensions_str = ",\n".join(dimensions_code)
            value_col = self.value_columns[0] if self.value_columns else "rate"

            return f"""# Suggested configuration for curve table
table = gs.Table(
    name="your_table_name",
    source="path/to/your/data.csv",
    dimensions={{
{dimensions_str}
    }},
    value="{value_col}"
)"""
        # Wide table configuration
        key_dimensions = []
        melt_columns = []

        for dim in self.data_dimensions:
            if dim.suggested_type == "key":
                key_dimensions.append(
                    f"        '{dim.name}': gs.DataDimension('{dim.name}')",
                )
            elif dim.suggested_type == "melt":
                # This would be the wide columns to melt
                melt_columns.append(dim.name)

        key_dims_str = ",\n".join(key_dimensions)
        value_col = self.value_columns[0] if self.value_columns else "rate"

        # For wide tables, we need to identify which columns to melt
        if melt_columns:
            melt_cols_str = ", ".join([f"'{col}'" for col in melt_columns])
            melt_dim_code = f"        'duration': gs.MeltDimension([{melt_cols_str}])"
            if key_dimensions:
                dimensions_str = key_dims_str + ",\n" + melt_dim_code
            else:
                dimensions_str = melt_dim_code
        else:
            dimensions_str = key_dims_str

        overflow_code = ""
        if self.overflow_candidate:
            overflow_code = f",\n            overflow=gs.ExtendOverflow('{self.overflow_candidate}', to_value=200)"

        return f"""# Suggested configuration for wide table
table = gs.Table(
    name="your_table_name",
    source="path/to/your/data.csv",  
    dimensions={{
{dimensions_str}{overflow_code}
    }},
    value="{value_col}"
)"""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "data_dimensions": [
                {
                    "name": dim.name,
                    "dtype": dim.dtype,
                    "unique_count": dim.unique_count,
                    "sample_values": dim.sample_values,
                    "suggested_type": dim.suggested_type,
                    "numeric_pattern": dim.numeric_pattern,
                }
                for dim in self.data_dimensions
            ],
            "value_columns": self.value_columns,
            "format": self.format,
            "overflow_candidate": self.overflow_candidate,
            "interpolation_opportunities": [
                {
                    "dimension": hint.dimension,
                    "detected_values": hint.detected_values,
                    "missing_values": hint.missing_values,
                    "suggested_method": hint.suggested_method,
                }
                for hint in self.interpolation_opportunities
            ],
            "row_count": self.row_count,
        }


def analyze_table(
    source: str | Path | pl.DataFrame,
    sample_rows: int = 1000,
    detect_overflow: bool = True,
    detect_interpolation: bool = True,
) -> TableSchema:
    """
    Analyze table structure and suggest loading configuration.

    Args:
        source: Data source to analyze
        sample_rows: Number of rows to sample for analysis
        detect_overflow: Whether to detect overflow columns
        detect_interpolation: Whether to detect interpolation opportunities

    Returns:
        TableSchema with analysis results

    """
    logger.debug(f"Starting table analysis for source: {source}")

    # Materialize the data
    df = _materialise(source)

    # Sample data if needed for performance
    if len(df) > sample_rows:
        df = df.sample(n=sample_rows, seed=42)
        logger.debug(f"Sampled {sample_rows} rows from {len(df)} total rows")

    row_count = len(df)
    all_columns = df.columns

    logger.debug(
        f"Analyzing DataFrame with {row_count} rows and {len(all_columns)} columns",
    )

    # Analyze each column
    dimension_info = []
    numeric_columns = []
    non_numeric_columns = []

    for col in all_columns:
        dtype_str = str(df[col].dtype)
        is_numeric = df[col].dtype.is_numeric()
        unique_values = df[col].unique().to_list()[:5]  # First 5 unique values
        unique_count = df[col].n_unique()

        if is_numeric:
            numeric_columns.append(col)

            # Determine if this looks like a key column or value column
            if unique_count == row_count or _is_likely_id_column(col):
                suggested_type = "key"
                numeric_pattern = _analyze_numeric_pattern(df[col])
            else:
                suggested_type = (
                    "melt"  # Could be melt column in wide table or value in curve table
                )
                numeric_pattern = None
        else:
            non_numeric_columns.append(col)
            suggested_type = "key"  # Non-numeric columns are typically keys
            numeric_pattern = None

        dimension_info.append(
            DimensionInfo(
                name=col,
                dtype=dtype_str,
                unique_count=unique_count,
                sample_values=unique_values,
                suggested_type=suggested_type,
                numeric_pattern=numeric_pattern,
            ),
        )

    # Determine table format (curve vs wide)
    # Curve tables have one value column, wide tables have multiple
    potential_value_columns = [
        col for col in numeric_columns if not _is_likely_id_column(col)
    ]

    is_wide = len(potential_value_columns) > 1
    table_format = "wide" if is_wide else "curve"

    logger.debug(f"Detected table format: {table_format}")

    # Determine value columns and update dimension types based on table format
    if is_wide:
        # For wide tables, the value is typically called "value" after melting
        value_columns = ["value"]

        # Update dimension info for wide columns - they should be melt type
        for dim in dimension_info:
            if dim.name in potential_value_columns:
                dim.suggested_type = "melt"
    # For curve tables, identify the single value column
    elif potential_value_columns:
        value_columns = [potential_value_columns[0]]
        # Update the value column dimension type
        for dim in dimension_info:
            if dim.name in value_columns:
                dim.suggested_type = "value"  # Mark as value column for curve tables
    else:
        # Fallback - last numeric column
        value_columns = [numeric_columns[-1]] if numeric_columns else ["rate"]
        # Update the fallback value column
        for dim in dimension_info:
            if dim.name in value_columns:
                dim.suggested_type = "value"

    # Detect overflow column if requested
    overflow_candidate = None
    if detect_overflow and is_wide:
        overflow_candidate = _detect_overflow_column(potential_value_columns, "auto")
        logger.debug(f"Overflow detection result: {overflow_candidate}")

    # Detect interpolation opportunities if requested
    interpolation_opportunities = []
    if detect_interpolation:
        for dim in dimension_info:
            if dim.suggested_type == "key" and dim.dtype in ["Int64", "Float64"]:
                hints = _detect_interpolation_opportunities(df[dim.name])
                if hints:
                    interpolation_opportunities.extend(
                        [
                            InterpolationHint(
                                dimension=dim.name,
                                detected_values=hint["detected"],
                                missing_values=hint["missing"],
                                suggested_method=hint["method"],
                            )
                            for hint in hints
                        ],
                    )

    schema = TableSchema(
        data_dimensions=dimension_info,
        value_columns=value_columns,
        format=table_format,
        overflow_candidate=overflow_candidate,
        interpolation_opportunities=interpolation_opportunities,
        row_count=row_count,
    )

    logger.info(
        f"Analysis complete: {table_format} table with {len(dimension_info)} dimensions",
    )
    return schema


# BACKWARD COMPATIBILITY FUNCTION - TO BE REMOVED IN NEW API
def _analyse_shape(
    df: pl.DataFrame,
    id: str | list[str] | None,
) -> tuple[list[str], list[str], list[str], bool]:
    """Analyse DataFrame shape and identify id and numeric columns.

    DEPRECATED: This function is maintained for backward compatibility only.
    Use analyze_table() for new code.

    This internal function performs comprehensive analysis of the DataFrame
    structure to automatically classify columns into identifiers and value
    columns. It handles both explicit column specifications and intelligent
    auto-detection based on data types and common actuarial naming patterns.
    The function determines whether the table is in curve format (single value
    column) or wide format (multiple value columns requiring melting).

    Args:
        df: DataFrame to analyse
        id: Explicit id column specification, or None for auto-detection

    Returns:
        tuple: (id_columns, numeric_wide_cols, text_wide_cols, is_wide)
            - id_columns: List of identifier column names
            - numeric_wide_cols: List of numeric wide column names (excluding id columns)
            - text_wide_cols: List of non-numeric wide column names (excluding id columns)
            - is_wide: True if multiple value columns (wide table), False if single value column (curve)

    Raises:
        ValueError: If specified id columns don't exist or other validation errors

    """
    if df.is_empty():
        raise ValueError(
            "DataFrame is empty - no rows to process.\n"
            "Suggestions:\n"
            "  • Check your data source contains data\n"
            "  • Verify any filtering hasn't removed all rows\n"
            "  • Ensure the file was read correctly",
        )

    # Get all column names and their types
    all_columns = df.columns
    numeric_columns = [col for col in all_columns if df[col].dtype.is_numeric()]
    non_numeric_columns = [col for col in all_columns if not df[col].dtype.is_numeric()]

    logger.debug(
        f"DataFrame analysis: {len(all_columns)} total columns, "
        f"{len(numeric_columns)} numeric, {len(non_numeric_columns)} non-numeric",
    )

    # Process id column specification
    if id is None:
        # Auto-detect: prioritize non-numeric columns first, then common id column names
        if non_numeric_columns:
            id_columns = [non_numeric_columns[0]]  # Take first non-numeric column
            logger.debug(f"Auto-detected id column from non-numeric: {id_columns[0]}")
        else:
            # All columns are numeric - look for common id column patterns
            potential_id_cols = []
            common_id_patterns = [
                "age",
                "year",
                "duration",
                "term",
                "time",
                "period",
                "index",
                "id",
            ]

            for col in all_columns:
                col_lower = col.lower()
                if any(pattern in col_lower for pattern in common_id_patterns):
                    potential_id_cols.append(col)

            if potential_id_cols:
                id_columns = [potential_id_cols[0]]  # Take first matching pattern
                logger.debug(
                    f"Auto-detected id column from pattern matching: {id_columns[0]}",
                )
            else:
                # Fallback: use first column as id if all else fails
                id_columns = [all_columns[0]]
                logger.debug(f"Using first column as id (fallback): {id_columns[0]}")
    elif isinstance(id, str):
        # Split string on comma only, not whitespace (to handle column names with spaces)
        if "," in id:
            id_columns = [col.strip() for col in id.split(",") if col.strip()]
        else:
            # Single column name - don't split
            id_columns = [id.strip()]
        logger.debug(f"Using specified id columns: {id_columns}")
    else:  # isinstance(id, list)
        id_columns = [str(col) for col in id]
        logger.debug(f"Using provided id column list: {id_columns}")

    # Validate that all id columns exist
    missing_columns = [col for col in id_columns if col not in all_columns]
    if missing_columns:
        available_cols = ", ".join(all_columns)
        raise ValueError(
            f"Specified id columns not found in DataFrame: {missing_columns}\n"
            f"Available columns: {available_cols}\n"
            f"Column types: {dict(zip(all_columns, [str(df[col].dtype) for col in all_columns], strict=False))}\n"
            f"Suggestions:\n"
            f"  • Check column name spelling and case sensitivity\n"
            f"  • Use df.columns to see available column names\n"
            f"  • Consider auto-detection by setting id=None",
        )

    # Separate remaining columns into numeric and non-numeric (excluding id columns)
    remaining_numeric = [col for col in numeric_columns if col not in id_columns]
    remaining_non_numeric = [
        col for col in non_numeric_columns if col not in id_columns
    ]

    # Determine if this is a wide table (multiple value columns)
    # Only count numeric columns as value columns for actuarial tables
    # Text columns are typically descriptive fields, not value columns to be melted
    is_wide = len(remaining_numeric) > 1

    logger.debug(
        f"Table type: {'wide' if is_wide else 'curve'} "
        f"({len(remaining_numeric)} numeric columns after id exclusion)",
    )

    return id_columns, remaining_numeric, remaining_non_numeric, is_wide


def _is_likely_id_column(col_name: str) -> bool:
    """Check if a column name suggests it's an ID/key column"""
    col_lower = col_name.lower()
    id_patterns = [
        "age",
        "year",
        "duration",
        "term",
        "time",
        "period",
        "index",
        "id",
        "key",
        "code",
        "product",
        "sex",
        "smoking",
    ]
    return any(pattern in col_lower for pattern in id_patterns)


def _analyze_numeric_pattern(series: pl.Series) -> str | None:
    """Analyze numeric patterns in a series"""
    try:
        values = series.drop_nulls().sort()
        if len(values) == 0:
            return None

        min_val = values.min()
        max_val = values.max()

        # Check if it's a continuous range
        if len(values) > 1:
            diffs = values.diff().drop_nulls()
            if len(diffs) > 0 and diffs.std() < 0.1:  # Nearly constant differences
                return f"{min_val}-{max_val}"

        return "continuous"
    except Exception:
        return None


def _detect_interpolation_opportunities(series: pl.Series) -> list[dict[str, Any]]:
    """Detect potential interpolation opportunities in a numeric series"""
    try:
        values = series.drop_nulls().sort().unique()
        if len(values) < 3:
            return []

        # Look for gaps in what appears to be a sequence
        diffs = values.diff().drop_nulls()
        if len(diffs) == 0:
            return []

        # Find the most common difference (step size)
        diff_list = diffs.to_list()
        if not diff_list:
            return []

        # If we have irregular gaps (differences vary significantly), suggest interpolation
        min_diff = min(diff_list)
        max_diff = max(diff_list)

        # If maximum gap is more than 2x the minimum gap, suggest interpolation
        if max_diff > min_diff * 2:
            # Suggest interpolation method based on data characteristics
            method = "linear"  # Default
            if values.min() > 0:  # All positive values might benefit from log-linear
                method = "log-linear"

            return [
                {
                    "detected": values.to_list(),
                    "missing": [],  # Would need more sophisticated gap detection to identify specific missing values
                    "method": method,
                },
            ]

        return []
    except Exception:
        return []
