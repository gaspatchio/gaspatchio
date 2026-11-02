# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Each export of the documented packages reaches the API docs with a docstring.
# ABOUTME: Reads source as the docs build does; a bare stub cannot hide one.
"""The API pages show a docstring for every public name of these packages.

The API reference is built by mkdocstrings, which reads source files rather
than importing them. When a module has a ``.pyi`` beside its ``.py``, the
docs build reads the stub, so a stub that redeclares a class or function with
a bare signature replaces the documented source definition with an
undocumented one. That is how most of the scenarios page, and the
``MortalityTable`` entry, once rendered with no descriptions at all.

These tests read the source the same way: they follow each exported name from
the package's ``__init__.py`` to the module that defines it and check the
docstring there, and they refuse any stub that redeclares an exported name
instead of re-exporting it.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import gaspatchio

_SOURCE_ROOT = Path(gaspatchio.__file__).parent.parent

# The packages whose public names the API pages document from source.
_PACKAGES = (
    "gaspatchio.scenarios",
    "gaspatchio.mortality",
    "gaspatchio.assumptions",
    "gaspatchio.util",
)


def _module_path(dotted: str) -> Path:
    """Return the ``.py`` file for a dotted ``gaspatchio`` module name."""
    base = _SOURCE_ROOT.joinpath(*dotted.split("."))
    package_init = base / "__init__.py"
    return package_init if package_init.exists() else base.with_suffix(".py")


def _imported_module(dotted_module: str, node: ast.ImportFrom) -> str:
    """Resolve a possibly relative ``from ... import`` to an absolute name."""
    if not node.level:
        return node.module or ""
    package = dotted_module
    if _module_path(dotted_module).name != "__init__.py":
        package = dotted_module.rpartition(".")[0]
    for _ in range(node.level - 1):
        package = package.rpartition(".")[0]
    return f"{package}.{node.module}" if node.module else package


def _definition_has_docstring(dotted_module: str, name: str) -> bool:
    """Say whether ``name`` carries a docstring where the docs build finds it.

    Follows ``from x import name`` re-exports to the defining module. A class
    or function counts when it has a docstring; a plain assignment
    (``BaseAggregator = _BaseAggregator``) counts when a string literal
    follows it, which is how the docs build documents an attribute.
    """
    body = ast.parse(_module_path(dotted_module).read_text()).body
    for index, node in enumerate(body):
        if isinstance(node, ast.ClassDef | ast.FunctionDef) and node.name == name:
            return bool(ast.get_docstring(node))
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            following = body[index + 1] if index + 1 < len(body) else None
            return (
                isinstance(following, ast.Expr)
                and isinstance(following.value, ast.Constant)
                and isinstance(following.value.value, str)
                and bool(following.value.value.strip())
            )
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if (alias.asname or alias.name) == name:
                    return _definition_has_docstring(
                        _imported_module(dotted_module, node), alias.name
                    )
    msg = f"{name} is neither defined nor imported in {dotted_module}"
    raise AssertionError(msg)


@pytest.mark.parametrize("package", _PACKAGES)
def test_every_exported_name_has_a_docstring_at_its_definition(package: str) -> None:
    """Each name in the package's ``__all__`` is documented at source."""
    exported = importlib.import_module(package).__all__
    missing = [
        name for name in exported if not _definition_has_docstring(package, name)
    ]
    assert not missing, (
        f"These names exported by {package} have no docstring where they are "
        f"defined, so the API page renders them blank: {missing}. Add a "
        "docstring to each definition."
    )


@pytest.mark.parametrize("package", _PACKAGES)
def test_no_stub_redeclares_an_exported_name(package: str) -> None:
    """A stub beside the package may re-export names, never redeclare them.

    The docs build reads ``__init__.pyi`` in place of ``__init__.py``. A class
    or function declared there has no docstring, and it is the one the API
    page shows.
    """
    stub = _module_path(package).with_suffix(".pyi")
    if not stub.exists():
        return
    exported = set(importlib.import_module(package).__all__)
    redeclared = sorted(
        node.name
        for node in ast.parse(stub.read_text()).body
        if isinstance(node, ast.ClassDef | ast.FunctionDef) and node.name in exported
    )
    assert not redeclared, (
        f"{stub.relative_to(_SOURCE_ROOT)} redeclares names {package} exports: "
        f"{redeclared}. The docs build reads the stub in place of the source, "
        "so these render without the source's docstrings. Delete the stub, or "
        "replace each declaration with `from <module> import Name as Name`."
    )
