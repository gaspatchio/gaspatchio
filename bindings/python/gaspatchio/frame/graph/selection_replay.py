# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Apply a document's recorded selection to the book, as a replay must.

An engine handed an executable artifact and a book values the policies the
model valued, not every row it was handed (section 7.6 of the specification). So
before anything is projected the book goes through each recorded step, in
order: a filter keeps the rows its core predicate holds for -- a null answer
keeps nothing, as the model's own filter did -- and a semi or anti join keeps
the rows whose key the carried right side matches, or does not.

The predicate is the recorded op-tree lowered by this producer's own core
lowering, over the book's columns under the names the tree reads them by; a
join's right side is the frame the document's assumptions directory carries
under the step's ``right_fingerprint``. A step no replay can apply is refused
by name (:class:`~.selection.SelectionRefusedError`), before a row is read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import polars as pl

from gaspatchio._semantic.join_keys import join_key_sides
from gaspatchio.frame.lowering.polars import lower_polars

from .op_json import op_node_from_json
from .selection import SelectionRefusedError, book_reads, selection_no_replay_can_make
from .validate import payload_frame

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["apply_selection", "selection_columns"]


def _steps(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the document's selection entries, or none."""
    return [step for step in document.get("selection") or () if isinstance(step, dict)]


def _nodes(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the document's nodes by id."""
    return {
        str(node["id"]): node
        for node in document.get("nodes") or ()
        if isinstance(node, dict) and "id" in node
    }


def selection_columns(document: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the book columns the recorded selection reads, sorted, each once.

    Raises:
        SelectionRefusedError: If a step reads a column the book does not hold.

    """
    nodes = _nodes(document)
    return tuple(
        sorted(
            {
                column
                for step in _steps(document)
                for column in book_reads(step, nodes).values()
            }
        )
    )


def apply_selection(document: Mapping[str, Any], book: pl.DataFrame) -> pl.DataFrame:
    """Return the rows of ``book`` the document's recorded selection keeps, in order.

    A document that records no selection returns the book as it was handed.

    Raises:
        SelectionRefusedError: If a step is one no replay can apply, reads a
            column the book does not hold, or is a join whose right side the
            document does not carry.

    """
    steps = _steps(document)
    if not steps:
        return book
    nodes = _nodes(document)
    cannot = selection_no_replay_can_make(steps, list(nodes.values()))
    if cannot is not None:
        raise SelectionRefusedError(str(steps[0].get("id")), cannot)
    for step in steps:
        reads = book_reads(step, nodes)
        missing = sorted(set(reads.values()) - set(book.columns))
        if missing:
            msg = (
                f"{step.get('id')} chooses rows on {', '.join(map(repr, missing))}, "
                "and the book handed over holds no such column. Hand over the "
                "policy data the model was run over, with every column its book "
                "names."
            )
            raise SelectionRefusedError(str(step.get("id")), msg)
        book = (
            _filtered(step, reads, book)
            if step.get("kind") == "filter"
            else _matched(document, step, reads, book)
        )
    return book


def _filtered(
    step: Mapping[str, Any], reads: Mapping[str, str], book: pl.DataFrame
) -> pl.DataFrame:
    """Return the rows one recorded filter keeps."""
    tree = op_node_from_json(step["expr"])
    view = pl.DataFrame(
        [book.get_column(arrived).alias(name) for name, arrived in reads.items()]
    )
    keeps = view.select(lower_polars(tree)).to_series()
    if keeps.dtype != pl.Boolean:
        msg = (
            f"{step.get('id')}'s condition answers {keeps.dtype} rather than true "
            "or false for each policy, so it cannot say which rows were kept. "
            "Export the model again."
        )
        raise SelectionRefusedError(str(step.get("id")), msg)
    return book.filter(keeps.fill_null(value=False))


def _matched(
    document: Mapping[str, Any],
    step: Mapping[str, Any],
    reads: Mapping[str, str],
    book: pl.DataFrame,
) -> pl.DataFrame:
    """Return the rows one recorded semi or anti join keeps."""
    attrs = (step.get("expr") or {}).get("attrs") or {}
    left, right = join_key_sides(attrs.get("on"))
    fingerprint = step.get("right_fingerprint")
    other = _right_side(document, fingerprint)
    if other is None:
        msg = (
            f"{step.get('id')} keeps the rows a second table's key "
            f"{'matches' if step.get('kind') == 'semi' else 'does not match'}, and "
            "this document does not carry that table"
            + (
                " -- it was handed to the join lazily, so no identity was taken"
                if fingerprint is None
                else f" ({fingerprint})"
            )
            + ". Hand the join an eager DataFrame, and export the model again "
            "with its assumption payloads."
        )
        raise SelectionRefusedError(str(step.get("id")), msg)
    on_book = [reads.get(name, name) for name in left]
    return book.join(
        other,
        left_on=on_book,
        right_on=list(right or left),
        how=str(step.get("kind")),  # type: ignore[arg-type]
        maintain_order="left",
    )


def _right_side(
    document: Mapping[str, Any], fingerprint: object
) -> pl.DataFrame | None:
    """Return the right side the document carries under one identity, or None."""
    if not isinstance(fingerprint, str):
        return None
    for entry in document.get("assumptions") or ():
        if (
            isinstance(entry, dict)
            and entry.get("kind") == "join"
            and entry.get("fingerprint") == fingerprint
            and isinstance(entry.get("payload"), dict)
            and "omitted" not in entry["payload"]
        ):
            frame, _ = payload_frame(entry["payload"])
            return frame
    return None
