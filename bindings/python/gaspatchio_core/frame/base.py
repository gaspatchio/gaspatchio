from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np
import polars as pl

# Import types
from gaspatchio_core.typing import IntoExprColumn

# ADDED: Import function wrappers
from .. import functions as gp_funcs

# Import proxies
from ..column import ColumnProxy, ExpressionProxy

# Import error handling
from ..errors import _handle_execution_error

# ADDED: Import registry
from ..frame.registry import _ACCESSOR_REGISTRY

# Import utilities
from ..util import get_default_mode, get_default_verbose

# ADDED: Import tracing components
from .tracing import append_operation_to_graph, build_trace_decorator

if TYPE_CHECKING:
    # Keep TYPE_CHECKING block for potential future forward refs if needed
    from typing import Callable  # For trace method signature

    # Add forward references for accessors used in type hints
    from ..accessors.date import DateFrameAccessor
    from ..accessors.finance import FinanceFrameAccessor


# TODO: Move _DEFAULT_THREADS to util? For now, define locally or assume 0.
_DEFAULT_THREADS = 0


class ActuarialFrame:
    """A DataFrame wrapper focusing on core DSL operations."""

    # ADDED: Accessor instance caches
    _date_accessor_instance: Optional["DateFrameAccessor"] = None
    _finance_accessor_instance: Optional["FinanceFrameAccessor"] = None

    def __init__(self, data=None, mode=None, verbose=None, threads=None):
        self._df: pl.LazyFrame | None = None
        self._column_order: List[str] = []
        self._schema: Dict[str, pl.DataType] | None = None

        self._mode = mode if mode is not None else get_default_mode()
        self._verbose = verbose if verbose is not None else get_default_verbose()
        # Placeholder for threads, actual configuration might happen elsewhere or be removed
        self._threads = threads if threads is not None else _DEFAULT_THREADS

        # ADDED: Initialize tracing attributes
        self._computation_graph: list[tuple[str, Any]] = []
        self._tracing: bool = False

        # Excluded context, _operation_log
        self._show_query_plan = False  # Keep this simple flag

        if isinstance(data, pl.LazyFrame):
            self._df = data
            self._schema = self._df.schema
            self._column_order = list(self._schema.keys())
        elif isinstance(data, pl.DataFrame):
            self._df = data.lazy()
            self._schema = self._df.schema
            self._column_order = list(self._schema.keys())
        elif isinstance(data, dict):
            self._df = pl.LazyFrame(data)
            self._schema = self._df.schema
            self._column_order = list(self._schema.keys())
        elif data is not None:
            raise TypeError("Data must be a Polars DataFrame, LazyFrame, or dictionary")

    # Excluded accessor properties (.date, .finance)

    def __getitem__(self, key: str) -> ColumnProxy:
        """Allow df['column'] access, returning a ColumnProxy."""
        if isinstance(key, str):
            # Basic proxy creation, no strict checking here for now
            return ColumnProxy(key, self)
        raise TypeError(f"Indexing with {type(key)} is not supported, use strings.")

    def __setitem__(self, key: str, value: Any):
        """Handle column assignment using df['column'] = value."""
        if key not in self._column_order:
            self._column_order.append(key)
        try:
            expr = self._convert_to_expr(value)

            # MODIFIED: Integrate tracing
            if self._tracing:
                append_operation_to_graph(self, key, expr)
                # Don't execute the operation yet in tracing mode
            else:
                # Execute directly if not tracing
                self._df = self._df.with_columns(expr.alias(key))

            # Basic logging if needed, removed verbose _operation_log
            # if self._verbose: print(f"Set column '{key}'")
        except Exception as e:
            # Use basic error re-raising, detailed handling is in _handle_execution_error
            raise type(e)(
                f"Error setting column '{key}': {str(e)}. "
                f"Value type: {type(value).__name__}"
            ) from e
        # No return self needed for __setitem__

    # ADDED: __dir__ method for basic introspection (can be enhanced later)
    def __dir__(self):
        """Provide basic list of attributes."""
        standard_attrs = set(object.__dir__(self))
        standard_attrs.update(dir(type(self)))
        try:
            column_attrs = set(self._df.columns)
        except Exception:
            column_attrs = set(self._column_order)
        # Exclude dynamic accessors for now
        return sorted(list(standard_attrs | column_attrs))

    def _expr_to_str(self, value):
        """Convert an expression to a readable string (simplified)."""
        if isinstance(value, ColumnProxy):
            return f"col('{value.name}')"
        elif isinstance(value, ExpressionProxy):
            # Attempt to represent the inner expression
            try:
                return str(value._expr)
            except Exception:
                return "ExpressionProxy(...)"
        elif isinstance(value, pl.Expr):
            return str(value)
        elif callable(value):
            return f"Function[{getattr(value, '__name__', 'anonymous')}]"
        else:
            return repr(value)

    def _convert_to_expr(self, value: Any) -> pl.Expr:
        """Convert a value to a Polars expression."""
        if isinstance(value, ColumnProxy):
            return pl.col(value.name)
        elif isinstance(value, ExpressionProxy):
            return value._expr
        elif isinstance(value, pl.Expr):
            return value
        elif isinstance(value, str):
            # Treat strings as column names by default in this context
            return pl.col(value)
        # Keep handling for numpy arrays if needed, otherwise remove
        elif isinstance(value, np.ndarray):
            return pl.lit(value)
        else:
            # Convert other types to literal
            return pl.lit(value)

    # Excluded: _log_query_plan (now in tracing.py)

    def show_query_plan(self, enabled: bool = True) -> ActuarialFrame:
        """Enable or disable query plan logging (basic implementation)."""
        # In this base version, it might just control a simple print in collect/profile
        # The actual logging is handled by log_query_plan in tracing.py when operations are applied
        self._show_query_plan = enabled  # Keep flag for potential other uses
        print(
            f"Query plan logging {'enabled' if enabled else 'disabled'} (via trace decorator)."
        )  # Basic feedback
        return self

    # ADDED: trace decorator method
    def trace(self, func: Callable) -> Callable:
        """Decorator to capture operations within a function call in optimize mode."""
        return build_trace_decorator(self)(func)

    def collect(self) -> pl.DataFrame:
        """Execute and materialize the dataframe."""
        # Query plan logging is now handled by the trace decorator/log_query_plan
        # if self._show_query_plan and self._df is not None:
        #     ...

        try:
            if self._df is None:
                return pl.DataFrame()  # Return empty if no data
            # Simplified thread handling
            return self._df.collect()
        except Exception as e:
            _handle_execution_error(self, e)  # Will re-raise or format

    def profile(self) -> pl.DataFrame:
        """Execute and materialize the dataframe with profiling."""
        # Query plan logging is handled by trace decorator
        # if self._show_query_plan and self._df is not None:
        #    ...

        try:
            if self._df is None:
                return pl.DataFrame()  # Return empty if no data
            # Polars profile() works on LazyFrames, no need to collect first
            # However, the exact behavior and output might need verification
            print("Running Polars profile()...")
            profile_df = self._df.profile()  # Returns a DataFrame with profile info
            # The profile_df itself might not be what the user expects back.
            # Typically, you collect *after* profiling the lazy operations.
            # Let's clarify the intent: Profile the execution *of* collect?
            # Or just get the profile info *about* the lazy frame?
            # For now, return the profile info DataFrame, but log a warning.
            print(
                "Warning: profile() returns profiling information, not the computed data. "
                "Call collect() separately if you need the results."
            )
            return profile_df
        except Exception as e:
            _handle_execution_error(self, e)  # Will re-raise or format

    # Excluded: optimize, get_operation_log, get_execution_stats

    def with_columns(self, *exprs: IntoExprColumn) -> ActuarialFrame:
        """Add columns to the DataFrame."""
        if self._df is None:
            raise ValueError("Cannot add columns to an uninitialized ActuarialFrame.")

        try:
            converted_exprs_dict = {}
            new_cols_order = []
            for e in exprs:
                polars_expr = self._convert_to_expr(e)
                # Attempt to get output name for tracing and column order update
                try:
                    output_name = polars_expr.meta.output_name()
                except Exception:
                    # Fallback if name cannot be determined (e.g., literal) - needs careful handling
                    # For now, we might skip tracing unnamed expressions or require explicit naming/alias
                    # Let's assume expressions added via with_columns must have names for tracing
                    raise ValueError(
                        f"Could not determine output name for expression: {polars_expr}. Use .alias()"
                    )

                converted_exprs_dict[output_name] = polars_expr
                if output_name not in self._column_order:
                    new_cols_order.append(output_name)

            # Integrate tracing
            if self._tracing:
                for name, expr in converted_exprs_dict.items():
                    append_operation_to_graph(self, name, expr)
                # Don't execute, just update potential column order
                self._column_order.extend(new_cols_order)
            else:
                # Execute directly
                self._df = self._df.with_columns(**converted_exprs_dict)
                self._schema = self._df.schema  # Update schema after execution
                self._column_order.extend(new_cols_order)

        except Exception as e:
            raise type(e)(f"Error adding columns: {e}") from e
        return self

    def pipe(
        self, func: Callable[..., ActuarialFrame | None], *args: Any, **kwargs: Any
    ) -> ActuarialFrame:
        """Apply a function that accepts and returns an ActuarialFrame."""
        # Tracing should ideally happen *inside* the piped function if it uses frame ops
        # The pipe itself doesn't introduce new traceable operations at this level
        result = func(self, *args, **kwargs)
        if result is not None and not isinstance(result, ActuarialFrame):
            raise TypeError(
                f"Pipe function must return an ActuarialFrame or None, got {type(result)}"
            )
        return result if result is not None else self

    # Excluded: Core function wrappers (fill_series, floor, round, etc.)
    # ADDED: Core function wrapper methods
    def fill_series(
        self,
        column: IntoExprColumn,
        limit: int,
    ) -> ExpressionProxy:
        """Apply fill_series using the core function."""
        expr = self._convert_to_expr(column)
        # Assuming gp_funcs.fill_series returns a Polars Expression
        result_expr = gp_funcs.fill_series(expr, limit=limit)
        return ExpressionProxy(result_expr, self)

    def floor(self, column: IntoExprColumn, divisor: float = 1.0) -> ExpressionProxy:
        """Apply floor using the core function."""
        expr = self._convert_to_expr(column)
        result_expr = gp_funcs.floor(expr, divisor=divisor)
        return ExpressionProxy(result_expr, self)

    def round(self, column: IntoExprColumn, decimals: int = 0) -> ExpressionProxy:
        """Apply round using the core function."""
        expr = self._convert_to_expr(column)
        result_expr = gp_funcs.round(expr, decimals=decimals)
        return ExpressionProxy(result_expr, self)

    def round_to_int(
        self, column: IntoExprColumn, strategy: str = "nearest"
    ) -> ExpressionProxy:
        """Apply round_to_int using the core function."""
        expr = self._convert_to_expr(column)
        result_expr = gp_funcs.round_to_int(expr, strategy=strategy)
        return ExpressionProxy(result_expr, self)

    def get_column_order(self) -> List[str]:
        """Return the tracked order of columns."""
        # Try to get from schema if available and frame exists, otherwise use tracked order
        if self._df is not None and self._schema:
            # Schema might not reflect additions made during tracing until collect
            # Return the manually tracked order for consistency during tracing
            # return list(self._schema.keys())
            pass
        return self._column_order

    # Internal helper methods like _find_similar_columns belong with error handling

    # --- Accessor Properties ---
    # ADDED: Dynamic property for 'date' frame accessor
    @property
    def date(self) -> "DateFrameAccessor":
        """Access date-related frame operations."""
        if self._date_accessor_instance is None:
            # Look up specifically for 'frame' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("frame")
            if not AccessorClass:
                raise AttributeError(
                    "No 'date' frame accessor registered or kind mismatch."
                )
            # Use the class retrieved from the registry
            self._date_accessor_instance = AccessorClass(self)
        return self._date_accessor_instance

    # ADDED: Dynamic property for 'finance' frame accessor
    @property
    def finance(self) -> "FinanceFrameAccessor":
        """Access finance-related frame operations."""
        if self._finance_accessor_instance is None:
            # Look up specifically for 'frame' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("frame")
            if not AccessorClass:
                raise AttributeError(
                    "No 'finance' frame accessor registered or kind mismatch."
                )
            # Use the class retrieved from the registry
            self._finance_accessor_instance = AccessorClass(self)
        return self._finance_accessor_instance

    # --- Dunder Methods ---

    def __dir__(self) -> List[str]:
        """Enhance dir() output to include standard methods, df methods, and accessors."""
        standard_attrs = list(super().__dir__())
        # Add methods from the underlying LazyFrame if available
        df_methods = []
        if hasattr(self, "_df") and self._df is not None:
            df_methods = [
                attr
                for attr in dir(self._df)
                if not attr.startswith("_") and callable(getattr(self._df, attr))
            ]

        # Include registered frame accessors by checking the nested dict
        accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "frame" in kinds
        ]

        return sorted(list(set(standard_attrs + df_methods + accessor_names)))

    def __repr__(self) -> str:
        """Return a string representation of the ActuarialFrame."""
        # TODO: Implement this method
        pass


# Any helper classes previously nested in ActuarialFrame should be moved too if they existed
