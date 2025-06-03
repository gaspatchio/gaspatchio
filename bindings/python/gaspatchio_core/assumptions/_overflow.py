"""
Internal module for handling overflow logic in wide tables.
"""

from __future__ import annotations

import re
from typing import Union

import polars as pl
from loguru import logger


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
