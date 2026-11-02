# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""No name in the shipped source is an internal decision number.

``test_comments_cite_no_decision_number.py`` holds the comments and the
docstrings. A name can carry a decision number as well -- a constant, a test, a
report's key, a key in a data file -- and a reader meets it with nowhere to look
it up. So a name is read here, and fails when one of its underscore-separated
parts is the letter ``R`` and two or three digits, in either case:

- **Python**, every tracked ``.py`` and ``.pyi`` under ``bindings/python``,
  ``engines/jax`` and ``viewer/python``: every identifier, and every string
  spelled like one, which is how a report's or a frame's keys are written.
- **The viewer and the Rust crates**, every tracked ``.ts``, ``.tsx``, ``.mts``
  and ``.mjs`` under ``viewer`` and ``.rs`` under ``core`` and
  ``bindings/python/src``: every word, read whole.
- **Data**, every key of every tracked ``.json`` under those three trees.

**Two or three digits, and never one.** That is what makes the check exact over
this repository: it fails on every name of that shape and on nothing else. A
single digit would take in ``r1`` and ``r2``, which are rates and row names in
the curve, IRR and scenario code and mean what they say. So a decision with a
single-digit number could still hide in a name, and the review of a change is
what catches that one.

**What is not read.** The built bundle under ``viewer/python``, whose short
names are a minifier's; workflows and configuration files.
"""

from __future__ import annotations

import functools
import io
import json
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

# One part of a name: an R and two or three digits, in either case.
_PART: Final = re.compile(r"^[Rr][0-9]{2,3}$")
# A cheap first look at a file's text, so that most files are never tokenized:
# the same shape, standing between characters that are not letters or digits.
_ANYWHERE: Final = re.compile(r"(?<![A-Za-z0-9])[Rr][0-9]{2,3}(?![A-Za-z0-9])")
_IDENTIFIER: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WORD: Final = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_STRING: Final = re.compile(r"^[rRbBuUfF]*('''|\"\"\"|'|\")(.*)\1$", re.DOTALL)

_PYTHON_TREES: Final = ("bindings/python", "engines/jax", "viewer/python")
_PYTHON_SUFFIXES: Final = (".py", ".pyi")
# Read word by word: each tree, and the suffixes read in it.
_WORDS: Final = (
    ("viewer", (".ts", ".tsx", ".mts", ".mjs")),
    ("core", (".rs",)),
    ("bindings/python/src", (".rs",)),
)
_DATA_TREES: Final = ("bindings/python", "engines/jax", "viewer")
# Built output, written by viewer/build.mjs and committed for the wheel.
_BUILT: Final = "viewer/python/gaspatchio_viewer/assets/"


class Named(NamedTuple):
    """One name that is a decision number: where it is, and the name."""

    path: str
    line: int | None
    name: str


def _numbered(name: str) -> bool:
    """Return whether any underscore-separated part of a name is a decision number."""
    return any(_PART.match(part) for part in name.split("_"))


def _python_names(source: str, path: str) -> list[Named]:
    """Return each identifier, and each string spelled like one, that is numbered."""
    found: list[Named] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.NAME:
            name = token.string
        elif token.type == tokenize.STRING:
            body = _STRING.match(token.string)
            if body is None or not _IDENTIFIER.match(body.group(2)):
                continue
            name = body.group(2)
        else:
            continue
        if _numbered(name):
            found.append(Named(path, token.start[0], name))
    return found


def _words(source: str, path: str) -> list[Named]:
    """Return each word of a file, read whole, that is numbered."""
    return [
        Named(path, number, word)
        for number, line in enumerate(source.splitlines(), start=1)
        for word in _WORD.findall(line)
        if _numbered(word)
    ]


def _keys(source: str, path: str) -> list[Named]:
    """Return each key of a JSON document spelled like a name that is numbered."""
    keys: list[str] = []

    def collect(pairs: list[tuple[str, object]]) -> dict[str, object]:
        keys.extend(key for key, _ in pairs)
        return dict(pairs)

    json.loads(source, object_pairs_hook=collect)
    return [
        Named(path, None, key)
        for key in keys
        if _IDENTIFIER.match(key) and _numbered(key)
    ]


def _names(root: Path, path: str) -> list[Named]:
    """Return the numbered names one file holds, read the way its kind is read."""
    source = (root / path).read_text("utf-8")
    if _ANYWHERE.search(source) is None:
        return []
    if path.endswith(_PYTHON_SUFFIXES):
        return _python_names(source, path)
    if path.endswith(".json"):
        return _keys(source, path)
    return _words(source, path)


def _read(path: str) -> bool:
    """Return whether the scan reads a tracked path."""
    if path.startswith(_BUILT):
        return False
    if path.endswith(_PYTHON_SUFFIXES):
        return path.startswith(tuple(f"{tree}/" for tree in _PYTHON_TREES))
    if path.endswith(".json"):
        return path.startswith(tuple(f"{tree}/" for tree in _DATA_TREES))
    return any(
        path.startswith(f"{tree}/") and path.endswith(suffixes)
        for tree, suffixes in _WORDS
    )


def _shipped_files() -> list[str]:
    """Return every tracked file the scan reads, repository-relative."""
    trees = {*_PYTHON_TREES, *_DATA_TREES, *(tree for tree, _ in _WORDS)}
    listed = subprocess.run(  # noqa: S603 -- git's own path and a fixed command
        [str(GIT), "ls-files", "-z", "--", *sorted(trees)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted(path for path in listed.split("\0") if path and _read(path))


@functools.cache
def _all_names() -> list[Named]:
    """Return every numbered name in every shipped file the scan reads."""
    return [named for path in _shipped_files() for named in _names(REPO, path)]


def test_no_name_is_a_decision_number() -> None:
    found = [
        f"{named.path}{'' if named.line is None else f':{named.line}'}: {named.name}"
        for named in _all_names()
    ]

    assert found == [], (
        "A name is an internal decision number, which a reader of this "
        "repository cannot look up. Name it for what it holds, and move every "
        "reader of it with it:\n  " + "\n  ".join(found)
    )


def test_the_scan_reads_code_and_data_and_not_the_built_bundle() -> None:
    files = set(_shipped_files())

    assert len(files) > 1000, "the scan found almost nothing to read"
    assert {
        "engines/jax/bench/gpu_qualify.py",
        "engines/jax/agreement.json",
        "engines/jax/tests/test_tallies.py",
        "bindings/python/gaspatchio/curves/_curve.py",
        "viewer/src/shell/App.tsx",
        "viewer/perf/measure.mjs",
        "core/src/identity.rs",
        "bindings/python/src/vector.rs",
    } <= files
    assert not any(path.startswith(_BUILT) for path in files)
    assert not any("node_modules/" in path for path in files)


def _r(number: int) -> str:
    """Return a numbered part, built so this file does not carry one."""
    return f"r{number}"


def test_the_scan_finds_numbered_names_and_passes_over_rates(tmp_path: Path) -> None:
    (tmp_path / "bench.py").write_text(
        f"{_r(44).upper()}_BAND = 1e-12\n"
        "rate = 0.05\n"
        "r2 = rate * 2\n"
        f'report = {{"worst_inside_{_r(44)}": True, "note": "{_r(44)} in prose"}}\n'
        f"def test_under_{_r(44)}() -> None: ...\n",
        "utf-8",
    )
    (tmp_path / "page.ts").write_text(
        f"const {_r(61)} = 1;\nconst r1 = 2;\n",
        "utf-8",
    )
    (tmp_path / "data.json").write_text(
        json.dumps({"cases": {_r(44): "note", "r2": "a rate", "id": _r(44)}}),
        "utf-8",
    )

    assert [(n.line, n.name) for n in _names(tmp_path, "bench.py")] == [
        (1, f"{_r(44).upper()}_BAND"),
        (4, f"worst_inside_{_r(44)}"),
        (5, f"test_under_{_r(44)}"),
    ]
    assert [(n.line, n.name) for n in _names(tmp_path, "page.ts")] == [(1, _r(61))]
    assert [n.name for n in _names(tmp_path, "data.json")] == [_r(44)]
