# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A ``pl.Expr`` that cooperates with gaspatchio proxies in either operand order.

``pl.Expr``'s binary operators raise on a ``ColumnProxy``/``ExpressionProxy``
operand instead of returning ``NotImplemented``, so Python never offers the
proxy its reflected method — ``lookup(...) * af.col`` raised while
``af.col * lookup(...)`` worked (gh#67). Frame-independent expressions the
framework hands to users (``Table.lookup`` and friends) are therefore wrapped
in this subclass: every binary operator unwraps a proxy operand to its
underlying expression first, and re-wraps its result so the property survives
operator chains. ``isinstance(x, pl.Expr)`` stays true throughout — this adds
interop, not a new type for callers to know about.
"""

from __future__ import annotations

from typing import cast

import polars as pl


def _unwrap(operand: object) -> object:
    """Return a proxy operand's underlying expression, other operands as-is."""
    to_expr = getattr(operand, "_to_expr", None)
    return to_expr() if callable(to_expr) else operand


class ProxyAwareExpr(pl.Expr):
    """``pl.Expr`` whose operators accept proxies on either side."""

    @classmethod
    def wrap(cls, expr: pl.Expr) -> ProxyAwareExpr:
        """Rebuild ``expr`` as a ``ProxyAwareExpr`` (shares the same plan)."""
        return cast("ProxyAwareExpr", cls._from_pyexpr(expr._pyexpr))  # noqa: SLF001

    def _binary(self, op: str, other: object) -> ProxyAwareExpr:
        result = getattr(super(), op)(_unwrap(other))
        return ProxyAwareExpr.wrap(result)

    # -- arithmetic -------------------------------------------------------
    def __add__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__add__``."""
        return self._binary("__add__", other)

    def __radd__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__radd__``."""
        return self._binary("__radd__", other)

    def __sub__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__sub__``."""
        return self._binary("__sub__", other)

    def __rsub__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rsub__``."""
        return self._binary("__rsub__", other)

    def __mul__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__mul__``."""
        return self._binary("__mul__", other)

    def __rmul__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rmul__``."""
        return self._binary("__rmul__", other)

    def __truediv__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__truediv__``."""
        return self._binary("__truediv__", other)

    def __rtruediv__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rtruediv__``."""
        return self._binary("__rtruediv__", other)

    def __floordiv__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__floordiv__``."""
        return self._binary("__floordiv__", other)

    def __rfloordiv__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rfloordiv__``."""
        return self._binary("__rfloordiv__", other)

    def __mod__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__mod__``."""
        return self._binary("__mod__", other)

    def __rmod__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rmod__``."""
        return self._binary("__rmod__", other)

    def __pow__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__pow__``."""
        return self._binary("__pow__", other)

    def __rpow__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rpow__``."""
        return self._binary("__rpow__", other)

    # -- comparisons ------------------------------------------------------
    def __eq__(self, other: object) -> ProxyAwareExpr:  # type: ignore[override]
        """Proxy-aware ``__eq__``."""
        return self._binary("__eq__", other)

    def __ne__(self, other: object) -> ProxyAwareExpr:  # type: ignore[override]
        """Proxy-aware ``__ne__``."""
        return self._binary("__ne__", other)

    def __lt__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__lt__``."""
        return self._binary("__lt__", other)

    def __le__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__le__``."""
        return self._binary("__le__", other)

    def __gt__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__gt__``."""
        return self._binary("__gt__", other)

    def __ge__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__ge__``."""
        return self._binary("__ge__", other)

    __hash__ = pl.Expr.__hash__

    # -- boolean ----------------------------------------------------------
    def __and__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__and__``."""
        return self._binary("__and__", other)

    def __rand__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__rand__``."""
        return self._binary("__rand__", other)

    def __or__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__or__``."""
        return self._binary("__or__", other)

    def __ror__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__ror__``."""
        return self._binary("__ror__", other)

    def __xor__(self, other: object) -> ProxyAwareExpr:
        """Proxy-aware ``__xor__``."""
        return self._binary("__xor__", other)

    def __rxor__(self, other: object) -> ProxyAwareExpr:
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
