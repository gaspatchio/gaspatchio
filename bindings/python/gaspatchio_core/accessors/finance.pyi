"""Stub file for finance accessors."""

from typing import TYPE_CHECKING

import polars as pl

from .base import BaseColumnAccessor, BaseFrameAccessor

if TYPE_CHECKING:
    from ..column.proxy import (
        ColumnProxy,
        ExpressionProxy,
        IntoExprColumn,
    )
    from ..frame.base import ActuarialFrame

class FinanceFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: "ActuarialFrame") -> None: ...
    def present_value(
        self,
        cashflow_col: "IntoExprColumn",
        rate_col: "IntoExprColumn",
        period_col: "IntoExprColumn",
    ) -> "ExpressionProxy": ...

class FinanceColumnAccessor(BaseColumnAccessor):
    _proxy: "ColumnProxy | ExpressionProxy"

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None: ...
    def _get_polars_expr(self) -> pl.Expr: ...
    def discount(
        self, rate_expr: "IntoExprColumn", n_periods_expr: "IntoExprColumn"
    ) -> "ExpressionProxy": ...
