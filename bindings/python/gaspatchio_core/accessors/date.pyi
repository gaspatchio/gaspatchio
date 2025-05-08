"""Type stubs for date accessors."""

import datetime
from typing import TYPE_CHECKING, Literal, Union

from .base import BaseColumnAccessor, BaseFrameAccessor

if TYPE_CHECKING:
    from ..column.proxy import ColumnProxy, ExpressionProxy
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
    def create_projection_timeline(
        self,
        valuation_date: datetime.date,
        projection_end_type: Literal[
            "maximum_age", "term_years", "term_months", "fixed_date"
        ] = ...,
        projection_end_value: Union[int, datetime.date] = ...,
        issue_age_column: str = ...,
        projection_frequency: Literal[
            "monthly", "quarterly", "semi-annual", "annual"
        ] = ...,
        projection_start_offset_months: int = ...,
        store_start_date: bool = ...,
        store_end_date: bool = ...,
        output_column: str = ...,
    ) -> "ActuarialFrame": ...

class DateColumnAccessor(BaseColumnAccessor):
    _proxy: "ColumnProxy | ExpressionProxy"

    def __init__(self, proxy: "ColumnProxy | ExpressionProxy") -> None: ...
    def to_period(self, freq: str = ...) -> "ExpressionProxy":  # Ellipsis for default
        ...
