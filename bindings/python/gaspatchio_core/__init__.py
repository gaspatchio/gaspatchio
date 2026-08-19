# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Deprecated import alias for :mod:`gaspatchio` — removed in 1.0.

The import name used to follow the repository (``gaspatchio-core``) rather
than the product. Since 0.8.3 the import name is ``gaspatchio``, matching the
PyPI name and the documentation. This package exists only so models written
against the old name keep running.

Every ``gaspatchio_core`` module is registered as the *same module object* as
its ``gaspatchio`` counterpart — the loader below returns the already-imported
real module instead of executing a copy. A copy would re-run registration
side effects and split module state (the assumption-table registry, accessor
registration), which is exactly the silent divergence this alias must never
introduce.
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
    from types import ModuleType

_OLD_NAME = "gaspatchio_core"
_NEW_NAME = "gaspatchio"

warnings.warn(
    "The 'gaspatchio_core' import name is deprecated and will be removed in "
    "1.0 — write 'import gaspatchio' instead (the import name now matches the "
    "package name). Existing code keeps working unchanged: every "
    "gaspatchio_core module is the same object as its gaspatchio counterpart.",
    DeprecationWarning,
    stacklevel=2,
)


class _AliasLoader(importlib.abc.Loader):
    """Hand the import machinery the real gaspatchio module, never a copy."""

    def __init__(self, real_name: str) -> None:
        self._real_name = real_name
        self._real_attrs: dict[str, object] = {}

    def create_module(self, spec: ModuleSpec) -> ModuleType:
        """Return the already-imported real module for this alias spec."""
        del spec  # the alias spec; the real module keeps its own
        module = importlib.import_module(self._real_name)
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
        real_name = _NEW_NAME + fullname[len(_OLD_NAME) :]
        return importlib.util.spec_from_loader(fullname, _AliasLoader(real_name))


sys.meta_path.insert(0, _AliasFinder())

# Replace this shim in sys.modules with the real package, so
# `import gaspatchio_core` and `import gaspatchio` name the same object.
sys.modules[_OLD_NAME] = importlib.import_module(_NEW_NAME)
