# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One spelling for every measured value: the one in ``ratchets.env``.

``.github/ratchets.env`` holds the values CI enforces -- four ceilings a count
may not rise above, two floors saying how much of the package a count was taken
over, and two SHA-256 digests of the settings the type-checker counts were
taken under. ``.github/RATCHETS.md`` says what each one measures, prints the
command that produced it, and quotes what that command should print. The value
therefore has three homes and only one of them can fail a build, so the other
two can go stale without anything noticing -- which is not hypothetical: the
ruff ceiling moved three times in four commits and the page was left behind
twice, rescued each time by whoever edited it next rather than by anything that
checks.

These tests hold the two documents to each other. They read the values from
``ratchets.env``, find each one's section on the page by its
``<!-- ratchet: NAME -->`` anchor, and assert that the value in the section's
heading and the value in its command block's expected output both equal it --
in both directions, so a recorded value with no page section and a page section
naming no recorded value fail too. Nothing here cares which way a value
ratchets, or whether it ratchets at all; the two documents have to agree on it
either way.

**Two shapes, one rule.** A recorded value is either a whole number or a
sixty-four character lower-case digest, and ``_KINDS`` below carries one entry
per shape: how it is written in ``ratchets.env``, how it is written in a
heading, how it is written in an expected output, and how to normalise it
before comparing. Everything else in this module is shared between them, and
adding a third shape is adding a fourth entry to that tuple rather than a
parallel copy of the assertions. The digests are held to exactly the rule the
figures are -- a sixty-four character heading is ugly and it is the price of
the value being checked at all, which is the trade this whole module exists to
make.

What they deliberately do NOT read is the running prose. Only the heading
line and the first fenced block under it carry the live figure; the prose
around them says what the value measures, why it sits where it does and how to
move it, and a scan for numbers anywhere in the section would forbid the
figures that explanation needs -- a file total, a composition, a toolchain
version. So the rest of the section is left alone.

They assert the documents against each other and never run ruff or clippy. The
live count belongs to the CI step, which already has it; a linter run inside
the standing suite would cost more than the defect. This is a pytest rather
than a CI step on purpose -- both recurrences happened at a keyboard, in
commits whose suites were run and whose CI was days away.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
RATCHETS_FILE = REPO_ROOT / ".github" / "ratchets.env"
PAGE_FILE = REPO_ROOT / ".github" / "RATCHETS.md"
CHECKOUT_MARKER = REPO_ROOT / ".git"

# The guard is keyed on the checkout, not on the two documents, because those
# two states are opposites. The source distribution ships
# `bindings/python/tests/` and does not ship `.github/` (measured on a local
# `maturin sdist`: 432 paths under `tests/`, zero `.github` entries, and no
# `.git` at its root), so a run from an unpacked sdist has nothing to compare
# and has to stand down. Inside a checkout the same absence is the offence
# this file exists to catch -- `ratchets.env` says it itself, "Deleting one is
# not how a ratchet is retired" -- and a skip there would say nothing about
# the state the file most wants named. The wheel is neither case: it ships two
# packages and no tests at all.
pytestmark = pytest.mark.skipif(
    not CHECKOUT_MARKER.exists(),
    reason="not a repository checkout; the sdist ships tests/ but no .github/",
)

_ANCHOR = re.compile(r"^<!--\s*ratchet:\s*([A-Za-z_][A-Za-z0-9_]*)\s*-->\s*$")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
_FENCE = re.compile(r"^\s*```")

# Every figure written into this module -- in an illustration below, in the one
# synthetic section the tests build -- is this one, which is not any recorded
# figure and never will be. The alternative was tried and failed inside a single
# commit: an earlier version illustrated `_expected_output_figures` with the
# live ruff ceiling of the day, and hand-corrected the illustration from 1769 to
# 1768 in the same commit because the ceiling had moved underneath it --
# silently, unmentioned anywhere. That is exactly the staleness this module
# exists to catch, happening in this module, a few lines above the assertion
# that catches it, and it recurred at once: the very next commit moved the
# ceiling again, so that 1768 was stale a second time the same day. Naming the
# live figure here would repeat the mistake a third time, which is why this
# comment does not. A figure with no relation to any ceiling cannot go stale,
# cannot be hand-updated, and tells a reader at a glance which figures in this
# file are live.
_NOT_A_CEILING = "999"

# The same argument, for the digest shape: a value that is not either recorded
# digest and never will be, so the synthetic sections below cannot go stale.
_NOT_A_DIGEST = "d" * 64


@dataclass(frozen=True, slots=True)
class _Kind:
    """One shape a recorded value takes, and how to find it in each document.

    Two entries exist: a whole number, and a SHA-256 digest. Splitting them
    here rather than in the assertions is what keeps the rule single -- the
    heading and the expected output must both spell the recorded value -- for
    values that are written and normalised differently. A third shape would be
    a third entry, not a second copy of the tests.
    """

    assignment: re.Pattern[str]
    in_heading: re.Pattern[str]
    in_answer: re.Pattern[str]

    def normalise(self, text: str) -> str:
        """Return one written value in the form two documents get compared in.

        Only figures need normalising, and they need it because the page is
        free to write ``2,771`` where the file writes ``2771``. Digests have
        one spelling, so this is the identity for them.
        """
        return text.replace(",", "").replace("_", "")


#: Whole numbers: the four ceilings and the two floors.
_FIGURE_KIND = _Kind(
    assignment=re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(\d[\d_]*)\s*$"),
    in_heading=re.compile(r"`(\d[\d,_]*)`"),
    in_answer=re.compile(r"\d[\d,_]*"),
)

#: SHA-256 digests: the settings each type-checker count was measured under.
#: Matched before the figure shape, so that an all-digit digest -- which no
#: tree will ever produce, and which the file is free to hold anyway -- is
#: read as the digest it is rather than as an implausible ceiling.
_DIGEST_KIND = _Kind(
    assignment=re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*([0-9a-f]{64})\s*$"),
    in_heading=re.compile(r"`([0-9a-f]{64})`"),
    in_answer=re.compile(r"[0-9a-f]{64}"),
)

_KINDS = (_DIGEST_KIND, _FIGURE_KIND)


@dataclass(frozen=True, slots=True)
class _Section:
    """One anchored section of the page: its heading and its command block."""

    name: str
    line: int
    heading: str
    block: tuple[str, ...]

    @property
    def where(self) -> str:
        """Name the section the way someone would go and find it again."""
        return f"RATCHETS.md:{self.line} ({self.name})"


def _text_of(path: Path) -> str:
    """Read one of the two documents, failing by name when it is not there.

    Reached only inside a checkout, where a missing document is the failure
    rather than a reason to stand down: the value it holds is what the CI
    steps read, and a step with no recorded value waves through the
    regression the ratchet exists to catch.
    """
    assert path.is_file(), (
        f"{path} is missing -- deleting a ratchet document is not how a "
        f"ratchet is retired; remove its step instead"
    )
    return path.read_text(encoding="utf-8")


def _recorded_values() -> dict[str, tuple[_Kind, str]]:
    """Return every ``NAME=<value>`` assignment in ``ratchets.env``.

    Parsed rather than grepped, and generalised over the names and the
    shapes: a check hand-written for ruff alone repeats this failure the day
    another value moves, and one hand-written for whole numbers repeats it
    the day a value stops being one.
    """
    found: dict[str, tuple[_Kind, str]] = {}
    for line in _text_of(RATCHETS_FILE).splitlines():
        for kind in _KINDS:
            assignment = kind.assignment.match(line)
            if assignment is not None:
                found[assignment.group(1)] = (kind, kind.normalise(assignment.group(2)))
                break
    return found


def _first_fenced_block(lines: list[str]) -> tuple[str, ...]:
    """Return the first fenced region, stopping at the next heading."""
    block: list[str] = []
    in_block = False
    for line in lines:
        if _FENCE.match(line):
            if in_block:
                break
            in_block = True
        elif in_block:
            block.append(line)
        elif _HEADING.match(line):
            break
    return tuple(block)


def _section_at(lines: list[str], anchor_index: int, name: str) -> _Section:
    """Read the heading and command block belonging to one anchor.

    The heading is the next non-blank line after the anchor; an anchor not
    sitting on one is reported as a section with no heading and no block,
    which the equality assertions then fail on.
    """
    empty = _Section(name=name, line=anchor_index + 1, heading="", block=())
    rest = lines[anchor_index + 1 :]
    for offset, line in enumerate(rest):
        if not line.strip():
            continue
        heading = _HEADING.match(line)
        if heading is None:
            return empty
        return _Section(
            name=name,
            line=anchor_index + 1,
            heading=heading.group(1),
            block=_first_fenced_block(rest[offset + 1 :]),
        )
    return empty


def _documented() -> dict[str, _Section]:
    """Return every anchored section on the page, keyed by the name it claims."""
    lines = _text_of(PAGE_FILE).splitlines()
    return {
        anchor.group(1): _section_at(lines, index, anchor.group(1))
        for index, line in enumerate(lines)
        if (anchor := _ANCHOR.match(line)) is not None
    }


def _heading_values(kind: _Kind, section: _Section) -> list[str]:
    """Return the backticked values of ``kind`` in a section's heading."""
    return [kind.normalise(text) for text in kind.in_heading.findall(section.heading)]


def _expected_output_values(kind: _Kind, section: _Section) -> list[str]:
    """Return the values a section's command block says the command prints.

    An expected output is written after an arrow -- ``-> "Found 999
    errors."``, ``# -> 53`` -- which is what separates the answer from the
    command that produces it. Everything after the first arrow on such a
    line is the answer. (The 999 is deliberately not any recorded figure;
    see ``_NOT_A_CEILING``.)

    What comes back is compared against ``[value]``, list against list, so
    the rule is *exactly one* value and it equals the recorded one: a
    second value is reported even when it repeats that value
    (``["999", "999"] != ["999"]``). That is stricter than "no value
    disagrees", and deliberately. A block whose expected output names two
    numbers has not said which of them the ledger keeps, and the day the
    value moves that is a question rather than a substitution. Failing
    when the second value appears asks it then, while both are still true,
    instead of when they have drifted apart.

    Reading only values of the section's own kind is what lets a digest
    section print a digest without the digit runs inside it being read as
    six loose figures.
    """
    values: list[str] = []
    for line in section.block:
        _, arrow, answer = line.partition("->")
        if arrow:
            values.extend(
                kind.normalise(text) for text in kind.in_answer.findall(answer)
            )
    return values


def _disagreement(
    kind: _Kind,
    section: _Section,
    read: Literal["heading", "expected output"],
    value: str,
) -> str | None:
    """Report one section's values, or ``None`` when they are exactly ``[value]``."""
    values_of = _heading_values if read == "heading" else _expected_output_values
    values = values_of(kind, section)
    if values == [value]:
        return None
    return (
        f"{section.where} {read} {values} != {RATCHETS_FILE.name} "
        f"{section.name}={value}"
    )


def _disagreements(read: Literal["heading", "expected output"]) -> list[str]:
    """Return one line per recorded value whose page values are not it."""
    sections = _documented()
    return [
        line
        for name, (kind, value) in sorted(_recorded_values().items())
        if name in sections
        and (line := _disagreement(kind, sections[name], read, value)) is not None
    ]


def test_both_documents_are_present() -> None:
    """Neither document may go missing: that is not how a ratchet is retired."""
    assert _text_of(RATCHETS_FILE)
    assert _text_of(PAGE_FILE)


def test_a_repeated_expected_figure_is_still_a_disagreement() -> None:
    """One value per block -- a second one fails even when it is the ceiling.

    The strictness is the part of the rule a reader is least likely to
    expect, so it is pinned here rather than left to be discovered by the
    first section whose command prints two numbers.

    The section is synthetic and so is its figure: it is ``_NOT_A_CEILING``
    throughout rather than whatever ruff happened to report this month, so
    that nothing here invites the hand-update it exists to catch.
    """
    figure = _NOT_A_CEILING
    section = _Section(
        name="RUFF_MAX",
        line=42,
        heading=f"Ruff violations -- `{figure}`",
        block=(
            f'.venv/bin/ruff check gaspatchio          # -> "Found {figure} errors."',
            f".venv/bin/ruff check gaspatchio --quiet  # -> {figure}",
        ),
    )

    assert _expected_output_values(_FIGURE_KIND, section) == [figure, figure]
    assert _disagreement(_FIGURE_KIND, section, "expected output", figure) == (
        f"RATCHETS.md:42 (RUFF_MAX) expected output ['{figure}', '{figure}'] "
        f"!= ratchets.env RUFF_MAX={figure}"
    )

    one_figure = replace(section, block=section.block[:1])
    assert _disagreement(_FIGURE_KIND, one_figure, "expected output", figure) is None


def test_a_recorded_digest_is_held_to_the_page_the_same_way() -> None:
    """A digest section is read as a digest, not as the digits inside one.

    The shape that would quietly break the rule is a digest block read with
    the figure patterns: ``a94c7167...`` contains digit runs, so a
    figure-shaped reader finds a handful of loose numbers in it and compares
    them against a value it can never equal. Pinning the two readers against
    one synthetic section says which one a digest section gets, and that the
    strictness is the same either way.

    Both values here are synthetic -- ``_NOT_A_DIGEST`` and
    ``_NOT_A_CEILING`` -- for the reason ``_NOT_A_CEILING`` exists.
    """
    digest = _NOT_A_DIGEST
    section = _Section(
        name="MYPY_SUPPRESSION_SHA",
        line=42,
        heading=f"Settings mypy was measured under -- `{digest}`",
        block=(
            ".venv/bin/python ../../.github/type_suppression_fingerprint.py mypy",
            f"# -> {digest}",
        ),
    )

    assert _heading_values(_DIGEST_KIND, section) == [digest]
    assert _expected_output_values(_DIGEST_KIND, section) == [digest]
    assert _disagreement(_DIGEST_KIND, section, "heading", digest) is None
    assert _disagreement(_DIGEST_KIND, section, "expected output", digest) is None

    # The same section read as a figure: nothing in the heading, and nothing
    # in the block either, because `_NOT_A_DIGEST` is all letters. That is
    # the reader a digest section must not get.
    assert _heading_values(_FIGURE_KIND, section) == []
    assert _disagreement(_FIGURE_KIND, section, "heading", _NOT_A_CEILING) == (
        f"RATCHETS.md:42 (MYPY_SUPPRESSION_SHA) heading [] "
        f"!= ratchets.env MYPY_SUPPRESSION_SHA={_NOT_A_CEILING}"
    )

    # A digest that lost a character is not a digest, and is not silently
    # read as one.
    truncated = replace(section, heading=f"Settings -- `{digest[:-1]}`")
    assert _heading_values(_DIGEST_KIND, truncated) == []


def test_the_two_documents_cover_the_same_ratchets() -> None:
    """Every recorded value has a section, and every section a value."""
    recorded = _recorded_values()
    sections = _documented()

    assert recorded, f"no NAME=<value> assignment parsed from {RATCHETS_FILE}"
    assert sections, f"no <!-- ratchet: NAME --> anchor parsed from {PAGE_FILE}"

    assert sorted(set(recorded) - set(sections)) == [], "value with no page section"
    assert sorted(set(sections) - set(recorded)) == [], "page section with no value"


def test_each_section_heading_repeats_its_recorded_figure() -> None:
    """The value in the heading is the recorded one, spelled a second time."""
    assert _disagreements("heading") == []


def test_each_command_block_expects_its_recorded_figure() -> None:
    """The value the section says its command prints is the recorded one too."""
    assert _disagreements("expected output") == []


def test_census_heading_and_example_match_the_enforced_ceilings() -> None:
    """The census uses its Python-owned limits rather than ratchets.env."""
    from tests.graph.census import ALLOWLIST_CEILINGS

    text = _text_of(PAGE_FILE)
    section = text.split("### Census allowlist totals — ", 1)[1].split("\n### ", 1)[0]
    heading, rest = section.split("\n", 1)
    assert [int(value) for value in re.findall(r"`(\d+)`", heading)] == list(
        ALLOWLIST_CEILINGS.values(),
    )
    example = rest.split("```", 2)[1]
    documented = dict(re.findall(r"'([A-Z_]+)': (\d+)", example))
    assert {
        name: int(value) for name, value in documented.items()
    } == ALLOWLIST_CEILINGS
