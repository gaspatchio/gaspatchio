# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import Literal

import numpy as np
import numpy.typing as npt
import polars as pl

from gaspatchio_core.schedule import DayCount

type InterpolationMethod = Literal["linear"]
type TimeInput = (
    float | int | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr
)

class Curve:
    tenors: tuple[float, ...]
    rates: tuple[float, ...]
    day_count: DayCount
    interpolation: InterpolationMethod

    def __init__(
        self,
        tenors: tuple[float, ...],
        rates: tuple[float, ...],
        day_count: DayCount,
        interpolation: InterpolationMethod = ...,
    ) -> None: ...
    @classmethod
    def from_zero_rates(
        cls,
        *,
        tenors: list[float],
        rates: list[float],
        day_count: DayCount | None = ...,
        interpolation: InterpolationMethod = ...,
    ) -> Curve: ...
    @classmethod
    def from_par_rates(
        cls,
        *,
        tenors: list[float],
        par_rates: list[float],
        day_count: DayCount | None = ...,
        interpolation: InterpolationMethod = ...,
    ) -> Curve: ...
    def spot_rate(
        self,
        t: TimeInput,
    ) -> float | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr: ...
    def discount_factor(
        self,
        t: TimeInput,
    ) -> float | list[float] | npt.NDArray[np.float64] | pl.Series | pl.Expr: ...
    def forward_rate(self, *, t1: float, t2: float) -> float: ...
    def shift_parallel(self, *, bps: float) -> Curve: ...
    def key_rate_shift(self, *, tenor: float, bps: float) -> Curve: ...
    def canonical_form(self) -> dict[str, object]: ...
    def source_sha(self) -> str: ...

__all__ = ["Curve"]
