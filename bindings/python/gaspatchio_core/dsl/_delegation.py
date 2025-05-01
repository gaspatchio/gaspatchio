import functools
import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Set

import polars as pl
import polars.exceptions

log = logging.getLogger(__name__)

# Import namespace types for isinstance checks

# Avoid circular imports at runtime but allow type checking
if TYPE_CHECKING:
    from gaspatchio_core.dsl.core import ActuarialFrame

_NUMERIC_UNARY: set[str] = {
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
    "log",  # Natural log
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

# Define namespaces explicitly for clarity and control
_NAMESPACES: set[str] = {
    "dt",
    "str",
    "list",
    "arr",
    "struct",
    "cat",
    "bin",
}

# Define reserved names that should NOT be autopatched initially
# These are handled explicitly by properties on the proxy classes
_RESERVED_ACCESSOR_NAMES: Set[str] = {
    "date",
    "finance",
    # Add other custom accessor names that are handled by @property
}


# --- DEFINE DelegatorDescriptor ---
class DelegatorDescriptor:
    """Descriptor to dynamically call the appropriate Polars method/namespace."""

    def __init__(self, name: str):
        self.name = name
        # Create the wrapper function *once* when the descriptor is initialized.
        # This wrapper handles both method calls and namespace access.
        self.wrapper_func = _make_wrapper(self.name)

    def __get__(self, instance, owner):
        """Called when accessing the attribute via an instance or class."""
        if instance is None:
            # Accessed on the class (e.g., ColumnProxy.dt). Return the unbound wrapper function.
            # This allows introspection like help(ColumnProxy.dt)
            return self.wrapper_func
        else:
            # Accessed on an instance (e.g., af['col'].dt).
            # Call the wrapper function with the instance.
            # The wrapper's logic determines what to return (e.g., raw ExprDT namespace or a method caller).
            return self.wrapper_func(instance)


# --- END DelegatorDescriptor ---


def _unwrap(arg: Any) -> Any:
    """Unwrap ColumnProxy or ExpressionProxy to its underlying Polars equivalent."""
    # Defer import until needed to avoid circular dependency
    from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy

    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr
    return arg


def _wrap(parent: Optional["ActuarialFrame"], result: Any) -> Any:
    """Wrap Polars Expressions into ExpressionProxy."""
    from gaspatchio_core.dsl.core import ExpressionProxy

    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
    # Potentially wrap namespace objects later if needed
    return result


def _vectorise_if_list(expr: pl.Expr, op_name: str) -> pl.Expr:
    """Apply unary numeric operations element-wise to list columns using list.eval."""
    # print(f"[Shim] Checking {op_name} on expr: {expr}")
    if op_name not in _NUMERIC_UNARY:
        # print(f"[Shim] {op_name} not in _NUMERIC_UNARY, returning original expr: {expr}")
        return expr

    is_list_type = False
    try:
        # Attempt to get the expression's output type.
        # This might require schema context in some cases, but try with None.
        # Note: This can potentially be expensive.
        output_schema = expr.meta.output_type(None)
        is_list_type = isinstance(output_schema, pl.List)
        # print(f"[Shim] Schema check for {op_name} on {expr}: type={output_schema}, is_list={is_list_type}")
    except (pl.ComputeError, AttributeError):
        # If we can't determine the schema, assume it's not a list to be safe.
        # print(f"[Shim] Schema check failed for {op_name} on {expr} (Error: {schema_err}), assuming not list.")
        is_list_type = False
    except (
        Exception
    ) as general_err:  # Catch other unexpected errors during schema check
        print(
            f"[Shim Warning] Unexpected error during schema check for {op_name} on {expr}: {general_err}. Assuming not list."
        )
        is_list_type = False

    if is_list_type:
        try:
            # print(f"[Shim] Attempting list.eval for list type {op_name}")
            element_method = getattr(pl.element(), op_name)
            if callable(element_method):
                eval_result = expr.list.eval(element_method())
                # print(f"[Shim] list.eval succeeded for {op_name}, returning result: {eval_result}")
                return eval_result
            else:
                # print(f"[Shim] pl.element().{op_name} not callable, skipping list.eval")
                return expr  # Return original if element method not callable
        except (pl.ComputeError, AttributeError, TypeError):
            # This catch block might be less necessary now but kept as a safeguard
            # print(f"[Shim] list.eval failed for {op_name} (Error: {e}), returning original expr: {expr}")
            return expr
    else:
        # print(f"[Shim] Not a list type or schema check failed for {op_name}, returning original expr: {expr}")
        return expr

    # Fallback just in case (shouldn't be reached)
    return expr


def _make_wrapper(name: str) -> Callable:
    """Factory to create the core logic function used by DelegatorDescriptor."""

    def method(self_proxy, *args: Any, **kwargs: Any) -> Any:
        """This function handles the actual delegation when the descriptor is accessed on an instance."""
        from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy

        base_expr: pl.Expr
        parent_af: Optional["ActuarialFrame"] = getattr(self_proxy, "_parent", None)

        # Determine base expression
        try:
            if isinstance(self_proxy, ColumnProxy):
                base_expr = pl.col(self_proxy.name)
            elif isinstance(self_proxy, ExpressionProxy):
                base_expr = self_proxy._expr
            else:
                raise TypeError(
                    f"Wrapper called on incompatible object type: {type(self_proxy).__name__}"
                )
        except AttributeError as e:
            raise TypeError(
                f"Failed to get base expression from proxy object: {e}"
            ) from e

        # Get the Polars attribute
        try:
            polars_attr = getattr(base_expr, name)
            is_top_level = False
        except AttributeError:
            # Check top-level functions as a fallback (e.g., pl.count())
            if hasattr(pl.functions, name):
                polars_attr = getattr(pl.functions, name)
                is_top_level = True
            else:
                proxy_type = type(self_proxy).__name__
                base_type = type(base_expr).__name__
                raise AttributeError(
                    f"Polars object '{base_type}' (accessed via '{proxy_type}') and polars.functions have no attribute '{name}'"
                )

        # Handle the attribute based on whether it's callable (method) or not (namespace/property)
        if callable(polars_attr):
            # Create a specific caller function for this method call
            @functools.wraps(polars_attr)
            def method_caller(*a, **kw):
                # ADDED: Check for unary operation on list type
                # We do this *inside* the caller, when the method is actually invoked
                if name in _NUMERIC_UNARY and not a and not kw:
                    input_dtype = None
                    try:
                        if isinstance(self_proxy, ColumnProxy) and parent_af:
                            # Attempt to get schema from the parent ActuarialFrame's LazyFrame
                            input_dtype = parent_af._df.collect_schema().get(
                                self_proxy.name
                            )
                        elif isinstance(self_proxy, ExpressionProxy) and parent_af:
                            # Attempt to resolve the expression's output type
                            try:
                                input_dtype = base_expr.meta.output_type(
                                    parent_af._df.schema
                                )
                            except Exception:
                                # Schema context might not be sufficient, proceed without list eval
                                pass

                        if isinstance(input_dtype, pl.List):
                            try:
                                element_method = getattr(pl.element(), name)
                                if callable(element_method):
                                    res_intermediate = base_expr.list.eval(
                                        element_method()
                                    )
                                    log.debug(
                                        f"Used list.eval shim for '{name}' on list column."
                                    )
                                    return _wrap(parent_af, res_intermediate)
                            except Exception as eval_err:
                                log.debug(
                                    f"list.eval shim failed for '{name}': {eval_err}. Falling back."
                                )
                                # Fall through to standard call if list.eval fails
                    except Exception as schema_err:
                        log.debug(
                            f"Schema check failed for list.eval shim '{name}': {schema_err}. Falling back."
                        )
                        # Fall through if schema check fails

                # Standard call if not handled by list.eval shim
                unwrapped_args = [_unwrap(arg) for arg in a]
                unwrapped_kwargs = {key: _unwrap(val) for key, val in kw.items()}
                try:
                    # Adjust call for top-level functions
                    if is_top_level:
                        # Prepend base expression for top-level functions
                        call_args = [base_expr] + unwrapped_args
                    else:
                        call_args = unwrapped_args

                    # Call the actual Polars method/function
                    res_intermediate = polars_attr(*call_args, **unwrapped_kwargs)
                except Exception as e:
                    raise type(e)(
                        f"Error calling Polars method/function '{name}' via proxy: {e}"
                    ) from e
                return _wrap(parent_af, res_intermediate)

            # If the descriptor was accessed with arguments, call the method.
            # Otherwise, return the callable method_caller itself.
            if args or kwargs:
                return method_caller(*args, **kwargs)
            else:
                return method_caller
        else:
            # Attribute is not callable (e.g., a namespace like .dt or a property)
            if args or kwargs:  # Namespaces/properties shouldn't be called with args
                raise TypeError(f"Attribute '{name}' is not callable")
            # Return the Polars namespace/property object directly, wrapped if it's an Expr
            return _wrap(parent_af, polars_attr)

    # Set name for the function returned by the factory (for introspection)
    method.__name__ = f"proxied_{name}"
    # Attempt to copy docstring from the Polars object if possible
    try:
        # Prioritize Expr attribute docstring
        polars_doc_attr = getattr(pl.Expr, name, None)
        if polars_doc_attr and hasattr(polars_doc_attr, "__doc__"):
            method.__doc__ = polars_doc_attr.__doc__
        else:
            # Fallback to top-level function docstring
            polars_func_doc = getattr(pl.functions, name, None)
            if polars_func_doc and hasattr(polars_func_doc, "__doc__"):
                method.__doc__ = polars_func_doc.__doc__
    except Exception:
        pass  # Ignore errors setting docstring

    return method


def _autopatch(proxy_cls: type) -> None:
    """Dynamically add proxied Polars Expr methods/properties/namespaces via descriptors."""
    # Import registry access here to ensure it sees registrations
    from .plugins import get_registered_accessors

    # Determine registry kind based on the patched class
    registry_kind = (
        "column"  # Both ColumnProxy and ExpressionProxy use column accessors
    )

    # Get registered accessor names for this kind to avoid patching them
    registered_accessors = get_registered_accessors(registry_kind).keys()

    # Combine standard expression attributes and known namespaces
    attrs_to_process = dir(pl.Expr) + list(_NAMESPACES)

    # Get explicitly defined attributes on the proxy class itself
    proxy_defined_attrs = set(dir(proxy_cls))

    processed_attrs: set[str] = set()  # Track attributes added by autopatch

    for attr_name in set(attrs_to_process):
        is_dunder = attr_name.startswith("__") and attr_name.endswith("__")

        # Skip explicitly reserved names (like .date, .finance handled by @property)
        # AND skip dynamically registered accessors
        if attr_name in _RESERVED_ACCESSOR_NAMES or attr_name in registered_accessors:
            # We still add reserved names to processed_attrs so they appear in dir()
            if attr_name in _RESERVED_ACCESSOR_NAMES:
                processed_attrs.add(attr_name)
            continue

        # Skip private/protected attributes unless they are dunder methods
        if attr_name.startswith("_") and not is_dunder:
            continue

        # Skip if already processed (e.g., handled by a previous condition)
        if attr_name in processed_attrs:
            continue

        # Don't overwrite dunder methods already defined on the proxy class
        if is_dunder and hasattr(proxy_cls, attr_name):
            processed_attrs.add(attr_name)
            continue

        # Don't overwrite attributes explicitly defined on the proxy class (like @property)
        # unless it's a dunder method (handled above)
        if not is_dunder and attr_name in proxy_defined_attrs:
            processed_attrs.add(attr_name)  # Ensure explicit props are in dir
            continue

        try:
            # Use DelegatorDescriptor to handle both methods and namespaces
            setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
            processed_attrs.add(attr_name)
        except Exception as e:
            log.warning(
                f"Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}"
            )

    # Enhance the __dir__ method to include autopatched attributes
    original_dir = getattr(proxy_cls, "__dir__", object.__dir__)

    # Use a static set of processed attributes for the new __dir__
    # This avoids recalculating or relying on potentially changing state
    static_processed_attrs = frozenset(processed_attrs)

    def __dir__(self):
        # Combine original __dir__, attributes defined on the class (like @property),
        # and the attributes dynamically added by autopatch.
        # Use dir(type(self)) to get class-level attributes like @property.
        return sorted(
            list(
                set(original_dir(self)) | set(dir(type(self))) | static_processed_attrs
            )
        )

    proxy_cls.__dir__ = __dir__
