"""
Shared utility functions for the assumptions module.

This module contains utility functions that are used across multiple
assumption table components. These were extracted from other modules
to reduce dependencies and improve modularity.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from loguru import logger


def _materialise(source: str | Path | pl.DataFrame) -> pl.DataFrame:
    """Materialize data from various sources into a Polars DataFrame.

    This internal function handles the conversion of different data sources
    (file paths or existing DataFrames) into a standardized Polars DataFrame
    format. It supports CSV and Parquet file formats with optimized reading
    settings for actuarial data, including extended schema inference for
    complex data types.

    Args:
        source: Data source - file path (str/Path) or existing DataFrame

    Returns:
        pl.DataFrame: The materialized DataFrame

    Raises:
        FileNotFoundError: If source file doesn't exist
        ValueError: If file format is not supported or data is invalid

    """
    if isinstance(source, pl.DataFrame):
        logger.debug(
            f"Using provided DataFrame with {source.shape[0]} rows and {source.shape[1]} columns",
        )
        return source

    # Convert to Path for easier handling
    if isinstance(source, str):
        source = Path(source)

    if not source.exists():
        # Enhanced error message with suggestions
        raise FileNotFoundError(
            f"Source file not found: {source}\\n"
            f"Suggestions:\\n"
            f"  • Check the file path is correct\\n"
            f"  • Ensure the file exists in the current working directory: {Path.cwd()}\\n"
            f"  • Use absolute path if the file is in a different directory\\n"
            f"  • Check file permissions",
        )

    # Detect file type and read appropriately
    suffix = source.suffix.lower()

    logger.debug(f"Reading {suffix} file: {source}")

    if suffix == ".csv":
        try:
            df = pl.read_csv(source, infer_schema_length=10000)
            logger.debug(
                f"Successfully read CSV with {df.shape[0]} rows and {df.shape[1]} columns",
            )
            return df
        except pl.exceptions.PolarsError as e:
            raise ValueError(
                f"Failed to read CSV file {source}: {e}\\n"
                f"Suggestions:\\n"
                f"  • Check the CSV format is valid (proper delimiters, headers)\\n"
                f"  • Ensure text encoding is UTF-8\\n"
                f"  • Try opening the file in a text editor to verify format\\n"
                f"  • Check for corrupted data or missing values",
            ) from e
        except Exception as e:
            raise ValueError(f"Unexpected error reading CSV file {source}: {e}") from e
    elif suffix == ".parquet":
        try:
            df = pl.read_parquet(source)
            logger.debug(
                f"Successfully read Parquet with {df.shape[0]} rows and {df.shape[1]} columns",
            )
            return df
        except pl.exceptions.PolarsError as e:
            raise ValueError(
                f"Failed to read Parquet file {source}: {e}\\n"
                f"Suggestions:\\n"
                f"  • Check the Parquet file is not corrupted\\n"
                f"  • Ensure the file was created with a compatible Parquet version\\n"
                f"  • Try reading with a different Parquet reader to verify integrity",
            ) from e
        except Exception as e:
            raise ValueError(
                f"Unexpected error reading Parquet file {source}: {e}",
            ) from e
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported formats: .csv, .parquet\\n"
            f"Suggestions:\\n"
            f"  • Convert your data to CSV or Parquet format\\n"
            f"  • Use pl.DataFrame() to create data programmatically\\n"
            f"  • Check file extension matches the actual format",
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
    conversions: dict[str, pl.DataType] = {}

    for col in key_columns:
        if col not in df.columns:
            continue

        try:
            # Try to convert to f64 - this will fail if data can't be converted
            df[col].cast(
                pl.Float64,
                strict=True,
            )  # Check castability without assignment
            conversions[col] = pl.Float64
            logger.debug(f"Marking key column '{col}' for f64 conversion")
        except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
            # Keep original type if conversion fails
            logger.debug(
                f"Keeping key column '{col}' as {df[col].dtype} (f64 conversion not possible)",
            )
            continue

    if conversions:
        df = df.with_columns(
            [pl.col(col).cast(dtype) for col, dtype in conversions.items()],
        )
        logger.info(
            f"Converted {len(conversions)} key columns to f64: {list(conversions.keys())}",
        )

    return df


def _detect_overflow_column(
    wide_cols: list[str],
    overflow: str | None,
) -> str | None:
    """Detect overflow column in wide table columns.

    This internal function identifies overflow columns in actuarial wide tables
    using either explicit specification or intelligent pattern matching. It
    recognizes common actuarial overflow column naming conventions such as
    "Ult.", "Ultimate", "999", and empty strings. This is crucial for proper
    handling of assumption tables where certain rates apply beyond the
    explicitly modeled duration periods.

    Args:
        wide_cols: List of wide column names to search
        overflow: Overflow specification - None, "auto", or specific column name

    Returns:
        str | None: The overflow column name if found, None otherwise

    Raises:
        ValueError: If explicit overflow column not found in wide_cols

    """
    if overflow is None:
        return None

    if overflow == "auto":
        # Common overflow patterns
        overflow_patterns = [
            "ult",
            "ult.",
            "ultimate",
            "term",
            "999",
            "",  # Empty string sometimes used for overflow
        ]

        # Search for overflow columns (case insensitive)
        for col in wide_cols:
            col_lower = col.lower().strip()
            if col_lower in overflow_patterns:
                return col

        # No overflow column found with auto detection
        return None
    # Explicit overflow column name specified
    if overflow in wide_cols:
        return overflow
    raise ValueError(
        f"Specified overflow column '{overflow}' not found in wide columns: {wide_cols}",
    )
