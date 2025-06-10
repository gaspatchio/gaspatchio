"""
Dimension implementations for the new assumption table API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    from ._strategies import FillStrategy, OverflowStrategy


class Dimension(ABC):
    """Base class for all dimension types"""

    @abstractmethod
    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process the dimension on the given DataFrame"""

    @abstractmethod
    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied to the DataFrame"""


@dataclass
class DataDimension(Dimension):
    """Map a data column directly to a dimension"""

    column: str
    rename_to: str | None = None
    dtype: pl.DataType | None = None  # Force specific dtype

    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied to the DataFrame"""
        if self.column not in df.columns:
            available_cols = ", ".join(df.columns)
            raise ValueError(
                f"Column '{self.column}' not found in DataFrame.\n"
                f"Available columns: {available_cols}",
            )

        if self.dtype is not None:
            current_dtype = df[self.column].dtype
            if current_dtype != self.dtype:
                logger.warning(
                    f"Column '{self.column}' has dtype {current_dtype}, "
                    f"but {self.dtype} was specified. Will attempt conversion.",
                )

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process the dimension on the given DataFrame"""
        self.validate(df)

        result = df

        # Apply dtype conversion if specified
        if self.dtype is not None:
            try:
                # For numeric conversions, try Float64 first if needed
                current_dtype = result[self.column].dtype
                if current_dtype == pl.String and self.dtype in (pl.Int32, pl.Int64):
                    # String to int needs to go through float first
                    result = result.with_columns(
                        pl.col(self.column).cast(pl.Float64).cast(self.dtype),
                    )
                else:
                    result = result.with_columns(pl.col(self.column).cast(self.dtype))
                logger.debug(f"Converted column '{self.column}' to {self.dtype}")
            except Exception as e:
                raise ValueError(
                    f"Failed to convert column '{self.column}' to {self.dtype}: {e}",
                )

        # Apply rename if specified
        if self.rename_to is not None and self.rename_to != self.column:
            result = result.rename({self.column: self.rename_to})
            logger.debug(f"Renamed column '{self.column}' to '{self.rename_to}'")

        return result


@dataclass
class MeltDimension(Dimension):
    """Melt wide columns into a long format dimension"""

    columns: list[str]
    name: str = "variable"
    overflow: OverflowStrategy | None = None
    fill: FillStrategy | None = None

    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied to the DataFrame"""
        missing_columns = [col for col in self.columns if col not in df.columns]
        if missing_columns:
            available_cols = ", ".join(df.columns)
            raise ValueError(
                f"Columns {missing_columns} not found in DataFrame.\n"
                f"Available columns: {available_cols}",
            )

        # Check for naming conflicts
        if self.name in df.columns and self.name not in self.columns:
            raise ValueError(
                f"Dimension name '{self.name}' conflicts with existing column. "
                f"Choose a different name or include it in columns to melt.",
            )

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process the dimension on the given DataFrame"""
        self.validate(df)

        # Get other columns (not being melted)
        other_columns = [col for col in df.columns if col not in self.columns]

        # Perform the melt operation
        result = df.unpivot(
            index=other_columns,
            on=self.columns,
            variable_name=self.name,
            value_name="value",
        )

        logger.debug(
            f"Melted {len(self.columns)} columns into dimension '{self.name}'. "
            f"Shape: {df.shape} -> {result.shape}",
        )

        # Apply overflow strategy if specified
        if self.overflow is not None:
            result = self.overflow.apply(result, self.name)
            logger.debug(f"Applied overflow strategy to dimension '{self.name}'")

        # Apply fill strategy if specified
        if self.fill is not None:
            # Group by non-dimension columns and apply fill within each group
            if other_columns:
                # Filter to only string column names (not expressions)
                valid_group_columns = [
                    col for col in other_columns if isinstance(col, str)
                ]

                if valid_group_columns:
                    try:
                        result = result.group_by(valid_group_columns).map_groups(
                            lambda group: self.fill.apply(group),
                        )
                    except Exception as e:
                        logger.warning(
                            f"Group-by fill failed ({e}), applying fill globally",
                        )
                        result = self.fill.apply(result)
                else:
                    result = self.fill.apply(result)
            else:
                result = self.fill.apply(result)
            logger.debug(f"Applied fill strategy to dimension '{self.name}'")

        return result


@dataclass
class CategoricalDimension(Dimension):
    """Add a constant categorical value as a dimension"""

    value: Any
    name: str | None = None  # Auto-generated if not provided

    def __post_init__(self):
        """Auto-generate name if not provided"""
        if self.name is None:
            # Generate a name based on the value
            if isinstance(self.value, str):
                # Use the string value as name (cleaned up)
                cleaned = self.value.lower().strip().replace(" ", "_").replace("-", "_")
                # Remove any leading/trailing underscores
                cleaned = cleaned.strip("_")
                self.name = cleaned
            else:
                # Use a generic name with the value
                self.name = f"category_{self.value}"

    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied to the DataFrame"""
        if self.name in df.columns:
            raise ValueError(
                f"Column '{self.name}' already exists in DataFrame. "
                f"Choose a different name for the categorical dimension.",
            )

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process the dimension on the given DataFrame"""
        self.validate(df)

        # Add the categorical column
        result = df.with_columns(pl.lit(self.value).alias(self.name))

        logger.debug(
            f"Added categorical dimension '{self.name}' with value {self.value!r}",
        )

        return result


@dataclass
class ComputedDimension(Dimension):
    """Compute a dimension from existing columns"""

    expression: pl.Expr
    name: str

    def validate(self, df: pl.DataFrame) -> None:
        """Validate this dimension can be applied to the DataFrame"""
        if self.name in df.columns:
            logger.warning(
                f"Column '{self.name}' already exists and will be overwritten "
                f"by computed dimension.",
            )

        # Try to validate the expression by running it on a sample
        try:
            # Test with first row only to check syntax
            sample = df.head(1)
            sample.with_columns(self.expression.alias("__test__"))
        except Exception as e:
            raise ValueError(
                f"Invalid expression for computed dimension '{self.name}': {e}",
            )

    def process(self, df: pl.DataFrame) -> pl.DataFrame:
        """Process the dimension on the given DataFrame"""
        self.validate(df)

        # Apply the computed expression
        result = df.with_columns(self.expression.alias(self.name))

        logger.debug(f"Added computed dimension '{self.name}'")

        return result
