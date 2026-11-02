# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import datetime as dt
from collections.abc import Iterable
from typing import Any, Literal

import polars as pl

from gaspatchio.column import ColumnProxy, ExpressionProxy
from gaspatchio.column.proxy_aware_expr import ProxyAwareExpr
from gaspatchio.frame.base import ActuarialFrame
from gaspatchio.rollforward._builder import RollforwardBuilder
from gaspatchio.schedule import Schedule

from .base import BaseFrameAccessor

type ExprLike = pl.Expr | ColumnProxy | ExpressionProxy

class ProjectionFrameAccessor(BaseFrameAccessor):
    def __init__(self, frame: ActuarialFrame) -> None: ...
    def set(
        self,
        *,
        schedule: Schedule | None = ...,
        valuation_date: dt.date | None = ...,
        until: Literal[
            "maximum_age",
            "term_years",
            "term_months",
            "fixed_date",
        ]
        | None = ...,
        until_value: int | dt.date | str | pl.Expr | None = ...,
        issue_age_column: str = ...,
        start_date: dt.date | None = ...,
        n_periods: int | None = ...,
        frequency: str | None = ...,
        per_policy: bool | None = ...,
        step_years: float | None = ...,
        steps_per_year: int | None = ...,
    ) -> ActuarialFrame: ...
    def rollforward(
        self,
        *,
        states: dict[str, ExprLike],
        points: Iterable[str] | None = ...,
        track_increments: bool = ...,
        lapse_when_all_non_positive: Iterable[str] = ...,
        contract_boundary: ExprLike | None = ...,
        batch_axes: tuple[str, ...] = ...,
        schedule: None = ...,
    ) -> RollforwardBuilder: ...
    def period_dates(self) -> ProxyAwareExpr: ...
    def year_fractions(self) -> ProxyAwareExpr: ...
    def t_years(self) -> ProxyAwareExpr: ...
    def anniversary_mask(self) -> ProxyAwareExpr: ...
    def is_in_force(self, *, end_date_column: str | None = ...) -> ProxyAwareExpr: ...
    def contract_boundary(
        self, *, end_date_column: str | None = ...
    ) -> ProxyAwareExpr: ...
    def canonical_form(self) -> dict[str, Any]: ...
    def source_sha(self) -> str: ...

# What the API reference documents from this module.
__all__ = ["ProjectionFrameAccessor"]
