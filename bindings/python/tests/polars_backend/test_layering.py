# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Polars lowering primitives do not load frontend modules at any level.

The expression implementations live in ``frame/lowering/_polars``, which is
now the one place they live: the ``polars_backend`` modules that used to
re-publish them are gone. Primitives may import other lowering helpers, but
not the column, accessor, function or frame frontend; this includes local and TYPE_CHECKING imports.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

POLARS_LOWERING_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "gaspatchio"
    / "frame"
    / "lowering"
    / "_polars"
)

# String prefixes that identify a frontend column-package import.
COLUMN_IMPORT_PREFIXES = (
    "gaspatchio.column",
    "gaspatchio.frame",
    "gaspatchio.functions",
    "gaspatchio.accessors",
)


def _polars_lowering_modules() -> list[Path]:
    modules = sorted(
        p for p in POLARS_LOWERING_DIR.glob("*.py") if p.name != "__init__.py"
    )
    assert modules, f"No Polars implementation modules found in {POLARS_LOWERING_DIR}"
    return modules


def _is_frontend_import(node: ast.ImportFrom | ast.Import) -> bool:
    def is_frontend(module: str) -> bool:
        if module == "gaspatchio.frame.lowering" or module.startswith(
            "gaspatchio.frame.lowering."
        ):
            return False
        return any(module.startswith(prefix) for prefix in COLUMN_IMPORT_PREFIXES)

    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
    else:
        # ast.Import: any aliased import path
        module = ""
        for alias in node.names:
            if is_frontend(alias.name):
                return True
        return False
    return is_frontend(module)


def _frontend_imports(source: str) -> list[str]:
    """Return frontend imports, including local and type-only dependencies."""
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and _is_frontend_import(node):
            offenders.append(ast.unparse(node))
    return offenders


@pytest.mark.parametrize(
    "statement",
    [
        "from gaspatchio.column.column_proxy import ColumnProxy",
        "from gaspatchio.frame.base import ActuarialFrame",
        "import gaspatchio.accessors.base",
        "from gaspatchio.functions.conditional import when",
    ],
)
def test_frontend_imports_are_detected(statement: str) -> None:
    assert _frontend_imports(statement)


def test_lowering_imports_are_allowed() -> None:
    assert not _frontend_imports(
        "from gaspatchio.frame.lowering.columns import column_reference"
    )


@pytest.mark.parametrize(
    "module_path", _polars_lowering_modules(), ids=lambda p: p.name
)
def test_no_frontend_imports(module_path: Path) -> None:
    """Each Polars primitive must not depend on frontend code.

    Proxy mask conversion belongs to the authoring layer. List evaluation receives
    an already lowered expression and has no need to inspect proxy classes.
    """
    source = module_path.read_text()
    offenders = _frontend_imports(source)
    assert not offenders, (
        f"{module_path.name} has {len(offenders)} frontend import(s) — "
        f"violates the Polars lowering → frontend layering invariant. Move proxy adaptation to the authoring layer. Offenders:\n  "
        + "\n  ".join(offenders)
    )


# Package initializers still expose the public API eagerly. This checks the
# primitives' own dependencies, not the transitive runtime import footprint.


@pytest.mark.parametrize("scope", ["if TYPE_CHECKING:", "def lower():"])
def test_nested_frontend_imports_are_detected(scope: str) -> None:
    assert _frontend_imports(
        f"{scope}\n    from gaspatchio.column.column_proxy import ColumnProxy"
    )
