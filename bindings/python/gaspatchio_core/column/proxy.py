from __future__ import annotations

from typing import TYPE_CHECKING, Any, List, Optional

import polars as pl

# ADDED: Import registry
from ..frame.registry import _ACCESSOR_REGISTRY

# Import specific accessor types only when type checking or within methods
if TYPE_CHECKING:
    # Import accessor types for type hinting properties
    # Use forward references
    from ..accessors.date import DateColumnAccessor
    from ..accessors.finance import FinanceColumnAccessor
    from ..frame.base import ActuarialFrame


# Helper to prevent direct instantiation and guide users
def _proxy_error():
    raise TypeError(
        "Cannot directly instantiate Proxy classes. Use DataFrame indexing (df['col']) "
        "or ActuarialFrame methods (df.floor('col')).",
    )


class ColumnProxy:
    """Represents a column within an ActuarialFrame."""

    # ADDED: Accessor instance caches
    _date_accessor_instance: Optional["DateColumnAccessor"] = None
    _finance_accessor_instance: Optional["FinanceColumnAccessor"] = None

    def __init__(self, name: str, parent: "ActuarialFrame"):
        self.name = name
        self._parent = parent

    # Prevent direct instantiation
    def __new__(cls, *args, **kwargs):
        if cls is ColumnProxy:
            _proxy_error()
        return super().__new__(cls)

    def _to_expr(self) -> pl.Expr:
        """Convert this proxy to a Polars expression."""
        return pl.col(self.name)

    def __repr__(self) -> str:
        return f"ColumnProxy(name='{self.name}')"

    # --- Common Methods ---
    def alias(self, name: str) -> "ExpressionProxy":
        """Rename the output of this expression."""
        expr = self._to_expr().alias(name)
        return ExpressionProxy(expr, self._parent)

    def cast(self, dtype: pl.DataType, strict: bool = True) -> "ExpressionProxy":
        """Cast the underlying expression to a different data type."""
        expr = self._to_expr().cast(dtype, strict=strict)
        return ExpressionProxy(expr, self._parent)

    # --- Operators ---
    # Define operators to return ExpressionProxy
    def __add__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() + other_expr, self._parent)

    def __sub__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() - other_expr, self._parent)

    def __mul__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() * other_expr, self._parent)

    def __truediv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() / other_expr, self._parent)

    def __floordiv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() // other_expr, self._parent)

    def __mod__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() % other_expr, self._parent)

    def __pow__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr().pow(other_expr), self._parent)

    # Comparison operators
    def __eq__(self, other: Any) -> "ExpressionProxy":  # type: ignore[override]
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() == other_expr, self._parent)

    def __ne__(self, other: Any) -> "ExpressionProxy":  # type: ignore[override]
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() != other_expr, self._parent)

    def __lt__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() < other_expr, self._parent)

    def __le__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() <= other_expr, self._parent)

    def __gt__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() > other_expr, self._parent)

    def __ge__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() >= other_expr, self._parent)

    # --- Accessors (Placeholders for dynamic loading) ---
    # __dir__ will be updated later to include registered accessors
    def __dir__(self) -> List[str]:
        """Enhance dir() output."""
        standard_attrs = list(super().__dir__())
        # Include methods/properties from the Polars Series/Expression API
        # This might need refinement based on which API (Series vs Expr) is more relevant
        pl_attrs = dir(pl.Series) + dir(pl.Expr)
        public_pl_attrs = [attr for attr in pl_attrs if not attr.startswith("_")]

        # Include registered column accessors by checking the nested dict
        accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "column" in kinds
        ]

        return sorted(list(set(standard_attrs + public_pl_attrs + accessor_names)))

    # --- Accessor Properties ---
    # ADDED: Dynamic property for 'date' column accessor
    @property
    def date(self) -> "DateColumnAccessor":
        """Access date-related column operations."""
        if self._date_accessor_instance is None:
            # Look up specifically for 'column' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'date' column accessor registered or kind mismatch."
                )
            # Use the class retrieved from the registry
            self._date_accessor_instance = AccessorClass(self)
        return self._date_accessor_instance

    # ADDED: Dynamic property for 'finance' column accessor
    @property
    def finance(self) -> "FinanceColumnAccessor":
        """Access finance-related column operations."""
        if self._finance_accessor_instance is None:
            # Look up specifically for 'column' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'finance' column accessor registered or kind mismatch."
                )
            # Use the class retrieved from the registry
            self._finance_accessor_instance = AccessorClass(self)
        return self._finance_accessor_instance


class ExpressionProxy:
    """Represents a Polars expression derived from ActuarialFrame operations."""

    # ADDED: Accessor instance caches
    # Use different cache names to avoid potential clashes if nested
    _date_accessor_instance_expr: Optional["DateColumnAccessor"] = None
    _finance_accessor_instance_expr: Optional["FinanceColumnAccessor"] = None

    def __init__(self, expr: pl.Expr, parent: "ActuarialFrame"):
        self._expr = expr
        self._parent = parent

    # Prevent direct instantiation
    def __new__(cls, *args, **kwargs):
        if cls is ExpressionProxy:
            _proxy_error()
        return super().__new__(cls)

    def _to_expr(self) -> pl.Expr:
        """Return the underlying Polars expression."""
        return self._expr

    def __repr__(self) -> str:
        # Attempt to get a shorter representation if possible
        try:
            # Polars internal representation can be verbose, try to simplify
            expr_str = str(self._expr)
            # Heuristic: shorten potentially long list representations
            if len(expr_str) > 100:
                expr_str = expr_str[:97] + "..."
        except Exception:
            expr_str = "..."  # Fallback
        return f"ExpressionProxy(expr={expr_str})"

    # --- Common Methods ---
    def alias(self, name: str) -> "ExpressionProxy":
        """Rename the output of this expression."""
        expr = self._expr.alias(name)
        return ExpressionProxy(expr, self._parent)

    def cast(self, dtype: pl.DataType, strict: bool = True) -> "ExpressionProxy":
        """Cast the expression to a different data type."""
        expr = self._expr.cast(dtype, strict=strict)
        return ExpressionProxy(expr, self._parent)

    # --- Operators ---
    # Define operators to combine expressions
    def __add__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr + other_expr, self._parent)

    def __sub__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr - other_expr, self._parent)

    def __mul__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr * other_expr, self._parent)

    def __truediv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr / other_expr, self._parent)

    def __floordiv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr // other_expr, self._parent)

    def __mod__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr % other_expr, self._parent)

    def __pow__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr.pow(other_expr), self._parent)

    # Comparison operators
    def __eq__(self, other: Any) -> "ExpressionProxy":  # type: ignore[override]
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr == other_expr, self._parent)

    def __ne__(self, other: Any) -> "ExpressionProxy":  # type: ignore[override]
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr != other_expr, self._parent)

    def __lt__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr < other_expr, self._parent)

    def __le__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr <= other_expr, self._parent)

    def __gt__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr > other_expr, self._parent)

    def __ge__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._expr >= other_expr, self._parent)

    # --- Accessors (Placeholders for dynamic loading) ---
    # __dir__ will be updated later to include registered accessors
    def __dir__(self) -> List[str]:
        """Enhance dir() output."""
        standard_attrs = list(super().__dir__())
        # Include methods/properties from the Polars Expression API
        pl_attrs = dir(pl.Expr)
        public_pl_attrs = [attr for attr in pl_attrs if not attr.startswith("_")]

        # Include registered column accessors by checking the nested dict
        accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "column" in kinds
        ]

        return sorted(list(set(standard_attrs + public_pl_attrs + accessor_names)))

    # --- Accessor Properties ---
    # ADDED: Dynamic property for 'date' column accessor
    @property
    def date(self) -> "DateColumnAccessor":
        """Access date-related expression operations."""
        # Note: This uses the same DateColumnAccessor but operates on an Expression
        if self._date_accessor_instance_expr is None:
            # Look up specifically for 'column' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'date' column accessor registered or kind mismatch."
                )
            # Use the class retrieved from the registry
            self._date_accessor_instance_expr = AccessorClass(self)
        return self._date_accessor_instance_expr

    # ADDED: Dynamic property for 'finance' column accessor
    @property
    def finance(self) -> "FinanceColumnAccessor":
        """Access finance-related expression operations."""
        # Note: This uses the same FinanceColumnAccessor but operates on an Expression
        if self._finance_accessor_instance_expr is None:
            # Look up specifically for 'column' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'finance' column accessor registered or kind mismatch."
                )
            # Use the class retrieved from the registry
            self._finance_accessor_instance_expr = AccessorClass(self)
        return self._finance_accessor_instance_expr
