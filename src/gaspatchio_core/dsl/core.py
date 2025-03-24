from __future__ import annotations

import logging as log
import os
import warnings
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import polars as pl

from gaspatchio_core.assumptions import table_registry


# Define custom warning class
class PerformanceWarning(Warning):
    """Warning for potential performance issues."""

    pass


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
        self._df = data.lazy() if hasattr(data, "lazy") else (data or pl.LazyFrame())
        self._computation_graph: List[Tuple[str, ...]] = []
        self._tracing = False
        self._context: Dict[str, Any] = {}  # Store local variables
        self._operation_log: List[str] = []
        self._batch_enabled = False
        self._batch_size = 10000

        # Use global defaults if not specified
        self._mode = mode if mode is not None else get_default_mode()
        self._verbose = verbose if verbose is not None else get_default_verbose()
        self._threads = threads if threads is not None else _DEFAULT_THREADS

    def __getitem__(self, key):
        """Allow df['column'] access"""
        if isinstance(key, str):
            return ColumnProxy(key, self)
        return self

    def __setitem__(self, key, value):
        """Capture df['column'] = value operations"""
        try:
            expr = self._convert_to_expr(value)

            if self._tracing:
                # When inside a traced function, register operation
                self._computation_graph.append(("column", key, expr))
                if self._verbose:
                    self._operation_log.append(
                        f"Set column '{key}' = {self._expr_to_str(value)}"
                    )
            else:
                # Direct execution when not tracing
                self._df = self._df.with_columns(expr.alias(key))
                if self._verbose:
                    self._operation_log.append(
                        f"Set column '{key}' = {self._expr_to_str(value)}"
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

            # Apply captured operations
            df = self._df
            for op_type, *op_args in operations:
                if op_type == "column":
                    col_name, expr = op_args
                    df = df.with_columns(expr.alias(col_name))
                elif op_type == "table_lookup":
                    table_name = op_args[0]
                    # For table lookups, we need to materialize the DataFrame
                    df_materialized = df.collect()

                    # Perform the lookup (using batching if enabled)
                    if self._batch_enabled:
                        result_df = self._batch_lookup(table_name, df_materialized)
                    else:
                        result_df = table_registry.py_lookup(
                            table_name, df_materialized
                        )

                    # Convert back to lazy DataFrame to preserve laziness in further operations
                    df = result_df.lazy()
                elif op_type == "register_table":
                    table_name, key_spec = op_args
                    # Materialize the DataFrame for registration
                    df_materialized = df.collect()

                    # Register the table
                    table_registry.py_register_table(
                        table_name, df_materialized, key_spec
                    )

                    # No need to update df since this operation doesn't modify the DataFrame
                elif op_type == "register_table_transform":
                    table_name, key_spec, transform_spec = op_args
                    # Materialize the DataFrame for registration
                    df_materialized = df.collect()

                    # Register the table with transform
                    table_registry.py_register_table_with_transform(
                        table_name, df_materialized, key_spec, transform_spec
                    )

                    # No need to update df since this operation doesn't modify the DataFrame

            self._df = df
            return result

        return wrapper

    def collect(self):
        """Execute and materialize the dataframe"""
        if self._threads > 0:
            # Set thread count if specified
            return self._df.collect(n_threads=self._threads)
        return self._df.collect()

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

    @staticmethod
    def create_key_spec(
        source_cols: Union[str, List[str]],
        table_cols: Optional[Union[str, List[str]]] = None,
    ) -> table_registry.KeySpec:
        """
        Create a KeySpec for table registry operations.

        Args:
            source_cols: Column name(s) in the source dataframe
            table_cols: Column name(s) in the table dataframe (defaults to source_cols if None)

        Returns:
            KeySpec object ready for registry operations
        """
        # Convert single column name to list
        if isinstance(source_cols, str):
            source_cols = [source_cols]

        # If table_cols not provided, use same as source_cols
        if table_cols is None:
            table_cols = source_cols
        elif isinstance(table_cols, str):
            table_cols = [table_cols]

        return table_registry.KeySpec(source_cols=source_cols, table_cols=table_cols)

    @staticmethod
    def create_transform_spec(
        id_vars: List[str], value_vars: List[str], var_name: str, value_name: str
    ) -> table_registry.TransformSpec:
        """
        Create a TransformSpec for wide-to-long transformations.

        Args:
            id_vars: Columns to keep as identifiers
            value_vars: Columns to unpivot (wide format columns)
            var_name: Name for the column that will contain the unpivoted column names
            value_name: Name for the column that will contain the values

        Returns:
            TransformSpec object ready for registry operations
        """
        return table_registry.TransformSpec(
            id_vars=id_vars,
            value_vars=value_vars,
            var_name=var_name,
            value_name=value_name,
        )

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

    def _batch_lookup(
        self, table_name: str, df_materialized: pl.DataFrame
    ) -> pl.DataFrame:
        """
        Perform table lookup in batches to reduce memory usage.

        Args:
            table_name: Name of the table to lookup
            df_materialized: Materialized dataframe to process

        Returns:
            Result dataframe with looked up values
        """
        if not self._batch_enabled or len(df_materialized) <= self._batch_size:
            # If batching is not enabled or dataframe is smaller than batch size,
            # perform the lookup directly
            return table_registry.py_lookup(table_name, df_materialized)

        # Process in batches
        if self._verbose:
            log.info(
                f"Performing batched lookup on {len(df_materialized)} rows with batch size {self._batch_size}"
            )

        result_dfs = []
        for i in range(0, len(df_materialized), self._batch_size):
            # Extract batch
            batch = df_materialized.slice(
                i, min(self._batch_size, len(df_materialized) - i)
            )

            # Perform lookup on batch
            batch_result = table_registry.py_lookup(table_name, batch)

            # Add to results
            result_dfs.append(batch_result)

        # Combine all batches
        return pl.concat(result_dfs)

    def lookup_table(self, table_name: str) -> "ActuarialFrame":
        """
        Lookup values from a registered table using the table registry.

        Args:
            table_name: Name of the registered table to lookup against current frame

        Returns:
            ActuarialFrame with looked up values merged in
        """
        if self._tracing:
            # When inside a traced function, register the operation
            self._computation_graph.append(("table_lookup", table_name))
            if self._verbose:
                self._operation_log.append(f"Lookup values from table '{table_name}'")
            return self
        else:
            # Direct execution when not tracing
            # We need to materialize the DataFrame for lookup
            df_materialized = self._df.collect()

            # Perform the lookup (using batching if enabled)
            if self._batch_enabled:
                result_df = self._batch_lookup(table_name, df_materialized)
            else:
                result_df = table_registry.py_lookup(table_name, df_materialized)

            # Create a new ActuarialFrame with the result
            result_frame = ActuarialFrame(
                result_df.lazy(),
                mode=self._mode,
                verbose=self._verbose,
                threads=self._threads,
            )

            # Copy batch settings
            result_frame._batch_enabled = self._batch_enabled
            result_frame._batch_size = self._batch_size

            # Copy operation log to maintain history
            result_frame._operation_log = self._operation_log.copy()
            if self._verbose:
                result_frame._operation_log.append(
                    f"Lookup values from table '{table_name}'"
                )

            return result_frame

    def lookup_table_vector(
        self, table_name: str, batch_size: Optional[int] = None
    ) -> "ActuarialFrame":
        """
        Lookup values from a registered table with support for vector/list columns.
        """
        if self._tracing:
            # When inside a traced function, register the operation
            self._computation_graph.append(("table_lookup_vector", table_name))
            if self._verbose:
                self._operation_log.append(f"Vector lookup from table '{table_name}'")
            return self

        # Get materialized DataFrame
        df_materialized = self._df.collect()

        # Perform the lookup (using batching if enabled)
        if batch_size:
            result_df = self._batch_lookup_vector(
                table_name, df_materialized, batch_size
            )
        else:
            # Use the Rust implementation directly
            result_df = table_registry.py_lookup_vector(table_name, df_materialized)

        # Create new ActuarialFrame with the result
        result_frame = ActuarialFrame(
            result_df.lazy(),
            mode=self._mode,
            verbose=self._verbose,
            threads=self._threads,
        )

        # Copy batch settings
        result_frame._batch_enabled = self._batch_enabled
        result_frame._batch_size = self._batch_size

        # Copy operation log
        result_frame._operation_log = self._operation_log.copy()
        if self._verbose:
            result_frame._operation_log.append(
                f"Vector lookup from table '{table_name}'"
            )

        return result_frame

    def register_table(
        self, table_name: str, key_spec: table_registry.KeySpec
    ) -> "ActuarialFrame":
        """
        Register the current frame as a lookup table.

        Args:
            table_name: Name to register the table as
            key_spec: KeySpec defining the key columns

        Returns:
            Self for method chaining
        """
        if self._tracing:
            # When inside a traced function, register the operation
            self._computation_graph.append(("register_table", table_name, key_spec))
            if self._verbose:
                self._operation_log.append(f"Register table '{table_name}'")
        else:
            # Direct execution when not tracing
            # We need to materialize the DataFrame for registration
            df_materialized = self._df.collect()

            # Register the table
            table_registry.py_register_table(table_name, df_materialized, key_spec)

            if self._verbose:
                self._operation_log.append(f"Register table '{table_name}'")

        return self

    def register_table_with_transform(
        self,
        table_name: str,
        key_spec: table_registry.KeySpec,
        transform_spec: table_registry.TransformSpec,
    ) -> "ActuarialFrame":
        """
        Register the current frame as a lookup table with transformation.

        Args:
            table_name: Name to register the table as
            key_spec: KeySpec defining the key columns
            transform_spec: TransformSpec defining how to transform the table

        Returns:
            Self for method chaining
        """
        if self._tracing:
            # When inside a traced function, register the operation
            self._computation_graph.append(
                ("register_table_transform", table_name, key_spec, transform_spec)
            )
            if self._verbose:
                self._operation_log.append(
                    f"Register table with transform '{table_name}'"
                )
        else:
            # Direct execution when not tracing
            # We need to materialize the DataFrame for registration
            df_materialized = self._df.collect()

            # Register the table with transform
            table_registry.py_register_table_with_transform(
                table_name, df_materialized, key_spec, transform_spec
            )

            if self._verbose:
                self._operation_log.append(
                    f"Register table with transform '{table_name}'"
                )

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
