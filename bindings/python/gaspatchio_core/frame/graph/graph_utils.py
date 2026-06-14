# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Utility functions for calculation graph operations.
"""

import re


def clean_expression_string(expr_str: str) -> str:
    """
    Clean up expression strings by removing file paths.
    
    Args:
        expr_str: Raw expression string
        
    Returns:
        Cleaned expression string
    """
    # Pattern to match file paths in the expression
    path_pattern = r'\.?/[\w/\-\.]+\.(py|so|cpython[^:]+):'
    expr_str = re.sub(path_pattern, '.', expr_str)
    
    # Clean up internal function patterns
    expr_str = re.sub(r'\.gaspatchio_core\._internal[^:]+:', '.', expr_str)
    
    return expr_str


def simplify_dtype(dtype_str: str) -> str:
    """
    Simplify Polars dtype string for cleaner display.
    
    Args:
        dtype_str: Polars data type string
        
    Returns:
        Simplified type name
    """
    type_map = {
        "Int64": "int",
        "Int32": "int",
        "Float64": "float",
        "Float32": "float",
        "Utf8": "string",
        "Boolean": "bool",
        "Date": "date",
        "Datetime": "datetime",
        "Duration": "duration",
        "List": "list",
    }
    
    for polars_type, simple_type in type_map.items():
        if dtype_str.startswith(polars_type):
            return simple_type
    
    return dtype_str.lower()