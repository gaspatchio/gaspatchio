"""Shared delegation logic for ColumnProxy and ExpressionProxy.

This module provides the core delegation system that allows proxy objects to
transparently forward method calls and attribute access to underlying Polars
expressions while adding additional functionality like list shimming and
enhanced error handling.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

import polars as pl
from loguru import logger

from .namespaces.dt_proxy import DtNamespaceProxy
from .namespaces.string_proxy import StringNamespaceProxy

# Import capture_source_context at module level for testability
try:
    from gaspatchio_core.errors.metadata import (
        capture_source_context as _capture_source_context,
    )
except ImportError:
    _capture_source_context = None  # type: ignore[assignment]

# Use a module-level reference for the import
capture_source_context = _capture_source_context

if TYPE_CHECKING:
    from gaspatchio_core.frame.base import ActuarialFrame

    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    ProxyType = ColumnProxy | ExpressionProxy


# === CONSTANTS ===

# Operations that are unary (no arguments) and should use list shimming
_NUMERIC_UNARY: set[str] = {
    # Basic operations
    "abs",
    "sign",
    # Rounding operations
    "floor",
    "ceil",
    "round",
    "round_sig_figs",
    # Exponential and logarithmic operations
    "exp",
    "log",
    "log1p",
    "ln",
    "log10",
    # Power and root operations
    "sqrt",
    "cbrt",
    "gamma",
    # Numeric checks (return Boolean)
    "is_nan",
    "is_finite",
    "is_infinite",
    "is_not_nan",
    "is_null",
    "is_not_null",
}

# Operations that may have arguments and should use list shimming
_NUMERIC_ELEMENTWISE: set[str] = {
    # Clipping operations
    "clip",
    "clip_min",
    "clip_max",
    # Arithmetic operations
    "add",
    "sub",
    "mul",
    "truediv",
    "floordiv",
    "pow",
    "mod",
    # Other numeric operations
    "round",  # Can take decimals argument
    "cast",  # Type casting
    "cum_prod",
    "cum_sum",
    "cum_min",
    "cum_max",
    "diff",
    "shift",
    "fill_null",
    "fill_nan",
    "interpolate",
}

# All available Polars expression namespaces
_NAMESPACES: set[str] = {
    "dt",  # Datetime operations
    "str",  # String operations
    "list",  # List operations
    "arr",  # Array operations
    "struct",  # Struct operations
    "cat",  # Categorical operations
    "bin",  # Binary operations
}


# === HELPER FUNCTIONS ===


def _unwrap(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap ColumnProxy, ExpressionProxy, or ConditionExpression to Polars expr."""
    from .column_proxy import ColumnProxy
    from .condition_expression import ConditionExpression
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        return pl.col(arg.name)
    if isinstance(arg, ExpressionProxy):
        return arg._expr  # noqa: SLF001
    if isinstance(arg, ConditionExpression):
        # Return raw boolean expression for methods like .filter()
        return arg._expr  # noqa: SLF001
    return arg


# Arithmetic operations that should coerce ConditionExpression to boolean (0.0/1.0)
_ARITHMETIC_OPS: set[str] = {"add", "sub", "mul", "truediv", "floordiv", "mod", "pow"}


def _unwrap_for_arithmetic(arg: Any) -> Any:  # noqa: ANN401
    """Unwrap for arithmetic, converting ConditionExpression to boolean float."""
    from .condition_expression import ConditionExpression

    if isinstance(arg, ConditionExpression):
        # For arithmetic ops, convert to boolean float (0.0/1.0)
        # This handles list vs scalar columns properly via list_conditional
        return arg._to_boolean_expr()  # noqa: SLF001
    return _unwrap(arg)


def _wrap(
    parent: Optional["ActuarialFrame"],
    result: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Wrap Polars Expressions into ExpressionProxy."""
    from .expression_proxy import ExpressionProxy

    if isinstance(result, pl.Expr):
        return ExpressionProxy(result, parent)
    return result


def _ensure_polars_expr_or_literal(
    arg: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Convert argument to Polars expression or literal if needed."""
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return _unwrap(arg) if hasattr(arg, "_expr") or hasattr(arg, "name") else arg


# === NAMESPACE HANDLING ===

# Define namespace proxies that have specialized implementations
SPECIALIZED_NAMESPACES = {
    "dt": lambda parent_proxy, parent_af: DtNamespaceProxy(parent_proxy, parent_af),
    "str": lambda parent_proxy, parent_af: StringNamespaceProxy(
        parent_proxy, parent_af
    ),
}


class GenericNamespaceProxy:
    """A generic proxy for Polars expression namespaces (list, arr, struct, etc.)."""

    def __init__(  # noqa: D107
        self, parent_proxy: "ProxyType", namespace_name: str
    ) -> None:
        self._parent_proxy = parent_proxy
        self._namespace_name = namespace_name
        self._parent_af = getattr(parent_proxy, "_parent", None)
        self._base_expr = _get_proxy_base_expr(parent_proxy)
        self._namespace_obj = self._get_namespace_obj()

    def _get_namespace_obj(self) -> Any:  # noqa: ANN401
        """Get the actual Polars namespace object."""
        try:
            return getattr(self._base_expr, self._namespace_name)
        except AttributeError as err:
            msg = f"Base expression has no namespace '{self._namespace_name}'"
            raise AttributeError(msg) from err

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Delegate method calls to the actual Polars namespace object."""
        # Get the method from the actual namespace object
        try:
            actual_method = getattr(self._namespace_obj, name)
        except AttributeError as err:
            msg = f"Polars namespace '{self._namespace_name}' has no attribute '{name}'"
            raise AttributeError(msg) from err

        if not callable(actual_method):
            msg = (
                f"Attribute '{name}' on namespace '{self._namespace_name}' not callable"
            )
            raise TypeError(msg)

        # Return a wrapper function
        @functools.wraps(actual_method)
        def namespace_method_caller(
            *args: Any,  # noqa: ANN401
            **kwargs: Any,  # noqa: ANN401
        ) -> Any:  # noqa: ANN401
            unwrapped_args = [_unwrap(arg) for arg in args]
            unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

            try:
                result = actual_method(*unwrapped_args, **unwrapped_kwargs)
            except Exception as e:
                msg = f"Error in '{self._namespace_name}.{name}': {e}"
                raise type(e)(msg) from e

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

    def __init__(self, name: str) -> None:
        """Initialize the descriptor with the attribute name."""
        self.name = name
        self.wrapper_logic = _make_wrapper(self.name)

    def __get__(
        self, instance: Optional["ProxyType"], owner: type["ProxyType"] | None = None
    ) -> Any:  # noqa: ANN401
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
    if isinstance(proxy, ExpressionProxy):
        return proxy._expr  # noqa: SLF001
    msg = f"Unsupported proxy type: {type(proxy).__name__}"
    raise TypeError(msg)


def _create_method_wrapper(
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: pl.Expr,
) -> Callable:
    """Create a wrapper for a Polars method."""

    def method_wrapper(
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
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
    except AttributeError:
        method_wrapper.__doc__ = f"Proxied Polars method: {name}"

    return method_wrapper


# === CORE DELEGATION SYSTEM ===


def _make_wrapper(
    name: str,
) -> Callable[..., Any]:
    """Create the core logic function used by DelegatorDescriptor.

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

    def wrapper(
        self_proxy: "ProxyType",
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Handle attribute access on proxy objects."""
        parent_af = getattr(self_proxy, "_parent", None)

        # Get the base expression and Polars attribute
        base_expr = _get_proxy_base_expr(self_proxy)
        try:
            polars_attr = getattr(base_expr, name)
        except AttributeError as e:
            proxy_type_name = type(self_proxy).__name__
            msg = f"'{proxy_type_name}' has no attribute '{name}': {e}"
            raise AttributeError(msg) from e

        # Handle callable attributes (methods)
        if callable(polars_attr):
            return _create_method_wrapper(
                name, polars_attr, self_proxy, parent_af, base_expr
            )

        # Handle non-callable attributes
        if args or kwargs:
            msg = f"Attribute '{name}' is not callable and cannot accept arguments."
            raise TypeError(msg)

        # Handle generic namespaces
        if name in _NAMESPACES and name not in SPECIALIZED_NAMESPACES:
            return GenericNamespaceProxy(self_proxy, name)

        # Return wrapped properties
        return _wrap(parent_af, polars_attr)

    wrapper.__name__ = f"proxied_{name}"
    return wrapper


def _unwrap_for_list_eval(
    arg: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Unwrap arguments for use within list.eval context.

    Inside list.eval, we can't use named columns like pl.col("name").
    We need to convert column references to pl.element() or literals.
    """
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    if isinstance(arg, ColumnProxy):
        # In list.eval context, we can't reference other columns by name
        msg = f"Cannot reference column '{arg.name}' inside list.eval context."
        raise TypeError(msg)
    if isinstance(arg, ExpressionProxy):
        # Complex expressions should also not be used in list.eval directly
        msg = "Cannot use complex expressions inside list.eval context."
        raise TypeError(msg)
    if isinstance(arg, pl.Expr):
        # Check if expression contains named column references
        expr_str = str(arg)
        if 'col("' in expr_str:
            msg = "Cannot use expressions with named columns inside list.eval."
            raise TypeError(msg)
    # For basic Python types, convert to literals that work in list.eval
    if isinstance(arg, (str, int, float, bool)):
        return pl.lit(arg)
    return arg


# === LIST SHIMMING DETECTION LOGIC ===


class ColumnTypeDetector:
    """Unified type detection for columns across schema and computation graph."""

    def __init__(self, parent_af: Optional["ActuarialFrame"]) -> None:
        """Initialize the detector with a parent ActuarialFrame."""
        self.parent_af = parent_af
        self._list_columns_cache: list[str] | None = None

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

        list_columns: set[str] = set()

        # Add from computation graph
        list_columns.update(self._get_list_columns_from_graph())

        # Add from schema
        try:
            schema = self.parent_af._df.collect_schema()  # noqa: SLF001
            list_columns.update(
                name for name, dtype in schema.items() if isinstance(dtype, pl.List)
            )
        except (AttributeError, RuntimeError):
            logger.trace("Failed to get schema for list column detection")

        self._list_columns_cache = list(list_columns)
        return self._list_columns_cache

    def _is_list_in_schema(self, column_name: str) -> bool:
        """Check if a column is a list type in the schema."""
        try:
            schema = self.parent_af._df.collect_schema()  # noqa: SLF001
            dtype = schema.get(column_name)
            return isinstance(dtype, pl.List)
        except (AttributeError, RuntimeError):
            return False

    def _is_list_in_graph(self, column_name: str) -> bool:
        """Check if a column is a list type in the computation graph."""
        graph = getattr(self.parent_af, "_computation_graph", None)
        if graph is None:
            return False

        for op in graph:
            if (
                hasattr(op, "alias")
                and op.alias == column_name
                and hasattr(op, "expected_dtype")
                and isinstance(op.expected_dtype, pl.List)
            ):
                return True
        return False

    def is_expression_list_output(self, expr: pl.Expr) -> bool:
        """Check if a Polars expression produces a list output type.

        Uses Polars schema inference to determine the output type of an expression.
        This is useful for ExpressionProxy where we don't have a column name to check.

        Args:
            expr: The Polars expression to check

        Returns:
            True if the expression produces a list type, False otherwise

        """
        if not self.parent_af or self.parent_af._df is None:  # noqa: SLF001
            return False

        try:
            # Use Polars' schema inference by applying the expression
            result_schema = self.parent_af._df.select(  # noqa: SLF001
                expr.alias("_type_check")
            ).collect_schema()
            dtype = result_schema.get("_type_check")
            return isinstance(dtype, pl.List)
        except Exception:  # noqa: BLE001
            # If schema inference fails, fall back to checking if expression
            # references list columns (heuristic)
            expr_str = str(expr)
            list_columns = self.get_all_list_columns()
            return _expr_references_list_column(expr_str, list_columns)

    def _get_list_columns_from_graph(self) -> list[str]:
        """Get list columns from the computation graph."""
        graph = getattr(self.parent_af, "_computation_graph", None)
        if graph is None:
            return []

        return [
            op.alias
            for op in graph
            if (
                hasattr(op, "alias")
                and hasattr(op, "expected_dtype")
                and isinstance(op.expected_dtype, pl.List)
            )
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
            logger.trace(
                f"Expression contains explicit list operations: {expr_str[:100]}..."
            )
            return True

        # Get all list columns and check if expression references any
        list_columns = detector.get_all_list_columns()
        logger.trace(f"All list columns: {list_columns}")

        references_list = _expr_references_list_column(expr_str, list_columns)
        expr_preview = expr_str[:100]
        logger.trace(
            f"Expression references list columns: {references_list}, {expr_preview}"
        )
        return references_list

    return False


# === METHOD EXECUTION ===


def _execute_list_shim(
    name: str,
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
    *,
    is_unary: bool,
) -> pl.Expr:
    """Execute a method using list.eval for element-wise operations."""
    element_method = getattr(pl.element(), name)

    if is_unary:
        return base_expr.list.eval(element_method())

    # For operations with arguments, try list.eval context unwrapping
    unwrapped_args = [_unwrap_for_list_eval(arg) for arg in args]
    unwrapped_kwargs = {k: _unwrap_for_list_eval(v) for k, v in kwargs.items()}
    return base_expr.list.eval(element_method(*unwrapped_args, **unwrapped_kwargs))


def _execute_regular(polars_attr: Callable, args: tuple, kwargs: dict) -> Any:  # noqa: ANN401
    """Execute a regular Polars method."""
    unwrapped_args = [_unwrap(arg) for arg in args]
    unwrapped_kwargs = {k: _unwrap(v) for k, v in kwargs.items()}
    return polars_attr(*unwrapped_args, **unwrapped_kwargs)


# === ERROR ENHANCEMENT ===


class ErrorEnhancer:
    """Centralized error handling and enhancement."""

    def __init__(self, self_proxy: "ProxyType") -> None:
        """Initialize error enhancer with proxy context."""
        self.proxy = self_proxy
        self.parent_af = getattr(self_proxy, "_parent", None)
        tracing = getattr(self.parent_af, "_tracing", False)
        self.is_tracing = bool(self.parent_af and tracing)

    def enhance_method_error(
        self, e: Exception, method_name: str, context_depth: int = 3
    ) -> Exception:
        """Enhance an error with proxy context information."""
        error_msg = f"Error calling proxied Polars method '{method_name}': {e}"

        # Add source context if tracing is enabled
        if self.is_tracing and capture_source_context is not None:
            try:
                context = capture_source_context(depth=context_depth)
                error_msg += (
                    f"\n  Called from: {context.display_filename}:{context.line_number}"
                )
                error_msg += f"\n  Source: {context.source_line}"
            except AttributeError:
                logger.trace("Failed to capture source context for error")

        new_error = type(e)(error_msg)
        # Attach proxy metadata using setattr to avoid type checker issues
        proxy_info = {
            "proxy_type": type(self.proxy).__name__,
            "method": method_name,
            "column": getattr(self.proxy, "name", None),
        }
        setattr(new_error, "proxy_info", proxy_info)  # noqa: B010
        setattr(new_error, "_dispatch_enhanced", True)  # noqa: B010
        return new_error


def _has_column_operands(args: tuple, kwargs: dict) -> bool:
    """Check if any argument is a column reference or expression with named columns."""
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    for arg in args:
        if isinstance(arg, (ColumnProxy, ExpressionProxy)):
            return True
        # Also check for pl.Expr with named columns (from _unwrap_for_arithmetic)
        if isinstance(arg, pl.Expr) and 'col("' in str(arg):
            return True
    for val in kwargs.values():
        if isinstance(val, (ColumnProxy, ExpressionProxy)):
            return True
        if isinstance(val, pl.Expr) and 'col("' in str(val):
            return True
    return False


def _execute_list_pow_plugin(
    base_expr: pl.Expr,
    args: tuple,
    *,
    base_is_list: bool = True,
) -> pl.Expr:
    """Execute pow using Rust list_pow plugin for list columns with column exponents.

    Handles three cases:
    - list ** list: direct list_pow call
    - list ** scalar: direct list_pow call (plugin handles broadcasting)
    - scalar ** list: uses exp/log identity since list_pow requires list base
    """
    from gaspatchio_core.functions.vector import list_pow

    if not args:
        msg = "pow requires an exponent argument"
        raise ValueError(msg)

    exp_arg = args[0]
    exp_expr = _unwrap(exp_arg)

    if not isinstance(exp_expr, pl.Expr):
        exp_expr = pl.lit(exp_expr)

    if base_is_list:
        logger.trace(f"Using list_pow plugin: base={base_expr}, exp={exp_expr}")
        return list_pow(base_expr, exp_expr)

    # scalar ** list: use exp/log identity (scalar^list = exp(list * log(scalar))).
    # The identity only holds for strictly positive bases. For zero or negative
    # bases, log() produces -inf/NaN which corrupts the result silently.
    # Guard: use when/then to handle base > 0 (exp/log), base == 0 (zero result),
    # and base < 0 (NaN with warning — negative bases with fractional exponents
    # are undefined in real numbers).
    logger.trace("Using guarded exp/log identity for scalar**list pow")
    exp_log_result = (exp_expr * base_expr.log()).list.eval(pl.element().exp())
    return (
        pl.when(base_expr > 0)
        .then(exp_log_result)
        .when(base_expr.eq(0))
        .then(exp_expr.list.eval(
            pl.when(pl.element() > 0).then(0.0)
            .when(pl.element().eq(0)).then(1.0)  # 0^0 = 1 by convention
            .otherwise(pl.lit(float("nan")))
        ))
        .otherwise(pl.lit(None))  # negative base: undefined for fractional exponents
    )


_CLIP_UPPER_ARG_INDEX = 2


def _execute_list_clip_plugin(
    base_expr: pl.Expr,
    args: tuple,
    kwargs: dict,
) -> pl.Expr:
    """Execute clip using Rust list_clip plugin for list columns with column bounds."""
    from gaspatchio_core.functions.vector import list_clip

    # Extract lower and upper bounds from args or kwargs
    lower_arg = None
    upper_arg = None

    if len(args) >= 1:
        lower_arg = args[0]
    if len(args) >= _CLIP_UPPER_ARG_INDEX:
        upper_arg = args[1]

    # Check kwargs for bounds (Polars uses lower_bound/upper_bound)
    if "lower_bound" in kwargs:
        lower_arg = kwargs["lower_bound"]
    if "upper_bound" in kwargs:
        upper_arg = kwargs["upper_bound"]

    # Convert to expressions
    lower_expr = _unwrap(lower_arg) if lower_arg is not None else pl.lit(float("-inf"))
    upper_expr = _unwrap(upper_arg) if upper_arg is not None else pl.lit(float("inf"))

    # Ensure they are Polars expressions
    if not isinstance(lower_expr, pl.Expr):
        lower_expr = pl.lit(lower_expr)
    if not isinstance(upper_expr, pl.Expr):
        upper_expr = pl.lit(upper_expr)

    logger.trace(
        f"Using list_clip plugin: values={base_expr}, "
        f"lower={lower_expr}, upper={upper_expr}"
    )
    return list_clip(base_expr, lower_expr, upper_expr)


def _method_caller(  # noqa: PLR0913
    *,
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: Any,  # noqa: ANN401
    a: tuple,
    kw: dict,
) -> Any:  # noqa: ANN401
    """Execute the delegated method with proper list-type handling."""
    # For pow: check if any ARGUMENT is a ColumnProxy referencing a list column
    # BEFORE unwrapping args (which converts ColumnProxy to pl.Expr).
    pow_arg_is_list = False
    if name == "pow" and a and parent_af:
        from .column_proxy import ColumnProxy

        detector = ColumnTypeDetector(parent_af)
        for arg in a:
            if isinstance(arg, ColumnProxy) and detector.is_list_column(arg.name):
                pow_arg_is_list = True
                logger.trace(f"Pow argument {arg.name} is list column")
                break

    # For arithmetic operations, pre-process args to convert ConditionExpression
    # to boolean float expressions (0.0/1.0) for mask patterns (GSP-12)
    if name in _ARITHMETIC_OPS:
        a = tuple(_unwrap_for_arithmetic(arg) for arg in a)
        kw = {k: _unwrap_for_arithmetic(v) for k, v in kw.items()}

    # Determine if we should use list shimming
    should_use_list_shim = _should_use_list_shim(name, self_proxy, parent_af, base_expr)
    pow_base_is_list = should_use_list_shim

    # If self is not a list but the argument is, still enable list shim for pow
    if not should_use_list_shim and pow_arg_is_list:
        should_use_list_shim = True
        pow_base_is_list = False  # self is scalar/expr, arg is the list
        logger.trace("Pow argument is list — enabling list shim with scalar base")

    # Check if this is a unary operation
    is_unary = name in _NUMERIC_UNARY and not a and not kw

    logger.trace(
        f"Method caller for {name}: list_shim={should_use_list_shim}, unary={is_unary}"
    )

    # Create error enhancer for this method call
    error_enhancer = ErrorEnhancer(self_proxy)

    try:
        if should_use_list_shim:
            # For pow on list columns, route directly to Rust list_pow plugin.
            # The list shim can't handle pow with column operands (list.eval
            # can't reference external columns), and native Polars pow fails
            # at collect time with InvalidOperationError on list dtypes.
            if name == "pow" and a:
                logger.trace(f"Routing pow to plugin (base_is_list={pow_base_is_list})")
                result = _execute_list_pow_plugin(base_expr, a, base_is_list=pow_base_is_list)
            else:
                try:
                    logger.trace(f"Executing list shim for {name}")
                    result = _execute_list_shim(name, base_expr, a, kw, is_unary=is_unary)
                except (TypeError, ValueError) as list_error:
                    # List shim failed - check if we can use a Rust plugin instead
                    logger.trace(f"List shim failed for {name}: {list_error}")

                    # For clip with column operands, use Rust list_clip plugin
                    if name == "clip" and _has_column_operands(a, kw):
                        logger.trace("Routing to list_clip Rust plugin")
                        result = _execute_list_clip_plugin(base_expr, a, kw)
                    else:
                        # Fallback to regular execution for other operations
                        result = _execute_regular(polars_attr, a, kw)
        else:
            result = _execute_regular(polars_attr, a, kw)
    except Exception as e:
        raise error_enhancer.enhance_method_error(e, name) from e

    return _wrap(parent_af, result)


# === AUTOPATCHING ===


def _autopatch(proxy_cls: type["ProxyType"]) -> None:
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
    processed_attrs: set[str] = set()

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
        # 3. Already exist on the proxy class (method overriding happens here)
        #    Custom implementations take precedence over Polars methods
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
        except AttributeError as e:
            # Rare, but good practice to handle exceptions
            logger.warning(
                f"Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}"
            )

    # === STEP 3: Enhance __dir__ for proper introspection ===
    # This ensures that when users call dir() on a proxy object,
    # they see both the original methods and the dynamically added Polars methods

    # Preserve any existing __dir__ implementation, or use object.__dir__ as fallback
    original_dir = getattr(proxy_cls, "__dir__", object.__dir__)

    # Define our enhanced __dir__ method
    def enhanced_dir(self: "ProxyType") -> list[str]:
        """Return all attributes on this proxy, including dynamic Polars attrs."""
        # Combine:
        # 1. Original attributes from the class
        # 2. Dynamically added Polars attributes
        # Only include successfully patched attributes (might be overly cautious)
        dynamic_attrs = {attr for attr in processed_attrs if hasattr(proxy_cls, attr)}
        return sorted(set(original_dir(self)) | dynamic_attrs)

    # Replace the proxy class's __dir__ method with our enhanced version
    proxy_cls.__dir__ = enhanced_dir
