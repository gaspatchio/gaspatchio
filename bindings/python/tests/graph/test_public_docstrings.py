# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The calculation graph's public docstrings are written for a public reader.

The API reference renders these docstrings verbatim: ``GraphExporter``,
``export()``, ``node_values()``, ``diff_artifacts`` and the rest of
``gaspatchio.frame.graph``'s public surface reach the published page exactly as
they are written here, and nothing between the source and the page reads them
for tone. So the vocabulary the project uses about itself -- what the code
calls a boundary between two of its parts, which pre-release the format is at,
the identifier a decision was filed under -- would reach a reader who has none
of that context, and reads to them as an unfinished product.

This walks the whole public surface: every name in the package's ``__all__``
that is a class or a function of this package, each class's own public
methods and properties, and each model's field descriptions. It fails on any
term in :data:`_INTERNAL_TERMS`, in any case, naming where the term is and
what to write instead. Extend the table when another one turns up; private
helpers and internal modules keep their own vocabulary and are not read here.

The one pre-release word a reader is owed is the schema identifier the
document carries, :data:`SCHEMA_ID`, which ``export()`` states so a reader
knows what the file will say it conforms to. That exact identifier is allowed;
any other spelling of it -- a stale one above all -- is not.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

from pydantic import BaseModel

from gaspatchio.frame import graph

# Each term, and what to say instead, matched in any case. Word-bounded where
# the term is a word, so an ordinary word that contains one is not caught.
_INTERNAL_TERMS: tuple[tuple[str, str], ...] = (
    (r"\bseams?\b", "say what the method does for its caller"),
    (r"\breference adapter\b", "say what the pairing is used for"),
    (r"v0-preview", "use the constant, or say the format is pre-release"),
    (r"\bpreview\b", "say the format is pre-release, and what that means"),
    (r"\bedition\b", "name the behaviour, not the format's release history"),
    (
        r"\b(?:working|private) (?:repository|record|branch|copy)\b",
        "the project's own workspace is no part of the product",
    ),
    (r"\bR\d{1,3}\b", "a decision's filing number means nothing to a reader"),
    (r"\bruling\b|\bruled\b", "state the behaviour and its reason"),
    # Any ticket-shaped identifier, less the standards a docstring may name.
    # Upper case only, unlike the rest: "level-4" is a tutorial, not a ticket.
    (
        r"(?-i:\b(?!(?:UTF|ISO|SHA|IEEE|RFC)-)[A-Z]{2,5}-\d+\b)",
        "a ticket number means nothing to a reader",
    ),
    # A stage label is the word and the number together: a policy called P1
    # in an example is a policy, not a stage.
    (
        r"\b(?:phase|stage|gate) P[1-4]\b|\bP[1-4] (?:phase|stage|gate)\b",
        "a stage label means nothing to a reader",
    ),
    (r"\bdoors?\b", "name the operation, the method or the call"),
    (r"\bMVP\b", "working vocabulary, not product"),
)


def _is_ours(obj: object) -> bool:
    """Return whether ``obj`` is defined in this package rather than borrowed."""
    return str(getattr(obj, "__module__", "")).startswith("gaspatchio")


def _members(cls: type) -> list[tuple[str, str]]:
    """Return each public method's and property's docstring a class defines."""
    found: list[tuple[str, str]] = []
    for name, member in vars(cls).items():
        if name.startswith("_"):
            continue
        target: Any = member
        if isinstance(member, (staticmethod, classmethod)):
            target = member.__func__
        if isinstance(member, property):
            target = member.fget
        if (callable(target) and _is_ours(target)) or isinstance(member, property):
            found.append((f"{cls.__name__}.{name}", inspect.getdoc(target) or ""))
    if issubclass(cls, BaseModel):
        found.extend(
            (f"{cls.__name__}.{field}", info.description or "")
            for field, info in cls.model_fields.items()
        )
    return found


def _public_docstrings() -> list[tuple[str, str]]:
    """Return every public docstring of the surface, with where it is."""
    found: list[tuple[str, str]] = []
    for name in graph.__all__:
        obj = getattr(graph, name)
        if not (inspect.isclass(obj) or inspect.isfunction(obj)) or not _is_ours(obj):
            continue
        found.append((name, inspect.getdoc(obj) or ""))
        if inspect.isclass(obj):
            found.extend(_members(obj))
    return found


def test_the_walk_reaches_what_the_api_page_renders() -> None:
    """The surface read here includes every object the published page renders."""
    reached = {where for where, _ in _public_docstrings()}

    assert {
        "GraphExporter",
        "GraphExporter.export",
        "GraphExporter.export_with_sidecar",
        "GraphExporter.node_values",
        "GraphFrameAccessor",
        "GraphFrameAccessor.affected",
        "GraphFrameAccessor.fingerprint",
        "validate_artifact",
        "diff_artifacts",
        "ModelIdentity",
        "ModelIdentity.model_points",
    } <= reached


def test_no_public_docstring_speaks_the_project_s_own_vocabulary() -> None:
    """Every hit is named with where it is and what to write instead."""
    hits = [
        f"{where}: {match.group(0)!r} -- {advice}"
        for where, text in _public_docstrings()
        for pattern, advice in _INTERNAL_TERMS
        for match in re.finditer(
            pattern, text.replace(graph.SCHEMA_ID, ""), re.IGNORECASE
        )
    ]

    assert hits == [], "\n".join(hits)


def test_export_states_the_identifier_its_document_carries() -> None:
    """A reader of ``export()`` is told what the file says it conforms to."""
    said = inspect.getdoc(graph.GraphExporter.export) or ""

    assert graph.SCHEMA_ID in said


def test_a_policy_called_p1_is_not_a_stage_label() -> None:
    """The table reads a stage label as a label, not as any P and a digit."""
    example = "policy_id: ['P1', 'P2'] -- and not one of them is phase P3."
    matched = [
        match.group(0)
        for pattern, _ in _INTERNAL_TERMS
        for match in re.finditer(pattern, example, re.IGNORECASE)
    ]

    assert matched == ["phase P3"]
