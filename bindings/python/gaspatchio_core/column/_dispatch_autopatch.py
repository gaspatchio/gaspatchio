# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Autopatch and descriptor layer for proxy dispatch.

This module owns the reflective wiring that makes ColumnProxy and
ExpressionProxy look like Polars expressions.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Optional

import polars as pl
from loguru import logger

from ._dispatch_common import _get_proxy_base_expr, _wrap
from ._dispatch_execution import _method_caller
from ._dispatch_namespaces import (
    SPECIALIZED_NAMESPACES,
    get_generic_namespace_proxy,
    is_namespace_name,
)

if TYPE_CHECKING:
    from ._dispatch_common import ProxyType
    from gaspatchio_core.frame.base import ActuarialFrame


class DelegatorDescriptor:
    """Descriptor that enables transparent delegation to Polars objects."""

    def __init__(self, name: str) -> None:
        """Initialize the descriptor with the attribute name."""
        self.name = name
        self.wrapper_logic = _make_wrapper(self.name)

    def __get__(
        self, instance: Optional["ProxyType"], owner: type["ProxyType"] | None = None
    ) -> Any:  # noqa: ANN401
        """Handle attribute access on the proxy instance or class."""
        if instance is None:
            return self.wrapper_logic

        if self.name in SPECIALIZED_NAMESPACES:
            parent_af = getattr(instance, "_parent", None)
            return SPECIALIZED_NAMESPACES[self.name](instance, parent_af)

        return self.wrapper_logic(instance)


def _create_method_wrapper(
    name: str,
    polars_attr: Callable,
    self_proxy: "ProxyType",
    parent_af: Optional["ActuarialFrame"],
    base_expr: pl.Expr,
) -> Callable:
    """Create a wrapper for a Polars method."""

    def method_wrapper(
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        return _method_caller(
            name=name,
            polars_attr=polars_attr,
            self_proxy=self_proxy,
            parent_af=parent_af,
            base_expr=base_expr,
            a=args,
            kw=kwargs,
        )

    try:
        method_wrapper.__doc__ = getattr(
            polars_attr, "__doc__", f"Proxied Polars method: {name}"
        )
    except AttributeError:
        method_wrapper.__doc__ = f"Proxied Polars method: {name}"

    return method_wrapper


def _make_wrapper(name: str) -> Callable[..., Any]:
    """Create the core logic function used by DelegatorDescriptor."""

    def wrapper(
        self_proxy: "ProxyType",
        *args: Any,  # noqa: ANN401
        **kwargs: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Handle attribute access on proxy objects."""
        parent_af = getattr(self_proxy, "_parent", None)

        base_expr = _get_proxy_base_expr(self_proxy)
        try:
            polars_attr = getattr(base_expr, name)
        except AttributeError as e:
            proxy_type_name = type(self_proxy).__name__
            msg = f"'{proxy_type_name}' has no attribute '{name}': {e}"
            raise AttributeError(msg) from e

        if callable(polars_attr):
            return _create_method_wrapper(
                name, polars_attr, self_proxy, parent_af, base_expr
            )

        if args or kwargs:
            msg = f"Attribute '{name}' is not callable and cannot accept arguments."
            raise TypeError(msg)

        if is_namespace_name(name) and name not in SPECIALIZED_NAMESPACES:
            return get_generic_namespace_proxy(self_proxy, name)

        return _wrap(parent_af, polars_attr)

    wrapper.__name__ = f"proxied_{name}"
    return wrapper


def _autopatch(proxy_cls: type["ProxyType"]) -> None:
    """Dynamically add Polars expression methods to proxy classes."""
    processed_attrs: set[str] = set()
    attrs_to_process = dir(pl.Expr) + list(_dispatch_namespace_names())

    for attr_name in set(attrs_to_process):
        is_internal = attr_name.startswith("_") and not (
            attr_name.startswith("__") and attr_name.endswith("__")
        )

        if is_internal or attr_name in processed_attrs or hasattr(proxy_cls, attr_name):
            if attr_name in ["apply", "map_elements", "map_batches"]:
                logger.trace(
                    f"TRACE: Skipping {attr_name} because: "
                    + (
                        "internal"
                        if is_internal
                        else "already processed"
                        if attr_name in processed_attrs
                        else "exists on proxy class"
                    )
                )
            processed_attrs.add(attr_name)
            continue

        try:
            setattr(proxy_cls, attr_name, DelegatorDescriptor(attr_name))
            processed_attrs.add(attr_name)
        except AttributeError as e:
            logger.warning(
                f"Skipping autopatch for '{attr_name}' on {proxy_cls.__name__}: {e}"
            )

    original_dir = getattr(proxy_cls, "__dir__", object.__dir__)

    def enhanced_dir(self: "ProxyType") -> list[str]:
        """Return all attributes on this proxy, including dynamic Polars attrs."""
        dynamic_attrs = {attr for attr in processed_attrs if hasattr(proxy_cls, attr)}
        return sorted(set(original_dir(self)) | dynamic_attrs)

    setattr(proxy_cls, "__dir__", enhanced_dir)


def _dispatch_namespace_names() -> set[str]:
    """Return all namespace names that should be reflectively exposed."""
    return {
        "dt",
        "str",
        "list",
        "arr",
        "struct",
        "cat",
        "bin",
    }
