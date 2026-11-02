# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Count the files that move when one operation's wording changes.

An operation says what it means twice: in the sentence a walk-through speaks
for it, and in the rule its specification clause states for a period
carrying no value. Both are written in the identifier table now, and this
counts how many other files repeat them -- how much a reviewer has to edit,
and keep in step, to change one operation's wording by one word.

The number is read at a release and never enforced. It is a size, not a
budget: a docstring that states a rule where a reader needs it is worth the
repetition, and the point of the count is that the repetition is visible and
tested rather than unnoticed and free to drift.

**What counts as a mention.** The sentence itself, and -- because a trace
sentence is a template whose fields are filled from the node, so that no
file outside the table carries it with its braces in -- the longest run of
literal characters between those fields, where that run reaches
twenty-four. Twenty-four because a shorter run is ordinary English ("the
present value of", "significant figures") that would match prose about
something else entirely; the templates whose longest run falls short are
counted on the template alone, which under-reports them, and under-reporting
is the side to err on for a number nobody is held to.

**Hand-written against generated.** The proxy surface and everything under
``gaspatchio/schemas`` are printed from something else, and so is
``contracts.json``; a wording change reaches them by running a generator.
Every other file is one somebody has to edit.

Run from ``bindings/python``::

    .venv/bin/python scripts/wording_places.py

``--all`` lists every identifier rather than only those repeated outside the
table, and a path argument reads a different tree with this tree's wording,
which is how a reading is taken at an older commit for comparison.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
VOCABULARY = ROOT / "bindings/python/gaspatchio/_semantic/vocabulary.py"
SEARCHED = ("bindings/python/gaspatchio", "bindings/python/tests", "spec")
GENERATED = (
    "bindings/python/gaspatchio/column/_generated_proxy.py",
    "bindings/python/gaspatchio/schemas",
    "spec/graph-artifact/conformance/contracts.json",
)
READABLE = frozenset({".py", ".pyi", ".json", ".md", ".txt", ".toml", ".yml", ".yaml"})
SHORTEST_RUN = 24


def _vocabulary() -> ModuleType:
    """Load the identifier table by path, without importing ``gaspatchio``."""
    spec = importlib.util.spec_from_file_location("_wording_table", VOCABULARY)
    if spec is None or spec.loader is None:
        message = f"Cannot load the identifier table from {VOCABULARY}"
        raise RuntimeError(message)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules[spec.name]
    return module


def needles(row: Any) -> tuple[str, ...]:  # noqa: ANN401 - the row is loaded by path
    """Return every piece of wording that would have to move with this row."""
    found: list[str] = []
    for text in (row.voice, row.rule):
        if text is None:
            continue
        found.append(text)
        longest = max((run.strip() for run in re.split(r"\{[^}]*\}", text)), key=len)
        if len(longest) >= SHORTEST_RUN:
            found.append(longest)
    return tuple(dict.fromkeys(found))


def _searchable(tree: Path) -> Iterator[Path]:
    """Yield every text file the count is taken over."""
    for searched in SEARCHED:
        for path in sorted((tree / searched).rglob("*")):
            if (
                path.is_file()
                and path.suffix in READABLE
                and "__pycache__" not in path.parts
            ):
                yield path


def _is_generated(tree: Path, path: Path) -> bool:
    """Return whether a wording reaches this file through a generator."""
    made = [tree / place for place in GENERATED]
    return any(path == place or place in path.parents for place in made)


def places(tree: Path) -> dict[str, tuple[list[Path], list[Path]]]:
    """Return, per identifier, the hand-written and generated files it is in."""
    rows = _vocabulary().VOCABULARY
    wanted = {row.identifier: needles(row) for row in rows}
    found: dict[str, tuple[list[Path], list[Path]]] = {
        identifier: ([], []) for identifier in wanted
    }
    for path in _searchable(tree):
        text = path.read_text("utf-8", errors="ignore")
        for identifier, pieces in wanted.items():
            if any(piece in text for piece in pieces):
                found[identifier][1 if _is_generated(tree, path) else 0].append(path)
    return found


def _report(found: dict[str, tuple[list[Path], list[Path]]], *, every: bool) -> None:
    """Print the per-identifier counts and the totals under them."""
    hand_total = sum(len(hand) for hand, _ in found.values())
    made_total = sum(len(made) for _, made in found.values())
    repeated = {
        identifier: pair
        for identifier, pair in found.items()
        if len(pair[0]) + len(pair[1]) > 1
    }
    print(f"{'identifier':<36}{'hand-written':>14}{'generated':>11}{'files':>7}")
    for identifier, (hand, made) in (found if every else repeated).items():
        print(
            f"{identifier:<36}{len(hand):>14}{len(made):>11}{len(hand) + len(made):>7}"
        )
    carry_a_sentence = sum(1 for pair in found.values() if pair[0] or pair[1])
    print(
        f"\n{len(found)} identifiers, {carry_a_sentence} of them found anywhere, "
        f"{len(repeated)} in more than one file"
    )
    print(
        f"{hand_total} hand-written mentions, {made_total} generated, "
        f"{hand_total + made_total} in all"
    )


def main() -> int:
    """Print how many files each operation's wording stands in."""
    parser = argparse.ArgumentParser(description="Places one wording change moves.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="list every identifier, not only those repeated outside the table",
    )
    parser.add_argument(
        "tree",
        nargs="?",
        type=Path,
        default=ROOT,
        help="the checkout to read; the default is the one this script is in",
    )
    arguments = parser.parse_args()
    _report(places(arguments.tree.resolve()), every=arguments.all)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
