"""Type stubs for expression_proxy.py."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

import polars as pl

# No longer need PolarsDataType here, handled in base
# ADDED: Import the base proxy
from .proxy import _BaseProxy

# Import types used in signatures
if TYPE_CHECKING:
    # No longer need Polars namespace types here, inherited from _BaseProxy
    # Keep local types
    from ..accessors.date import DateColumnAccessor
    from ..accessors.finance import FinanceColumnAccessor
    from ..frame.base import ActuarialFrame

    # Keep ExpressionProxy for self-reference if needed, though return types are in base
    from .expression_proxy import ExpressionProxy

# MODIFIED: Inherit from _BaseProxy
class ExpressionProxy(_BaseProxy):
    """Type stub for ExpressionProxy."""

    # Keep specific attributes
    _expr: pl.Expr
    _parent: Optional[ActuarialFrame]
    _date_accessor_instance_expr: Optional[DateColumnAccessor]
    _finance_accessor_instance_expr: Optional[FinanceColumnAccessor]
    _dynamic_accessor_cache: Dict[str, Any]
    _list_broadcast_metadata: Optional[Dict[str, Any]]

    # Keep specific methods
    def __init__(self, expr: pl.Expr, parent: Optional[ActuarialFrame]) -> None: ...
    def _to_expr(self) -> pl.Expr: ...
    def __repr__(self) -> str: ...

    # Keep specific properties
    @property
    def date(self) -> "DateColumnAccessor": ...
    @property
    def finance(self) -> "FinanceColumnAccessor": ...

    # REMOVED: Operator Overloads (inherited)
    # REMOVED: Common Autopatched Methods/Namespaces (inherited)
    # REMOVED: Autopatched Unary Numeric Methods (inherited)
    # REMOVED: Namespaces (inherited)
    # REMOVED: __dir__ (inherited)
