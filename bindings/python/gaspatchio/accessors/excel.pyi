# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for Excel accessors."""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame
    from ..typing import IntoExprColumn  # For yearfrac

type BasisType = (
    Literal[
        0,
        1,
        2,
        3,
        4,
        "us_nasd_30_360",
        "act/act",
        "actual/360",
        "actual/365",
        "european_30_360",
    ]
    | int
    | str
)

class ExcelFrameAccessor:
    _frame: ActuarialFrame

    def __init__(self, frame: ActuarialFrame) -> None: ...

class ExcelColumnAccessor:
    _proxy: ExpressionProxy | ColumnProxy  # Assuming ColumnProxy is also possible

    def __init__(self, proxy: ExpressionProxy | ColumnProxy) -> None: ...
    def from_excel_serial(self, epoch: str = ...) -> ExpressionProxy: ...
    def yearfrac(
        self, end_date_expr: IntoExprColumn, basis: BasisType = ...
    ) -> ExpressionProxy: ...
    def irr(
        self,
        *,
        guess: IntoExprColumn | None = ...,
        default_guess: float | None = ...,
    ) -> ExpressionProxy: ...
    def pv(
        self,
        nper: IntoExprColumn,
        pmt: IntoExprColumn,
        *,
        fv: float | None = ...,
        typ: int | None = ...,
    ) -> ExpressionProxy: ...
    def round(self, num_digits: int = ...) -> ExpressionProxy: ...
    def days(self, start_date: IntoExprColumn) -> ExpressionProxy: ...
    def edate(self, months: IntoExprColumn) -> ExpressionProxy: ...
    def eomonth(self, months: IntoExprColumn) -> ExpressionProxy: ...
