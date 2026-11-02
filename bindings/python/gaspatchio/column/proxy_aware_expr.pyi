# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

from typing import Any

import polars as pl

from gaspatchio._semantic.ir import OpNode
from gaspatchio._shape import Kind
from gaspatchio.column._generated_proxy import _GeneratedProxySurface
from gaspatchio.column.condition_expression import ConditionExpression
from gaspatchio.column.expression_proxy import ExpressionProxy
from gaspatchio.frame.base import ActuarialFrame

# The declared vocabulary comes before ``pl.Expr``: at runtime every name the
# generated surface holds is answered by the bound frame's expression proxy,
# so its typed signature is the one a caller meets. The operators are this
# class's own.
class ProxyAwareExpr(_GeneratedProxySurface, pl.Expr):  # type: ignore[misc]
    _node: OpNode
    _parent: ActuarialFrame | None
    _kind_explicit: Kind | None
    @classmethod
    def wrap(
        cls,
        expr: pl.Expr,
        node: OpNode | None = None,
        parent: object | None = None,
    ) -> ProxyAwareExpr: ...
    @classmethod
    def _from_proxy(cls, proxy: ExpressionProxy) -> ProxyAwareExpr: ...
    def _as_proxy(self) -> ExpressionProxy: ...
    def alias(self, name: str) -> ProxyAwareExpr: ...
    def __getattr__(self, name: str) -> Any: ...  # noqa: ANN401
    def _composed(self, op: str, other: object) -> OpNode | None: ...
    def _answers_as_the_frame(self, op: str) -> bool: ...
    def _operated(self, op: str, other: object) -> ProxyAwareExpr | ExpressionProxy: ...
    def _binary(
        self, op: str, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __add__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __radd__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __sub__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rsub__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __mul__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rmul__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __truediv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rtruediv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __floordiv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rfloordiv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __mod__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rmod__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __pow__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rpow__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __eq__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __ne__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __lt__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __le__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __gt__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __ge__(  # type: ignore[override]
        self, other: object
    ) -> ProxyAwareExpr | ExpressionProxy | ConditionExpression: ...
    def __hash__(self) -> int: ...
    def __and__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rand__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __or__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __ror__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __xor__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def __rxor__(self, other: object) -> ProxyAwareExpr | ExpressionProxy: ...  # type: ignore[override]
    def _unary(self, op: str) -> ProxyAwareExpr: ...
    def __neg__(self) -> ProxyAwareExpr: ...  # type: ignore[override]
    def __pos__(self) -> ProxyAwareExpr: ...
    def __abs__(self) -> ProxyAwareExpr: ...  # type: ignore[override]
    def __invert__(self) -> ProxyAwareExpr: ...  # type: ignore[override]
