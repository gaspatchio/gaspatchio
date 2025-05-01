from __future__ import annotations

import logging as log
import os
import re  # Added for robust extraction
from contextlib import contextmanager
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

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

# ADD TYPE_CHECKING import for DateColumnAccessor
if TYPE_CHECKING:
    from .accessors.date import DateColumnAccessor, DateFrameAccessor

    # ADD TYPE_CHECKING import for Finance accessors
    from .accessors.finance import FinanceColumnAccessor, FinanceFrameAccessor


# RESTORED MISSING BLOCK
# Define custom warning class
class PerformanceWarning(Warning):
    """Warning for potential performance issues."""

    pass


# Enable performance monitoring via telemetry
configure_telemetry(enable=True)


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

    # Add the .date property
    @property
    def date(self) -> "DateColumnAccessor":
        """Access date-specific methods for this expression."""
        # Import locally to prevent runtime circular dependency
        from .accessors.date import DateColumnAccessor

        return DateColumnAccessor(self)

    # ADD the .finance property
    @property
    def finance(self) -> "FinanceColumnAccessor":
        """Access finance-specific methods for this expression."""
        # Import locally to prevent runtime circular dependency
        from .accessors.finance import FinanceColumnAccessor

        return FinanceColumnAccessor(self)

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
        """Cast the expression to a specific data type."""
        casted_expr = self._expr.cast(dtype)
        return ExpressionProxy(casted_expr, self._parent)

    # ADDED: __dir__ method
    def __dir__(self):
        """Provide a list of attributes for introspection, including registered accessors."""
        # Start with standard attributes
        standard_attrs = set(object.__dir__(self))
        standard_attrs.update(dir(type(self)))

        # Add registered column accessors
        # Import locally to prevent runtime circular dependency during registration
        from .plugins import get_registered_accessors

        column_accessors = set(get_registered_accessors("column").keys())

        return sorted(list(standard_attrs | column_accessors))


class ColumnProxy:
    """Proxy for DataFrame columns that captures operations."""

    def __init__(self, name, parent):
        self.name = name
        self._parent = parent

    # Add the .date property
    @property
    def date(self) -> "DateColumnAccessor":
        """Access date-specific methods for this column."""
        # Import locally to prevent runtime circular dependency
        from .accessors.date import DateColumnAccessor

        return DateColumnAccessor(self)

    # ADD the .finance property
    @property
    def finance(self) -> "FinanceColumnAccessor":
        """Access finance-specific methods for this column."""
        # Import locally to prevent runtime circular dependency
        from .accessors.finance import FinanceColumnAccessor

        return FinanceColumnAccessor(self)

    def collect(self):
        """Collect the column as a Series."""
        return self._parent.collect()[self.name]

    def __array__(self):
        """Support for NumPy functions."""
        # This allows NumPy functions to work with ColumnProxy objects
        # by converting to a NumPy array when needed
        return self.collect().to_numpy()

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

    # ADDED: apply method for compatibility
    def apply(
        self, func: Callable[[Any], Any], return_dtype: pl.PolarsDataType | None = None
    ) -> ExpressionProxy:
        """Apply a Python function element-wise to the column.

        This is a convenience method that maps to Polars' `map_elements`.

        Args:
            func: The function to apply to each element.
            return_dtype: Optional Polars dtype for the returned expression.
                It's often recommended to provide this for performance.

        Returns:
            An ExpressionProxy representing the operation.
        """
        expr = pl.col(self.name).map_elements(func, return_dtype=return_dtype)
        return ExpressionProxy(expr, self._parent)

    # ADDED: __dir__ method
    def __dir__(self):
        """Provide a list of attributes for introspection, including registered accessors."""
        # Start with standard attributes
        standard_attrs = set(object.__dir__(self))
        standard_attrs.update(dir(type(self)))

        # Add registered column accessors
        # Import locally to prevent runtime circular dependency during registration
        from .plugins import get_registered_accessors

        column_accessors = set(get_registered_accessors("column").keys())

        return sorted(list(standard_attrs | column_accessors))


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
                initial_columns = list(data.collect_schema().keys())
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
        self._show_query_plan = False  # Flag to control query plan logging
        self._column_order: List[str] = initial_columns  # Track column addition order

        # Use global defaults if not specified
        self._mode = mode if mode is not None else get_default_mode()
        self._verbose = verbose if verbose is not None else get_default_verbose()
        self._threads = threads if threads is not None else _DEFAULT_THREADS

    # ADDED: .date property for frame-level date operations
    @property
    def date(self) -> "DateFrameAccessor":
        """Access date-specific methods for this ActuarialFrame."""
        # Import locally to prevent runtime circular dependency
        from .accessors.date import DateFrameAccessor

        return DateFrameAccessor(self)

    # ADDED: .finance property for frame-level finance operations
    @property
    def finance(self) -> "FinanceFrameAccessor":
        """Access finance-specific methods for this ActuarialFrame."""
        # Import locally to prevent runtime circular dependency
        from .accessors.finance import FinanceFrameAccessor

        return FinanceFrameAccessor(self)

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

    # ADDED: __dir__ method for enhanced introspection
    def __dir__(self):
        """Provide a comprehensive list of attributes for introspection.

        Includes standard methods, column names, and custom accessors.
        """
        # Start with standard attributes of the class and instance
        standard_attrs = set(object.__dir__(self))
        standard_attrs.update(dir(type(self)))

        # Add column names (if available)
        try:
            column_attrs = set(self._df.columns)
        except Exception:
            # Handle cases where schema might not be available yet
            column_attrs = set(self._column_order)  # Use tracked order as fallback

        # Combine and sort
        # Note: Explicit accessors like .date are already included via dir(type(self))
        return sorted(list(standard_attrs | column_attrs))

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
        elif isinstance(value, str):
            # ADDED: Treat strings as column names
            return pl.col(value)
        elif isinstance(value, np.ndarray):
            # For numpy arrays, convert to literal
            return pl.lit(value)
        else:
            # For all other types, convert to literal
            return pl.lit(value)

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

    def _extract_missing_column_robust(self, error_str: str) -> str | None:
        """Attempts to extract the missing column name from specific error patterns.
        Assumes error_str is derived from `str(ColumnNotFoundError)`.
        """
        # Pattern 1: Starts with column name, followed by newline
        # Example: 'invalid_start\n\nResolved plan...'
        match = re.match(r"^([^\s'\"]+)\n", error_str)
        if match:
            return match.group(1)

        # Pattern 2: contains "column 'col_name' not found" (less common from str(e)?)
        match = re.search(r"column\s*'([^']*)'\s*not found", error_str, re.IGNORECASE)
        if match:
            return match.group(1)

        # Pattern 3: contains "unable to find column \"col_name\""
        match = re.search(r"unable to find column \\\"([^\\\"]*)\\\"", error_str)
        if match:
            return match.group(1)

        # Pattern 4: Format like "ColumnNotFoundError: policy_duration_as_int"
        match = re.search(r"ColumnNotFoundError:\s*([^\s'\"]+)", error_str)
        if match:
            return match.group(1)

        # Pattern 5: Fallback for missing columns that were assigned but not in the dataframe
        # Look for any column name that we've tracked but isn't in the final dataframe
        for col in self._column_order:
            if col in error_str:
                return col

        # If no patterns match, return None
        return None

    def _format_column_error(
        self, original_exception: Exception, missing_col: str, original_msg: str
    ) -> Exception:
        """Formats a helpful error message for a missing column, including original error."""
        try:
            # Use columns property which works for both Lazy and Eager frames
            available_cols = self._df.columns
        except Exception:
            available_cols = self._column_order  # Fallback

        similar_cols = self._find_similar_columns(missing_col, available_cols)

        error_msg = f"Column '{missing_col}' not found in the DataFrame.\n\n"

        if similar_cols:
            error_msg += (
                "Did you mean one of these?\n - " + "\n - ".join(similar_cols) + "\n\n"
            )

        error_msg += "Available columns are:\n - " + "\n - ".join(available_cols)
        error_msg += (
            f"\n\nOriginal Polars Error: {original_msg}"  # Include original message
        )

        # Return a new exception of the original type with the formatted message
        return type(original_exception)(error_msg)

    def _handle_execution_error(self, e: Exception):
        """Handles potential Polars errors during collect/profile, improving context."""
        original_error_msg = str(e)
        log.debug(
            f"Handling execution error. Original Polars Error: {original_error_msg}"
        )
        log.debug(f"Raw error message repr for extraction: {repr(original_error_msg)}")

        # Prioritize specific Polars error types
        if isinstance(e, pl.ColumnNotFoundError):
            missing_col = self._extract_missing_column_robust(original_error_msg)
            if missing_col:
                # Format and raise the specific column error
                raise self._format_column_error(
                    e, missing_col, original_error_msg
                ) from None
            else:
                # If extraction fails, raise with original message but add available columns hint
                log.warning("Column extraction failed for ColumnNotFoundError.")
                try:
                    available_cols = self._df.columns
                except Exception:
                    available_cols = self._column_order  # Fallback
                raise type(e)(
                    f"{original_error_msg}\n\nAvailable columns: {available_cols}"
                ) from None

        # Handle Type/Operation errors specifically - original message is usually best
        elif isinstance(
            e, (pl.InvalidOperationError, TypeError, pl.SchemaError, pl.ComputeError)
        ):
            # Add available columns info if it seems like a column issue based on keywords
            if (
                "column" in original_error_msg.lower()
                or "field" in original_error_msg.lower()
            ):
                try:
                    available_cols = self._df.columns
                except Exception:
                    available_cols = self._column_order  # Fallback
                raise type(e)(
                    f"Polars operation/schema error: {original_error_msg}\n\nAvailable columns might be: {available_cols}"
                ) from None
            else:
                raise type(e)(
                    f"Polars operation/schema error: {original_error_msg}"
                ) from None

        # Fallback for other/unexpected errors
        log.warning(f"Unhandled exception type during execution: {type(e).__name__}")
        raise e  # Re-raise the original exception

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


# Ensure autopatch calls are at the very end
from ._delegation import _autopatch

_autopatch(ColumnProxy)
_autopatch(ExpressionProxy)

# Import plugins module at the end to trigger registration AFTER core classes are defined
from . import plugins  # noqa: F401 - Ensures registration happens
