"""Type stubs for Gaspatchio Assumption API v2 - New modular assumption table system."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

if TYPE_CHECKING:
    from gaspatchio_core.column.column_proxy import ColumnProxy
    from gaspatchio_core.column.expression_proxy import ExpressionProxy
    from gaspatchio_core.scenarios.shocks import Shock

# Type alias for lookup arguments
LookupValue = str | pl.Expr | "ColumnProxy" | "ExpressionProxy"

# Type alias for storage mode
StorageModeType = Literal["auto", "hash", "array"]

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
        storage_mode: StorageModeType = "auto",
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
    def lookup(self, **kwargs: LookupValue) -> pl.Expr: ...
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
    def schema(self) -> TableSchema: ...
    @property
    def dimensions(self) -> dict[str, Dimension]: ...
    @property
    def metadata(self) -> dict[str, Any] | None: ...
    @property
    def storage_mode(self) -> str: ...

class TableBuilder:
    """Builder pattern for constructing assumption tables with validation."""

    def __init__(self, name: str) -> None: ...
    def source(self, source: str | Path | pl.DataFrame) -> TableBuilder: ...
    def dimension(self, name: str, dimension: str | Dimension) -> TableBuilder: ...
    def value(self, column_name: str) -> TableBuilder: ...
    def metadata(self, metadata: dict[str, Any]) -> TableBuilder: ...
    def validate(self, enabled: bool = True) -> TableBuilder: ...
    def build(self) -> Table: ...

# Analysis Classes
class DimensionInfo:
    """Information about a detected dimension in the data."""

    name: str
    dtype: str
    unique_count: int
    sample_values: list[Any]
    suggested_type: Literal["key", "melt", "categorical", "value"]
    numeric_pattern: str | None

class TableSchema:
    """Complete schema analysis of an assumption table."""

    data_dimensions: list[DimensionInfo]
    value_columns: list[str]
    format: Literal["long", "wide", "mixed"]
    overflow_candidate: str | None
    interpolation_opportunities: list[Any]
    row_count: int

    def to_dict(self) -> dict[str, Any]: ...

# Dimension Classes
class Dimension:
    """Base class for dimension types."""

    def validate(self, df: pl.DataFrame) -> None: ...
    def process(self, df: pl.DataFrame) -> pl.DataFrame: ...

class DataDimension(Dimension):
    """Represents a simple data column dimension."""

    def __init__(self, column_name: str) -> None: ...

class MeltDimension(Dimension):
    """Transforms wide format data to long format."""

    def __init__(
        self,
        id_vars: list[str],
        value_vars: list[str],
        var_name: str = "variable",
        value_name: str = "value",
    ) -> None: ...

class CategoricalDimension(Dimension):
    """Adds a constant categorical value to the data."""

    def __init__(self, name: str, value: Any) -> None: ...

class ComputedDimension(Dimension):
    """Creates computed columns based on expressions."""

    def __init__(self, name: str, expression: pl.Expr) -> None: ...

# Strategy Classes
class OverflowStrategy:
    """Base class for overflow handling strategies."""

class ExtendOverflow(OverflowStrategy):
    """Extends boundary values for overflow handling."""

    def __init__(self, max_extension: int = 200) -> None: ...

class AutoDetectOverflow(OverflowStrategy):
    """Automatically detects and handles overflow columns."""

    def __init__(self, max_extension: int = 200) -> None: ...

class FillStrategy:
    """Base class for fill strategies."""

class LinearInterpolate(FillStrategy):
    """Linear interpolation fill strategy."""

class FillConstant(FillStrategy):
    """Fill with constant value strategy."""

    def __init__(self, value: Any) -> None: ...

class FillForward(FillStrategy):
    """Forward fill strategy."""

# Analysis Functions
def analyze_table(
    source: str | Path | pl.DataFrame,
    sample_size: int = 1000,
) -> TableSchema: ...

# Metadata Functions
def get_table_metadata(table_name: str) -> dict[str, Any] | None: ...
def list_tables() -> list[str]: ...
def list_tables_with_metadata() -> dict[str, dict[str, Any]]: ...
