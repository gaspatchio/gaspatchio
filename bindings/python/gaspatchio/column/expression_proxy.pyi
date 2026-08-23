# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for expression_proxy.py."""

from typing import TYPE_CHECKING, Any, Literal

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
    from ..accessors.projection import ProjectionColumnAccessor
    from ..frame.base import ActuarialFrame

# MODIFIED: Inherit from _BaseProxy
class ExpressionProxy(_BaseProxy):
    """Type stub for ExpressionProxy."""

    # Keep specific attributes
    _expr: pl.Expr
    _parent: ActuarialFrame | None
    _date_accessor_instance_expr: DateColumnAccessor | None
    _finance_accessor_instance_expr: FinanceColumnAccessor | None
    _projection_accessor_instance_expr: ProjectionColumnAccessor | None
    _dynamic_accessor_cache: dict[str, Any]
    _kind_explicit: str | None
    _shape_cached: Any
    _kind_cached: Any

    # Keep specific methods
    def __init__(
        self,
        expr: pl.Expr,
        parent: ActuarialFrame | None,
        *,
        kind: str | None = ...,
    ) -> None: ...
    def _to_expr(self) -> pl.Expr: ...

    # Keep specific properties
    @property
    def shape(self) -> Literal["scalar", "list", "unknown"]: ...
    @property
    def kind(self) -> Literal["value", "comparison", "boolean_mask", "unknown"]: ...
    @property
    def date(self) -> DateColumnAccessor: ...
    @property
    def finance(self) -> FinanceColumnAccessor: ...
    @property
    def projection(self) -> ProjectionColumnAccessor: ...

    # REMOVED: Operator Overloads (inherited)
    # REMOVED: Common Autopatched Methods/Namespaces (inherited)
    # REMOVED: Autopatched Unary Numeric Methods (inherited)
    # REMOVED: Namespaces (inherited)
    # REMOVED: __dir__ (inherited)
