# ABOUTME: Type stubs for conditional expressions (when/then/otherwise)
# ABOUTME: Provides type hints for Excel-style IF() with list broadcasting
"""Type stubs for conditional expressions (when/then/otherwise).

Provides type hints for Excel-style IF() functionality with automatic
list broadcasting for actuarial projections.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from gaspatchio_core.column.expression_proxy import ExpressionProxy
from gaspatchio_core.frame.base import ActuarialFrame

class ConditionalProxy:
    """Represents an in-progress conditional expression chain."""

    _list_columns: set[str] | None
    _otherwise_expr: pl.Expr | None

    def __init__(
        self, condition_expr: pl.Expr, parent: ActuarialFrame | None
    ) -> None: ...
    def then(self, value: Any) -> ConditionalProxy: ...  # noqa: ANN401
    def when(self, condition: Any) -> ConditionalProxy: ...  # noqa: ANN401
    def otherwise(self, value: Any) -> ExpressionProxy: ...  # noqa: ANN401
    def needs_list_broadcasting(self) -> bool: ...
    def get_list_broadcasting_metadata(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...
    def _to_expr(self) -> pl.Expr: ...

def when(condition: Any) -> ConditionalProxy: ...  # noqa: ANN401
