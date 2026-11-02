# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Sequence
from typing import Any, Literal

import polars as pl

from gaspatchio._authoring.escape import PolarsNative
from gaspatchio._semantic.ir import OpNode
from gaspatchio.accessors.date import DateColumnAccessor
from gaspatchio.accessors.excel import ExcelColumnAccessor
from gaspatchio.accessors.finance import FinanceColumnAccessor
from gaspatchio.accessors.projection import ProjectionColumnAccessor
from gaspatchio.frame.base import ActuarialFrame

from ._generated_proxy import _GeneratedProxySurface
from .shape import Kind

class ExpressionProxy(_GeneratedProxySurface):
    # Keep specific attributes
    _parent: ActuarialFrame | None
    _node_cached: OpNode | None
    _lowered: pl.Expr | None
    _date_accessor_instance_expr: DateColumnAccessor | None
    _finance_accessor_instance_expr: FinanceColumnAccessor | None
    _projection_accessor_instance_expr: ProjectionColumnAccessor | None
    _dynamic_accessor_cache: dict[str, Any]
    _kind_explicit: Kind | None
    _shape_cached: Any
    _kind_cached: Any

    # Keep specific methods
    def __init__(
        self,
        expr: pl.Expr,
        parent: ActuarialFrame | None,
        *,
        kind: Kind | None = ...,
    ) -> None: ...
    @classmethod
    def _from_node(
        cls,
        node: OpNode,
        parent: ActuarialFrame | None,
        *,
        kind: Kind | None = ...,
    ) -> ExpressionProxy: ...
    def _init_fields(
        self,
        *,
        node: OpNode | None,
        lowered: pl.Expr | None,
        parent: ActuarialFrame | None,
        kind: Kind | None,
    ) -> None: ...
    def _to_expr(self) -> pl.Expr: ...
    # The explicit way out of the vocabulary, on a formula already under
    # way: one Polars expression method, minting an ``EngineNative`` node.
    def polars_native(self, *, deps: Sequence[str] | None = ...) -> PolarsNative: ...

    # The semantic node this proxy carries, and the expression derived from
    # it on first contact -- both resolved lazily, hence properties.
    @property
    def _node(self) -> OpNode: ...
    @property
    def _expr(self) -> pl.Expr: ...

    # Keep specific properties
    @property
    def shape(self) -> Literal["scalar", "list", "unknown"]: ...
    @property
    def kind(self) -> Literal["value", "comparison", "boolean_mask", "unknown"]: ...
    @property
    def date(self) -> DateColumnAccessor: ...
    @property
    def finance(self) -> FinanceColumnAccessor: ...
    @property
    def projection(self) -> ProjectionColumnAccessor: ...
    # Resolved at run time through ``__getattr__`` off the accessor
    # registry, the same way ``projection`` above is. Declared because an
    # unfinished expression reaches the Excel functions exactly as a
    # column does -- ``(af.premium * af.factor).excel.pv(...)`` -- and a
    # stub that named the other three was telling every type checker that
    # one of them was not there.
    @property
    def excel(self) -> ExcelColumnAccessor: ...

# What the API reference documents from this module.
__all__ = ["ExpressionProxy"]
