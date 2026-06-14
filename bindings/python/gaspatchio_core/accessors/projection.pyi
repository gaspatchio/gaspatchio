# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Stub file for projection accessors."""

from typing import TYPE_CHECKING, Literal

import polars as pl

from .base import BaseColumnAccessor

if TYPE_CHECKING:
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame

class ProjectionColumnAccessor(BaseColumnAccessor):
    _proxy: "ColumnProxy | ExpressionProxy"

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None: ...
    def _get_polars_expr(self) -> pl.Expr: ...
    def _get_parent_frame(self) -> "ActuarialFrame": ...
    def _build_discount_factors(
        self,
        cashflow_expr: pl.Expr,
        discount_rate: "float | ExpressionProxy | ColumnProxy | None",
        discount_factor: "ExpressionProxy | ColumnProxy | None",
    ) -> pl.Expr: ...
    def cumulative_survival(
        self,
        rate_timing: "Literal['beginning_of_period', 'end_of_period'] | None" = None,
        start_at: float | None = 1.0,
    ) -> "ExpressionProxy": ...
    def with_period(
        self, period: int, value: float | str
    ) -> "ExpressionProxy": ...
    def with_periods(
        self, updates: dict[int, int | float | str]
    ) -> "ExpressionProxy": ...
    def previous_period(
        self, fill_value: float = 0.0
    ) -> "ExpressionProxy": ...
    def next_period(
        self, fill_value: float = 0.0
    ) -> "ExpressionProxy": ...
    def at_period(
        self, relative_period: int, fill_value: float | None = 0.0
    ) -> "ExpressionProxy": ...
    def prospective_value(
        self,
        discount_rate: "float | ExpressionProxy | ColumnProxy | None" = None,
        discount_factor: "ExpressionProxy | ColumnProxy | None" = None,
        *,
        timing: "Literal['beginning_of_period', 'end_of_period']" = "end_of_period",
    ) -> "ExpressionProxy": ...
    def accumulate(
        self,
        *,
        initial: "str | pl.Expr | ExpressionProxy | ColumnProxy",
        multiply: "str | pl.Expr | ExpressionProxy | ColumnProxy",
        add: "str | pl.Expr | ExpressionProxy | ColumnProxy",
    ) -> "ExpressionProxy": ...
