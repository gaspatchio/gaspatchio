# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Whose lifecycle a registered assumption table is on.

An assumption table registered under a name it already had, with different
data, warns: the native kernel refuses the lazy lookups built against the
earlier data, and a user who still holds one needs to hear that before the
collect that fails. Some tables are the framework's own, though. A scenario
run stacks each base table across the scenarios of one batch, composes that
batch, collects it and only then stacks the next batch under the same name.
Nothing built against a batch's table outlives the batch, so there is no
lookup left to go stale and nothing to tell the user. A table registered
inside :func:`framework_owned_tables` is on that lifecycle and does not warn
when it replaces itself.

It lives apart from both packages that use it: the assumption table reads
it and the scenario run sets it, and each already imports the other's
neighbourhood.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_FRAMEWORK_OWNED: ContextVar[bool] = ContextVar("framework_owned_tables", default=False)


@contextmanager
def framework_owned_tables() -> Iterator[None]:
    """Register the tables built inside this block as the framework's own.

    Use it only where the framework collects everything built against a
    table before it registers that name again.
    """
    token = _FRAMEWORK_OWNED.set(True)
    try:
        yield
    finally:
        _FRAMEWORK_OWNED.reset(token)


def registering_framework_owned() -> bool:
    """Whether a table registered now is the framework's own."""
    return _FRAMEWORK_OWNED.get()


__all__ = ["framework_owned_tables", "registering_framework_owned"]
