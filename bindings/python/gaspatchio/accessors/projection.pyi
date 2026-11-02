# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import Literal

import polars as pl

from gaspatchio._semantic.ir import OpNode
from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame

from .base import BaseColumnAccessor

class ProjectionColumnAccessor(BaseColumnAccessor):
    _proxy: ColumnProxy | ExpressionProxy

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None: ...
    def _get_node(self) -> OpNode: ...
    def _get_parent_frame(self) -> ActuarialFrame: ...
    def cumulative_survival(
        self,
        rate_timing: Literal["beginning_of_period", "end_of_period"] | None = None,
        start_at: float | None = 1.0,
        *,
        from_survival: bool = False,
    ) -> ExpressionProxy: ...
    def with_period(self, period: int, value: float) -> ExpressionProxy: ...
    def with_periods(self, updates: dict[int, int | float]) -> ExpressionProxy: ...
    def previous_period(self, fill_value: float = 0.0) -> ExpressionProxy: ...
    def next_period(self, fill_value: float = 0.0) -> ExpressionProxy: ...
    def at_period(
        self, relative_period: int, fill_value: float | None = 0.0
    ) -> ExpressionProxy: ...
    def remaining_sum(self) -> ExpressionProxy: ...
    def broadcast_to_periods(
        self, like: ColumnProxy | ExpressionProxy | pl.Expr | None = None
    ) -> ExpressionProxy: ...
    def prospective_value(
        self,
        discount_rate: float | ExpressionProxy | ColumnProxy | None = None,
        discount_factor: ExpressionProxy | ColumnProxy | None = None,
        *,
        timing: Literal["beginning_of_period", "end_of_period"] = "end_of_period",
    ) -> ExpressionProxy: ...
    def accumulate(
        self,
        *,
        initial: float | pl.Expr | ExpressionProxy | ColumnProxy,
        multiplier: float | pl.Expr | ExpressionProxy | ColumnProxy,
        addend: float | pl.Expr | ExpressionProxy | ColumnProxy,
        reverse: bool = False,
    ) -> ExpressionProxy: ...

# What the API reference documents from this module.
__all__ = ["ProjectionColumnAccessor"]
