# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Compatibility facade for proxy dispatch internals.

The real implementations now live in:
- ``_dispatch_common.py`` for shared helpers
- ``_dispatch_namespaces.py`` for namespace proxying
- ``_dispatch_execution.py`` for execution/routing
- ``_dispatch_autopatch.py`` for descriptor/autopatch wiring
"""

from ._dispatch_autopatch import DelegatorDescriptor, _autopatch
from ._dispatch_common import (
    _ensure_polars_expr_or_literal,
    _get_proxy_base_expr,
    _unwrap,
    _unwrap_for_arithmetic,
    _wrap,
)
from ._dispatch_execution import (
    _ARITHMETIC_OPS,
    _BACKEND_LIST_OPS,
    _NUMERIC_ELEMENTWISE,
    _NUMERIC_UNARY,
    ErrorEnhancer,
    _execute_list_shim,
    _execute_regular,
    _has_column_operands,
    _method_caller,
    _should_use_list_shim,
    capture_source_context,
)
from ._dispatch_namespaces import (
    SPECIALIZED_NAMESPACES,
    _NAMESPACES,
    GenericNamespaceProxy,
)

__all__ = [
    "_ARITHMETIC_OPS",
    "_BACKEND_LIST_OPS",
    "_NAMESPACES",
    "_NUMERIC_ELEMENTWISE",
    "_NUMERIC_UNARY",
    "ErrorEnhancer",
    "GenericNamespaceProxy",
    "SPECIALIZED_NAMESPACES",
    "DelegatorDescriptor",
    "_autopatch",
    "_ensure_polars_expr_or_literal",
    "_execute_list_shim",
    "_execute_regular",
    "_get_proxy_base_expr",
    "_has_column_operands",
    "_method_caller",
    "_should_use_list_shim",
    "_unwrap",
    "_unwrap_for_arithmetic",
    "_wrap",
    "capture_source_context",
]
