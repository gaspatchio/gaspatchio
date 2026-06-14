# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for date accessors."""

from typing import TYPE_CHECKING

from .base import BaseColumnAccessor, BaseFrameAccessor

if TYPE_CHECKING:
    from ..column.column_proxy import ColumnProxy
    from ..column.expression_proxy import ExpressionProxy
    from ..frame.base import ActuarialFrame
    from ..typing import IntoExprColumn

class DateFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: "ActuarialFrame") -> None: ...
    def create_timeline(
        self,
        start_col: "IntoExprColumn",
        end_col: "IntoExprColumn",
        freq: str = ...,  # Ellipsis for default
        new_col_name: str = ...,  # Ellipsis for default
        closed: str = ...,  # Ellipsis for default
    ) -> "ActuarialFrame": ...
    def add_duration(
        self,
        date_col: "IntoExprColumn",
        duration_str: str,
        new_col_name: str | None = ...,  # Ellipsis for default
    ) -> "ActuarialFrame": ...

class DateColumnAccessor(BaseColumnAccessor):
    _proxy: "ColumnProxy | ExpressionProxy"

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None: ...
    def to_period(self, freq: str = ...) -> "ExpressionProxy":  # Ellipsis for default
        ...
