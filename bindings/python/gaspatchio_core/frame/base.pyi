# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self, TypeVar

import polars as pl

from gaspatchio_core.typing import IntoExprColumn

# ADDED: Import accessor types (use forward references if needed initially)
from ..accessors.date import DateFrameAccessor
from ..accessors.excel import ExcelFrameAccessor
from ..accessors.finance import FinanceFrameAccessor

# ADDED: Import ExpressionProxy for method return types
from ..column import ColumnProxy, ExpressionProxy

if TYPE_CHECKING:
    from ..column import ExpressionProxy

# Define a type variable for the class itself for method chaining
ActuarialFrameT = TypeVar("ActuarialFrameT", bound=ActuarialFrame)

class _AggregationResult:
    """Base class for aggregation results that provides convenient scalar access."""

    _df: pl.DataFrame

    def __init__(self, df: pl.DataFrame) -> None: ...
    def __getitem__(self, key: str) -> Any: ...
    @property
    def to_frame(self) -> pl.DataFrame: ...

class MaxResult(_AggregationResult):
    """Result wrapper for max() method that provides convenient scalar access."""

class MinResult(_AggregationResult):
    """Result wrapper for min() method that provides convenient scalar access."""

class MeanResult(_AggregationResult):
    """Result wrapper for mean() method that provides convenient scalar access."""

class StdResult(_AggregationResult):
    """Result wrapper for std() method that provides convenient scalar access."""

class VarResult(_AggregationResult):
    """Result wrapper for var() method that provides convenient scalar access."""

class MedianResult(_AggregationResult):
    """Result wrapper for median() method that provides convenient scalar access."""

class SumResult(_AggregationResult):
    """Result wrapper for sum() method that provides convenient scalar access."""

class CountResult(_AggregationResult):
    """Result wrapper for count() method that provides convenient scalar access."""

class ProductResult(_AggregationResult):
    """Result wrapper for product() method that provides convenient scalar access."""

class QuantileResult(_AggregationResult):
    """Result wrapper for quantile() method that provides convenient scalar access."""

class ActuarialFrame:
    """A DataFrame wrapper focusing on core DSL operations.

    Stub file for the base implementation.
    """

    _df: pl.LazyFrame | None
    _column_order: list[str]
    _schema: dict[str, pl.DataType] | None
    _mode: str
    _verbose: bool
    _threads: int
    _show_query_plan: bool
    _computation_graph: list[tuple[str, Any]]
    _tracing: bool
    # ADDED: Accessor instance cache stubs
    _date_accessor_instance: DateFrameAccessor | None
    _finance_accessor_instance: FinanceFrameAccessor | None
    _excel_accessor_instance: ExcelFrameAccessor | None
    # ADDED: attribute-eligible column set
    _attr_columns_set: set[str]

    def __init__(
        self,
        data: pl.LazyFrame | pl.DataFrame | dict[str, Any] | None = None,
        mode: str | None = None,
        verbose: bool | None = None,
        threads: int | None = None,
    ) -> None: ...
    def __getitem__(self, key: str) -> ColumnProxy:
        """Allow df['column'] access, returning a ColumnProxy."""

    def __setitem__(self, key: str, value: Any) -> None:
        """Handle column assignment using df['column'] = value."""

    def __getattr__(self, name: str) -> ColumnProxy: ...
    def __setattr__(self, name: str, value: Any) -> None: ...
    def __dir__(self) -> list[str]:
        """Provide enhanced list including accessors and eligible column names."""

    def _convert_to_expr(self, value: Any) -> pl.Expr:
        """Convert a value to a Polars expression."""

    def show_query_plan(self, enabled: bool = True) -> Self:
        """Enable or disable query plan logging (basic implementation)."""

    def trace(self, func: Callable[..., Any]) -> Callable[..., ActuarialFrameT | None]:
        """Decorator to capture operations within a function call in optimize mode."""

    def collect(self, *, engine: str = "streaming") -> pl.DataFrame:
        """Execute and materialize the dataframe.

        Public escape hatch from the lazy ``ActuarialFrame`` graph to an
        eager :class:`polars.DataFrame`. Use inside a stochastic scenario
        kernel when you need column arrays for a numpy RNG.
        """

    def profile(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Execute and materialize the dataframe with profiling, returning (result_df, profile_info)."""

    def with_columns(self, *exprs: IntoExprColumn) -> Self:
        """Add columns to the DataFrame."""

    def select(
        self,
        *exprs: IntoExprColumn,
        **named_exprs: IntoExprColumn,
    ) -> Self:
        """Select columns from the DataFrame."""

    def pipe(
        self,
        func: Callable[..., ActuarialFrame | None],
        *args: Any,
        **kwargs: Any,
    ) -> Self:
        """Apply a function that accepts and returns an ActuarialFrame."""

    def get_column_order(self) -> list[str]:
        """Return the tracked order of columns."""

    # ADDED: Declare accessor properties
    @property
    def date(self) -> DateFrameAccessor: ...
    @property
    def finance(self) -> FinanceFrameAccessor: ...
    @property
    def excel(self) -> ExcelFrameAccessor: ...
    @property
    def columns(self) -> list[str]: ...

    # ADDED: Core function wrapper method signatures
    def fill_series(
        self,
        column: IntoExprColumn,
        start: int = 0,
        increment: int = 1,
    ) -> ExpressionProxy:
        """Apply fill_series using the core function."""
    def max(self) -> MaxResult:
        """Calculate maximum values across all numeric columns.

        Returns a single-row result containing the maximum value for each column.
        """
    def min(self) -> MinResult:
        """Calculate minimum values across all numeric columns.

        Returns a single-row result containing the minimum value for each column.
        """
    def mean(self) -> MeanResult:
        """Calculate mean values across all numeric columns.

        Returns a single-row result containing the mean value for each column.
        """
    def std(self, ddof: int = 1) -> StdResult:
        """Calculate standard deviation across all numeric columns.

        Returns a single-row result containing the standard deviation for each column.
        """
    def var(self, ddof: int = 1) -> VarResult:
        """Calculate variance across all numeric columns.

        Returns a single-row result containing the variance for each column.
        """
    def median(self) -> MedianResult:
        """Calculate median values across all numeric columns.

        Returns a single-row result containing the median value for each column.
        """
    def sum(self) -> SumResult:
        """Calculate sum totals across all numeric columns.

        Returns a single-row result containing the sum total for each column.
        """
    def count(self) -> CountResult:
        """Count non-null values in each column.

        Returns a single-row result containing the count of non-null values for each column.
        """
    def product(self) -> ProductResult:
        """Calculate the product of values in each numeric column.

        Returns a single-row result containing the product for each column.
        """
    def quantile(
        self, quantile: float, interpolation: str = "nearest"
    ) -> QuantileResult:
        """Calculate quantile values across all numeric columns.

        Returns a single-row result containing the specified quantile for each column.
        """
