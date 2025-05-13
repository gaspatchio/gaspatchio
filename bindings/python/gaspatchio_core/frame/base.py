from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import numpy as np
import polars as pl

# Import types
from gaspatchio_core.typing import IntoExprColumn

# Import proxies
from ..column import ColumnProxy, ExpressionProxy

# Import error handling
from ..errors import _handle_execution_error

# ADDED: Import registry
from ..frame.registry import _ACCESSOR_REGISTRY

# ADDED: Import function wrappers from the correct module
from ..functions import vector as gp_funcs

# Import telemetry for apply/map warnings
# Import utilities
from ..util import get_default_mode, get_default_verbose

# ADDED: Import tracing components
from .tracing import append_operation_to_graph, build_trace_decorator

if TYPE_CHECKING:
    # Keep TYPE_CHECKING block for potential future forward refs if needed
    from typing import Callable  # For trace method signature

    # Add forward references for accessors used in type hints
    from ..accessors.date import DateFrameAccessor
    from ..accessors.excel import ExcelFrameAccessor
    from ..accessors.finance import FinanceFrameAccessor


# TODO: Move _DEFAULT_THREADS to util? For now, define locally or assume 0.
_DEFAULT_THREADS = 0


class ActuarialFrame:
    """A lazy, chainable, and traceable DataFrame for actuarial modeling.

    The ActuarialFrame provides a high-level API for common actuarial
    calculations and data manipulations, leveraging Polars LazyFrames for
    performance. It supports tracing of operations for optimization and
    introspection, and provides convenient accessors for specialized
    functionality (e.g., date, finance, excel operations).

    Args:
        data (dict | polars.DataFrame | polars.LazyFrame | None, optional): Initial data to populate the frame.
            Can be a Python dictionary, a Polars DataFrame, or a Polars LazyFrame.
            If None, an empty frame is initialized. Defaults to None.
        mode (str | None, optional): The operational mode: "run", "optimize", or "debug".
            - "run": Executes operations eagerly.
            - "optimize": Defers execution and builds a computation graph.
            - "debug": Provides more verbose output.
            Defaults to the global default mode (`get_default_mode`).
        verbose (bool | None, optional): Enables or disables verbose logging.
            Defaults to the global default verbosity (`get_default_verbose`).
        threads (int | None, optional): Number of threads for parallel operations.
            Defaults to a system-dependent value or `_DEFAULT_THREADS`.

    Attributes:
        date (DateFrameAccessor): Accessor for date-related operations.
        excel (ExcelFrameAccessor): Accessor for Excel-like operations.
        finance (FinanceFrameAccessor): Accessor for financial calculations.
        columns (list[str]): A list of column names in their current order.

    Examples:
        **Initialization and Basic Operations**

        >>> from gaspatchio_core import ActuarialFrame
        >>> data = {
        ...     "policy_id": [1, 1, 2, 2, 3],
        ...     "inception_date": ["2020-01-01", "2020-01-01", "2021-05-10", "2021-05-10", "2022-02-20"],
        ...     "premium": [100, 150, 200, 50, 300],
        ...     "claims": [0, 50, 10, 0, 120]
        ... }
        >>> af = ActuarialFrame(data)
        >>> af["loss_ratio"] = af["claims"] / af["premium"]
        >>> result = af.collect()
        >>> print(result.head(3))
        shape: (3, 5)
        ┌───────────┬────────────────┬─────────┬────────┬────────────┐
        │ policy_id ┆ inception_date ┆ premium ┆ claims ┆ loss_ratio │
        │ ---       ┆ ---            ┆ ---     ┆ ---    ┆ ---        │
        │ i64       ┆ str            ┆ i64     ┆ i64    ┆ f64        │
        ╞═══════════╪════════════════╪═════════╪════════╪════════════╡
        │ 1         ┆ 2020-01-01     ┆ 100     ┆ 0      ┆ 0.0        │
        │ 1         ┆ 2020-01-01     ┆ 150     ┆ 50     ┆ 0.333333   │
        │ 2         ┆ 2021-05-10     ┆ 200     ┆ 10     ┆ 0.05       │
        └───────────┴────────────────┴─────────┴────────┴────────────┘

        **Using `sum` over a group**

        >>> af = ActuarialFrame(data)
        >>> af["total_premium_per_policy"] = af["premium"].sum().over("policy_id")
        >>> result_with_sum = af.collect()
        >>> print(result_with_sum)
        shape: (5, 5)
        ┌───────────┬────────────────┬─────────┬────────┬──────────────────────────┐
        │ policy_id ┆ inception_date ┆ premium ┆ claims ┆ total_premium_per_policy │
        │ ---       ┆ ---            ┆ ---     ┆ ---    ┆ ---                      │
        │ i64       ┆ str            ┆ i64     ┆ i64    ┆ i64                      │
        ╞═══════════╪════════════════╪═════════╪════════╪══════════════════════════╡
        │ 1         ┆ 2020-01-01     ┆ 100     ┆ 0      ┆ 250                      │
        │ 1         ┆ 2020-01-01     ┆ 150     ┆ 50     ┆ 250                      │
        │ 2         ┆ 2021-05-10     ┆ 200     ┆ 10     ┆ 250                      │
        │ 2         ┆ 2021-05-10     ┆ 50      ┆ 0      ┆ 250                      │
        │ 3         ┆ 2022-02-20     ┆ 300     ┆ 120    ┆ 300                      │
        └───────────┴────────────────┴─────────┴────────┴──────────────────────────┘

        **Using an accessor (e.g., date accessor)**

        Assume 'inception_date' needs to be parsed to a date type first.
        For simplicity, let's imagine it's already a date type for this example.
        (Actual parsing would use `af["inception_date"].str.to_date("%Y-%m-%d")` or similar)

        >>> # If 'inception_date' was a date type:
        >>> # af["inception_year"] = af.date.year("inception_date")
        >>> # af_with_year = af.collect()
        >>> # print(af_with_year.select(["policy_id", "inception_year"]))

    """

    # ADDED: Accessor instance caches
    _date_accessor_instance: Optional["DateFrameAccessor"] = None
    _excel_accessor_instance: Optional["ExcelFrameAccessor"] = None
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
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
        elif isinstance(data, pl.DataFrame):
            self._df = data.lazy()
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
        elif isinstance(data, dict):
            self._df = pl.LazyFrame(data)
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
        elif data is not None:
            raise TypeError("Data must be a Polars DataFrame, LazyFrame, or dictionary")

    # Excluded accessor properties (.date, .finance)

    def __getitem__(self, key: str) -> ColumnProxy:
        """Allow df['column'] access, returning a ColumnProxy."""
        if isinstance(key, str):
            # Basic proxy creation, no strict checking here for now
            return ColumnProxy(key, self)
        else:
            raise TypeError(
                f"ActuarialFrame indices must be strings, not {type(key).__name__}"
            )

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
            # Treat strings as literals in this general conversion context
            return pl.lit(value)
        # Keep handling for numpy arrays if needed, otherwise remove
        elif isinstance(value, np.ndarray):
            return pl.lit(value)
        else:
            # Default to literal for unsupported types
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
        try:
            if self._df is None:
                # Ensure an empty schema matching Polars behavior for empty LazyFrame.collect()
                return pl.DataFrame(schema={})

            final_df = self._df
            # Apply computation graph if it exists (typically built in optimize mode via tracing)
            if self._computation_graph:
                # The trace decorator might have already logged the plan if verbose
                # but repeating here or having a more structured way to log before collect is fine.
                if self._show_query_plan:
                    from .tracing import (
                        log_query_plan,  # Local import to avoid circularity at module level
                    )

                    log_query_plan(
                        self._computation_graph, final_df
                    )  # Log before applying

                for name, expr_val in self._computation_graph:
                    # Ensure expr_val is a polars expression. _convert_to_expr should handle this
                    # during __setitem__ or with_columns before it gets into the graph.
                    final_df = final_df.with_columns(expr_val.alias(name))

                # Optionally clear the graph after applying, though the tracer resets it per call.
                # self._computation_graph = []

            return final_df.collect()
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

    # Excluded: optimize, get_execution_stats

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
                self._schema = self._df.collect_schema()
                self._column_order.extend(new_cols_order)

        except Exception as e:
            raise type(e)(f"Error adding columns: {e}") from e
        return self

    def select(
        self, *exprs: IntoExprColumn, **named_exprs: IntoExprColumn
    ) -> ActuarialFrame:
        """Select columns from the DataFrame.

        Accepts positional expressions (column names, proxies, or expressions) and
        keyword arguments for renamed/new expressions.

        Args:
            *exprs: Columns or expressions to select.
            **named_exprs: Expressions to select with specific output names.

        Returns:
            The modified ActuarialFrame.
        """
        if self._df is None:
            raise ValueError(
                "Cannot select columns from an uninitialized ActuarialFrame."
            )

        try:
            # Convert positional and keyword arguments to Polars expressions
            converted_positional = [self._convert_to_expr(e) for e in exprs]
            converted_named = {
                name: self._convert_to_expr(e) for name, e in named_exprs.items()
            }

            # Combine positional and named arguments for the underlying select
            all_exprs_to_select = converted_positional + [
                expr.alias(name) for name, expr in converted_named.items()
            ]

            # TODO: Add tracing logic here if needed for select operation
            # if self._tracing:
            #     ... Record selection ...
            # else:

            # Call underlying Polars select
            self._df = self._df.select(all_exprs_to_select)

            # Update schema and column order AFTER execution
            # This might be expensive; consider lazy update or collect_schema()
            self._schema = self._df.collect_schema()
            # Reconstruct column order based on the *new* schema from select
            self._column_order = list(self._schema.keys())

        except Exception as e:
            raise type(e)(f"Error selecting columns: {e}") from e
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
        start: int = 0,
        increment: int = 1,
    ) -> ExpressionProxy:
        """Apply fill_series using the core function."""
        expr = self._convert_to_expr(column)
        result_expr = gp_funcs.fill_series(expr, start=start, increment=increment)
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

    @property
    def excel(self) -> "ExcelFrameAccessor":
        """Access excel-related frame operations."""
        if self._excel_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("excel", {}).get("frame")
            if not AccessorClass:
                raise AttributeError(
                    "No 'excel' frame accessor registered or kind mismatch."
                )
            self._excel_accessor_instance = AccessorClass(self)
        return self._excel_accessor_instance

    def __getattr__(self, name: str) -> Any:
        """Dynamically instantiate and return registered frame accessors."""
        # REVERT: Check registry for nested dict entry
        kind_dict = _ACCESSOR_REGISTRY.get(name)

        if kind_dict:
            AccessorClass = kind_dict.get("frame")
            if AccessorClass:
                # Instantiate the accessor, passing the frame instance
                accessor_instance = AccessorClass(self)
                # Cache the instance on the object itself
                setattr(self, name, accessor_instance)
                return accessor_instance
            else:
                # Found name, but not 'frame' kind
                raise AttributeError(f"Accessor '{name}' is not a frame accessor.")
        else:
            # Did not find name in registry
            # Fallback to standard attribute error
            raise AttributeError(
                f"No '{name}' frame accessor registered or attribute found."
            )

    # --- Dunder Methods ---

    # ADDED: columns property
    @property
    def columns(self) -> List[str]:
        """Return the names of the columns in the current order."""
        # Use the explicitly tracked order, as the underlying LazyFrame schema
        # might not reflect changes made via assign/with_columns until collect.
        # if self._df is not None:
        #     try:
        #         # Note: .columns on LazyFrame is okay, schema resolution is the expensive part
        #         return self._df.columns
        #     except Exception:
        #         pass # Fallback to tracked order if error
        return self._column_order

    def __dir__(self) -> List[str]:
        """Enhance dir() output to include standard methods, df methods, and accessors."""
        standard_attrs = list(
            super().__dir__()
        )  # Use object.__dir__(self) or similar if needed
        # Add methods from the underlying LazyFrame if available
        df_methods = []
        if hasattr(self, "_df") and self._df is not None:
            try:
                df_methods = [
                    attr
                    for attr in dir(self._df)
                    if not attr.startswith("_")  # and callable(getattr(self._df, attr))
                ]
            except Exception:
                df_methods = []  # Ignore errors if _df is weird

        # REVERT: Include registered frame accessors based on nested dict structure
        accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "frame" in kinds
        ]

        return sorted(list(set(standard_attrs + df_methods + accessor_names)))

    def __repr__(self) -> str:
        """Return a string representation of the ActuarialFrame."""
        if self._df is None:
            return "ActuarialFrame(uninitialized)"

        try:
            schema = self._df.collect_schema()
            num_cols = len(schema)
            shape_info = f"shape: ({num_cols} columns)"

            # For better representation, show a sample of columns
            cols_preview = ", ".join(self._column_order[:5])
            if len(self._column_order) > 5:
                cols_preview += ", ..."

            mode_info = f"mode: {self._mode}"

            return f"ActuarialFrame({shape_info}, cols: [{cols_preview}], {mode_info})"
        except Exception:
            # Fallback if we can't calculate schema
            return (
                f"ActuarialFrame(cols: {len(self._column_order)}, mode: {self._mode})"
            )
