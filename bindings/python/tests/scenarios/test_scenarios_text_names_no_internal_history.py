# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What the scenarios package says to a user names no version history or internal path.

A 1.0.0 build refused a dict of aggregations with "v0.1 plan format detected
... v0.2 uses a list ... See ref/41-backend-portability/specs/...§10", and its
public docstrings spoke of "the v0.2 surface (GSP-101)" and "This implements
GSP-65". A user has no ``ref/`` directory, no issue tracker behind a GSP number
and no reason to know which pre-release shape a rule replaced: the sentence is
said in words, about what to write.

Read here: every string literal in ``gaspatchio/scenarios`` that is not a
docstring (the text a refusal or a warning hands over), and the docstring of
the package and of everything it and ``gaspatchio.scenarios.shocks`` export
(what ``help()`` and the API reference show).
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Final

import pytest

import gaspatchio.scenarios
import gaspatchio.scenarios.shocks

_PACKAGE: Final = Path(gaspatchio.scenarios.__file__).resolve().parent

# A pre-release version, a path into the repository's reference tree, an
# internal issue number. The seed salt ``gsp-100|...`` is lower case and is
# data, not text: changing it would change every derived seed.
_INTERNAL: Final = re.compile(r"\bv0\.\d+\b|\bref/\d|\bGSP-\d+\b")


def _spoken_literals(path: Path) -> list[str]:
    """Return ``file:line: text`` for each non-docstring literal naming history."""
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    documentation = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    return [
        f"{path.name}:{node.lineno}: {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in documentation
        and _INTERNAL.search(node.value)
    ]


def test_no_message_names_a_version_a_ref_path_or_an_issue() -> None:
    """Refusals and warnings say what to do, not which pre-release came before."""
    found = [
        line
        for path in sorted(_PACKAGE.glob("*.py"))
        for line in _spoken_literals(path)
    ]
    assert found == []


def _public_objects() -> list[tuple[str, object]]:
    exported = [
        (f"{module.__name__}.{name}", getattr(module, name))
        for module in (gaspatchio.scenarios, gaspatchio.scenarios.shocks)
        for name in getattr(module, "__all__", ())
    ]
    return [("gaspatchio.scenarios", gaspatchio.scenarios), *exported]


_PUBLIC: Final = _public_objects()


# Ids by name: an object's repr carries its address, which differs between
# the workers of a parallel run and would make each collect different tests.
@pytest.mark.parametrize(("name", "obj"), _PUBLIC, ids=[name for name, _ in _PUBLIC])
def test_no_public_docstring_names_a_version_a_ref_path_or_an_issue(
    name: str, obj: object
) -> None:
    """``help()`` and the API reference read these to the user."""
    doc = inspect.getdoc(obj) or ""
    assert not _INTERNAL.findall(doc), (name, _INTERNAL.findall(doc))


def test_aggregations_keyed_by_alias_are_refused_with_the_fix() -> None:
    """The refusal says what a plan's aggregations look like and how to get there."""
    with pytest.raises(ValueError, match="aggregations are a list") as info:
        gaspatchio.scenarios.parse_aggregations(
            {"scr": {"kind": "Sum", "column": "loss"}}  # type: ignore[arg-type]
        )
    said = str(info.value)
    assert "'scr'" in said
    assert "move each key into its entry as 'alias'" in said


def test_the_audit_record_module_names_no_issue_and_its_version_note_holds() -> None:
    """The record's module says what it is, and its 2.1 note says what 2.1 removed.

    Its docstring opened "Audit sidecar writer/reader for GSP-101.", an issue
    number a reader has no tracker behind, and the comment over
    ``AUDIT_SCHEMA_VERSION`` called 2.1 additive over 2.0 -- "every field a
    2.0 reader knows is still written" -- when 2.1 removed
    ``run_metadata.library_version``, the key 0.9.0's 2.0 record wrote.
    """
    from gaspatchio.scenarios import _audit

    assert not _INTERNAL.findall(inspect.getdoc(_audit) or "")
    source = Path(_audit.__file__).read_text("utf-8")
    note = source[: source.index('AUDIT_SCHEMA_VERSION = "2.1"')]
    note = note[note.rindex("# 2.1 adds") :]
    assert "every field a 2.0 reader knows is still written" not in note
    assert "removes ``run_metadata.library_version``" in note
