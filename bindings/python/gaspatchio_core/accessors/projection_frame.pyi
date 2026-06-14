# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for ProjectionFrameAccessor."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Literal

import polars as pl

from .base import BaseFrameAccessor

if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame
    from ..rollforward._builder import RollforwardBuilder
    from ..schedule import Schedule

class ProjectionFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: "ActuarialFrame") -> None: ...
    def set(
        self,
        *,
        schedule: "Schedule | None" = ...,
        valuation_date: dt.date | None = ...,
        until: Literal[
            "maximum_age",
            "term_years",
            "term_months",
            "fixed_date",
            "next_anniversary",
        ]
        | None = ...,
        until_value: int | dt.date | str | pl.Expr | None = ...,
        issue_age_column: str = ...,
        inception_column: str = ...,
        start_date: dt.date | None = ...,
        n_periods: int | None = ...,
        frequency: str | None = ...,
        per_policy: bool | None = ...,
    ) -> "ActuarialFrame": ...
    def rollforward(self, **kwargs: Any) -> "RollforwardBuilder": ...
    def period_dates(self) -> pl.Expr: ...
    def year_fractions(self) -> pl.Expr: ...
    def t_years(self) -> pl.Expr: ...
    def anniversary_mask(self) -> pl.Expr: ...
    def is_in_force(self, *, end_date_column: str | None = ...) -> pl.Expr: ...
    def contract_boundary(self, *, end_date_column: str | None = ...) -> pl.Expr: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...
