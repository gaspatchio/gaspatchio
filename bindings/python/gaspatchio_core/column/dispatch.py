"""Shared delegation logic for ColumnProxy and ExpressionProxy.

This module provides the core delegation system that allows proxy objects to
transparently forward method calls and attribute access to underlying Polars
expressions while adding additional functionality like list shimming and
enhanced error handling.
"""

import functools
import re
from typing import TYPE_CHECKING, Any, Callable, Optional, Set, Type

import polars as pl
from loguru import logger

from .namespaces.dt_proxy import DtNamespaceProxy
from .namespaces.string_proxy import StringNamespaceProxy

# Import capture_source_context at module level for testability
try:
    from ..errors.metadata import capture_source_context
except ImportError:
    capture_source_context = None

if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    ProxyType = ColumnProxy | ExpressionProxy


# === CONSTANTS ===

# Operations that are unary (no arguments) and should use list shimming
_NUMERIC_UNARY: Set[str] = {
    # Basic operations
    "abs", "sign",
    # Rounding operations
    "floor", "ceil", "round", "round_sig_figs",
    # Exponential and logarithmic operations
    "exp", "log", "log1p", "ln", "log10",
    # Power and root operations
    "sqrt", "cbrt", "gamma",
    # Numeric checks (return Boolean)
    "is_nan", "is_finite", "is_infinite", "is_not_nan",
    "is_null", "is_not_null",
}

# Operations that may have arguments and should use list shimming
_NUMERIC_ELEMENTWISE: Set[str] = {
    # Clipping operations
    "clip", "clip_min", "clip_max",
    # Arithmetic operations
    "add", "sub", "mul", "truediv", "floordiv", "pow", "mod",
    # Other numeric operations
    "round",  # Can take decimals argument
    "cast",   # Type casting
    "cum_prod", "shift", "fill_null",
}

# All available Polars expression namespaces
_NAMESPACES: Set[str] = {
    "dt",     # Datetime operations
    "str",    # String operations
    "list",   # List operations
    "arr",    # Array operations
    "struct", # Struct operations
    "cat",    # Categorical operations
    "bin",    # Binary operations
}


# === HELPER FUNCTIONS ===

def _unwrap(arg: Any) -> Any:
    """Unwrap ColumnProxy or ExpressionProxy to its underlying Polars equivalent."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr
    return arg


def _wrap(parent: Optional["ActuarialFrame"], result: Any) -> Any:
    """Wrap Polars Expressions into ExpressionProxy."""
    from .expression_proxy import ExpressionProxy

    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
    return result


def _ensure_polars_expr_or_literal(arg: Any) -> Any:
    """Convert argument to Polars expression or literal if needed."""
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return _unwrap(arg) if hasattr(arg, '_expr') or hasattr(arg, 'name') else arg


# === NAMESPACE HANDLING ===

# Define namespace proxies that have specialized implementations
SPECIALIZED_NAMESPACES = {
    "dt": lambda parent_proxy, parent_af: DtNamespaceProxy(parent_proxy, parent_af),
    "str": lambda parent_proxy, parent_af: StringNamespaceProxy(parent_proxy, parent_af),
}


class GenericNamespaceProxy:
    """A generic proxy for Polars expression namespaces (list, arr, struct, etc.)."""

    def __init__(self, parent_proxy: "ProxyType", namespace_name: str):
        self._parent_proxy = parent_proxy
        self._namespace_name = namespace_name
        self._parent_af = getattr(parent_proxy, "_parent", None)
        self._base_expr = _get_proxy_base_expr(parent_proxy)
        self._namespace_obj = self._get_namespace_obj()

    def _get_namespace_obj(self):
        """Get the actual Polars namespace object."""
        try:
            return getattr(self._base_expr, self._namespace_name)
        except AttributeError:
            raise AttributeError(
                f"Base expression has no namespace '{self._namespace_name}'"
            )

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Delegate method calls to the actual Polars namespace object."""
        # Get the method from the actual namespace object
        try:
            actual_method = getattr(self._namespace_obj, name)
        except AttributeError:
            raise AttributeError(
                f"Polars namespace '{self._namespace_name}' has no attribute '{name}'"
            )

        if not callable(actual_method):
            raise TypeError(
                f"Attribute '{name}' on namespace '{self._namespace_name}' is not callable"
            )

        # Return a wrapper function
        @functools.wraps(actual_method)
        def namespace_method_caller(*args: Any, **kwargs: Any) -> Any:
            unwrapped_args = [_unwrap(arg) for arg in args]
            unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

            try:
                result = actual_method(*unwrapped_args, **unwrapped_kwargs)
            except Exception as e:
                raise type(e)(
                    f"Error calling Polars namespace method '{self._namespace_name}.{name}': {e}"
                ) from e

            return _wrap(self._parent_af, result)

        return namespace_method_caller


# === CORE DELEGATION SYSTEM ===

class DelegatorDescriptor:
    """Descriptor that enables transparent delegation to Polars objects.
    
    This descriptor is the core mechanism that allows proxy objects to behave
    like Polars expressions. When an attribute is accessed on a proxy object,
    this descriptor intercepts the access and delegates it to the underlying
    Polars expression, handling all the necessary wrapping and unwrapping.
    
    Attributes:
        name: The name of the attribute being delegated
        wrapper_logic: The function that handles the actual delegation
    """

    def __init__(self, name: str):
        self.name = name
        self.wrapper_logic = _make_wrapper(self.name)

    def __get__(
        self, instance: Optional["ProxyType"], owner: Optional[Type["ProxyType"]] = None
    ) -> Any:
        """Handle attribute access on the proxy instance or class."""
        if instance is None:
            # Accessed on the class itself (e.g., ColumnProxy.alias).
            return self.wrapper_logic

        # Handle namespaces with specialized proxies
        if self.name in SPECIALIZED_NAMESPACES:
            parent_af = getattr(instance, "_parent", None)
            return SPECIALIZED_NAMESPACES[self.name](instance, parent_af)

        # For all other attributes, use the wrapper logic
        return self.wrapper_logic(instance)


def _get_proxy_base_expr(proxy: "ProxyType") -> pl.Expr:
    """Get the base expression from a proxy object."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy
    
    if isinstance(proxy, ColumnProxy):
        return pl.col(proxy.name)
    elif isinstance(proxy, ExpressionProxy):
        return proxy._expr
    else:
        raise TypeError(f"Unsupported proxy type: {type(proxy).__name__}")


def _create_method_wrapper(
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: pl.Expr,
) -> Callable:
    """Create a wrapper for a Polars method."""
    def method_wrapper(*args: Any, **kwargs: Any) -> Any:
        return _method_caller(
            name=name,
            polars_attr=polars_attr,
            self_proxy=self_proxy,
            parent_af=parent_af,
            base_expr=base_expr,
            a=args,
            kw=kwargs,
        )
    
    # Preserve docstring
    try:
        method_wrapper.__doc__ = getattr(
            polars_attr, "__doc__", f"Proxied Polars method: {name}"
        )
    except Exception:
        method_wrapper.__doc__ = f"Proxied Polars method: {name}"
    
    return method_wrapper


# === CORE DELEGATION SYSTEM ===

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
        """Handle attribute access on proxy objects."""
        parent_af = getattr(self_proxy, "_parent", None)
        
        # Get the base expression and Polars attribute
        base_expr = _get_proxy_base_expr(self_proxy)
        try:
            polars_attr = getattr(base_expr, name)
        except AttributeError as e:
            proxy_type_name = type(self_proxy).__name__
            raise AttributeError(
                f"Polars object accessed via '{proxy_type_name}' has no attribute '{name}': {e}"
            )
        
        # Handle callable attributes (methods)
        if callable(polars_attr):
            return _create_method_wrapper(
                name, polars_attr, self_proxy, parent_af, base_expr
            )
        
        # Handle non-callable attributes
        if args or kwargs:
            raise TypeError(
                f"Attribute '{name}' is not callable and cannot accept arguments."
            )

        # Handle generic namespaces
        if name in _NAMESPACES and name not in SPECIALIZED_NAMESPACES:
            return GenericNamespaceProxy(self_proxy, name)
        
        # Return wrapped properties
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


# === LIST SHIMMING DETECTION LOGIC ===

class ColumnTypeDetector:
    """Unified type detection for columns across schema and computation graph."""
    
    def __init__(self, parent_af: Optional["ActuarialFrame"]):
        self.parent_af = parent_af
        self._list_columns_cache = None
    
    def is_list_column(self, column_name: str) -> bool:
        """Check if a column is a list type in either schema or computation graph."""
        if not self.parent_af:
            return False
        
        # Check computation graph first (more recent info)
        if self._is_list_in_graph(column_name):
            return True
        
        # Then check schema
        return self._is_list_in_schema(column_name)
    
    def get_all_list_columns(self) -> list[str]:
        """Get all list columns from both schema and computation graph."""
        if self._list_columns_cache is not None:
            return self._list_columns_cache
        
        if not self.parent_af:
            return []
        
        list_columns = set()
        
        # Add from computation graph
        list_columns.update(self._get_list_columns_from_graph())
        
        # Add from schema
        try:
            schema = self.parent_af._df.collect_schema()
            list_columns.update(
                name for name, dtype in schema.items() 
                if isinstance(dtype, pl.List)
            )
        except Exception:
            pass
        
        self._list_columns_cache = list(list_columns)
        return self._list_columns_cache
    
    def _is_list_in_schema(self, column_name: str) -> bool:
        """Check if a column is a list type in the schema."""
        try:
            schema = self.parent_af._df.collect_schema()
            dtype = schema.get(column_name)
            return isinstance(dtype, pl.List)
        except Exception:
            return False
    
    def _is_list_in_graph(self, column_name: str) -> bool:
        """Check if a column is a list type in the computation graph."""
        if not hasattr(self.parent_af, "_computation_graph"):
            return False
        
        for op in self.parent_af._computation_graph:
            if (hasattr(op, "alias") and op.alias == column_name and
                hasattr(op, "expected_dtype") and 
                isinstance(op.expected_dtype, pl.List)):
                return True
        return False
    
    def _get_list_columns_from_graph(self) -> list[str]:
        """Get list columns from the computation graph."""
        if not hasattr(self.parent_af, "_computation_graph"):
            return []
        
        return [
            op.alias for op in self.parent_af._computation_graph
            if (hasattr(op, "alias") and hasattr(op, "expected_dtype") and 
                isinstance(op.expected_dtype, pl.List))
        ]


def _expr_references_list_column(expr_str: str, list_columns: list[str]) -> bool:
    """Check if an expression references any list columns."""
    for col_name in list_columns:
        # Pattern matches col("name") with optional quotes and whitespace
        col_pattern = rf'\bcol\s*\(\s*["\']?{re.escape(col_name)}["\']?\s*\)'
        if re.search(col_pattern, expr_str):
            logger.trace(f"Expression references list column: {col_name}")
            return True
    return False


def _should_use_list_shim(
    name: str,
    self_proxy: "ProxyType", 
    parent_af: Optional["ActuarialFrame"],
    base_expr: pl.Expr,
) -> bool:
    """Determine if list shimming should be used for the operation."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy
    
    # Only consider list shimming for numeric operations
    if name not in _NUMERIC_UNARY and name not in _NUMERIC_ELEMENTWISE:
        return False
    
    if not parent_af:
        return False
    
    logger.trace(f"Checking list shim for {name}")
    
    # Create a type detector for this operation
    detector = ColumnTypeDetector(parent_af)
    
    # For ColumnProxy, check directly
    if isinstance(self_proxy, ColumnProxy):
        is_list = detector.is_list_column(self_proxy.name)
        if is_list:
            logger.trace(f"Column {self_proxy.name} is list type")
        return is_list
    
    # For ExpressionProxy, use heuristics
    if isinstance(self_proxy, ExpressionProxy):
        expr_str = str(base_expr)
        
        # Quick check: explicit list operations
        if "list." in expr_str.lower():
            logger.trace(f"Expression contains explicit list operations: {expr_str[:100]}...")
            return True
        
        # Get all list columns and check if expression references any
        list_columns = detector.get_all_list_columns()
        logger.trace(f"All list columns: {list_columns}")
        
        references_list = _expr_references_list_column(expr_str, list_columns)
        logger.trace(f"Expression references list columns: {references_list}, expr_str={expr_str[:100]}...")
        return references_list
    
    return False


# === METHOD EXECUTION ===

def _execute_list_shim(
    name: str,
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
    is_unary: bool,
) -> pl.Expr:
    """Execute a method using list.eval for element-wise operations."""
    element_method = getattr(pl.element(), name)
    
    if is_unary:
        return base_expr.list.eval(element_method())
    
    # For operations with arguments, try list.eval context unwrapping
    try:
        unwrapped_args = [_unwrap_for_list_eval(arg) for arg in args]
        unwrapped_kwargs = {
            k: _unwrap_for_list_eval(v) for k, v in kwargs.items()
        }
        return base_expr.list.eval(
            element_method(*unwrapped_args, **unwrapped_kwargs)
        )
    except ValueError:
        # Can't use list.eval context (e.g., column references)
        # This will likely fail but preserves original behavior
        raise


def _execute_regular(polars_attr: Callable, args: tuple, kwargs: dict) -> Any:
    """Execute a regular Polars method."""
    unwrapped_args = [_unwrap(arg) for arg in args]
    unwrapped_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
    return polars_attr(*unwrapped_args, **unwrapped_kwargs)


# === ERROR ENHANCEMENT ===

class ErrorEnhancer:
    """Centralized error handling and enhancement."""
    
    def __init__(self, self_proxy: "ProxyType"):
        self.proxy = self_proxy
        self.parent_af = getattr(self_proxy, '_parent', None)
        self.is_tracing = self.parent_af and self.parent_af._tracing
    
    def enhance_method_error(self, e: Exception, method_name: str, context_depth: int = 3) -> Exception:
        """Enhance an error with proxy context information."""
        error_msg = f"Error calling proxied Polars method '{method_name}': {e}"
        
        # Add source context if tracing is enabled
        if self.is_tracing and capture_source_context is not None:
            try:
                context = capture_source_context(depth=context_depth)
                error_msg += f"\n  Called from: {context.display_filename}:{context.line_number}"
                error_msg += f"\n  Source: {context.source_line}"
            except Exception:
                pass
        
        new_error = type(e)(error_msg)
        # Attach proxy metadata
        new_error.proxy_info = {
            'proxy_type': type(self.proxy).__name__,
            'method': method_name,
            'column': getattr(self.proxy, 'name', None)
        }
        new_error._dispatch_enhanced = True
        return new_error


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
    """Execute the delegated method with proper list-type handling."""
    # Determine if we should use list shimming
    should_use_list_shim = _should_use_list_shim(name, self_proxy, parent_af, base_expr)
    
    # Check if this is a unary operation
    is_unary = name in _NUMERIC_UNARY and not a and not kw
    
    logger.trace(f"Method caller for {name}: list_shim={should_use_list_shim}, unary={is_unary}")
    
    # Create error enhancer for this method call
    error_enhancer = ErrorEnhancer(self_proxy)
    
    try:
        if should_use_list_shim:
            try:
                logger.trace(f"Executing list shim for {name}")
                result = _execute_list_shim(name, base_expr, a, kw, is_unary)
            except Exception as list_error:
                # Fallback to regular execution if list shimming fails
                logger.trace(f"List shim failed for {name}, falling back to regular: {list_error}")
                result = _execute_regular(polars_attr, a, kw)
        else:
            result = _execute_regular(polars_attr, a, kw)
    except Exception as e:
        raise error_enhancer.enhance_method_error(e, name) from e
    
    return _wrap(parent_af, result)


# === AUTOPATCHING ===

def _autopatch(proxy_cls: Type["ProxyType"]) -> None:
    """Dynamically add Polars expression methods to proxy classes.

    This function enhances proxy classes (ColumnProxy, ExpressionProxy) by:
    1. Discovering all available Polars expression methods and properties
    2. Adding them to the proxy class using descriptors for lazy delegation
    3. Preserving any custom methods already defined on the proxy class
    4. Enhancing __dir__ for proper introspection and IDE support

    The key innovation is that proxy class methods take precedence over
    Polars methods, allowing custom implementations to override defaults.

    Args:
        proxy_cls: The proxy class to enhance (ColumnProxy or ExpressionProxy)
    
    Example:
        >>> _autopatch(ColumnProxy)
        # Now ColumnProxy instances can call any Polars expression method:
        # col_proxy.sum(), col_proxy.mean(), col_proxy.dt.year(), etc.
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
            # Debug info for interesting methods
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
