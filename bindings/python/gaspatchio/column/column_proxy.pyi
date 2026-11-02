# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Callable, Sequence
from typing import Any, ClassVar, Literal

import polars as pl
from polars.type_aliases import PolarsDataType

from gaspatchio._authoring.escape import PolarsNative
from gaspatchio._semantic.ir import OpNode
from gaspatchio.accessors.date import DateColumnAccessor
from gaspatchio.accessors.excel import ExcelColumnAccessor
from gaspatchio.accessors.finance import FinanceColumnAccessor
from gaspatchio.accessors.projection import ProjectionColumnAccessor
from gaspatchio.frame.base import ActuarialFrame

from ._generated_proxy import _GeneratedProxySurface
from .expression_proxy import ExpressionProxy

# What a state column's ``increments`` and ``captures`` hand back: indexed by a
# step's label or a capture point, it answers an expression.
class _RollforwardFieldAccessor:
    def __init__(
        self,
        parent: ActuarialFrame,
        column_name: str,
        kind: Literal["increments", "captures"],
    ) -> None: ...
    def __getitem__(self, key: str) -> ExpressionProxy: ...

class ColumnProxy(_GeneratedProxySurface):
    # Keep specific attributes
    name: str
    _parent: ActuarialFrame | None
    _date_accessor_instance_col: DateColumnAccessor | None
    _excel_accessor_instance_col: ExcelColumnAccessor | None
    _finance_accessor_instance_col: FinanceColumnAccessor | None
    _projection_accessor_instance_col: ProjectionColumnAccessor | None
    _dynamic_accessor_cache: dict[str, Any]
    _shape_cached: Any
    _node_cached: OpNode | None

    kind: ClassVar[Literal["value"]]

    # Keep specific methods
    def __init__(self, name: str, parent: ActuarialFrame | None) -> None: ...
    def _to_expr(self) -> pl.Expr: ...

    # This column as an op-tree node -- built on first use, hence a property.
    @property
    def _node(self) -> OpNode: ...
    # The explicit way out of the vocabulary: one Polars expression
    # method, reached by name, minting an ``EngineNative`` node that
    # says so.
    def polars_native(self, *, deps: Sequence[str] | None = ...) -> PolarsNative: ...
    # A tracked rollforward's movements and captured balances, read through
    # the state column a compilation produced.
    @property
    def increments(self) -> _RollforwardFieldAccessor: ...
    @property
    def captures(self) -> _RollforwardFieldAccessor: ...
    # The two Python-callback methods the class really defines. They differ
    # in what the callback is handed: `map_elements` calls it once per value,
    # `map_batches` calls it once with the whole column as a `pl.Series` --
    # which is why the element-wise one is the slow one to reach for last.
    def map_elements(
        self, func: Callable[[Any], Any], return_dtype: PolarsDataType | None = None
    ) -> ExpressionProxy: ...
    def map_batches(
        self,
        func: Callable[[pl.Series], Any],
        return_dtype: PolarsDataType | None = None,
    ) -> ExpressionProxy: ...

    # Keep specific properties
    @property
    def shape(self) -> Literal["scalar", "list", "unknown"]: ...
    @property
    def date(self) -> DateColumnAccessor: ...
    @property
    def finance(self) -> FinanceColumnAccessor: ...
    @property
    def excel(self) -> ExcelColumnAccessor: ...
    @property
    def projection(self) -> ProjectionColumnAccessor: ...

# What the API reference documents from this module.
__all__ = ["ColumnProxy"]
