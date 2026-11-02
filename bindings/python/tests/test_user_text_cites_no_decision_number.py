# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""No text the package hands a user cites an internal decision number.

A refusal, a report line or an error message is read by someone with nowhere
to look up a reference written as the letter ``R`` and a number: the records
those numbers index are not published. A rule a user is told about is cited by
the section of the specification that states it, or said in words. So every
string literal in the package that can reach a user is held free of one here
-- everything but a docstring or a bare string statement, which document the
code rather than speak to its user. Comments are not string literals, and are
not read here.

**A docstring of the public API speaks to its user as well.** The API
reference renders it on the published site, and ``help()`` prints it, so it
is read here too: every public module's own, and every public class's,
function's, method's and field's, wherever the class or function is defined,
once a public module hands it out. A module is public when no part of its
dotted name begins with an underscore. A private module's own docstrings
document the code, as its comments do, and ``test_comments_cite_no_decision_number.py``
holds both to the same rule.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
import typing
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pydantic import BaseModel

if TYPE_CHECKING:
    from types import ModuleType

_PACKAGE: Final = Path(__file__).resolve().parents[1] / "gaspatchio"

# How a decision is cited: an R and one to three digits, standing alone. A
# longer run -- a policy id such as R4001 in an example -- is not one.
_CITATION: Final = re.compile(r"\bR[0-9]{1,3}\b")


def _citations(path: Path, root: Path) -> list[str]:
    """Return ``file:line: token`` for each decision number a literal carries."""
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    # A string standing as a statement of its own is documentation -- a
    # module's, a class's, a function's or an attribute's docstring.
    documentation = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    return [
        f"{path.relative_to(root).as_posix()}:{node.lineno}: {token}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in documentation
        for token in _CITATION.findall(node.value)
    ]


def test_no_string_a_user_can_read_cites_a_decision_number() -> None:
    sources = sorted([*_PACKAGE.rglob("*.py"), *_PACKAGE.rglob("*.pyi")])
    assert len(sources) > 100, "the scan found almost nothing to read"

    found = [hit for path in sources for hit in _citations(path, _PACKAGE.parent)]

    assert found == [], (
        "A string a user can read cites an internal decision number. Cite the "
        "section of spec/graph-artifact/v0-preview.md that states the rule, or "
        "say it in words:\n  " + "\n  ".join(found)
    )


def test_the_scan_reads_messages_and_passes_over_documentation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "example.py"
    source.write_text(
        '"""A module whose docstring cites R45."""\n'
        "# A comment citing R46.\n"
        "LIMIT = 3\n"
        '"""An attribute docstring citing R47."""\n'
        "\n"
        "\n"
        "def refuse(column: str) -> str:\n"
        '    """Say why, citing R48."""\n'
        '    return f"{column} is refused under R49, as R4001 is not"\n',
        "utf-8",
    )

    assert _citations(source, tmp_path) == ["example.py:9: R49"]


def _public_module_names() -> list[str]:
    """Return every module whose dotted name has no underscore-led part.

    The tutorials are left out: they are standalone scripts a user copies into
    a directory of their own, not a module anyone imports.
    """
    names = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        parts = list(path.relative_to(_PACKAGE.parent).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        if "tutorials" in parts or any(part.startswith("_") for part in parts[1:]):
            continue
        names.append(".".join(parts))
    return names


def _where(obj: object) -> str:
    """Return where a class or function is defined, as its dotted path."""
    return f"{obj.__module__}.{getattr(obj, '__qualname__', '?')}"


def _ours(obj: object) -> bool:
    """Return whether ``obj`` is defined in this package rather than borrowed."""
    return str(getattr(obj, "__module__", "")).startswith("gaspatchio")


def _handed_out(module: ModuleType) -> list[object]:
    """Return the classes and functions of ours a public module hands out."""
    names = getattr(module, "__all__", None)
    if names is None:
        names = [name for name in vars(module) if not name.startswith("_")]
    return [
        obj
        for name in names
        if (obj := getattr(module, name, None)) is not None
        and (inspect.isclass(obj) or inspect.isfunction(obj))
        and _ours(obj)
    ]


def _handed_by_property(getter: object) -> object | None:
    """Return the class of ours a public property hands out, where it names one.

    A namespace such as ``af.premium.str`` is a class defined in a private
    module and reached only through a property, and the API reference renders
    it all the same.
    """
    try:
        handed = typing.get_type_hints(getter).get("return")
    except (NameError, TypeError):
        return None
    return handed if inspect.isclass(handed) and _ours(handed) else None


def _members(cls: type) -> list[tuple[str, object]]:
    """Return each public member a class defines or inherits from a class of ours."""
    found: list[tuple[str, object]] = []
    for owner in cls.__mro__:
        if not _ours(owner):
            continue
        for name, member in vars(owner).items():
            if name.startswith("_"):
                continue
            target: object = member
            if isinstance(member, (staticmethod, classmethod)):
                target = member.__func__
            elif isinstance(member, property):
                target = member.fget
                handed = _handed_by_property(member.fget)
                if handed is not None:
                    found.append((_where(handed), handed))
            found.append((f"{_where(cls)}.{name}", target))
    return found


def _public_docstrings() -> list[tuple[str, str]]:
    """Return every docstring of the public API, with where it is."""
    found: list[tuple[str, str]] = []
    walked: set[int] = set()

    def walk(obj: object, where: str) -> None:
        if id(obj) in walked:
            return
        walked.add(id(obj))
        found.append((where, getattr(obj, "__doc__", None) or ""))
        if not inspect.isclass(obj):
            return
        for place, member in _members(obj):
            if (inspect.isclass(member) or inspect.isfunction(member)) and _ours(
                member
            ):
                walk(member, place)
        if issubclass(obj, BaseModel):
            found.extend(
                (f"{_where(obj)}.{field}", info.description or "")
                for field, info in obj.model_fields.items()
            )

    for name in _public_module_names():
        module = importlib.import_module(name)
        found.append((name, module.__doc__ or ""))
        for obj in _handed_out(module):
            walk(obj, _where(obj))
    return found


def _stub_docstrings() -> list[tuple[str, str]]:
    """Return the docstrings a public module's stub gives its public names.

    The API reference reads a module's stub beside its source, so a docstring
    written into the stub is rendered as well.
    """
    found: list[tuple[str, str]] = []
    for name in _public_module_names():
        path = _PACKAGE.parent / Path(*name.split("."))
        stub = path / "__init__.pyi" if path.is_dir() else path.with_suffix(".pyi")
        if not stub.is_file():
            continue
        tree = ast.parse(stub.read_text("utf-8"))
        found.append((f"{name} (stub)", ast.get_docstring(tree) or ""))
        pending: list[tuple[ast.AST, str]] = [(tree, name)]
        while pending:
            node, where = pending.pop()
            for child in ast.iter_child_nodes(node):
                if not isinstance(
                    child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ) or child.name.startswith("_"):
                    continue
                place = f"{where}.{child.name} (stub)"
                found.append((place, ast.get_docstring(child) or ""))
                if isinstance(child, ast.ClassDef):
                    pending.append((child, place.removesuffix(" (stub)")))
    return found


def test_no_public_docstring_cites_a_decision_number() -> None:
    documented = _public_docstrings()
    reached = {where for where, _ in documented}
    # What the published reference renders is among what is read here.
    assert {
        "gaspatchio.frame.base.ActuarialFrame",
        "gaspatchio.frame.base.ActuarialFrame.collect",
        "gaspatchio.scenarios._aggregated.run_aggregated",
        "gaspatchio.assumptions._api.Table.lookup",
        "gaspatchio.column._generated_proxy.StringNamespace",
        "gaspatchio.engines.format",
    } <= reached

    found = [
        f"{where}: {token}"
        for where, text in [*documented, *_stub_docstrings()]
        for token in _CITATION.findall(text)
    ]

    assert found == [], (
        "A docstring of the public API cites an internal decision number. Cite "
        "the section of spec/graph-artifact/v0-preview.md that states the rule, "
        "or say it in words:\n  " + "\n  ".join(found)
    )
