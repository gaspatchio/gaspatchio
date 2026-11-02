# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One row per operation, held against the document and against the docstrings.

An operation's tier, its specification clause, the sentence a walk-through
speaks for it and the rule its clause states for a period carrying no value
were four copies in four files with nothing between them. They are one row
now, and these are the checks that keep the row honest at both ends.

**Upward, the document is the authority.** The census below reads
``spec/graph-artifact/v0-preview.md`` and fails when a row's clause is not
a section of it, when that section does not answer for the identifier, or
when a row quotes a rule the section does not state. The document is never
written from the row: a disagreement is a wrong row.

**Downward, the row is the authority.** Every hand-written docstring that
states a rule names the row it states, and fails here when the two part
company. The four reductions are where that bites: what they do with a null
period changed, and one docstring was left saying the old thing, which
is the drift this file exists to catch the next time.

**Sideways, the kit prints the clause column.** ``contracts.json`` is
generated from the same rows, and its checked-in bytes are compared with
what the generator produces, so a clause that moves in the table and not in
the published map fails before a consumer is sent to the wrong section.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from gaspatchio._semantic.vocabulary import VOCABULARY, Operation
from gaspatchio.frame.graph.tiers import TIERS
from gaspatchio.frame.graph.trace_voice import SENTENCES, SPOKEN_BY_SUBSTITUTION

if TYPE_CHECKING:
    from types import ModuleType

_REPOSITORY = Path(__file__).resolve().parents[4]
_SPECIFICATION = _REPOSITORY / "spec" / "graph-artifact" / "v0-preview.md"
_CONFORMANCE = _REPOSITORY / "spec" / "graph-artifact" / "conformance"
_VOCABULARY_SECTION = "### 11.1 The core vocabulary"

# Where each rule sentence is hand-written outside the row: the identifier,
# the module, and the object inside it whose docstring states it, an empty
# name meaning the module's own docstring. Named one by one rather than
# found by a search, because a site that quietly stopped stating the rule
# would drop out of a search and take its own check with it.
_DOCSTRING_SITES: Final[tuple[tuple[str, str, str], ...]] = (
    ("sum", "gaspatchio._semantic.operations", "_list_sum"),
    ("sum", "gaspatchio.frame.lowering.rules.reduction", ""),
    ("sum", "gaspatchio.frame.lowering.rules.reduction", "_lower_sum"),
    ("mean", "gaspatchio._semantic.operations", "_list_mean"),
    ("mean", "gaspatchio.frame.lowering.rules.reduction", "_lower_mean"),
    ("min", "gaspatchio._semantic.operations", "_list_min"),
    ("min", "gaspatchio.frame.lowering.rules.reduction", "_lower_min"),
    ("max", "gaspatchio._semantic.operations", "_list_max"),
    ("max", "gaspatchio.frame.lowering.rules.reduction", "_lower_max"),
    # The two folds share one lowering and one module, so one sentence in
    # each place answers for both rows; 11.1.9 states the rule once for the
    # pair and the rows quote it once each.
    ("cum_prod", "gaspatchio.frame.lowering.rules.accumulation", ""),
    ("cum_prod", "gaspatchio.frame.lowering.rules.accumulation", "_lower_accumulation"),
    ("cum_sum", "gaspatchio.frame.lowering.rules.accumulation", ""),
    ("cum_sum", "gaspatchio.frame.lowering.rules.accumulation", "_lower_accumulation"),
    (
        "projection.cumulative_survival",
        "gaspatchio.accessors.projection",
        "ProjectionColumnAccessor.cumulative_survival",
    ),
    (
        "projection.cumulative_survival",
        "gaspatchio.frame.lowering.rules.projection",
        "_lower_cumulative_survival",
    ),
    (
        "projection.accumulate",
        "gaspatchio.accessors.projection",
        "ProjectionColumnAccessor.accumulate",
    ),
    (
        "projection.accumulate",
        "gaspatchio.frame.lowering._polars.plugins",
        "accumulate",
    ),
    (
        "projection.remaining_sum",
        "gaspatchio.accessors.projection",
        "ProjectionColumnAccessor.remaining_sum",
    ),
    (
        "projection.remaining_sum",
        "gaspatchio.frame.lowering.rules.projection",
        "_lower_remaining_sum",
    ),
    (
        "projection.prospective_value",
        "gaspatchio.accessors.projection",
        "ProjectionColumnAccessor.prospective_value",
    ),
)

# The same sentences where the docstring is generated rather than written:
# the proxy surface renders the binder's own words, so these read the row
# through the generator. A drift test already holds the file byte for byte;
# this says what those bytes have to say.
_GENERATED_SITES: Final[tuple[tuple[str, str, str], ...]] = (
    ("sum", "gaspatchio.column._generated_proxy", "ListNamespace.sum"),
    ("mean", "gaspatchio.column._generated_proxy", "ListNamespace.mean"),
    ("min", "gaspatchio.column._generated_proxy", "ListNamespace.min"),
    ("max", "gaspatchio.column._generated_proxy", "ListNamespace.max"),
)

# The rows whose rule no docstring states in the clause's own words. It is
# empty and is meant to stay empty: the last six sentences were brought
# across, four of them into docstrings that had claimed the whole answer
# went null where their clause keeps the other positions. The name stays
# because it is the other half of the partition below -- somewhere for a
# rule row nobody has censused to be named on purpose, so that a new row
# arriving uncovered is a decision somebody took rather than an omission
# nobody noticed.
_RULES_STATED_IN_OTHER_WORDS: Final[frozenset[str]] = frozenset()


def _flattened(text: str) -> str:
    """Return ``text`` with backticks dropped and whitespace closed to one space.

    Both the document and a docstring wrap their prose, so a sentence in
    either can carry a newline in the middle of it. Comparing the flattened
    forms asks whether the words are the same rather than whether the two
    happened to wrap in the same place.

    Backticks go for the same reason, one step further in. The document
    marks a code span with one backtick and a docstring marks it with two,
    so ``s[t]`` and `s[t]` are one span spelled for two readers. Dropping
    the character from both sides lets the row keep the document's spelling
    and each docstring keep its own.
    """
    return " ".join(text.replace("`", "").split())


def _clauses() -> dict[str, str]:
    """Return the text of every numbered section, keyed by its number.

    A section runs to the next heading of any level, which is what "the
    clause states it" has to mean for a document whose entries are one
    heading each.
    """
    lines = _SPECIFICATION.read_text("utf-8").splitlines(keepends=True)
    headings = [
        index for index, line in enumerate(lines) if re.match(r"^#{2,4} ", line)
    ]
    sections: dict[str, str] = {}
    for position, index in enumerate(headings):
        numbered = re.match(r"^#{2,4} (\d+(?:\.\d+)*)", lines[index])
        if numbered is None:
            continue
        end = headings[position + 1] if position + 1 < len(headings) else len(lines)
        sections[numbered.group(1)] = "".join(lines[index:end])
    return sections


_CLAUSES: Final[dict[str, str]] = _clauses()


def _printed_vocabulary() -> list[str]:
    """Return the identifiers the document's own 11.1 table prints, in order."""
    text = _SPECIFICATION.read_text("utf-8")
    tail = text[text.index(_VOCABULARY_SECTION) + len(_VOCABULARY_SECTION) :]
    stop = tail.find("\n#")
    section = tail if stop < 0 else tail[:stop]
    rows = [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.strip().startswith("|")
    ]
    body = [row for row in rows if not all(set(cell) <= set("-: ") for cell in row)]
    return [row[0] for row in body[1:]]


def _docstring(module_name: str, attribute: str) -> str:
    """Return the docstring of one named site, module or object inside it."""
    module = importlib.import_module(module_name)
    if not attribute:
        return inspect.getdoc(module) or ""
    owner: object = module
    for step in attribute.split("."):
        owner = getattr(owner, step)
    return inspect.getdoc(owner) or ""


def _kit_module(name: str) -> ModuleType:
    """Load one conformance-kit script by path, the way the kit is run."""
    spec = importlib.util.spec_from_file_location(
        f"_kit_{name}", _CONFORMANCE / f"{name}.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - a path guard
        message = f"cannot load the kit script {name}"
        raise RuntimeError(message)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def _rule_rows() -> list[str]:
    """Return every identifier whose row quotes a rule from its clause."""
    return [entry.identifier for entry in VOCABULARY if entry.rule is not None]


# --- the table itself --------------------------------------------------------


def test_every_identifier_stands_once() -> None:
    """One row per operation: a second row is a second answer nobody reads."""
    identifiers = [entry.identifier for entry in VOCABULARY]

    assert len(identifiers) == len(set(identifiers))


def test_the_rows_stand_in_the_order_the_document_prints_them() -> None:
    """Scanning the table against the document is two columns, not a lookup.

    The document's own 11.1 table is the fifteen binary operators a formula
    is written with, and then every other identifier alphabetically. The
    rows take that order so that a reviewer holding the two side by side
    reads down both at once.
    """
    assert [entry.identifier for entry in VOCABULARY] == _printed_vocabulary()


# --- the three views ---------------------------------------------------------


def test_the_tier_table_is_the_row_s_tier_column() -> None:
    """Every tier the classifier reads comes from the row, and only there."""
    assert dict(TIERS) == {entry.identifier: entry.tier for entry in VOCABULARY}


def test_the_sentence_table_is_the_row_s_voice_column() -> None:
    """Every sentence a walk-through speaks comes from the row, and only there."""
    assert dict(SENTENCES) == {
        entry.identifier: entry.voice for entry in VOCABULARY if entry.voice is not None
    }


def test_the_operators_are_the_rows_that_carry_no_sentence() -> None:
    """A row without a sentence is an operator whose arithmetic already speaks."""
    assert (
        frozenset(entry.identifier for entry in VOCABULARY if entry.voice is None)
        == SPOKEN_BY_SUBSTITUTION
    )


# --- the document is the authority -------------------------------------------


@pytest.mark.parametrize("entry", VOCABULARY, ids=lambda entry: entry.identifier)
def test_every_row_names_a_section_the_document_has(entry: Operation) -> None:
    """A clause nothing in the document answers to sends a consumer nowhere."""
    assert entry.clause in _CLAUSES


@pytest.mark.parametrize("entry", VOCABULARY, ids=lambda entry: entry.identifier)
def test_every_row_s_section_answers_for_that_identifier(entry: Operation) -> None:
    """The section a row points at is one that talks about the operation.

    Several sections answer for a family in one entry -- the three ways of
    moving a value to a whole step, the eight date operations, the eleven
    schedule reads -- so the heading is not always the identifier. The
    section's own text always names it.
    """
    assert entry.identifier in _CLAUSES[entry.clause]


@pytest.mark.parametrize("identifier", _rule_rows())
def test_every_rule_a_row_quotes_is_stated_by_its_own_clause(identifier: str) -> None:
    """The rule is read out of the document, never written into it.

    A row quoting a sentence its clause does not state is a row that has
    drifted from the authority, and the fix is the row. This is the check
    that says so, and it is why nothing in this file edits the document.
    """
    entry = next(row for row in VOCABULARY if row.identifier == identifier)
    assert entry.rule is not None

    assert _flattened(entry.rule) in _flattened(_CLAUSES[entry.clause])


# --- the row is the authority for every docstring that states it -------------


@pytest.mark.parametrize(
    ("identifier", "module_name", "attribute"),
    _DOCSTRING_SITES,
    ids=[
        f"{site[0]}-{site[1].rsplit('.', 1)[-1]}-{site[2] or 'module'}"
        for site in _DOCSTRING_SITES
    ],
)
def test_each_hand_written_docstring_states_its_row_s_rule(
    identifier: str, module_name: str, attribute: str
) -> None:
    """One sentence, hand-written once, and checked everywhere it is repeated."""
    entry = next(row for row in VOCABULARY if row.identifier == identifier)
    assert entry.rule is not None

    assert _flattened(entry.rule) in _flattened(_docstring(module_name, attribute))


@pytest.mark.parametrize(
    ("identifier", "module_name", "attribute"),
    _GENERATED_SITES,
    ids=[site[0] for site in _GENERATED_SITES],
)
def test_each_generated_docstring_carries_the_rule_it_was_rendered_from(
    identifier: str, module_name: str, attribute: str
) -> None:
    """The public surface says what the row says, because it is printed from it."""
    entry = next(row for row in VOCABULARY if row.identifier == identifier)
    assert entry.rule is not None

    assert _flattened(entry.rule) in _flattened(_docstring(module_name, attribute))


def test_every_rule_row_is_either_censused_or_reported() -> None:
    """A new rule cannot arrive with nobody having decided where it is said.

    Either a docstring states the row's sentence and is named above, or the
    row is named as one whose docstrings state the rule in other words. The
    second list is empty, so today this says every rule row is censused; a
    rule belonging to neither list fails here.
    """
    censused = {identifier for identifier, _, _ in _DOCSTRING_SITES}

    assert censused | _RULES_STATED_IN_OTHER_WORDS == set(_rule_rows())


def test_no_row_is_both_censused_and_reported() -> None:
    """The two lists are a partition: a row is checked here or it is not."""
    censused = {identifier for identifier, _, _ in _DOCSTRING_SITES}

    assert not censused & _RULES_STATED_IN_OTHER_WORDS


# --- the kit prints the clause column ----------------------------------------


def test_the_published_clause_map_is_the_bytes_the_table_generates() -> None:
    """One map, generated, so a moved clause cannot ship half-applied.

    ``contracts.json`` is read by ``build_kit.py`` and by the boundary
    review, and a consumer holding it is told which section to implement. It
    is the table's clause column printed alphabetically, and these are the
    bytes.
    """
    generator = _kit_module("make_contracts")

    assert (_CONFORMANCE / "contracts.json").read_bytes() == generator.contracts_bytes()
