# ABOUTME: Core ActuarialFrame implementation for actuarial modeling
# ABOUTME: Main DataFrame wrapper with computation graph and tracing support
# ruff: noqa: D100, TC001, TD002, TD003, FIX002, ANN204, ANN401, E501, PLR0913, C901, PLR0912, PLR0915, ANN001, ANN201, D102, D101, SLF001, TID252, D107, TRY003, EM101, EM102, ERA001, ANN202, PGH003, BLE001, FBT001, FBT002, T201, D401, TRY300, B904, N806, D301, RET503, S110, C414, SIM118, PLR2004
# type: ignore[return-value, attr-defined, arg-type, assignment, override, misc]
"""Core ActuarialFrame implementation for actuarial modeling."""

from __future__ import annotations

import keyword
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl
from loguru import logger

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
from .tracing import (
    append_operation_to_graph,
    build_trace_decorator,
)

if TYPE_CHECKING:
    # Keep TYPE_CHECKING block for potential future forward refs if needed
    from collections.abc import Callable  # For trace method signature

    # Add forward references for accessors used in type hints
    from ..accessors.date import DateFrameAccessor
    from ..accessors.excel import ExcelFrameAccessor
    from ..accessors.finance import FinanceFrameAccessor

    # Import TracedOperation for type hints
    from ..errors.metadata import TracedOperation


# TODO: Move _DEFAULT_THREADS to util? For now, define locally or assume 0.
_DEFAULT_THREADS = 0


class _AggregationResult:
    """Base class for aggregation results that provides convenient scalar access."""

    def __init__(self, df: pl.DataFrame):
        self._df = df

    def __getitem__(self, key: str) -> Any:
        """Return the scalar value directly for convenience."""
        return self._df[key][0]

    def __repr__(self) -> str:
        return repr(self._df)

    def __str__(self) -> str:
        return str(self._df)

    @property
    def to_frame(self) -> pl.DataFrame:
        """Allow access to the underlying DataFrame if needed."""
        return self._df


class MaxResult(_AggregationResult):
    """Result wrapper for max() method that provides convenient scalar access."""


class MinResult(_AggregationResult):
    """Result wrapper for min() method that provides convenient scalar access."""


class MeanResult(_AggregationResult):
    """Result wrapper for mean() method that provides convenient scalar access."""


class StdResult(_AggregationResult):
    """Result wrapper for std() method that provides convenient scalar access."""


class VarResult(_AggregationResult):
    """Result wrapper for var() method that provides convenient scalar access."""


class MedianResult(_AggregationResult):
    """Result wrapper for median() method that provides convenient scalar access."""


class SumResult(_AggregationResult):
    """Result wrapper for sum() method that provides convenient scalar access."""


class CountResult(_AggregationResult):
    """Result wrapper for count() method that provides convenient scalar access."""


class ProductResult(_AggregationResult):
    """Result wrapper for product() method that provides convenient scalar access."""


class QuantileResult(_AggregationResult):
    """Result wrapper for quantile() method that provides convenient scalar access."""


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
        ...     "inception_date": [
        ...         "2020-01-01",
        ...         "2020-01-01",
        ...         "2021-05-10",
        ...         "2021-05-10",
        ...         "2022-02-20",
        ...     ],
        ...     "premium": [100, 150, 200, 50, 300],
        ...     "claims": [0, 50, 10, 0, 120],
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
    _date_accessor_instance: DateFrameAccessor | None = None
    _excel_accessor_instance: ExcelFrameAccessor | None = None
    _finance_accessor_instance: FinanceFrameAccessor | None = None

    def __init__(self, data=None, mode=None, verbose=None, threads=None):
        self._df: pl.LazyFrame | None = None
        self._column_order: list[str] = []
        # Maintain a fast set of attribute-eligible column names
        self._attr_columns_set: set[str] = set()
        self._schema: dict[str, pl.DataType] | None = None

        self._mode = mode if mode is not None else get_default_mode()
        self._verbose = verbose if verbose is not None else get_default_verbose()
        # Placeholder for threads, actual configuration might happen elsewhere or be removed
        self._threads = threads if threads is not None else _DEFAULT_THREADS

        # ADDED: Initialize tracing attributes
        # Support both legacy tuple format and new TracedOperation format for backward compatibility
        self._computation_graph: list[tuple[str, Any] | TracedOperation] = []
        self._tracing: bool = False

        # Excluded context, _operation_log
        self._show_query_plan = False  # Keep this simple flag

        if isinstance(data, pl.LazyFrame):
            self._df = data
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
            self._refresh_attr_columns_set()
        elif isinstance(data, pl.DataFrame):
            self._df = data.lazy()
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
            self._refresh_attr_columns_set()
        elif isinstance(data, dict):
            self._df = pl.LazyFrame(data)
            self._schema = self._df.collect_schema()
            self._column_order = list(self._schema.keys())
            self._refresh_attr_columns_set()
        elif data is not None:
            raise TypeError("Data must be a Polars DataFrame, LazyFrame, or dictionary")

    # Excluded accessor properties (.date, .finance)

    def __getitem__(self, key: str) -> ColumnProxy:
        """Allow df['column'] access, returning a ColumnProxy."""
        if isinstance(key, str):
            # Basic proxy creation, no strict checking here for now
            return ColumnProxy(key, self)
        raise TypeError(
            f"ActuarialFrame indices must be strings, not {type(key).__name__}"
        )

    def __setitem__(self, key: str, value: Any):
        """Handle column assignment using df['column'] = value."""
        if key not in self._column_order:
            self._column_order.append(key)
            self._refresh_attr_columns_set()
        try:
            # Check for list broadcast metadata BEFORE converting to expr
            if (
                hasattr(value, "_list_broadcast_metadata")
                and value._list_broadcast_metadata is not None
            ):
                metadata = value._list_broadcast_metadata
                # element_wise: True means expression already handles element-wise ops
                # (e.g., projection accessor using .list.eval())
                if metadata.get("element_wise") and "list_columns" not in metadata:
                    # Just apply expression directly - it handles element-wise already
                    expr = self._convert_to_expr(value)
                    if self._tracing:
                        append_operation_to_graph(self, key, expr)
                        self._df = self._df.with_columns(expr.alias(key))
                    else:
                        self._df = self._df.with_columns(expr.alias(key))
                    return
                self._apply_conditional_list_broadcasting(key, metadata)
                return

            expr = self._convert_to_expr(value)

            # MODIFIED: Integrate tracing
            if self._tracing:
                append_operation_to_graph(self, key, expr)
                # ALSO apply to _df immediately for models that access _df directly
                self._df = self._df.with_columns(expr.alias(key))
            else:
                # Execute directly if not tracing
                self._df = self._df.with_columns(expr.alias(key))

            # Basic logging if needed, removed verbose _operation_log
            # if self._verbose: print(f"Set column '{key}'")
        except Exception as e:
            # Use basic error re-raising, detailed handling is in _handle_execution_error
            raise type(e)(
                f"Error setting column '{key}': {e!s}. "
                f"Value type: {type(value).__name__}"
            ) from e
        # No return self needed for __setitem__

    def _expr_to_str(self, value):
        """Convert an expression to a readable string (simplified)."""
        if isinstance(value, ColumnProxy):
            return f"col('{value.name}')"
        if isinstance(value, ExpressionProxy):
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
        if isinstance(value, ExpressionProxy):
            return value._expr
        if isinstance(value, pl.Expr):
            return value
        if isinstance(value, str):
            # Treat strings as literals in this general conversion context
            return pl.lit(value)
        # Keep handling for numpy arrays if needed, otherwise remove
        if isinstance(value, np.ndarray):
            return pl.lit(value)
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

                for operation in self._computation_graph:
                    # Handle both old tuple format and new TracedOperation format
                    if isinstance(operation, tuple):
                        # Legacy format: (name, expr)
                        name, expr_val = operation
                        final_df = final_df.with_columns(expr_val.alias(name))
                    else:
                        # New format: TracedOperation
                        # Skip if expression is a string (description only, already executed eagerly)
                        # This happens for list broadcasting operations in debug mode
                        if isinstance(operation.expression, str):
                            logger.trace(
                                f"Skipping '{operation.alias}' - already executed eagerly"
                            )
                            continue
                        final_df = final_df.with_columns(
                            operation.expression.alias(operation.alias)
                        )

                # Optionally clear the graph after applying, though the tracer resets it per call.
                # self._computation_graph = []

            return final_df.collect()
        except Exception as e:
            _handle_execution_error(self, e)  # Will re-raise or format

    def profile(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Execute and materialize the dataframe with profiling, returning (result_df, profile_info)."""
        try:
            if self._df is None:
                # Return empty dataframes for both result and profile
                return pl.DataFrame(), pl.DataFrame()

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

                for operation in self._computation_graph:
                    # Handle both old tuple format and new TracedOperation format
                    if isinstance(operation, tuple):
                        # Legacy format: (name, expr)
                        name, expr_val = operation
                        final_df = final_df.with_columns(expr_val.alias(name))
                    else:
                        # New format: TracedOperation
                        # Skip if expression is a string (description only, already executed eagerly)
                        # This happens for list broadcasting operations in debug mode
                        if isinstance(operation.expression, str):
                            logger.trace(
                                f"Skipping '{operation.alias}' - already executed eagerly"
                            )
                            continue
                        final_df = final_df.with_columns(
                            operation.expression.alias(operation.alias)
                        )

                # Optionally clear the graph after applying, though the tracer resets it per call.
                # self._computation_graph = []

            # Use Polars profile to get both result and profile info
            result_df, profile_info = final_df.profile()
            return result_df, profile_info
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
                self._refresh_attr_columns_set()
            else:
                # Execute directly
                self._df = self._df.with_columns(**converted_exprs_dict)
                self._schema = self._df.collect_schema()
                self._column_order.extend(new_cols_order)
                self._refresh_attr_columns_set()

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
            self._refresh_attr_columns_set()

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

    def get_column_order(self) -> list[str]:
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
    def date(self) -> DateFrameAccessor:
        """Access date-related frame operations."""
        if self._date_accessor_instance is None:
            # Look up specifically for 'frame' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("frame")
            if not AccessorClass:
                # Late import to ensure registration if registry was reset in tests
                try:
                    from ..accessors import date as _date_mod  # noqa: F401

                    AccessorClass = _ACCESSOR_REGISTRY.get("date", {}).get("frame")
                except Exception:
                    AccessorClass = None
                if not AccessorClass:
                    # Fallback to direct import of the built-in accessor class
                    try:
                        from ..accessors.date import (
                            DateFrameAccessor as _BuiltInDateAccessor,
                        )

                        AccessorClass = _BuiltInDateAccessor
                    except Exception:
                        raise AttributeError(
                            "No 'date' frame accessor registered or kind mismatch."
                        )
            # Use the class retrieved from the registry
            self._date_accessor_instance = AccessorClass(self)
        return self._date_accessor_instance

    # ADDED: Dynamic property for 'finance' frame accessor
    @property
    def finance(self) -> FinanceFrameAccessor:
        """Access finance-related frame operations."""
        if self._finance_accessor_instance is None:
            # Look up specifically for 'frame' kind using nested dict
            AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("frame")
            if not AccessorClass:
                try:
                    from ..accessors import finance as _finance_mod  # noqa: F401

                    AccessorClass = _ACCESSOR_REGISTRY.get("finance", {}).get("frame")
                except Exception:
                    AccessorClass = None
                if not AccessorClass:
                    try:
                        from ..accessors.finance import (
                            FinanceFrameAccessor as _BuiltInFinanceAccessor,
                        )

                        AccessorClass = _BuiltInFinanceAccessor
                    except Exception:
                        raise AttributeError(
                            "No 'finance' frame accessor registered or kind mismatch."
                        )
            # Use the class retrieved from the registry
            self._finance_accessor_instance = AccessorClass(self)
        return self._finance_accessor_instance

    @property
    def excel(self) -> ExcelFrameAccessor:
        """Access excel-related frame operations."""
        if self._excel_accessor_instance is None:
            AccessorClass = _ACCESSOR_REGISTRY.get("excel", {}).get("frame")
            if not AccessorClass:
                try:
                    from ..accessors import excel as _excel_mod  # noqa: F401

                    AccessorClass = _ACCESSOR_REGISTRY.get("excel", {}).get("frame")
                except Exception:
                    AccessorClass = None
                if not AccessorClass:
                    try:
                        from ..accessors.excel import (
                            ExcelFrameAccessor as _BuiltInExcelAccessor,
                        )

                        AccessorClass = _BuiltInExcelAccessor
                    except Exception:
                        raise AttributeError(
                            "No 'excel' frame accessor registered or kind mismatch."
                        )
            self._excel_accessor_instance = AccessorClass(self)
        return self._excel_accessor_instance

    def max(self):
        """Calculate maximum values across all numeric columns.

        Returns a single-row frame containing the maximum value for each column.
        Essential for identifying outliers, validating data ranges, and determining
        upper bounds in actuarial calculations.

        !!! note "When to use"
            * **Data Validation:** Identify outliers in premium amounts, sum assured,
                or claim values that may require investigation.
            * **Experience Analysis:** Find maximum claim amounts, policy sizes, or
                ages in a portfolio for risk assessment.
            * **Regulatory Reporting:** Determine maximum exposure amounts for
                solvency calculations and stress testing.
            * **Pricing Boundaries:** Identify upper limits for age bands, benefit
                amounts, or policy terms in product design.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing maximum values for each column.

        Examples
        --------
        **Scalar Example: Portfolio Maximum Values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 67, 35],
            "sum_assured": [100000, 500000, 250000, 1000000],
            "annual_premium": [1200, 6000, 8500, 15000],
        }
        af = ActuarialFrame(data)
        max_values = af.max()
        print(max_values)
        print("Max age:", max_values["age"][0])
        print("Max sum assured:", max_values["sum_assured"][0])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────┬─────────────┬────────────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ annual_premium │
        │ ---       ┆ --- ┆ ---         ┆ ---            │
        │ str       ┆ i64 ┆ i64         ┆ i64            │
        ╞═══════════╪═════╪═════════════╪════════════════╡
        │ P004      ┆ 67  ┆ 1000000     ┆ 15000          │
        └───────────┴─────┴─────────────┴────────────────┘
        Max age: 67
        Max sum assured: 1000000
        ```

        **Vector Example: Maximum Monthly Claims**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "policy_year": [1, 2],
            "monthly_claims": [
                [0, 500, 0, 1200, 0, 0, 800, 0, 0, 0, 0, 2500],
                [0, 0, 3000, 0, 0, 1500, 0, 0, 0, 4000, 0, 0]
            ],
            "monthly_premiums": [
                [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000],
                [1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500, 1500]
            ]
        }
        af = ActuarialFrame(data)

        # Get maximum values to understand worst-case scenarios
        max_values = af.max()
        print(max_values)
        print("Max policy year:", max_values["policy_year"][0])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────────────┬─────────────────────────────────────┬─────────────────────────────────────┐
        │ policy_id ┆ policy_year ┆ monthly_claims                      ┆ monthly_premiums                    │
        │ ---       ┆ ---         ┆ ---                                 ┆ ---                                 │
        │ str       ┆ i64         ┆ list[i64]                           ┆ list[i64]                           │
        ╞═══════════╪═════════════╪═════════════════════════════════════╪═════════════════════════════════════╡
        │ P002      ┆ 2           ┆ [0, 500, 3000, 1200, … 4000, 0, 0]  ┆ [1500, 1500, 1500, 1500, … 1500]    │
        └───────────┴─────────────┴─────────────────────────────────────┴─────────────────────────────────────┘
        Max policy year: 2
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute max on an uninitialized ActuarialFrame.")

        # The underlying LazyFrame.max() returns a LazyFrame with one row
        # We collect it here to return an eager DataFrame
        result_df = self._df.max().collect()
        return MaxResult(result_df)

    def min(self):
        """Calculate minimum values across all numeric columns.

        Returns a single-row frame containing the minimum value for each column.
        Essential for identifying baseline values, detecting anomalies, and establishing
        lower bounds in actuarial calculations.

        !!! note "When to use"
            * **Data Quality Checks:** Identify potential data errors like negative
                ages, zero premiums, or missing values coded as extreme minimums.
            * **Portfolio Analysis:** Find minimum entry ages, smallest policy sizes,
                or lowest premium amounts for market segmentation.
            * **Risk Assessment:** Determine minimum coverage levels, deductibles, or
                retention limits in reinsurance analysis.
            * **Product Design:** Establish minimum benefit guarantees, surrender values,
                or contribution limits for new products.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing minimum values for each column.

        Examples
        --------
        **Scalar Example: Portfolio Minimum Values**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 67, 35],
            "sum_assured": [100000, 500000, 250000, 1000000],
            "annual_premium": [1200, 6000, 8500, 15000],
        }
        af = ActuarialFrame(data)
        min_values = af.min()
        print(min_values)
        print("Min age:", min_values["age"])
        print("Min sum assured:", min_values["sum_assured"])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────┬─────────────┬────────────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ annual_premium │
        │ ---       ┆ --- ┆ ---         ┆ ---            │
        │ str       ┆ i64 ┆ i64         ┆ i64            │
        ╞═══════════╪═════╪═════════════╪════════════════╡
        │ P001      ┆ 25  ┆ 100000      ┆ 1200           │
        └───────────┴─────┴─────────────┴────────────────┘
        Min age: 25
        Min sum assured: 100000
        ```

        **Vector Example: Minimum Monthly Claims**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "policy_year": [1, 2],
            "monthly_claims": [
                [0, 500, 0, 1200, 0, 0, 800, 0, 0, 0, 0, 2500],
                [0, 0, 3000, 0, 0, 1500, 0, 0, 0, 4000, 0, 0]
            ],
            "monthly_retention": [
                [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000],
                [500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500]
            ]
        }
        af = ActuarialFrame(data)

        # Get minimum values to understand retention levels
        min_values = af.min()
        print(min_values)
        print("Min retention level:", min_values["monthly_retention"])
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────────────┬─────────────────────────────────────┬─────────────────────────────────────┐
        │ policy_id ┆ policy_year ┆ monthly_claims                      ┆ monthly_retention                   │
        │ ---       ┆ ---         ┆ ---                                 ┆ ---                                 │
        │ str       ┆ i64         ┆ list[i64]                           ┆ list[i64]                           │
        ╞═══════════╪═════════════╪═════════════════════════════════════╪═════════════════════════════════════╡
        │ P001      ┆ 1           ┆ [0, 0, 0, 0, … 0, 0, 0]             ┆ [500, 500, 500, 500, … 500]         │
        └───────────┴─────────────┴─────────────────────────────────────┴─────────────────────────────────────┘
        Min retention level: [500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500, 500]
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute min on an uninitialized ActuarialFrame.")

        # The underlying LazyFrame.min() returns a LazyFrame with one row
        # We collect it here to return an eager DataFrame
        result_df = self._df.min().collect()
        return MinResult(result_df)

    def mean(self):
        """Calculate mean values across all numeric columns.

        Returns a single-row frame containing the mean value for each numeric column.
        Essential for portfolio analysis, experience studies, and establishing
        benchmarks in actuarial calculations.

        !!! note "When to use"
            * **Experience Analysis:** Calculate average claim amounts, policy sizes,
                or premium levels for portfolio segmentation and pricing.
            * **Trend Analysis:** Determine average lapse rates, mortality rates, or
                expense ratios over observation periods.
            * **Benchmarking:** Establish portfolio averages for age, sum assured, or
                duration to compare against industry standards.
            * **Reserve Calculations:** Compute average policy values, benefit amounts,
                or reserve factors for grouped calculations.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing mean values for numeric columns.

        Examples
        --------
        **Scalar Example: Portfolio Averages**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004"],
            "age": [25, 45, 67, 35],
            "sum_assured": [100000, 500000, 250000, 1000000],
            "annual_premium": [1200, 6000, 8500, 15000],
        }
        af = ActuarialFrame(data)
        mean_values = af.mean()
        print(mean_values)
        print("Average age:", mean_values["age"])
        print("Average sum assured:", mean_values["sum_assured"])
        ```

        ```text
        shape: (1, 3)
        ┌──────┬──────────────┬─────────────────┐
        │ age  ┆ sum_assured  ┆ annual_premium  │
        │ ---  ┆ ---          ┆ ---             │
        │ f64  ┆ f64          ┆ f64             │
        ╞══════╪══════════════╪═════════════════╡
        │ 43.0 ┆ 462500.0     ┆ 7425.0          │
        └──────┴──────────────┴─────────────────┘
        Average age: 43.0
        Average sum assured: 462500.0
        ```

        **Vector Example: Average Monthly Experience**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002"],
            "policy_year": [1, 2],
            "monthly_claims": [
                [0, 500, 0, 1200, 0, 0, 800, 0, 0, 0, 0, 2500],
                [0, 0, 3000, 0, 0, 1500, 0, 0, 0, 4000, 0, 0]
            ],
            "monthly_lapses": [
                [2, 1, 3, 0, 1, 2, 1, 0, 1, 0, 2, 1],
                [1, 0, 2, 1, 0, 1, 0, 1, 0, 2, 1, 0]
            ]
        }
        af = ActuarialFrame(data)

        # Get average monthly experience
        mean_values = af.mean()
        print(mean_values)
        ```

        ```text
        shape: (1, 4)
        ┌─────────────┬───────────────────────────────┬──────────────────────────────┐
        │ policy_year ┆ monthly_claims                ┆ monthly_lapses               │
        │ ---         ┆ ---                           ┆ ---                          │
        │ f64         ┆ list[f64]                     ┆ list[f64]                    │
        ╞═════════════╪═══════════════════════════════╪══════════════════════════════╡
        │ 1.5         ┆ [0.0, 250.0, 1500.0, … 0.0]   ┆ [1.5, 0.5, 2.5, … 0.5]       │
        └─────────────┴───────────────────────────────┴──────────────────────────────┘
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute mean on an uninitialized ActuarialFrame.")

        result_df = self._df.mean().collect()
        return MeanResult(result_df)

    def std(self, ddof: int = 1):
        """Calculate standard deviation across all numeric columns.

        Returns a single-row frame containing the standard deviation for each numeric column.
        Essential for risk assessment, volatility analysis, and confidence interval
        calculations in actuarial modeling.

        !!! note "When to use"
            * **Risk Assessment:** Measure volatility in claim amounts, premium variations,
                or mortality experience for pricing and reserving.
            * **Experience Monitoring:** Quantify variability in lapse rates, expense ratios,
                or benefit utilization for assumption setting.
            * **Confidence Intervals:** Calculate standard errors for mortality estimates,
                reserve factors, or pricing assumptions.
            * **Portfolio Analysis:** Assess homogeneity of risk groups by comparing
                standard deviations across segments.

        Parameters
        ----------
        ddof : int, default 1
            Delta degrees of freedom. The divisor is N - ddof.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing standard deviations for numeric columns.

        Examples
        --------
        **Scalar Example: Premium Volatility Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", "P005"],
            "age_band": ["25-35", "25-35", "36-45", "36-45", "46-55"],
            "annual_premium": [1200, 1350, 3500, 3200, 8500],
            "sum_assured": [100000, 150000, 350000, 300000, 500000],
        }
        af = ActuarialFrame(data)
        std_values = af.std()
        print(std_values)
        print("Premium volatility:", std_values["annual_premium"])
        ```

        ```text
        shape: (1, 2)
        ┌──────────────────┬─────────────┐
        │ annual_premium   ┆ sum_assured │
        │ ---              ┆ ---         │
        │ f64              ┆ f64         │
        ╞══════════════════╪═════════════╡
        │ 2913.8           ┆ 158113.9    │
        └──────────────────┴─────────────┘
        Premium volatility: 2913.8
        ```

        **Vector Example: Monthly Claims Volatility**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "product": ["Term Life", "Whole Life"],
            "monthly_claims": [
                [0, 1000, 500, 2000, 0, 3000, 1500, 0, 2500, 1000, 0, 4000],
                [5000, 6000, 4500, 7000, 5500, 8000, 6500, 5000, 7500, 6000, 9000, 10000]
            ],
            "monthly_premiums": [
                [50000, 50000, 52000, 51000, 50000, 49000, 50000, 51000, 50000, 50000, 51000, 50000],
                [120000, 125000, 122000, 128000, 124000, 130000, 126000, 123000, 127000, 125000, 129000, 132000]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate standard deviation for risk assessment
        std_values = af.std()
        print(std_values)
        print("Term Life claims volatility:", round(std_values["monthly_claims"][0], 2))
        print("Whole Life claims volatility:", round(std_values["monthly_claims"][1], 2))
        ```

        ```text
        shape: (1, 3)
        ┌────────────┬──────────────────────────────┬───────────────────────────────┐
        │ product    ┆ monthly_claims               ┆ monthly_premiums              │
        │ ---        ┆ ---                          ┆ ---                           │
        │ str        ┆ list[f64]                    ┆ list[f64]                     │
        ╞════════════╪══════════════════════════════╪═══════════════════════════════╡
        │ null       ┆ [1443.38, 1443.38]           ┆ [831.66, 3207.14]             │
        └────────────┴──────────────────────────────┴───────────────────────────────┘
        Term Life claims volatility: 1443.38
        Whole Life claims volatility: 1443.38
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute std on an uninitialized ActuarialFrame.")

        result_df = self._df.std(ddof=ddof).collect()
        return StdResult(result_df)

    def var(self, ddof: int = 1):
        """Calculate variance across all numeric columns.

        Returns a single-row frame containing the variance for each numeric column.
        Used for risk metrics, ANOVA calculations, and statistical modeling in
        actuarial applications.

        !!! note "When to use"
            * **Risk Metrics:** Calculate variance in loss ratios, combined ratios,
                or expense ratios for enterprise risk management.
            * **Statistical Testing:** Perform ANOVA on mortality rates, lapse rates,
                or claim frequencies across different cohorts.
            * **Credibility Theory:** Calculate variance components for Bühlmann
                credibility factors in experience rating.
            * **Asset-Liability Modeling:** Measure variance in investment returns,
                liability cash flows, or surplus positions.

        Parameters
        ----------
        ddof : int, default 1
            Delta degrees of freedom. The divisor is N - ddof.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing variances for numeric columns.

        Examples
        --------
        **Scalar Example: Claims Variance Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "month": [1, 2, 3, 4, 5, 6],
            "claims_count": [45, 52, 38, 61, 43, 55],
            "claims_amount": [125000, 145000, 95000, 185000, 120000, 165000],
        }
        af = ActuarialFrame(data)
        var_values = af.var()
        print(var_values)
        print("Claims count variance:", var_values["claims_count"])
        print("Claims amount variance:", var_values["claims_amount"])
        ```

        ```text
        shape: (1, 3)
        ┌───────┬──────────────┬──────────────────┐
        │ month ┆ claims_count ┆ claims_amount    │
        │ ---   ┆ ---          ┆ ---              │
        │ f64   ┆ f64          ┆ f64              │
        ╞═══════╪══════════════╪══════════════════╡
        │ 3.5   ┆ 70.3         ┆ 1.091e9          │
        └───────┴──────────────┴──────────────────┘
        Claims count variance: 70.3
        Claims amount variance: 1091000000.0
        ```

        **Vector Example: Experience Variance Components**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "region": ["North", "South"],
            "quarterly_lapse_rates": [
                [0.025, 0.028, 0.022, 0.026],
                [0.031, 0.029, 0.033, 0.030]
            ],
            "quarterly_mortality_rates": [
                [0.0010, 0.0011, 0.0009, 0.0010],
                [0.0012, 0.0013, 0.0011, 0.0014]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate variance for credibility analysis
        var_values = af.var()
        print(var_values)
        print("North region lapse variance:", var_values["quarterly_lapse_rates"][0])
        print("South region lapse variance:", var_values["quarterly_lapse_rates"][1])
        ```

        ```text
        shape: (1, 3)
        ┌────────────┬────────────────────────┬──────────────────────────────┐
        │ region     ┆ quarterly_lapse_rates  ┆ quarterly_mortality_rates    │
        │ ---        ┆ ---                    ┆ ---                          │
        │ str        ┆ list[f64]              ┆ list[f64]                    │
        ╞════════════╪════════════════════════╪══════════════════════════════╡
        │ null       ┆ [0.000007, 0.000003]   ┆ [0.0000000067, 0.0000000167] │
        └────────────┴────────────────────────┴──────────────────────────────┘
        North region lapse variance: 0.000007
        South region lapse variance: 0.000003
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute var on an uninitialized ActuarialFrame.")

        result_df = self._df.var(ddof=ddof).collect()
        return VarResult(result_df)

    def median(self):
        """Calculate median values across all numeric columns.

        Returns a single-row frame containing the median value for each numeric column.
        Useful for robust central tendency measures that are less affected by outliers
        in actuarial data.

        !!! note "When to use"
            * **Robust Analysis:** Use median instead of mean when data contains outliers,
                such as large claims or extreme ages in the portfolio.
            * **Income Analysis:** Analyze median policyholder income or premium levels
                for market segmentation and product design.
            * **Experience Studies:** Calculate median time to claim, policy duration,
                or age at lapse for more representative measures.
            * **Pricing Benchmarks:** Determine median rates or factors when comparing
                across competitors or market segments.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing median values for numeric columns.

        Examples
        --------
        **Scalar Example: Median Policy Metrics**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", "P005"],
            "duration_years": [1, 3, 5, 7, 15],
            "annual_premium": [1200, 3500, 2800, 4200, 12000],
            "age": [25, 35, 42, 38, 65],
        }
        af = ActuarialFrame(data)
        median_values = af.median()
        print(median_values)
        print("Median duration:", median_values["duration_years"])
        print("Median premium:", median_values["annual_premium"])
        ```

        ```text
        shape: (1, 3)
        ┌────────────────┬────────────────┬──────┐
        │ duration_years ┆ annual_premium ┆ age  │
        │ ---            ┆ ---            ┆ ---  │
        │ f64            ┆ f64            ┆ f64  │
        ╞════════════════╪════════════════╪══════╡
        │ 5.0            ┆ 3500.0         ┆ 38.0 │
        └────────────────┴────────────────┴──────┘
        Median duration: 5.0
        Median premium: 3500.0
        ```

        **Vector Example: Median Monthly Performance**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "agent": ["A001", "A002"],
            "monthly_sales": [
                [3, 5, 2, 8, 4, 6, 3, 7, 5, 4, 6, 9],
                [12, 15, 10, 18, 14, 16, 11, 20, 13, 17, 15, 22]
            ],
            "monthly_commission": [
                [450, 750, 300, 1200, 600, 900, 450, 1050, 750, 600, 900, 1350],
                [1800, 2250, 1500, 2700, 2100, 2400, 1650, 3000, 1950, 2550, 2250, 3300]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate median for typical performance assessment
        median_values = af.median()
        print(median_values)
        print("Agent A001 median sales:", median_values["monthly_sales"][0])
        print("Agent A002 median sales:", median_values["monthly_sales"][1])
        ```

        ```text
        shape: (1, 3)
        ┌────────────┬────────────────────┬──────────────────────┐
        │ agent      ┆ monthly_sales      ┆ monthly_commission   │
        │ ---        ┆ ---                ┆ ---                  │
        │ str        ┆ list[f64]          ┆ list[f64]            │
        ╞════════════╪════════════════════╪══════════════════════╡
        │ null       ┆ [5.0, 15.0]        ┆ [750.0, 2250.0]      │
        └────────────┴────────────────────┴──────────────────────┘
        Agent A001 median sales: 5.0
        Agent A002 median sales: 15.0
        ```

        """
        if self._df is None:
            raise ValueError(
                "Cannot compute median on an uninitialized ActuarialFrame."
            )

        result_df = self._df.median().collect()
        return MedianResult(result_df)

    def sum(self):
        """Calculate sum totals across all numeric columns.

        Returns a single-row frame containing the sum total for each numeric column.
        Critical for calculating portfolio totals, aggregate exposures, and overall
        metrics in actuarial reporting.

        !!! note "When to use"
            * **Portfolio Totals:** Calculate total sum assured, total premiums collected,
                or total claims paid for financial reporting.
            * **Exposure Analysis:** Sum total lives covered, total benefits, or total
                risk amounts for reinsurance and capital calculations.
            * **Revenue Reporting:** Aggregate premium income, fee revenue, or investment
                income across product lines or time periods.
            * **Claims Analysis:** Total claim counts, amounts paid, or reserves across
                different claim types or cohorts.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing sum totals for numeric columns.

        Examples
        --------
        **Scalar Example: Portfolio Totals**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "product": ["Term", "Whole Life", "Universal", "Term", "Endowment"],
            "policies_inforce": [1250, 890, 445, 2100, 325],
            "annual_premium": [1500000, 3200000, 2100000, 2800000, 1900000],
            "sum_assured": [125000000, 89000000, 67000000, 315000000, 48000000],
        }
        af = ActuarialFrame(data)
        sum_values = af.sum()
        print(sum_values)
        print("Total policies:", sum_values["policies_inforce"])
        print("Total premium:", sum_values["annual_premium"])
        print("Total exposure:", sum_values["sum_assured"])
        ```

        ```text
        shape: (1, 3)
        ┌──────────────────┬────────────────┬─────────────┐
        │ policies_inforce ┆ annual_premium ┆ sum_assured │
        │ ---              ┆ ---            ┆ ---         │
        │ i64              ┆ i64            ┆ i64         │
        ╞══════════════════╪════════════════╪═════════════╡
        │ 5010             ┆ 11500000       ┆ 644000000   │
        └──────────────────┴────────────────┴─────────────┘
        Total policies: 5010
        Total premium: 11500000
        Total exposure: 644000000
        ```

        **Vector Example: Monthly Totals**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "branch": ["North", "South"],
            "monthly_new_business": [
                [120, 135, 110, 145, 130, 125, 140, 155, 135, 140, 130, 160],
                [95, 100, 90, 105, 110, 95, 100, 115, 105, 100, 95, 120]
            ],
            "monthly_premium": [
                [180000, 202500, 165000, 217500, 195000, 187500, 210000, 232500, 202500, 210000, 195000, 240000],
                [142500, 150000, 135000, 157500, 165000, 142500, 150000, 172500, 157500, 150000, 142500, 180000]
            ]
        }
        af = ActuarialFrame(data)

        # Get total new business and premiums
        sum_values = af.sum()
        print(sum_values)
        ```

        ```text
        shape: (1, 2)
        ┌───────────────────────────────────────┬───────────────────────────────────────┐
        │ monthly_new_business                  ┆ monthly_premium                       │
        │ ---                                   ┆ ---                                   │
        │ list[i64]                             ┆ list[i64]                             │
        ╞═══════════════════════════════════════╪═══════════════════════════════════════╡
        │ [215, 235, 200, 250, … 240, 225, 280] ┆ [322500, 352500, 300000, … 420000]    │
        └───────────────────────────────────────┴───────────────────────────────────────┘
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute sum on an uninitialized ActuarialFrame.")

        result_df = self._df.sum().collect()
        return SumResult(result_df)

    def count(self):
        """Count non-null values in each column.

        Returns a single-row frame containing the count of non-null values for each column.
        Essential for data quality assessment, completeness checks, and exposure
        calculations in actuarial analysis.

        !!! note "When to use"
            * **Data Quality:** Assess completeness of critical fields like policy ID,
                sum assured, or premium to identify missing data issues.
            * **Exposure Calculation:** Count policies, lives, or claims for exposure-based
                calculations in pricing and reserving.
            * **Cohort Analysis:** Determine size of different risk groups, age bands,
                or product segments for credibility assessment.
            * **Validation:** Verify record counts match expected values after data
                processing, joins, or filtering operations.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing non-null counts for each column.

        Examples
        --------
        **Scalar Example: Data Completeness Check**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "policy_id": ["P001", "P002", "P003", "P004", None],
            "age": [25, 45, None, 35, 52],
            "sum_assured": [100000, 500000, 250000, None, 300000],
            "status": ["Active", "Active", "Lapsed", "Active", "Active"],
        }
        af = ActuarialFrame(data)
        counts = af.count()
        print(counts)
        print("Complete policies:", counts["policy_id"])
        print("Complete ages:", counts["age"])
        print("Data completeness %:", counts["age"] / 5 * 100)
        ```

        ```text
        shape: (1, 4)
        ┌───────────┬─────┬─────────────┬────────┐
        │ policy_id ┆ age ┆ sum_assured ┆ status │
        │ ---       ┆ --- ┆ ---         ┆ ---    │
        │ u32       ┆ u32 ┆ u32         ┆ u32    │
        ╞═══════════╪═════╪═════════════╪════════╡
        │ 4         ┆ 4   ┆ 4           ┆ 5      │
        └───────────┴─────┴─────────────┴────────┘
        Complete policies: 4
        Complete ages: 4
        Data completeness %: 80.0
        ```

        **Vector Example: Monthly Activity Counts**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "month": ["Jan", "Feb"],
            "daily_claims": [
                [5, 3, 0, 4, None, 2, 1, 0, 3, None, 4, 2, 0, 1, 5],
                [2, None, 3, 1, 0, 4, None, 2, 0, 3, 1, None, 4, 2, 0]
            ],
            "daily_lapses": [
                [1, 0, 0, 2, 1, 0, 0, 1, 0, 0, 1, 0, 2, 0, 1],
                [0, 1, 0, 0, 2, 0, 1, 0, 1, 0, 0, 1, 0, 2, 0]
            ]
        }
        af = ActuarialFrame(data)

        # Count valid daily observations
        counts = af.count()
        print(counts)
        ```

        ```text
        shape: (1, 3)
        ┌───────┬──────────────┬──────────────┐
        │ month ┆ daily_claims ┆ daily_lapses │
        │ ---   ┆ ---          ┆ ---          │
        │ u32   ┆ u32          ┆ u32          │
        ╞═══════╪══════════════╪══════════════╡
        │ 2     ┆ 2            ┆ 2            │
        └───────┴──────────────┴──────────────┘
        ```

        """
        if self._df is None:
            raise ValueError("Cannot compute count on an uninitialized ActuarialFrame.")

        result_df = self._df.count().collect()
        return CountResult(result_df)

    def product(self):
        """Calculate the product of values in each numeric column.

        Returns a single-row frame containing the product of all values for each numeric column.
        Useful for compound calculations, probability chains, and multiplicative factors
        in actuarial modeling.

        !!! note "When to use"
            * **Compound Interest:** Calculate accumulated values using multiple period
                growth factors or discount factors.
            * **Probability Chains:** Multiply survival probabilities, persistency rates,
                or success rates across multiple periods.
            * **Factor Application:** Apply multiple adjustment factors, loading factors,
                or credibility factors in sequence.
            * **Index Calculations:** Compute cumulative index values from period-to-period
                change factors.

        Returns
        -------
        pl.DataFrame
            A frame with one row containing products for numeric columns.

        Examples
        --------
        **Scalar Example: Survival Probability Chain**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "year": [1, 2, 3, 4, 5],
            "annual_survival": [0.999, 0.998, 0.997, 0.995, 0.993],
            "annual_persistency": [0.95, 0.92, 0.90, 0.88, 0.85],
        }
        af = ActuarialFrame(data)
        products = af.product()
        print(products)
        print("5-year survival probability:", round(products["annual_survival"], 6))
        print("5-year persistency:", round(products["annual_persistency"], 4))
        ```

        ```text
        shape: (1, 3)
        ┌──────┬─────────────────┬────────────────────┐
        │ year ┆ annual_survival ┆ annual_persistency │
        │ ---  ┆ ---             ┆ ---                │
        │ i64  ┆ f64             ┆ f64                │
        ╞══════╪═════════════════╪════════════════════╡
        │ 120  ┆ 0.982089        ┆ 0.59262            │
        └──────┴─────────────────┴────────────────────┘
        5-year survival probability: 0.982089
        5-year persistency: 0.5926
        ```

        **Vector Example: Discount Factor Chains**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "scenario": ["Base", "Stressed"],
            "monthly_discount": [
                [0.9992, 0.9992, 0.9992, 0.9992, 0.9992, 0.9992],
                [0.9990, 0.9990, 0.9990, 0.9990, 0.9990, 0.9990]
            ],
            "monthly_survival": [
                [0.9999, 0.9999, 0.9999, 0.9999, 0.9999, 0.9999],
                [0.9998, 0.9998, 0.9998, 0.9998, 0.9998, 0.9998]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate cumulative factors
        products = af.product()
        print(products)
        ```

        ```text
        shape: (1, 3)
        ┌──────────┬──────────────────┬──────────────────┐
        │ scenario ┆ monthly_discount ┆ monthly_survival │
        │ ---      ┆ ---              ┆ ---              │
        │ str      ┆ list[f64]        ┆ list[f64]        │
        ╞══════════╪══════════════════╪══════════════════╡
        │ null     ┆ [0.9952, 0.9940] ┆ [0.9994, 0.9988] │
        └──────────┴──────────────────┴──────────────────┘
        ```

        """
        if self._df is None:
            raise ValueError(
                "Cannot compute product on an uninitialized ActuarialFrame."
            )

        # Product is not available on LazyFrame, need to use select with expressions
        # Also need to handle non-numeric columns
        schema = self._df.collect_schema()
        numeric_cols = [
            pl.col(name).product().alias(name)
            for name, dtype in schema.items()
            if dtype.is_numeric()
        ]

        # Add non-numeric columns as nulls to maintain consistent output
        non_numeric_cols = [
            pl.lit(None).alias(name)
            for name, dtype in schema.items()
            if not dtype.is_numeric()
        ]

        all_cols = numeric_cols + non_numeric_cols
        result_df = self._df.select(all_cols).head(1).collect()
        return ProductResult(result_df)

    def quantile(self, quantile: float, interpolation: str = "nearest"):
        """Calculate quantile values across all numeric columns.

        Returns a single-row frame containing the specified quantile for each numeric column.
        Essential for risk assessment, percentile-based analysis, and regulatory reporting
        in actuarial applications.

        !!! note "When to use"
            * **Risk Assessment:** Calculate VaR (Value at Risk) at different confidence
                levels (e.g., 95th, 99th percentile) for solvency calculations.
            * **Experience Analysis:** Determine percentile thresholds for large claims,
                high-risk ages, or outlier detection in portfolios.
            * **Pricing Segmentation:** Identify quantile boundaries for premium bands,
                risk tiers, or underwriting categories.
            * **Regulatory Reporting:** Calculate required percentiles for stress testing,
                capital requirements, or reserve adequacy testing.

        Parameters
        ----------
        quantile : float
            Quantile value between 0 and 1 (e.g., 0.5 for median, 0.95 for 95th percentile).
        interpolation : str, default "nearest"
            Interpolation method: "nearest", "higher", "lower", "midpoint", or "linear".

        Returns
        -------
        pl.DataFrame
            A frame with one row containing quantile values for numeric columns.

        Examples
        --------
        **Scalar Example: Claims Distribution Analysis**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "claim_id": list(range(1, 101)),
            "claim_amount": [
                1000,
                1500,
                2000,
                2500,
                3000,
                3500,
                4000,
                5000,
                6000,
                7500,
                8000,
                9000,
                10000,
                12000,
                15000,
                18000,
                20000,
                25000,
                30000,
                35000,
                40000,
                45000,
                50000,
                60000,
                75000,
                85000,
                95000,
                100000,
                120000,
                150000,
            ]
            + [2000] * 70,
            "processing_days": list(range(5, 35)) + list(range(10, 80)),
        }
        af = ActuarialFrame(data)

        # Calculate key percentiles
        p90 = af.quantile(0.90)
        p95 = af.quantile(0.95)
        p99 = af.quantile(0.99)

        print("90th percentile:")
        print(p90)
        print("\\nClaim amount 90th percentile:", p90["claim_amount"])
        print("Claim amount 95th percentile:", p95["claim_amount"])
        print("Claim amount 99th percentile:", p99["claim_amount"])
        ```

        ```text
        90th percentile:
        shape: (1, 3)
        ┌──────────┬──────────────┬─────────────────┐
        │ claim_id ┆ claim_amount ┆ processing_days │
        │ ---      ┆ ---          ┆ ---             │
        │ f64      ┆ f64          ┆ f64             │
        ╞══════════╪══════════════╪═════════════════╡
        │ 90.0     ┆ 85000.0      ┆ 71.0            │
        └──────────┴──────────────┴─────────────────┘

        Claim amount 90th percentile: 85000.0
        Claim amount 95th percentile: 100000.0
        Claim amount 99th percentile: 150000.0
        ```

        **Vector Example: Portfolio Risk Percentiles**

        ```python
        from gaspatchio_core import ActuarialFrame

        data = {
            "product": ["Term Life", "Whole Life"],
            "claim_amounts": [
                [10000, 15000, 20000, 25000, 30000, 35000, 40000, 50000, 75000, 100000,
                 150000, 200000, 250000, 300000, 500000, 750000, 1000000, 1500000, 2000000, 3000000],
                [50000, 75000, 100000, 125000, 150000, 175000, 200000, 250000, 300000, 400000,
                 500000, 600000, 750000, 900000, 1000000, 1250000, 1500000, 2000000, 2500000, 5000000]
            ]
        }
        af = ActuarialFrame(data)

        # Calculate 95th percentile for risk assessment
        var_95 = af.quantile(0.95)
        print("95% VaR by product:")
        print(var_95)
        ```

        ```text
        95% VaR by product:
        shape: (1, 2)
        ┌────────────┬──────────────────────────────────┐
        │ product    ┆ claim_amounts                    │
        │ ---        ┆ ---                              │
        │ str        ┆ list[f64]                        │
        ╞════════════╪══════════════════════════════════╡
        │ null       ┆ [2000000.0, 2500000.0]           │
        └────────────┴──────────────────────────────────┘
        ```

        """
        if self._df is None:
            raise ValueError(
                "Cannot compute quantile on an uninitialized ActuarialFrame."
            )

        result_df = self._df.quantile(quantile, interpolation=interpolation).collect()
        return QuantileResult(result_df)

    def __getattr__(self, name: str) -> Any:
        """Dynamically return accessors or provide pandas-style column attribute access."""
        # Reserved accessor properties should always resolve via properties
        if name in {"date", "excel", "finance"}:
            return object.__getattribute__(self, name)
        # 1) Accessors precedence (existing behavior)
        kind_dict = _ACCESSOR_REGISTRY.get(name)
        if kind_dict and "frame" in kind_dict:
            AccessorClass = kind_dict.get("frame")
            if AccessorClass:
                accessor_instance = AccessorClass(self)
                # Cache accessor instance to avoid re-instantiation; do not cache columns
                object.__setattr__(self, name, accessor_instance)
                return accessor_instance

        # 2) Identifier validation
        if not isinstance(name, str) or not name.isidentifier():
            raise AttributeError(f"'{name}' is not a valid attribute name")
        # 3) Keyword rejection
        if keyword.iskeyword(name):
            raise AttributeError(
                f"'{name}' is a Python keyword; use af['{name}'] instead"
            )
        # 4) Underscore/dunder names disallowed via attribute
        if name.startswith("_"):
            raise AttributeError(
                f"'{name}' is not available via attribute access; use af['{name}']"
            )
        # 5) Conflicts with class attributes/properties/methods (skip if accessor name or reserved name)
        if hasattr(type(self), name):
            kind_dict2 = _ACCESSOR_REGISTRY.get(name)
            if not (kind_dict2 and ("frame" in kind_dict2)) and name not in {
                "date",
                "excel",
                "finance",
            }:
                raise AttributeError(
                    f"'{name}' conflicts with existing method/attribute"
                )
        # 6) Column attribute access
        if name in self._attr_columns_set:
            return self[name]

        # 7) Unknown attribute: choose error style
        accessor_names = [
            n for n, kinds in _ACCESSOR_REGISTRY.items() if "frame" in kinds
        ]
        has_builtins = any(n in {"date", "excel", "finance"} for n in accessor_names)
        if accessor_names and not has_builtins:
            # In contexts where only custom frame accessors are present (tests patching registry)
            raise AttributeError(
                f"No '{name}' frame accessor registered or attribute found."
            )
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'. If '{name}' is a column name, use af['{name}'] instead."
        )

    def __setattr__(self, name: str, value: Any) -> None:
        """Support attribute-style column assignment for eligible identifiers."""
        # Reserved/internal or existing attributes/accessors: normal behavior
        if (
            hasattr(self, name)
            or hasattr(type(self), name)
            or name in _ACCESSOR_REGISTRY
        ):
            return object.__setattr__(self, name, value)

        # Allow setting known internal/private attributes
        if name.startswith("_"):
            # Known internal fields
            known_internal = {
                "_df",
                "_column_order",
                "_attr_columns_set",
                "_schema",
                "_mode",
                "_verbose",
                "_threads",
                "_show_query_plan",
                "_computation_graph",
                "_tracing",
                "_date_accessor_instance",
                "_excel_accessor_instance",
                "_finance_accessor_instance",
            }
            if (name in known_internal) or hasattr(type(self), name):
                return object.__setattr__(self, name, value)
            # Otherwise underscore names are not valid for column assignment
            raise AttributeError(
                f"'{name}' is not a valid attribute name; use af['{name}'] = ..."
            )

        # Enforce identifier policy for column assignment
        if (
            (not isinstance(name, str))
            or (not name.isidentifier())
            or keyword.iskeyword(name)
        ):
            raise AttributeError(
                f"'{name}' is not a valid attribute name; use af['{name}'] = ..."
            )

        # Treat as column assignment and delegate to __setitem__
        self[name] = value

    def __getattribute__(self, name: str) -> Any:
        """Intercept attribute access to raise on method/attribute conflicts with columns."""
        # Allow internals fast-path
        if not isinstance(name, str) or name.startswith("_"):
            return object.__getattribute__(self, name)

        cls = type(self)
        # If the attribute exists on the class (method/property) AND is also an eligible column,
        # raise a clear conflict error to guide users to bracket notation.
        if hasattr(cls, name):
            # Accessor names should NOT raise conflict; they must win
            kind_dict = _ACCESSOR_REGISTRY.get(name)
            is_accessor_name = bool(kind_dict and ("frame" in kind_dict))
            # Reserved accessor property names should not raise either
            if name in {"date", "excel", "finance"}:
                return object.__getattribute__(self, name)
            try:
                attr_set = object.__getattribute__(self, "_attr_columns_set")
            except Exception:
                # Initialization edge-cases: defer to default behavior
                return object.__getattribute__(self, name)
            if (name in attr_set) and (not is_accessor_name):
                raise AttributeError(
                    f"'{name}' conflicts with existing method/attribute"
                )
        return object.__getattribute__(self, name)

    # --- Dunder Methods ---

    # ADDED: columns property
    @property
    def columns(self) -> list[str]:
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

    def __dir__(self) -> list[str]:
        """Enhance dir() to include eligible column names and registered frame accessors."""
        attrs = set(super().__dir__())
        # Add methods from the underlying LazyFrame if available
        if hasattr(self, "_df") and self._df is not None:
            try:
                df_methods = [
                    attr for attr in dir(self._df) if not attr.startswith("_")
                ]
                attrs.update(df_methods)
            except Exception:
                pass
        # Add registered frame accessor names
        accessor_names = [
            name for name, kinds in _ACCESSOR_REGISTRY.items() if "frame" in kinds
        ]
        attrs.update(accessor_names)
        # Add attribute-eligible column names
        attrs.update(self._attr_columns_set)
        return sorted(list(attrs))

    # --- Internal helpers ---
    def _refresh_attr_columns_set(self) -> None:
        """Recompute the set of columns that are valid for attribute access."""
        eligible: set[str] = set()
        for c in self._column_order:
            if (
                isinstance(c, str)
                and c.isidentifier()
                and (not keyword.iskeyword(c))
                and (not c.startswith("_"))
            ):
                eligible.add(c)
        self._attr_columns_set = eligible

    def _apply_conditional_list_broadcasting(
        self, key: str, metadata: dict[str, Any]
    ) -> None:
        """Apply list broadcasting for conditional expressions.

        This method handles when-then-otherwise conditionals that involve list columns.
        It uses the explode/re-aggregate pattern to apply element-wise conditionals.

        Behavior by mode:
        - **Debug mode**: Executes the pattern eagerly and captures a TracedOperation
          in the computation graph for debugging and visualization. The operation
          includes metadata about the list columns, conditional expression, and
          source location.
        - **Optimize mode**: Executes the pattern directly without tracing overhead.

        Args:
            key: Name of the column to create
            metadata: Dictionary with:
                - list_columns (set[str]): List columns to explode
                - conditional_expr (pl.Expr): Conditional expression to apply

        Example:
            >>> af = ActuarialFrame({"month": [[0, 1, 2]], "amt": [[100, 200, 300]]})
            >>> af.adjusted = when(af.month == 0).then(0.0).otherwise(af.amt)
            >>> # In debug mode: captures operation + executes
            >>> # In optimize mode: just executes

        """
        # Extract metadata
        list_columns = metadata["list_columns"]
        conditional_expr = metadata["conditional_expr"]

        # In tracing mode: execute eagerly AND capture operation
        if self._tracing:
            from ..errors.metadata import capture_source_context
            from .tracing import (
                create_list_broadcast_traced_operations,  # type: ignore[attr-defined]
            )

            # CRITICAL: Apply pending operations before list broadcasting
            # List broadcasting needs the actual schema to determine which columns are lists
            # But in debug mode, columns may only exist in the computation graph
            if self._computation_graph:
                logger.trace(
                    f"Debug mode: Applying {len(self._computation_graph)} pending "
                    f"operation(s) before list broadcasting for '{key}'"
                )
                # Apply all pending operations to the LazyFrame
                for op in self._computation_graph:
                    # Skip string expressions (already applied)
                    if isinstance(op.expression, str):
                        continue
                    self._df = self._df.with_columns(op.expression.alias(op.alias))

                # Note: We keep operations in the graph for collect() to use
                # but they're already in _df so collect() will skip re-applying them

            # Capture source location from user code
            source_metadata = None
            for depth in range(2, 10):
                temp_metadata = capture_source_context(depth=depth)
                if not any(
                    internal in temp_metadata.file_name
                    for internal in [
                        "gaspatchio_core/frame/",
                        "gaspatchio_core/column/",
                        "gaspatchio_core/functions/",
                        "<frozen",
                        "site-packages/",
                    ]
                ):
                    source_metadata = temp_metadata
                    break

            # Create traced operations for this list broadcasting
            traced_ops = create_list_broadcast_traced_operations(
                frame_instance=self,
                result_col=key,
                list_columns=list_columns,
                conditional_expr=conditional_expr,
                metadata=source_metadata,
            )

            # Append to computation graph
            self._computation_graph.extend(traced_ops)

            logger.trace(
                f"Debug mode: Executing list broadcasting for '{key}' eagerly "
                f"and captured {len(traced_ops)} operation(s)"
            )

        # Execute the pattern (both modes reach here now)
        new_df = self._build_list_broadcasting_df(key, conditional_expr, list_columns)

        # In tracing mode, materialize immediately then convert back to lazy
        # This prevents nested lazy operations that Polars can't optimize
        if self._tracing:
            try:
                # Disable optimizations that might cause schema inference issues
                self._df = new_df.collect(
                    type_coercion=False,
                    predicate_pushdown=False,
                    projection_pushdown=False,
                ).lazy()
                logger.trace(
                    f"Debug mode: Materialized list broadcasting for '{key}' "
                    "to prevent nested lazy operations"
                )
            except Exception as e:
                # If collection fails (e.g., schema inference error),
                # fall back to keeping it lazy and hope for the best
                logger.warning(
                    f"Debug mode: Could not materialize list broadcasting for '{key}': {e}. "
                    "Keeping as lazy frame."
                )
                self._df = new_df
        else:
            self._df = new_df

    def _build_list_broadcasting_df(
        self, result_col: str, conditional_expr: pl.Expr, list_columns: set[str]
    ) -> pl.LazyFrame:
        """Build DataFrame with list broadcasting using explode/re-aggregate pattern.

        Args:
            result_col: Name of the result column
            conditional_expr: The conditional expression to apply
            list_columns: Set of list column names to explode

        Returns:
            LazyFrame with the result column added as a list

        """
        if self._df is None:
            msg = "Cannot apply list broadcasting to uninitialized ActuarialFrame"
            raise ValueError(msg)

        # Get schema to determine which columns to aggregate
        schema = self._df.collect_schema()

        # Filter list_columns to only include columns that exist and are actually lists
        valid_list_cols = {
            col
            for col in list_columns
            if col in schema and isinstance(schema[col], pl.List)
        }

        # Convert set to list for explode
        list_cols_to_explode = list(valid_list_cols)

        # Build aggregation expressions:
        # After exploding, columns that were exploded become scalar and need re-aggregation
        # - Columns in valid_list_cols: were exploded, now scalar -> aggregate back to list
        # - Other list columns in schema: weren't exploded, still list -> take first (which is the whole list)
        # - Scalar columns: weren't exploded, still scalar -> take first
        agg_exprs = []
        for col_name in schema.keys():
            if col_name in valid_list_cols:
                # Was exploded, now scalar - aggregate back to list
                agg_exprs.append(pl.col(col_name))
            elif isinstance(schema[col_name], pl.List):
                # Is a list column but wasn't exploded - take first to keep as-is
                agg_exprs.append(pl.col(col_name).first())
            else:
                # Scalar column - take first value to maintain scalar type
                agg_exprs.append(pl.col(col_name).first())

        # Add the result column as a list (it was created as scalar after explode)
        agg_exprs.append(pl.col(result_col))

        # Build explode/re-aggregate pipeline
        return (
            self._df.with_row_index("_row_id")
            .explode(list_cols_to_explode)
            .with_columns(**{result_col: conditional_expr})
            .group_by("_row_id", maintain_order=True)
            .agg(agg_exprs)
            .drop("_row_id")
        )

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
