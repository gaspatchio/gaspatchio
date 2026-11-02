# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101
"""No test under the repository's ``tests/`` shells a package manager or a build tool.

``uv run gspio ...`` resolves the project it is started in, and a project with
an extension module is built to do that: a test written that way compiles the
Rust core in whatever tree it runs from, so its answer is about a fresh build
rather than the package under test, and it takes minutes to give it. A test
runs the CLI through its own interpreter -- ``sys.executable -m
gaspatchio.cli`` -- or a model with ``sys.executable``.

This reads every test module's source for a subprocess call whose command
starts with ``uv``, ``uvx``, ``maturin`` or ``cargo``, written as an argument
list or as a shell string.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS = Path(__file__).resolve().parent.parent
_BUILD_TOOLS = frozenset({"uv", "uvx", "maturin", "cargo"})
_SUBPROCESS_CALLS = frozenset(
    {"run", "Popen", "call", "check_call", "check_output", "getoutput", "system"}
)


def _command_head(node: ast.expr) -> str | None:
    """Return the program a command literal names, or None if it is not a literal."""
    if isinstance(node, ast.List | ast.Tuple) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        words = node.value.split()
        return words[0] if words else None
    return None


def _build_tool_calls(path: Path, root: Path) -> list[str]:
    """Return each subprocess call in ``path`` that starts a build tool."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else None
        if name not in _SUBPROCESS_CALLS or not node.args:
            continue
        head = _command_head(node.args[0])
        if head in _BUILD_TOOLS:
            found.append(f"{path.relative_to(root)}:{node.lineno} runs {head}")
    return found


def test_no_test_shells_a_build_tool() -> None:
    """Every subprocess a test starts is this interpreter or the model it runs."""
    modules = sorted(_TESTS.rglob("*.py"))
    assert modules, "no test modules found"

    found = [
        call for module in modules for call in _build_tool_calls(module, _TESTS.parent)
    ]

    assert found == [], (
        "A test shells a package manager or build tool, which builds the tree "
        "it runs in; run the CLI as [sys.executable, '-m', 'gaspatchio.cli', ...] "
        f"instead: {found}"
    )


def test_the_reader_sees_both_spellings(tmp_path: Path) -> None:
    """The guard reads an argument list and a shell string alike."""
    module = tmp_path / "test_probe.py"
    module.write_text(
        "import os, subprocess\n"
        "subprocess.run(['uv', 'run', 'gspio'])\n"
        "os.system('cargo build')\n"
        "subprocess.run([sys.executable, '-m', 'gaspatchio.cli'])\n"
    )
    found = _build_tool_calls(module, tmp_path)

    assert [line.rsplit(" ", 1)[-1] for line in found] == ["uv", "cargo"]
