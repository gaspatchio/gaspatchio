# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Tripwire: no module in ``gaspatchio`` is a second door onto another one.

A shim here is a module that **defines nothing** — no ``def`` and no
``class`` anywhere in it — whose body is only imports, ``__all__`` and a
docstring, and which imports at least one name. Such a module holds no
implementation. Everything it publishes was written somewhere else, so its
only effect is to give an operation a second spelling: two import paths,
two places a reader has to look, two things to keep in agreement when the
implementation moves.

**A package ``__init__.py`` of that shape is not a shim, and this is the
whole exemption.** A package has to publish its names from somewhere, and
the ``__init__.py`` is the place the language gives it — the door. There is
exactly one per package, a reader knows where to find it without being
told, and it is the only file whose name says "this is what the package
publishes". A module *beside* the door with the same shape says nothing new:
it is the door's contents spelled a second way, at an address the reader has
no reason to prefer. That is the difference, and it is why this walk exempts
``__init__.py`` by name rather than by an allowlist entry.

The import requirement is what makes the shape mean "second door". A module
that defines nothing and imports nothing — an empty package marker, a
docstring-only placeholder — republishes nothing and gives no operation a
second spelling, so it is outside what this tripwire is for.

``tutorials/`` is exempt on the same argument the census uses: those are
worked example models shipped for documentation, written the way a user's
own model is written, not framework modules.

**The allowlist is empty**, and it is here to stay empty. A reviewed
exception would be a module that re-publishes another module's names and is
worth keeping anyway — and the argument for one is the argument already
rejected in thirteen cases at once. Adding an entry is the conspicuous line
in the diff that says a fourteenth was different; it is not a way to land a
shim quietly.

The thirteen this tripwire was written for went in the same commit:
``gaspatchio/polars_backend/`` (five modules and its door) re-published
``frame/lowering/_polars``, ``gaspatchio/accessors/excel_functions/`` (seven
modules and an empty door) re-published ``frame/lowering/_excel``, and
``gaspatchio/schedule/_canonical.py`` re-published ``canonical_bytes`` from
``gaspatchio._identity`` to nobody at all.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

# This file lives at bindings/python/tests/; the package it walks is
# bindings/python/gaspatchio.
PACKAGE_ROOT: Final[Path] = Path(__file__).resolve().parent.parent / "gaspatchio"

# Path prefixes (POSIX-style, relative to the scanned root, no leading
# slash) that this walk does not read at all.
EXEMPT_PREFIXES: Final[tuple[str, ...]] = ("tutorials/",)

# Reviewed exceptions, keyed on the path relative to the scanned root. It is
# empty. See the module docstring for what putting something in it would mean.
ALLOWLIST: Final[frozenset[str]] = frozenset()

# Two modules that have been in the package throughout and are emphatically
# not shims. A walk that reaches neither reached nothing, and a walk that
# reached nothing reports clean.
WALK_ANCHORS: Final[tuple[str, ...]] = ("frame/base.py", "accessors/excel.py")


def _is_a_docstring(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_an_all_assignment(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return all(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        )
    return isinstance(node, ast.AnnAssign) and (
        isinstance(node.target, ast.Name) and node.target.id == "__all__"
    )


def is_shim_shaped(source: str) -> bool:
    """Report whether ``source`` is a module that only re-publishes names.

    Three conditions, all of them necessary: it defines no function and no
    class anywhere in it; every statement in its body is an import, a
    docstring or an ``__all__`` assignment; and at least one of those
    statements is an import, because a module that imports nothing
    re-publishes nothing.
    """
    tree = ast.parse(source)
    if any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        for node in ast.walk(tree)
    ):
        return False
    imports = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports += 1
            continue
        if _is_a_docstring(node) or _is_an_all_assignment(node):
            continue
        return False
    return imports > 0


def shim_shaped_modules(root: Path) -> list[str]:
    """Every shim-shaped module under ``root``, doors included, as POSIX paths."""
    return [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*.py"))
        if not path.relative_to(root).as_posix().startswith(EXEMPT_PREFIXES)
        and is_shim_shaped(path.read_text(encoding="utf-8"))
    ]


def format_shims(offenders: list[str]) -> str:
    """Render ``offenders`` as an actionable failure message."""
    return "\n".join(
        [
            (
                "Module(s) that define nothing and only re-publish another "
                "module's names, at an address that is not the package's door:"
            ),
            *(f"  {path}" for path in offenders),
            (
                "Each of these gives an operation a second spelling. Delete it "
                "and point its callers at the module the names were written in. "
                "If the names belong in this package's public surface, publish "
                "them from its __init__.py, which is the one door a reader "
                "knows to look at."
            ),
        ]
    )


def test_no_module_is_a_second_door() -> None:
    """Outside a package ``__init__.py``, nothing in ``gaspatchio`` is a shim.

    The count this holds at zero is the count of second spellings. It was
    thirteen before the commit that added this test, across two whole
    subpackages and one private module nothing imported, and every one of
    them dated from an implementation move that left its old address
    forwarding.
    """
    scanned = {
        path.relative_to(PACKAGE_ROOT).as_posix() for path in PACKAGE_ROOT.rglob("*.py")
    }
    for anchor in WALK_ANCHORS:
        assert anchor in scanned, (
            f"the walk did not reach {anchor} — PACKAGE_ROOT resolves to "
            f"{PACKAGE_ROOT}, which is not the package this test is about"
        )

    offenders = [
        path
        for path in shim_shaped_modules(PACKAGE_ROOT)
        if Path(path).name != "__init__.py" and path not in ALLOWLIST
    ]
    assert not offenders, format_shims(offenders)


def test_tripwire_detects_a_shim(tmp_path: Path) -> None:
    """A module beside the door that only re-publishes the door's names."""
    target = tmp_path / "reports" / "totals.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '"""Compatibility imports for :mod:`elsewhere.totals`."""\n\n'
        "from elsewhere.totals import total\n\n"
        '__all__ = ["total"]\n',
        encoding="utf-8",
    )

    assert shim_shaped_modules(tmp_path) == ["reports/totals.py"]


def test_a_package_door_of_the_same_shape_is_reported_but_exempt(
    tmp_path: Path,
) -> None:
    """The door is found by the walk and excused by its name, not by a list.

    Byte-for-byte the body of the module above, at the one address where
    re-publishing names is the file's job.
    """
    target = tmp_path / "reports" / "__init__.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '"""Compatibility imports for :mod:`elsewhere.totals`."""\n\n'
        "from elsewhere.totals import total\n\n"
        '__all__ = ["total"]\n',
        encoding="utf-8",
    )

    found = shim_shaped_modules(tmp_path)

    assert found == ["reports/__init__.py"]
    assert not [path for path in found if Path(path).name != "__init__.py"]


def test_a_module_that_defines_something_is_not_a_shim(tmp_path: Path) -> None:
    """One ``def`` anywhere in the file is an implementation to point at."""
    target = tmp_path / "reports" / "totals.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '"""A module with a body."""\n\n'
        "from elsewhere.totals import total\n\n\n"
        "def doubled(value: int) -> int:\n"
        "    return total(value) * 2\n\n\n"
        '__all__ = ["doubled"]\n',
        encoding="utf-8",
    )

    assert shim_shaped_modules(tmp_path) == []


def test_a_module_that_imports_nothing_is_not_a_shim(tmp_path: Path) -> None:
    """An empty marker re-publishes nothing, so it is nobody's second door."""
    target = tmp_path / "reports" / "totals.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('"""Nothing lives here yet."""\n', encoding="utf-8")

    assert shim_shaped_modules(tmp_path) == []


def test_a_module_that_does_anything_else_is_not_a_shim(tmp_path: Path) -> None:
    """A statement that is not an import, a docstring or ``__all__``.

    A re-export module that also computes something is doing work of its
    own, whatever else is wrong with it, so it is not this tripwire's to
    report.
    """
    target = tmp_path / "reports" / "totals.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "from elsewhere.totals import total\n\n"
        "DOUBLED = total * 2\n\n"
        '__all__ = ["DOUBLED", "total"]\n',
        encoding="utf-8",
    )

    assert shim_shaped_modules(tmp_path) == []


def test_tutorials_are_exempt(tmp_path: Path) -> None:
    """Shipped example model code is not framework surface."""
    target = tmp_path / "tutorials" / "level-9-new" / "model.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '"""Compatibility imports for :mod:`elsewhere.totals`."""\n\n'
        "from elsewhere.totals import total\n\n"
        '__all__ = ["total"]\n',
        encoding="utf-8",
    )

    assert shim_shaped_modules(tmp_path) == []
