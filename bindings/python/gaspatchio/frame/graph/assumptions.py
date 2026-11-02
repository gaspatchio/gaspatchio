# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Which assumption bases a model read, taken off its own operation trees.

A graph that says how every column was computed and nothing about the
bases those columns were computed *from* leaves a reviewer with half an
answer. "Which mortality table was this run against? Which curve? Which
projection schedule?" is not a question about a formula, and re-running
the model to find out is exactly what an audit record exists to make
unnecessary (*Audit by default*).

Nothing is derived here that the graph does not already hold. A lookup
node carries the table's name and the content hash of its processed
frame; a schedule read and a curve read each carry the artefact's own
``source_sha()``. The same attributes ``frame/lowering/rules`` puts on
those nodes so a lowering can resolve them are what this walk reads back
out -- so the section can never name a base the model did not read.

A compiled rollforward's node names its schedule beside its compilation:
the compiled fingerprint is the machine alone, so the call
carries the schedule's ``source_sha()`` as data, and the machine reads the
schedule even if no formula asks for dates. The compilation's own node is
where that read is named; the calls that read a state back out of it read
the compilation, and name the schedule no second time.

**It can miss one it did.** The walk reads what the record's own tree
names, and a tree is only as complete as the recording that made it.
Where an expression reached the fold already collapsed into a single
engine-native fragment -- a lookup combined with a scalar literal is the
shape that reaches this today -- the read sits inside that fragment's
text, which carries the engine's own spelling of the call and neither
the table's name nor its content hash. The base is named nowhere for
this walk to find, so the section comes back empty while the node's own
``formula`` still says ``lookup(...)``. Reading it back out of the
fragment's text would be inventing the answer rather than reporting it.
What the record does say is where to distrust it: such a node carries
``tier`` ``engine_native``, which is the field that tells a reader the
account may be short, and a node at ``engine_native`` or ``opaque``
inherits Annex A.2's reading that the record's own account of it is
partial. Widening what is kept belongs where the fragment is minted,
not here.

**A join's right side is a base too.** A column that arrived from a second
table rests on that table exactly as a rate rests on a mortality basis. The
record used to identify it without carrying it -- so a consumer holding the
file could read what a joined model did and could not do it. The right side
is now an entry of its own, kind ``join``, carrying the frame the join was
handed under the identity the node already published (section 11.1.2).

**One walk, two readings.** :func:`artefacts_read` answers for the model:
every base, once, in one order. :func:`assumptions_read_by_node` answers
for one column at a time, and is what lets a reader join a figure to the
base it rests on rather than inferring the join from a node's `source`.
The two are the same traversal because a directory and an index that
could disagree would be worse than either on its own. **The one place they
differ is the join**, and it is the reading rather than a drift: a joined
node's formula read nothing, so the per-node index names nothing for it and
the directory still carries the base. :func:`assumptions_read_by_node` says
why in full.

**Every base is named, and three kinds are named after their contents.** A
table states its own name -- that is the string a lookup resolves by. A
schedule, a curve and a join's right side are value objects with nothing but
their content to be called, so each is known here by its kind and the first
eight digits of the identity beside it: ``curve:75ef1e0c``,
``schedule:7bac022a``, ``join:dfae08cf``.

The alternative was a null, and a null cost the join. A node's names are
what §8's ``reads_assumptions`` carries, so an entry with no name could
be named by no node -- and a curve sat in the directory with nothing
tying it to the figures that rested on it, which is precisely the
directory-and-usage pairing Article 244(g) asks for. Inventing a name a
model author never used would be a claim about the model; a name that is
the kind and the digest, in that shape, is a claim about nothing except
the entry it stands on, and a reader who suspects it of being more than
that can check it against the fingerprint written beside it in one
glance. Where an artefact ever does state a name of its own, that name
is what appears -- the synthesis fills a gap rather than overriding
anybody.

**The name is a label; the fingerprint is the identity.** Two entries of
one kind whose digests agree in their first eight digits would share a
label, and the section still tells them apart -- by the whole digest,
which is what it sorts and de-duplicates on. A name is what a reader
follows a join by, not what the format identifies a base by, and the
eight digits are chosen for the length a person reads off a screen.

**And the values themselves.** :func:`payload_of` reads a base's contents
back out of the artefacts the process registered while the model was
written. A directory of names and digests tells a reader which mortality
basis a run used and leaves them to find it; the digest is only checkable
against a file somebody still holds. Carrying the values makes the entry
answer for itself -- a reader re-hashes what is in front of them and
either the two agree or the artifact is wrong (*No vendor lock-in, by
construction*). Each kind is projected as the very thing its declared
identity was taken over, and not a re-derivation of it: a table hands
over its processed frame, a join its right side in the sorted order the
hash was taken over, a schedule and a curve their own
``canonical_form()``. A base this process cannot reach hands over
nothing, and the entry says so under that reason rather than the export
failing -- a log that crossed a process boundary still names what the
model read. It says so out loud as well: both ways of not reaching a
base warn, because a section that quietly came back short is the one
thing an account of what a model rests on must not be.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

import polars as pl
from loguru import logger

from gaspatchio._dtypes import neutral_dtype
from gaspatchio._identity import SHA256_PREFIX
from gaspatchio._semantic.ir import Call, walk

from .graph_models import ROLLFORWARD_CALL
from .value_extractor import _a_count_past_the_calendar

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from gaspatchio._semantic.ir import OpNode
    from gaspatchio.assumptions._data import TableData
    from gaspatchio.typing import PolarsDataType

    from .graph_builder import CalcGraph
    from .graph_models import NodeId

__all__ = [
    "ArtefactKind",
    "ArtefactReference",
    "TableSource",
    "artefacts_read",
    "assumptions_read_by_node",
    "payload_of",
    "table_source_of",
]

# Which assumption primitive an entry records. Closed, and the same four
# words the artifact format writes on the wire.
ArtefactKind = Literal["table", "join", "schedule", "curve"]

# How each kind states itself on a ``Call``: the attribute carrying its
# content identity, and the attribute a name of its own would be read
# from. A table is the only kind that states one, and its identity and
# its name are two attributes rather than one because two tables holding
# the same values under different names share a fingerprint -- the pair
# is the identity, which is the reading
# ``frame/lowering/rules/lookup.py`` sets out. The other three state none,
# and are named after their contents below.
_ARTEFACT_ATTRIBUTES: Final[tuple[tuple[ArtefactKind, str, str | None], ...]] = (
    ("table", "table_fingerprint", "table"),
    ("join", "right_fingerprint", None),
    ("schedule", "schedule", None),
    ("curve", "curve", None),
)

# The kinds the per-node index leaves out. A joined node's
# ``reads_assumptions`` stays empty because that field names what a node's own
# formula read, and an arriving column's formula read nothing: the key
# selected the row and computed no value (section 11.1.2). The directory still
# carries the right side, and a reader reconciling an arriving column to it
# matches the node's own ``right_fingerprint`` against that section -- which is
# what Annex A.2 now says where a reader meets the gap.
_ABSENT_FROM_THE_NODE: Final[frozenset[ArtefactKind]] = frozenset({"join"})

# How many digits of a base's identity a name taken from it wears. Eight
# is the length somebody reads off a screen and types into a search, and
# it is enough of the digest to check the name against the fingerprint
# beside it without reading either twice.
_NAME_DIGITS: Final[int] = 8


@dataclass(frozen=True, slots=True)
class ArtefactReference:
    """One assumption base a model read: what kind it is, and which one.

    Attributes:
        kind: Which assumption primitive this is.
        name: What the entry is called. A table's own name where it
            states one; otherwise the kind and the first eight digits of
            ``fingerprint``, which is a label a reader can follow a join
            by and check at a glance. It is not the identity -- two
            entries of one kind whose digests agree that far would share
            it.
        fingerprint: The base's content identity, and the thing that
            actually tells two entries apart.

    """

    kind: ArtefactKind
    name: str
    fingerprint: str


def artefacts_read(graph: CalcGraph) -> tuple[ArtefactReference, ...]:
    """Return every base a tree names, sorted and de-duplicated.

    Args:
        graph: The folded calculation graph. Its operation trees and the
            schedules of compilations those trees name are read. Two things
            therefore reach no entry: a column that merely holds
            assumption values, which has no tree behind it at all, and a
            tree that collapsed to one engine-native fragment, whose read
            is inside the fragment's text and carries neither a name nor a
            hash there. The first is a column the model never computed;
            the second is a base the model did read, and the reading
            node's ``tier`` is where a reader is told so (see this
            module's own account of it). A join is here on the same terms
            as the rest: its node's tree carries ``right_fingerprint``, so
            a join that brought a column contributes one entry per distinct
            right side, and a right side handed over lazily -- which has no
            identity on the node at all -- contributes none. A selection
            step's tree is read too: a semi or anti join's right side is a
            base the model's choice of policies rests on, and the document
            carries it so a replay can make the same choice.

    Returns:
        One reference per distinct base, ordered by kind, then by name,
        then by identity. A base read from four formulas appears once --
        this is a directory of what the model rests on, not a log of the
        reads -- and the order is a property of the model rather than of
        the run, so two artifacts of one model compare as written.

    """
    trees = [*graph.op_trees.values(), *(step.tree for step in graph.selection)]
    found = {reference for tree in trees for reference in _references_in(tree)}
    return tuple(sorted(found, key=_in_order))


def assumptions_read_by_node(graph: CalcGraph) -> dict[NodeId, tuple[str, ...]]:
    """Return, per node, the names of the entries that node's own tree reads.

    Args:
        graph: The folded calculation graph.

    Returns:
        One entry per node that has an operation tree, holding that tree's
        assumption names sorted and de-duplicated -- usually empty, since
        most formulas read columns rather than bases. A node with no tree
        of its own is absent rather than empty: a column nothing accounts
        for has no formula to answer for, and a caller reads its own
        default over them. A base a tree names contributes wherever the
        node's own formula is what read it: a curve is named after its own
        contents, so a node reading one names the same string the entry
        carries and the join resolves for it as it does for a table.

        **A join's right side is the one that does not**, and the omission
        is the reading rather than a gap in it. This field is what a node's
        own formula read, and an arriving column's formula read nothing:
        the key selected the row and computed no value, which is why such a
        node's ``reads`` is empty too (section 11.1.2). Naming the entry
        here would say the arriving column *resolved* a base the way a
        lookup does, and every consumer that reads a non-empty
        ``reads_assumptions`` as a lookup would then read it as one. The
        directory still carries the right side; a reader reconciling an
        arriving column to it matches the node's own ``right_fingerprint``
        against that section, which is what Annex A.2 says.

    """
    return {
        node_id: tuple(
            sorted(
                {
                    entry.name
                    for entry in _references_in(tree)
                    if entry.kind not in _ABSENT_FROM_THE_NODE
                }
            )
        )
        for node_id, tree in graph.op_trees.items()
    }


def payload_of(reference: ArtefactReference) -> dict[str, Any] | None:
    """Return the contents of the base ``reference`` names, or None where it cannot.

    Args:
        reference: One entry of the directory :func:`artefacts_read`
            returns. Only its kind and its identity are used: the identity
            is what the artefact was filed under when the formula reading
            it was written, and the name is what a reader calls the base
            rather than a key into anything.

    Returns:
        Plain JSON -- no engine object, no type this document has not
        named -- or None where this process holds no artefact under that
        identity. Each kind hands over the very form its declared
        fingerprint was taken over, so a reader re-hashes what is in front
        of them rather than a reconstruction of it:

        - a **table** hands over its processed frame: the ``dimensions``
          it is keyed by and the ``value`` column it answers with, then
          every column of that frame in the frame's own order, each with
          the neutral type (§10) the content grammar tags it under, and
          then the rows. Those columns are ``f64``, ``i64`` or ``str``:
          the registry refuses a value column that is not a float; safely
          representable numeric keys are normalized to Float64; wide signed
          integer keys retain their identity as Int64; and text stays text.
          **A date or a timestamp dimension publishes as a ``date`` or a
          ``datetime``**, its values as section 10's ISO-8601 text -- that
          is the kind the table's fingerprint is taken in (section 12.3), so
          a count of days the kernel keys by is not what travels; a
          timestamp in a zone other than UTC has no payload form that keeps
          its zone, and its values are not carried. A non-finite float travels as
          the string sentinel
          ``"NaN"``, ``"Infinity"`` or ``"-Infinity"``, which
          ``_wire_value`` explains. Storage width is deliberately absent
          -- the grammar collapses it, so a consumer that rebuilds the
          rows at any width re-derives the same digest;
        - a **join** hands over the right side the join was given, in the
          sorted order its fingerprint was taken over: the same ``columns``
          and ``rows`` a table publishes and **no ``dimensions`` and no
          ``value``**. A join declares no key and answer roles -- equality
          of key values is the whole matching rule, and the key is named on
          the node -- so there is nothing here to assign a role to, and an
          entry stating one would be claiming a reading of the frame that
          the join never made;
        - a **schedule** and a **curve** hand over their own
          ``canonical_form()``, which is already plain JSON and is already
          the form their ``source_sha()`` is taken over.

        None is not an error and is not a null payload: it is this process
        saying it does not hold *these* values, which the caller states as
        an omission whose reason is that the values are unavailable rather
        than that they were weighed and declined. Three things say that. The
        base may never have been built here -- a model can be exported from
        a log that crossed a process boundary, and refusing to write the
        artifact because a dictionary in this interpreter is empty would
        lose the whole record to recover one section of it. Or the base may
        have moved off the identity the formula read it under, which
        ``_table_payload`` explains. Or two tables may share the processed
        content fingerprint while assigning its columns different key and
        answer roles. The digest and its one sidecar filename distinguish
        none of those roles, so carrying either schema would attribute it to
        both tables. In every case the values under that fingerprint are not
        available to be carried unambiguously; each path warns rather than
        passing in silence.

    """
    # The registry is reached from inside the call: it is the far side of
    # the lowering, which imports this package, and naming it at import
    # time would close the loop.
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        curve_for,
        join_right_for,
        schedule_for,
        table_for,
        table_schemas_for,
    )

    try:
        if reference.kind == "table":
            schemas = table_schemas_for(reference.fingerprint)
            if len(schemas) > 1:
                # The document records the omission, and validate and the
                # viewer show it, so this is logged rather than warned.
                logger.warning(
                    f"The audit file names assumption table '{reference.name}' but "
                    f"leaves its values out: another table in this process holds "
                    f"exactly the same values with different key and rate columns, "
                    f"and the file identifies a table's values by their content "
                    f"alone, so it could not say which columns are the keys. Export "
                    f"the model from a process that builds only the tables it reads, "
                    f"and the values travel with it."
                )
                return None
            return _table_payload(
                table_for(reference.fingerprint), reference.fingerprint
            )
        if reference.kind == "join":
            right = join_right_for(reference.fingerprint)
            dropped = _column_the_wire_drops(right, "join", reference.name)
            return None if dropped is not None else _frame_payload(right)
        if reference.kind == "schedule":
            return dict(schedule_for(reference.fingerprint).canonical_form())
        return dict(curve_for(reference.fingerprint).canonical_form())
    except KeyError:
        # Recorded in the document, so logged rather than warned (see above).
        logger.warning(
            f"Assumption {reference.kind} '{reference.name}' is not registered in this "
            f"process under {reference.fingerprint}, so the artifact names "
            f"the base, keeps its identity and carries no values for it. "
            f"This is what a model exported from a log that crossed a "
            f"process boundary looks like from the inside. Build the base "
            f"in the same process that exports the frame if the values are "
            f"to travel with it."
        )
        return None


@dataclass(frozen=True, slots=True)
class TableSource:
    """Where a table's values came from, as far as this process can say.

    Attributes:
        file: The resolved path the table was handed, or None where it was
            handed a frame.
        shaped_by: Each step of the table's own recipe that reshaped what it
            read -- a column renamed, cast, melted, set or computed -- in
            the order the dimensions were declared. Empty where the
            processed frame is a plain read of the source.

    """

    file: Path | None
    shaped_by: tuple[dict[str, Any], ...]


def table_source_of(reference: ArtefactReference) -> TableSource | None:
    """Return where a table came from, or None where this process cannot say.

    A table handed a path when it was built names that file; one handed a
    frame names none, and that is an answer too -- the model built it in its
    own code. Its recipe says, besides, whether the processed frame is a
    plain read of what it was handed or was reshaped on the way. All of it is
    known only while this process holds the table the formula read, under
    its name and with the values it read: a base built somewhere else, or
    one that has moved since -- ``Table.extend`` re-stamps the live object --
    is a table this process cannot speak for, and the answer is None.

    Args:
        reference: One table entry of the directory :func:`artefacts_read`
            returns.

    Returns:
        The table's source, or None.

    """
    from gaspatchio.assumptions._processing import (  # noqa: PLC0415 — import cycle
        shaping_steps,
    )
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        table_by_name,
    )

    table = table_by_name(reference.name)
    if table is None:
        return None
    held: str = table._registered_sha  # noqa: SLF001 — the stamp the node carries
    if held != reference.fingerprint:
        return None
    return TableSource(
        file=table._source_file,  # noqa: SLF001 — recorded at build
        shaped_by=(
            *table._inherited_steps,  # noqa: SLF001 — what a shock or a stack carried over
            *shaping_steps(table._dimensions),  # noqa: SLF001 — the recipe
        ),
    )


def _table_payload(table: TableData, fingerprint: str) -> dict[str, Any] | None:
    """Return one assumption table's contents, as the wire carries them.

    The frame is the processed one the table registered and took its
    content hash over, handed on untouched: not a projection of it and not
    a re-sort of it. The two have to be the same frame or the payload
    would fail the one check it exists to pass -- a reader re-hashing the
    values under the published content grammar and reaching the
    fingerprint written beside them.

    **A table filed under one identity can move to another while the
    process is still running.** ``Table.extend`` appends rows and re-stamps
    the object in place, so the registry -- which holds the live object,
    not a copy of the frame -- can hand back a table whose values are no
    longer the ones ``fingerprint`` names. Inlining those would publish
    values under a digest that does not hash to them, in the one section
    whose whole promise is that it does, and a reader doing the check the
    schema invites would find the artifact lying rather than find the
    drift. So the identity is re-read off the table and compared before
    anything is carried, and a table that moved off its key is reported as
    values this process does not hold -- which is the truth about them.
    """
    name: str = table._name  # noqa: SLF001 — the name the node carries beside it
    moved_to: str = table._registered_sha  # noqa: SLF001 — the stamp the node carries
    if moved_to != fingerprint:
        # Recorded in the document, so logged rather than warned (see above).
        logger.warning(
            f"Assumption table '{name}' has moved since the formula reading "
            f"it was written: the formula read it under "
            f"{fingerprint}, and the table now carries {moved_to}. "
            f"Table.extend re-stamps the live object in place, so the values "
            f"the recorded identity names are no longer here to be carried. "
            f"The artifact keeps that identity and carries no values for it; "
            f"publishing the current rows under the recorded digest would "
            f"fail the re-hash the format invites a reader to run. If the "
            f"values are to travel, export before extending the table."
        )
        return None
    from gaspatchio.assumptions._processing import (  # noqa: PLC0415 — import cycle
        _in_its_kinds,
    )

    # The frame the fingerprint was taken over: a date or timestamp key in
    # its own kind, as Table.fingerprint() hashes it (section 12.3).
    frame = _in_its_kinds(
        table._materialised_df(),  # noqa: SLF001 — the registered frame
        table._key_kinds,  # noqa: SLF001 — the kind the table was built from
    )
    if _column_the_wire_drops(frame, "table", name) is not None:
        return None
    return {
        "dimensions": sorted(table._dimensions),  # noqa: SLF001 — the keys it is keyed by
        "value": table._value,  # noqa: SLF001 — the column it answers with
        **_frame_payload(frame),
    }


def _frame_payload(frame: pl.DataFrame) -> dict[str, Any]:
    """Return the columns and rows of one frame, as the wire carries them.

    The half of a payload that is the values themselves, shared by the two
    kinds whose fingerprint is a content hash over a frame: a table's
    processed frame, and a join's sorted right side. Both are hashed under
    one grammar (§12.3), so both publish under one projection -- every
    column in the frame's own order, each with the neutral type (§10) the
    grammar tags it under, and then every row in the frame's own order.

    Nothing is sorted, projected or re-typed here. The caller hands over the
    frame its declared fingerprint was taken over and this writes it down;
    §13 puts that obligation on the producer in as many words, and a payload
    tidied on the way out is a payload that re-hashes to nothing.

    What the two kinds do not share is what sits beside the values: a table
    states the ``dimensions`` it is keyed by and the ``value`` it answers
    with, and a join states neither, having no roles to declare.
    """
    return {
        "columns": [
            {"name": name, "dtype": neutral_dtype(dtype, column=name)}
            for name, dtype in frame.schema.items()
        ],
        "rows": [
            [_wire_value(value) for value in row]
            for row in _dates_as_iso_text(frame).iter_rows()
        ],
    }


# Section 10's wire form for a date and an instant: ISO-8601 text. The
# fraction carries every digit the column's unit holds, so a nanosecond
# instant travels whole -- a Python datetime would cut it at the microsecond.
_ISO_DATE: Final[str] = "%Y-%m-%d"
_ISO_INSTANT: Final[str] = "%Y-%m-%dT%H:%M:%S%.f"


def _dates_as_iso_text(frame: pl.DataFrame) -> pl.DataFrame:
    """Return ``frame`` with each date and timestamp as its ISO-8601 text.

    Section 10 puts a ``date`` value on the wire as an ISO calendar date and
    a ``datetime`` value as an ISO timestamp, wherever it appears, an
    assumption payload included -- in a ``list[date]`` or ``list[datetime]``
    column too, each element as its text, at every depth. A timestamp in UTC
    is written as the UTC instant it is, with no offset, as a zone-naive one
    is: the content grammar reads the two alike (section 12.3). The column's
    declared type is taken off the frame before this, so it still says
    ``date`` or ``datetime``.
    """
    as_text = [
        frame[name].list.eval(_as_iso_text(pl.element(), dtype.inner))
        if isinstance(dtype, pl.List)
        else _iso_text_of(frame[name], dtype)
        for name, dtype in frame.schema.items()
        if _leaf(dtype).base_type() in (pl.Date, pl.Datetime)
    ]
    return frame.with_columns(as_text) if as_text else frame


def _iso_text_of(column: pl.Series, dtype: PolarsDataType) -> pl.Series:
    """Return a date or timestamp column as its ISO-8601 text."""
    return column.dt.to_string(
        _ISO_DATE if isinstance(dtype, pl.Date) else _ISO_INSTANT
    )


def _as_iso_text(expr: pl.Expr, dtype: PolarsDataType) -> pl.Expr:
    """Return ``expr`` with each date or timestamp it holds, at any depth, as text."""
    if isinstance(dtype, pl.List):
        return expr.list.eval(_as_iso_text(pl.element(), dtype.inner))
    return expr.dt.to_string(_ISO_DATE if isinstance(dtype, pl.Date) else _ISO_INSTANT)


def _leaf(dtype: PolarsDataType) -> PolarsDataType:
    """Return the type at the bottom of a possibly nested list type."""
    while isinstance(dtype, pl.List | pl.Array):
        dtype = dtype.inner
    return dtype


def _column_the_wire_drops(
    frame: pl.DataFrame, kind: str, name: str | None
) -> str | None:
    """Return the column of ``frame`` a payload cannot carry, warning; else None.

    Two values have no payload form that re-hashes to the digest beside it
    (section 13: the payload MUST be the frame the fingerprint was taken
    over), so the entry keeps its identity and states its values
    ``unavailable``, as it does for values this process cannot carry
    unambiguously:

    * A timestamp in a zone other than UTC, per policy or in a list. It is
      hashed with its zone (section 12.3: one instant shown in another zone
      is another column), and a payload declares a column ``datetime`` and
      nothing more: section 10's ISO text carries an offset at most, never
      the zone.
    * A date or a timestamp outside the years 1 to 9999. Section 10 writes it
      as ISO-8601 text of the form JSON Schema calls ``date`` or
      ``date-time``, whose year is four digits, so it has no such text, and
      section 11.1.33 puts such a date outside the domain; past about 262,000
      years from 1970 the engine cannot even write it.
    """
    for column, dtype in frame.schema.items():
        leaf = _leaf(dtype)
        zone = getattr(leaf, "time_zone", None)
        if isinstance(leaf, pl.Datetime) and zone not in (None, "UTC"):
            # Recorded in the document, so logged rather than warned (see payload_of).
            logger.warning(
                f"The audit file names assumption {kind} '{name}' and leaves its "
                f"values out: its column '{column}' holds timestamps in the zone "
                f"{zone}, which its identity is taken in, and a payload states a "
                f"timestamp's text but not its zone, so the values written down "
                f"would re-hash to another identity. Convert the column to UTC "
                f"before the {kind} is built, and the values travel with it."
            )
            return column
        past = _a_count_past_the_calendar(frame.get_column(column))
        if past is not None:
            # Recorded in the document, so logged rather than warned (see payload_of).
            logger.warning(
                f"The audit file names assumption {kind} '{name}' and leaves its "
                f"values out: its column '{column}' holds a date outside the years "
                f"1 to 9999 ({past}), which a payload writes as ISO-8601 text with "
                f"a four-digit year and so cannot write at all. Keep the date "
                f"within the calendar -- a sentinel such as 9999-12-31 carried "
                f"past it, or a count read in another unit than it was written "
                f"in, are the usual causes -- and the values travel with it."
            )
            return column
    return None


# A cell is a scalar or, in a ``list[T]`` column, a list of cells at any depth.
_Cell = float | int | str | None | list["_Cell"]


# The static numeric tower admits ``int`` wherever it names ``float``; the
# return spells ``int`` because preserving the integer JSON token is the claim.
def _wire_value(value: _Cell) -> _Cell:
    """Return one cell in the form section 10 puts on the wire.

    A table payload's columns are ``f64``, ``i64``, ``str``, ``bool``, or a
    ``date`` or ``datetime`` key already written as its ISO text
    (``_dates_as_iso_text``), so the one cell JSON cannot carry as it stands
    is a non-finite float.
    ``NaN`` and ``Infinity`` are what a lenient writer emits and what a
    strict parser refuses, and null is not available to stand in for one:
    null is the missing-value marker, and a rate nobody supplied and a rate
    that came out of a division by zero are different assumptions that the
    content grammar hashes differently. So a non-finite travels as a string
    naming itself, and the column's declared type stays ``f64`` -- which is
    what makes the string unambiguous. A ``str`` column holding the text
    ``"NaN"`` holds that text; an ``f64`` column holding it holds the
    number, and a consumer maps it back before hashing.

    Section 10 says "wherever a value appears", so a ``list[f64]`` cell --
    a join's right side may carry one -- has each non-finite element written
    the same way, at every depth; the column's declared ``list[f64]`` is what
    makes those strings numbers, as ``f64`` does for a scalar cell.

    Nothing else is touched: an integer stays an integer. A date reaches
    here already as its text, and a table's list key is refused outright. A schedule
    and a curve never come here at all: each hands over its own
    ``canonical_form()``, and if either ever needs a per-cell wire form it
    will need one written against its own types.
    """
    if isinstance(value, list):
        return [_wire_value(element) for element in value]
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    return value


def _references_in(tree: OpNode) -> Iterator[ArtefactReference]:
    """Yield every base ``tree`` names, in the order the walk meets them.

    Duplicates are yielded rather than suppressed: what counts as a
    duplicate differs between the two readings above, and a walk that
    de-duplicated for one of them would be answering the other's question
    badly.
    """
    for node in walk(tree):
        if not isinstance(node, Call) or _reads_through_its_compilation(node):
            continue
        attrs = dict(node.attrs)
        for kind, identity, names in _ARTEFACT_ATTRIBUTES:
            fingerprint = attrs.get(identity)
            if not isinstance(fingerprint, str):
                continue
            stated = attrs.get(names) if names is not None else None
            name = (
                stated
                if isinstance(stated, str)
                else _after_its_contents(kind, fingerprint)
            )
            yield ArtefactReference(kind=kind, name=name, fingerprint=fingerprint)


def _reads_through_its_compilation(node: Call) -> bool:
    """Return whether ``node`` reads its schedule through a compilation it names.

    Every rollforward call carries the ``schedule`` its machine runs on, by
    that schedule's ``source_sha()``, beside the machine's fingerprint, which
    leaves the schedule out. The schedule is the compilation's
    read: the bare ``rollforward`` call is the compilation's own node and names
    it, and a call reading a state, an increment or the whole struct back out
    is a read of that compilation and names it there, not a second time.
    """
    return node.name.startswith(f"{ROLLFORWARD_CALL}.")


def _after_its_contents(kind: ArtefactKind, fingerprint: str) -> str:
    """Return the name a base that states none of its own is known by.

    The kind and the first eight digits of the identity, which is a name
    wearing its derivation on its face: a reader who wants to know where
    it came from reads the fingerprint beside it. Nothing about the model
    is being claimed -- an author who never named a curve still has not
    named one -- and the module's own account says why a null was worse.
    """
    return f"{kind}:{fingerprint.removeprefix(SHA256_PREFIX)[:_NAME_DIGITS]}"


def _in_order(reference: ArtefactReference) -> tuple[str, str, str]:
    """Return the sort key: kind, then name, then identity.

    Every reference carries all three, so the key is total -- sorting a
    mixture of strings and nulls is an error in some readers and an
    arbitrary order in the rest. The last key is what settles a pair of
    one kind whose names tie, which for a base named after its contents
    means a pair whose digests agree in eight digits.
    """
    return (reference.kind, reference.name, reference.fingerprint)
