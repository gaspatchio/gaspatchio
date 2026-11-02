# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Recognize callable operations without importing an execution backend.

Built-ins come from the semantic vocabulary. Extensions publish a live collection
of names, so a custom backend's registration/removal remains visible without a
second independently maintained set. Recognition says what a formula means;
backend dispatch separately decides whether that engine can compute it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio._semantic.vocabulary import VOCABULARY

if TYPE_CHECKING:
    from collections.abc import Container

_BUILTIN_CALLS = frozenset(op.identifier for op in VOCABULARY if op.node_kind == "call")
_ENGINE_CALLS: dict[str, Container[str]] = {}


def register_engine_calls(engine: str, names: Container[str]) -> None:
    """Publish a backend's live call registry without importing that backend.

    Re-publishing the same collection is harmless. Replacing another collection
    under the same engine name would silently hide its extensions and is refused.
    """
    if engine in _ENGINE_CALLS and _ENGINE_CALLS[engine] is not names:
        msg = f"{engine!r} already has a call registry. Update its existing collection."
        raise ValueError(msg)
    _ENGINE_CALLS[engine] = names


def is_known_call(name: str) -> bool:
    """Recognize a built-in call or one currently supplied by an extension."""
    return name in _BUILTIN_CALLS or any(
        name in names for names in _ENGINE_CALLS.values()
    )
