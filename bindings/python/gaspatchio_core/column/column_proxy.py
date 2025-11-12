"""Defines the ColumnProxy class."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import polars as pl

from .expression_proxy import ExpressionProxy  # Runtime import

# Use TYPE_CHECKING for imports that would cause circular dependencies at runtime
if TYPE_CHECKING:
    from ..accessors.date import DateColumnAccessor
    from ..accessors.excel import ExcelColumnAccessor
    from ..accessors.finance import FinanceColumnAccessor
    from ..frame.base import ActuarialFrame
    from .condition_expression import ConditionExpression

# Import the registry for accessor lookup
from ..frame.registry import _ACCESSOR_REGISTRY


class ColumnProxy:
    """Represents a column identifier within an ActuarialFrame, acting as a starting point for expressions."""

    # Cache for accessor instances
    _date_accessor_instance: DateColumnAccessor | None = None
    _excel_accessor_instance: ExcelColumnAccessor | None = None
    _finance_accessor_instance: FinanceColumnAccessor | None = None

    def __init__(self, name: str, parent: ActuarialFrame):
        """Initialize a ColumnProxy.

        Note: Users should not typically instantiate this directly.
        Obtain instances via ActuarialFrame indexing (e.g., `af['column_name']`).
        """
        if not isinstance(name, str) or not name:
            raise ValueError("ColumnProxy name must be a non-empty string.")
        # Avoid holding a direct reference to the parent's LazyFrame/DataFrame if possible,
        # but we need it for context (schema, _convert_to_expr, apply_function).
        # Consider passing only necessary context if this becomes an issue.
        self.name = name
        self._parent = parent  # Reference to the parent ActuarialFrame
        self._dynamic_accessor_cache: dict[str, Any] = {}  # Initialize cache

    def _to_expr(self) -> pl.Expr:
        """Convert this proxy to a base Polars column expression."""
        return pl.col(self.name)

    def __repr__(self) -> str:
        return f"ColumnProxy(name='{self.name}')"

    # --- Operator Overloads ---
    # Operators always produce an ExpressionProxy

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
    def __eq__(self, other: object) -> ConditionExpression:  # type: ignore[override]
        """Equality comparison.

        Returns ConditionExpression with metadata for list_conditional plugin.
        """
        from gaspatchio_core.column.condition_expression import ConditionExpression

        left_expr = self._to_expr()
        right_expr = self._parent._convert_to_expr(other)
        comparison_expr = left_expr == right_expr

        return ConditionExpression(
            expr=comparison_expr,
            parent=self._parent,
            operator="eq",
            left=left_expr,
            right=right_expr,
        )

    def __ne__(self, other: object) -> ExpressionProxy:  # type: ignore[override]
        """Inequality comparison."""
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() != other_expr, self._parent)

    def __lt__(self, other: Any) -> ExpressionProxy:
        """Less than comparison."""
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() < other_expr, self._parent)

    def __le__(self, other: Any) -> ExpressionProxy:
        """Less than or equal comparison."""
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() <= other_expr, self._parent)

    def __gt__(self, other: Any) -> ExpressionProxy:
        """Greater than comparison."""
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() > other_expr, self._parent)

    def __ge__(self, other: Any) -> ExpressionProxy:
        """Greater than or equal comparison."""
        other_expr = self._parent._convert_to_expr(other)
        return ExpressionProxy(self._to_expr() >= other_expr, self._parent)

    # --- Reverse Operators ---
    def __radd__(self, other: Any) -> ExpressionProxy:
        """Reverse addition operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.add(self)

    def __rsub__(self, other: Any) -> ExpressionProxy:
        """Reverse subtraction operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.sub(self)

    def __rmul__(self, other: Any) -> ExpressionProxy:
        """Reverse multiplication operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.mul(self)

    def __rtruediv__(self, other: Any) -> ExpressionProxy:
        """Reverse true division operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.truediv(self)

    def __rfloordiv__(self, other: Any) -> ExpressionProxy:
        """Reverse floor division operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.floordiv(self)

    def __rmod__(self, other: Any) -> ExpressionProxy:
        """Reverse modulo operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.mod(self)

    def __rpow__(self, other: Any) -> ExpressionProxy:
        """Reverse power operator."""
        # Convert other to a proxy and use dispatch system
        from .expression_proxy import ExpressionProxy

        other_expr = self._parent._convert_to_expr(other)
        other_proxy = ExpressionProxy(other_expr, self._parent)
        return other_proxy.pow(self)

    # --- Explicitly Defined Methods/Properties ---
    # These are methods we define directly, not relying on autopatching initially.
    # Common ones like alias and cast could be here or handled by autopatch.

    def map_elements(self, func: Callable, return_dtype=None) -> ExpressionProxy:
        """Apply a Python function to each element of the column.

        Args:
            func: Function to apply to each element
            return_dtype: Optional polars DataType for the result

        Returns:
            ExpressionProxy: Result of applying the function

        """
        # Directly call the (potentially monkey-patched) Polars method.
        # The telemetry wrapper should handle this transparently.
        base_expr = self._to_expr()
        result_expr = base_expr.map_elements(func, return_dtype=return_dtype)
        return ExpressionProxy(result_expr, self._parent)

    def map_batches(self, func: Callable, return_dtype=None) -> ExpressionProxy:
        """Apply a Python function to the entire column as a Series.

        This is more efficient than apply for operations that can process
        multiple values at once, especially for NumPy or vector operations.

        Args:
            func: Function that receives a Series and returns a Series or array
            return_dtype: Optional polars DataType for the result

        Returns:
            ExpressionProxy: Result of applying the function

        """
        # Directly call the (potentially monkey-patched) Polars method.
        base_expr = self._to_expr()
        result_expr = base_expr.map_batches(func, return_dtype=return_dtype)
        return ExpressionProxy(result_expr, self._parent)

    # --- Accessor Properties ---
    # These properties provide access to specialized namespaces (e.g., date, finance).
    # They are explicitly defined here and use the accessor registry.

    @property
    def date(self) -> DateColumnAccessor:
        """Access date-related column operations."""
        if self._date_accessor_instance is None:
            # Look up specifically for 'column' kind using the registry
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'date' column accessor registered or kind mismatch."
                )
            # Instantiate the accessor, passing this ColumnProxy instance
            self._date_accessor_instance = AccessorClass(self)
        return self._date_accessor_instance

    @property
    def finance(self) -> FinanceColumnAccessor:
        """Access finance-related column operations."""
        if self._finance_accessor_instance is None:
            # Look up specifically for 'column' kind using the registry
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'finance' column accessor registered or kind mismatch."
                )
            # Instantiate the accessor, passing this ColumnProxy instance
            self._finance_accessor_instance = AccessorClass(self)
        return self._finance_accessor_instance

    @property
    def excel(self) -> ExcelColumnAccessor:
        """Access excel-related column operations."""
        if self._excel_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("excel", {}).get("column")
            if not AccessorClass:
                raise AttributeError(
                    "No 'excel' column accessor registered or kind mismatch."
                )
            self._excel_accessor_instance = AccessorClass(self)
        return self._excel_accessor_instance

    # --- Dynamic Accessor Handling --- ADDED BACK
    def __getattr__(self, name: str) -> Any:
        """Dynamically instantiate and return registered column accessors."""
        # Check cache first (simple dict cache)
        # Use object.__getattribute__ to avoid recursion if cache doesn't exist yet
        # (Though initializing in __init__ is better)
        _cache = object.__getattribute__(self, "_dynamic_accessor_cache")
        if name in _cache:
            return _cache[name]

        # Check registry for column accessors
        AccessorClass = _ACCESSOR_REGISTRY.get(name, {}).get("column")
        if AccessorClass:
            try:
                # Instantiate the accessor, passing this proxy instance
                accessor_instance = AccessorClass(self)
                # Cache the instance
                # self._dynamic_accessor_cache[name] = accessor_instance # Causes recursion if cache check fails
                _cache[name] = accessor_instance
                return accessor_instance
            except Exception as e:
                # Catch potential instantiation errors
                raise AttributeError(
                    f"Error instantiating accessor '{name}': {e}"
                ) from e
        else:
            # If not in registry, raise standard attribute error
            # The error message should be specific about accessors vs. regular attributes
            raise AttributeError(
                f"No '{name}' column accessor registered or attribute found."
            )

    def __dir__(self) -> list[str]:
        """Enhance dir() to include registered column accessors and proxied methods."""
        # Start with standard attributes
        attrs = set(object.__dir__(self))

        # Add explicitly defined properties/methods if needed (like .date, .finance if they weren't dynamic)
        # attrs.add('date')
        # attrs.add('finance')

        # Add registered column accessors
        column_accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "column" in kinds
        ]
        attrs.update(column_accessor_names)

        # Add methods/properties proxied from pl.Expr via autopatch
        # This requires knowing which methods are patched - use inspect or a predefined list?
        # For simplicity, let's rely on the autopatch mechanism to handle these
        # dynamically if possible, otherwise, list common ones or use introspection
        # on pl.Expr if feasible without performance hit.
        # Example (if autopatch doesn't handle dir):
        # try:
        #     expr_attrs = {m for m in dir(pl.Expr) if not m.startswith('_')}
        #     attrs.update(expr_attrs)
        # except Exception:
        #     pass # Ignore errors inspecting pl.Expr

        return sorted(list(attrs))

    # NOTE: Delegation for Polars methods is now handled by the DelegatorDescriptor
    #       set via _autopatch. __getattr__ here is *only* for accessors.
