# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How a selected row of the book is found again in the frame the model ran.

A policy axis is chosen over the book **before** the model runs: ``--policies
:1`` is the first row of the file and ``--policies 7`` the row carrying that
id. The values on the entry are read out of the frame the model **hands
back**, and until this module existed the two were joined by nothing but the
row's position -- the exporter read row *n* of the finished frame because the
selector had counted row *n* of the book.

**That join is an assumption about the model, and models disprove it.** A
model that sorts (``af.sort("amount", descending=True)``), one that filters,
one that joins a table matching a row twice: each leaves the finished frame
holding the same policies in another arrangement, and a position carried
across the gap lands on a policy nobody selected. The document that comes out
states the selected policy's id, the selected row's sentence and another
row's numbers, and it passes deep validation, because every claim in it is
consistent with every other. That is the worst failure this format has --
not a value missing, but a value present, wrong, and under a name a reader
trusts.

So the identity travels. The export stamps every row of the book with its own
position before the model starts, under a name no model would write
(:data:`ROW_STAMP`), and reads the selected rows back out of the finished
frame by that stamp instead of by counting. The stamp is the export's own
scaffolding and never reaches the document: :func:`~.graph_builder.fold`
leaves it out of the graph's inputs and holes, the exporter leaves it out of
the values a node's width is certified from and out of the frame the envelope
is written against, and the command leaves it out of the results file it
writes beside the artifact.

**Three answers, in this order, and two of them are refusals.**

1. The stamp is in the finished frame and exactly one row carries the value
   the selector stamped: that row is the entry, wherever the model put it.
2. The stamp is gone -- the model collected and rebuilt its frame from a
   plain DataFrame, or named the columns it keeps in a ``select`` -- and the
   entry's policy id is carried by exactly one row of the finished frame:
   that row is the entry. An id is weaker evidence than a stamp, because a
   model can move an id too; it is also the evidence the actuary would use
   themselves, and it is the one this exporter has always used for
   ``--policies 7``.
3. Otherwise the export refuses, in words, naming what the model did to the
   book and the ways through.

The third answer is where two principles disagree and the disagreement is
settled. *Meet you where you are* wants a document out of whatever the model
did; *Audit by default* wants no number under a name that is not its own. A
refusal costs the caller a command line; the alternative costs them a
valuation with one policy's numbers filed under another policy's id, found
by whoever is reading it when it matters. So this refuses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final

import polars as pl
from loguru import logger

from .policies import PolicySelectionError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .policies import SelectedPolicy

__all__ = [
    "ROW_STAMP",
    "LocatedRow",
    "locate_the_selection",
    "pin_each_entry",
    "stamp_the_book",
    "without_the_stamp",
]

# The export's own name for a row of the book, and it is a name rather than a
# convention: a model reaching a column called this would have had to type it,
# and the frame refuses an underscore-prefixed attribute at the assignment
# door in the first place. It sits in the same reserved namespace as the
# frame's retained definitions (``__gaspatchio_retained__``) and the
# rollforward's movement readings (``__rf_reading_``), for the same reason --
# the export needs a column of its own and the model must never meet one.
ROW_STAMP: Final[str] = "__gaspatchio_export_row__"

# How many rows a refusal reads back before it stops. Enough to see the shape
# of what the model did -- two rows or two hundred -- without printing a frame
# at somebody.
_SHOWN: Final[int] = 5

# The column a match is counted at. Local to one call, and named in the same
# reserved namespace so that a frame already carrying every other name this
# module knows about still has one free.
_FOUND_AT: Final[str] = "__gaspatchio_located_at__"


@dataclass(frozen=True, slots=True)
class LocatedRow:
    """One axis entry and the row of the finished frame it is.

    Attributes:
        entry: The selection's own entry, with ``why`` amended where the
            model moved the row -- a sentence saying "row 0 of 2" about a
            book whose row 0 finished at position 1 is a sentence a reader
            would check and find wrong.
        pin: The column-and-value pairs that name this row of the finished
            frame, or None where the stamp did not survive the run. Matched
            rather than counted, so it holds through the export's own
            ``--filter`` as well -- including a filter that explodes a
            per-period column into a row per period, where the pin selects
            that policy's rows and the extractor takes the first, exactly as
            a pinned id always has.
        policy_id: The id this entry is pinned by instead, where the stamp is
            gone and the id is unique in the finished frame. None where the
            pin is doing the work.

    """

    entry: SelectedPolicy
    pin: tuple[tuple[str, Any], ...] | None
    policy_id: str | None


def stamp_the_book(book: pl.DataFrame) -> pl.DataFrame:
    """Return ``book`` with the export's own row stamp on every row.

    Applied to the frame the document is an account of and to nothing else:
    the plan's own run writes an audit record of its own, and a column this
    export invented has no business in it.

    Idempotent, so a caller that stamps a frame already stamped gets the
    stamp it already had rather than a second one under a name that can only
    be written once.
    """
    if ROW_STAMP in book.columns:
        return book
    return book.with_row_index(ROW_STAMP)


def without_the_stamp(frame: pl.DataFrame) -> pl.DataFrame:
    """Return ``frame`` with the export's row stamp taken back off.

    Every door out of this export goes through here: the results file the
    command writes beside the artifact, the book the plan's own fold is taken
    over, and the frame the envelope's context is read against. A stamp that
    leaked into any of them would be this export's scaffolding presented as
    the model's data.
    """
    if ROW_STAMP not in frame.columns:
        return frame
    return frame.drop(ROW_STAMP)


def pin_each_entry(
    selection: Sequence[SelectedPolicy],
    rows: pl.DataFrame,
    *,
    axis_columns: Sequence[str] = (),
) -> tuple[SelectedPolicy, ...]:
    """Return the selection with each entry carrying the key its row is.

    Read off ``rows`` -- the frame the run will have -- at the position the
    selector counted, which is the last moment the two are known to be the
    same rows in the same order.

    Args:
        selection: The axis as the selector produced it.
        rows: The frame the model will run over, carrying the stamp.
        axis_columns: The columns an axis the run cross-joined onto the book
            contributes, named by the door that did the cross-join. A book
            row is one row of the book and several of the grid, so on a
            scenario run the stamp alone names three rows and the scenario
            is what tells them apart. Nothing here guesses which columns
            those are: the caller that multiplied the book says so, because
            it is the only thing that knows.

    Returns:
        The same entries, each carrying the pin its row is named by, or the
        selection unchanged where the frame carries no stamp at all.

    """
    if ROW_STAMP not in rows.columns:
        return tuple(selection)
    columns = (ROW_STAMP, *(name for name in axis_columns if name in rows.columns))
    held = {name: rows[name] for name in columns}
    return tuple(
        replace(entry, pin=tuple((name, held[name][entry.row]) for name in columns))
        for entry in selection
    )


def locate_the_selection(
    finished: pl.DataFrame,
    selection: Sequence[SelectedPolicy],
    *,
    id_column: str,
) -> tuple[LocatedRow, ...]:
    """Return, per axis entry, the row of ``finished`` that entry is.

    Args:
        finished: The frame the model handed back, before the export's own
            ``--filter`` narrows it. The model's own doing is measured here
            and the caller's narrowing is not: a row this export was asked
            to cut is a cut the envelope records, and a row the model
            discarded is a row there is nothing to quote for.
        selection: The axis, each entry carrying the pin :func:`pin_each_entry`
            put on it.
        id_column: The column a policy id is matched in, for the fallback.

    Returns:
        One :class:`LocatedRow` per entry, in the axis's own order.

    Raises:
        PolicySelectionError: If a selected row is not in the finished frame,
            is in it more than once, or cannot be told from any other row
            because the model dropped the stamp and the id cannot stand in.

    """
    return tuple(_located(finished, entry, id_column=id_column) for entry in selection)


def _located(
    finished: pl.DataFrame, entry: SelectedPolicy, *, id_column: str
) -> LocatedRow:
    """Return one entry's row, or refuse because there is no honest answer."""
    if entry.pin is None or ROW_STAMP not in finished.columns:
        return _by_the_id(finished, entry, id_column=id_column)
    matched = _rows_matching(finished, entry.pin)
    if len(matched) == 1:
        return LocatedRow(_moved_to(entry, matched[0]), entry.pin, None)
    if not matched:
        raise PolicySelectionError(_the_model_discarded_it(entry))
    raise PolicySelectionError(_the_model_duplicated_it(entry, matched))


def _by_the_id(
    finished: pl.DataFrame, entry: SelectedPolicy, *, id_column: str
) -> LocatedRow:
    """Return the entry pinned by its id, or refuse for the reason it cannot be.

    The fallback for a model that did not hand the stamp back. It is the pin
    ``--policies 7`` has always used, and it is sound on exactly the
    condition that selector is sound on: one row of the finished frame
    carries the id.
    """
    carrying: list[int] = []
    if entry.policy_id is not None and id_column in finished.columns:
        carrying = _rows_carrying(finished, id_column, entry.policy_id)
        if len(carrying) == 1:
            logger.warning(
                f"The model did not hand back the row stamp this export put on "
                f"the book, so {entry.policy_id!r} is pinned by column "
                f"{id_column!r} instead -- the one row of the finished frame "
                "that carries it."
            )
            return LocatedRow(_moved_to(entry, carrying[0]), None, entry.policy_id)
    raise PolicySelectionError(
        _the_model_dropped_the_stamp(entry, id_column=id_column, carrying=carrying)
    )


def _rows_matching(finished: pl.DataFrame, pin: Sequence[tuple[str, Any]]) -> list[int]:
    """Return the positions of ``finished`` the pin names."""
    narrowed = finished.with_row_index(_FOUND_AT)
    for column, value in pin:
        if column not in narrowed.columns:
            return []
        narrowed = narrowed.filter(pl.col(column) == value)
    return [int(found) for found in narrowed[_FOUND_AT]]


def _rows_carrying(finished: pl.DataFrame, id_column: str, wanted: str) -> list[int]:
    """Return the positions of ``finished`` whose id column reads ``wanted``.

    Compared as text, which is how the selector read the book and how the
    envelope writes a policy id whatever the column's own type -- so the
    comparison here and the string the document carries are one string.
    """
    try:
        narrowed = finished.with_row_index(_FOUND_AT).filter(
            pl.col(id_column).cast(pl.String) == wanted
        )
    except Exception as failure:  # noqa: BLE001 -- a cast the engine refuses is a miss
        logger.trace(f"Could not match policy {wanted!r} in {id_column!r}: {failure}")
        return []
    return [int(found) for found in narrowed[_FOUND_AT]]


def _moved_to(entry: SelectedPolicy, found: int) -> SelectedPolicy:
    """Return the entry with ``why`` saying where the model left the row.

    Silent where the model left it where it found it, which is every model
    that does not reorder its frame and therefore every sentence already in
    a committed document. Where it moved, the sentence says so rather than
    leaving a reader to reconcile "row 0 of 2" against a finished frame whose
    row 0 is somebody else.
    """
    if found == entry.row:
        return entry
    return replace(
        entry,
        why=f"{entry.why}; the model left it at row {found:,} of the frame it "
        "handed back",
    )


def _the_model_discarded_it(entry: SelectedPolicy) -> str:
    """Return the refusal for a selected row the finished frame has not got."""
    return (
        f"The row this export selected -- {entry.why!r} -- is not in the frame "
        "the model handed back. Every row of the model points was stamped "
        "before the model ran so that a selected row could be found again "
        "afterwards, and no row of the finished frame carries this one's "
        "stamp: the model discarded it, with a filter, a join that matched "
        "nothing, or an aggregation that folded it away. Every value in an "
        "artifact is a quotation of a row that ran, and there is no row here "
        "to quote -- writing the entry anyway would put whichever row landed "
        "in that position under this policy's name. Select a row the model "
        "keeps, or narrow the run to the rows you mean with --filter, which "
        "is cut before the selection is made and which the envelope records "
        "on every entry of the axis."
    )


def _the_model_duplicated_it(entry: SelectedPolicy, found: Sequence[int]) -> str:
    """Return the refusal for a selected row the model left in more than once."""
    shown = ", ".join(f"{row:,}" for row in found[:_SHOWN])
    more = "" if len(found) <= _SHOWN else ", and more"
    return (
        f"{len(found):,} rows of the frame the model handed back are the row "
        f"this export selected -- {entry.why!r} -- at rows {shown}{more}. The "
        "model duplicated it, so naming that row asks a question with more "
        "than one answer. Taking the first would put one of those rows' "
        "numbers under a name the others answer to as well, which is the "
        "wrong number against the right policy. Narrow the run to the rows "
        "you mean with --filter, which is cut before the selection is made "
        "and which the envelope records on every entry of the axis, or "
        "select a row the model leaves alone."
    )


def _the_model_dropped_the_stamp(
    entry: SelectedPolicy, *, id_column: str, carrying: Sequence[int]
) -> str:
    """Return the refusal for a run that carried no identity through itself."""
    return (
        "Every row of the model points is stamped before the model runs, so "
        "that a selected row can be found again in the frame the model hands "
        "back, and this model did not hand the stamp back -- a Phase 1 that "
        "collects and rebuilds the frame from a plain DataFrame drops it, and "
        "so does naming the columns to keep. Without it the row "
        f"this export selected -- {entry.why!r} -- cannot be told from any "
        "other row of the finished frame, and reading a row position off a "
        "frame the model may have sorted is how one policy's numbers end up "
        "under another policy's name. "
        f"{_why_the_id_cannot_stand_in(entry, id_column, carrying)} "
        "Two ways through: name the policy by id -- "
        f"{_the_id_selector(entry)} -- which is matched against the finished "
        "frame's own id column and does not depend on position; or narrow "
        "the run to the rows you mean with --filter, which is cut before the "
        "selection is made and which the envelope records on every entry of "
        "the axis."
    )


def _why_the_id_cannot_stand_in(
    entry: SelectedPolicy, id_column: str, carrying: Sequence[int]
) -> str:
    """Return the clause saying why the id fallback did not answer either."""
    if entry.policy_id is None:
        return (
            "This entry carries no policy id to fall back on, because the "
            "book names no identifier column."
        )
    if not carrying:
        return (
            f"Policy {entry.policy_id!r} is not in column {id_column!r} of the "
            "finished frame either, so there is nothing to match it against."
        )
    shown = ", ".join(f"{row:,}" for row in carrying[:_SHOWN])
    more = "" if len(carrying) <= _SHOWN else ", and more"
    return (
        f"{len(carrying):,} rows of the finished frame carry policy "
        f"{entry.policy_id!r} in column {id_column!r} -- rows {shown}{more} -- "
        "so matching on it would answer with one of them and call it the one."
    )


def _the_id_selector(entry: SelectedPolicy) -> str:
    """Return the ``--policies`` term that names this entry's policy by id."""
    if entry.policy_id is None:
        return "--policies <id>"
    return f"--policies 'id:{entry.policy_id}'"
