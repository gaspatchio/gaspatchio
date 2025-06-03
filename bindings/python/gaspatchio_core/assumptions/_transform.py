"""
Internal module for transforming DataFrames into tidy formats.
"""

from __future__ import annotations

from typing import Dict, Union  # Added Dict for type hint

import polars as pl
from loguru import logger

from ._overflow import (
    _create_overflow_expansion,
    _detect_overflow_column,
    _get_max_numeric_duration,
)


def _convert_keys_to_f64(df: pl.DataFrame, key_columns: list[str]) -> pl.DataFrame:
    """Convert lookup key columns to f64 where possible for optimal performance.

    This function attempts to convert key columns to f64 for faster lookups.
    Only converts columns that can be safely converted without data loss.
    String columns containing numeric values (like "1", "2", "3") will be
    converted to f64, while mixed or non-numeric columns retain their original type.

    Args:
        df: DataFrame to process
        key_columns: List of key column names to attempt conversion

    Returns:
        pl.DataFrame: DataFrame with converted key columns
    """
    conversions: Dict[str, pl.DataType] = {}  # Corrected type hint

    for col in key_columns:
        if col not in df.columns:
            continue

        try:
            # Try to convert to f64 - this will fail if data can't be converted
            df[col].cast(
                pl.Float64, strict=True
            )  # Check castability without assignment
            conversions[col] = pl.Float64
            logger.debug(f"Marking key column '{col}' for f64 conversion")
        except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
            # Keep original type if conversion fails
            logger.debug(
                f"Keeping key column '{col}' as {df[col].dtype} (f64 conversion not possible)"
            )
            continue

    if conversions:
        df = df.with_columns(
            [pl.col(col).cast(dtype) for col, dtype in conversions.items()]
        )
        logger.info(
            f"Converted {len(conversions)} key columns to f64: {list(conversions.keys())}"
        )

    return df


def _tidy_curve(df: pl.DataFrame, id_cols: list[str], value: str) -> pl.DataFrame:
    """Tidy a curve table (single numeric column) with proper column naming.

    This internal function handles the tidying of curve-format assumption tables
    where there is a single value column alongside identifier columns. It
    validates that the table structure is indeed a curve (not a wide table),
    renames the value column to the specified name for consistency, and ensures
    proper column ordering for downstream processing and lookups.

    Args:
        df: DataFrame with id columns + single numeric column
        id_cols: List of id column names
        value: Desired name for the value column

    Returns:
        pl.DataFrame: Tidy curve table with renamed value column

    Raises:
        ValueError: If multiple numeric columns found or no numeric columns
    """
    # Get numeric columns (excluding id columns)
    numeric_cols = [
        col for col in df.columns if col not in id_cols and df[col].dtype.is_numeric()
    ]

    if len(numeric_cols) == 0:
        raise ValueError(
            f"No numeric columns found for curve table. "
            f"Curve tables must have exactly one numeric column. "
            f"Available columns: {df.columns}, ID columns: {id_cols}"
        )
    elif len(numeric_cols) > 1:
        raise ValueError(
            f"Multiple numeric columns found for curve table: {numeric_cols}. "
            f"This appears to be a wide table. Use wide table loading for tables with multiple value columns."
        )

    # Rename the single numeric column to the desired value name
    original_value_col = numeric_cols[0]
    if original_value_col != value:
        df = df.rename({original_value_col: value})

    # Return DataFrame with id columns + renamed value column
    return df.select(id_cols + [value])


def _tidy_wide_basic(
    df: pl.DataFrame, id_cols: list[str], wide_cols: list[str], value: str
) -> pl.DataFrame:
    """Tidy a wide table by melting wide columns to long format.

    This internal function transforms wide-format assumption tables into
    standardized long format using Polars' unpivot operation. It melts the
    specified wide columns while preserving identifier columns, creating a
    "variable" column for the original column names and a value column for
    the rates. This transformation is essential for efficient lookups and
    consistent data structure across different assumption table formats.

    Args:
        df: DataFrame with id columns + wide columns
        id_cols: List of id column names
        wide_cols: List of wide column names to melt
        value: Name for the melted value column

    Returns:
        pl.DataFrame: Long format table with id_cols + ["variable"] + [value]
    """
    # Validate that all wide columns exist in the DataFrame
    missing_cols = [col for col in wide_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Specified wide columns not found in DataFrame: {missing_cols}"
        )

    # Melt the wide table to long format
    tidy_df = df.unpivot(
        on=wide_cols,
        index=id_cols,
        variable_name="variable",
        value_name=value,
    )

    # Ensure variable column is string type
    tidy_df = tidy_df.with_columns(pl.col("variable").cast(pl.Utf8))

    return tidy_df


def _tidy_wide_with_overflow_expansion(
    df: pl.DataFrame,
    id_cols: list[str],
    wide_cols: list[str],
    value: str,
    overflow: Union[str, None] = None,
    max_overflow: int = 200,
) -> pl.DataFrame:
    """Tidy a wide table with overflow expansion.

    This internal function combines basic wide table melting with overflow
    expansion capabilities. It first transforms the wide table to long format,
    then identifies overflow columns and expands their values across the
    specified duration range. This creates a comprehensive assumption table
    that covers both explicitly modeled durations and extended periods using
    ultimate rates, which is essential for long-term actuarial projections.

    Args:
        df: DataFrame with id columns + wide columns
        id_cols: List of id column names
        wide_cols: List of wide column names to melt
        value: Name for the melted value column
        overflow: Overflow column specification or None
        max_overflow: Maximum duration to expand overflow values to.
            Only used when overflow handling is enabled. Defaults to 200.

    Returns:
        pl.DataFrame: Long format table with overflow expansion applied
    """
    # Start with basic wide table melting
    tidy_df = _tidy_wide_basic(df, id_cols, wide_cols, value)

    # Handle overflow expansion if enabled
    if overflow is not None:
        overflow_col = _detect_overflow_column(wide_cols, overflow)

        if overflow_col is not None:
            # Get max numeric duration for expansion start point
            max_numeric_duration = _get_max_numeric_duration(
                wide_cols, exclude_overflow=overflow_col
            )

            if max_numeric_duration is not None:
                # Expand from (max_numeric + 1) to max_overflow
                start_expansion = max_numeric_duration + 1

                expansion_df = _create_overflow_expansion(
                    tidy_df, id_cols, overflow_col, value, start_expansion, max_overflow
                )

                # Concatenate original tidy data with expansion
                if not expansion_df.is_empty():
                    tidy_df = pl.concat([tidy_df, expansion_df])

    return tidy_df
