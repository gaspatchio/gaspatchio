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
        # Import proxy types for isinstance checks
        from .column_proxy import ColumnProxy
        from .expression_proxy import ExpressionProxy

        # === STEP 1: Setup - get parent context and base expression ===
        parent_af = getattr(self_proxy, "_parent", None)

        try:
            # Create the base polars expression based on proxy type
            if isinstance(self_proxy, ColumnProxy):
                base_expr = pl.col(self_proxy.name)
            elif isinstance(self_proxy, ExpressionProxy):
                base_expr = self_proxy._expr
            else:
                raise TypeError(f"Unsupported proxy type: {type(self_proxy).__name__}")

            # Get the attribute from the Polars expression
            polars_attr = getattr(base_expr, name)
        except AttributeError as e:
            proxy_type_name = type(self_proxy).__name__
            raise AttributeError(
                f"Polars object accessed via '{proxy_type_name}' has no attribute '{name}': {e}"
            )

        # === STEP 2: Handle based on attribute type (method vs property) ===

        # If attribute is a method, create a method caller
        if callable(polars_attr):

            def method_caller(*a: Any, **kw: Any) -> Any:
                """Execute the delegated method with proper list-type handling.

                Examples:
                    - af["premium"].round(2)  # Rounds premiums to 2 decimal places
                    - af["claim_amounts"].abs() # Gets absolute value of claims
                    - af["surrender_values"].sqrt() # Takes square root of surrender values

                Vector Column Example:
                    When af["profit_vectors"] contains lists of values like:
                    [
                      [10.1, -5.2, 8.3],     # Policy 1's profit by year
                      [-3.4, 7.5, -2.6],     # Policy 2's profit by year
                      [4.7, -6.8, 9.9]       # Policy 3's profit by year
                    ]

                    And you call: af["profit_vectors"].abs()

                    The result will be:
                    [
                      [10.1, 5.2, 8.3],      # Absolute values within each list
                      [3.4, 7.5, 2.6],
                      [4.7, 6.8, 9.9]
                    ]

                    Without special list handling, this operation would fail or give
                    incorrect results, as standard Polars operations aren't designed
                    to work element-wise on nested lists.
                """
                # ===== LIST TYPE SHIMMING SECTION =====
                # Why do we need list shimming?
                #   For operations like abs(), round(), sqrt() on columns containing LISTS,
                #   we need to apply the operation to EACH ELEMENT in EACH LIST,
                #   not to the list as a whole.
                #
                #   Example without shimming:
                #     af["cashflow_vectors"].sqrt() would fail because sqrt() can't operate on lists
                #
                #   Example with shimming:
                #     Each number inside each list gets sqrt() applied to it

                # Only applies to unary operations (no arguments) listed in _NUMERIC_UNARY
                is_unary_numeric_op = name in _NUMERIC_UNARY and not a and not kw
                should_use_list_shim = False

                # Check if we're working with a list column
                if is_unary_numeric_op:
                    # Try to determine if column is a list type
                    if isinstance(self_proxy, ColumnProxy) and parent_af:
                        try:
                            dtype = parent_af._df.schema.get(self_proxy.name)
                            should_use_list_shim = isinstance(dtype, pl.List)
                        except Exception:
                            pass  # If schema lookup fails, don't use shim
                    elif isinstance(self_proxy, ExpressionProxy):
                        should_use_list_shim = True  # Try shimming for expressions

                # ===== EXECUTION SECTION =====
                try:
                    # === LIST COLUMN HANDLING PATH ===
                    if should_use_list_shim:
                        try:
                            # The magic: instead of applying the operation directly,
                            # we use list.eval() with pl.element() to apply it to each
                            # element inside each list.
                            #
                            # Example for af["reserve_vectors"].abs():
                            #   1. We get the abs() method via pl.element().abs()
                            #   2. We apply it using list.eval() which executes it on each element
                            element_method = getattr(pl.element(), name)
                            result = base_expr.list.eval(element_method())
                        except Exception:
                            # Fall back to standard execution if list shimming fails
                            unwrapped_args = [_unwrap(arg) for arg in a]
                            unwrapped_kwargs = {k: _unwrap(v) for k, v in kw.items()}
                            result = polars_attr(*unwrapped_args, **unwrapped_kwargs)

                    # === STANDARD COLUMN HANDLING PATH ===
                    else:
                        # Standard method execution for scalar columns
                        # Example: af["lapse_rate"].round(4) - normal scalar operation
                        unwrapped_args = [_unwrap(arg) for arg in a]
                        unwrapped_kwargs = {k: _unwrap(v) for k, v in kw.items()}
                        result = polars_attr(*unwrapped_args, **unwrapped_kwargs)
                except Exception as e:
                    # Provide better error context
                    raise type(e)(
                        f"Error calling proxied Polars method '{name}': {e}"
                    ) from e

                # Wrap the result back into our proxy system
                return _wrap(parent_af, result)

            # Add docstring to help with introspection
            try:
                method_caller.__doc__ = getattr(
                    polars_attr, "__doc__", f"Proxied Polars method: {name}"
                )
            except Exception:
                method_caller.__doc__ = (
                    f"Proxied Polars method: {name} (docstring unavailable)"
                )

            return method_caller

        # === STEP 3: Handle non-callable attributes (properties and namespaces) ===
        # Properties shouldn't be called with arguments
        if args or kwargs:
            raise TypeError(
                f"Attribute '{name}' is not callable and cannot accept arguments."
            )

        # Special handling for namespaces vs regular properties
        # Examples of namespaces:
        #   - af["policy_date"].dt        # Date/time namespace
        #   - af["coverage_code"].str     # String namespace
        #   - af["benefit_amounts"].list  # List namespace
        if name in _NAMESPACES:
            return NamespaceProxy(self_proxy, name)  # Return a namespace proxy
        else:
            return _wrap(parent_af, polars_attr)  # Wrap property value

    # Set name for the wrapper function (helps with debugging)
    wrapper.__name__ = f"proxied_{name}"
    return wrapper


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
            processed_attrs.add(attr_name)  # Mark as processed even if skipped
            continue

        # Add the attribute to the proxy class using the descriptor
        try:
            # This creates the dynamic delegation mechanism for each Polars method
            # When users call this attribute, the descriptor will handle the delegation
            setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
            processed_attrs.add(attr_name)  # Track successfully added attributes
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
