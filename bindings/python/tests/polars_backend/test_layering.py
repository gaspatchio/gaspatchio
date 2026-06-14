# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Layering invariant: polars_backend/ has zero top-level column/ imports.

The dispatch refactor (PRs #99 / #100 / #101) established a one-way layering
between the frontend (``column/``, ``frame/``, ``functions/``) and the Polars
implementation (``polars_backend/``). Frontend modules import from
``polars_backend/`` at module load time; ``polars_backend/`` does NOT import
from ``column/`` at module load time.

There is one bounded exception: ``masks.py`` and ``list_eval.py`` both have
function-local ``from gaspatchio_core.column...`` imports inside helper
functions (deferred to break the masks↔condition_expression cycle and to
avoid pulling the whole frontend during ``import gaspatchio_core``). Those
deferred imports are documented at the call sites and do not violate the
load-order invariant.

This test parses each ``polars_backend/*.py`` file with ``ast`` and walks
its top-level statements. Any ``from gaspatchio_core.column...`` or
``import gaspatchio_core.column...`` at module scope fails the test.
Function-local and ``TYPE_CHECKING``-guarded imports are ignored — those
do not contribute to module-load order.

If you genuinely need to import from ``column/`` in a new ``polars_backend/``
module, defer the import inside the function body and document why at the
call site (the way ``masks.py`` does for proxy-type dispatch helpers).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

POLARS_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "gaspatchio_core"
    / "polars_backend"
)

# String prefixes that identify a frontend column-package import.
COLUMN_IMPORT_PREFIXES = (
    "gaspatchio_core.column",
    "gaspatchio_core.frame",
    "gaspatchio_core.functions",
    "gaspatchio_core.accessors",
)


def _polars_backend_modules() -> list[Path]:
    return sorted(p for p in POLARS_BACKEND_DIR.glob("*.py") if p.name != "__init__.py")


def _is_frontend_import(node: ast.ImportFrom | ast.Import) -> bool:
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
    else:
        # ast.Import: any aliased import path
        module = ""
        for alias in node.names:
            if any(alias.name.startswith(p) for p in COLUMN_IMPORT_PREFIXES):
                return True
        return False
    return any(module.startswith(p) for p in COLUMN_IMPORT_PREFIXES)


def _top_level_frontend_imports(source: str) -> list[str]:
    """Return human-readable descriptions of any TOP-LEVEL frontend imports.

    Function-local and ``if TYPE_CHECKING:``-guarded imports are excluded —
    they don't contribute to module-load order.
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in tree.body:
        # Skip TYPE_CHECKING blocks (they don't execute at runtime).
        if (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == "TYPE_CHECKING"
        ):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)) and _is_frontend_import(
            node
        ):
            offenders.append(ast.unparse(node))
    return offenders


@pytest.mark.parametrize("module_path", _polars_backend_modules(), ids=lambda p: p.name)
def test_no_top_level_column_imports(module_path: Path) -> None:
    """Each polars_backend submodule must not import column/ at module load.

    Bounded exception: ``masks.py`` and ``list_eval.py`` have function-local
    column/ imports for proxy-type dispatch — those happen at call time,
    not import time, so they don't break the layering. This test only
    catches *top-level* statements.
    """
    source = module_path.read_text()
    offenders = _top_level_frontend_imports(source)
    assert not offenders, (
        f"{module_path.name} has {len(offenders)} top-level frontend import(s) — "
        f"violates the polars_backend → frontend layering invariant. Move them "
        f"inside function bodies or remove. Offenders:\n  "
        + "\n  ".join(offenders)
    )


# Note: a runtime "import gaspatchio_core.polars_backend pulls no column
# modules" check is not feasible — the parent ``gaspatchio_core`` package
# eager-loads its public surface in ``__init__.py``, so ``import
# gaspatchio_core.polars_backend`` always triggers the frontend load via
# the package init. The AST check above is the actual invariant: it
# verifies the polars_backend submodules don't *themselves* import from
# the frontend at top level, which is what the layering rule actually
# guarantees.
