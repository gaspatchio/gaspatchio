# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

import functools
from typing import TYPE_CHECKING, Any, Callable, Optional

import polars as pl
import polars.exceptions

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

# --- ADD NAMESPACE CONSTANT ---
_NAMESPACES: set[str] = {
    "dt",
    "str",
    "list",
    "arr",  # Alias for list, good to include explicitly?
    "struct",
    "cat",
    "bin",
}  # Add others if needed
# --- END NAMESPACE CONSTANT ---


# --- DEFINE DelegatorDescriptor ---
class DelegatorDescriptor:
    """Descriptor to dynamically call the appropriate Polars method/namespace."""

    def __init__(self, name: str):
        self.name = name
        # Create the wrapper function *once* when the descriptor is initialized.
        self.wrapper_func = _make_wrapper(self.name)

    def __get__(self, instance, owner):
        """Called when accessing the attribute via an instance or class."""
        if instance is None:
            # Accessed on the class (e.g., ColumnProxy.dt). Return the unbound wrapper function.
            return self.wrapper_func
        else:
            # Accessed on an instance (e.g., af['col'].dt).
            # Call the wrapper function with the instance.
            # The wrapper's logic determines what to return (e.g., raw ExprDT namespace).
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
    # Add NamespaceProxy to unwrap logic if needed later
    return arg


def _wrap(parent: Optional["ActuarialFrame"], result: Any) -> Any:
    """Wrap Polars Expressions into ExpressionProxy."""
    # Keep imports just in case needed elsewhere
    from gaspatchio_core.dsl.core import ExpressionProxy

    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
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
        # This outer function is now primarily for the descriptor.__get__
        # It needs to return a callable if the underlying Polars attribute is callable.
        from gaspatchio_core.dsl.core import ColumnProxy, ExpressionProxy

        base_expr: pl.Expr
        parent_af: Optional["ActuarialFrame"] = getattr(self_proxy, "_parent", None)

        # --- Determine base expression (needed to check if attr is callable) ---\
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

        # --- Get the Polars attribute to check callability ---\
        try:
            polars_attr = getattr(base_expr, name)
        except AttributeError:
            proxy_type = type(self_proxy).__name__
            base_type = type(base_expr).__name__
            raise AttributeError(
                f"Polars object '{base_type}' (accessed via '{proxy_type}') has no attribute '{name}'"
            )

        # --- Return either the method_caller or the raw attribute ---\
        if callable(polars_attr):
            # print(f"[Wrapper] Attr '{name}' is callable, returning method_caller")
            @functools.wraps(
                polars_attr
            )  # Preserve original method signature/docstring
            def method_caller(
                *a, **kw
            ):  # These are the args passed to the *proxied* method call
                # --- Re-determine base_expr and parent_af inside the caller ---
                # self_proxy is available via closure
                inner_base_expr: pl.Expr
                inner_parent_af: Optional["ActuarialFrame"] = getattr(
                    self_proxy, "_parent", None
                )
                try:
                    if isinstance(self_proxy, ColumnProxy):
                        inner_base_expr = pl.col(self_proxy.name)
                    elif isinstance(self_proxy, ExpressionProxy):
                        inner_base_expr = self_proxy._expr
                    else:
                        # Should not happen if initial check passed
                        raise TypeError(
                            f"method_caller called on incompatible object type: {type(self_proxy).__name__}"
                        )
                except AttributeError as e:
                    raise TypeError(
                        f"method_caller failed to get base expression: {e}"
                    ) from e

                # print(f"[Caller] Calling proxied method '{name}' with args: {a}, kwargs: {kw}")
                res_intermediate: Any = None
                vectorized = False

                # --- Pre-emptive check inside the caller ---
                if name in _NUMERIC_UNARY and not a and not kw:
                    input_dtype = None
                    try:
                        if isinstance(self_proxy, ColumnProxy) and inner_parent_af:
                            input_dtype = inner_parent_af._df.collect_schema().get(
                                self_proxy.name
                            )
                        elif (
                            isinstance(self_proxy, ExpressionProxy) and inner_parent_af
                        ):
                            try:
                                input_dtype = inner_base_expr.meta.output_type(
                                    inner_parent_af._df.schema
                                )
                            except Exception:
                                pass

                        if isinstance(input_dtype, pl.List):
                            element_method = getattr(pl.element(), name)
                            if callable(element_method):
                                res_intermediate = inner_base_expr.list.eval(
                                    element_method()
                                )
                                vectorized = True
                                # print(f"[Caller] Constructed list.eval expr: {res_intermediate}")

                    except Exception as e:
                        print(
                            f"[Caller Warning] Error during pre-emptive vectorization check for {name}: {e}"
                        )
                        vectorized = False
                        res_intermediate = None

                # --- Standard Polars call (if not vectorized) ---
                if not vectorized:
                    unwrapped_args = [_unwrap(arg) for arg in a]
                    unwrapped_kwargs = {key: _unwrap(val) for key, val in kw.items()}
                    try:
                        # Use the polars_attr obtained earlier
                        res_intermediate = polars_attr(
                            *unwrapped_args, **unwrapped_kwargs
                        )
                        # print(f"[Caller] Standard Polars call '{name}' result: {res_intermediate}")
                    except Exception as e:
                        # print(f"[Caller] Error calling Polars method '{name}': {e}")
                        raise type(e)(
                            f"Error calling Polars method '{name}' via proxy: {e}"
                        ) from e

                # --- Wrap result ---
                wrapped_result = _wrap(inner_parent_af, res_intermediate)
                # print(f"[Caller] Wrapping final result for '{name}', wrapped: {wrapped_result}")
                return wrapped_result

            # Attempt to set docstring on the caller function
            try:
                method_caller.__doc__ = getattr(
                    polars_attr, "__doc__", f"Proxied Polars method: {name}"
                )
            except Exception:
                method_caller.__doc__ = (
                    f"Proxied Polars method: {name} (docstring unavailable)"
                )

            return method_caller  # Return the callable wrapper

        else:
            # print(f"[Wrapper] Attr '{name}' is NOT callable, returning raw attr: {polars_attr}")
            # Handle non-callable attributes (properties, namespaces)
            if args or kwargs:  # Properties/namespaces shouldn't be called with args
                raise TypeError(f"Attribute '{name}' is not callable")
            # For namespaces/properties, we might need to wrap them if they return Expr, but handle later.
            # For now, return the raw Polars object (e.g., ExprDT). _wrap handles Expr results.
            return _wrap(parent_af, polars_attr)

    # Set name for the function returned by the factory (for introspection)
    method.__name__ = f"proxied_{name}"
    # Docstring for the descriptor itself might be useful, but set on method_caller for methods
    return method


def _autopatch(proxy_cls: type) -> None:
    """Dynamically add proxied Polars Expr methods/properties/namespaces via descriptors."""
    processed_attrs: set[str] = set()
    attrs_to_process = dir(pl.Expr) + list(_NAMESPACES)

    for attr_name in set(attrs_to_process):
        is_dunder = attr_name.startswith("__") and attr_name.endswith("__")

        if attr_name.startswith("_") and not is_dunder:
            continue
        if attr_name in processed_attrs:
            continue

        if is_dunder and hasattr(proxy_cls, attr_name):
            processed_attrs.add(attr_name)
            continue

        try:
            # --- MODIFIED: Use DelegatorDescriptor ---
            setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
            # --- END MODIFIED ---
            processed_attrs.add(attr_name)
        except Exception as e:
            print(
                f"Warning: Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}"
            )

    # Add __dir__ method
    original_dir = getattr(proxy_cls, "__dir__", object.__dir__)

    def __dir__(self):
        return sorted(list(set(original_dir(self)) | processed_attrs))

    proxy_cls.__dir__ = __dir__
