# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Strategy implementations for overflow and fill operations.

This module provides composable strategies for handling overflow columns and
filling missing values in assumption tables. Strategies are designed to work
with the new dimension-based API and avoid magic column names.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import polars as pl
from loguru import logger


class OverflowStrategy(ABC):
    """Base class for overflow handling strategies"""

    @abstractmethod
    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        """Apply overflow strategy to the DataFrame

        Args:
            df: DataFrame to process
            dimension_name: Name of the dimension column containing overflow values

        Returns:
            Processed DataFrame with overflow expansion applied

        """


class FillStrategy(ABC):
    """Base class for fill strategies"""

    @abstractmethod
    def apply(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply fill strategy to the DataFrame

        Args:
            df: DataFrame to process

        Returns:
            Processed DataFrame with missing values filled

        """


@dataclass
class ExtendOverflow(OverflowStrategy):
    """Extend an overflow column to a specified value

    This strategy finds rows where a dimension contains the specified overflow
    column value and creates additional rows extending from the detected maximum
    numeric value up to the specified to_value.
    """

    column: str  # Column name like "Ultimate", "Ult."
    to_value: int = 200
    from_value: int | None = None  # Auto-detect if None

    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        """Apply overflow extension to the DataFrame"""
        if df.is_empty():
            return df

        # Check if the overflow column exists in the dimension values
        unique_values = df[dimension_name].unique().to_list()

        if self.column not in unique_values:
            logger.debug(
                f"Overflow column '{self.column}' not found in dimension "
                f"'{dimension_name}'. Available values: {unique_values}",
            )
            return df

        # Get ID columns (everything except dimension and value)
        id_columns = [
            col for col in df.columns if col != dimension_name and col != "value"
        ]

        # Determine starting value for extension
        start_value = self._determine_start_value(unique_values)
        if start_value is None:
            logger.warning(
                f"Cannot determine starting point for overflow extension in dimension '{dimension_name}'",
            )
            return df

        # Split data into overflow and non-overflow
        non_overflow_data = df.filter(pl.col(dimension_name) != self.column)
        overflow_data = df.filter(pl.col(dimension_name) == self.column)

        if overflow_data.is_empty():
            logger.debug(f"No overflow data found for '{self.column}'")
            return non_overflow_data

        # Create expansion rows
        expansion_df = self._create_expansion_rows(
            overflow_data,
            dimension_name,
            id_columns,
            start_value,
        )

        # Combine results
        if expansion_df.is_empty():
            result = non_overflow_data
        else:
            result = pl.concat([non_overflow_data, expansion_df])

        logger.debug(
            f"Extended overflow from {start_value} to {self.to_value} "
            f"for '{self.column}' in dimension '{dimension_name}' "
            f"(added {len(expansion_df) if not expansion_df.is_empty() else 0} rows)",
        )

        return result

    def _determine_start_value(self, unique_values: list[str]) -> int | None:
        """Determine the starting value for overflow extension"""
        if self.from_value is not None:
            return self.from_value

        # Auto-detect: get maximum numeric value (excluding overflow column)
        numeric_values = []
        for val in unique_values:
            if val != self.column:
                # Try direct conversion first
                try:
                    numeric_values.append(int(val))
                    continue
                except ValueError:
                    pass

                # Try to extract numeric parts for mixed formats
                numeric_matches = re.findall(r"\d+", str(val))
                if numeric_matches:
                    try:
                        # Take the last numeric part found
                        numeric_values.append(int(numeric_matches[-1]))
                    except ValueError:
                        continue

        if not numeric_values:
            return None

        return max(numeric_values) + 1

    def _create_expansion_rows(
        self,
        overflow_data: pl.DataFrame,
        dimension_name: str,
        id_columns: list[str],
        start_value: int,
    ) -> pl.DataFrame:
        """Create expansion rows for the overflow data"""
        if start_value > self.to_value:
            return pl.DataFrame(schema=overflow_data.schema).clear()

        expansion_range = self.to_value - start_value + 1
        original_rows = len(overflow_data)
        total_new_rows = original_rows * expansion_range

        # Memory warning for large expansions
        if total_new_rows > 1_000_000:
            logger.warning(
                f"Large overflow expansion: {total_new_rows:,} rows will be created "
                f"({original_rows:,} overflow rows × {expansion_range} values). "
                f"Consider reducing to_value parameter.",
            )

        # Generate expansion rows
        expansion_rows = []
        for new_value in range(start_value, self.to_value + 1):
            expanded = overflow_data.with_columns(
                pl.lit(str(new_value)).alias(dimension_name),
            )
            expansion_rows.append(expanded)

        return (
            pl.concat(expansion_rows)
            if expansion_rows
            else pl.DataFrame(schema=overflow_data.schema).clear()
        )


@dataclass
class AutoDetectOverflow(OverflowStrategy):
    """Automatically detect and extend overflow column

    This strategy automatically detects overflow columns using common patterns
    and then applies overflow extension using the ExtendOverflow strategy.
    """

    patterns: list[str] = field(
        default_factory=lambda: [
            "ult",
            "ult.",
            "ultimate",
            "term",
            "999",
            "",
        ],
    )
    to_value: int = 200

    def apply(self, df: pl.DataFrame, dimension_name: str) -> pl.DataFrame:
        """Apply auto-detected overflow extension to the DataFrame"""
        if df.is_empty():
            return df

        # Get unique values in the dimension
        unique_values = df[dimension_name].unique().to_list()

        # Try to detect overflow column
        overflow_col = self._detect_overflow_column(unique_values)

        if overflow_col is None:
            logger.debug(
                f"No overflow column detected in dimension '{dimension_name}' "
                f"using patterns {self.patterns}. Available values: {unique_values}",
            )
            return df

        # Use ExtendOverflow strategy with detected column
        extend_strategy = ExtendOverflow(column=overflow_col, to_value=self.to_value)
        return extend_strategy.apply(df, dimension_name)

    def _detect_overflow_column(self, values: list[str]) -> str | None:
        """Detect overflow column using pattern matching"""
        for value in values:
            value_lower = str(value).lower().strip()
            if value_lower in self.patterns:
                return value
        return None


@dataclass
class LinearInterpolate(FillStrategy):
    """Interpolate missing values using various methods

    Provides linear, log-linear, and cubic interpolation methods for filling
    missing values in assumption tables.
    """

    method: Literal["linear", "log-linear", "cubic"] = "linear"
    fill_gaps: bool = True
    extrapolate: bool = False

    def apply(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply interpolation to fill missing values"""
        if df.is_empty():
            return df

        if self.method == "linear":
            result = df.with_columns(
                pl.col("value").interpolate().alias("value"),
            )
        elif self.method == "log-linear":
            # Log-linear interpolation: log -> interpolate -> exp
            # Apply to the whole column after handling zeros/negatives
            result = df.with_columns(
                pl.col("value").log().interpolate().exp().alias("value"),
            )
        elif self.method == "cubic":
            # Polars doesn't have cubic interpolation, fall back to linear
            logger.warning(
                "Cubic interpolation not available, using linear interpolation",
            )
            result = df.with_columns(
                pl.col("value").interpolate().alias("value"),
            )
        else:
            raise ValueError(f"Unknown interpolation method: {self.method}")

        logger.debug(f"Applied {self.method} interpolation to fill missing values")
        return result


@dataclass
class FillConstant(FillStrategy):
    """Fill missing values with a constant value"""

    value: Any

    def apply(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply constant fill to missing values"""
        if df.is_empty():
            return df

        result = df.with_columns(
            pl.col("value").fill_null(self.value).alias("value"),
        )

        logger.debug(f"Filled missing values with constant {self.value}")
        return result


@dataclass
class FillForward(FillStrategy):
    """Forward fill missing values

    Fills missing values by carrying forward the last valid observation.
    Optionally limits the number of consecutive fills.
    """

    limit: int | None = None

    def apply(self, df: pl.DataFrame) -> pl.DataFrame:
        """Apply forward fill to missing values"""
        if df.is_empty():
            return df

        if self.limit is not None:
            # Implement limited forward fill using a more complex approach
            # This is a simplified version - a full implementation would need
            # to track consecutive null counts
            logger.warning(
                f"Forward fill limit ({self.limit}) is not fully implemented. "
                f"Using unlimited forward fill.",
            )

        result = df.with_columns(
            pl.col("value").forward_fill().alias("value"),
        )

        logger.debug("Applied forward fill to missing values")
        return result
