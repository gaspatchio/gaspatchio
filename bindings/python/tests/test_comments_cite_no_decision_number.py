# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""No comment or docstring in the shipped source cites an internal decision number.

A reference written as the letter ``R`` and a number points into records that
are not published. A maintainer who meets one is sent nowhere, at exactly the
place the code relies on the reason, so the reason is written out instead: the
rule in words, or the section of ``spec/graph-artifact/v0-preview.md`` that
states it.

``test_user_text_cites_no_decision_number.py`` holds what a user reads -- refusals,
messages, the public API's docstrings. This holds what a maintainer reads:

- **Python**, every tracked ``.py`` and ``.pyi`` under ``bindings/python``,
  ``engines/jax`` and ``viewer/python`` -- the packages, their tests, their
  benchmarks and their tutorials. Its comments and every docstring are read;
  its other strings are code, and the package's are the other guard's.
- **The viewer**, every tracked ``.ts``, ``.tsx``, ``.mts``, ``.mjs`` and
  ``.css`` under ``viewer`` -- its source, its tests and its build scripts.
  These are read whole, comments and code alike: a string there is text the
  page shows, and it is held to the same rule.
- **Rust**, every tracked ``.rs`` under ``core`` and ``bindings/python/src``,
  read whole as well: a doc comment there is rendered documentation.

**What is not read.** The built bundle under ``viewer/python``: it is minified
output that carries no comments, and its short identifiers are a minifier's.
Workflows and configuration files are not read either.

A line that matches and is not a citation is allowed by name below, with the
reason it is not one.
"""

from __future__ import annotations

import ast
import functools
import io
import re
import shutil
import subprocess
import tokenize
from pathlib import Path
from typing import Final, NamedTuple

import pytest

REPO: Final = Path(__file__).resolve().parents[3]
GIT: Final = shutil.which("git")
pytestmark = pytest.mark.skipif(
    not (REPO / ".git").exists() or GIT is None, reason="requires checkout"
)

# How a decision is cited: an R and one to three digits, standing alone. A
# longer run -- a policy id such as R4001 in an example -- is not one.
_CITATION: Final = re.compile(r"\bR[0-9]{1,3}\b")

_PYTHON_TREES: Final = ("bindings/python", "engines/jax", "viewer/python")
_PYTHON_SUFFIXES: Final = (".py", ".pyi")
# Read whole, comments and code alike: each tree, and the suffixes read in it.
_WHOLE: Final = (
    ("viewer", (".ts", ".tsx", ".mts", ".mjs", ".css")),
    ("core", (".rs",)),
    ("bindings/python/src", (".rs",)),
)
# Built output, written by viewer/build.mjs and committed for the wheel.
_BUILT: Final = "viewer/python/"

# A file and one of its lines, stripped, that matches and cites nothing.
_NOT_A_CITATION: Final[dict[tuple[str, str], str]] = {}


class Hit(NamedTuple):
    """One match: where it is, what matched, and the line it stands on."""

    path: str
    line: int
    token: str
    text: str


def _python_hits(source: str, path: str) -> list[Hit]:
    """Return every match in a Python file's comments and docstrings.

    A docstring is any string standing as a statement of its own -- a
    module's, a class's, a function's or an attribute's. A comment is the
    tokenizer's own token, so a ``#`` inside a string is never one.
    """
    lines = source.splitlines()
    found = [
        Hit(path, token.start[0], match.group(), lines[token.start[0] - 1].strip())
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
        for match in _CITATION.finditer(token.string)
    ]
    for node in ast.walk(ast.parse(source, filename=path)):
        if not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        text = node.value.value
        for match in _CITATION.finditer(text):
            line = node.value.lineno + text.count("\n", 0, match.start())
            found.append(Hit(path, line, match.group(), lines[line - 1].strip()))
    return found


def _whole_file_hits(source: str, path: str) -> list[Hit]:
    """Return every match anywhere in a file, line by line."""
    return [
        Hit(path, number, match.group(), line.strip())
        for number, line in enumerate(source.splitlines(), start=1)
        for match in _CITATION.finditer(line)
    ]


def _hits(root: Path, path: str) -> list[Hit]:
    """Return the matches one file holds, read the way its kind is read."""
    source = (root / path).read_text("utf-8")
    if _CITATION.search(source) is None:
        return []
    if path.endswith(_PYTHON_SUFFIXES):
        return _python_hits(source, path)
    return _whole_file_hits(source, path)


def _read_whole(path: str) -> bool:
    """Return whether a tracked path is a source read whole, not as Python."""
    return not path.startswith(_BUILT) and any(
        path.startswith(f"{tree}/") and path.endswith(suffixes)
        for tree, suffixes in _WHOLE
    )


def _shipped_sources() -> list[str]:
    """Return every tracked source file the scan reads, repository-relative."""
    trees = (*_PYTHON_TREES, *(tree for tree, _ in _WHOLE))
    listed = subprocess.run(  # noqa: S603 -- git's own path and a fixed command
        [str(GIT), "ls-files", "-z", "--", *trees],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(
        path
        for path in listed.split("\0")
        if (
            path.startswith(tuple(f"{tree}/" for tree in _PYTHON_TREES))
            and path.endswith(_PYTHON_SUFFIXES)
        )
        or _read_whole(path)
    )


@functools.cache
def _all_hits() -> list[Hit]:
    """Return every match in every shipped source file."""
    return [hit for path in _shipped_sources() for hit in _hits(REPO, path)]


def test_no_comment_or_docstring_cites_a_decision_number() -> None:
    found = [
        f"{hit.path}:{hit.line}: {hit.token}"
        for hit in _all_hits()
        if (hit.path, hit.text) not in _NOT_A_CITATION
    ]

    assert found == [], (
        "A comment, a docstring or a line of source cites an internal decision "
        "number, which a reader of this repository cannot look up. Write the "
        "reasoning it stands for instead -- the rule in words, or the section "
        "of spec/graph-artifact/v0-preview.md that states it:\n  " + "\n  ".join(found)
    )


def test_every_allowed_line_still_matches() -> None:
    """An allowance whose line has gone is removed, not kept in case."""
    matched = {(hit.path, hit.text) for hit in _all_hits()}

    assert set(_NOT_A_CITATION) <= matched, set(_NOT_A_CITATION) - matched


def test_the_scan_reads_what_ships_and_not_the_built_bundle() -> None:
    sources = set(_shipped_sources())

    assert len(sources) > 900, "the scan found almost nothing to read"
    assert {
        "bindings/python/gaspatchio/frame/base.py",
        "bindings/python/tests/test_user_text_cites_no_decision_number.py",
        "engines/jax/src/gaspatchio_jax/plan.py",
        "engines/jax/tests/test_aggregate.py",
        "engines/jax/bench/aggregate_probe.py",
        "viewer/src/shell/App.tsx",
        "viewer/src/reader/compare.ts",
        "viewer/src/shell/shell.css",
        "viewer/test/layout.test.ts",
        "viewer/e2e/panes.spec.ts",
        "viewer/perf/measure.mjs",
        "core/src/identity.rs",
        "bindings/python/src/lib.rs",
    } <= sources
    assert "viewer/python/gaspatchio_viewer/assets/viewer.js" not in sources
    assert not any(
        path.startswith(_BUILT) and not path.endswith(_PYTHON_SUFFIXES)
        for path in sources
    )
    assert not any("node_modules/" in path for path in sources)


def _cite(number: int) -> str:
    """Return a citation-shaped token, built so this file does not carry one."""
    return f"R{number}"


def test_the_scan_reads_comments_and_docstrings_and_passes_over_code(
    tmp_path: Path,
) -> None:
    (tmp_path / "example.py").write_text(
        f'"""A module whose docstring cites {_cite(45)}."""\n'
        f"# A comment citing {_cite(46)}.\n"
        "LIMIT = 3\n"
        f'"""An attribute docstring citing {_cite(47)}."""\n'
        "\n"
        "\n"
        "def refuse(column: str) -> str:\n"
        '    """Say why,\n'
        f'    citing {_cite(48)} on its second line."""\n'
        f'    return f"{{column}} is refused under {_cite(49)}, as R4001 is not"\n',
        "utf-8",
    )
    (tmp_path / "page.ts").write_text(
        f"// A comment citing {_cite(50)}.\n"
        f'const label = "{_cite(51)}"; /* and one citing {_cite(52)} */\n'
        "const id = 'R4001';\n",
        "utf-8",
    )

    assert sorted((hit.line, hit.token) for hit in _hits(tmp_path, "example.py")) == [
        (1, _cite(45)),
        (2, _cite(46)),
        (4, _cite(47)),
        (9, _cite(48)),
    ]
    assert [(hit.line, hit.token) for hit in _hits(tmp_path, "page.ts")] == [
        (1, _cite(50)),
        (2, _cite(51)),
        (2, _cite(52)),
    ]
