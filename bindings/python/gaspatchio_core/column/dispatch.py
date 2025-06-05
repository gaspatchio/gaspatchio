"""Shared delegation logic for ColumnProxy and ExpressionProxy."""

import functools
from typing import TYPE_CHECKING, Any, Callable, Optional, Set, Type

import polars as pl
import polars.exceptions
from loguru import logger

from .namespaces.dt_proxy import DtNamespaceProxy
from .namespaces.string_proxy import StringNamespaceProxy

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

# Numeric methods that should be applied element-wise on list columns
_NUMERIC_ELEMENTWISE: Set[str] = {
    "clip",
    "clip_min",
    "clip_max",
    "round",  # Also in unary, but can take decimals arg
    "pow",  # Can be binary
    "mod",  # Binary operation
    "add",
    "sub",
    "mul",
    "truediv",
    "floordiv",
    "cast",  # Type casting
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


def _ensure_polars_expr_or_literal(arg: Any) -> Any:
    """Ensure an argument is a Polars expression or a Polars literal if it's a basic type."""
    from .column_proxy import ColumnProxy  # Defer import
    from .expression_proxy import ExpressionProxy  # Defer import

    if isinstance(arg, (ColumnProxy, ExpressionProxy)):
        return _unwrap(arg)
    if isinstance(arg, pl.Expr):
        return arg
    # For basic Python types that Polars might expect as literals (e.g., in `when().then().otherwise()`)
    # or for arguments like `ambiguous` in strptime.
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return arg  # Return as-is if it's some other type (e.g., a Polars DataType like pl.Date)


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

        # MODIFIED: Handle 'dt' namespace specifically for instances
        if self.name == "dt":
            parent_af = getattr(instance, "_parent", None)
            return DtNamespaceProxy(parent_proxy=instance, parent_af=parent_af)
        # ADDED: Handle 'str' namespace specifically for instances
        if (
            self.name == "str"
        ):  # Ensure this is checked after 'dt' or handled mutually exclusively if logic demands
            parent_af = getattr(instance, "_parent", None)
            return StringNamespaceProxy(parent_proxy=instance, parent_af=parent_af)

        # Original logic for other attributes on an instance
        # Accessed on an instance (e.g., col_proxy.alias). Pass the instance.
        # The wrapper_logic will then decide whether to return a method caller or a property value.
        return self.wrapper_logic(instance)


# Wrapper Factory
def _make_wrapper(name: str) -> Callable[["ProxyType", ...], Any]:
    """Factory to create the core logic function used by DelegatorDescriptor.

    This is the heart of the proxy delegation system. It creates wrapper functions
    that handle attribute access and method calls on proxy objects, implementing both
    standard Polars behavior and special optimizations like list column handling.

    Examples where this is used:
        - af["mortality_rate"].abs()   # Unary operation
        - af["interest_rate"].round(2) # Method with args
        - af["policy_date"].dt.year()  # Namespace method
        - af["policy_id"].str.contains("XYZ") # String namespace methods
        - af["benefit_amounts"].list.sum() # List column aggregation

    Vector Operation Example:
        When working with columns containing vectors (lists), special handling ensures
        operations apply to each element, not the whole list:

        # Column structure: "projected_cashflows" contains lists of values
        # [
        #   [100.2, -50.5, 75.8],    # First policy's cashflows
        #   [-25.3, 60.4, -10.9],    # Second policy's cashflows
        #   [45.6, -80.7, 30.2]      # Third policy's cashflows
        # ]

        # When applying abs() to this column:
        af["projected_cashflows"].abs()

        # Without list shimming, this would try to take abs() of each list as a whole
        # With list shimming, it correctly applies abs() to each element:
        # [
        #   [100.2, 50.5, 75.8],     # First policy's absolute cashflows
        #   [25.3, 60.4, 10.9],      # Second policy's absolute cashflows
        #   [45.6, 80.7, 30.2]       # Third policy's absolute cashflows
        # ]
    """

    def wrapper(self_proxy: "ProxyType", *args: Any, **kwargs: Any) -> Any:
        """Handle attribute access on proxy objects, either method calls or properties."""
        from .column_proxy import ColumnProxy
        from .expression_proxy import ExpressionProxy

        parent_af = getattr(self_proxy, "_parent", None)
        try:
            if isinstance(self_proxy, ColumnProxy):
                base_expr = pl.col(self_proxy.name)
            elif isinstance(self_proxy, ExpressionProxy):
                base_expr = self_proxy._expr
            else:
                raise TypeError(f"Unsupported proxy type: {type(self_proxy).__name__}")
            polars_attr = getattr(base_expr, name)
        except AttributeError as e:
            proxy_type_name = type(self_proxy).__name__
            raise AttributeError(
                f"Polars object accessed via '{proxy_type_name}' has no attribute '{name}': {e}"
            )
        if callable(polars_attr):

            def _mc(*a: Any, **kw: Any) -> Any:
                return _method_caller(
                    name=name,
                    polars_attr=polars_attr,
                    self_proxy=self_proxy,
                    parent_af=parent_af,
                    base_expr=base_expr,
                    a=a,
                    kw=kw,
                )

            try:
                _mc.__doc__ = getattr(
                    polars_attr, "__doc__", f"Proxied Polars method: {name}"
                )
            except Exception:
                _mc.__doc__ = f"Proxied Polars method: {name} (docstring unavailable)"
            return _mc
        if args or kwargs:
            raise TypeError(
                f"Attribute '{name}' is not callable and cannot accept arguments."
            )

        # MODIFIED: Ensure generic NamespaceProxy is not used for "dt" or "str".
        # These are now handled by their specific proxies via DelegatorDescriptor.__get__ for instances.
        if name in _NAMESPACES and name not in ["dt", "str"]:
            return NamespaceProxy(self_proxy, name)
        # MODIFICATION: Explicitly check for dt and str to prevent them from falling into the 'else' block
        # if they were accessed at the class level (where instance specific proxies aren't made)
        # However, DelegatorDescriptor already handles instance-specific proxies for dt and str.
        # This 'else' handles non-callable attributes and cases where 'name' is 'dt' or 'str'
        # but accessed at class level (instance is None in __get__), or if it's a non-proxied namespace.
        # The DelegatorDescriptor's __get__ should return the wrapper_logic for class-level access,
        # which then comes here. If 'name' is 'dt' or 'str' here, it means it's likely class-level.
        # For class-level access, returning the raw Polars namespace object might be intended.
        elif name in ["dt", "str"]:
            # This case is primarily for class-level access like ColumnProxy.dt or ColumnProxy.str
            # It returns the raw Polars namespace object (e.g., polars.expr.datetime_functions.ExprDTFunctions)
            # This is consistent with how non-proxied namespaces would be handled if they were properties.
            return polars_attr  # Return the raw polars attribute (namespace object)
        else:
            # This handles actual properties (non-callable, non-namespace)
            return _wrap(parent_af, polars_attr)

    wrapper.__name__ = f"proxied_{name}"
    return wrapper


def _unwrap_for_list_eval(arg: Any) -> Any:
    """Unwrap arguments for use within list.eval context.

    Inside list.eval, we can't use named columns like pl.col("name").
    We need to convert column references to pl.element() or literals.
    """
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        # In list.eval context, we can't reference other columns by name
        # This should be a literal value instead
        raise ValueError(
            f"Cannot reference column '{arg.name}' inside list.eval context. Use literal values or pl.element()."
        )
    if isinstance(arg, ExpressionProxy):
        # Complex expressions should also not be used in list.eval directly
        raise ValueError(
            "Cannot use complex expressions inside list.eval context. Use literal values or pl.element()."
        )
    # For basic Python types, convert to literals that work in list.eval
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return arg


def _method_caller(
    *,
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: Any,
    a: tuple,
    kw: dict,
) -> Any:
    """Execute the delegated method with proper list-type handling. (Moved out of wrapper)"""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    # Check if this is a unary numeric op (no args)
    is_unary_numeric_op = name in _NUMERIC_UNARY and not a and not kw
    # Check if this is an element-wise numeric op (may have args)
    is_elementwise_op = name in _NUMERIC_ELEMENTWISE

    should_use_list_shim = False
    if is_unary_numeric_op or is_elementwise_op:
        if isinstance(self_proxy, ColumnProxy) and parent_af:
            try:
                # Use collect_schema() to avoid performance warning
                schema = parent_af._df.collect_schema()
                dtype = schema.get(self_proxy.name)
                should_use_list_shim = isinstance(dtype, pl.List)
            except Exception:
                pass
        elif isinstance(self_proxy, ExpressionProxy):
            # For expressions, we can't easily determine the output type
            # Be more conservative: only try list shimming if the expression string
            # suggests it might involve list operations
            expr_str = str(base_expr)
            # Heuristic: if the expression contains list operations or references list columns
            might_be_list = False
            if "list." in expr_str.lower():
                # Expression contains explicit list operations
                might_be_list = True
            elif parent_af:
                # Check if the expression references any list columns by name
                schema = parent_af._df.collect_schema()
                list_column_names = [
                    name for name, dtype in schema.items() if isinstance(dtype, pl.List)
                ]
                # Check if any list column names appear in the expression
                might_be_list = any(
                    f'col("{col_name}")' in expr_str or f"'{col_name}'" in expr_str
                    for col_name in list_column_names
                )
            should_use_list_shim = might_be_list

    try:
        if should_use_list_shim:
            try:
                # Get the element method
                element_method = getattr(pl.element(), name)
                if is_unary_numeric_op:
                    # For unary ops, call without arguments
                    result = base_expr.list.eval(element_method())
                else:
                    # For element-wise ops with arguments, use special unwrapping for list.eval context
                    try:
                        unwrapped_args = [_unwrap_for_list_eval(arg) for arg in a]
                        unwrapped_kwargs = {
                            k: _unwrap_for_list_eval(v) for k, v in kw.items()
                        }
                        result = base_expr.list.eval(
                            element_method(*unwrapped_args, **unwrapped_kwargs)
                        )
                    except ValueError:
                        # If we can't unwrap for list.eval (e.g., column references), fall back to regular method
                        unwrapped_args = [_unwrap(arg) for arg in a]
                        unwrapped_kwargs = {k: _unwrap(v) for k, v in kw.items()}
                        result = polars_attr(*unwrapped_args, **unwrapped_kwargs)
            except Exception:
                # Fallback to regular method call if list.eval fails
                unwrapped_args = [_unwrap(arg) for arg in a]
                unwrapped_kwargs = {k: _unwrap(v) for k, v in kw.items()}
                result = polars_attr(*unwrapped_args, **unwrapped_kwargs)
        else:
            # Regular method call for non-list columns
            unwrapped_args = [_unwrap(arg) for arg in a]
            unwrapped_kwargs = {k: _unwrap(v) for k, v in kw.items()}
            result = polars_attr(*unwrapped_args, **unwrapped_kwargs)
    except Exception as e:
        raise type(e)(f"Error calling proxied Polars method '{name}': {e}") from e
    return _wrap(parent_af, result)


# Autopatching Function
def _autopatch(proxy_cls: Type["ProxyType"]) -> None:
    """Dynamically add proxied Polars Expr methods/properties/namespaces via descriptors.

    This function is the "magic" that makes the proxy classes behave like Polars expressions.
    It works by:
    1. Finding all methods/properties available on Polars expressions
    2. Adding them to the proxy class using descriptors
    3. Respecting any existing methods already defined on the proxy class
    4. Adding a specialized __dir__ method for proper introspection

    Method Override Mechanism:
    -------------------------
    When there's a name conflict between a custom method in your proxy class and
    a Polars method, your implementation ALWAYS takes precedence. The check
    `hasattr(proxy_cls, attr_name)` ensures that any methods you've defined on your
    proxy class won't be overwritten by the Polars equivalent.

    Example: If you define your own custom `map_elements` method on ColumnProxy,
    and Polars also has a `map_elements` method, your implementation will be used
    when calling `af["column"].map_elements(...)`.

    Args:
        proxy_cls: The proxy class to enhance with Polars methods
    """
    # === STEP 1: Prepare for patching ===
    processed_attrs: Set[str] = set()

    # Get all available attributes from Polars expressions and our defined namespaces
    attrs_to_process = dir(pl.Expr) + list(_NAMESPACES)

    # === STEP 2: Patch each attribute onto the proxy class ===
    for attr_name in set(attrs_to_process):  # Use set to avoid duplicates
        # Determine if attribute is internal (starts with _ but isn't a dunder method)
        is_internal = attr_name.startswith("_") and not (
            attr_name.startswith("__") and attr_name.endswith("__")
        )

        # Skip attributes that:
        # 1. Are internal Polars details (like _expr)
        # 2. Have already been processed
        # 3. Already exist on the proxy class (this is where method overriding happens!)
        #    This is crucial: your custom implementations take precedence over Polars methods
        if is_internal or attr_name in processed_attrs or hasattr(proxy_cls, attr_name):
            # Debug info for apply and map_elements
            if attr_name in ["apply", "map_elements", "map_batches"]:
                logger.trace(
                    f"TRACE: Skipping {attr_name} because: "
                    + (
                        "internal"
                        if is_internal
                        else "already processed"
                        if attr_name in processed_attrs
                        else "exists on proxy class"
                    )
                )
            processed_attrs.add(attr_name)  # Mark as processed even if skipped
            continue

        # Add the attribute to the proxy class using the descriptor
        try:
            # This creates the dynamic delegation mechanism for each Polars method
            # When users call this attribute, the descriptor will handle the delegation
            setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
            processed_attrs.add(attr_name)  # Track successfully added attributes

            # Debug for interesting methods
        except Exception as e:
            # Rare, but good practice to handle exceptions
            print(
                f"Warning: Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}"
            )

    # === STEP 3: Enhance __dir__ for proper introspection ===
    # This ensures that when users call dir() on a proxy object,
    # they see both the original methods and the dynamically added Polars methods

    # Preserve any existing __dir__ implementation, or use object.__dir__ as fallback
    original_dir = getattr(proxy_cls, "__dir__", object.__dir__)

    # Define our enhanced __dir__ method
    def __dir__(self):
        """Return all attributes available on this proxy, including dynamic Polars attributes."""
        # Combine:
        # 1. Original attributes from the class
        # 2. Dynamically added Polars attributes
        # Only include successfully patched attributes (might be overly cautious)
        dynamic_attrs = {attr for attr in processed_attrs if hasattr(proxy_cls, attr)}
        return sorted(list(set(original_dir(self)) | dynamic_attrs))

    # Replace the proxy class's __dir__ method with our enhanced version
    proxy_cls.__dir__ = __dir__
