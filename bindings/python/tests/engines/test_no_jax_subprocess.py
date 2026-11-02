# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The core loads no engine's dependencies, proved in a process of its own.

An actuary who installed gaspatchio to run a model installed a model runner.
The seam knows the names of engines it has never loaded, and the whole of
that claim is that importing the core -- package, seam and command line --
puts nothing of an engine into the interpreter.

In a subprocess rather than in this one, because this test session has
imported stub providers and engine modules of its own by the time it runs,
and a reading taken inside it would be a reading of the test suite rather
than of the package.
"""

from __future__ import annotations

import subprocess
import sys


def test_the_core_never_imports_jax() -> None:
    code = (
        "import gaspatchio, gaspatchio.engines, gaspatchio.cli, sys; "
        "print(sorted(m for m in sys.modules "
        "if m.startswith(('jax', 'gaspatchio_jax'))))"
    )

    out = subprocess.run(  # noqa: S603 -- this interpreter, a fixed argument list
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert out.strip() == "[]"
