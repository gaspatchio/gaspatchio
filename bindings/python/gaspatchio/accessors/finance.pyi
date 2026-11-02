# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import Literal

import polars as pl

from gaspatchio._semantic.ir import AttrValue
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame

from .base import BaseColumnAccessor, BaseFrameAccessor

class FinanceFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: ActuarialFrame) -> None: ...
    def discount_factor(
        self,
        rate_col: str,
        periods_col: str,
        output_col: str,
        method: Literal["spot", "forward"] = "spot",
    ) -> ActuarialFrame: ...
    def present_value(
        self,
        cashflow_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        rate_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        period_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
    ) -> ExpressionProxy: ...

class FinanceColumnAccessor(BaseColumnAccessor):
    _proxy: ColumnProxy | ExpressionProxy

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None: ...
    def _emit(
        self,
        name: str,
        extra_args: tuple[object, ...] = ...,
        attrs: tuple[tuple[str, AttrValue], ...] = ...,
    ) -> ExpressionProxy: ...
    def to_monthly(
        self, method: Literal["compound", "simple"] = "compound"
    ) -> ExpressionProxy: ...
    def compound(self, rate: float, periods_per_year: int) -> ExpressionProxy: ...
    def discount(
        self,
        rate_expr: ColumnProxy | ExpressionProxy | pl.Expr | float,
        n_periods_expr: ColumnProxy | ExpressionProxy | pl.Expr | float,
    ) -> ExpressionProxy: ...

# What the API reference documents from this module.
__all__ = ["FinanceColumnAccessor", "FinanceFrameAccessor"]
