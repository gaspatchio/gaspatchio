# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``pl.Expr`` that cooperates with gaspatchio proxies in either operand order.

``pl.Expr``'s binary operators raise on a ``ColumnProxy``/``ExpressionProxy``
operand instead of returning ``NotImplemented``, so Python never offers the
proxy its reflected method — ``lookup(...) * af.col`` raised while
``af.col * lookup(...)`` worked (gh#67). Frame-independent expressions the
framework hands to users (``Table.lookup``, ``CompiledRollforward.expr_for``,
the ``Schedule.*_expr`` family) are therefore wrapped in this subclass.

When the other operand **is a proxy**, the operation is handed to the proxy's
reflected operator, because the proxy layer owns operator semantics the raw
polars operators lack (list arithmetic shims such as ``**`` on list columns).
The result is then the proxy layer's ``ExpressionProxy`` — the frame-native
currency, with the full accessor surface. When the other operand is anything
else, the operator delegates to polars unchanged and re-wraps, so the property
survives operator chains and ``isinstance(x, pl.Expr)`` stays true.

The guarantee covers **operator** chains only. Every ``pl.Expr`` *method*
(``.clip()``, ``.fill_null()``, ``.alias()``, …) is inherited unchanged and
returns a plain ``pl.Expr`` — after which a proxy operand raises again.
Closing that hole would mean intercepting every Expr-returning attribute,
which is more magic than the interop is worth. The supported idiom for method
chains is to assign to a frame column first (``af.rate = table.lookup(...)``)
and continue from the column proxy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import polars as pl

if TYPE_CHECKING:
    from gaspatchio.column.expression_proxy import ExpressionProxy

# A binary op with a proxy operand is handed to the proxy's method for the
# mirrored operand order: ``self OP other`` == ``other REFLECTED_OP self``.
_REFLECTED = {
    "__add__": "__radd__",
    "__radd__": "__add__",
    "__sub__": "__rsub__",
    "__rsub__": "__sub__",
    "__mul__": "__rmul__",
    "__rmul__": "__mul__",
    "__truediv__": "__rtruediv__",
    "__rtruediv__": "__truediv__",
    "__floordiv__": "__rfloordiv__",
    "__rfloordiv__": "__floordiv__",
    "__mod__": "__rmod__",
    "__rmod__": "__mod__",
    "__pow__": "__rpow__",
    "__rpow__": "__pow__",
    "__and__": "__rand__",
    "__rand__": "__and__",
    "__or__": "__ror__",
    "__ror__": "__or__",
    "__xor__": "__rxor__",
    "__rxor__": "__xor__",
    "__eq__": "__eq__",
    "__ne__": "__ne__",
    "__lt__": "__gt__",
    "__gt__": "__lt__",
    "__le__": "__ge__",
    "__ge__": "__le__",
}


class ProxyAwareExpr(pl.Expr):
    """``pl.Expr`` whose operators accept proxies on either side."""

    @classmethod
    def wrap(cls, expr: pl.Expr) -> ProxyAwareExpr:
        """Rebuild ``expr`` as a ``ProxyAwareExpr`` (shares the same plan)."""
        return cast("ProxyAwareExpr", cls._from_pyexpr(expr._pyexpr))  # noqa: SLF001

    def _binary(self, op: str, other: object) -> ProxyAwareExpr | ExpressionProxy:
        if hasattr(other, "_to_expr"):
            reflected = getattr(other, _REFLECTED[op], None)
            if reflected is not None:
                # The proxy layer owns operator semantics polars lacks
                # (list-column shims); hand it the whole operation.
                return cast("ExpressionProxy", reflected(self))
            other = other._to_expr()  # noqa: SLF001
        return ProxyAwareExpr.wrap(getattr(super(), op)(other))

    # -- arithmetic -------------------------------------------------------
    def __add__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__add__``."""
        return self._binary("__add__", other)

    def __radd__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__radd__``."""
        return self._binary("__radd__", other)

    def __sub__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__sub__``."""
        return self._binary("__sub__", other)

    def __rsub__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rsub__``."""
        return self._binary("__rsub__", other)

    def __mul__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__mul__``."""
        return self._binary("__mul__", other)

    def __rmul__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rmul__``."""
        return self._binary("__rmul__", other)

    def __truediv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__truediv__``."""
        return self._binary("__truediv__", other)

    def __rtruediv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rtruediv__``."""
        return self._binary("__rtruediv__", other)

    def __floordiv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__floordiv__``."""
        return self._binary("__floordiv__", other)

    def __rfloordiv__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rfloordiv__``."""
        return self._binary("__rfloordiv__", other)

    def __mod__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__mod__``."""
        return self._binary("__mod__", other)

    def __rmod__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rmod__``."""
        return self._binary("__rmod__", other)

    def __pow__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__pow__``."""
        return self._binary("__pow__", other)

    def __rpow__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rpow__``."""
        return self._binary("__rpow__", other)

    # -- comparisons ------------------------------------------------------
    def __eq__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__eq__``."""
        return self._binary("__eq__", other)

    def __ne__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__ne__``."""
        return self._binary("__ne__", other)

    def __lt__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__lt__``."""
        return self._binary("__lt__", other)

    def __le__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__le__``."""
        return self._binary("__le__", other)

    def __gt__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__gt__``."""
        return self._binary("__gt__", other)

    def __ge__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__ge__``."""
        return self._binary("__ge__", other)

    __hash__ = pl.Expr.__hash__

    # -- boolean ----------------------------------------------------------
    def __and__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__and__``."""
        return self._binary("__and__", other)

    def __rand__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rand__``."""
        return self._binary("__rand__", other)

    def __or__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__or__``."""
        return self._binary("__or__", other)

    def __ror__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__ror__``."""
        return self._binary("__ror__", other)

    def __xor__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__xor__``."""
        return self._binary("__xor__", other)

    def __rxor__(self, other: object) -> ProxyAwareExpr | ExpressionProxy:  # type: ignore[override]
        """Proxy-aware ``__rxor__``."""
        return self._binary("__rxor__", other)

    # -- unary ------------------------------------------------------------
    def __neg__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__neg__``."""
        return ProxyAwareExpr.wrap(super().__neg__())

    def __pos__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__pos__``."""
        return ProxyAwareExpr.wrap(super().__pos__())

    def __abs__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__abs__``."""
        return ProxyAwareExpr.wrap(super().__abs__())

    def __invert__(self) -> ProxyAwareExpr:
        """Proxy-aware ``__invert__``."""
        return ProxyAwareExpr.wrap(super().__invert__())
