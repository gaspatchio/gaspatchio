"""
Internal module for DataFrame structural analysis.
"""

from __future__ import annotations

from typing import Tuple, Union  # Corrected import for Tuple

import polars as pl
from loguru import logger


def _analyse_shape(
    df: pl.DataFrame, id: Union[str, list[str], None]
) -> Tuple[list[str], list[str], list[str], bool]:  # Corrected type hint for tuple
    """Analyse DataFrame shape and identify id and numeric columns.

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
            "  • Ensure the file was read correctly"
        )

    # Get all column names and their types
    all_columns = df.columns
    numeric_columns = [col for col in all_columns if df[col].dtype.is_numeric()]
    non_numeric_columns = [col for col in all_columns if not df[col].dtype.is_numeric()]

    logger.debug(
        f"DataFrame analysis: {len(all_columns)} total columns, "
        f"{len(numeric_columns)} numeric, {len(non_numeric_columns)} non-numeric"
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
                    f"Auto-detected id column from pattern matching: {id_columns[0]}"
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
            f"Column types: {dict(zip(all_columns, [str(df[col].dtype) for col in all_columns]))}\n"
            f"Suggestions:\n"
            f"  • Check column name spelling and case sensitivity\n"
            f"  • Use df.columns to see available column names\n"
            f"  • Consider auto-detection by setting id=None"
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
        f"({len(remaining_numeric)} numeric columns after id exclusion)"
    )

    return id_columns, remaining_numeric, remaining_non_numeric, is_wide
