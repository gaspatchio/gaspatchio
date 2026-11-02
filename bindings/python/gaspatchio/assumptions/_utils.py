# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

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

from gaspatchio._dtypes import UnmappedDtypeError


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
            f"Using provided DataFrame with {source.shape[0]} rows and "
            f"{source.shape[1]} columns",
        )
        return source

    # Convert to Path for easier handling
    if isinstance(source, str):
        source = Path(source)

    if not source.exists():
        # Enhanced error message with suggestions
        msg = (
            f"Source file not found: {source}\n"
            f"Suggestions:\n"
            f"  • Check the file path is correct\n"
            "  • Ensure the file exists in the current working directory: "
            f"{Path.cwd()}\n"
            f"  • Use absolute path if the file is in a different directory\n"
            f"  • Check file permissions"
        )
        raise FileNotFoundError(msg)

    # Detect file type and read appropriately
    suffix = source.suffix.lower()

    logger.debug(f"Reading {suffix} file: {source}")

    if suffix == ".csv":
        try:
            df = pl.read_csv(source, infer_schema_length=10000)
        except pl.exceptions.PolarsError as e:
            msg = (
                f"Failed to read CSV file {source}: {e}\n"
                f"Suggestions:\n"
                f"  • Check the CSV format is valid (proper delimiters, headers)\n"
                f"  • Ensure text encoding is UTF-8\n"
                f"  • Try opening the file in a text editor to verify format\n"
                f"  • Check for corrupted data or missing values"
            )
            raise ValueError(msg) from e
        except Exception as e:
            msg = f"Unexpected error reading CSV file {source}: {e}"
            raise ValueError(msg) from e
        logger.debug(
            f"Successfully read CSV with {df.shape[0]} rows and {df.shape[1]} columns",
        )
        return df
    if suffix == ".parquet":
        try:
            df = pl.read_parquet(source)
        except pl.exceptions.PolarsError as e:
            msg = (
                f"Failed to read Parquet file {source}: {e}\n"
                f"Suggestions:\n"
                f"  • Check the Parquet file is not corrupted\n"
                f"  • Ensure the file was created with a compatible Parquet version\n"
                f"  • Try reading with a different Parquet reader to verify integrity"
            )
            raise ValueError(msg) from e
        except Exception as e:
            msg = f"Unexpected error reading Parquet file {source}: {e}"
            raise ValueError(msg) from e
        logger.debug(
            f"Successfully read Parquet with {df.shape[0]} rows and "
            f"{df.shape[1]} columns",
        )
        return df
    msg = (
        f"Unsupported file format: {suffix}. Supported formats: .csv, .parquet\n"
        f"Suggestions:\n"
        f"  • Convert your data to CSV or Parquet format\n"
        f"  • Use pl.DataFrame() to create data programmatically\n"
        f"  • Check file extension matches the actual format"
    )
    raise ValueError(msg)


def _keys_fit_f64_range(source: pl.Series, converted: pl.Series) -> bool:
    """Keep wide integer keys outside the existing Float64 normalization path."""
    # Every value of these dtypes fits exactly. Comparing an Int32 (or
    # narrower) Series with 2**53 would itself overflow Polars' scalar RHS.
    if source.dtype in (pl.Int8, pl.Int16, pl.Int32, pl.UInt8, pl.UInt16, pl.UInt32):
        return True
    exact_integer_limit = 2**53
    if source.dtype.is_signed_integer():
        valid = source.is_null() | (
            (source >= -exact_integer_limit) & (source <= exact_integer_limit)
        )
        return bool(valid.all())
    if source.dtype.is_unsigned_integer():
        return bool((source.is_null() | (source <= exact_integer_limit)).all())
    if source.dtype == pl.String:
        # The caller has already parsed every cell as a float, so what is
        # left to ask is what the cells spell. Polars' Int64 cast answers
        # that exactly: a decimal, an exponent, or digits past i64 come back
        # null where the cell was not. Where every cell spells a whole
        # number, the column is judged on those integers against the same
        # closed interval an Int64 column is judged against -- which is the
        # rule as published, and the one already applied below the boundary,
        # where ["007", "008"] already means ["7", "8"]. So the boundary
        # spelling is admitted here, and the one past it is not.
        spelled = source.cast(pl.Int64, strict=False)
        if bool(spelled.is_null().eq(source.is_null()).all()):
            valid = spelled.is_null() | (
                (spelled >= -exact_integer_limit) & (spelled <= exact_integer_limit)
            )
            return bool(valid.all())
        # Any other spelling is only worth its float, and at 2**53 a float
        # stops telling neighbours apart -- "9007199254740992.0" and
        # "9007199254740993.0" are one double. Those keep the strict range
        # rather than certifying a conversion that folds two keys into one.
        valid = converted.is_null() | (
            converted.is_finite() & (converted.abs() < exact_integer_limit)
        )
        return bool(valid.all())
    return True


# The largest value a signed 64-bit integer holds. Every integer a lookup
# key travels as -- in the frame, in the assumption payload, in the content
# hash -- is that width, so this is where an unsigned key stops having an
# exact name rather than where it stops being unsigned.
_I64_MAX = 2**63 - 1


def _unsigned_key_refusal(column: str, offending: int) -> str:
    """Word the refusal for an unsigned key too large to name exactly."""
    return (
        f"Assumption table key column {column!r} holds {offending}, which is "
        "larger than the signed 64-bit integer a lookup key travels as.\n"
        "\n"
        "A key has to be named exactly or two keys become one, and above "
        f"{_I64_MAX} there is no exact numeric name left: a float would round "
        "neighbouring keys together and hand one rate to two policies.\n"
        "\n"
        "Keep the digits by holding the key as text -- cast the column with "
        ".cast(pl.String), and look it up with text keys too -- or cast it "
        "with .cast(pl.Int64) if the values really are within range."
    )


def _signed_key_dtype(source: pl.Series, column: str) -> type[pl.DataType]:
    """Name an unsigned key column's signed type, or refuse the value that has none.

    An unsigned column is not a problem in itself: the question is only
    whether its values fit the signed width every key travels in. That is a
    question about the data, so it is measured rather than assumed -- a
    ``UInt64`` of policy numbers is an ``Int64`` of policy numbers, and only
    a value past the signed maximum has no name to be given.
    """
    largest = source.max()
    if largest is not None and int(largest) > _I64_MAX:  # type: ignore[arg-type]
        raise UnmappedDtypeError(_unsigned_key_refusal(column, int(largest)))  # type: ignore[arg-type]
    return pl.Int64


def _normalise_key_dtypes(df: pl.DataFrame, key_columns: list[str]) -> pl.DataFrame:
    """Give each lookup key column the widest exact type the lookup can use.

    f64 first, because that is the type the native lookup is fastest on and
    the one most keys fit: ages, durations, and text spellings of ordinary
    numbers all land there without losing a digit. A column whose values
    would not survive the round trip keeps its own type instead -- adjacent
    integers above 2**53, and text that means more than its float.

    The one type that cannot simply be kept is an unsigned 64-bit integer,
    because nothing downstream has a name for it: the payload, the content
    hash and the graph all carry integers as i64. Such a column is given the
    signed name its values do fit, and only a value past the signed maximum
    is refused -- by its own value, so the author can see which key it was.

    Args:
        df: DataFrame to process
        key_columns: List of key column names to attempt conversion

    Returns:
        pl.DataFrame: DataFrame with converted key columns

    Raises:
        UnmappedDtypeError: An unsigned key column holds a value above the
            signed 64-bit maximum, which no exact numeric name can carry.

    """
    conversions: dict[str, type[pl.DataType]] = {}
    for col in key_columns:
        if col not in df.columns:
            continue

        try:
            # Try to convert to f64 - this will fail if data can't be converted
            converted = df[col].cast(
                pl.Float64,
                strict=True,
            )  # Check castability without assignment

            if not _keys_fit_f64_range(df[col], converted):
                logger.debug(
                    f"Keeping key column '{col}' as {df[col].dtype} "
                    "(f64 conversion would change key identity)",
                )
                if df[col].dtype.is_unsigned_integer():
                    conversions[col] = _signed_key_dtype(df[col], col)
                continue
            conversions[col] = pl.Float64
            logger.debug(f"Marking key column '{col}' for f64 conversion")
        except (pl.exceptions.ComputeError, pl.exceptions.InvalidOperationError):
            # Keep original type if conversion fails
            logger.debug(
                f"Keeping key column '{col}' as {df[col].dtype} "
                "(f64 conversion not possible)",
            )
            continue

    if conversions:
        df = df.with_columns(
            [pl.col(col).cast(dtype) for col, dtype in conversions.items()],
        )
        logger.debug(
            f"Normalised {len(conversions)} key columns: "
            f"{ {col: str(dtype) for col, dtype in conversions.items()} }",
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
    msg = (
        f"Specified overflow column '{overflow}' not found in wide columns: {wide_cols}"
    )
    raise ValueError(msg)
