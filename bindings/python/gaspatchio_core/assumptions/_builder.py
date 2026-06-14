# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Builder pattern implementation for Table creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from ._api import Table
from ._dimensions import (
    CategoricalDimension,
    ComputedDimension,
    DataDimension,
    Dimension,
    MeltDimension,
)


class TableBuilder:
    """Fluent builder for complex table configurations."""

    def __init__(self, name: str) -> None:
        """
        Initialize a new TableBuilder.

        Args:
            name: Unique table name for registration

        """
        self.name = name
        self._dimensions: dict[str, Dimension] = {}
        self._source: str | Path | pl.DataFrame | None = None
        self._value: str = "rate"

    def from_source(self, source: str | Path | pl.DataFrame) -> TableBuilder:
        """
        Set the data source for the table.

        Args:
            source: Data source (file path or DataFrame)

        Returns:
            Self for chaining

        """
        self._source = source
        return self

    def with_data_dimension(
        self,
        name: str,
        column: str,
        rename_to: str | None = None,
        dtype: pl.DataType | None = None,
    ) -> TableBuilder:
        """
        Add a data dimension that maps directly from a column.

        Args:
            name: Dimension name
            column: Source column name
            rename_to: Optional rename for the dimension
            dtype: Optional data type conversion

        Returns:
            Self for chaining

        """
        self._dimensions[name] = DataDimension(
            column=column,
            rename_to=rename_to,
            dtype=dtype,
        )
        return self

    def with_melt_dimension(
        self,
        name: str,
        columns: list[str],
        overflow: Any | None = None,
        fill: Any | None = None,
    ) -> TableBuilder:
        """
        Add a melt dimension that transforms wide columns to long format.

        Args:
            name: Dimension name
            columns: List of columns to melt
            overflow: Optional overflow strategy
            fill: Optional fill strategy

        Returns:
            Self for chaining

        """
        self._dimensions[name] = MeltDimension(
            columns=columns,
            name=name,
            overflow=overflow,
            fill=fill,
        )
        return self

    def with_categorical_dimension(
        self,
        name: str,
        value: Any,
        dimension_name: str | None = None,
    ) -> TableBuilder:
        """
        Add a categorical dimension with a constant value.

        Args:
            name: Dimension name
            value: Constant value for this dimension
            dimension_name: Optional custom name for the dimension column

        Returns:
            Self for chaining

        """
        self._dimensions[name] = CategoricalDimension(
            value=value,
            name=dimension_name or name,
        )
        return self

    def with_computed_dimension(
        self,
        name: str,
        expression: pl.Expr,
        alias: str | None = None,
    ) -> TableBuilder:
        """
        Add a computed dimension from an expression.

        Args:
            name: Dimension name
            expression: Polars expression to compute the dimension
            alias: Optional alias for the computed column

        Returns:
            Self for chaining

        """
        self._dimensions[name] = ComputedDimension(
            expression=expression,
            name=alias or name,
        )
        return self

    def with_value_column(self, name: str) -> TableBuilder:
        """
        Set the name of the value column.

        Args:
            name: Value column name

        Returns:
            Self for chaining

        """
        self._value = name
        return self

    def with_dimension(self, name: str, dimension: Dimension) -> TableBuilder:
        """
        Add a pre-configured dimension object.

        Args:
            name: Dimension name
            dimension: Dimension object

        Returns:
            Self for chaining

        """
        self._dimensions[name] = dimension
        return self

    def build(self) -> Table:
        """
        Build the Table object from the configured builder.

        Returns:
            Configured Table instance

        Raises:
            ValueError: If source is not set or no dimensions are configured

        """
        if self._source is None:
            msg = "Source must be set before building table"
            raise ValueError(msg)

        if not self._dimensions:
            msg = "At least one dimension must be configured"
            raise ValueError(msg)

        return Table(
            name=self.name,
            source=self._source,
            dimensions=self._dimensions,
            value=self._value,
        )

    def reset(self) -> TableBuilder:
        """
        Reset the builder to initial state (keeping only the name).

        Returns:
            Self for chaining

        """
        self._dimensions = {}
        self._source = None
        self._value = "rate"
        return self

    def copy(self) -> TableBuilder:
        """
        Create a copy of this builder.

        Returns:
            New TableBuilder with same configuration

        """
        new_builder = TableBuilder(self.name)
        new_builder._dimensions = self._dimensions.copy()
        new_builder._source = self._source
        new_builder._value = self._value
        return new_builder

    def __repr__(self) -> str:
        """Return string representation of the builder."""
        return (
            f"TableBuilder(name={self.name!r}, "
            f"dimensions={len(self._dimensions)}, "
            f"source={'set' if self._source else 'unset'}, "
            f"value={self._value!r})"
        )
