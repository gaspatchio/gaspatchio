"""
Main assumption table API (v2) - Table class with dimension-based structure.

This module replaces the old monolithic load_assumptions() function with a
modular system that separates concerns and improves composability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger
from polars.plugins import register_plugin_function

from .._internal import PyAssumptionTableRegistry
from ._analysis import TableSchema, analyze_table
from ._dimensions import DataDimension, Dimension
from ._utils import _convert_keys_to_f64, _materialise

# Global metadata storage for assumption tables
_TABLE_METADATA: dict[str, dict[str, Any]] = {}

# Import LIB path for plugin calls
try:
    from .._internal import LIB
except ImportError:
    LIB = None


class Table:
    """
    Main assumption table class with dimension-based structure.

    This class provides a clean API for creating assumption tables using
    composable dimension types and strategies, replacing the old monolithic
    load_assumptions() function.
    """

    def __init__(
        self,
        name: str,
        source: str | Path | pl.DataFrame,
        dimensions: dict[str, str | Dimension],
        value: str = "rate",
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Create a new assumption table.

        Args:
            name: Unique table name for registration
            source: Data source (file path or DataFrame)
            dimensions: Mapping of dimension names to dimension objects or column names
            value: Name for the value column
            validate: Whether to validate data on load
            metadata: Optional metadata dictionary to store with the table

        """
        self._name = name

        # Normalize dimensions - convert strings to DataDimension objects
        self._dimensions = {}
        for dim_name, dim_config in dimensions.items():
            if isinstance(dim_config, str):
                self._dimensions[dim_name] = DataDimension(dim_config)
            else:
                self._dimensions[dim_name] = dim_config

        self._value = value
        self._validate = validate
        self._df: pl.DataFrame | None = None
        self._schema: TableSchema | None = None

        # Store metadata if provided
        if metadata is not None:
            _TABLE_METADATA[name] = metadata.copy()
            logger.debug(f"Stored metadata for table '{name}': {metadata}")

        # Process the data during initialization
        self._process_data(source)

    def _process_data(self, source: str | Path | pl.DataFrame) -> None:
        """Process the data through dimension transformations and register with Rust"""
        logger.debug(f"Processing data for table '{self._name}'")

        # Materialize the source data
        df = _materialise(source)

        if self._validate:
            # Check if we have MeltDimension - if so, value column will be created
            has_melt_dimension = any(
                dim.__class__.__name__ == "MeltDimension"
                for dim in self._dimensions.values()
            )

            # Only validate value column exists if we don't have melt dimension
            if not has_melt_dimension and self._value not in df.columns:
                available_cols = ", ".join(df.columns)
                raise ValueError(
                    f"Value column '{self._value}' not found in DataFrame.\n"
                    f"Available columns: {available_cols}",
                )

        # Process dimensions in order
        # Note: Order matters for dependencies (e.g., ComputedDimension depends on others)
        current_df = df

        # Process dimensions in a specific order:
        # 1. DataDimension (base columns, renames)
        # 2. CategoricalDimension (add constant columns)
        # 3. MeltDimension (pivot operations)
        # 4. ComputedDimension (depends on other columns)

        dimension_order = [
            "DataDimension",
            "CategoricalDimension",
            "MeltDimension",
            "ComputedDimension",
        ]

        for dimension_type in dimension_order:
            for dim_name, dimension in self._dimensions.items():
                if dimension.__class__.__name__ == dimension_type:
                    if self._validate:
                        dimension.validate(current_df)
                    current_df = dimension.process(current_df)
                    logger.debug(f"Processed dimension '{dim_name}' ({dimension_type})")

                    # Handle MeltDimension value column naming
                    if (
                        dimension_type == "MeltDimension"
                        and "value" in current_df.columns
                    ):
                        if self._value != "value":
                            current_df = current_df.rename({"value": self._value})
                            logger.debug(
                                f"Renamed melt value column from 'value' to '{self._value}'",
                            )

        # Collect key columns (all columns except the value column)
        key_columns = [col for col in current_df.columns if col != self._value]

        if not key_columns:
            raise ValueError(
                f"No key columns found after dimension processing. "
                f"All columns cannot be the value column '{self._value}'",
            )

        # Convert keys to f64 for Rust compatibility
        processed_df = _convert_keys_to_f64(current_df, key_columns)

        # Store the processed DataFrame
        self._df = processed_df

        # Register with Rust registry
        try:
            registry = PyAssumptionTableRegistry()
            registry.register_table(
                name=self._name,
                df=processed_df,
                keys=key_columns,
                value_column=self._value,
            )
            logger.info(
                f"Successfully registered table '{self._name}' with {len(processed_df)} rows, "
                f"{len(key_columns)} key columns: {key_columns}",
            )
        except Exception as e:
            logger.error(f"Failed to register table '{self._name}' with Rust: {e}")
            raise

    def lookup(self, **kwargs: str | pl.Expr) -> pl.Expr:
        """
        Create a lookup expression using dimension names.

        Args:
            **kwargs: Dimension name to column/expression mapping

        Returns:
            Polars expression for the lookup

        """
        if self._validate:
            self.validate_lookup(**kwargs)

        # Convert kwargs to a list of expressions in the order of key columns
        if self._df is None:
            raise RuntimeError("Table data not processed. This should not happen.")

        key_columns = [col for col in self._df.columns if col != self._value]

        # Validate that all required dimensions are provided
        if set(kwargs.keys()) != set(self._dimensions.keys()):
            provided = set(kwargs.keys())
            required = set(self._dimensions.keys())
            missing = required - provided
            extra = provided - required

            error_parts = []
            if missing:
                error_parts.append(f"Missing dimensions: {sorted(missing)}")
            if extra:
                error_parts.append(f"Extra dimensions: {sorted(extra)}")

            raise ValueError(
                f"Dimension mismatch for table '{self._name}'. "
                + "; ".join(error_parts)
                + f"\nRequired dimensions: {sorted(required)}",
            )

        # Build list of expressions in key column order
        key_exprs = []
        for col in key_columns:
            if col in kwargs:
                value = kwargs[col]
                if isinstance(value, str):
                    key_exprs.append(pl.col(value))
                elif isinstance(value, pl.Expr):
                    key_exprs.append(value)
                else:
                    # Convert literal values to expressions
                    key_exprs.append(pl.lit(value))
            else:
                # This shouldn't happen due to validation above, but handle gracefully
                raise ValueError(f"No value provided for key column '{col}'")

        # Create the actual plugin call to Rust lookup implementation
        logger.debug(
            f"Creating lookup expression for table '{self._name}' with {len(key_exprs)} keys",
        )

        if LIB is None:
            # For testing purposes, return a placeholder expression
            # In production, this would indicate a compilation issue
            logger.warning(
                "Plugin library not available - using placeholder expression for testing",
            )
            return pl.lit(None).alias("lookup_result")

        return register_plugin_function(
            plugin_path=LIB,
            function_name="lookup_by_table_and_hash",  # Must match #[polars_expr] function name
            args=key_exprs,
            kwargs={"table_name": self._name},
            is_elementwise=False,  # Vector lookup is not elementwise
        )

    def extend(
        self,
        source: str | Path | pl.DataFrame,
        dimensions: dict[str, Dimension] | None = None,
        validate: bool = True,
    ) -> Table:
        """
        Extend table with additional data slices.

        Args:
            source: Additional data to add
            dimensions: Dimension overrides for this slice
            validate: Whether to validate compatibility

        Returns:
            Self for chaining

        """
        logger.debug(f"Extending table '{self._name}' with additional data")

        # Use original dimensions by default, with optional overrides
        extend_dimensions = self._dimensions.copy()
        if dimensions:
            extend_dimensions.update(dimensions)

        # Process the additional data the same way as original
        df = _materialise(source)
        current_df = df

        # Apply dimension processing
        dimension_order = [
            "DataDimension",
            "CategoricalDimension",
            "MeltDimension",
            "ComputedDimension",
        ]

        for dimension_type in dimension_order:
            for dim_name, dimension in extend_dimensions.items():
                if dimension.__class__.__name__ == dimension_type:
                    if validate:
                        dimension.validate(current_df)
                    current_df = dimension.process(current_df)

        # Get key columns
        key_columns = [col for col in current_df.columns if col != self._value]

        # Convert keys to f64
        processed_df = _convert_keys_to_f64(current_df, key_columns)

        # Append to existing table using Rust registry
        try:
            registry = PyAssumptionTableRegistry()
            registry.append_to_table(
                name=self._name,
                df=processed_df,
                keys=key_columns,
                value_column=self._value,
            )
            logger.info(
                f"Successfully extended table '{self._name}' with {len(processed_df)} additional rows",
            )
        except Exception as e:
            logger.error(f"Failed to extend table '{self._name}': {e}")
            raise

        # Update our stored DataFrame by concatenating
        if self._df is not None:
            self._df = pl.concat([self._df, processed_df])

        return self

    @property
    def schema(self) -> TableSchema:
        """Get the analyzed schema of this table"""
        if self._schema is None:
            if self._df is None:
                raise RuntimeError("Table data not processed")
            self._schema = analyze_table(self._df)
        return self._schema

    @property
    def dimensions(self) -> dict[str, Dimension]:
        """Get dimension configuration (returns a copy)"""
        return self._dimensions.copy()

    def dimension_values(self, dimension: str) -> list[Any]:
        """Get unique values for a specific dimension"""
        if dimension not in self._dimensions:
            available_dims = ", ".join(self._dimensions.keys())
            raise ValueError(
                f"Dimension '{dimension}' not found. Available dimensions: {available_dims}",
            )

        if self._df is None:
            raise RuntimeError("Table data not processed")

        # Find the actual column name for this dimension
        # For most dimensions, it's the same as the dimension name
        # But some dimensions might rename columns
        column_name = dimension

        # Check if column exists directly
        if column_name in self._df.columns:
            return self._df[column_name].unique().to_list()

        # For dimensions that might rename, try to find the actual column
        # This is a simplified approach - a full implementation would track renames
        for col in self._df.columns:
            if col != self._value:  # Skip value column
                # This is a placeholder - real implementation would have better logic
                return self._df[col].unique().to_list()

        return []

    def to_dataframe(self) -> pl.DataFrame:
        """Export the complete table as a DataFrame"""
        if self._df is None:
            raise RuntimeError("Table data not processed")
        return self._df.clone()

    def describe(self) -> str:
        """Get a human-readable description of the table"""
        if self._df is None:
            return f"Table '{self._name}' (not processed)"

        key_columns = [col for col in self._df.columns if col != self._value]

        lines = [
            f"Table: {self._name}",
            f"Rows: {len(self._df):,}",
            f"Value column: {self._value}",
            f"Key columns ({len(key_columns)}): {', '.join(key_columns)}",
            f"Dimensions ({len(self._dimensions)}): {', '.join(self._dimensions.keys())}",
        ]

        # Add dimension details
        for dim_name, dimension in self._dimensions.items():
            dim_type = dimension.__class__.__name__
            lines.append(f"  - {dim_name}: {dim_type}")

        return "\n".join(lines)

    @property
    def metadata(self) -> dict[str, Any] | None:
        """Get metadata for this table"""
        metadata = _TABLE_METADATA.get(self._name)
        if metadata is not None:
            return metadata.copy()
        return None

    def validate_lookup(self, **kwargs) -> None:
        """Validate a lookup configuration without executing"""
        # Check that all provided dimensions exist
        for dim_name in kwargs:
            if dim_name not in self._dimensions:
                available_dims = ", ".join(self._dimensions.keys())
                raise ValueError(
                    f"Invalid dimension '{dim_name}' for table '{self._name}'. "
                    f"Available dimensions: {available_dims}",
                )

        # Check that all required dimensions are provided
        required_dims = set(self._dimensions.keys())
        provided_dims = set(kwargs.keys())

        if required_dims != provided_dims:
            missing = required_dims - provided_dims
            extra = provided_dims - required_dims

            error_parts = []
            if missing:
                error_parts.append(f"Missing: {sorted(missing)}")
            if extra:
                error_parts.append(f"Extra: {sorted(extra)}")

            raise ValueError(
                f"Dimension mismatch for table '{self._name}': "
                + "; ".join(error_parts),
            )


def get_table_metadata(table_name: str) -> dict[str, Any] | None:
    """Retrieve metadata for a registered assumption table.

    Args:
        table_name: Name of the table to get metadata for

    Returns:
        dict | None: Copy of metadata dictionary if found, None otherwise

    """
    metadata = _TABLE_METADATA.get(table_name)
    if metadata is not None:
        return metadata.copy()
    return None


def list_tables() -> list[str]:
    """List all registered assumption tables.

    Returns:
        list[str]: List of table names that have been registered

    """
    try:
        registry = PyAssumptionTableRegistry()
        return registry.list_tables()
    except Exception as e:
        logger.warning(f"Failed to get table list from registry: {e}")
        return []


def list_tables_with_metadata() -> dict[str, dict[str, Any]]:
    """List all assumption tables that have metadata stored.

    Returns:
        dict: Dictionary mapping table names to their metadata

    """
    return _TABLE_METADATA.copy()
