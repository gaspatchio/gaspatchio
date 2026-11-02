# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Which model points an artifact carries values for, and why each one is there.

An artifact used to carry one policy. It still carries one by default -- the
first row of the book, which is where the data happened to put it -- and it
may now carry several, on an axis the envelope declares. This module is what
turns what the caller typed into that axis.

**Nothing here is automatic.** No ranking column is inferred, no cohorts are
built, no anomaly rule fires. A selection that picks badly is worse than a
visibly arbitrary one, because a clever rule looks authoritative and an
arbitrary one does not: a reader who sees "row 0 of 1,000" knows exactly how
much to read into it. So the forms below are the whole vocabulary, each one
says plainly what it did, and every entry carries the sentence saying how it
came to be in the file.

Five forms, read in this order, and the first that matches wins:

``:30`` ``3:40`` ``::10`` ``-5:``
    **Row positions**, and only where the whole term matches the slice
    grammar -- optional sign, digits, a colon, and at most one more colon.
    Python's own semantics, exactly: 0-based, half-open, negative counting
    from the end, a step allowed. ``ids[3:40]`` in an interpreter and
    ``--policies 3:40`` here select the same policies, and that is a
    property a test holds rather than a claim this docstring makes.

``all``
    Every policy in the book, subject to the size guard the caller applies
    to the finished document.

``spread:5@sum_assured``
    Order the book by one column and walk it at even spacing, ends
    included. Any term beginning ``spread:`` is read this way. The column
    is read from the model points **as they arrive**: a selection is made
    before the model runs, so it cannot order the book by a number the
    model has not computed yet.

``id:POL-000343``
    **One policy id, taken verbatim**, whatever it looks like. This is the
    escape, and it is what makes the rule above safe: a book whose ids are
    `3:40` or `all` or `spread:5@x`, or whose ids contain a comma, has
    policies that no other form can reach.

``1,7,42`` ``POL-000343,GB-2019-88231``
    **Everything else is an id**, or a comma-separated run of them, taken
    in the order given.

**Position and identity are confusable, which is why every entry records
both.** On the books this framework ships they are one apart -- an
``Int64`` ``point_id`` starting at 1, sorted, with no gaps -- and on a real
book they are nothing of the kind: ids are strings, out of order, with gaps,
and sometimes repeated. Neither shape is safe to infer from, so the grammar
decides by the term's own form rather than by what the book happens to hold,
and ``why`` records the row and the id together on every entry.

**An id is matched as text.** The envelope writes ``policy_id`` as a string
whatever the column's own type, so the comparison here is against each row's
id stringified -- ``--policies 7`` reaches an ``Int64`` 7 and writes ``"7"``,
and the extractor reading the frame afterwards puts the id back into the
column's own type.

**A repeated id is refused rather than resolved.** Three rows carrying `7`
make ``--policies 7`` a question with three answers, and taking the first
would put one row's numbers under a name two other rows also answer to.

**The cut is made before the selection, so the refusal's advice is a way
through.** ``--filter`` narrows the rows an export's values are read off, and
every form above is read among the rows it keeps: ``--policies 7 --filter
'scenario_id == "BASE"'`` reaches the one BASE row carrying 7, where reading
the id over the whole cross-joined frame first refused it as carried by three
and then recommended that very filter. Where the cut names a column the book
does not carry yet -- ``col('year') == 5``, a column the model computes --
nothing can be cut before the run and the selection is made over every row,
which is what it always was.

**A selected row is found again after the run, not counted to.** What each
entry records is a row of the book; what its values are read off is a row of
the frame the model handed back, and the two are joined by a stamp this export
puts on the book rather than by the position matching.
:mod:`~gaspatchio.frame.graph.row_identity` is where that join lives and where
it refuses when the model has made it impossible.

**A selection chooses which policies are sampled and never which are
computed, and nothing here touches the frame the model runs over.** The
temptation is obvious -- two policies asked for, two rows run, and the
export is a hundred times faster on a real book -- and it is wrong for a
reason that has nothing to do with speed. A model with a cross-row step
answers differently when the book behind it is smaller: a scenario axis in
this framework is a cross-join on the model-point frame, and a fold over
one reads across rows. Narrow the run and policy 291's number in a
two-policy export stops being policy 291's number in the run the actuary
did -- and this document's whole claim is that every value in it is a
quotation of a real run. A value that is only what it is because the export
narrowed the book is a quotation of nothing.

So a portfolio total stays a portfolio total, and a caller who genuinely
wants a narrower run has the option that means that: the export's own
``filter``, which §7 defines as the cut the sampled rows were narrowed by
and which the envelope records on every entry of the axis. Selection and
filtering are two different things and the document says them separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    import polars as pl

__all__ = [
    "DEFAULT_SELECTION",
    "PolicySelectionError",
    "SelectedPolicy",
    "refuse_over_the_ceiling",
    "select_policies",
]

# What the axis holds when nobody said otherwise: the first row of the book.
# Today's document, said in the grammar the other forms are said in, rather
# than a second spelling of one policy.
DEFAULT_SELECTION: Final[str] = ":1"

# How many of the things a refusal reads back before it stops. Enough to see
# the shape of an id or the name of a column -- a dropped leading zero, a
# number where a string was expected -- without printing a model-point file
# at somebody.
_SHOWN: Final[int] = 5

# What a row-position term looks like, whole: an optional sign, digits, a
# colon, and at most one more of each. **Strict, and that is the point.** A
# policy id is a string the book's author chose and it may look like
# anything -- `POL-000343`, `GB-2019-88231`, and on an unlucky book `3:40` --
# so the grammar decides what a term is by the term's own shape, never by
# whether the book happens to carry a policy of that name. Anything this does
# not match is an id, and `id:` reaches the ids this would otherwise swallow.
_SLICE: Final[re.Pattern[str]] = re.compile(r"^-?\d*:-?\d*(?::-?\d*)?$")

# The prefix that makes a colon mean "spread" rather than "slice". Read
# before the slice grammar, because ``spread:5@column`` carries a colon of
# its own and would otherwise be read as a slice of nothing.
_SPREAD: Final[str] = "spread:"

# The escape, and the reason the rules above are safe to state as shapes.
# Everything after it is one policy id, verbatim: `id:3:40` names the policy
# called `3:40`, `id:all` the policy called `all`, and `id:a,b` a single id
# with a comma in it. Without it a book whose ids collide with the grammar
# has policies no selection can name at all.
_LITERAL: Final[str] = "id:"

# The word for every policy in the book.
_ALL: Final[str] = "all"


class PolicySelectionError(ValueError):
    """A selection that names no honest set of model points."""


@dataclass(frozen=True, slots=True)
class SelectedPolicy:
    """One model point on the artifact's policy axis.

    Attributes:
        row: The 0-based position this policy sits at in the book as it
            arrived. Recorded even where the selector named an id, because
            position and identity are confusable -- one apart on the books
            this framework ships, unrelated on a real one -- and a reader
            should never have to work out which was meant.
        policy_id: The id at that row, as a string, or None where the book
            names no policy column at all -- a selection by row position
            works on such a book and an entry for it has no id to give.
        why: The plain sentence saying how this policy came to be in the
            file. It travels into the artifact unchanged.
        by_identity: Whether this entry was reached by naming an id or by
            counting rows. **It records how the entry was found and no
            longer decides how it is read back**: since the export stamps
            every row of the book before the model runs
            (:mod:`~gaspatchio.frame.graph.row_identity`), both kinds of
            entry are located in the finished frame by that stamp and a row
            position never crosses the run. What it still decides is the
            sentence -- "named on the command line" and "selected by ':1'"
            are two different accounts of how a policy came to be here.
        pin: The column-and-value pairs naming this entry's row of the frame
            the model runs over, or None where that frame carries no stamp
            for the selector to read off. Put on by
            :func:`~gaspatchio.frame.graph.row_identity.pin_each_entry` at
            the last moment the selected rows and the run's rows are known
            to be the same rows in the same order, and read back after the
            run so that an entry's samples are the row it named rather than
            whatever the model left in that position.
        cut: The cut this entry's row sits in, written the way section 7
            writes one, or None where the rows were not cut. It is how a
            scenario export says which scenario a row is -- a cross-joined
            frame names every policy once per scenario, and an entry that
            did not say which would leave three identical-looking rows on
            the axis under one id. Set by the producer that knows the
            shape of the frame, never by the selector, which reads rows
            and not what made them.

    """

    row: int
    policy_id: str | None
    why: str
    by_identity: bool = False
    cut: str | None = None
    pin: tuple[tuple[str, Any], ...] | None = None


def select_policies(  # noqa: PLR0913 — one parameter per thing a sentence or a refusal has to be able to name
    specs: Sequence[str],
    *,
    book: pl.DataFrame,
    id_column: str | None,
    source: str,
    kept: Sequence[int] | None = None,
    cut: str | None = None,
) -> tuple[SelectedPolicy, ...]:
    """Return the policy axis ``specs`` names, in the order it names it.

    Every spec is read on its own and the results are concatenated, then
    de-duplicated **keeping the first occurrence**: a policy named twice is
    one entry, at the position it was first asked for, because an axis is a
    list of model points rather than a list of requests.

    **The cut comes first and the selection is made inside it.** ``--filter``
    is the member that says which rows are behind a value, and a selection
    resolved over rows the filter has already thrown away is a selection
    answering a question nobody asked: ``--policies 7 --filter
    'scenario_id == "BASE"'`` used to refuse policy 7 as carried by three
    rows and then recommend the very filter that leaves one of them. So the
    filter is applied to the frame the run will have, and every form here --
    a slice, ``all``, a ``spread``, an id -- is read among the rows it keeps.

    Args:
        specs: The ``--policies`` values, in the order the command line gave
            them. Empty selects :data:`DEFAULT_SELECTION`, which is the first
            row of the book.
        book: The model points as they arrive, before the model runs. Both
            the row positions and the ``spread`` orderings are taken over
            this frame and over no other: a selection is made before there is
            anything computed to select on.
        id_column: The column holding the policy identifier, or None where
            the book names none. Selecting by id on a book with no id column
            is refused rather than guessed at.
        source: The model-point file's own name, for the sentences. It is
            what a reader of ``why`` is told the row was counted in.
        kept: The rows ``--filter`` keeps, as positions in ``book`` and in
            its order, or None where nothing was cut or where the cut names
            a column the book does not carry yet. A selection is made among
            these and the positions recorded stay the book's own, so
            ``why`` names a row a reader can find in the file.
        cut: The filter that kept them, for the sentences. It is what a
            reader of ``why`` is told the selection was made inside.

    Returns:
        One entry per policy, in selection order, each carrying its row, its
        id and the sentence saying how it got there. Never empty: a selection
        that lands on nothing is refused rather than returned. **Nothing
        here narrows the run** -- the rows are named, not taken, because the
        model runs the whole book whatever is selected.

    Raises:
        PolicySelectionError: If a spec is not one of the forms, if an id is
            not among the rows the cut keeps or is carried by more than one
            of them, if a slice selects nothing, if the cut itself keeps
            nothing, or if a ``spread`` column is missing, per-period, or
            too coarse to separate the number of points asked for.

    """
    total = book.height
    identifiers = _identifiers(book, id_column, total)
    positions = tuple(range(total)) if kept is None else tuple(kept)
    if not positions:
        raise PolicySelectionError(_a_cut_with_nothing_in_it(cut, source, total))
    among = _among(cut, positions)
    chosen: dict[int, SelectedPolicy] = {}
    for spec in specs or (DEFAULT_SELECTION,):
        for entry in _one_spec(
            spec.strip(),
            book=book,
            identifiers=identifiers,
            id_column=id_column,
            source=source,
            positions=positions,
            among=among,
        ):
            chosen.setdefault(entry.row, entry)
    return tuple(chosen.values())


def _among(cut: str | None, positions: Sequence[int]) -> str:
    """Return the clause a sentence adds where a cut was made before it.

    Empty where nothing was cut, which is every sentence in every document
    written before the cut was read first -- so an unfiltered export's
    ``why`` is the sentence it always was, to the character.
    """
    if cut is None:
        return ""
    return f", among the {len(positions):,} rows {cut!r} keeps"


def _identifiers(
    book: pl.DataFrame, id_column: str | None, total: int
) -> list[str | None]:
    """Return each row's policy id as a string, or None where the book has none."""
    if id_column is None or id_column not in book.columns:
        return [None] * total
    return [None if value is None else str(value) for value in book[id_column]]


def _one_spec(  # noqa: PLR0913 — one parameter per thing a refusal has to be able to name; folding them into an object would rename the list rather than shorten it
    spec: str,
    *,
    book: pl.DataFrame,
    identifiers: Sequence[str | None],
    id_column: str | None,
    source: str,
    positions: Sequence[int],
    among: str,
) -> list[SelectedPolicy]:
    """Return the entries one spec names, refusing where it names none honestly.

    Read by shape, in one order, first match winning: a whole-term slice,
    the word for the book, a term beginning ``spread:``, the ``id:`` escape,
    and otherwise a run of ids. Deciding by shape rather than by what the
    book holds is what keeps the answer the same on two books -- a rule that
    read ``3:40`` as a slice on one book and an id on another would make the
    same command line mean two things.

    Every form is read over ``positions`` -- the rows the cut kept, or every
    row where nothing was cut -- and records the book's own row number, so
    the grammar means one thing and the sentence names a row a reader can
    find in the file.
    """
    total = len(identifiers)
    if _SLICE.match(spec):
        return _slice(
            spec,
            identifiers=identifiers,
            source=source,
            positions=positions,
            among=among,
        )
    if spec == _ALL:
        return [
            _entry(
                row,
                identifiers,
                f"row {row:,} of {total:,} in {source}, one of every policy "
                f"in the book{among}",
            )
            for row in positions
        ]
    if spec.startswith(_SPREAD):
        return _spread(
            spec,
            book=book,
            identifiers=identifiers,
            source=source,
            positions=positions,
            among=among,
        )
    wanted = (
        [spec[len(_LITERAL) :]]
        if spec.startswith(_LITERAL)
        else [part.strip() for part in spec.split(",") if part.strip()]
    )
    return _by_identity(
        spec,
        wanted,
        book=book,
        identifiers=identifiers,
        id_column=id_column,
        source=source,
        positions=positions,
        among=among,
    )


def _entry(
    row: int,
    identifiers: Sequence[str | None],
    why: str,
    *,
    by_identity: bool = False,
) -> SelectedPolicy:
    """Return one axis entry, reading the id off the row it sits at."""
    return SelectedPolicy(
        row=row,
        policy_id=identifiers[row],
        why=why,
        by_identity=by_identity,
    )


def _by_identity(  # noqa: PLR0913 — one parameter per thing a refusal has to be able to name
    spec: str,
    wanted: Sequence[str],
    *,
    book: pl.DataFrame,
    identifiers: Sequence[str | None],
    id_column: str | None,
    source: str,
    positions: Sequence[int],
    among: str,
) -> list[SelectedPolicy]:
    """Return the entries a run of named policy ids reaches.

    What is matched is the id the book carries and not the position it sits
    at. Matched as text, because an id arrives as text -- from a command
    line, from a URL -- and because the envelope writes ``policy_id`` as a
    string whatever the column's own type is; the comparison and the record
    are then the same string.

    **Matched among the rows the cut keeps.** A cross-joined scenario frame
    carries policy 7 once per scenario, and ``--filter 'scenario_id ==
    "BASE"'`` leaves one of them: reading the id over every row and then
    recommending that filter was advice the command could not take.

    **An id carried by more than one of those rows is refused.** It is a
    question with several answers, and answering it with the first row would
    put that row's numbers under a name two other rows also answer to -- the
    wrong number against the right policy, which is worse than no number. A
    caller who meant one of those rows names a column that separates them,
    which the refusal works out and prints, or counts rows.
    """
    total = len(identifiers)
    if not wanted:
        raise PolicySelectionError(_named_nothing(spec, source=source, total=total))
    if id_column is None:
        raise PolicySelectionError(_no_identifier_column(wanted, source=source))
    rows: dict[str, list[int]] = {}
    for row in positions:
        identifier = identifiers[row]
        if identifier is not None:
            rows.setdefault(identifier, []).append(row)
    entries: list[SelectedPolicy] = []
    for identifier in wanted:
        found = rows.get(identifier)
        if not found:
            raise PolicySelectionError(
                _no_such_policy(
                    identifier,
                    id_column=id_column,
                    identifiers=identifiers,
                    source=source,
                    total=len(positions),
                )
            )
        if len(found) > 1:
            raise PolicySelectionError(
                _an_id_more_than_one_row_answers_to(
                    identifier,
                    book=book,
                    id_column=id_column,
                    rows=found,
                    source=source,
                )
            )
        row = found[0]
        entries.append(
            _entry(
                row,
                identifiers,
                f"named on the command line, row {row:,} of {total:,} in "
                f"{source}{among}",
                by_identity=True,
            )
        )
    return entries


def _slice(
    spec: str,
    *,
    identifiers: Sequence[str | None],
    source: str,
    positions: Sequence[int],
    among: str,
) -> list[SelectedPolicy]:
    """Return the entries a Python slice of the book names.

    Python's own semantics, and deliberately nothing beside them: a reader
    who knows what ``ids[-5:]`` does in an interpreter knows what ``-5:``
    does here, and a grammar that was nearly Python would be the worse of
    the two options. What it is a slice *of* is the rows the cut kept, which
    is the whole book wherever nothing was cut.
    """
    total = len(identifiers)
    parts = spec.split(":")
    bounds: list[int | None] = [None if part == "" else int(part) for part in parts]
    if len(bounds) == 2:  # noqa: PLR2004 — a two-part slice states no step
        bounds.append(None)
    if bounds[2] == 0:
        raise PolicySelectionError(_a_step_of_nothing(spec))
    rows = list(positions)[slice(*bounds)]
    if not rows:
        raise PolicySelectionError(
            _an_empty_slice(spec, source=source, total=len(positions))
        )
    return [
        _entry(
            row,
            identifiers,
            f"row {row:,} of {total:,} in {source}, selected by {spec!r}{among}",
        )
        for row in rows
    ]


def _an_id_more_than_one_row_answers_to(
    identifier: str,
    *,
    book: pl.DataFrame,
    id_column: str,
    rows: Sequence[int],
    source: str,
) -> str:
    """Return the refusal for an id more than one of the kept rows carries.

    **Every way through it names is a way through that works.** The one it
    used to lead with did not: ``--filter`` was recommended by a refusal
    raised before the filter was applied, so taking the advice produced the
    same refusal. The filter is now cut first, and this sentence goes
    further -- it looks for a column whose values tell the offending rows
    apart and prints the exact expression that leaves one of them.
    """
    shown = ", ".join(f"{row:,}" for row in rows[:_SHOWN])
    more = "" if len(rows) <= _SHOWN else ", and more"
    separator = _a_column_that_separates(book, id_column, rows)
    ways = (
        "Two ways through, and a scenario run wants the first: "
        if separator
        else "Two ways through: "
    )
    by_filter = (
        f"narrow to the rows you mean with --filter {separator!r}, which is "
        "cut before the selection is made and which the envelope records on "
        "every entry of the axis; or "
        if separator
        else "name the column that separates them with --policy-id-column; or "
    )
    return (
        f"{len(rows):,} rows of {source} carry policy {identifier!r} in "
        f"column {id_column!r} -- rows {shown}{more} -- so naming that id "
        "asks a question with more than one answer. Taking the first would "
        "put one row's numbers under a name the others answer to as well, "
        f"which is the wrong number against the right policy. {ways}"
        f"{by_filter}"
        f"count rows with a ':N' slice -- '{rows[0]}:{rows[0] + 1}' is the "
        "first of them."
    )


# The framework's own column namespace, which the export's row stamp sits in.
_RESERVED_NAMESPACE: Final[str] = "__gaspatchio_"


def _a_column_that_separates(
    book: pl.DataFrame, id_column: str, rows: Sequence[int]
) -> str | None:
    """Return a filter expression leaving one of ``rows``, or None if none does.

    Read off the frame the selection is made over, because a way through has
    to be checkable before it is offered: the column named here holds a
    different value on every one of the rows sharing the id, so the
    expression printed leaves exactly one and the caller's next command
    succeeds. A scenario run's ``scenario_id`` is the case this was written
    for and nothing here knows that -- it is the first column that separates
    the rows, whatever the model points call it.

    None where no single column does, and the sentence then offers only the
    ways through that remain. Naming a filter that does not resolve the
    ambiguity is the defect this whole function exists to close.
    """
    import polars as pl  # noqa: PLC0415 — the frame types are only needed here

    for column in book.columns:
        # The export's own row stamp (``row_identity.ROW_STAMP``) separates
        # every row by construction, and like every name in the framework's
        # reserved namespace it is scaffolding no model or command line may
        # name: a filter on it would put the stamp on the wire. It is never
        # the way through.
        if (
            column == id_column
            or column.startswith(_RESERVED_NAMESPACE)
            or isinstance(book.schema[column], pl.List)
        ):
            continue
        values = [book[column][row] for row in rows]
        if any(value is None for value in values) or len(set(values)) != len(values):
            continue
        return f"col({column!r}) == {values[0]!r}"
    return None


def _spread(  # noqa: PLR0913 — one parameter per thing a refusal or a sentence has to be able to name
    spec: str,
    *,
    book: pl.DataFrame,
    identifiers: Sequence[str | None],
    source: str,
    positions: Sequence[int],
    among: str,
) -> list[SelectedPolicy]:
    """Return the entries an even walk of the book, ordered by one column, names.

    The book is sorted by the named column, ties broken by the row position
    so the answer does not depend on the order the rows happened to arrive
    in, and then walked at even spacing with both ends included. What it is
    not is a sample: it is an ordering and a ruler, which is why the column
    is named by the caller and never inferred.

    Ordered over the rows the cut kept, and the column's coarseness measured
    over them too: a spread of five taken inside a filter that keeps three
    rows is the same over-fine walk the refusal below already names, and
    measuring it over the whole book would let it through.
    """
    import polars as pl  # noqa: PLC0415 — the frame types are only needed here

    total = len(positions)
    count, _, column = spec[len(_SPREAD) :].partition("@")
    if not column:
        raise PolicySelectionError(_named_nothing(spec, source=source, total=total))
    try:
        points = int(count)
    except ValueError:
        raise PolicySelectionError(
            _named_nothing(spec, source=source, total=total)
        ) from None
    if points < 1:
        raise PolicySelectionError(_a_spread_of_nothing(spec, points))
    if column not in book.columns:
        raise PolicySelectionError(_no_such_column(column, book=book, source=source))
    if isinstance(book.schema[column], pl.List):
        raise PolicySelectionError(_a_per_period_column(column, source=source))
    inside = set(positions)
    distinct = (
        book[column].n_unique()
        if total == book.height
        else book[column].gather(list(positions)).n_unique()
    )
    if distinct < points:
        raise PolicySelectionError(
            _too_coarse(
                column, points=points, distinct=distinct, source=source, total=total
            )
        )
    walk = (
        book.with_row_index("__row__")
        .sort(column, "__row__", nulls_last=True)["__row__"]
        .to_list()
    )
    ordered = [row for row in walk if row in inside]
    walked = _evenly_spaced(len(ordered), points)
    return [
        _entry(
            int(ordered[position]),
            identifiers,
            f"row {int(ordered[position]):,} of {len(identifiers):,} in "
            f"{source}, {place + 1} of {points} spread over {column!r}{among}",
        )
        for place, position in enumerate(walked)
    ]


def _evenly_spaced(length: int, points: int) -> list[int]:
    """Return ``points`` positions spread across ``length``, both ends included.

    One point is the first, which is the only end a single point can be at.
    Two are the two ends, and the rest divide the run between them; the
    rounding is the ordinary one, so the spacing is even to within a row.
    """
    if points == 1:
        return [0]
    return [round(place * (length - 1) / (points - 1)) for place in range(points)]


def _named_nothing(spec: str, *, source: str, total: int) -> str:
    """Return the refusal for a spec that is none of the four forms."""
    return (
        f"{spec!r} is not a way of naming model points. A policy axis is "
        "written in one of these forms: ':30', '3:40', '::10' and '-5:' name "
        "row positions, with Python's own slice semantics; 'all' is every "
        f"one of the {total:,} policies in {source}; 'spread:5@sum_assured' "
        "orders the book by one column and walks it at even spacing; "
        "'id:POL-000343' names one policy verbatim, whatever it looks like; "
        "and anything else is an id, or a comma-separated run of them. A "
        "term is read by its own shape rather than by what the book holds, "
        "so 'id:' is how a policy whose id looks like one of the other "
        "forms is reached."
    )


def _a_step_of_nothing(spec: str) -> str:
    """Return the refusal for a slice whose step is zero."""
    return (
        f"The slice {spec!r} steps by zero, which walks the book without "
        "ever reaching the next policy. Python refuses the same slice for "
        "the same reason. Step by 1 to take every policy in the range, or "
        "by 10 to take every tenth."
    )


def _a_cut_with_nothing_in_it(cut: str | None, source: str, total: int) -> str:
    """Return the refusal for a ``--filter`` that keeps no row to select among."""
    return (
        f"--filter {cut!r} keeps none of the {total:,} rows of {source}, and "
        "the selection is made among the rows it keeps -- so there is no "
        "policy for the artifact to carry values for and no axis to put one "
        "on. Widen the filter, or drop it and select with --policies, which "
        "names rows rather than cutting them."
    )


def _an_empty_slice(spec: str, *, source: str, total: int) -> str:
    """Return the refusal for a slice that lands on no row of the book."""
    return (
        f"The slice {spec!r} selects no rows of the {total:,} policies in "
        f"{source}, so there is no policy for the artifact to carry values "
        "for. An axis with nothing on it is a document that says nothing "
        "about any model point. Widen the slice -- ':1' is the first policy, "
        "':30' the first thirty, '-5:' the last five."
    )


def _no_identifier_column(wanted: Sequence[str], *, source: str) -> str:
    """Return the refusal for ids asked of a book that names no policy column."""
    return (
        f"{', '.join(repr(one) for one in wanted)} was asked for by id, and "
        f"{source} carries no policy identifier column to match it against. "
        "Commas mean identity, and identity needs a column that holds one. "
        "Name the column with --policy-id-column, or select by row position "
        "instead -- ':1' is the first policy and '-5:' the last five."
    )


def _no_such_policy(
    identifier: str,
    *,
    id_column: str,
    identifiers: Sequence[str | None],
    source: str,
    total: int,
) -> str:
    """Return the refusal for an id the book does not carry."""
    present = [one for one in identifiers if one is not None][:_SHOWN]
    return (
        f"Policy {identifier!r} is not in column {id_column!r}, and "
        f"{source} holds {total:,} policies. A policy axis names the model "
        "points the artifact carries values for, so an id matching none of "
        "them would put an entry on that axis with no policy behind it. Ids "
        f"present include: {present}. Ask for one the book carries, or "
        "select by row position instead -- ':1' is the first policy, '-5:' "
        "the last five."
    )


def _no_such_column(column: str, *, book: pl.DataFrame, source: str) -> str:
    """Return the refusal for a spread over a column the book does not hold."""
    return (
        f"No column named {column!r} arrives in {source}, so there is "
        "nothing to order the book by. 'spread' walks the book in the order "
        "one column puts it in, and that column is read from the model "
        "points as they arrive -- a selection is made before the model runs, "
        "so it cannot order the book by a number the model has not computed "
        f"yet. Columns that do arrive include: {book.columns[:_SHOWN]}."
    )


def _a_per_period_column(column: str, *, source: str) -> str:
    """Return the refusal for a spread over a column holding a run of values."""
    return (
        f"Column {column!r} in {source} holds one value per projection "
        "period, and a book cannot be ordered by a run of values -- at which "
        "period would the order be taken? 'spread' needs one value per "
        "policy to sort by. Name a column holding one value per policy, or "
        "select by row position instead."
    )


def _too_coarse(
    column: str, *, points: int, distinct: int, source: str, total: int
) -> str:
    """Return the refusal for a spread finer than the column can separate."""
    return (
        f"Column {column!r} holds {distinct:,} distinct "
        f"{'value' if distinct == 1 else 'values'} across the {total:,} "
        f"policies in {source}, and {points} evenly spaced points were asked "
        "for. A spread cannot separate the book more finely than the column "
        "it is ordered by does: past that, the walk returns the same policy "
        "twice and calls the result a spread. Ask for at most "
        f"{distinct:,}, or order by a column that separates the book more "
        "finely."
    )


def _a_spread_of_nothing(spec: str, points: int) -> str:
    """Return the refusal for a spread asking for no points at all."""
    return (
        f"{spec!r} asks for {points} points, and a spread of fewer than one "
        "policy is an axis with nothing on it. Ask for at least one -- "
        "'spread:1@column' is the policy that column orders first."
    )


def _too_large(measured: int, limit: int) -> str:
    """Return the refusal for a selection whose document is over the ceiling."""
    return (
        f"This selection assembles a {measured:,}-byte document and "
        f"--max-size is {limit:,} bytes. Per-policy bytes vary by model -- a "
        "projection over 241 periods costs several times what one over 83 "
        "does -- so the guard is over the finished document rather than over "
        "a count of policies. Select fewer policies, or raise --max-size if "
        "whoever opens this file can hold it."
    )


def refuse_over_the_ceiling(measured: int, limit: int) -> None:
    """Refuse a document heavier than the caller said it would accept.

    Measured over the assembled document and before it is written, because
    a file that is too large to open is not made smaller by being on disk,
    and because what the guard is protecting is whoever opens the file
    rather than the disk it sits on.

    Args:
        measured: The finished document's weight in bytes, in the
            serialisation it is about to be written in.
        limit: The ceiling the caller set, in bytes.

    Raises:
        PolicySelectionError: If ``measured`` is over ``limit``.

    """
    if measured > limit:
        raise PolicySelectionError(_too_large(measured, limit))
