"""Shared delegation logic for ColumnProxy and ExpressionProxy."""

import functools
from typing import TYPE_CHECKING, Any, Callable, Optional, Set, Type

import polars as pl
import polars.exceptions

# Avoid circular imports at runtime but allow type checking
if TYPE_CHECKING:
    # Import proxy types for type hinting within functions/methods
    # Import frame type for context
    from ..frame.base import ActuarialFrame
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    # Define a type alias for proxy types
    ProxyType = ColumnProxy | ExpressionProxy


# Constants
_NUMERIC_UNARY: Set[str] = {
    # Basic
    "abs",
    "sign",
    # Rounding
    "floor",
    "ceil",
    "round",
    "round_sig_figs",
    # Exponents/Logs
    "exp",
    "log",
    "log1p",
    "ln",
    "log10",
    # Power/Roots
    "sqrt",
    "cbrt",
    "gamma",
    # Numeric Checks (return Bool, but unary)
    "is_nan",
    "is_finite",
    "is_infinite",
    "is_not_nan",
    "is_null",
    "is_not_null",
}

_NAMESPACES: Set[str] = {
    "dt",
    "str",
    "list",
    "arr",
    "struct",
    "cat",
    "bin",
}


# Helper Functions
def _unwrap(arg: Any) -> Any:
    """Unwrap ColumnProxy or ExpressionProxy to its underlying Polars equivalent."""
    # Defer import until needed to avoid circular dependency issues at runtime
    # This is slightly redundant with TYPE_CHECKING but ensures it works if called early
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr
    # Consider adding NamespaceProxy handling later if needed
    return arg


def _wrap(parent: Optional["ActuarialFrame"], result: Any) -> Any:
    """Wrap Polars Expressions into ExpressionProxy."""
    from .expression_proxy import ExpressionProxy  # Defer import

    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
    # Potentially wrap other types like Series or namespace objects later if needed
    return result


# --- ADD NamespaceProxy --- START ---
class NamespaceProxy:
    """A proxy for Polars expression namespaces (dt, str, list, etc.)."""

    def __init__(self, parent_proxy: "ProxyType", namespace_name: str):
        self._parent_proxy = parent_proxy
        self._namespace_name = namespace_name
        self._parent_af = getattr(parent_proxy, "_parent", None)

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Delegate method calls to the actual Polars namespace object."""
        # Get the base expression from the parent proxy
        from .column_proxy import ColumnProxy
        from .expression_proxy import ExpressionProxy

        if isinstance(self._parent_proxy, ColumnProxy):
            base_expr = pl.col(self._parent_proxy.name)
        elif isinstance(self._parent_proxy, ExpressionProxy):
            base_expr = self._parent_proxy._expr
        else:
            raise TypeError(
                "NamespaceProxy parent must be ColumnProxy or ExpressionProxy"
            )

        # Get the actual Polars namespace object (e.g., ExprDT, ExprList)
        try:
            actual_namespace_obj = getattr(base_expr, self._namespace_name)
        except AttributeError:
            # Should not happen if NamespaceProxy is created correctly
            raise AttributeError(
                f"Base expression has no namespace '{self._namespace_name}'"
            )

        # Get the method from the actual namespace object
        try:
            actual_method = getattr(actual_namespace_obj, name)
        except AttributeError:
            raise AttributeError(
                f"Polars namespace '{self._namespace_name}' has no attribute '{name}'"
            )

        if not callable(actual_method):
            # If the attribute on the namespace isn't callable, raise error
            # (or handle properties if namespaces have them, unlikely for dt/str/list)
            raise TypeError(
                f"Attribute '{name}' on namespace '{self._namespace_name}' is not callable"
            )

        # Return a wrapper function (similar to method_caller)
        @functools.wraps(actual_method)
        def namespace_method_caller(*args: Any, **kwargs: Any) -> Any:
            # Unwrap arguments
            unwrapped_args = [_unwrap(arg) for arg in args]
            unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

            # Call the actual namespace method
            try:
                result_intermediate = actual_method(*unwrapped_args, **unwrapped_kwargs)
            except Exception as e:
                raise type(e)(
                    f"Error calling Polars namespace method '{self._namespace_name}.{name}': {e}"
                ) from e

            # Wrap and return the result
            return _wrap(self._parent_af, result_intermediate)

        return namespace_method_caller


# --- ADD NamespaceProxy --- END ---


# Descriptor for delegation
class DelegatorDescriptor:
    """Descriptor to dynamically delegate calls to the underlying Polars object."""

    def __init__(self, name: str):
        self.name = name
        # Create the core wrapper function once per attribute name
        self.wrapper_logic = _make_wrapper(self.name)

    def __get__(
        self, instance: Optional["ProxyType"], owner: Optional[Type["ProxyType"]] = None
    ) -> Any:
        """Handle attribute access on the proxy instance or class."""
        if instance is None:
            # Accessed on the class itself (e.g., ColumnProxy.alias). Return the unbound logic.
            # This might be useful for introspection but typically accessed via instance.
            return self.wrapper_logic
        else:
            # Accessed on an instance (e.g., col_proxy.alias). Pass the instance.
            # The wrapper_logic will then decide whether to return a method caller or a property value.
            return self.wrapper_logic(instance)


# Wrapper Factory
def _make_wrapper(name: str) -> Callable[["ProxyType", ...], Any]:
    """Factory to create the core logic function used by DelegatorDescriptor."""

    # This outer function determines if the attribute is callable and returns either
    # the actual method_caller or the direct (wrapped) property/namespace.
    def wrapper(self_proxy: "ProxyType", *args: Any, **kwargs: Any) -> Any:
        # Import proxy types here for isinstance check
        from .column_proxy import ColumnProxy
        from .expression_proxy import ExpressionProxy

        # Determine the base Polars expression and parent frame context
        base_expr: pl.Expr
        parent_af: Optional["ActuarialFrame"] = getattr(self_proxy, "_parent", None)

        try:
            if isinstance(self_proxy, ColumnProxy):
                base_expr = pl.col(self_proxy.name)
            elif isinstance(self_proxy, ExpressionProxy):
                base_expr = self_proxy._expr
            else:
                # This case should ideally not be reached if used correctly
                raise TypeError(
                    f"Delegation wrapper called on unsupported type: {type(self_proxy).__name__}"
                )
        except AttributeError as e:
            raise TypeError(
                f"Failed to get base expression from proxy object: {e}"
            ) from e

        # Get the corresponding attribute from the Polars expression object
        try:
            polars_attr = getattr(base_expr, name)
        except AttributeError:
            proxy_type_name = type(self_proxy).__name__
            base_expr_type_name = type(base_expr).__name__
            raise AttributeError(
                f"Polars object '{base_expr_type_name}' (accessed via '{proxy_type_name}') has no attribute '{name}'"
            )

        # If the Polars attribute is callable (a method or namespace accessor)
        if callable(polars_attr):
            # We return a dedicated function `method_caller` that will handle
            # the actual execution, including list shimming and wrapping.
            @functools.wraps(polars_attr)
            def method_caller(*a: Any, **kw: Any) -> Any:
                # Re-resolve base_expr and parent inside the actual call
                # self_proxy is available via closure
                inner_base_expr: pl.Expr
                inner_parent_af: Optional["ActuarialFrame"] = getattr(
                    self_proxy, "_parent", None
                )

                # Check parent type *before* creating base expr, if possible
                is_list_type: Optional[bool] = (
                    None  # None means unknown/ExpressionProxy
                )
                if isinstance(self_proxy, ColumnProxy) and inner_parent_af:
                    try:
                        schema = inner_parent_af._df.schema
                        dtype = schema.get(self_proxy.name)
                        if dtype:
                            is_list_type = isinstance(dtype, pl.List)
                        else:
                            is_list_type = (
                                True  # Assume might become list, rely on except
                            )
                    except Exception:
                        is_list_type = True  # Assume might become list on error
                elif isinstance(self_proxy, ExpressionProxy):
                    is_list_type = (
                        True  # Assume ExpressionProxy could be list, rely on except
                    )

                try:
                    if isinstance(self_proxy, ColumnProxy):
                        inner_base_expr = pl.col(self_proxy.name)
                    elif isinstance(self_proxy, ExpressionProxy):
                        inner_base_expr = self_proxy._expr
                    else:
                        raise TypeError(
                            f"method_caller on unsupported type: {type(self_proxy).__name__}"
                        )
                except AttributeError as e:
                    raise TypeError(
                        f"method_caller failed to get base expression: {e}"
                    ) from e

                # --- Shim logic with try/except --- START ---
                vectorized = False
                result_intermediate: Any = None
                if is_list_type is True and name in _NUMERIC_UNARY and not a and not kw:
                    try:
                        # Attempt to get the method on pl.element()
                        element_method = getattr(pl.element(), name)
                        if callable(element_method):
                            # Try applying the list.eval shim
                            shimmed_expr = inner_base_expr.list.eval(element_method())
                            result_intermediate = shimmed_expr
                            vectorized = True  # Mark as handled by shim
                    except (
                        AttributeError,  # If .list or pl.element().name fails
                        TypeError,  # If element_method not callable
                        pl.ComputeError,  # Potential eval errors
                        polars.exceptions.InvalidOperationError,  # If .list.eval called on non-list
                    ):
                        vectorized = False
                        result_intermediate = None  # Ensure intermediate is cleared
                # --- Shim logic with try/except --- END ---

                # --- Standard Polars Call --- START ---
                # Only run standard call if not handled by shimming
                if not vectorized:
                    # Get the standard Polars attribute
                    try:
                        polars_attr = getattr(inner_base_expr, name)
                    except AttributeError:
                        # This re-raises the original error if the attribute truly doesn't exist
                        proxy_type_name = type(self_proxy).__name__
                        base_expr_type_name = type(inner_base_expr).__name__
                        raise AttributeError(
                            f"Polars object '{base_expr_type_name}' (accessed via '{proxy_type_name}') has no attribute '{name}'"
                        )

                    # Check again if it's callable *after* potentially shimming
                    if not callable(polars_attr):
                        raise TypeError(
                            f"Attribute '{name}' on Polars object is not callable after potential shimming."
                        )

                    # Unwrap arguments before passing to Polars
                    unwrapped_args = [_unwrap(arg) for arg in a]
                    unwrapped_kwargs = {key: _unwrap(val) for key, val in kw.items()}

                    try:
                        # Call the original Polars method/attribute
                        result_intermediate = polars_attr(
                            *unwrapped_args, **unwrapped_kwargs
                        )
                    except Exception as e:
                        # Improve error context
                        raise type(e)(
                            f"Error calling proxied Polars method '{name}': {e}"
                        ) from e
                # --- Standard Polars Call --- END ---

                # --- Wrap Result --- START ---
                # Wrap the result (either shimmeed or standard) if it's a Polars expression
                wrapped_result = _wrap(inner_parent_af, result_intermediate)
                # --- Wrap Result --- END ---
                return wrapped_result

            # Attempt to add docstring to the caller
            try:
                method_caller.__doc__ = getattr(
                    polars_attr, "__doc__", f"Proxied Polars method: {name}"
                )
            except Exception:
                method_caller.__doc__ = (
                    f"Proxied Polars method: {name} (docstring unavailable)"
                )

            # Return the method_caller closure, ready to be called with user arguments
            return method_caller

        # If the Polars attribute is NOT callable (e.g., a property)
        else:
            # Properties shouldn't be called with arguments
            if args or kwargs:
                raise TypeError(
                    f"Attribute '{name}' is not callable and cannot accept arguments."
                )
            # --- MODIFIED: Check for namespace ---
            if name in _NAMESPACES:
                # Return a NamespaceProxy instead of the raw namespace object
                return NamespaceProxy(self_proxy, name)
            else:
                # Wrap other non-callable properties directly (if they return Expr)
                return _wrap(parent_af, polars_attr)
            # --- END MODIFIED ---

    # Set name for the function returned by the factory (for introspection)
    wrapper.__name__ = f"proxied_{name}"
    return wrapper


# Autopatching Function
def _autopatch(proxy_cls: Type["ProxyType"]) -> None:
    """Dynamically add proxied Polars Expr methods/properties/namespaces via descriptors."""
    processed_attrs: Set[str] = set()

    # Combine attributes from pl.Expr and defined namespaces
    attrs_to_process = dir(pl.Expr) + list(_NAMESPACES)

    for attr_name in set(attrs_to_process):  # Use set to avoid duplicates
        is_internal = attr_name.startswith("_") and not (
            attr_name.startswith("__") and attr_name.endswith("__")
        )

        # Skip internal attributes (like _expr, _parent), already processed, or already defined on the proxy
        if is_internal or attr_name in processed_attrs or hasattr(proxy_cls, attr_name):
            processed_attrs.add(attr_name)  # Mark as processed even if skipped
            continue

        # Use the DelegatorDescriptor to handle the delegation logic
        try:
            setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
            processed_attrs.add(attr_name)
        except Exception as e:
            # Should be rare with descriptors, but good practice
            print(
                f"Warning: Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}"
            )

    # --- Add __dir__ method --- START ---
    # Get the original __dir__ if it exists, otherwise default to object.__dir__
    original_dir = getattr(proxy_cls, "__dir__", object.__dir__)

    # Define the new __dir__ method
    def __dir__(self):
        # Combine original attributes with the dynamically added Polars attributes
        # Filter processed_attrs to only include those successfully set (might be overly cautious)
        dynamic_attrs = {attr for attr in processed_attrs if hasattr(proxy_cls, attr)}
        return sorted(list(set(original_dir(self)) | dynamic_attrs))

    # Assign the new __dir__ method to the proxy class
    proxy_cls.__dir__ = __dir__
    # --- Add __dir__ method --- END ---
