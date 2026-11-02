# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Column submodule, providing proxy classes for interacting with Polars expressions."""

# The escape a column or expression opens into Polars, and the namespaces a
# column carries, are documented with it; this is where they are imported from.
from gaspatchio._authoring.escape import (
    PolarsNative,
    PolarsNativeDate,
    PolarsNativeString,
)

from ._generated_proxy import ListNamespace, StringNamespace
from .column_proxy import ColumnProxy
from .condition_expression import ConditionExpression
from .expression_proxy import ExpressionProxy

__all__ = [
    "ColumnProxy",
    "ConditionExpression",
    "ExpressionProxy",
    "ListNamespace",
    "PolarsNative",
    "PolarsNativeDate",
    "PolarsNativeString",
    "StringNamespace",
]
