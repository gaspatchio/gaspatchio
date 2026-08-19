# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The deprecated ``gaspatchio_core`` import alias must keep old models running.

Until 1.0, every ``gaspatchio_core`` module must be the *same object* as its
``gaspatchio`` counterpart — not a re-executed copy. A copy would duplicate
module state (accessor registration, the assumption-table registry) and break
``isinstance`` checks across the boundary, which is exactly the silent failure
mode the alias exists to prevent.
"""

from __future__ import annotations

import subprocess
import sys

import gaspatchio
import gaspatchio._internal
import gaspatchio.assumptions
import gaspatchio_core
import gaspatchio_core._internal
import gaspatchio_core.assumptions


def _run_fresh_interpreter(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter so import-time behaviour is observable.

    Import-time effects (the deprecation warning, first-import aliasing) fire
    once per process; the pytest process has long since imported everything.
    """
    return subprocess.run(  # noqa: S603 — fixed argv, test-controlled input
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


class TestAliasIdentity:
    """gaspatchio_core.* must resolve to the very same module objects."""

    def test_top_level_alias_is_same_module(self):
        """`import gaspatchio_core` and `import gaspatchio` name one object."""
        assert gaspatchio_core is gaspatchio

    def test_submodule_alias_is_same_module(self):
        """Submodules alias through — no parallel package tree exists."""
        assert gaspatchio_core.assumptions is gaspatchio.assumptions

    def test_attribute_access_yields_same_class(self):
        """Classes reached via the old name are the same class objects."""
        assert gaspatchio_core.assumptions.Table is gaspatchio.assumptions.Table
        assert gaspatchio_core.ActuarialFrame is gaspatchio.ActuarialFrame

    def test_compiled_extension_aliases(self):
        """The PyO3 extension module aliases like any pure-Python module."""
        assert gaspatchio_core._internal is gaspatchio._internal  # noqa: SLF001

    def test_old_name_first_does_not_duplicate_modules(self):
        """Importing via the old name *first* must not execute a second copy.

        The pytest process has already imported everything under the new name,
        so this scenario — the one every existing model hits — needs a fresh
        interpreter.
        """
        result = _run_fresh_interpreter(
            "import gaspatchio_core.accessors.excel as old\n"
            "import gaspatchio.accessors.excel as new\n"
            "assert old is new, 'alias re-executed the module: state is duplicated'\n"
            "import gaspatchio_core\n"
            "import gaspatchio\n"
            "assert gaspatchio_core is gaspatchio\n",
        )
        assert result.returncode == 0, result.stderr


class TestAliasDeprecationWarning:
    """The old name must warn, loudly enough to steer new code to gaspatchio."""

    def test_import_emits_deprecation_warning(self):
        """A fresh `import gaspatchio_core` raises exactly our warning."""
        result = _run_fresh_interpreter(
            "import warnings\n"
            "with warnings.catch_warnings(record=True) as caught:\n"
            "    warnings.simplefilter('always')\n"
            "    import gaspatchio_core\n"
            "matches = [\n"
            "    w for w in caught\n"
            "    if issubclass(w.category, DeprecationWarning)\n"
            "    and 'gaspatchio_core' in str(w.message)\n"
            "]\n"
            "assert matches, 'importing gaspatchio_core did not warn'\n",
        )
        assert result.returncode == 0, result.stderr

    def test_new_name_does_not_warn(self):
        """The new name imports silently — no deprecation noise for new code."""
        result = _run_fresh_interpreter(
            "import warnings\n"
            "with warnings.catch_warnings(record=True) as caught:\n"
            "    warnings.simplefilter('always')\n"
            "    import gaspatchio\n"
            "matches = [\n"
            "    w for w in caught\n"
            "    if issubclass(w.category, DeprecationWarning)\n"
            "    and 'gaspatchio_core' in str(w.message)\n"
            "]\n"
            "assert not matches, 'importing gaspatchio must not warn'\n",
        )
        assert result.returncode == 0, result.stderr
