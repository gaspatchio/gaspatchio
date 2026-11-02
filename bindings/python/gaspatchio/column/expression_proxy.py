# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: ANN204, TID252, E501, ERA001, TRY003, EM102, PLR2004, TRY300, BLE001, N806, EM101
"""Defines the ExpressionProxy class."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import polars as pl

# Use TYPE_CHECKING for imports that would cause circular dependencies at runtime
if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaspatchio._authoring.escape import PolarsNative, ProxyType
    from gaspatchio._semantic.ir import OpNode

    from ..accessors.date import DateColumnAccessor
    from ..accessors.finance import FinanceColumnAccessor
    from ..frame.base import ActuarialFrame
    # No forward reference needed for ColumnProxy as it's not directly used in signatures here
    # from .column_proxy import ColumnProxy

# Import the registry for accessor lookup
from gaspatchio._shape import (
    _UNSET,
    Kind,
    Shape,
    _kind_from_dtype,
    _shape_from_expr_dtype,
)

from ..frame.registry import _ACCESSOR_REGISTRY
from ._declared import _accessor_attribute, _names_with_accessors
from ._generated_proxy import _GeneratedProxySurface


class ExpressionProxy(_GeneratedProxySurface):
    """Represents a Polars expression derived from ActuarialFrame operations or ColumnProxy methods."""

    # Cache for accessor instances specific to ExpressionProxy
    _date_accessor_instance_expr: DateColumnAccessor | None = None
    _finance_accessor_instance_expr: FinanceColumnAccessor | None = None
    _dynamic_accessor_cache: dict[str, Any]  # Cache for dynamically created accessors

    def __init__(
        self,
        expr: pl.Expr,
        parent: ActuarialFrame | None,
        *,
        kind: Kind | None = None,
    ):
        """Initialize an ExpressionProxy around an already-built expression.

        Args:
            expr: The underlying Polars expression.
            parent: The originating ActuarialFrame, used for context.
                    Can be None if the expression is detached.
            kind: Optional explicit kind. When provided, overrides dtype-driven
                    fallback. Used by mask-producing operators (`&`, `|`, `~`)
                    to assert `kind="boolean_mask"` even when the dtype probe
                    can't see through the combined expression.

        """
        if not isinstance(expr, pl.Expr):
            raise TypeError(
                f"ExpressionProxy must be initialized with a Polars expression, got {type(expr).__name__}"
            )
        self._init_fields(node=None, lowered=expr, parent=parent, kind=kind)

    @classmethod
    def _from_node(
        cls,
        node: OpNode,
        parent: ActuarialFrame | None,
        *,
        kind: Kind | None = None,
    ) -> ExpressionProxy:
        """Build a proxy that carries a semantic node, not a finished expression.

        This is what every operator dunder and the ``when`` chain return now.
        The Polars expression is derived on first contact (see ``_expr``) and
        cached, so a chain of ten operators lowers once, at the end, rather
        than ten times on the way through.
        """
        proxy = object.__new__(cls)
        proxy._init_fields(node=node, lowered=None, parent=parent, kind=kind)  # noqa: SLF001
        return proxy

    def _init_fields(
        self,
        *,
        node: OpNode | None,
        lowered: pl.Expr | None,
        parent: ActuarialFrame | None,
        kind: Kind | None,
    ) -> None:
        """Set the instance state shared by both construction paths."""
        self._node_cached = node
        self._lowered = lowered
        self._parent = parent
        self._dynamic_accessor_cache = {}  # Initialize cache per instance
        self._kind_explicit: Kind | None = kind
        self._shape_cached: tuple[int, Shape] | object = _UNSET
        self._kind_cached: tuple[int, Kind] | object = _UNSET

    @property
    def _node(self) -> OpNode:
        """The semantic node this expression stands for.

        A proxy built from a raw Polars expression has no semantic tree to
        offer, so it reports an ``EngineNative`` node -- an honest "something
        else built this" rather than a guess at what it means. Built lazily:
        only an expression that becomes an operand ever needs one.
        """
        node = self._node_cached
        if node is None:
            from gaspatchio.frame.lowering.ingress import native_node  # noqa: PLC0415

            lowered = self._lowered
            if lowered is None:  # pragma: no cover - one of the two is always set
                msg = "ExpressionProxy carries neither a node nor an expression"
                raise RuntimeError(msg)
            node = native_node(lowered)
            self._node_cached = node
        return node

    @property
    def _expr(self) -> pl.Expr:
        """The Polars expression, derived from the node on first contact.

        Lowering happens once per proxy and is cached: the chain
        ``af.premiums - af.claims - af.expenses`` builds three nodes and
        lowers exactly one tree, at the moment something asks for the
        expression.
        """
        lowered = self._lowered
        if lowered is None:
            from gaspatchio.frame.lowering.context import context_for  # noqa: PLC0415
            from gaspatchio.frame.lowering.polars import lower_polars  # noqa: PLC0415

            lowered = lower_polars(self._node, context_for(self._parent))
            self._lowered = lowered
        return lowered

    def _to_expr(self) -> pl.Expr:
        """Return the underlying Polars expression."""
        return self._expr

    @property
    def shape(self) -> Shape:
        """Resolved shape of this expression."""
        gen = getattr(self._parent, "_schema_generation", 0) if self._parent else 0
        if self._shape_cached is _UNSET or self._shape_cached[0] != gen:  # type: ignore[index]
            self._shape_cached = (gen, _shape_from_expr_dtype(self._parent, self._expr))
        return self._shape_cached[1]  # type: ignore[index]

    @property
    def kind(self) -> Kind:
        """Resolved kind: explicit override > dtype-driven fallback > value."""
        if self._kind_explicit is not None:
            return self._kind_explicit
        gen = getattr(self._parent, "_schema_generation", 0) if self._parent else 0
        if self._kind_cached is _UNSET or self._kind_cached[0] != gen:  # type: ignore[index]
            self._kind_cached = (gen, _kind_from_dtype(self._expr, self._parent))
        return self._kind_cached[1]  # type: ignore[index]

    def __repr__(self) -> str:
        """Provide a concise representation of the proxied expression."""
        try:
            # Attempt to get a meaningful name or representation
            expr_repr = repr(self._expr)
            # Use a simple heuristic to avoid excessively long reprs
            if len(expr_repr) < 100:
                return f"ExpressionProxy(expr={expr_repr})"
            # Fallback for complex expressions
            output_name = self._expr.meta.output_name()
            return f"ExpressionProxy(expr=[{output_name}])"
        except Exception:
            # Broad catch just in case repr or meta fails
            return "ExpressionProxy(expr=[unknown])"

    # --- Operator Overloads ---
    # Every operator emits a semantic BinOp node; the Polars expression that
    # computes it is derived later, by lowering (see _authoring/emit.py).

    # Comparison operators

    # --- Reverse Operators ---
    # The other operand is the receiver the author wrote first, so it becomes
    # the node's left child: `1 - af.pols_if` emits BinOp("sub", Lit(1), ...).

    def polars_native(self, *, deps: Sequence[str] | None = None) -> PolarsNative:
        """Continue this expression with a Polars method no operation names.

        The counterpart of ``ColumnProxy.polars_native`` on a formula that is
        already under way: everything written so far keeps the record it
        earned, and the escape applies from this point on. See that method
        for what the escape is for, what it costs, and what it refuses.

        Parameters
        ----------
        deps : Sequence[str], optional
            The columns the resulting expression reads -- every column the
            expression so far reads, plus any the method adds. Needed only
            where the expression will not report them itself, and checked
            against what it does report where it will.

        Returns
        -------
        PolarsNative
            The open escape, on which one Polars expression method is called.

        Examples
        --------
        A high-water mark over the account values of a book, taken after the
        charges have already been netted off in the framework's own
        operations:

        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> af = ActuarialFrame(
        ...     pl.DataFrame(
        ...         {"account_value": [100.0, 120.0, 90.0], "charge": [1.0, 2.0, 3.0]}
        ...     )
        ... )
        >>> net = af.account_value - af.charge
        >>> af.high_water = net.polars_native().cum_max()
        >>> af.collect()["high_water"].to_list()
        [99.0, 118.0, 118.0]

        Both columns the line reads stay declared, the one the escape was
        opened on and the one the expression before it brought:

        >>> af.graph.precedents("high_water")
        ('account_value', 'charge')

        """
        from gaspatchio._authoring.escape import PolarsNative  # noqa: PLC0415

        # The escape's receiver type names ExpressionProxy as this module's
        # stub declares it, and pyright, checking this file, holds the class
        # defined here to be another one. They are one class at run time.
        return PolarsNative(cast("ProxyType", self), deps)

    # --- Explicitly Defined Accessor Properties ---
    # Accessors that are commonly used or have specific logic can be defined explicitly.
    # Other registered accessors are resolved by __getattr__.

    @property
    def date(self) -> DateColumnAccessor:
        """Access date-related expression operations."""
        if "date" not in self._dynamic_accessor_cache:
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'date' column accessor registered or kind mismatch."
                )
            # Pass `self` (the ExpressionProxy instance) to the accessor
            self._dynamic_accessor_cache["date"] = AccessorClass(self)
        return self._dynamic_accessor_cache["date"]

    @property
    def finance(self) -> FinanceColumnAccessor:
        """Access finance-related expression operations."""
        if "finance" not in self._dynamic_accessor_cache:
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'finance' column accessor registered or kind mismatch."
                )
            self._dynamic_accessor_cache["finance"] = AccessorClass(self)
        return self._dynamic_accessor_cache["finance"]

    # --- Dynamic Accessor Handling --- ADDED
    # The registered column accessors, reached as attributes: one definition
    # for a column and an expression alike.
    __getattr__ = _accessor_attribute

    def __dir__(self) -> list[str]:
        """Include registered accessors beside the declared method surface."""
        return _names_with_accessors(self)


# What the API reference documents from this module.
__all__ = ["ExpressionProxy"]
