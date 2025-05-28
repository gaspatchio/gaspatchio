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
from loguru import logger

from .._internal import PyAssumptionTableRegistry

# Global metadata storage for assumption tables
_TABLE_METADATA: Dict[str, Dict[str, Any]] = {}


def get_table_metadata(table_name: str) -> Dict[str, Any] | None:
    """Retrieve metadata for a registered assumption table.

    Actuarial assumption tables often contain important metadata about their
    source, creation date, and business context. This function allows you to
    retrieve the metadata dictionary that was stored when the table was loaded
    using `load_assumptions()`.

    !!! note "When to use"
        *   Documenting assumption table sources and versions for audit trails.
        *   Retrieving business metadata like effective dates, basis descriptions, or source systems.
        *   Validating that the correct assumption table version is being used in models.
        *   Creating assumption inventory reports that show table metadata alongside model results.

    Args:
        table_name: Name of the table to get metadata for

    Returns:
        dict | None: Copy of metadata dictionary if found, None otherwise

    Examples
    --------
    Scalar example - Retrieving Mortality Table Metadata::

        Scenario: You've loaded a mortality table with metadata and want to verify its source information.

        ```python
        import polars as pl
        from gaspatchio_core.assumptions import load_assumptions, get_table_metadata

        # Load table with metadata
        mortality_data = pl.DataFrame({
            "age": [20, 21, 22],
            "qx": [0.001, 0.0011, 0.0012]
        })

        metadata = {
            "source": "2012 IAM Mortality Tables",
            "effective_date": "2013-01-01",
            "table_type": "select_ultimate"
        }

        load_assumptions("mortality_2012", mortality_data, metadata=metadata)

        # Retrieve metadata
        retrieved_metadata = get_table_metadata("mortality_2012")
        print(retrieved_metadata["source"])
        ```

        ```
        2012 IAM Mortality Tables
        ```

    Vector (list) example – Multiple Table Metadata Comparison::

        Scenario: You want to compare metadata across multiple assumption tables to ensure consistency.

        ```python
        import polars as pl
        from gaspatchio_core.assumptions import load_assumptions, get_table_metadata

        # Load multiple tables with different metadata
        for year in [2012, 2017]:
            data = pl.DataFrame({
                "age": [20, 21],
                "qx": [0.001 * (1 + (year-2012)*0.1), 0.0011 * (1 + (year-2012)*0.1)]
            })

            metadata = {
                "source": f"{year} IAM Mortality Tables",
                "year": year
            }

            load_assumptions(f"mortality_{year}", data, metadata=metadata)

        # Compare metadata
        table_names = ["mortality_2012", "mortality_2017"]
        for name in table_names:
            meta = get_table_metadata(name)
            if meta:
                print(f"{name}: {meta['source']}")
        ```

        ```
        mortality_2012: 2012 IAM Mortality Tables
        mortality_2017: 2017 IAM Mortality Tables
        ```
    """
    metadata = _TABLE_METADATA.get(table_name)
    if metadata is not None:
        return metadata.copy()
    return None


def list_tables_with_metadata() -> Dict[str, Dict[str, Any]]:
    """List all assumption tables that have metadata stored.

    This function provides an inventory of all loaded assumption tables that
    have associated metadata. It's useful for discovering what tables are
    available and understanding their business context without having to
    remember specific table names.

    !!! note "When to use"
        *   Creating assumption inventory reports for actuarial documentation.
        *   Auditing which assumption tables are currently loaded in your analysis session.
        *   Discovering available tables when working with unfamiliar models or datasets.
        *   Building assumption governance dashboards that track table usage and metadata.

    Returns:
        dict: Dictionary mapping table names to their metadata

    Examples
    --------
    Scalar example - Basic Inventory Report::

        Scenario: You want to see all loaded assumption tables and their basic information.

        ```python
        import polars as pl
        from gaspatchio_core.assumptions import load_assumptions, list_tables_with_metadata

        # Load a few tables with metadata
        mortality_data = pl.DataFrame({"age": [20, 21], "qx": [0.001, 0.0011]})
        load_assumptions("mortality_2012", mortality_data,
                        metadata={"source": "2012 IAM", "type": "mortality"})

        lapse_data = pl.DataFrame({"duration": [1, 2], "lapse_rate": [0.05, 0.03]})
        load_assumptions("lapse_ultimate", lapse_data,
                        metadata={"source": "Company Experience", "type": "lapse"})

        # List all tables with metadata
        all_tables = list_tables_with_metadata()
        print(f"Found {len(all_tables)} tables with metadata")
        ```

        ```
        Found 2 tables with metadata
        ```

    Vector (list) example – Metadata Reporting by Type::

        Scenario: You want to group assumption tables by their type for documentation purposes.

        ```python
        import polars as pl
        from gaspatchio_core.assumptions import load_assumptions, list_tables_with_metadata

        # Load multiple tables with type metadata
        tables_info = [
            ("mortality_select", {"age": [20, 21], "qx": [0.001, 0.0011]}, {"type": "mortality"}),
            ("mortality_ultimate", {"age": [20, 21], "qx": [0.0008, 0.0009]}, {"type": "mortality"}),
            ("lapse_early", {"duration": [1, 2], "rate": [0.05, 0.03]}, {"type": "lapse"}),
        ]

        for name, data, metadata in tables_info:
            df = pl.DataFrame(data)
            load_assumptions(name, df, metadata=metadata)

        # Group by type
        all_tables = list_tables_with_metadata()
        type_groups = {}
        for table_name, metadata in all_tables.items():
            table_type = metadata.get("type", "unknown")
            if table_type not in type_groups:
                type_groups[table_type] = []
            type_groups[table_type].append(table_name)

        for table_type, table_names in type_groups.items():
            print(f"{table_type}: {len(table_names)} tables")
        ```

        ```
        mortality: 2 tables
        lapse: 1 tables
        ```
    """
    return _TABLE_METADATA.copy()


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
            f"Source file not found: {source}\n"
            f"Suggestions:\n"
            f"  • Check the file path is correct\n"
            f"  • Ensure the file exists in the current working directory: {Path.cwd()}\n"
            f"  • Use absolute path if the file is in a different directory\n"
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
                f"Failed to read CSV file {source}: {e}\n"
                f"Suggestions:\n"
                f"  • Check the CSV format is valid (proper delimiters, headers)\n"
                f"  • Ensure text encoding is UTF-8\n"
                f"  • Try opening the file in a text editor to verify format\n"
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
                f"Failed to read Parquet file {source}: {e}\n"
                f"Suggestions:\n"
                f"  • Check the Parquet file is not corrupted\n"
                f"  • Ensure the file was created with a compatible Parquet version\n"
                f"  • Try reading with a different Parquet reader to verify integrity"
            ) from e
        except Exception as e:
            raise ValueError(
                f"Unexpected error reading Parquet file {source}: {e}"
            ) from e
    else:
        raise ValueError(
            f"Unsupported file format: {suffix}. Supported formats: .csv, .parquet\n"
            f"Suggestions:\n"
            f"  • Convert your data to CSV or Parquet format\n"
            f"  • Use pl.DataFrame() to create data programmatically\n"
            f"  • Check file extension matches the actual format"
        )


def _analyse_shape(
    df: pl.DataFrame, id: Union[str, list[str], None]
) -> tuple[list[str], list[str], list[str], bool]:
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


def _detect_overflow_column(
    wide_cols: list[str], overflow: Union[str, None]
) -> Union[str, None]:
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

    This internal function extracts numeric duration values from column names
    to determine the maximum explicitly modeled duration in a wide table. It
    handles various column naming conventions including pure numeric columns
    ("1", "2", "3") and mixed formats ("Duration_1", "Year_5"). This maximum
    value is used to determine the starting point for overflow expansion in
    assumption tables.

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
    conversions = {}

    for col in key_columns:
        if col not in df.columns:
            continue

        try:
            # Try to convert to f64 - this will fail if data can't be converted
            converted = df[col].cast(pl.Float64, strict=True)
            conversions[col] = pl.Float64
            logger.debug(f"Converting key column '{col}' to f64")
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


def _create_overflow_expansion(
    df: pl.DataFrame,
    id_cols: list[str],
    overflow_col: str,
    value: str,
    start_value: int,
    max_value: int,
) -> pl.DataFrame:
    """Create overflow expansion rows for the specified range.

    This internal function generates additional rows for assumption tables
    by replicating overflow rates across a range of duration values. It
    takes the overflow column values and creates new rows for each duration
    from start_value to max_value, effectively extending the assumption
    table coverage beyond the explicitly modeled durations. This is common
    in actuarial tables where ultimate rates apply to extended periods.

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

    # Calculate expansion size for memory warning
    expansion_range = max_value - start_value + 1
    original_rows = len(overflow_data)
    total_new_rows = original_rows * expansion_range

    # Memory warning for large expansions
    if total_new_rows > 1_000_000:
        logger.warning(
            f"Large overflow expansion detected: {total_new_rows:,} rows will be created "
            f"({original_rows:,} overflow rows × {expansion_range} duration values). "
            f"This may consume significant memory. Consider reducing max_overflow parameter."
        )
    elif total_new_rows > 100_000:
        logger.info(
            f"Overflow expansion creating {total_new_rows:,} rows "
            f"({original_rows:,} overflow rows × {expansion_range} duration values)"
        )

    # Create expanded rows for each duration in range
    expansion_rows = []
    for duration in range(start_value, max_value + 1):
        # Create a copy of overflow data with new variable values
        expanded = overflow_data.with_columns(pl.lit(str(duration)).alias("variable"))
        expansion_rows.append(expanded)

    # Concatenate all expansion rows
    if expansion_rows:
        result = pl.concat(expansion_rows)
        logger.debug(
            f"Created {len(result)} overflow expansion rows for range {start_value}-{max_value}"
        )
        return result
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
    lookup_keys: Union[list[str], None] = None,
) -> pl.DataFrame:
    """Load and register assumption tables from various sources.

    This function provides a unified interface for loading actuarial assumption
    tables from CSV files, Parquet files, or Polars DataFrames. It automatically
    detects the table format (curve vs wide table) and handles data transformation,
    overflow expansion, and registration for high-performance lookups.

    !!! note "When to use"
        *   Loading mortality tables for life insurance pricing and reserving calculations.
        *   Importing lapse rate assumptions for policy projection models.
        *   Setting up morbidity tables for disability insurance or critical illness products.
        *   Loading economic scenario assumptions like interest rates or inflation curves.
        *   Preparing assumption tables for IFRS 17 or Solvency II regulatory models.

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
        lookup_keys: Optional list of custom column names to use for lookups.
            If provided, the processed table columns will be renamed to match
            these names for clearer lookup code. For wide tables, should include
            both id column names and the variable column name.
            Example: ["issue_age", "year_lookup"] for a 2-key lookup.

    Returns:
        pl.DataFrame: The processed and registered assumption table.
            For curves: [id_cols..., value_col]
            For wide tables: [id_cols..., "variable", value_col]

    Raises:
        ValueError: For invalid parameters or malformed data.
        FileNotFoundError: If source file doesn't exist.

    Examples
    --------
    Basic curve loading::

        Scenario: Loading an interest rate curve for pricing calculations.

        | Term | Rate  | Description                    |
        |------|-------|--------------------------------|
        | 1    | 0.025 | 1-year Treasury rate          |
        | 5    | 0.035 | 5-year Treasury rate          |
        | 10   | 0.042 | 10-year Treasury rate         |

        ```python
        import polars as pl
        import gaspatchio_core as gs

        df = pl.DataFrame({
            "term": [1, 5, 10],
            "interest_rate": [0.025, 0.035, 0.042]
        })
        gs.load_assumptions("treasury_curve", df, value="interest_rate")

        # Lookup interest rates for specific terms
        rate = gs.lookup_assumptions("treasury_curve", {"term": 5})
        print(rate)
        ```

        ```
        0.035
        ```

    Wide table loading::

        Scenario: Loading a mortality table with separate columns for male and female rates.

        | Age | Male_qx | Female_qx | Description              |
        |-----|---------|-----------|--------------------------|
        | 30  | 0.00074 | 0.00049   | Age 30 mortality rates   |
        | 31  | 0.00081 | 0.00053   | Age 31 mortality rates   |
        | 32  | 0.00089 | 0.00058   | Age 32 mortality rates   |

        ```python
        import polars as pl
        import gaspatchio_core as gs

        mortality_df = pl.DataFrame({
            "age": [30, 31, 32],
            "male_qx": [0.00074, 0.00081, 0.00089],
            "female_qx": [0.00049, 0.00053, 0.00058]
        })
        gs.load_assumptions("mortality_table", mortality_df)

        # Lookup male mortality rate for age 31
        qx_male = gs.lookup_assumptions("mortality_table", {"age": 31, "variable": "male_qx"})
        print(qx_male)
        ```

        ```
        0.00081
        ```

    Overflow handling::

        Scenario: Loading a morbidity table with ultimate rates that need to be extended.

        | Age | Year_1 | Year_2 | Ultimate | Description                    |
        |-----|--------|--------|----------|--------------------------------|
        | 40  | 0.0120 | 0.0110 | 0.0095   | Age 40 disability rates       |
        | 41  | 0.0135 | 0.0125 | 0.0105   | Age 41 disability rates       |

        ```python
        import polars as pl
        import gaspatchio_core as gs

        morbidity_df = pl.DataFrame({
            "age": [40, 41],
            "1": [0.0120, 0.0135],
            "2": [0.0110, 0.0125],
            "Ultimate": [0.0095, 0.0105]
        })
        gs.load_assumptions("morbidity_table", morbidity_df,
                           overflow="Ultimate", max_overflow=5)

        # Lookup expanded ultimate rate for year 4 (should use ultimate value)
        rate_year4 = gs.lookup_assumptions("morbidity_table", {"age": 40, "variable": "4"})
        print(rate_year4)
        ```

        ```
        0.0095
        ```

    Custom lookup keys::

        Scenario: Loading a mortality table with custom column names for clearer lookup code.

        ```python
        import polars as pl
        import gaspatchio_core as gs

        mortality_df = pl.DataFrame({
            "age": [30, 31, 32],
            "1": [0.00074, 0.00081, 0.00089],
            "2": [0.00049, 0.00053, 0.00058],
            "Ultimate": [0.00045, 0.00048, 0.00052]
        })

        # Load with custom lookup key names
        gs.load_assumptions("mortality_table", mortality_df,
                           lookup_keys=["issue_age", "year_lookup"],
                           overflow="Ultimate")

        # Now use the custom key names for lookups
        qx = gs.assumption_lookup("issue_age", "year_lookup",
                                 table_name="mortality_table")
        ```
    """

    logger.info(f"Loading assumption table '{name}'")

    # Enhanced parameter validation with specific error messages
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            "name must be a non-empty string\n"
            "Suggestions:\n"
            "  • Use descriptive names like 'mortality_2012' or 'lapse_ultimate'\n"
            "  • Avoid empty strings or whitespace-only names"
        )

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "value must be a non-empty string\n"
            "Suggestions:\n"
            "  • Use descriptive names like 'rate', 'qx', 'probability'\n"
            "  • Avoid empty strings or whitespace-only names"
        )

    if value_vars is not None and not isinstance(value_vars, list):
        raise ValueError(
            "value_vars must be a list of column names or None\n"
            "Examples:\n"
            "  • value_vars=['Male', 'Female'] for gender-specific columns\n"
            "  • value_vars=['1', '2', '3', 'Ultimate'] for duration columns"
        )

    if not isinstance(max_overflow, int) or max_overflow < 1 or max_overflow > 1000:
        raise ValueError(
            "max_overflow must be an integer between 1 and 1000\n"
            "Suggestions:\n"
            "  • Use 200 for typical actuarial projections\n"
            "  • Use 100 for shorter-term analyses\n"
            "  • Use 500+ only for very long-term projections"
        )

    # Validate overflow parameter
    if overflow is not None and overflow != "auto" and not isinstance(overflow, str):
        raise ValueError(
            "overflow must be 'auto', a column name string, or None\n"
            "Examples:\n"
            "  • overflow='auto' for automatic detection\n"
            "  • overflow='Ultimate' for explicit overflow column\n"
            "  • overflow=None to disable overflow handling"
        )

    # Validate metadata parameter
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError(
            "metadata must be a dictionary or None\n"
            "Examples:\n"
            "  • metadata={'source': '2012 IAM Tables', 'version': '1.0'}\n"
            "  • metadata={'effective_date': '2013-01-01', 'basis': 'select_ultimate'}"
        )

    # Validate lookup_keys parameter
    if lookup_keys is not None:
        if not isinstance(lookup_keys, list):
            raise ValueError(
                "lookup_keys must be a list of strings or None\n"
                "Examples:\n"
                "  • lookup_keys=['issue_age', 'year_lookup'] for 2-key lookup\n"
                "  • lookup_keys=['age'] for single-key lookup"
            )
        if not all(isinstance(key, str) and key.strip() for key in lookup_keys):
            raise ValueError(
                "All lookup_keys must be non-empty strings\n"
                "Examples:\n"
                "  • lookup_keys=['issue_age', 'year_lookup']\n"
                "  • lookup_keys=['age', 'duration']"
            )

    # Step 1: Materialize the data
    try:
        df = _materialise(source)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load data for table '{name}': {e}")
        raise

    # Step 2: Analyse the shape and identify columns
    try:
        id_columns, numeric_columns, text_columns, is_wide = _analyse_shape(df, id)
    except ValueError as e:
        logger.error(f"Failed to analyze table structure for '{name}': {e}")
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

        # Apply custom lookup keys if provided
        if lookup_keys is not None:
            expected_keys = len(id_columns)
            if len(lookup_keys) != expected_keys:
                raise ValueError(
                    f"lookup_keys length ({len(lookup_keys)}) must match number of id columns ({expected_keys}) for curve tables\n"
                    f"Expected: {expected_keys} keys for id columns: {id_columns}\n"
                    f"Provided: {len(lookup_keys)} keys: {lookup_keys}"
                )

            # Create rename mapping for id columns
            rename_mapping = dict(zip(id_columns, lookup_keys))
            tidy_df = tidy_df.rename(rename_mapping)
            final_keys = lookup_keys
        else:
            final_keys = id_columns

        # Convert key columns to f64 where possible for optimal lookup performance
        tidy_df = _convert_keys_to_f64(tidy_df, final_keys)

        # Register with TableRegistry
        registry = PyAssumptionTableRegistry()
        registry.register_table(
            name=name,
            df=tidy_df,
            keys=final_keys,
            value_column=value,
        )

        # Store metadata if provided
        if metadata is not None:
            _TABLE_METADATA[name] = metadata.copy()

        # Success logging for curve tables
        logger.info(
            f"Successfully loaded curve table '{name}': "
            f"{len(tidy_df)} rows, {len(id_columns)} id columns"
        )

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

        # Apply custom lookup keys if provided
        if lookup_keys is not None:
            expected_keys = len(id_columns) + 1  # +1 for variable column
            if len(lookup_keys) != expected_keys:
                raise ValueError(
                    f"lookup_keys length ({len(lookup_keys)}) must match number of lookup columns ({expected_keys}) for wide tables\n"
                    f"Expected: {expected_keys} keys for id columns + variable: {id_columns + ['variable']}\n"
                    f"Provided: {len(lookup_keys)} keys: {lookup_keys}"
                )

            # Create rename mapping for id columns + variable column
            original_keys = id_columns + ["variable"]
            rename_mapping = dict(zip(original_keys, lookup_keys))
            tidy_df = tidy_df.rename(rename_mapping)
            final_keys = lookup_keys
        else:
            final_keys = id_columns + ["variable"]  # Include variable column in keys

        # Convert key columns to f64 where possible for optimal lookup performance
        tidy_df = _convert_keys_to_f64(tidy_df, final_keys)

        # Register with TableRegistry for wide tables
        registry = PyAssumptionTableRegistry()
        registry.register_table(
            name=name,
            df=tidy_df,
            keys=final_keys,
            value_column=value,
        )

        # Store metadata if provided
        if metadata is not None:
            _TABLE_METADATA[name] = metadata.copy()

        # Success logging for wide tables
        expanded_info = ""
        if overflow is not None and overflow_col is not None:
            expanded_info = f", overflow expanded to {max_overflow}"

        logger.info(
            f"Successfully loaded wide table '{name}': "
            f"{len(tidy_df)} rows, {len(id_columns)} id columns, "
            f"{len(columns_to_melt)} value columns{expanded_info}"
        )

        return tidy_df
