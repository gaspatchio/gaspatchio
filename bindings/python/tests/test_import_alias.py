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

import importlib.util
import subprocess
import sys
import tempfile
from types import CodeType

import gaspatchio
import gaspatchio._internal
import gaspatchio.assumptions
import gaspatchio_core
import gaspatchio_core._internal
import gaspatchio_core.assumptions


def _run_python(*argv: str) -> subprocess.CompletedProcess[str]:
    """Run the interpreter with ``argv`` from a neutral temporary cwd.

    ``sys.path[0]`` is the child's cwd, so running from ``bindings/python``
    would resolve the packages from the source tree and validate the tree
    instead of the installed distribution these tests exist to check.
    """
    with tempfile.TemporaryDirectory() as neutral_cwd:
        return subprocess.run(  # noqa: S603 — fixed argv, test-controlled input
            [sys.executable, *argv],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            cwd=neutral_cwd,
        )


def _run_fresh_interpreter(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter so import-time behaviour is observable.

    Import-time effects (the deprecation warning, first-import aliasing) fire
    once per process; the pytest process has long since imported everything.
    """
    return _run_python("-c", code)


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

    def test_runner_model_load_surfaces_the_warning(self, tmp_path):
        """`gspio run-model` on an old-name model must show the warning.

        Models load as "model_module", not __main__, so PEP 565's default
        filters would hide the DeprecationWarning from exactly the audience
        the shim exists to migrate — the runner installs a message-anchored
        filter to surface it.
        """
        model = tmp_path / "old_model.py"
        model.write_text(
            "import gaspatchio_core\n\n\ndef life_model(af):\n    return af\n",
        )
        result = _run_fresh_interpreter(
            "from gaspatchio.runner import load_model_from_path\n"
            f"load_model_from_path({str(model)!r}, 'life_model')\n",
        )
        assert result.returncode == 0, result.stderr
        assert "deprecated" in result.stderr, (
            "the CLI model-load path swallowed the deprecation warning:\n"
            + result.stderr
        )


class TestAliasHonesty:
    """The alias must not invent modules, mislabel errors, or break -m."""

    def test_find_spec_reports_no_phantom_modules(self):
        """Probing a nonexistent old-name module must say 'not found'."""
        spec = importlib.util.find_spec("gaspatchio_core.definitely_not_real")
        assert spec is None

    def test_missing_submodule_error_names_the_old_path(self):
        """A typo'd old-name import must error about the name the user typed."""
        result = _run_fresh_interpreter("import gaspatchio_core.assumtions\n")
        assert result.returncode != 0
        assert "gaspatchio_core.assumtions" in result.stderr
        assert "gaspatchio.assumtions'" not in result.stderr

    def test_dash_m_on_the_package_gives_the_standard_error(self):
        """`python -m gaspatchio_core` must not crash inside runpy."""
        result = _run_python("-m", "gaspatchio_core")
        assert "AttributeError" not in result.stderr
        assert "gaspatchio_core.__main__" in result.stderr

    def test_loader_provides_code_objects_for_dash_m(self):
        """`python -m gaspatchio_core.x` needs get_code on the alias loader."""
        spec = importlib.util.find_spec("gaspatchio_core.cli")
        assert spec is not None
        assert spec.loader is not None
        code = spec.loader.get_code("gaspatchio_core.cli")
        assert isinstance(code, CodeType)

    def test_failed_real_import_leaves_no_finder_behind(self):
        """If the real package can't import, the shim must fail whole.

        An orphaned meta-path finder would silently serve a same-process
        retry of the old name without ever re-running the shim body (and
        its deprecation warning).
        """
        result = _run_fresh_interpreter(
            "import sys\n"
            "# Poison the real package so the shim's own import of it fails.\n"
            "sys.modules['gaspatchio'] = None\n"
            "try:\n"
            "    import gaspatchio_core\n"
            "except ImportError:\n"
            "    pass\n"
            "else:\n"
            "    raise SystemExit('shim import unexpectedly succeeded')\n"
            "finders = [f for f in sys.meta_path if 'Alias' in type(f).__name__]\n"
            "assert not finders, f'orphaned alias finder left behind: {finders}'\n",
        )
        assert result.returncode == 0, result.stderr
