# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""No refusal, report or message this engine writes cites a decision number.

A refusal names the clause it rests on, and a reader follows that clause to
the specification. A reference written as the letter ``R`` and a number sends
them nowhere: the records those numbers index are not published. So every
string literal in the engine that can reach a user is held free of one here --
everything but a docstring or a bare string statement, which document the code
rather than speak to its user. Comments are not string literals, and are not
read here.

**What the package hands out speaks to its user as well.** ``help()`` prints
the docstrings of the package and of what its ``__all__`` exports, so those
are read too: the package's own, each exported class's and function's, their
public members', and the docstring of each module that defines one. The
modules behind them are the engine's workings, and their docstrings and
comments are held to the same rule by the core suite's
``tests/test_comments_cite_no_decision_number.py``, which reads this tree as well.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import re
from pathlib import Path
from typing import Final

import gaspatchio_jax

_PACKAGE: Final = Path(__file__).resolve().parents[1] / "src" / "gaspatchio_jax"

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


def test_no_refusal_or_message_cites_a_decision_number() -> None:
    sources = sorted(_PACKAGE.rglob("*.py"))
    assert len(sources) > 20, "the scan found almost nothing to read"

    found = [hit for path in sources for hit in _citations(path, _PACKAGE.parent)]

    assert found == [], (
        "A refusal or message cites an internal decision number. Cite the "
        "section of spec/graph-artifact/v0-preview.md that states the rule, or "
        "leave the clause out and say the reason in words:\n  " + "\n  ".join(found)
    )


def test_the_scan_reads_clauses_and_passes_over_documentation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "example.py"
    source.write_text(
        '"""A lowering whose docstring cites R45."""\n'
        "# A comment citing R46.\n"
        '_SUBSET = "16.1"\n'
        '"""An attribute docstring citing R47."""\n'
        "\n"
        "\n"
        "def refusal() -> dict[str, str]:\n"
        '    """Say why, citing R48."""\n'
        '    return {"clause": "R49", "what": "keyed as R4001, not a decision"}\n',
        "utf-8",
    )

    assert _citations(source, tmp_path) == ["example.py:9: R49"]


def _ours(obj: object) -> bool:
    """Return whether ``obj`` is defined in this package rather than borrowed."""
    return str(getattr(obj, "__module__", "")).startswith("gaspatchio_jax")


def _exported_docstrings() -> list[tuple[str, str]]:
    """Return every docstring of what the package exports, with where it is."""
    found = [("gaspatchio_jax", gaspatchio_jax.__doc__ or "")]
    modules: set[str] = set()
    for name in gaspatchio_jax.__all__:
        obj = getattr(gaspatchio_jax, name)
        if not (inspect.isclass(obj) or inspect.isfunction(obj)) or not _ours(obj):
            continue
        modules.add(obj.__module__)
        where = f"{obj.__module__}.{obj.__qualname__}"
        found.append((where, obj.__doc__ or ""))
        if not inspect.isclass(obj):
            continue
        for owner in obj.__mro__:
            if not _ours(owner):
                continue
            for member_name, member in vars(owner).items():
                if member_name.startswith("_"):
                    continue
                target = member.fget if isinstance(member, property) else member
                target = getattr(target, "__func__", target)
                if inspect.isfunction(target) or isinstance(member, property):
                    found.append((f"{where}.{member_name}", target.__doc__ or ""))
    found.extend(
        (module, importlib.import_module(module).__doc__ or "")
        for module in sorted(modules)
    )
    return found


def test_what_the_package_exports_cites_no_decision_number() -> None:
    documented = _exported_docstrings()
    reached = {where for where, _ in documented}
    assert {
        "gaspatchio_jax",
        "gaspatchio_jax.engine",
        "gaspatchio_jax.engine.JaxEngine",
        "gaspatchio_jax.engine.JaxEngine.run",
        "gaspatchio_jax.engine.JaxEngine.aggregate",
    } <= reached

    found = [
        f"{where}: {token}"
        for where, text in documented
        for token in _CITATION.findall(text)
    ]

    assert found == [], (
        "A docstring of what the package exports cites an internal decision "
        "number, and help() prints it. Cite the section of "
        "spec/graph-artifact/v0-preview.md that states the rule, or say it in "
        "words:\n  " + "\n  ".join(found)
    )
