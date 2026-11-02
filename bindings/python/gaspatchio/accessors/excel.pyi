# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import datetime

import polars as pl

from gaspatchio._semantic.ir import AttrValue
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame

type BasisType = int | str

class ExcelFrameAccessor:
    _frame: ActuarialFrame

    def __init__(self, frame: ActuarialFrame) -> None: ...

class ExcelColumnAccessor:
    _proxy: ExpressionProxy | ColumnProxy  # Assuming ColumnProxy is also possible

    def __init__(self, proxy: ExpressionProxy | ColumnProxy) -> None: ...
    def _get_parent_frame(self) -> ActuarialFrame: ...
    def _emit(
        self,
        name: str,
        extra_args: tuple[object, ...] = ...,
        attrs: tuple[tuple[str, AttrValue], ...] = ...,
    ) -> ExpressionProxy: ...
    def from_excel_serial(self, epoch: str = ...) -> ExpressionProxy: ...
    def yearfrac(
        self,
        end_date_expr: ColumnProxy | ExpressionProxy | pl.Expr | datetime.date,
        basis: BasisType = ...,
    ) -> ExpressionProxy: ...
    def irr(
        self,
        *,
        guess: ColumnProxy | ExpressionProxy | pl.Expr | float | None = ...,
        default_guess: float | None = ...,
    ) -> ExpressionProxy: ...
    def pv(
        self,
        nper: ColumnProxy | ExpressionProxy | pl.Expr | float,
        pmt: ColumnProxy | ExpressionProxy | pl.Expr | float,
        *,
        fv: float | None = ...,
        typ: int | None = ...,
    ) -> ExpressionProxy: ...
    def round(self, num_digits: int = ...) -> ExpressionProxy: ...
    def norm_s_dist(self, *, cumulative: bool = ...) -> ExpressionProxy: ...
    def days(
        self, start_date: ColumnProxy | ExpressionProxy | pl.Expr | datetime.date
    ) -> ExpressionProxy: ...
    def edate(
        self, months: ColumnProxy | ExpressionProxy | pl.Expr | int
    ) -> ExpressionProxy: ...
    def eomonth(
        self, months: ColumnProxy | ExpressionProxy | pl.Expr | int
    ) -> ExpressionProxy: ...

# What the API reference documents from this module.
__all__ = ["ExcelColumnAccessor"]
