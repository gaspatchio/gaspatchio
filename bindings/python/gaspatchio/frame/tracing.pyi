# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable

import polars as pl

from .base import ActuarialFrame
from .calculations import CalculationRecord

__all__ = ["build_trace_decorator", "log_query_plan"]

def log_query_plan(
    records: list[CalculationRecord], frame_df: pl.LazyFrame
) -> None: ...
def build_trace_decorator(
    frame_instance: ActuarialFrame,
) -> Callable[..., ActuarialFrame | None]:  # Specify return type of wrapped func
    ...
