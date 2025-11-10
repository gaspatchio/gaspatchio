"""Defines the ExpressionProxy class."""
# ruff: noqa: ANN204, ANN401, TID252, E501, ERA001, TRY003, EM102, PLR2004, TRY300, BLE001, D401, N806, EM101, C414

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

# Use TYPE_CHECKING for imports that would cause circular dependencies at runtime
if TYPE_CHECKING:
    from ..accessors.date import DateColumnAccessor
    from ..accessors.finance import FinanceColumnAccessor
    from ..frame.base import ActuarialFrame
    # No forward reference needed for ColumnProxy as it's not directly used in signatures here
    # from .column_proxy import ColumnProxy

# Import the registry for accessor lookup
from ..frame.registry import _ACCESSOR_REGISTRY


class ExpressionProxy:
    """Represents a Polars expression derived from ActuarialFrame operations or ColumnProxy methods."""

    # Cache for accessor instances specific to ExpressionProxy
    _date_accessor_instance_expr: DateColumnAccessor | None = None
    _finance_accessor_instance_expr: FinanceColumnAccessor | None = None
    _dynamic_accessor_cache: dict[str, Any]  # Cache for dynamically created accessors

    def __init__(self, expr: pl.Expr, parent: ActuarialFrame | None):
        """Initialize an ExpressionProxy.

        Args:
            expr: The underlying Polars expression.
            parent: The originating ActuarialFrame, used for context.
                    Can be None if the expression is detached.

        """
        if not isinstance(expr, pl.Expr):
            raise TypeError(
                f"ExpressionProxy must be initialized with a Polars expression, got {type(expr).__name__}"
            )
        self._expr = expr
        self._parent = parent
        self._dynamic_accessor_cache = {}  # Initialize cache per instance
        self._list_broadcast_metadata: dict[str, Any] | None = None  # For conditionals

    def _to_expr(self) -> pl.Expr:
        """Return the underlying Polars expression."""
        return self._expr

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
    # Operators combine with other proxies or compatible types, returning a new ExpressionProxy

    def __add__(self, other: Any) -> ExpressionProxy:
        """Addition operator."""
        # Use the dispatch system to handle list column shimming
        return self.add(other)

    def __sub__(self, other: Any) -> ExpressionProxy:
        """Subtraction operator."""
        # Use the dispatch system to handle list column shimming
        return self.sub(other)

    def __mul__(self, other: Any) -> ExpressionProxy:
        """Multiplication operator."""
        # Use the dispatch system to handle list column shimming
        return self.mul(other)

    def __truediv__(self, other: Any) -> ExpressionProxy:
        """True division operator."""
        # Use the dispatch system to handle list column shimming
        return self.truediv(other)

    def __floordiv__(self, other: Any) -> ExpressionProxy:
        """Floor division operator."""
        # Use the dispatch system to handle list column shimming
        return self.floordiv(other)

    def __mod__(self, other: Any) -> ExpressionProxy:
        """Modulo operator."""
        # Use the dispatch system to handle list column shimming
        return self.mod(other)

    def __pow__(self, other: Any) -> ExpressionProxy:
        """Power operator."""
        # Use the dispatch system to handle list column shimming
        return self.pow(other)

    # Comparison operators
    def __eq__(self, other: object) -> ExpressionProxy:  # type: ignore[override]
        """Equality comparison."""
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        return ExpressionProxy(self._expr == other_expr, self._parent)

    def __ne__(self, other: object) -> ExpressionProxy:  # type: ignore[override]
        """Inequality comparison."""
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        return ExpressionProxy(self._expr != other_expr, self._parent)

    def __lt__(self, other: Any) -> ExpressionProxy:
        """Less than comparison."""
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        return ExpressionProxy(self._expr < other_expr, self._parent)

    def __le__(self, other: Any) -> ExpressionProxy:
        """Less than or equal comparison."""
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        return ExpressionProxy(self._expr <= other_expr, self._parent)

    def __gt__(self, other: Any) -> ExpressionProxy:
        """Greater than comparison."""
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        return ExpressionProxy(self._expr > other_expr, self._parent)

    def __ge__(self, other: Any) -> ExpressionProxy:
        """Greater than or equal comparison."""
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        return ExpressionProxy(self._expr >= other_expr, self._parent)

    # --- Reverse Operators ---
    def __radd__(self, other: Any) -> ExpressionProxy:
        """Reverse addition operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.add(self)

    def __rsub__(self, other: Any) -> ExpressionProxy:
        """Reverse subtraction operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.sub(self)

    def __rmul__(self, other: Any) -> ExpressionProxy:
        """Reverse multiplication operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.mul(self)

    def __rtruediv__(self, other: Any) -> ExpressionProxy:
        """Reverse true division operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.truediv(self)

    def __rfloordiv__(self, other: Any) -> ExpressionProxy:
        """Reverse floor division operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.floordiv(self)

    def __rmod__(self, other: Any) -> ExpressionProxy:
        """Reverse modulo operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.mod(self)

    def __rpow__(self, other: Any) -> ExpressionProxy:
        """Reverse power operator."""
        # Convert other to a proxy and use dispatch system
        other_expr = (
            self._parent._convert_to_expr(other) if self._parent else pl.lit(other)
        )
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.pow(self)

    # --- Explicitly Defined Accessor Properties ---
    # Accessors that are commonly used or have specific logic can be defined explicitly.
    # Others will be handled by the autopatcher.

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
    def __getattr__(self, name: str) -> Any:
        """Dynamically instantiate and return registered column accessors."""
        # Check cache first
        # Use object.__getattribute__ to avoid recursion if cache doesn't exist yet
        _cache = object.__getattribute__(self, "_dynamic_accessor_cache")
        if name in _cache:
            return _cache[name]

        # Check registry for column accessors
        AccessorClass = _ACCESSOR_REGISTRY.get(name, {}).get("column")
        if AccessorClass:
            try:
                # Instantiate, passing this ExpressionProxy instance
                accessor_instance = AccessorClass(self)
                # Cache the instance
                # self._dynamic_accessor_cache[name] = accessor_instance # Avoid direct access
                _cache[name] = accessor_instance
                return accessor_instance
            except Exception as e:
                raise AttributeError(
                    f"Error instantiating accessor '{name}': {e}"
                ) from e
        else:
            # If not an accessor, assume it might be a method/property on the
            # underlying Polars expression - this should be handled by autopatch,
            # but raise a specific error if autopatch isn't set up or fails.
            # The autopatch mechanism *should* prevent __getattr__ from being called
            # for proxied methods. If we reach here, something is wrong.
            raise AttributeError(
                f"No '{name}' column accessor registered, and attribute not found on proxied Expr."
            )

    def __dir__(self) -> list[str]:
        """Enhance dir() to include registered column accessors and proxied methods."""
        # Start with standard attributes
        attrs = set(object.__dir__(self))

        # Add registered column accessors
        column_accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "column" in kinds
        ]
        attrs.update(column_accessor_names)

        # Add methods/properties proxied from pl.Expr
        # Similar to ColumnProxy, rely on autopatch or introspection
        # try:
        #     expr_attrs = {m for m in dir(self._expr) if not m.startswith('_')}
        #     attrs.update(expr_attrs)
        # except Exception:
        #     pass

        return sorted(list(attrs))

    # NOTE: Delegation for Polars methods is handled by DelegatorDescriptor via _autopatch.
    #       __getattr__ here is *only* for accessors.
