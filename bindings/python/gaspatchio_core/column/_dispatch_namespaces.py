# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Namespace proxying for Polars expression namespaces.

This module owns the "attribute is a namespace" branch of proxy dispatch.
It does not decide list routing or autopatching; it only exposes the generic
and specialized namespace adapters.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ._dispatch_common import _get_proxy_base_expr, _unwrap, _wrap
from .namespaces.dt_proxy import DtNamespaceProxy
from .namespaces.string_proxy import StringNamespaceProxy

if TYPE_CHECKING:
    from .column_proxy import ColumnProxy
    from .expression_proxy import ExpressionProxy

    ProxyType = ColumnProxy | ExpressionProxy


_NAMESPACES: set[str] = {
    "dt",
    "str",
    "list",
    "arr",
    "struct",
    "cat",
    "bin",
}


SPECIALIZED_NAMESPACES = {
    "dt": lambda parent_proxy, parent_af: DtNamespaceProxy(parent_proxy, parent_af),
    "str": lambda parent_proxy, parent_af: StringNamespaceProxy(
        parent_proxy, parent_af
    ),
}


def get_generic_namespace_proxy(
    proxy: "ProxyType",
    namespace_name: str,
) -> GenericNamespaceProxy:
    """Build a generic namespace proxy for non-specialized namespaces."""
    return GenericNamespaceProxy(proxy, namespace_name)


class GenericNamespaceProxy:
    """A generic proxy for Polars expression namespaces (list, arr, struct, etc.)."""

    def __init__(self, parent_proxy: "ProxyType", namespace_name: str) -> None:
        self._parent_proxy = parent_proxy
        self._namespace_name = namespace_name
        self._parent_af = getattr(parent_proxy, "_parent", None)
        self._base_expr = _get_proxy_base_expr(parent_proxy)
        self._namespace_obj = self._get_namespace_obj()

    def _get_namespace_obj(self) -> Any:  # noqa: ANN401
        """Get the actual Polars namespace object."""
        try:
            return getattr(self._base_expr, self._namespace_name)
        except AttributeError as err:
            msg = f"Base expression has no namespace '{self._namespace_name}'"
            raise AttributeError(msg) from err

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """Delegate method calls to the actual Polars namespace object."""
        try:
            actual_method = getattr(self._namespace_obj, name)
        except AttributeError as err:
            msg = f"Polars namespace '{self._namespace_name}' has no attribute '{name}'"
            raise AttributeError(msg) from err

        if not callable(actual_method):
            msg = (
                f"Attribute '{name}' on namespace '{self._namespace_name}' not callable"
            )
            raise TypeError(msg)

        @functools.wraps(actual_method)
        def namespace_method_caller(
            *args: Any,  # noqa: ANN401
            **kwargs: Any,  # noqa: ANN401
        ) -> Any:  # noqa: ANN401
            unwrapped_args = [_unwrap(arg) for arg in args]
            unwrapped_kwargs = {key: _unwrap(val) for key, val in kwargs.items()}

            try:
                result = actual_method(*unwrapped_args, **unwrapped_kwargs)
            except Exception as e:
                msg = f"Error in '{self._namespace_name}.{name}': {e}"
                raise type(e)(msg) from e

            return _wrap(self._parent_af, result)

        return namespace_method_caller


def is_namespace_name(name: str) -> bool:
    """Return True if the attribute name is a known Polars namespace."""
    return name in _NAMESPACES
