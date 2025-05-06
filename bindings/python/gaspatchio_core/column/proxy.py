from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, List, Optional

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

    # --- Reverse Operators ---
    def __radd__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr + self._to_expr(), self._parent)

    def __rsub__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr - self._to_expr(), self._parent)

    def __rmul__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr * self._to_expr(), self._parent)

    def __rtruediv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr / self._to_expr(), self._parent)

    def __rfloordiv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr // self._to_expr(), self._parent)

    def __rmod__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr % self._to_expr(), self._parent)

    def __rpow__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr.pow(self._to_expr()), self._parent)

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

    def __getattr__(self, name: str) -> Any:
        """Dynamically instantiate and return registered column accessors."""
        # REVERT: Check registry for nested dict entry
        # registry_entry is expected to be a tuple (AccessorClass, kind)
        registry_entry = _ACCESSOR_REGISTRY.get(name)

        if (
            registry_entry
            and isinstance(registry_entry, tuple)
            and len(registry_entry) == 2
        ):
            AccessorClass, kind = registry_entry
            if kind == "column":
                # Instantiate the accessor, passing the proxy instance
                accessor_instance = AccessorClass(self)
                # Cache the instance on the object itself
                setattr(self, name, accessor_instance)
                return accessor_instance

        # If not a column accessor or not found, raise AttributeError
        # Attempt to proxy to underlying Polars expression methods
        try:
            # Get the Polars expression associated with this proxy
            expr = self._to_expr()
            # Check if the attribute exists on the expression object
            attr = getattr(expr, name)

            # If the attribute is callable (a method), wrap it
            if callable(attr):

                def method_wrapper(*args, **kwargs):
                    # Call the original Polars method
                    result = attr(*args, **kwargs)
                    # If the result is a new Polars expression, wrap it back into an ExpressionProxy
                    if isinstance(result, pl.Expr):
                        return ExpressionProxy(result, self._parent)
                    # Otherwise, return the result directly (e.g., for aggregation results like sum)
                    return result

                return method_wrapper
            else:
                # If it's a property, return it directly
                # This might need adjustment if properties return Expressions
                return attr

        except AttributeError:
            # If the attribute doesn't exist on the Polars expression either, raise the final error
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' and no matching column accessor was found."
            )

    # ADDED: Apply method
    def apply(self, func: Callable, return_dtype=pl.Float64) -> ExpressionProxy:
        """Apply a Python function element-wise to this column.

        Args:
            func: The Python function to apply.
            return_dtype: The expected Polars dtype of the function's return value.
                          Defaults to pl.Float64.

        Returns:
            An ExpressionProxy representing the result of the function application.
        """
        # Delegate to the parent frame's apply_function method
        return self._parent.apply_function(func, self, return_dtype=return_dtype)


class ExpressionProxy:
    """Represents a Polars expression derived from ActuarialFrame operations."""

    # ADDED: Accessor instance caches
    # Use different cache names to avoid potential clashes if nested
    _date_accessor_instance_expr: Optional["DateColumnAccessor"] = None
    _finance_accessor_instance_expr: Optional["FinanceColumnAccessor"] = None

    # Cache for dynamically created accessor instances
    _dynamic_accessor_cache: dict[str, Any]

    def __init__(self, expr: pl.Expr, parent: "ActuarialFrame"):
        if not isinstance(expr, pl.Expr):
            raise TypeError(f"Expected a Polars expression, got {type(expr)}")
        self._expr = expr
        self._parent = parent
        self._dynamic_accessor_cache = {}  # Initialize cache

    def _to_expr(self) -> pl.Expr:
        """Return the underlying Polars expression."""
        return self._expr

    def __repr__(self) -> str:
        # Attempt to get a shorter representation if possible
        try:
            # Use Polars internal repr logic if available and reasonable
            expr_repr = repr(self._expr)
            # Heuristic: keep it short
            if len(expr_repr) < 100:
                return f"ExpressionProxy(expr={expr_repr})"
            else:
                # Fallback for very complex expressions
                return f"ExpressionProxy(expr=[{self._expr.meta.output_name()}])"
        except Exception:
            return f"ExpressionProxy(expr=[{self._expr.meta.output_name()}])"

    # --- Common Methods ---
    def alias(self, name: str) -> "ExpressionProxy":
        """Rename the output of this expression."""
        expr = self._expr.alias(name)
        return ExpressionProxy(expr, self._parent)

    def cast(self, dtype: pl.DataType, strict: bool = True) -> "ExpressionProxy":
        """Cast the underlying expression to a different data type."""
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

    # --- Reverse Operators ---
    def __radd__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr + self._expr, self._parent)

    def __rsub__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr - self._expr, self._parent)

    def __rmul__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr * self._expr, self._parent)

    def __rtruediv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr / self._expr, self._parent)

    def __rfloordiv__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr // self._expr, self._parent)

    def __rmod__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr % self._expr, self._parent)

    def __rpow__(self, other: Any) -> "ExpressionProxy":
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(other_expr.pow(self._expr), self._parent)

    # --- Accessors & Polars Method Proxying ---
    def __dir__(self) -> List[str]:
        """Enhance dir() output for ExpressionProxy."""
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

    def __getattr__(self, name: str) -> Any:
        """Dynamically instantiate registered column accessors or proxy to Polars methods."""
        # Check cache first
        if name in self._dynamic_accessor_cache:
            return self._dynamic_accessor_cache[name]

        # Check registry for accessors
        # registry_entry is expected to be a tuple (AccessorClass, kind)
        registry_entry = _ACCESSOR_REGISTRY.get(name)

        if (
            registry_entry
            and isinstance(registry_entry, tuple)
            and len(registry_entry) == 2
        ):
            AccessorClass, kind = registry_entry
            if kind == "column":
                # Instantiate the accessor, passing the proxy instance
                accessor_instance = AccessorClass(self)
                # Cache the instance
                self._dynamic_accessor_cache[name] = accessor_instance
                return accessor_instance

        # If not a column accessor or not found, attempt to proxy to Polars expression methods
        try:
            attr = getattr(self._expr, name)

            # If the attribute is callable (a method), wrap it
            if callable(attr):

                def method_wrapper(*args, **kwargs):
                    result = attr(*args, **kwargs)
                    # Wrap result if it's an expression
                    if isinstance(result, pl.Expr):
                        return ExpressionProxy(result, self._parent)
                    return result

                return method_wrapper
            else:
                # If it's a property, return it directly.
                # If the property itself returns an Expr, it should ideally be wrapped,
                # but getattr won't know that. Accessor properties handle this.
                return attr

        except AttributeError:
            # Final fallback: raise attribute error
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}' and no matching column accessor was found."
            )
