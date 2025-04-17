from __future__ import annotations

import logging as log
import os
import warnings
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, List, Tuple

import numpy as np
import polars as pl

# ADDED: Import thefuzz
from thefuzz import process

# ADDED: Import custom functions
from gaspatchio_core.functions import fill_series as core_fill_series
from gaspatchio_core.functions import floor as core_floor
from gaspatchio_core.functions import round as core_round
from gaspatchio_core.functions import round_to_int as core_round_to_int

# ADDED: Import telemetry module
from gaspatchio_core.telemetry import configure_telemetry
from gaspatchio_core.typing import IntoExprColumn


# Define custom warning class
class PerformanceWarning(Warning):
    """Warning for potential performance issues."""

    pass


# Enable performance monitoring via telemetry
configure_telemetry(enable=True)


# Try to import numba, but make it optional
try:
    import numba

    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False

    # Define empty functions as placeholders
    class numba:
        @staticmethod
        def vectorize(func):
            return func

        @staticmethod
        def njit(func):
            return func


# Global settings
_DEFAULT_MODE = os.environ.get("GASPATCHIO_MODE", "debug")
_DEFAULT_VERBOSE = os.environ.get("GASPATCHIO_VERBOSE", "True").lower() in (
    "true",
    "1",
    "yes",
)
_DEFAULT_THREADS = int(
    os.environ.get("GASPATCHIO_THREADS", "0")
)  # 0 means use all available


def get_default_mode() -> str:
    """Get the default execution mode."""
    return _DEFAULT_MODE


def set_default_mode(mode: str) -> None:
    """Set the default execution mode."""
    global _DEFAULT_MODE
    if mode not in ("debug", "optimize"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'debug' or 'optimize'")
    _DEFAULT_MODE = mode
    os.environ["GASPATCHIO_MODE"] = mode


def get_default_verbose() -> bool:
    """Get the default verbosity setting."""
    return _DEFAULT_VERBOSE


def set_default_verbose(verbose: bool) -> None:
    """Set the default verbosity setting."""
    global _DEFAULT_VERBOSE
    _DEFAULT_VERBOSE = verbose


@contextmanager
def execution_mode(mode: str):
    """Context manager for temporarily changing the execution mode."""
    old_mode = get_default_mode()
    try:
        set_default_mode(mode)
        yield
    finally:
        set_default_mode(old_mode)


class ExpressionProxy:
    """Proxy for Polars expressions that captures operations."""

    def __init__(self, expr, parent):
        self._expr = expr
        self._parent = parent

    # Arithmetic operations
    def __add__(self, other):
        expr = self._expr + self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __radd__(self, other):
        expr = self._parent._convert_to_expr(other) + self._expr
        return ExpressionProxy(expr, self._parent)

    def __sub__(self, other):
        expr = self._expr - self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rsub__(self, other):
        expr = self._parent._convert_to_expr(other) - self._expr
        return ExpressionProxy(expr, self._parent)

    def __mul__(self, other):
        expr = self._expr * self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rmul__(self, other):
        expr = self._parent._convert_to_expr(other) * self._expr
        return ExpressionProxy(expr, self._parent)

    def __truediv__(self, other):
        expr = self._expr / self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rtruediv__(self, other):
        expr = self._parent._convert_to_expr(other) / self._expr
        return ExpressionProxy(expr, self._parent)

    def __floordiv__(self, other):
        expr = self._expr // self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rfloordiv__(self, other):
        expr = self._parent._convert_to_expr(other) // self._expr
        return ExpressionProxy(expr, self._parent)

    def __pow__(self, other):
        expr = self._expr ** self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rpow__(self, other):
        expr = self._parent._convert_to_expr(other) ** self._expr
        return ExpressionProxy(expr, self._parent)

    def __mod__(self, other):
        expr = self._expr % self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rmod__(self, other):
        expr = self._parent._convert_to_expr(other) % self._expr
        return ExpressionProxy(expr, self._parent)

    # Comparison operations
    def __eq__(self, other):
        expr = self._expr == self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __ne__(self, other):
        expr = self._expr != self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __lt__(self, other):
        expr = self._expr < self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __le__(self, other):
        expr = self._expr <= self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __gt__(self, other):
        expr = self._expr > self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __ge__(self, other):
        expr = self._expr >= self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def alias(self, name):
        """Alias the expression with a name."""
        return ExpressionProxy(self._expr.alias(name), self._parent)

    def cast(self, dtype):
        """Cast the expression to a specific data type, handling lists."""
        # Define common scalar Polars types
        scalar_types = (
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Float32,
            pl.Float64,
            pl.Boolean,
            pl.Utf8,  # Add other scalar types like Date, Datetime, Duration etc. if needed
        )

        # Check if the target dtype is a scalar type instance or class
        is_scalar_target = False
        if isinstance(dtype, pl.DataType):  # e.g., pl.Int64()
            # Check if the base type is in our tuple of scalar types
            try:  # Use try-except as base_type might not exist for all types
                if dtype.base_type() in scalar_types:
                    is_scalar_target = True
            except AttributeError:
                pass
        elif isinstance(dtype, type) and issubclass(
            dtype, pl.DataType
        ):  # e.g., pl.Int64
            if dtype in scalar_types:
                is_scalar_target = True

        if is_scalar_target:
            # If casting to a scalar type, assume the operation might be on list elements.
            # Use list.eval to apply the cast element-wise.
            # This assumes Polars handles the case where self._expr is *not* a list gracefully,
            # or that the context implies it's likely a list.
            casted_expr = self._expr.list.eval(pl.element().cast(dtype))

            # Preserve the original expression name if list.eval changes it
            try:
                original_name = self._expr.meta.output_name()
                casted_expr = casted_expr.alias(original_name)
            except (
                Exception
            ):  # Handle cases where meta or output_name might not be available
                pass

        else:
            # If casting to a non-scalar type (e.g., List, Struct), use the direct cast.
            casted_expr = self._expr.cast(dtype)

        return ExpressionProxy(casted_expr, self._parent)


class ColumnProxy:
    """Proxy for DataFrame columns that captures operations."""

    def __init__(self, name, parent):
        self.name = name
        self._parent = parent

    def apply(self, func):
        """Apply a function to this column."""
        return self._parent.apply_function(func, self)

    def collect(self):
        """Collect the column as a Series."""
        return self._parent.collect()[self.name]

    def __array__(self):
        """Support for NumPy functions."""
        # This allows NumPy functions to work with ColumnProxy objects
        # by converting to a NumPy array when needed
        return self.collect().to_numpy()

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Support for NumPy universal functions."""
        # Handle NumPy ufuncs like np.sqrt, np.exp, etc.
        if method == "__call__":
            # Convert the ufunc to a lambda function
            func = lambda x: ufunc(x)
            return self._parent.apply_function(func, self)
        return NotImplemented

    # Arithmetic operations
    def __add__(self, other):
        expr = pl.col(self.name) + self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __radd__(self, other):
        expr = self._parent._convert_to_expr(other) + pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    def __sub__(self, other):
        expr = pl.col(self.name) - self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rsub__(self, other):
        expr = self._parent._convert_to_expr(other) - pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    def __mul__(self, other):
        expr = pl.col(self.name) * self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rmul__(self, other):
        expr = self._parent._convert_to_expr(other) * pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    def __truediv__(self, other):
        expr = pl.col(self.name) / self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rtruediv__(self, other):
        expr = self._parent._convert_to_expr(other) / pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    def __floordiv__(self, other):
        expr = pl.col(self.name) // self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rfloordiv__(self, other):
        expr = self._parent._convert_to_expr(other) // pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    def __pow__(self, other):
        expr = pl.col(self.name) ** self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rpow__(self, other):
        expr = self._parent._convert_to_expr(other) ** pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    def __mod__(self, other):
        expr = pl.col(self.name) % self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __rmod__(self, other):
        expr = self._parent._convert_to_expr(other) % pl.col(self.name)
        return ExpressionProxy(expr, self._parent)

    # Comparison operations
    def __eq__(self, other):
        expr = pl.col(self.name) == self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __ne__(self, other):
        expr = pl.col(self.name) != self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __lt__(self, other):
        expr = pl.col(self.name) < self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __le__(self, other):
        expr = pl.col(self.name) <= self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __gt__(self, other):
        expr = pl.col(self.name) > self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)

    def __ge__(self, other):
        expr = pl.col(self.name) >= self._parent._convert_to_expr(other)
        return ExpressionProxy(expr, self._parent)


class ActuarialFrame:
    """A DataFrame wrapper that captures operations while allowing direct Python execution"""

    def __init__(self, data=None, mode=None, verbose=None, threads=None):
        # Initialize _df correctly based on whether data is Lazy or Eager
        if data is None:
            self._df = pl.LazyFrame()
            initial_columns = []
        elif isinstance(data, pl.LazyFrame):
            self._df = data
            # Need to collect schema to get initial columns for LazyFrame
            try:
                initial_columns = list(data.schema.keys())
            except (
                Exception
            ):  # Handle cases where schema might not be immediately available
                initial_columns = []  # Or collect a small sample: data.limit(1).columns
        elif isinstance(data, pl.DataFrame):
            self._df = data.lazy()
            initial_columns = list(data.columns)
        else:
            # Attempt to convert other types, e.g., dictionaries
            try:
                self._df = pl.LazyFrame(data)
                initial_columns = list(self._df.schema.keys())
            except Exception as e:
                raise TypeError(
                    f"Unsupported data type for ActuarialFrame: {type(data)}. Error: {e}"
                )

        self._computation_graph: List[Tuple[str, ...]] = []
        self._tracing = False
        self._context: Dict[str, Any] = {}  # Store local variables
        self._operation_log: List[str] = []
        self._batch_enabled = False
        self._batch_size = 10000
        self._show_query_plan = False  # Flag to control query plan logging
        self._column_order: List[str] = initial_columns  # Track column addition order

        # Use global defaults if not specified
        self._mode = mode if mode is not None else get_default_mode()
        self._verbose = verbose if verbose is not None else get_default_verbose()
        self._threads = threads if threads is not None else _DEFAULT_THREADS

    def __getitem__(self, key):
        """Allow df['column'] access"""
        if isinstance(key, str):
            # Ensure the column exists in the internal order if accessed
            # This helps catch typos early if the column wasn't added yet.
            # Note: This check might be too strict depending on usage patterns.
            # if key not in self._column_order and key not in self._df.columns:
            #     raise KeyError(f"Column '{key}' not found in ActuarialFrame.")
            return ColumnProxy(key, self)
        # Allow slicing or other indexing on the underlying frame if needed?
        # For now, return self to avoid breaking expected behavior elsewhere.
        return self

    def __setitem__(self, key, value):
        """Capture df['column'] = value operations"""
        # Track the order of column assignment *before* the operation
        if key not in self._column_order:
            self._column_order.append(key)
        try:
            expr = self._convert_to_expr(value)

            if self._tracing:
                # When inside a traced function, register operation
                self._computation_graph.append(("column", key, expr))
                if self._verbose:
                    self._operation_log.append(
                        f"Set column '{key}' = {self._expr_to_str(value)} (traced)"
                    )
            else:
                # Direct execution when not tracing
                self._df = self._df.with_columns(expr.alias(key))
                if self._verbose:
                    self._operation_log.append(
                        f"Set column '{key}' = {self._expr_to_str(value)} (executed)"
                    )
        except Exception as e:
            # Enhance the error with context
            raise type(e)(
                f"Error setting column '{key}': {str(e)}. "
                f"Value type: {type(value).__name__}"
            ) from e
        return self

    def _expr_to_str(self, value):
        """Convert an expression to a readable string for logging"""
        if isinstance(value, ColumnProxy):
            return f"Column[{value.name}]"
        elif isinstance(value, pl.Expr):
            return str(value)
        elif callable(value):
            return f"Function[{value.__name__}]"
        else:
            return repr(value)

    def _convert_to_expr(self, value):
        """Convert a value to a Polars expression."""
        if isinstance(value, ColumnProxy):
            # For ColumnProxy, use the column name to create an expression
            return pl.col(value.name)
        elif isinstance(value, ExpressionProxy):
            # For ExpressionProxy, return the internal expression
            return value._expr
        elif isinstance(value, pl.Expr):
            # For direct Polars expressions, return as is
            return value
        elif callable(value):
            # For callable functions, vectorize them
            return self._vectorize_function(value)
        elif isinstance(value, np.ndarray):
            # For numpy arrays, convert to literal
            return pl.lit(value)
        else:
            # For all other types, convert to literal
            return pl.lit(value)

    def _vectorize_function(self, func):
        """Convert a Python function to a vectorized Polars expression"""
        # Implementation varies by mode (debug vs optimize)
        if self._mode == "optimize" and HAS_NUMBA:
            try:
                # Try to use Numba in optimize mode
                try:
                    # Always attempt vectorize first
                    jit_func = numba.vectorize(func)
                    return lambda s: s.map_elements(
                        lambda x: jit_func(x), return_dtype=pl.Float64
                    )
                except Exception:
                    # If vectorize fails, always try njit
                    jit_func = numba.njit(func)
                    return lambda s: s.map_elements(
                        lambda x: jit_func(x), return_dtype=pl.Float64
                    )
            except Exception as e2:
                if self._verbose:
                    log.warning(
                        f"Function {func.__name__} couldn't be compiled with Numba. "
                        f"Falling back to Python execution. Reason: {str(e2)}"
                    )
                # Fall back to Python UDF
                return lambda s: s.map_elements(func, return_dtype=pl.Float64)
        else:
            # In debug mode or when Numba is not available, use the original Python function
            return lambda s: s.map_elements(func, return_dtype=pl.Float64)

    def apply_function(self, func, *args):
        """Apply a function to one or more columns."""
        # Convert all arguments to expressions
        expr_args = [self._convert_to_expr(arg) for arg in args]

        # Default to Float64 for return_dtype to avoid warnings
        return_dtype = pl.Float64

        if self._mode == "debug":
            try:
                if len(expr_args) == 1:
                    # Single column case - use map_elements with return_dtype
                    return ExpressionProxy(
                        expr_args[0].map_elements(
                            lambda x: func(x),
                            return_dtype=return_dtype,
                            skip_nulls=False,
                        ),
                        self,
                    )
                else:
                    # Multiple columns case - use struct and map_elements
                    return ExpressionProxy(
                        pl.struct(expr_args).map_elements(
                            lambda row: func(*[row[i] for i in range(len(expr_args))]),
                            return_dtype=return_dtype,
                            skip_nulls=False,
                        ),
                        self,
                    )
            except Exception as e:
                raise RuntimeError(f"Error applying function in debug mode: {e}")
        else:  # optimize mode
            try:
                # Try to use Polars' optimized functions if possible
                if hasattr(func, "__polars_func__"):
                    # Function has a Polars-optimized version
                    return ExpressionProxy(func.__polars_func__(*expr_args), self)
                elif HAS_NUMBA:
                    # Use Numba if available
                    vectorized_func = self._vectorize_function(func)
                    if len(expr_args) == 1:
                        # Now vectorized_func returns a lambda function
                        return ExpressionProxy(
                            vectorized_func(expr_args[0]),
                            self,
                        )
                    else:
                        # For multiple arguments, pass the struct to the vectorized function
                        return ExpressionProxy(
                            pl.struct(expr_args).map_elements(
                                lambda row: func(
                                    *[row[i] for i in range(len(expr_args))]
                                ),
                                return_dtype=return_dtype,
                                skip_nulls=False,
                            ),
                            self,
                        )
                else:
                    # Fall back to Python execution with a warning
                    warnings.warn(
                        "Function execution falling back to Python mode. "
                        "This may impact performance. Consider using Numba or "
                        "providing a Polars-optimized version.",
                        PerformanceWarning,
                    )
                    if len(expr_args) == 1:
                        return ExpressionProxy(
                            expr_args[0].map_elements(
                                lambda x: func(x),
                                return_dtype=return_dtype,
                                skip_nulls=False,
                            ),
                            self,
                        )
                    else:
                        return ExpressionProxy(
                            pl.struct(expr_args).map_elements(
                                lambda row: func(
                                    *[row[i] for i in range(len(expr_args))]
                                ),
                                return_dtype=return_dtype,
                                skip_nulls=False,
                            ),
                            self,
                        )
            except Exception as e:
                raise RuntimeError(f"Error applying function in optimize mode: {e}")

    def _log_query_plan(self, operations):
        """Log the query plan before execution"""
        log.info("===== QUERY PLAN =====")
        for i, (op_type, *op_args) in enumerate(operations):
            if op_type == "column":
                col_name, expr = op_args
                log.info(f"  {i + 1}. SET COLUMN: '{col_name}' = {expr}")
            elif op_type == "table_lookup":
                table_name = op_args[0]
                log.info(f"  {i + 1}. TABLE LOOKUP: '{table_name}'")
            elif op_type == "table_lookup_vector":
                table_name = op_args[0]
                log.info(f"  {i + 1}. VECTOR LOOKUP: '{table_name}'")
            elif op_type == "register_table":
                table_name, key_spec = op_args
                log.info(
                    f"  {i + 1}. REGISTER TABLE: '{table_name}' with keys {key_spec.source_cols}"
                )
            elif op_type == "register_table_transform":
                table_name, key_spec, transform_spec = op_args
                log.info(f"  {i + 1}. REGISTER TRANSFORMED TABLE: '{table_name}'")

        # Include Polars execution plan if available
        try:
            polars_plan = self._df.explain()
            log.info("POLARS EXECUTION PLAN:")
            log.info(polars_plan)
        except Exception as e:
            log.info(f"Could not retrieve Polars execution plan: {e}")

        log.info("=======================")

    def show_query_plan(self, enabled=True):
        """Enable or disable query plan logging before execution"""
        self._show_query_plan = enabled
        return self

    def trace(self, func):
        """Decorator to trace a function's dataframe operations"""

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Enable tracing for wrapped function calls
            original_tracing = self._tracing
            self._tracing = True

            # Debug mode: execute directly
            if self._mode == "debug":
                try:
                    result = func(*args, **kwargs)
                finally:
                    self._tracing = original_tracing
                return result

            # Optimize mode: capture operations
            old_graph = self._computation_graph
            self._computation_graph = []

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                self._computation_graph = old_graph
                self._tracing = original_tracing
                raise e

            operations = self._computation_graph
            self._computation_graph = old_graph
            self._tracing = original_tracing

            # NEW: Output the query plan before execution
            if self._verbose or self._show_query_plan:
                self._log_query_plan(operations)

            # Apply captured operations
            df = self._df
            for op_type, *op_args in operations:
                if op_type == "column":
                    col_name, expr = op_args
                    df = df.with_columns(expr.alias(col_name))

            self._df = df
            return result

        return wrapper

    def _extract_missing_column(self, error_str: str) -> str | None:
        """Attempts to extract the missing column name from various error formats."""
        missing_col = None
        # Check specific formats first
        if "ColumnNotFoundError:" in error_str:
            # Example: "... raised ColumnNotFoundError: 'my_col'"
            parts = error_str.split("ColumnNotFoundError:")
            if len(parts) > 1:
                # Extract text after the error name, often enclosed in quotes
                potential_col = parts[1].strip().strip("'\"")
                # Simple heuristic: if it doesn't contain obvious error text, assume it's the column
                if (
                    potential_col
                    and "Resolved plan" not in potential_col
                    and "\n" not in potential_col
                ):
                    return potential_col

        elif "' not found" in error_str:
            # Example: "column 'my_col' not found"
            parts = error_str.split("'")
            if len(parts) >= 2:
                return parts[1]

        elif "\n\nResolved plan until failure:" in error_str:
            # Example: "my col name\n\nResolved plan..."
            possible_missing = error_str.split("\n\nResolved plan until failure:")[
                0
            ].strip()
            # Removed the 'no spaces' check here
            if possible_missing:
                return possible_missing

        # Fallback: Search known columns in the error string (less reliable)
        if not missing_col and "FAILED HERE RESOLVING" in error_str:
            try:
                current_cols = self._df.collect_schema().names()
                # Prioritize columns that were assigned but aren't in the final schema
                assigned_but_missing = [
                    col
                    for col in self._column_order
                    if col not in current_cols and col in error_str
                ]
                if assigned_but_missing:
                    missing_col = assigned_but_missing[
                        0
                    ]  # Take the first likely candidate
                else:
                    # Last resort: look for unknown words that look like identifiers
                    for word in error_str.split():
                        potential_col = word.strip("'\"[]():.,")
                        if (
                            potential_col
                            and potential_col not in current_cols
                            and len(potential_col) > 3
                            and potential_col.lower()
                            not in ["some", "other", "error", "involving", "maybe"]
                        ):
                            missing_col = potential_col
                            break
            except Exception:
                pass  # Ignore schema collection errors during fallback

        return missing_col

    def _format_column_error(
        self, original_exception: Exception, missing_col: str
    ) -> Exception:
        """Formats a helpful error message for a missing column."""
        try:
            available_cols = self._df.collect_schema().names()
        except Exception:
            available_cols = self._column_order

        similar_cols = self._find_similar_columns(missing_col, available_cols)

        error_msg = f"Column '{missing_col}' not found in the DataFrame.\n\n"

        if similar_cols:
            error_msg += (
                "Did you mean one of these?\n - " + "\n - ".join(similar_cols) + "\n\n"
            )

        error_msg += "Available columns are:\n - " + "\n - ".join(available_cols)

        # Return a new exception of the original type with the formatted message
        return type(original_exception)(error_msg)

    def _handle_execution_error(self, e: Exception):
        """Handles potential ColumnNotFoundErrors during collect/profile, re-raising others."""
        error_str = str(e)
        # Check if it looks like a column error
        is_column_error = (
            "ColumnNotFoundError" in str(type(e))
            or "column" in error_str.lower()
            and "not found" in error_str.lower()
            or "FAILED HERE RESOLVING" in error_str
        )

        if is_column_error:
            missing_col = self._extract_missing_column(error_str)
            if missing_col:
                # Format and raise the specific column error
                raise self._format_column_error(e, missing_col) from None

        # If it wasn't a column error we could identify, or extraction failed,
        # re-raise the original exception.
        raise e

    def collect(self):
        """Execute and materialize the dataframe"""
        try:
            if self._threads > 0:
                return self._df.collect(n_threads=self._threads)
            return self._df.collect()
        except Exception as e:
            self._handle_execution_error(e)

    def profile(self):
        """Execute and materialize the dataframe with profiling"""
        try:
            if self._threads > 0:
                return self._df.profile(n_threads=self._threads)
            return self._df.profile()
        except Exception as e:
            self._handle_execution_error(e)

    def _find_similar_columns(
        self, missing_col, available_cols, max_distance=3, max_suggestions=5
    ):
        """
        Find column names similar to the missing column using thefuzz library.

        Args:
            missing_col: The missing column name
            available_cols: List of available column names
            max_distance: Maximum edit distance to consider a match (as a ratio threshold)
            max_suggestions: Maximum number of suggestions to return

        Returns:
            List of column names similar to the missing one
        """
        if not missing_col or not available_cols:
            return []

        # Use thefuzz for finding similar columns

        # Convert the max_distance parameter to a ratio threshold (0-100)
        ratio_threshold = max(0, 100 - (max_distance * 20))

        # Use process.extract to find the most similar columns
        matches = process.extract(missing_col, available_cols, limit=max_suggestions)

        # Filter by score threshold
        matches = [(col, score) for col, score in matches if score >= ratio_threshold]

        # Extract just the column names
        similar_cols = [match[0] for match in matches]
        return similar_cols

    def optimize(self):
        """Apply Polars optimizations to the computation graph"""
        # Polars already does this, but we could add domain-specific optimizations
        return self

    def get_operation_log(self):
        """Return the operation log for debugging"""
        return self._operation_log

    def get_execution_stats(self):
        """Return execution statistics (for optimize mode)"""
        if self._mode == "optimize":
            # Get statistics from Polars execution
            return {
                "operations": len(self._operation_log),
                "optimized_ops": sum(
                    1 for op in self._operation_log if "optimized" in op
                ),
                "python_fallbacks": sum(
                    1 for op in self._operation_log if "fallback" in op
                ),
            }
        return None

    def batch_operations(self, batch_size: int = 10000) -> "ActuarialFrame":
        """
        Enable batch processing for large datasets.
        For operations like table lookups that require materialization,
        this will process the data in smaller chunks to reduce memory usage.

        Args:
            batch_size: Number of rows to process in each batch

        Returns:
            Self for method chaining
        """
        self._batch_enabled = True
        self._batch_size = batch_size
        if self._verbose:
            log.info(f"Batch processing enabled with batch size {batch_size}")
        return self

    def with_columns(self, *exprs) -> "ActuarialFrame":
        """
        Add columns to the DataFrame.

        Args:
            *exprs: Expression(s) for the new columns

        Returns:
            Self for method chaining
        """
        if self._tracing:
            # When inside a traced function, we can't directly modify the DataFrame
            # Instead, we'll need to capture these operations and apply them later
            for expr in exprs:
                if hasattr(expr, "_alias") and callable(expr._alias):
                    col_name = expr._alias
                    self._computation_graph.append(("column", col_name, expr))
                    if self._verbose:
                        self._operation_log.append(f"Add column '{col_name}'")
        else:
            # Direct execution when not tracing
            self._df = self._df.with_columns(*exprs)
            if self._verbose:
                self._operation_log.append("Add columns with expression")

        return self

    def pipe(self, func, *args, **kwargs) -> "ActuarialFrame":
        """
        Apply a function to the DataFrame that returns an ActuarialFrame.

        Args:
            func: Function that takes an ActuarialFrame as first argument
            *args: Additional positional arguments to pass to func
            **kwargs: Additional keyword arguments to pass to func

        Returns:
            ActuarialFrame: Result of applying func
        """
        result = func(self, *args, **kwargs)
        return result if result is not None else self

    # ADDED: Wrapper methods for custom functions
    def fill_series(
        self, expr: IntoExprColumn, start: int = 0, increment: int = 1
    ) -> ExpressionProxy:
        """Applies the fill_series function to an expression."""
        polars_expr = self._convert_to_expr(expr)
        result_expr = core_fill_series(polars_expr, start=start, increment=increment)
        return ExpressionProxy(result_expr, self)

    def floor(
        self, expr: IntoExprColumn, divisor: int = 1, default: int = 0
    ) -> ExpressionProxy:
        """Applies the floor function to an expression."""
        polars_expr = self._convert_to_expr(expr)
        result_expr = core_floor(polars_expr, divisor=divisor, default=default)
        return ExpressionProxy(result_expr, self)

    def round(self, expr: IntoExprColumn, decimal_places: int = 0) -> ExpressionProxy:
        """Applies the round function to an expression."""
        polars_expr = self._convert_to_expr(expr)
        result_expr = core_round(polars_expr, decimal_places=decimal_places)
        return ExpressionProxy(result_expr, self)

    def round_to_int(self, expr: IntoExprColumn) -> ExpressionProxy:
        """Applies the round_to_int function to an expression."""
        polars_expr = self._convert_to_expr(expr)
        result_expr = core_round_to_int(polars_expr)
        return ExpressionProxy(result_expr, self)

    def get_column_order(self) -> List[str]:
        """Return the tracked order of column additions/assignments."""
        return self._column_order


def run_model(model_func: Callable, df: ActuarialFrame) -> ActuarialFrame:
    """Run a model function on an ActuarialFrame"""
    # If we're in debug mode, just run the function directly
    if df._mode == "debug":
        result = model_func(df)
        return df if result is None else result

    # In optimize mode, use the tracer
    traced_func = df.trace(model_func)
    traced_func(df)
    return df
