"""
Internal module for data source materialization.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import polars as pl
from loguru import logger


def _materialise(source: Union[str, Path, pl.DataFrame]) -> pl.DataFrame:
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
            f"Using provided DataFrame with {source.shape[0]} rows and {source.shape[1]} columns"
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
            f"  • Check file permissions"
        )

    # Detect file type and read appropriately
    suffix = source.suffix.lower()

    logger.debug(f"Reading {suffix} file: {source}")

    if suffix == ".csv":
        try:
            df = pl.read_csv(source, infer_schema_length=10000)
            logger.debug(
                f"Successfully read CSV with {df.shape[0]} rows and {df.shape[1]} columns"
            )
            return df
        except pl.exceptions.PolarsError as e:
            raise ValueError(
                f"Failed to read CSV file {source}: {e}\\n"
                f"Suggestions:\\n"
                f"  • Check the CSV format is valid (proper delimiters, headers)\\n"
                f"  • Ensure text encoding is UTF-8\\n"
                f"  • Try opening the file in a text editor to verify format\\n"
                f"  • Check for corrupted data or missing values"
            ) from e
        except Exception as e:
            raise ValueError(f"Unexpected error reading CSV file {source}: {e}") from e
    elif suffix == ".parquet":
        try:
            df = pl.read_parquet(source)
            logger.debug(
                f"Successfully read Parquet with {df.shape[0]} rows and {df.shape[1]} columns"
            )
            return df
        except pl.exceptions.PolarsError as e:
            raise ValueError(
                f"Failed to read Parquet file {source}: {e}\\n"
                f"Suggestions:\\n"
                f"  • Check the Parquet file is not corrupted\\n"
                f"  • Ensure the file was created with a compatible Parquet version\\n"
                f"  • Try reading with a different Parquet reader to verify integrity"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Unexpected error reading Parquet file {source}: {e}"
            ) from e
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported formats: .csv, .parquet\\n"
            f"Suggestions:\\n"
            f"  • Convert your data to CSV or Parquet format\\n"
            f"  • Use pl.DataFrame() to create data programmatically\\n"
            f"  • Check file extension matches the actual format"
        )
