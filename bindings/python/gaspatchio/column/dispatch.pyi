# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Type stubs for dispatch.py."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

# Use forward references for types defined elsewhere to avoid circular imports
if TYPE_CHECKING:
    from ..frame.base import ActuarialFrame
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

# Constants
_NUMERIC_UNARY: set[str]
_NUMERIC_ELEMENTWISE: set[str]
_NAMESPACES: set[str]

# Helper Functions
def _unwrap(arg: Any) -> Any: ...
def _wrap(parent: ActuarialFrame | None, result: Any) -> Any: ...
def _ensure_polars_expr_or_literal(arg: Any) -> Any: ...

# Descriptor
class DelegatorDescriptor:
    name: str
    wrapper_logic: Callable[..., Any]

    def __init__(self, name: str) -> None: ...
    def __get__(
        self, instance: ColumnProxy | ExpressionProxy | None, owner: type[ColumnProxy | ExpressionProxy] | None = None
    ) -> Any: ...

# Wrapper Factory
def _make_wrapper(name: str) -> Callable[..., Any]: ...

# Autopatching Function
def _autopatch(proxy_cls: type[ColumnProxy | ExpressionProxy]) -> None: ...
