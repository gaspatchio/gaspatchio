"""
Assumption loading module - provides load_assumptions function.

This module implements the new assumption loading API that supports both
curve (1D) and wide table (2D) formats with automatic overflow handling.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Literal, Union

import polars as pl

from ..registry import TableRegistry

# Global metadata storage for assumption tables
_TABLE_METADATA: Dict[str, Dict[str, Any]] = {}


def get_table_metadata(table_name: str) -> Dict[str, Any] | None:
    """Retrieve metadata for a registered table.

    Args:
        table_name: Name of the table to get metadata for

    Returns:
        dict | None: Copy of metadata dictionary if found, None otherwise
    """
    metadata = _TABLE_METADATA.get(table_name)
    if metadata is not None:
        return metadata.copy()
    return None


def list_tables_with_metadata() -> Dict[str, Dict[str, Any]]:
    """List all tables that have metadata stored.

    Returns:
        dict: Dictionary mapping table names to their metadata
    """
    return _TABLE_METADATA.copy()


def _materialise(source: Union[str, Path, pl.DataFrame]) -> pl.DataFrame:
    """Materialize data from various sources into a Polars DataFrame.

    Args:
        source: Data source - file path (str/Path) or existing DataFrame

    Returns:
        pl.DataFrame: The materialized DataFrame

    Raises:
        FileNotFoundError: If source file doesn't exist
        ValueError: If file format is not supported or data is invalid
    """
    if isinstance(source, pl.DataFrame):
        return source

    # Convert to Path for easier handling
    if isinstance(source, str):
        source = Path(source)

    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    # Detect file type and read appropriately
    suffix = source.suffix.lower()

    if suffix == ".csv":
        try:
            return pl.read_csv(source, infer_schema_length=10000)
        except Exception as e:
            raise ValueError(f"Failed to read CSV file {source}: {e}") from e
    elif suffix == ".parquet":
        try:
            return pl.read_parquet(source)
        except Exception as e:
            raise ValueError(f"Failed to read Parquet file {source}: {e}") from e
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported formats: .csv, .parquet"
        )


def _analyse_shape(
    df: pl.DataFrame, id: Union[str, list[str], None]
) -> tuple[list[str], list[str], list[str], bool]:
    """Analyse DataFrame shape and identify id and numeric columns.

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
        raise ValueError("DataFrame is empty")

    # Get all column names and their types
    all_columns = df.columns
    numeric_columns = [col for col in all_columns if df[col].dtype.is_numeric()]
    non_numeric_columns = [col for col in all_columns if not df[col].dtype.is_numeric()]

    # Process id column specification
    if id is None:
        # Auto-detect: prioritize non-numeric columns first, then common id column names
        if non_numeric_columns:
            id_columns = [non_numeric_columns[0]]  # Take first non-numeric column
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
            else:
                # Fallback: use first column as id if all else fails
                id_columns = [all_columns[0]]
    elif isinstance(id, str):
        # Split string on comma only, not whitespace (to handle column names with spaces)
        if "," in id:
            id_columns = [col.strip() for col in id.split(",") if col.strip()]
        else:
            # Single column name - don't split
            id_columns = [id.strip()]
    else:  # isinstance(id, list)
        id_columns = [str(col) for col in id]

    # Validate that all id columns exist
    missing_columns = [col for col in id_columns if col not in all_columns]
    if missing_columns:
        raise ValueError(
            f"Specified id columns not found in DataFrame: {missing_columns}"
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

    return id_columns, remaining_numeric, remaining_non_numeric, is_wide


def _detect_overflow_column(
    wide_cols: list[str], overflow: Union[str, None]
) -> Union[str, None]:
    """Detect overflow column in wide table columns.

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
    else:
        # Explicit overflow column name specified
        if overflow in wide_cols:
            return overflow
        else:
            raise ValueError(
                f"Specified overflow column '{overflow}' not found in wide columns: {wide_cols}"
            )


def _get_max_numeric_duration(
    wide_cols: list[str], exclude_overflow: Union[str, None] = None
) -> Union[int, None]:
    """Get the maximum numeric value among wide columns.

    Args:
        wide_cols: List of wide column names
        exclude_overflow: Overflow column to exclude from search

    Returns:
        int | None: Maximum numeric value found, or None if no numeric columns
    """
    max_duration = None

    for col in wide_cols:
        # Skip overflow column if specified
        if exclude_overflow is not None and col == exclude_overflow:
            continue

        # Try to convert to integer directly first (for pure numeric columns like "1", "2", "3")
        try:
            duration = int(col)
            if max_duration is None or duration > max_duration:
                max_duration = duration
            continue
        except ValueError:
            pass

        # If direct conversion fails, try to extract numeric parts (for columns like "Duration_1", "Year_5")
        numeric_matches = re.findall(r"\d+", col)
        if numeric_matches:
            # Take the last numeric part found (handles cases like "Duration_1_SubPart_2" -> 2)
            try:
                duration = int(numeric_matches[-1])
                if max_duration is None or duration > max_duration:
                    max_duration = duration
            except ValueError:
                # Skip if conversion still fails
                continue

    return max_duration


def _tidy_curve(df: pl.DataFrame, id_cols: list[str], value: str) -> pl.DataFrame:
    """Tidy a curve table (single numeric column) with proper column naming.

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


def _create_overflow_expansion(
    df: pl.DataFrame,
    id_cols: list[str],
    overflow_col: str,
    value: str,
    start_value: int,
    max_value: int,
) -> pl.DataFrame:
    """Create overflow expansion rows for the specified range.

    Args:
        df: Melted DataFrame containing overflow data
        id_cols: List of id column names
        overflow_col: Name of the overflow column in the variable column
        value: Name of the value column
        start_value: Starting duration value for expansion
        max_value: Maximum duration value for expansion

    Returns:
        pl.DataFrame: Expanded DataFrame with additional rows for the range
    """
    if start_value > max_value:
        # No expansion needed - return empty DataFrame with correct schema
        return pl.DataFrame(schema=df.schema).clear()

    # Filter to only overflow rows
    overflow_data = df.filter(pl.col("variable") == overflow_col)

    if overflow_data.is_empty():
        # No overflow data to expand - return empty DataFrame with correct schema
        return pl.DataFrame(schema=df.schema).clear()

    # Create expanded rows for each duration in range
    expansion_rows = []
    for duration in range(start_value, max_value + 1):
        # Create a copy of overflow data with new variable values
        expanded = overflow_data.with_columns(pl.lit(str(duration)).alias("variable"))
        expansion_rows.append(expanded)

    # Concatenate all expansion rows
    if expansion_rows:
        return pl.concat(expansion_rows)
    else:
        return pl.DataFrame(schema=df.schema).clear()


def _tidy_wide_with_overflow_expansion(
    df: pl.DataFrame,
    id_cols: list[str],
    wide_cols: list[str],
    value: str,
    overflow: Union[str, None] = None,
    max_overflow: int = 200,
) -> pl.DataFrame:
    """Tidy a wide table with overflow expansion.

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


def load_assumptions(
    name: str,
    source: Union[str, Path, pl.DataFrame],
    *,
    id: Union[str, list[str], None] = None,
    value: str = "rate",
    value_vars: Union[list[str], None] = None,
    overflow: Union[Literal["auto"], str, None] = "auto",
    max_overflow: int = 200,
    metadata: dict[str, Any] | None = None,
) -> pl.DataFrame:
    """Load and register assumption tables from various sources.

    This function provides a unified interface for loading actuarial assumption
    tables from CSV files, Parquet files, or Polars DataFrames. It automatically
    detects the table format (curve vs wide table) and handles data transformation,
    overflow expansion, and registration for high-performance lookups.

    Args:
        name: Unique name for the assumption table. Used for lookups via
            assumption_lookup(). Must not conflict with existing table names.
        source: Data source - file path (str/Path) or Polars DataFrame.
            Supported formats: .csv, .parquet
        id: Column name(s) to use as lookup keys. If None, auto-detects the
            first non-numeric column(s). Can be a single column name or list
            of column names for composite keys.
        value: Name for the value column in the output table. Defaults to "rate".
            For wide tables, this becomes the column name after melting.
        value_vars: For wide tables, specific columns to melt. If None, melts all
            numeric columns (excluding id columns). Useful for selective melting
            like ["MNS", "FNS", "MS", "FS"] from gender/smoking combinations.
        overflow: Overflow handling for wide tables. Options:
            - "auto": Auto-detect overflow columns (e.g., "Ult.", "Ultimate")
            - str: Explicit overflow column name
            - None: No overflow handling
        max_overflow: Maximum duration to expand overflow values to.
            Only used when overflow handling is enabled. Defaults to 200.
        metadata: Optional metadata dictionary to store with the table.
            Can be retrieved later for documentation purposes.

    Returns:
        pl.DataFrame: The processed and registered assumption table.
            For curves: [id_cols..., value_col]
            For wide tables: [id_cols..., "variable", value_col]

    Raises:
        ValueError: For invalid parameters or malformed data.
        FileNotFoundError: If source file doesn't exist.

    Examples:
        Basic curve loading:
        >>> import polars as pl
        >>> df = pl.DataFrame({"Age": [20, 21], "qx": [0.001, 0.0011]})
        >>> result = load_assumptions("curve_test", df, value="qx")
        >>> result.columns
        ['Age', 'qx']
        >>> len(result)
        2

        Wide table loading:
        >>> wide_df = pl.DataFrame({
        ...     "Age": [20, 21],
        ...     "1": [0.001, 0.0011],
        ...     "2": [0.0008, 0.0009]
        ... })
        >>> result = load_assumptions("wide_test", wide_df)
        >>> result.columns
        ['Age', 'variable', 'rate']
        >>> len(result)  # 2 ages * 2 durations
        4

        Overflow handling:
        >>> overflow_df = pl.DataFrame({
        ...     "Age": [20, 21],
        ...     "1": [0.001, 0.0011],
        ...     "Ult.": [0.0005, 0.0006]
        ... })
        >>> result = load_assumptions("overflow_test", overflow_df,
        ...                          overflow="Ult.", max_overflow=3)
        >>> len(result)  # 2 ages * (2 original + 2 expanded) = 8
        8
    """

    # Parameter validation
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")

    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty string")

    if value_vars is not None and not isinstance(value_vars, list):
        raise ValueError("value_vars must be a list of column names or None")

    if not isinstance(max_overflow, int) or max_overflow < 1 or max_overflow > 1000:
        raise ValueError("max_overflow must be an integer between 1 and 1000")

    # Validate overflow parameter
    if overflow is not None and overflow != "auto" and not isinstance(overflow, str):
        raise ValueError("overflow must be 'auto', a column name string, or None")

    # Validate metadata parameter
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary or None")

    # Step 1: Materialize the data
    try:
        df = _materialise(source)
    except (FileNotFoundError, ValueError) as e:
        raise e  # Re-raise with original message

    # Step 2: Analyse the shape and identify columns
    try:
        id_columns, numeric_columns, text_columns, is_wide = _analyse_shape(df, id)
    except ValueError as e:
        raise ValueError(f"Failed to analyse DataFrame structure: {e}") from e

    # Handle value_vars for selective melting
    if value_vars is not None:
        # Validate that all value_vars exist in the DataFrame
        missing_value_vars = [col for col in value_vars if col not in df.columns]
        if missing_value_vars:
            raise ValueError(
                f"Specified value_vars columns not found in DataFrame: {missing_value_vars}"
            )

        # Use value_vars instead of auto-detected numeric columns
        columns_to_melt = value_vars
        # Force wide table detection when value_vars is specified (even for single column)
        is_wide = True
    else:
        columns_to_melt = numeric_columns

    # Determine table type and process accordingly
    if len(columns_to_melt) == 0:
        raise ValueError(
            "No columns found to use as values. "
            "Specify value_vars or ensure there are numeric columns for values."
        )
    elif not is_wide:
        # Curve table - single numeric column
        try:
            tidy_df = _tidy_curve(df, id_columns, value)
        except ValueError as e:
            raise e  # Re-raise with original message

        # Register with TableRegistry
        registry = TableRegistry()
        registry.register_table(
            name=name,
            df=tidy_df,
            keys=id_columns,
            value_column=value,
        )

        # Store metadata if provided
        if metadata is not None:
            _TABLE_METADATA[name] = metadata.copy()

        return tidy_df
    else:
        # Wide table - multiple value columns
        # For overflow detection, use the columns that will actually be melted
        if value_vars is not None:
            # When value_vars is specified, only look for overflow in those columns
            overflow_detection_cols = columns_to_melt
        else:
            # When auto-detecting, combine numeric and text columns for overflow detection
            overflow_detection_cols = numeric_columns + text_columns

        # Handle overflow detection if enabled
        overflow_col = None
        if overflow is not None:
            try:
                overflow_col = _detect_overflow_column(
                    overflow_detection_cols, overflow
                )
            except ValueError as e:
                raise e  # Re-raise with original message

        # Get max numeric duration for potential expansion (even if not used yet)
        max_numeric_duration = _get_max_numeric_duration(
            overflow_detection_cols, exclude_overflow=overflow_col
        )

        try:
            tidy_df = _tidy_wide_with_overflow_expansion(
                df, id_columns, columns_to_melt, value, overflow, max_overflow
            )
        except ValueError as e:
            raise e  # Re-raise with original message

        # Register with TableRegistry for wide tables
        registry = TableRegistry()
        registry.register_table(
            name=name,
            df=tidy_df,
            keys=id_columns + ["variable"],  # Include variable column in keys
            value_column=value,
        )

        # Store metadata if provided
        if metadata is not None:
            _TABLE_METADATA[name] = metadata.copy()

        return tidy_df
