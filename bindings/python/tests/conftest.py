# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Top-level test fixtures for gaspatchio_core.

This conftest installs an autouse fixture that snapshots and restores
the process-global default mode + verbose flags around every test.

Why: several tests mutate `gaspatchio_core.util._DEFAULT_MODE` and
`_DEFAULT_VERBOSE` (e.g. tests/frame/test_tracing.py, tests/util/test_utils.py,
tests/integration/test_mode_parity_smoke.py, tests/test_core.py). Some restore
in try/finally; others do not. When a polluting test leaves mode='optimize',
subsequent tests that call `pl.Expr.map_elements` (notably Schedule.from_inception)
hit the telemetry wrapper which sys.exit(1)s in optimize mode, aborting the run.

This fixture eliminates that whole class of test-order sensitivity. It does
not change behaviour for tests that don't touch mode/verbose.
"""

from __future__ import annotations

import pytest

from gaspatchio_core.util import (
    get_default_mode,
    get_default_verbose,
    set_default_mode,
    set_default_verbose,
)


@pytest.fixture(autouse=True)
def _restore_global_mode_and_verbose() -> object:
    """Snapshot/restore default mode + verbose around every test."""
    saved_mode = get_default_mode()
    saved_verbose = get_default_verbose()
    yield
    set_default_mode(saved_mode)
    set_default_verbose(saved_verbose)
