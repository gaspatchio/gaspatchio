# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Deprecated import alias for :mod:`gaspatchio` — removed in 1.0.

The import name used to follow the repository (``gaspatchio-core``) rather
than the product. The import name is now ``gaspatchio``, matching the PyPI
name and the documentation. This package exists only so models written
against the old name keep running.

Every ``gaspatchio_core`` module is registered as the *same module object* as
its ``gaspatchio`` counterpart — the loader below returns the already-imported
real module instead of executing a copy. A copy would re-run registration
side effects and split module state (the assumption-table registry, accessor
registration), which is exactly the silent divergence this alias must never
introduce.

Two deliberate limits, stated here because they are the boundary of the
promise:

- **Runtime only.** Static type checkers (mypy, pyright) resolve names from
  files, not from a meta-path finder, so typed code must import ``gaspatchio``
  directly to keep its types.
- **A narrow identity window.** While a ``gaspatchio_core.x`` import is in
  flight, the import machinery stamps the alias spec onto the real module and
  ``exec_module`` restores the original; an abort (e.g. KeyboardInterrupt)
  landing inside that window leaves ``__spec__`` pointing at the alias, which
  breaks ``importlib.reload`` for that one module in the running session.
  Accepted: the window is microseconds on the first import of each aliased
  submodule, and the loader protocol offers no hook to close it.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec
    from types import CodeType, ModuleType

_OLD_NAME = "gaspatchio_core"
_NEW_NAME = "gaspatchio"

warnings.warn(
    "The 'gaspatchio_core' import name is deprecated and will be removed in "
    "1.0 — write 'import gaspatchio' instead (the import name now matches the "
    "package name). Existing code keeps working unchanged at runtime; static "
    "type checkers resolve only the new name, so rename imports in typed code.",
    DeprecationWarning,
    stacklevel=2,
)


def _real_name_for(fullname: str) -> str:
    """Map a deprecated ``gaspatchio_core[.x]`` name to its real module name."""
    return _NEW_NAME + fullname[len(_OLD_NAME) :]


class _AliasLoader(importlib.abc.Loader):
    """Hand the import machinery the real gaspatchio module, never a copy."""

    def __init__(self, real_name: str) -> None:
        self._real_name = real_name
        self._real_attrs: dict[str, object] = {}

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        """Return the already-imported real module for this alias spec."""
        del spec  # the alias spec; the real module keeps its own
        try:
            module = importlib.import_module(self._real_name)
        except ModuleNotFoundError as exc:
            if exc.name != self._real_name:
                # A genuinely missing third-party module inside the real
                # module's body — not ours to reword.
                raise
            old_name = _OLD_NAME + self._real_name[len(_NEW_NAME) :]
            msg = (
                f"No module named '{old_name}'. (The deprecated "
                f"'gaspatchio_core' alias resolves it to '{self._real_name}', "
                "which does not exist either — the import name is now "
                "'gaspatchio'.)"
            )
            raise ModuleNotFoundError(msg, name=old_name) from exc
        # The machinery stamps the alias spec onto whatever create_module
        # returns; snapshot the real identity so exec_module can restore it.
        self._real_attrs = {
            name: getattr(module, name)
            for name in ("__spec__", "__loader__", "__name__", "__package__")
            if hasattr(module, name)
        }
        return module

    def exec_module(self, module: ModuleType) -> None:
        """Restore the real module's identity; it is already executed."""
        for name, value in self._real_attrs.items():
            setattr(module, name, value)

    def get_code(self, fullname: str) -> CodeType | None:
        """Delegate to the real loader so ``python -m gaspatchio_core.x`` runs."""
        real_name = _real_name_for(fullname)
        spec = importlib.util.find_spec(real_name)
        if spec is None or spec.loader is None:
            msg = f"no code object available for '{fullname}'"
            raise ImportError(msg, name=fullname)
        real_get_code = getattr(spec.loader, "get_code", None)
        if real_get_code is None:
            msg = f"loader for '{real_name}' provides no code object"
            raise ImportError(msg, name=fullname)
        code: CodeType | None = real_get_code(real_name)
        return code


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Route any ``gaspatchio_core[.x]`` import to the ``gaspatchio[.x]`` module."""

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        """Match the deprecated prefix and alias it to the real module."""
        del path, target  # finder-protocol arguments; only the name matters
        if fullname != _OLD_NAME and not fullname.startswith(_OLD_NAME + "."):
            return None
        real_name = _real_name_for(fullname)
        # Only claim names whose real module actually exists — otherwise
        # importlib.util.find_spec() would report phantom modules and
        # feature-probing code would take the wrong branch.
        try:
            real_spec = importlib.util.find_spec(real_name)
        except ModuleNotFoundError:
            return None
        if real_spec is None:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(real_name))


# Import the real package FIRST: if it fails, the shim import fails whole and
# nothing is left registered (an orphaned finder would silently serve later
# retries without ever re-running this module's deprecation warning).
_target = importlib.import_module(_NEW_NAME)
sys.meta_path.insert(0, _AliasFinder())

# Replace this shim in sys.modules with the real package, so
# `import gaspatchio_core` and `import gaspatchio` name the same object.
sys.modules[_OLD_NAME] = _target
