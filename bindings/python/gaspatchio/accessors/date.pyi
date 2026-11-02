# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import datetime

import polars as pl

from gaspatchio.column.column_proxy import ColumnProxy
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame

from .base import BaseColumnAccessor, BaseFrameAccessor

class DateFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: ActuarialFrame) -> None: ...
    def create_timeline(
        self,
        start_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        end_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        freq: str = ...,  # Ellipsis for default
        new_col_name: str = ...,  # Ellipsis for default
        closed: str = ...,  # Ellipsis for default
    ) -> ActuarialFrame: ...
    def add_duration(
        self,
        date_col: str | ColumnProxy | ExpressionProxy | pl.Expr | pl.Series,
        duration_str: str,
        new_col_name: str | None = ...,  # Ellipsis for default
    ) -> ActuarialFrame: ...

class DateColumnAccessor(BaseColumnAccessor):
    _proxy: ColumnProxy | ExpressionProxy

    def __init__(self, proxy: ColumnProxy | ExpressionProxy) -> None: ...
    def months_between(
        self,
        other: ColumnProxy | ExpressionProxy | datetime.date,
    ) -> ExpressionProxy: ...
    def to_period(self, freq: str = ...) -> ExpressionProxy:  # Ellipsis for default
        ...

# What the API reference documents from this module.
__all__ = ["DateColumnAccessor", "DateFrameAccessor"]
