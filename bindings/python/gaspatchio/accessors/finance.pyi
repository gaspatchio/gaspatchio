# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Stub file for finance accessors."""

from typing import TYPE_CHECKING, Literal

import polars as pl

from .base import BaseColumnAccessor, BaseFrameAccessor

if TYPE_CHECKING:
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..typing import IntoExprColumn
    from ..frame.base import ActuarialFrame

class FinanceFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: "ActuarialFrame") -> None: ...
    def discount_factor(
        self,
        rate_col: str,
        periods_col: str,
        output_col: str,
        method: "Literal['spot', 'forward']" = "spot",
    ) -> "ActuarialFrame": ...
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
    def to_monthly(
        self, method: "Literal['compound', 'simple']" = "compound"
    ) -> "ExpressionProxy": ...
    def compound(
        self, rate: float, periods_per_year: int
    ) -> "ExpressionProxy": ...
    def discount(
        self, rate_expr: "IntoExprColumn", n_periods_expr: "IntoExprColumn"
    ) -> "ExpressionProxy": ...
