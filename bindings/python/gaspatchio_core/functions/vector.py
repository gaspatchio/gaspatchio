"""Vector operation plugins for Gaspatchio.

Provides Rust-powered Polars expression plugins for high-performance
vector operations on list columns.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

# Import the internal module to get its path
IMPORT_ERROR_MSG = (
    "Failed to import the gaspatchio_core native extension (_internal). "
    "Ensure the project is built and installed correctly "
    "(e.g., using 'maturin develop -uv')."
)

try:
    from gaspatchio_core import _internal
except ImportError as e:
    raise ImportError(IMPORT_ERROR_MSG) from e

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

# Get the path to the compiled extension from the imported module
LIB = Path(_internal.__file__)


def fill_series(expr: IntoExprColumn, start: int = 0, increment: int = 1) -> pl.Expr:
    """Fill a list column with sequential integers.

    Args:
        expr: Column or expression to fill
        start: Starting value for sequence
        increment: Increment between values

    Returns:
        Expression with filled list column

    """
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        # This is likely a ColumnProxy object
        expr = pl.col(expr.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        # This is likely an ExpressionProxy object
        expr = expr._expr  # noqa: SLF001

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="fill_series",
        is_elementwise=True,
        kwargs={"start": start, "increment": increment},
    )


def floor(expr: IntoExprColumn, divisor: int = 1, default: int = 0) -> pl.Expr:
    """Floor division operation.

    Args:
        expr: Column or expression to apply floor division
        divisor: Divisor for floor division
        default: Default value for null results

    Returns:
        Expression with floor division results

    """
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        # This is likely a ColumnProxy object
        expr = pl.col(expr.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        # This is likely an ExpressionProxy object
        expr = expr._expr  # noqa: SLF001

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="floor",
        is_elementwise=True,
        kwargs={"divisor": divisor, "default": default},
    )


def round(expr: IntoExprColumn, decimal_places: int = 0) -> pl.Expr:  # noqa: A001
    """Round values to specified decimal places.

    Args:
        expr: Column or expression to round
        decimal_places: Number of decimal places

    Returns:
        Expression with rounded values

    """
    # Handle ColumnProxy and ExpressionProxy
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        expr = pl.col(expr.name)
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        expr = expr._expr  # noqa: SLF001

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="round",
        is_elementwise=True,
        kwargs={"decimal_places": decimal_places},
    )


def round_to_int(expr: IntoExprColumn) -> pl.Expr:
    """Round values to nearest integer.

    Args:
        expr: Column or expression to round

    Returns:
        Expression with integer-rounded values

    """
    # Handle ColumnProxy and ExpressionProxy
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        expr = pl.col(expr.name)
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        expr = expr._expr  # noqa: SLF001

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="round_to_int",
        is_elementwise=True,
    )


def list_pow(base: pl.Expr, exp: pl.Expr) -> pl.Expr:
    """Element-wise power operation on list columns.

    Computes base ** exp element-wise for list columns, eliminating the need
    for EXPLODE/GROUP_BY pattern. Always returns Float64 values.

    Supports:
        - list ** list (pairwise, requires same inner lengths)
        - list ** scalar (broadcasts scalar to each element)

    Args:
        base: Base values (List column or expression)
        exp: Exponent values (List column, scalar column, or expression)

    Returns:
        Expression with element-wise power results as List<Float64>

    Raises:
        ComputeError: If base is not a List type
        ComputeError: If inner list lengths don't match (for list ** list)

    Examples:
        >>> import polars as pl
        >>> from gaspatchio_core.functions.vector import list_pow
        >>>
        >>> # List ** List
        >>> df = pl.DataFrame(
        ...     {"base": [[2.0, 3.0], [4.0, 5.0]], "exp": [[2.0, 3.0], [2.0, 2.0]]}
        ... )
        >>> df.with_columns(result=list_pow(pl.col("base"), pl.col("exp")))

        >>> # List ** Scalar
        >>> df.with_columns(result=list_pow(pl.col("base"), pl.lit(2.0)))

    Note:
        This is an internal function used by the finance accessor.
        Actuaries should use `af.finance.discount_factor()` instead.

    """
    return register_plugin_function(
        plugin_path=LIB,
        function_name="list_pow",
        args=[base, exp],
        is_elementwise=True,
    )


def list_conditional(
    left: pl.Expr,
    right: pl.Expr,
    then_val: pl.Expr,
    otherwise_val: pl.Expr,
    operator: str,
) -> pl.Expr:
    """Element-wise conditional operation on list columns.

    Computes when/then/otherwise conditionals element-wise for list columns,
    eliminating the need for EXPLODE/GROUP_BY pattern. Always returns Float64 values.

    Supports:
        - list op list (pairwise comparison, requires same inner lengths)
        - list op scalar (broadcasts scalar to each element)
        - then/otherwise can be list or scalar

    Args:
        left: Left values for comparison (List column or expression)
        right: Right values for comparison (List/scalar column or expression)
        then_val: Values when condition is true (List/scalar column or expression)
        otherwise_val: Values when condition is false (List/scalar or expression)
        operator: Comparison operator - "eq", "ne", "lt", "lte", "gt", "gte"

    Returns:
        Expression with element-wise conditional results as List<Float64>

    Raises:
        ComputeError: If left is not a List type
        ComputeError: If inner list lengths don't match (for list op list)
        ComputeError: If operator is not valid

    Examples:
        >>> import polars as pl
        >>> from gaspatchio_core.functions.vector import list_conditional
        >>>
        >>> # List == List with scalar then/otherwise
        >>> df = pl.DataFrame(
        ...     {
        ...         "month": [[0, 1, 2], [0, 1]],
        ...         "term": [[2, 2, 2], [1, 1]],
        ...         "benefit": [100.0, 200.0],
        ...     }
        ... )
        >>> df.with_columns(
        ...     payment=list_conditional(
        ...         pl.col("month"),
        ...         pl.col("term"),
        ...         pl.col("benefit"),
        ...         pl.lit(0.0),
        ...         "eq",
        ...     )
        ... )

        >>> # List < Scalar with scalar then/otherwise
        >>> df.with_columns(
        ...     in_force=list_conditional(
        ...         pl.col("month"), pl.lit(12), pl.lit(1.0), pl.lit(0.0), "lt"
        ...     )
        ... )

    Note:
        This is an internal function used by the conditional module.
        Actuaries should use `when().then().otherwise()` pattern instead.

    """
    return register_plugin_function(
        plugin_path=LIB,
        function_name="list_conditional",
        args=[left, right, then_val, otherwise_val],
        is_elementwise=True,
        kwargs={"operator": operator},
    )
