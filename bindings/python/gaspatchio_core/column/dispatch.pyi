"""Type stubs for dispatch.py."""

from typing import TYPE_CHECKING, Any, Callable, Optional, Set, Type

import polars as pl

# Use forward references for types defined elsewhere to avoid circular imports
if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

# Constants
_NUMERIC_UNARY: Set[str]
_NUMERIC_ELEMENTWISE: Set[str]
_NAMESPACES: Set[str]

# Helper Functions
def _unwrap(arg: Any) -> Any: ...
def _wrap(parent: Optional["ActuarialFrame"], result: Any) -> Any: ...
def _ensure_polars_expr_or_literal(arg: Any) -> Any: ...

# Column Type Detection
class ColumnTypeDetector:
    """Unified type detection for columns across schema and computation graph."""
    
    parent_af: Optional["ActuarialFrame"]
    
    def __init__(self, parent_af: Optional["ActuarialFrame"]) -> None: ...
    def is_list_column(self, column_name: str) -> bool: ...
    def get_all_list_columns(self) -> list[str]: ...
    def is_expression_list_output(self, expr: pl.Expr) -> bool: ...

# Descriptor
class DelegatorDescriptor:
    name: str
    wrapper_logic: Callable[..., Any]

    def __init__(self, name: str) -> None: ...
    def __get__(
        self, instance: Optional["ColumnProxy | ExpressionProxy"], owner: Optional[Type["ColumnProxy | ExpressionProxy"]] = None
    ) -> Any: ...

# Wrapper Factory
def _make_wrapper(name: str) -> Callable[..., Any]: ...

# Autopatching Function
def _autopatch(proxy_cls: Type["ColumnProxy | ExpressionProxy"]) -> None: ...
