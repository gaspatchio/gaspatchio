# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for column_proxy.py."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, ClassVar, Dict, Literal, Optional

import polars as pl
from polars.type_aliases import PolarsDataType

# ADDED: Import the base proxy
from .proxy import _BaseProxy

# Import types used in signatures
if TYPE_CHECKING:
    # No longer need Polars namespace types here, inherited from _BaseProxy
    # Keep local types
    from ..accessors.date import DateColumnAccessor
    from ..accessors.excel import ExcelColumnAccessor
    from ..accessors.finance import FinanceColumnAccessor
    from ..accessors.projection import ProjectionColumnAccessor
    from ..frame.base import ActuarialFrame
    from .expression_proxy import ExpressionProxy

# MODIFIED: Inherit from _BaseProxy
class ColumnProxy(_BaseProxy):
    """Type stub for ColumnProxy."""

    # Keep specific attributes
    name: str
    _parent: Optional[ActuarialFrame]
    _date_accessor_instance_col: Optional[DateColumnAccessor]
    _excel_accessor_instance_col: Optional[ExcelColumnAccessor]
    _finance_accessor_instance_col: Optional[FinanceColumnAccessor]
    _projection_accessor_instance_col: Optional[ProjectionColumnAccessor]
    _dynamic_accessor_cache: Dict[str, Any]
    _shape_cached: Any

    kind: ClassVar[Literal["value"]]

    # Keep specific methods
    def __init__(self, name: str, parent: Optional[ActuarialFrame]) -> None: ...
    def _to_expr(self) -> pl.Expr: ...
    def __repr__(self) -> str: ...
    def apply(
        self, func: Callable, return_dtype: PolarsDataType | None = None
    ) -> "ExpressionProxy": ...

    # Keep specific properties
    @property
    def shape(self) -> Literal["scalar", "list", "unknown"]: ...
    @property
    def date(self) -> "DateColumnAccessor": ...
    @property
    def finance(self) -> "FinanceColumnAccessor": ...
    @property
    def excel(self) -> "ExcelColumnAccessor": ...
    @property
    def projection(self) -> "ProjectionColumnAccessor": ...

    # REMOVED: Operator Overloads (inherited)
    # REMOVED: Common Autopatched Methods/Namespaces (inherited)
    # REMOVED: Autopatched Unary Numeric Methods (inherited)
    # REMOVED: Namespaces (inherited)
    # REMOVED: __dir__ (inherited)
