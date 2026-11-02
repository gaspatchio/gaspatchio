# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Fixtures that keep one test's stub engine out of the next test's process.

Discovery writes into two process-wide dictionaries and imports provider
modules into ``sys.modules``. A test that leaves either moved leaves the
next test reading a name it never asked for, which is the order-sensitivity
this whole directory would otherwise be built on.

The file sink's writer runs on a thread of its own, and a test that leaves
one running is a failure of that test and of no other: each test is given a
bounded time to let its writers end, and a writer an earlier test left behind
is not counted against a later one.
"""

from __future__ import annotations

import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from gaspatchio.engines import PROVIDERS, REGISTERED_ENGINES, protocol

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _discovery_is_restored() -> Iterator[None]:
    """Put discovery's two dictionaries and ``sys.modules`` back afterwards."""
    providers = dict(PROVIDERS)
    engines = dict(REGISTERED_ENGINES)
    modules = set(sys.modules)
    yield
    PROVIDERS.clear()
    PROVIDERS.update(providers)
    REGISTERED_ENGINES.clear()
    REGISTERED_ENGINES.update(engines)
    for name in set(sys.modules) - modules:
        if name.endswith("_engine") or name.startswith("stub_"):
            del sys.modules[name]


# The threads alive when the running test began. A writer an earlier test left
# running is that test's failure, and is not counted against this one.
_ALIVE_BEFORE: set[threading.Thread] = set()

# How long, in seconds, a test's writers may take to end once the test is over,
# and how long a writer may go without taking a row or writing a byte before
# the sink stops waiting on it -- a minute in a run, where nothing a test here
# writes takes a second.
_WRITERS_END_WITHIN = 15.0
_PATIENCE_UNDER_TEST = 10.0


def writers() -> list[str]:
    """Return the file sink's writer threads this test started and left running."""
    return sorted(
        one.name
        for one in threading.enumerate()
        if one.name.startswith(protocol._WRITER)  # noqa: SLF001 -- the sink's own name for them
        and one not in _ALIVE_BEFORE
    )


@pytest.fixture(autouse=True)
def _no_writer_outlives_its_test(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail a test that leaves a writer running, once it has had time to end.

    Every wait here is bounded: the sink's own waits by the patience it is
    given under test, and this one by :data:`_WRITERS_END_WITHIN`. A test
    whose writer never ends fails in seconds, rather than hanging the run.
    """
    monkeypatch.setattr(protocol, "_PATIENCE", _PATIENCE_UNDER_TEST)
    _ALIVE_BEFORE.clear()
    _ALIVE_BEFORE.update(threading.enumerate())
    yield
    deadline = time.monotonic() + _WRITERS_END_WITHIN
    while writers() and time.monotonic() < deadline:
        time.sleep(0.05)
    left = writers()
    if left:
        pytest.fail(
            f"{len(left)} of the file sink's writer threads outlived this test "
            f"by {_WRITERS_END_WITHIN:.0f} s: {left}"
        )
