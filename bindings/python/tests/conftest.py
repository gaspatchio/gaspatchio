# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Top-level test fixtures for gaspatchio.

This conftest installs autouse fixtures that snapshot and restore the
process-global execution settings around every test.

Why, for mode + verbose: several tests change `gaspatchio.util`'s default
mode and verbosity (e.g. tests/frame/test_tracing.py,
tests/util/test_utils.py, tests/integration/test_mode_parity_smoke.py,
tests/test_core.py). Some restore in try/finally; others do not. When a
polluting test leaves mode='optimize', subsequent tests that call
`pl.Expr.map_elements` (notably Schedule.from_inception) hit the telemetry
wrapper which sys.exit(1)s in optimize mode, aborting the run.

Why, for the error mode: `set_error_mode()` writes both the module global and
the `AF_ERROR_MODE` environment variable, and `get_error_mode()` reads the
environment first. A test that lowers the mode therefore lowers it for every
test that runs after it in the same process, whatever file it lives in --
`pytest tests/frame tests/errors` left `AF_ERROR_MODE=basic` behind and the
attribution tests, which are enhanced-tier machinery, stopped attributing.
Running the same two directories the other way round passed, which is what made
it look like a flake rather than leaked state.

These fixtures eliminate that whole class of test-order sensitivity. They do
not change behaviour for tests that leave the settings alone.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

# Help-text tests read the CLI's plain words. Typer forces a colour terminal
# when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, reading it once when
# typer.rich_utils is imported, and the escape codes then split `--results`
# into pieces no substring check finds -- green on a laptop, red on CI.
# `_TYPER_FORCE_DISABLE_TERMINAL` is Typer's own switch for this; set it before
# anything imports Typer, and reset the constant in case a plugin already did.
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
if "typer.rich_utils" in sys.modules:
    sys.modules["typer.rich_utils"].FORCE_TERMINAL = False

from loguru import logger

from gaspatchio.util import (
    _ERROR_MODES,
    get_default_mode,
    get_default_verbose,
    get_error_mode,
    set_default_mode,
    set_default_verbose,
    set_error_mode,
)

# The package mutes its own log records when it is imported, as a library
# should, and many tests here read those records through a sink of their
# own. So the session turns them on, the way an application does, once the
# package has been imported above. That library use stays quiet is tested in
# a fresh interpreter, in tests/test_library_logging.py.
logger.enable("gaspatchio")

if TYPE_CHECKING:
    from collections.abc import Iterator

# What `set_error_mode()` accepts, read from the one place it is spelled; the
# fixture only needs to know whether a snapshot is safe to hand back.
_VALID_ERROR_MODES = _ERROR_MODES


@pytest.fixture(autouse=True)
def _restore_global_mode_and_verbose() -> object:
    """Snapshot/restore default mode + verbose around every test."""
    saved_mode = get_default_mode()
    saved_verbose = get_default_verbose()
    yield
    set_default_mode(saved_mode)
    set_default_verbose(saved_verbose)


@pytest.fixture(autouse=True)
def _restore_error_mode() -> Iterator[None]:
    """Snapshot/restore the error mode -- global and environment -- per test.

    The error mode lives in two places and the two halves are restored
    separately. `set_error_mode()` writes the module global and the
    `AF_ERROR_MODE` environment variable; `get_error_mode()` prefers the
    variable when it is set and falls back to the global when it is not, so
    putting one back alone still leaks the other.

    The global half goes first, through `set_error_mode()` -- which also writes
    the variable, and which rejects anything that is not a real mode, so it is
    only called when the snapshot is a value it will accept. A stray
    `AF_ERROR_MODE=whatever` in a developer's environment therefore leaves the
    global alone rather than erroring out of every test's teardown.

    The environment half goes last and is authoritative: the variable is put
    back to exactly what it was, including absent, over whatever
    `set_error_mode()` just wrote.
    """
    saved_env = os.environ.get("AF_ERROR_MODE")
    saved_mode = get_error_mode()
    yield
    if saved_mode in _VALID_ERROR_MODES:
        set_error_mode(saved_mode)
    if saved_env is None:
        os.environ.pop("AF_ERROR_MODE", None)
    else:
        os.environ["AF_ERROR_MODE"] = saved_env
