from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, Tuple

import polars as pl

if TYPE_CHECKING:
    from .base import ActuarialFrame

def log_query_plan(
    operations: List[Tuple[str, Any]], frame_df: pl.LazyFrame
) -> None: ...
def build_trace_decorator(
    frame_instance: ActuarialFrame,
) -> Callable[..., ActuarialFrame | None]:  # Specify return type of wrapped func
    ...
def append_operation_to_graph(
    frame_instance: ActuarialFrame, name: str, expr: Any
) -> None: ...
