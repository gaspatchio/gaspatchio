"""
Public API for assumption loading and metadata management.

This module provides the primary interface for loading actuarial assumption
tables, handling various formats, and managing associated metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal, Union

import polars as pl
from loguru import logger

from .._internal import PyAssumptionTableRegistry
from ._analysis import _analyse_shape
from ._config import _get_table_config, _store_table_config
from ._overflow import (
    _detect_overflow_column,  # Keep for now, may be used by load_assumptions directly
)
from ._source import _materialise
from ._transform import (
    _convert_keys_to_f64,
    _tidy_curve,
    _tidy_wide_with_overflow_expansion,
)
from ._validation import (
    _validate_additional_keys,
    _validate_append_compatibility,
    _validate_table_exists_for_append,
)

# Global metadata storage for assumption tables
_TABLE_METADATA: Dict[str, Dict[str, Any]] = {}


def _validate_load_assumptions_params(
    name: str,
    value: str,
    value_vars: Union[list[str], None],
    max_overflow: int,
    overflow: Union[Literal["auto"], str, None],
    metadata: dict[str, Any] | None,
    lookup_keys: Union[list[str], None],
    additional_keys: dict[str, Any] | None,
) -> None:
    """Validate parameters for the load_assumptions function.

    Internal helper function that validates all input parameters to ensure they
    meet the requirements for assumption table loading.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError(
            "name must be a non-empty string\\n"
            "Suggestions:\\n"
            "  • Use descriptive names like 'mortality_2012' or 'lapse_ultimate'\\n"
            "  • Avoid empty strings or whitespace-only names"
        )
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "value must be a non-empty string\\n"
            "Suggestions:\\n"
            "  • Use descriptive names like 'rate', 'qx', 'probability'\\n"
            "  • Avoid empty strings or whitespace-only names"
        )
    if value_vars is not None and not isinstance(value_vars, list):
        raise ValueError(
            "value_vars must be a list of column names or None\\n"
            "Examples:\\n"
            "  • value_vars=['Male', 'Female'] for gender-specific columns\\n"
            "  • value_vars=['1', '2', '3', 'Ultimate'] for duration columns"
        )
    if not isinstance(max_overflow, int) or max_overflow < 1 or max_overflow > 1000:
        raise ValueError(
            "max_overflow must be an integer between 1 and 1000\\n"
            "Suggestions:\\n"
            "  • Use 200 for typical actuarial projections\\n"
            "  • Use 100 for shorter-term analyses\\n"
            "  • Use 500+ only for very long-term projections"
        )
    if overflow is not None and overflow != "auto" and not isinstance(overflow, str):
        raise ValueError(
            "overflow must be 'auto', a column name string, or None\\n"
            "Examples:\\n"
            "  • overflow='auto' for automatic detection\\n"
            "  • overflow='Ultimate' for explicit overflow column\\n"
            "  • overflow=None to disable overflow handling"
        )
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError(
            "metadata must be a dictionary or None\\n"
            "Examples:\\n"
            "  • metadata={'source': '2012 IAM Tables', 'version': '1.0'}\\n"
            "  • metadata={'effective_date': '2013-01-01', 'basis': 'select_ultimate'}"
        )
    if lookup_keys is not None:
        if not isinstance(lookup_keys, list):
            raise ValueError(
                "lookup_keys must be a list of strings or None\\n"
                "Examples:\\n"
                "  • lookup_keys=['issue_age', 'year_lookup'] for 2-key lookup\\n"
                "  • lookup_keys=['age'] for single-key lookup"
            )
        if not all(isinstance(key, str) and key.strip() for key in lookup_keys):
            raise ValueError(
                "All lookup_keys must be non-empty strings\\n"
                "Examples:\\n"
                "  • lookup_keys=['issue_age', 'year_lookup']\\n"
                "  • lookup_keys=['age', 'duration']"
            )

    # Validate additional_keys using the validation module
    _validate_additional_keys(additional_keys)


def _determine_table_processing_strategy(
    df: pl.DataFrame,
    id_param: Union[str, list[str], None],
    value_vars_param: Union[list[str], None],
) -> tuple[list[str], list[str], list[str], bool]:
    """Analyzes DataFrame shape and determines if it's wide, and which columns to melt.

    Internal helper function that examines the DataFrame structure to determine
    the appropriate processing strategy for assumption table loading.
    """
    try:
        id_columns, numeric_columns, text_columns, is_wide = _analyse_shape(
            df, id_param
        )
    except ValueError as e:
        logger.error(f"Failed to analyze table structure: {e}")
        raise ValueError(f"Failed to analyse DataFrame structure: {e}") from e

    columns_to_melt: list[str]
    if value_vars_param is not None:
        missing_value_vars = [col for col in value_vars_param if col not in df.columns]
        if missing_value_vars:
            raise ValueError(
                f"Specified value_vars columns not found in DataFrame: {missing_value_vars}"
            )
        columns_to_melt = value_vars_param
        is_wide = True  # Force wide if value_vars is specified
    else:
        columns_to_melt = numeric_columns

    if not columns_to_melt:
        raise ValueError(
            "No columns found to use as values. "
            "Specify value_vars or ensure there are numeric columns for values."
        )
    return id_columns, columns_to_melt, text_columns, is_wide


def _prepare_final_keys(
    original_keys: list[str],
    lookup_keys_param: Union[list[str], None],
    expected_len: int,
    table_type_for_error: str,
) -> tuple[list[str], pl.DataFrame | None, dict[str, str]]:
    """Prepares final key names and rename mapping if lookup_keys are provided.

    Internal helper function that handles the transformation of column names
    when custom lookup keys are specified by the user.
    """
    rename_mapping = {}
    final_keys = original_keys
    df_to_rename = None  # Placeholder, will be set by caller if rename is needed

    if lookup_keys_param is not None:
        if len(lookup_keys_param) != expected_len:
            raise ValueError(
                f"lookup_keys length ({len(lookup_keys_param)}) must match number of "
                f"id columns ({expected_len}) for {table_type_for_error} tables\\n"
                f"Expected: {expected_len} keys for id columns: {original_keys}\\n"
                f"Provided: {len(lookup_keys_param)} keys: {lookup_keys_param}"
            )
        rename_mapping = dict(zip(original_keys, lookup_keys_param))
        final_keys = lookup_keys_param
    return final_keys, df_to_rename, rename_mapping


def _process_curve_table_logic(
    df: pl.DataFrame,
    id_columns: list[str],
    value_param: str,
    lookup_keys_param: Union[list[str], None],
) -> tuple[pl.DataFrame, list[str]]:
    """Processes a DataFrame as a curve table.

    Internal helper function that handles the transformation and registration
    of curve-format assumption tables.
    """
    try:
        tidy_df = _tidy_curve(df, id_columns, value_param)
    except ValueError as e:
        raise e

    final_keys, _, rename_mapping = _prepare_final_keys(
        original_keys=id_columns,
        lookup_keys_param=lookup_keys_param,
        expected_len=len(id_columns),
        table_type_for_error="curve",
    )
    if rename_mapping:
        tidy_df = tidy_df.rename(rename_mapping)

    tidy_df = _convert_keys_to_f64(tidy_df, final_keys)
    return tidy_df, final_keys


def _process_wide_table_logic(
    df: pl.DataFrame,
    id_columns: list[str],
    columns_to_melt: list[str],
    text_columns: list[str],  # Needed for overflow detection if value_vars is None
    value_param: str,
    overflow_param: Union[Literal["auto"], str, None],
    max_overflow_param: int,
    lookup_keys_param: Union[list[str], None],
    value_vars_param: Union[list[str], None],  # To guide overflow detection cols
) -> tuple[pl.DataFrame, list[str], str | None]:
    """Processes a DataFrame as a wide table, handling overflow and melting.

    Internal helper function that handles the transformation and registration
    of wide-format assumption tables, including overflow expansion.
    """
    overflow_col_name_detected: str | None = None
    if overflow_param is not None:
        # Determine columns for overflow detection
        if value_vars_param is not None:
            overflow_detection_cols = columns_to_melt  # Use specified value_vars
        else:
            # For auto-detection, combine numeric (columns_to_melt) and text columns
            overflow_detection_cols = columns_to_melt + text_columns

        try:
            overflow_col_name_detected = _detect_overflow_column(
                overflow_detection_cols, overflow_param
            )
        except ValueError as e:
            raise e

    try:
        tidy_df = _tidy_wide_with_overflow_expansion(
            df,
            id_columns,
            columns_to_melt,
            value_param,
            overflow_param,  # Pass the original overflow parameter
            max_overflow_param,
        )
    except ValueError as e:
        raise e

    original_keys_for_rename = id_columns + ["variable"]
    final_keys, _, rename_mapping = _prepare_final_keys(
        original_keys=original_keys_for_rename,
        lookup_keys_param=lookup_keys_param,
        expected_len=len(id_columns) + 1,
        table_type_for_error="wide",
    )
    if rename_mapping:
        tidy_df = tidy_df.rename(rename_mapping)

    tidy_df = _convert_keys_to_f64(tidy_df, final_keys)
    return tidy_df, final_keys, overflow_col_name_detected


def _finalize_table_registration_and_log(
    name: str,
    tidy_df: pl.DataFrame,
    final_keys: list[str],
    value_column: str,
    metadata_param: dict[str, Any] | None,
    is_wide: bool,
    id_columns_len: int,
    columns_to_melt_len: int | None = None,  # Only for wide tables
    overflow_col_name: str | None = None,  # Only for wide tables with overflow
    max_overflow: int | None = None,  # Only for wide tables with overflow
) -> None:
    """Registers the table and logs success.

    Internal helper function that completes the assumption table loading process
    by registering the table and logging appropriate success messages.
    """
    registry = PyAssumptionTableRegistry()
    registry.register_table(
        name=name,
        df=tidy_df,
        keys=final_keys,
        value_column=value_column,
    )

    if metadata_param is not None:
        _TABLE_METADATA[name] = metadata_param.copy()

    if is_wide:
        expanded_info = ""
        if overflow_col_name and max_overflow is not None:
            expanded_info = f", overflow expanded to {max_overflow}"
        logger.info(
            f"Successfully loaded wide table '{name}': "
            f"{len(tidy_df)} rows, {id_columns_len} id columns, "
            f"{columns_to_melt_len or 0} value columns{expanded_info}"
        )
    else:
        logger.info(
            f"Successfully loaded curve table '{name}': "
            f"{len(tidy_df)} rows, {id_columns_len} id columns"
        )


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
    additional_keys: dict[str, Any] | None = None,
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
        additional_keys: Optional dictionary of additional key-value pairs to add as columns.
            Each key becomes a column name with the corresponding value added as a literal
            to all rows. Used for multi-dimensional tables where different data sources
            represent different categories (e.g., {"sex": "M", "smoking": "NS"}).
            Example: additional_keys={"sex": "F", "smoking": "SM"} adds sex and smoking columns.

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

    _validate_load_assumptions_params(
        name,
        value,
        value_vars,
        max_overflow,
        overflow,
        metadata,
        lookup_keys,
        additional_keys,
    )

    try:
        df = _materialise(source)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load data for table '{name}': {e}")
        raise

    # Add additional keys as literal columns if provided
    if additional_keys is not None and len(additional_keys) > 0:
        logger.debug(f"Adding additional keys as columns: {additional_keys}")

        # Check for column name conflicts
        existing_columns = df.columns
        conflicting_keys = [
            key for key in additional_keys.keys() if key in existing_columns
        ]
        if conflicting_keys:
            raise ValueError(
                f"additional_keys contain column names that already exist in the data: {conflicting_keys}\n"
                f"Existing columns: {existing_columns}\n"
                f"Additional keys: {list(additional_keys.keys())}\n"
                f"Please choose different names for additional_keys to avoid conflicts."
            )

        for key, value_literal in additional_keys.items():
            df = df.with_columns(pl.lit(value_literal).alias(key))
            logger.debug(f"Added column '{key}' with value {repr(value_literal)}")

    # Handle additional keys properly with auto-detection
    if additional_keys is not None and len(additional_keys) > 0:
        additional_key_names = list(additional_keys.keys())

        if id is None:
            # For auto-detection with additional keys, we need to run the detection first
            # then add any additional keys that aren't already detected
            temp_id_columns, _, _, _ = _determine_table_processing_strategy(
                df, None, value_vars
            )

            # Only add additional keys that aren't already in the detected ID columns
            unique_additional_keys = [
                key for key in additional_key_names if key not in temp_id_columns
            ]
            modified_id = temp_id_columns + unique_additional_keys
        elif isinstance(id, str):
            # Only add additional keys that aren't already in the explicit ID
            unique_additional_keys = [key for key in additional_key_names if key != id]
            modified_id = [id] + unique_additional_keys
        else:  # id is already a list
            # Only add additional keys that aren't already in the explicit ID list
            unique_additional_keys = [
                key for key in additional_key_names if key not in id
            ]
            modified_id = list(id) + unique_additional_keys
        logger.debug(f"Modified id columns to include additional keys: {modified_id}")
    else:
        modified_id = id

    id_columns, columns_to_melt, text_columns, is_wide = (
        _determine_table_processing_strategy(df, modified_id, value_vars)
    )

    tidy_df: pl.DataFrame
    final_keys: list[str]
    overflow_col_name_for_log: str | None = None

    if not is_wide:
        tidy_df, final_keys = _process_curve_table_logic(
            df, id_columns, value, lookup_keys
        )
    else:
        tidy_df, final_keys, overflow_col_name_for_log = _process_wide_table_logic(
            df,
            id_columns,
            columns_to_melt,
            text_columns,  # Pass text_columns for overflow detection logic
            value,
            overflow,
            max_overflow,
            lookup_keys,
            value_vars,  # Pass value_vars for overflow detection logic
        )

    _finalize_table_registration_and_log(
        name=name,
        tidy_df=tidy_df,
        final_keys=final_keys,
        value_column=value,
        metadata_param=metadata,
        is_wide=is_wide,
        id_columns_len=len(id_columns),
        columns_to_melt_len=len(columns_to_melt) if is_wide else None,
        overflow_col_name=overflow_col_name_for_log if is_wide else None,
        max_overflow=max_overflow if is_wide and overflow_col_name_for_log else None,
    )

    # Store configuration for potential append operations
    config = {
        "id": id,
        "value": value,
        "value_vars": value_vars,
        "overflow": overflow,
        "max_overflow": max_overflow,
        "lookup_keys": lookup_keys,
        "additional_keys": additional_keys,
    }
    _store_table_config(name, config)
    logger.debug(
        f"Stored configuration for table '{name}' for future append operations"
    )

    return tidy_df


def append_assumptions(
    name: str,
    source: Union[str, Path, pl.DataFrame],
    *,
    additional_keys: dict[str, Any],  # REQUIRED for append
    id: Union[str, list[str], None] = None,
    value: str = "rate",
    value_vars: Union[list[str], None] = None,
    overflow: Union[Literal["auto"], str, None] = "auto",
    max_overflow: int = 200,
    metadata: dict[str, Any] | None = None,
    lookup_keys: Union[list[str], None] = None,
) -> pl.DataFrame:
    """Append data to an existing assumption table with additional keys.

    This function enables appending multiple data sources to a single assumption
    table with additional keys for multi-dimensional lookups. This replaces the
    current pattern of multiple separate tables by consolidating them into a
    single table with additional dimensions.

    !!! note "When to use"
        *   Consolidating multiple mortality tables (e.g., male/female, smoker/non-smoker) into a single table.
        *   Adding new data segments to existing assumption tables without creating separate tables.
        *   Building multi-dimensional lookup tables with consistent structure across segments.
        *   Replacing patterns where table names encode data dimensions.

    Args:
        name: Name of the existing assumption table to append to. Table must already
            exist (created via load_assumptions).
        source: Data source - file path (str/Path) or Polars DataFrame.
            Supported formats: .csv, .parquet
        additional_keys: Dictionary of additional key-value pairs to add as columns.
            REQUIRED parameter. Each key becomes a column name with the corresponding
            value added as a literal to all rows. Must have the same keys as the
            original table but different values to avoid conflicts.
            Example: additional_keys={"sex": "F", "smoking": "SM"}
        id: Column name(s) to use as lookup keys. Must match original table structure
            if specified. If None, uses the same auto-detection logic as original table.
        value: Name for the value column. Must match the original table's value column name.
        value_vars: For wide tables, specific columns to melt. Must match original table
            structure if specified.
        overflow: Overflow handling for wide tables. Must match original table setting.
        max_overflow: Maximum duration to expand overflow values to. Must match original
            table setting.
        metadata: Optional metadata dictionary. Does not affect compatibility.
        lookup_keys: Optional list of custom column names. Must match original table
            if the original table used custom lookup keys.

    Returns:
        pl.DataFrame: The processed and appended data in the same format as the original table.

    Raises:
        ValueError: If table doesn't exist, parameters don't match original table,
            or additional_keys create conflicts.
        FileNotFoundError: If source file doesn't exist.

    Examples
    --------
    Multi-dimensional mortality table consolidation::

        Scenario: Replace 4 separate mortality tables with a single consolidated table.

        ```python
        import polars as pl
        import gaspatchio_core as gs

        # Load base table (first segment)
        fsm_data = pl.DataFrame({
            "age": [30, 31, 32],
            "qx": [0.00074, 0.00081, 0.00089]
        })
        gs.load_assumptions("mortality_cso", fsm_data,
                           additional_keys={"sex": "F", "smoking": "SM"})

        # Append remaining segments
        msm_data = pl.DataFrame({
            "age": [30, 31, 32],
            "qx": [0.00095, 0.00103, 0.00112]
        })
        gs.append_assumptions("mortality_cso", msm_data,
                             additional_keys={"sex": "M", "smoking": "SM"})

        fns_data = pl.DataFrame({
            "age": [30, 31, 32],
            "qx": [0.00049, 0.00053, 0.00058]
        })
        gs.append_assumptions("mortality_cso", fns_data,
                             additional_keys={"sex": "F", "smoking": "NS"})

        mns_data = pl.DataFrame({
            "age": [30, 31, 32],
            "qx": [0.00063, 0.00068, 0.00074]
        })
        gs.append_assumptions("mortality_cso", mns_data,
                             additional_keys={"sex": "M", "smoking": "NS"})

        # Now lookup with clean multi-dimensional syntax
        rate = gs.assumption_lookup("sex", "smoking", "age",
                                   table_name="mortality_cso")
        ```

    Wide table appending with overflow::

        Scenario: Append morbidity data with consistent overflow handling.

        ```python
        import polars as pl
        import gaspatchio_core as gs

        # Load base morbidity table (product A)
        product_a_data = pl.DataFrame({
            "age": [40, 41],
            "1": [0.0120, 0.0135],
            "2": [0.0110, 0.0125],
            "Ultimate": [0.0095, 0.0105]
        })
        gs.load_assumptions("morbidity_table", product_a_data,
                           overflow="Ultimate", max_overflow=10,
                           additional_keys={"product": "A"})

        # Append product B with same structure
        product_b_data = pl.DataFrame({
            "age": [40, 41],
            "1": [0.0140, 0.0155],
            "2": [0.0130, 0.0145],
            "Ultimate": [0.0115, 0.0125]
        })
        gs.append_assumptions("morbidity_table", product_b_data,
                             additional_keys={"product": "B"})

        # Lookup works across all products
        rate = gs.assumption_lookup("product", "age", "variable",
                                   table_name="morbidity_table")
        ```
    """
    logger.info(f"Appending data to assumption table '{name}'")

    # Validate table exists for append
    _validate_table_exists_for_append(name)

    # Validate required additional_keys parameter
    if additional_keys is None:
        raise ValueError(
            "additional_keys parameter is required for append_assumptions. "
            "This parameter distinguishes the new data from existing data in the table. "
            "Example: additional_keys={'sex': 'F', 'smoking': 'SM'}"
        )

    # Validate additional_keys format
    _validate_additional_keys(additional_keys)

    # Get original table configuration
    original_config = _get_table_config(name)
    logger.debug(f"Retrieved original configuration for table '{name}'")

    # Use original configuration values where new values are None or default
    # This ensures consistency with the original table when defaults are used
    effective_value = value if value != "rate" else original_config.get("value", "rate")
    effective_overflow = (
        overflow if overflow != "auto" else original_config.get("overflow", "auto")
    )
    effective_max_overflow = (
        max_overflow
        if max_overflow != 200
        else original_config.get("max_overflow", 200)
    )

    # Build configuration for validation using effective values
    new_config = {
        "id": id,
        "value": effective_value,
        "value_vars": value_vars,
        "overflow": effective_overflow,
        "max_overflow": effective_max_overflow,
        "lookup_keys": lookup_keys,
        "additional_keys": additional_keys,
    }

    # Validate compatibility between original and new configurations
    _validate_append_compatibility(original_config, new_config)
    logger.debug("Append compatibility validation passed")

    # Process the new data through the same pipeline as load_assumptions
    try:
        df = _materialise(source)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Failed to load data for append to table '{name}': {e}")
        raise

    # Add additional keys as literal columns
    logger.debug(f"Adding additional keys as columns: {additional_keys}")

    # Check for column name conflicts
    existing_columns = df.columns
    conflicting_keys = [
        key for key in additional_keys.keys() if key in existing_columns
    ]
    if conflicting_keys:
        raise ValueError(
            f"additional_keys contain column names that already exist in the data: {conflicting_keys}\n"
            f"Existing columns: {existing_columns}\n"
            f"Additional keys: {list(additional_keys.keys())}\n"
            f"Please choose different names for additional_keys to avoid conflicts."
        )

    for key, value_literal in additional_keys.items():
        df = df.with_columns(pl.lit(value_literal).alias(key))
        logger.debug(f"Added column '{key}' with value {repr(value_literal)}")

    # Use original configuration values where new values are None or default
    # This ensures consistency with the original table
    effective_id = id if id is not None else original_config.get("id")
    effective_value_vars = (
        value_vars if value_vars is not None else original_config.get("value_vars")
    )
    effective_lookup_keys = (
        lookup_keys if lookup_keys is not None else original_config.get("lookup_keys")
    )

    # Handle additional keys properly with auto-detection for append
    # Use the same logic as load_assumptions to maintain consistency
    if len(additional_keys) > 0:
        additional_key_names = list(additional_keys.keys())

        if effective_id is None:
            # For auto-detection with additional keys, run detection first then add unique additional keys
            temp_id_columns, _, _, _ = _determine_table_processing_strategy(
                df, None, effective_value_vars
            )

            # Only add additional keys that aren't already in the detected ID columns
            unique_additional_keys = [
                key for key in additional_key_names if key not in temp_id_columns
            ]
            modified_id = temp_id_columns + unique_additional_keys
        elif isinstance(effective_id, str):
            # Only add additional keys that aren't already in the explicit ID
            unique_additional_keys = [
                key for key in additional_key_names if key != effective_id
            ]
            modified_id = [effective_id] + unique_additional_keys
        else:  # effective_id is already a list
            # Only add additional keys that aren't already in the explicit ID list
            unique_additional_keys = [
                key for key in additional_key_names if key not in effective_id
            ]
            modified_id = list(effective_id) + unique_additional_keys
        logger.debug(f"Modified id columns to include additional keys: {modified_id}")
    else:
        modified_id = effective_id

    # Process through the same transformation pipeline
    id_columns, columns_to_melt, text_columns, is_wide = (
        _determine_table_processing_strategy(df, modified_id, effective_value_vars)
    )

    tidy_df: pl.DataFrame
    final_keys: list[str]
    overflow_col_name_for_log: str | None = None

    if not is_wide:
        tidy_df, final_keys = _process_curve_table_logic(
            df, id_columns, effective_value, effective_lookup_keys
        )
    else:
        tidy_df, final_keys, overflow_col_name_for_log = _process_wide_table_logic(
            df,
            id_columns,
            columns_to_melt,
            text_columns,
            effective_value,
            effective_overflow,
            effective_max_overflow,
            effective_lookup_keys,
            effective_value_vars,
        )

    # TEMPORARY: Remove existing table before registering appended data
    # Note: This will be replaced with direct hashmap insertion in later steps
    registry = PyAssumptionTableRegistry()

    # For now, we can't truly "append" to the Rust table, so we'll just validate
    # the data processing pipeline and return the transformed DataFrame
    # The actual table registration will be implemented in Step 7 with Rust append
    logger.debug(f"Processed append data for table '{name}' (not yet registered)")

    # Store metadata if provided (append operation doesn't replace existing metadata)
    if metadata is not None:
        _TABLE_METADATA[name] = metadata.copy()

    # Log success
    if is_wide:
        expanded_info = ""
        if overflow_col_name_for_log and effective_max_overflow is not None:
            expanded_info = f", overflow expanded to {effective_max_overflow}"
        logger.info(
            f"Successfully appended to wide table '{name}': "
            f"{len(tidy_df)} new rows, {len(id_columns)} id columns, "
            f"{len(columns_to_melt)} value columns{expanded_info}"
        )
    else:
        logger.info(
            f"Successfully appended to curve table '{name}': "
            f"{len(tidy_df)} new rows, {len(id_columns)} id columns"
        )

    logger.debug(f"Append operation completed for table '{name}'")
    return tidy_df
