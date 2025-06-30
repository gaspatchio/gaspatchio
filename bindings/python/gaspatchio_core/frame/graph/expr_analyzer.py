"""
Expression analyzer for extracting dependencies from Polars expressions.

This module provides functionality to analyze Polars expressions and extract
the column names they depend on, which is essential for building calculation graphs.
"""

from __future__ import annotations

import polars as pl
from loguru import logger


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
        logger.error(f"meta.root_names() not available: {e}")
        logger.error("This feature requires a recent version of Polars.")
        logger.error("Please upgrade Polars: pip install --upgrade polars")
        raise RuntimeError(
            "Polars version is too old. The calculation graph feature requires "
            "expr.meta.root_names() which is not available in your version. "
            "Please upgrade Polars to use this feature."
        ) from e
        
    except Exception as e:
        # Handle any other errors from the meta API
        logger.warning(f"Failed to extract dependencies using meta API: {e}")
        logger.warning("Returning empty dependency list")
        return []




def analyze_expression_tree(expr: pl.Expr) -> dict:
    """
    Analyze an expression using only Polars meta API.
    
    This function extracts information about a Polars expression using only
    the official meta API methods, avoiding any string-based parsing.
    
    Args:
        expr: A Polars expression to analyze
        
    Returns:
        A dictionary containing:
        - dependencies: List of column names the expression depends on
        - is_literal: Whether the expression is a literal value (if available)
        - output_name: The output column name (if determinable)
        - has_multiple_outputs: Whether expression expands to multiple columns (if available)
        
    Note:
        Only fields that can be reliably determined via the Polars meta API
        are included in the result. Missing fields indicate the information
        is not available through the API.
    """
    # Always include dependencies
    result = {
        "dependencies": extract_dependencies(expr)
    }
    
    # Try to get is_literal from meta API
    try:
        result["is_literal"] = expr.meta.is_literal()
    except Exception as e:
        logger.trace(f"Could not determine is_literal: {e}")
        
    # Try to get output name
    try:
        output_name = expr.meta.output_name(raise_if_undetermined=False)
        if output_name is not None:
            result["output_name"] = output_name
    except Exception as e:
        logger.trace(f"Could not determine output_name: {e}")
        
    # Try to get has_multiple_outputs
    try:
        result["has_multiple_outputs"] = expr.meta.has_multiple_outputs()
    except Exception as e:
        logger.trace(f"Could not determine has_multiple_outputs: {e}")
    
    return result