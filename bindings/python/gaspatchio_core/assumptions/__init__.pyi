# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for Gaspatchio Assumption API v2 - New modular assumption table system.

Every signature here is checked against the implementation by stubtest — the
``gaspatchio_core.assumptions`` tree is deliberately NOT allowlisted, so a stub
that drifts from the runtime fails CI rather than lying to editors and type
checkers (see gh#72).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from gaspatchio_core.assumptions._analysis import InterpolationHint

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.scenarios.shocks import Shock

# Core API Classes
class Table:
    """Main assumption table class with dimension-based structure."""

    def __init__(
        self,
        name: str,
        source: str | Path | pl.DataFrame,
        dimensions: dict[str, str | Dimension],
        value: str = "rate",
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
        storage_mode: Literal["auto", "hash", "array"] = "auto",
        on_missing: str | float = "raise",
    ) -> None: ...
    @classmethod
    def from_scenario_files(
        cls,
        scenario_files: dict[str, str | Path],
        scenario_column: str,
        dimensions: dict[str, str | Dimension],
        value: str,
        name: str | None = None,
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> Table: ...
    @classmethod
    def from_scenario_template(
        cls,
        path_template: str,
        scenario_ids: list[str] | list[int],
        scenario_column: str,
        dimensions: dict[str, str | Dimension],
        value: str,
        name: str | None = None,
        validate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> Table: ...
    @classmethod
    def from_shocks(
        cls,
        base_table: Table,
        shocks: dict[str, list[Shock]],
        value_column: str,
    ) -> dict[str, Table]: ...
    def lookup(
        self,
        _dimensions: dict[str, str | pl.Expr | ColumnProxy] | None = None,
        on_missing: str | float | None = None,
        **kwargs: str | pl.Expr | ColumnProxy,
    ) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
    def with_shock(self, shock: Shock, name: str | None = None) -> Table: ...
    def extend(
        self,
        source: str | Path | pl.DataFrame,
        dimensions: dict[str, Dimension] | None = None,
        validate: bool = True,
    ) -> Table: ...
    def to_dataframe(self) -> pl.DataFrame: ...
    def describe(self) -> str: ...
    def dimension_values(self, dimension: str) -> list[Any]: ...
    def validate_lookup(self, **kwargs) -> None: ...
    @property
    def name(self) -> str: ...
    @property
    def schema(self) -> TableSchema: ...
    @property
    def dimensions(self) -> dict[str, Dimension]: ...
    @property
    def metadata(self) -> dict[str, Any] | None: ...
    @property
    def storage_mode(self) -> str: ...

class TableBuilder:
    """Fluent builder for constructing assumption tables step by step."""

    def __init__(self, name: str) -> None: ...
    def from_source(self, source: str | Path | pl.DataFrame) -> TableBuilder: ...
    def with_data_dimension(
        self,
        name: str,
        column: str,
        rename_to: str | None = None,
        dtype: pl.DataType | None = None,
    ) -> TableBuilder: ...
    def with_melt_dimension(
        self,
        name: str,
        columns: list[str],
        overflow: Any | None = None,
        fill: Any | None = None,
    ) -> TableBuilder: ...
    def with_categorical_dimension(
        self,
        name: str,
        value: Any,
        dimension_name: str | None = None,
    ) -> TableBuilder: ...
    def with_computed_dimension(
        self,
        name: str,
        expression: pl.Expr,
        alias: str | None = None,
    ) -> TableBuilder: ...
    def with_value_column(self, name: str) -> TableBuilder: ...
    def with_dimension(self, name: str, dimension: Dimension) -> TableBuilder: ...
    def build(self) -> Table: ...
    def reset(self) -> TableBuilder: ...
    def copy(self) -> TableBuilder: ...

# Analysis Classes
@dataclass
class DimensionInfo:
    """Information about a detected dimension in the data."""

    name: str
    dtype: str
    unique_count: int
    sample_values: list[Any]
    suggested_type: Literal["key", "melt", "categorical", "value"]
    numeric_pattern: str | None = None

@dataclass
class TableSchema:
    """Complete schema analysis of an assumption table."""

    data_dimensions: list[DimensionInfo]
    value_columns: list[str]
    format: Literal["curve", "wide"]
    overflow_candidate: str | None = None
    interpolation_opportunities: list[InterpolationHint] = ...
    row_count: int = 0

    def to_dict(self) -> dict[str, Any]: ...

# Dimension Classes
class Dimension(metaclass=abc.ABCMeta):
    """Base class for dimension types."""

    @abc.abstractmethod
    def validate(self, df: pl.DataFrame) -> None: ...
    @abc.abstractmethod
    def process(self, df: pl.DataFrame) -> pl.DataFrame: ...

@dataclass
class DataDimension(Dimension):
    """Represents a simple data column dimension."""

    column: str
    rename_to: str | None = None
    dtype: pl.DataType | None = None
    def validate(self, df: pl.DataFrame) -> None: ...
    def process(self, df: pl.DataFrame) -> pl.DataFrame: ...

@dataclass
class MeltDimension(Dimension):
    """Melts wide-format columns into a long-format dimension."""

    columns: list[str]
    name: str = "variable"
    overflow: OverflowStrategy | None = None
    fill: FillStrategy | None = None
    def validate(self, df: pl.DataFrame) -> None: ...
    def process(self, df: pl.DataFrame) -> pl.DataFrame: ...

@dataclass
class CategoricalDimension(Dimension):
    """Adds a constant categorical value to the data."""

    value: Any
    name: str | None = None
    def validate(self, df: pl.DataFrame) -> None: ...
    def process(self, df: pl.DataFrame) -> pl.DataFrame: ...

@dataclass
class ComputedDimension(Dimension):
    """Creates computed columns based on expressions."""

    expression: pl.Expr
    name: str
    def validate(self, df: pl.DataFrame) -> None: ...
    def process(self, df: pl.DataFrame) -> pl.DataFrame: ...

# Strategy Classes
class OverflowStrategy(metaclass=abc.ABCMeta):
    """Base class for overflow handling strategies."""

@dataclass
class ExtendOverflow(OverflowStrategy):
    """Extends a boundary column's value out to a maximum key."""

    column: str
    to_value: int = 200
    from_value: int | None = None

@dataclass
class AutoDetectOverflow(OverflowStrategy):
    """Detects overflow columns by name pattern and extends them."""

    patterns: list[str] = ...
    to_value: int = 200

class FillStrategy(metaclass=abc.ABCMeta):
    """Base class for fill strategies."""

@dataclass
class LinearInterpolate(FillStrategy):
    """Interpolates missing values between known points."""

    method: Literal["linear", "log-linear", "cubic"] = "linear"
    fill_gaps: bool = True
    extrapolate: bool = False

@dataclass
class FillConstant(FillStrategy):
    """Fills missing values with a constant."""

    value: Any

@dataclass
class FillForward(FillStrategy):
    """Forward-fills missing values."""

    limit: int | None = None

# Analysis Functions
def analyze_table(
    source: str | Path | pl.DataFrame,
    sample_rows: int = 1000,
    detect_overflow: bool = True,
    detect_interpolation: bool = True,
) -> TableSchema: ...

# Metadata Functions
def get_table_metadata(table_name: str) -> dict[str, Any] | None: ...
def list_tables() -> list[str]: ...
def list_tables_with_metadata() -> dict[str, dict[str, Any]]: ...
