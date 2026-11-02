# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Expression analyzer for extracting dependencies from Polars expressions.

This module provides functionality to analyze Polars expressions and extract
the column names they depend on, which is essential for building calculation graphs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from gaspatchio._warning import warn

if TYPE_CHECKING:
    import polars as pl


def extract_dependencies(expr: pl.Expr) -> list[str]:
    """
    Extract column names referenced in a Polars expression.

    This function uses Polars' built-in meta.root_names() API to extract
    column dependencies accurately. It handles:
    - Simple column references: pl.col("x")
    - Multiple columns: pl.col("x") + pl.col("y")
    - Nested expressions: pl.col("x").clip(0, 100)
    - Conditional expressions: pl.when().then().otherwise()
    - Function calls: pl.max("x", "y")
    - Literal values: Returns empty list

    Args:
        expr: A Polars expression to analyze

    Returns:
        A sorted list of unique column names referenced in the expression

    Raises:
        RuntimeError: If Polars version is too old and doesn't support meta.root_names()

    """
    try:
        # Use Polars' built-in meta.root_names() method
        # This is the proper way to extract column dependencies
        dependencies = expr.meta.root_names()
        logger.trace(f"Extracted dependencies using meta.root_names(): {dependencies}")

        # Sort for consistent output
        return sorted(dependencies)

    except AttributeError as e:
        # meta.root_names() not available - Polars version is too old
        msg = (
            "Polars version is too old. The calculation graph feature requires "
            "expr.meta.root_names() which is not available in your version. "
            "Please upgrade Polars to use this feature."
        )
        raise RuntimeError(msg) from e

    except Exception as e:  # noqa: BLE001 -- the documented failure mode of this public helper: an expression the meta API cannot walk returns [] and says so as a GaspatchioWarning (test_dependencies_that_cannot_be_read_are_not_returned_in_silence)
        warn(
            f"The columns this expression reads could not be found through "
            f"Polars' meta API, so none are returned: {e}. Pass a Polars "
            f'expression built from columns, such as pl.col("age") * 2.'
        )
        return []


def analyze_expression_tree(expr: pl.Expr) -> dict[str, list[str] | bool | str]:
    """
    Analyze an expression using only Polars meta API.

    This function extracts information about a Polars expression using only
    the official meta API methods, avoiding any string-based parsing.

    Args:
        expr: A Polars expression to analyze

    Returns:
        A dictionary containing:
        - dependencies: List of column names the expression depends on
        - is_literal: Whether the expression is a literal value
        - output_name: The output column name, present only where Polars can
          determine it without a schema
        - has_multiple_outputs: Whether expression expands to multiple columns

    """
    # Always include dependencies
    result: dict[str, list[str] | bool | str] = {
        "dependencies": extract_dependencies(expr)
    }

    # None of these three raises on a Polars expression: is_literal and
    # has_multiple_outputs answer a bool, and output_name answers None for an
    # expression whose name depends on a schema it has not been given.
    result["is_literal"] = expr.meta.is_literal()
    output_name = expr.meta.output_name(raise_if_undetermined=False)
    if output_name is not None:
        result["output_name"] = output_name
    result["has_multiple_outputs"] = expr.meta.has_multiple_outputs()
    return result
