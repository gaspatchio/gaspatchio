# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Which book columns a recorded selection step reads, and what no replay can make.

A replay of an artifact applies the model's recorded selection to the book
before it projects (section 7.6): ``gspio run-artifact`` on any engine, and the
frame's own engine door, value exactly the policies the model valued. That is
only possible where a step decides on what the book holds. This module reads a
step's ``reads`` back through the document's nodes to the book columns they
stand for -- an arriving column, or one renamed on the way in -- and says by
name what a replay cannot do: a predicate outside the core vocabulary, and a
predicate over a column the model calculates. The exporter asks it before it
writes an executable document, and the replay asks it again before it reads a
row, so the two refuse the same steps in the same words.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from .graph_models import NodeType, Provenance

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "SelectionRefusedError",
    "book_reads",
    "selection_no_replay_can_make",
]

# The one tier a replay applies a predicate under.
_CORE: Final[str] = "core"


class SelectionRefusedError(ValueError):
    """A recorded selection step a replay cannot apply to the book, named.

    ``step`` is the step's id; the message names its line where the document
    states one, says what stands in the way and ends with the move.
    """

    def __init__(self, step: str, message: str) -> None:
        """Hold the step's id beside the sentence."""
        super().__init__(message)
        self.step = step


def _named(step: Mapping[str, Any]) -> str:
    """Return how a refusal names one step: its id, and its line where known."""
    where = step.get("source_location")
    ident = str(step.get("id") or "a selection step")
    return f"{ident} ({where})" if isinstance(where, str) else ident


def book_reads(
    step: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]
) -> dict[str, str]:
    """Return, for each column the step's tree names, the book column it stands for.

    A read binds to the definition its column held when the step was taken.
    An arriving column is the book's own; a column renamed on the way in is
    the arriving column under another name, followed back through the rename
    record. Anything else -- a calculated column, a column handed over at a
    line, a hole -- is not on the book at all, and a step reading one cannot
    be applied to the book before the projection.

    Raises:
        SelectionRefusedError: Naming the step and the column it reads.

    """
    mapping: dict[str, str] = {}
    for read in step.get("reads") or ():
        node = nodes.get(str(read))
        if node is None:
            msg = (
                f"{_named(step)} reads {read!r}, which no node of this document "
                "is. Export the model again."
            )
            raise SelectionRefusedError(str(step.get("id")), msg)
        name = node.get("column")
        arrived = _arriving_column(node, nodes)
        if not isinstance(name, str) or arrived is None:
            msg = (
                f"{_named(step)} chooses rows on {_read_named(step, str(read))}, "
                "which the model calculates rather than reads from the book. "
                "A replay applies "
                "the recorded selection to the book before it projects, so the "
                "condition must read columns the book holds. Filter on the "
                "model-point columns the value is calculated from, or keep the "
                "rows and mask the cash flows with when(...)."
            )
            raise SelectionRefusedError(str(step.get("id")), msg)
        mapping[name] = arrived
    return mapping


def _read_named(step: Mapping[str, Any], read: str) -> str:
    """Return how a refusal names one read, a rollforward by the states it reads.

    A compiled rollforward's node id is its fingerprint, which is not a word
    the author wrote. The step's tree names the state it reads from that run
    (a ``rollforward.state`` call whose fingerprint the id abbreviates), so
    the refusal leads with ``'av'`` and keeps the id beside it.
    """
    kind, _, short = read.partition(":")
    if kind != "rollforward" or not short:
        return repr(read)
    states: list[str] = []
    pending: list[object] = [step.get("expr")]
    while pending:
        part = pending.pop()
        if isinstance(part, list):
            pending.extend(reversed(part))
            continue
        if not isinstance(part, dict):
            continue
        attrs = part.get("attrs")
        if part.get("name") == "rollforward.state" and isinstance(attrs, dict):
            fingerprint = str(attrs.get("fingerprint", "")).rpartition(":")[2]
            state = attrs.get("state")
            if (
                fingerprint.startswith(short)
                and isinstance(state, str)
                and state not in states
            ):
                states.append(state)
        pending.extend(reversed([v for k, v in part.items() if k != "attrs"]))
    if not states:
        return repr(read)
    quoted = [repr(state) for state in states]
    listed = (
        quoted[0] if len(quoted) == 1 else ", ".join(quoted[:-1]) + f" and {quoted[-1]}"
    )
    noun = "state" if len(states) == 1 else "states"
    return f"the rollforward {noun} {listed} ({read})"


def _arriving_column(
    node: Mapping[str, Any], nodes: Mapping[str, Mapping[str, Any]]
) -> str | None:
    """Return the book column a node stands for, or None where it stands for none."""
    seen: set[str] = set()
    while True:
        kind, provenance = node.get("kind"), node.get("provenance")
        if kind == NodeType.INPUT.value and provenance == Provenance.MODEL_POINTS.value:
            column = node.get("column")
            return column if isinstance(column, str) else None
        reads: Sequence[object] = node.get("reads") or ()
        if (
            kind != NodeType.COMPUTED.value
            or provenance != Provenance.RENAME.value
            or len(reads) != 1
            or str(reads[0]) in seen
        ):
            return None
        seen.add(str(reads[0]))
        upstream = nodes.get(str(reads[0]))
        if upstream is None:
            return None
        node = upstream


def selection_no_replay_can_make(
    steps: Sequence[Mapping[str, Any]], nodes: Sequence[Mapping[str, Any]]
) -> str | None:
    """Return why a replay could not apply these steps to the book, or None.

    The first step that stands in the way decides: a predicate whose tree is
    not core (an engine's own expression text, or an identifier the
    vocabulary does not list), or one that reads a column the book does not
    hold (:func:`book_reads`).
    """
    by_id = {str(node["id"]): node for node in nodes if "id" in node}
    for step in steps:
        tier = step.get("tier")
        if tier != _CORE:
            return (
                f"{_named(step)} chooses rows with a condition outside the core "
                f"vocabulary (tier {tier!r}): a replay of the executable "
                "artifact applies the recorded selection itself, and no engine "
                "can apply a condition the format does not define. Write the "
                "condition from the frame's columns -- af.filter(af.status == "
                '"IF") -- or with comparisons, &, |, ~, is_in and the null tests '
                "in Polars, or select the model points before the run."
            )
        try:
            book_reads(step, by_id)
        except SelectionRefusedError as refused:
            return str(refused)
    return None
