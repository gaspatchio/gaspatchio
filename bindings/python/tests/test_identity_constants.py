# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One spelling for the framework's identity scheme and its scratch prefix.

Every ``source_sha()`` and ``fingerprint()`` the framework hands out is
stamped with the scheme it was taken under, and every rollforward kernel
scratch column is named with the prefix that keeps it out of the model's
own schema. Both are read back elsewhere -- by the stamp parser, by the
column that strips the scratch away on collect -- so a second spelling of
either is a place the two can drift apart without a test noticing. These
tests hold the package to one spelling of each: the constant.
"""

from __future__ import annotations

import ast
from pathlib import Path

from gaspatchio._identity import SHA256_PREFIX
from gaspatchio.rollforward._registry import HIDDEN_PREFIX

PACKAGE = Path(__file__).resolve().parents[1] / "gaspatchio"


def _docstring_line_numbers(tree: ast.Module) -> set[int]:
    """Return every line a module, class or function docstring occupies.

    Prose is allowed to name the scheme -- that is how the docstrings and
    their doctests say what a stamp looks like -- so the search is over
    code only, and this is the part of each file that is not code.
    """
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    occupied: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = first.end_lineno or first.lineno
            occupied.update(range(first.lineno, end + 1))
    return occupied


def _spelt_at(path: Path, prefix: str) -> list[int]:
    """Return the line of every string in ``path`` whose value starts with ``prefix``.

    Reading the parsed value rather than the source text is what separates
    a second spelling of a constant from prose that merely names one. A
    field description reading "The framework's 'sha256:<hex>' stamp" is a
    sentence about the scheme; ``"sha256:"`` at the head of a string is the
    scheme itself, written out again -- and it is caught however it is
    written, single- or double-quoted, an f-string, a ``%`` template, a
    ``.format`` template or one half of a concatenation.

    Docstrings are skipped, so the prose and doctests that say what a stamp
    looks like are free to say it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_line_numbers(tree)
    return sorted(
        {
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(prefix)
            and node.lineno not in docstrings
        }
    )


def _offenders(prefix: str, *, defined_in: str) -> list[str]:
    """Return ``path:line`` for every string that spells ``prefix`` itself."""
    return [
        f"{path.relative_to(PACKAGE)}:{line}"
        for path in sorted(PACKAGE.rglob("*.py"))
        if path.name != defined_in
        for line in _spelt_at(path, prefix)
    ]


def test_the_stamp_scheme_is_spelled_once() -> None:
    """Only ``_canonical`` writes the scheme; everywhere else reads it."""
    assert SHA256_PREFIX == "sha256:"

    assert _offenders(SHA256_PREFIX, defined_in="_canonical.py") == []


def test_the_scratch_prefix_is_spelled_once() -> None:
    """Only the registry that mints the scratch names writes the prefix."""
    assert HIDDEN_PREFIX == "__rollforward_"

    assert _offenders(HIDDEN_PREFIX, defined_in="_registry.py") == []
