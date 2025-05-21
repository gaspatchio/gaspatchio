from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, TypeVar

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
ActuarialFrameT = TypeVar("ActuarialFrameT", bound="ActuarialFrame")

class ActuarialFrame:
    """A DataFrame wrapper focusing on core DSL operations.

    Stub file for the base implementation.
    """

    _df: pl.LazyFrame | None
    _column_order: List[str]
    _schema: Dict[str, pl.DataType] | None
    _mode: str
    _verbose: bool
    _threads: int
    _show_query_plan: bool
    _computation_graph: list[tuple[str, Any]]
    _tracing: bool
    # ADDED: Accessor instance cache stubs
    _date_accessor_instance: Optional[DateFrameAccessor]
    _finance_accessor_instance: Optional[FinanceFrameAccessor]
    _excel_accessor_instance: Optional[ExcelFrameAccessor]

    def __init__(
        self,
        data: pl.LazyFrame | pl.DataFrame | Dict[str, Any] | None = None,
        mode: str | None = None,
        verbose: bool | None = None,
        threads: int | None = None,
    ) -> None: ...
    def __getitem__(self, key: str) -> ColumnProxy:
        """Allow df['column'] access, returning a ColumnProxy."""
        ...

    def __setitem__(self, key: str, value: Any) -> None:
        """Handle column assignment using df['column'] = value."""
        ...

    def __dir__(self) -> List[str]:
        """Provide basic list of attributes."""
        ...

    def _expr_to_str(self, value: Any) -> str:
        """Convert an expression to a readable string (simplified)."""
        ...

    def _convert_to_expr(self, value: Any) -> pl.Expr:
        """Convert a value to a Polars expression."""
        ...

    def show_query_plan(self: ActuarialFrameT, enabled: bool = True) -> ActuarialFrameT:
        """Enable or disable query plan logging (basic implementation)."""
        ...

    def trace(self, func: Callable[..., Any]) -> Callable[..., ActuarialFrameT | None]:
        """Decorator to capture operations within a function call in optimize mode."""
        ...

    def collect(self) -> pl.DataFrame:
        """Execute and materialize the dataframe."""
        ...

    def profile(self) -> pl.DataFrame:
        """Execute and materialize the dataframe with profiling (stub)."""
        ...

    def with_columns(self: ActuarialFrameT, *exprs: IntoExprColumn) -> ActuarialFrameT:
        """Add columns to the DataFrame."""
        ...

    def pipe(
        self: ActuarialFrameT,
        func: Callable[..., Optional[ActuarialFrame]],
        *args: Any,
        **kwargs: Any,
    ) -> ActuarialFrameT:
        """Apply a function that accepts and returns an ActuarialFrame."""
        ...

    def get_column_order(self) -> List[str]:
        """Return the tracked order of columns."""
        ...

    # ADDED: Declare accessor properties
    @property
    def date(self) -> DateFrameAccessor: ...
    @property
    def finance(self) -> FinanceFrameAccessor: ...
    @property
    def excel(self) -> ExcelFrameAccessor: ...

    # ADDED: Core function wrapper method signatures
    def fill_series(
        self,
        column: IntoExprColumn,
        limit: int,
    ) -> ExpressionProxy:
        """Apply fill_series using the core function."""
        ...

    def apply_function(
        self,
        func: Callable[..., Any],
        *args: IntoExprColumn,
        return_dtype: pl.DataType = pl.Float64,
    ) -> ExpressionProxy: ...
