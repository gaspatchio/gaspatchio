from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from polars.plugins import register_plugin_function

__version__ = "0.1.0"

if TYPE_CHECKING:
    from gaspatchio_core.typing import IntoExprColumn

LIB = Path(__file__).parent


def init_logging(level=logging.INFO, format_str=None):
    """Initialize Python logging which will also capture Rust logs.

    Parameters
    ----------
    level : int
        The logging level to use (default: logging.INFO)
    format_str : str, optional
        Custom format string for logging. If None, a default format is used.
    """
    if format_str is None:
        format_str = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"

    # Configure Python logging
    logging.basicConfig(
        level=level,
        format=format_str,
        force=True,  # Force reconfiguration if already configured
    )

    # Create a logger for the gaspatchio_core module
    logger = logging.getLogger("gaspatchio_core")
    logger.setLevel(level)

    # Log that initialization is complete
    logger.info("Logging initialized for gaspatchio_core")
    logger.debug("Debug logging enabled for gaspatchio_core")


def pig_latinnify(expr: IntoExprColumn) -> pl.Expr:
    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="pig_latinnify",
        is_elementwise=True,
    )


def noop(expr: IntoExprColumn) -> pl.Expr:
    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="noop",
        is_elementwise=True,
    )


def fill_series(expr: IntoExprColumn, start: int = 0, increment: int = 1) -> pl.Expr:
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        # This is likely a ColumnProxy object
        expr = pl.col(expr.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        # This is likely an ExpressionProxy object
        expr = expr._expr

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="fill_series",
        is_elementwise=True,
        kwargs={"start": start, "increment": increment},
    )


def floor(expr: IntoExprColumn, divisor: int = 1, default: int = 0) -> pl.Expr:
    # Handle ColumnProxy objects by extracting the column name
    if hasattr(expr, "name") and hasattr(expr, "_parent"):
        # This is likely a ColumnProxy object
        expr = pl.col(expr.name)
    # Handle ExpressionProxy objects by extracting the underlying expression
    elif hasattr(expr, "_expr") and hasattr(expr, "_parent"):
        # This is likely an ExpressionProxy object
        expr = expr._expr

    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="floor",
        is_elementwise=True,
        kwargs={"divisor": divisor, "default": default},
    )


def midpoint_2d(expr: IntoExprColumn, ref_point: tuple[float, float]) -> pl.Expr:
    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="midpoint_2d",
        is_elementwise=True,
        kwargs={"ref_point": ref_point},
    )


def abs_i64(expr: IntoExprColumn) -> pl.Expr:
    return register_plugin_function(
        args=[expr],
        plugin_path=LIB,
        function_name="abs_i64",
        is_elementwise=True,
    )


def lookup(
    lookup_values: IntoExprColumn, *key_columns: IntoExprColumn, table_name: str
) -> pl.Expr:
    """
    Look up values from a table using one or more key columns.

    Parameters
    ----------
    lookup_values : IntoExprColumn
        The column to use as values for the lookup
    *key_columns : IntoExprColumn
        One or more key columns to use for lookup
    table_name : str
        The name of the lookup table

    Returns
    -------
    pl.Expr
        Expression with looked up values
    """
    logger = logging.getLogger("gaspatchio_core.lookup")

    # Handle ColumnProxy objects for lookup_values
    if hasattr(lookup_values, "name") and hasattr(lookup_values, "_parent"):
        lookup_values = pl.col(lookup_values.name)
    elif hasattr(lookup_values, "_expr") and hasattr(lookup_values, "_parent"):
        lookup_values = lookup_values._expr

    # Process key columns
    processed_keys = []
    for i, key in enumerate(key_columns):
        if hasattr(key, "name") and hasattr(key, "_parent"):
            processed_keys.append(pl.col(key.name))
            logger.debug(
                f"Converted key {i} ColumnProxy to col expr: {processed_keys[-1]}"
            )
        elif hasattr(key, "_expr") and hasattr(key, "_parent"):
            processed_keys.append(key._expr)
            logger.debug(
                f"Extracted _expr from key {i} ExpressionProxy: {processed_keys[-1]}"
            )
        else:
            processed_keys.append(key)
            logger.debug(f"Used key {i} as is: {processed_keys[-1]}")

    # Debug: print the current environment
    logger.debug(f"Table name: {table_name}")

    return register_plugin_function(
        args=[lookup_values, *processed_keys],
        plugin_path=LIB,
        function_name="lookup",
        is_elementwise=True,
        kwargs={"table_name": table_name},
    )
