# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""How a reader of a node gets back to the artefact it was emitted against.

Most operations carry everything they need in the node: ``at_period``
needs an offset, ``to_monthly`` needs a method name, and both fit in a
typed attribute. Three kinds do not. A ``Schedule`` expression depends on
the whole schedule -- its frequency, horizon, day count, business-day
convention, calendar, inception column. A compiled rollforward depends on
an entire compiled IR plus the plugin arguments its kernel was built
with. A ``Curve`` read depends on its tenors, rates, interpolation and
extrapolation. Copying any of them into ``Call.attrs`` would be
transcribing an object into a tuple of strings and calling it a graph.

So the node carries the artefact's **own published identity** --
``Schedule.source_sha()``, ``CompiledRollforward.fingerprint()``,
``Curve.source_sha()`` -- and this module maps that identity back to the
object. All three are SHA-256 digests over a canonical form the artefact
already computes for audit (*Audit by default*); none is invented here.
Each of those canonical forms holds every value its object computes
with, and that -- not the fact that it is a digest -- is what makes it
safe to resolve by. The compiled rollforward is the one that holds that
only in a pair: its fingerprint is the machine alone and leaves out the
schedule the machine runs on, so its calls carry the
schedule's ``source_sha()`` beside it and the compilation is filed under
both.

An assumption ``Table`` is the fourth entry, and it is here for a
different reason from the other three. Its lowering records the processed
key/value roles beside the content hash, and the kernel checks both when
it resolves the name at execution time. The object also supplies the
artifact's account of which bases the
model was run against -- the node carries the table's name and the
content hash of its processed frame, and a reader wanting more than that
pair has to reach the table itself. Registering it at the very site that
puts the hash on the node is what stops the two from ever naming
different things: one call produces both. That agreement is by
**adjacency, and single-threaded** -- the registration and the attribute
are two lines of one emission with no user code between them, which is a
sound argument in one thread and not a lock. Two threads emitting one
name at once would land on a refusal rather than a wrong number, because
the hash on the node is still checked against the base that answers.

**A table is filed twice, because the pair on the node is what identifies
it and neither half does the job alone.** The pair is the one
``frame/lowering/rules/lookup.py`` describes. ``table_for`` is keyed by
content. Two tables with the same processed values under different names
share a fingerprint, so it answers with *a* table holding those values,
not necessarily the one whose name the node carries -- which is exactly
right for reading the values back and would be wrong for reading a name
back. ``table_named`` is keyed by name, last writer wins, which is the
rule the kernel's own by-name resolution follows; and it answers only
after checking that the table it found still carries the content hash the
node was written over. A reader that wants the values asks the first. A
reader that wants *the base this formula named* asks the second, and
there is no third answer: a name whose data has moved is refused, never
quietly resolved by content instead.

**Content alone does not bind a table's column roles.** The schema directory
pins ordered keys and the answer column per name-and-content pair. If names
sharing one content hash have different roles, the artifact exporter omits
that content-only payload as unavailable: the existing payload identity cannot
say which interpretation it carries. Native lookups still use their own pinned
roles. Equal content is interchangeable only after those roles agree.

**The native kernel also checks at collection.** Lowering carries the
name, processed-content hash and ordered key/value roles into the plugin.
The kernel checks them against the same immutable registry snapshot it
uses for the lookup, before applying any missing-key policy. A replaced,
extended or unbound table refuses; identical content with identical roles
still works. This keeps a lazy plan from silently changing its assumptions
without retaining every historical table in memory.

**A mortality read is the caller that wants the name.** ``structure``,
``select_period`` and ``age_basis`` are three flat values, and a flat
value is exactly what an attribute holds, so the convention is on the
node and the lowering rebuilds the clamp from it without reaching
anything here. All that is left to reach is the base underneath, which
the node carries as the same name-and-content-hash pair every lookup
carries -- and it has to be resolved by the name, because ``Table.lookup``
resolves by that same name again at execution time. A base found by
content alone can be a table called something else entirely, and then the
model reads rates it never named while every attribute on the node still
says otherwise: a wrong number, with no refusal anywhere.
``MortalityTable.source_sha()`` still travels on the node, because a
reader is owed the wrapper's published identity, but nothing resolves by
it.

**Because it cannot.** A wrapper's canonical form covers the convention
and the underlying table's name and dimension set; it does not cover a
single rate, as ``MortalityTable.source_sha`` says of itself. So two
wrappers holding one convention over one table name and two different
sets of rates -- exactly what a scenario sweep builds, one per batch --
publish the same digest. A directory keyed on it kept the first of them
and handed it to every later batch, whose lookup then refused: the
``Table`` inside that first wrapper had been superseded by the batch that
came after it. The refusal was right -- a lookup resolving by name to
newer values is how a shock arrives as zero sensitivity -- and the object
it fired on should never have been returned. The name is what carries a
sweep's batch back to its own rates, since every batch rebuilds under one
name and the newest is the one that batch is reading; the content hash
beside it is what proves the base that answered is still the one the read
was written over.

**And an entry is the live artefact, not a copy of what it held.**
``Table.extend`` appends rows and re-stamps the object in place, so a
table filed under one content hash can be holding different values by
the time anybody fetches it: ``table_for`` still answers, and answers
with a table whose ``_registered_sha`` is no longer the key it was asked
under. Nothing here chases that. Copying every frame on the way in would
cost the memory of a model's whole assumption set to defend against a
case the caller can see for itself in one comparison, and a directory
that silently refused a moved table would lose the identity the node
still legitimately carries. So the rule belongs to the caller and is one
line long: **re-read ``_registered_sha`` off what came back and compare
it with the key before treating the values as that key's.**
``frame/graph/assumptions.py`` is the caller that does, and reports a
table that moved off its key as values this process does not hold rather
than publishing them under a digest they no longer hash to.
``table_named`` is asked under a name *and* a hash, so it has both halves
of the comparison in hand and makes it itself; ``table_for`` is asked
under the hash alone and has nothing to compare it with.

**Why identity is a safe key, where ``id()`` was not.** The ingress table
for raw expressions (``NATIVE_REFS``) is keyed by ``id()`` precisely
because two structurally identical Polars expressions may still be
different objects that must not be confused. The opposite is true here:
two artefacts with the same canonical form *are* interchangeable -- that
is what a content fingerprint means, and it is the same argument
``rollforward/_registry.py`` already makes for sharing one materialised
struct column between two compilations of one model. First writer wins,
for the same reason. The by-name directory is the one place that rule is
inverted, and for the mirror of the same reason: a name is not an
identity, two tables under one name are *not* interchangeable, and the
one a formula written now means is the newest -- which is exactly what
the kernel it will execute against would resolve.

**A join's right side is the fifth entry, and the only one that is not an
artefact at all.** It is a plain frame a model handed to one call, with no
published identity of its own and no name anybody gave it -- which is exactly
why the node can carry nothing but its content hash, and why that hash cannot
be resolved anywhere except here. ``register_join_right`` says what is filed
and what it costs; the short of it is that the frame kept is the *sorted* one
the hash was taken over, because the artifact must inline the very frame its
declared fingerprint was taken over and a second sort at export would be a
second derivation of it.

Entries live for the process. One entry per distinct schedule, compiled
rollforward, curve, assumption table or join right side in a model -- units,
not thousands -- and a scenario worker process repopulates naturally when the
model function rebuilds them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio.assumptions._data import TableData
    from gaspatchio.curves._data import CurveData
    from gaspatchio.rollforward._data import CompiledData
    from gaspatchio.schedule._data import ScheduleData

_SCHEDULES: dict[str, ScheduleData] = {}
# A compilation is filed under its run: the machine's fingerprint and the
# schedule it runs on (``register_rollforward`` says why both).
_ROLLFORWARDS: dict[tuple[str, str], CompiledData] = {}
_CURVES: dict[str, CurveData] = {}
_TABLES: dict[str, TableData] = {}
_TABLES_BY_NAME: dict[str, TableData] = {}
# The right-hand side of every join that brought a column, under the content
# identity the join node carries. What is filed is the sorted frame the hash
# was taken over, never the caller's own: :func:`register_join_right` says why.
_JOIN_RIGHTS: dict[str, pl.DataFrame] = {}
# The ordered key columns and answer column are part of a lookup's meaning,
# although the published node carries only name and processed-content hash.
# Pin that meaning once per published identity pair. A second interpretation
# of the same pair is ambiguous and must use another public name.
_TABLE_SCHEMAS: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {}


def register_schedule(schedule: ScheduleData) -> str:
    """Record ``schedule`` under its own source SHA and return that SHA."""
    sha = schedule.source_sha()
    _SCHEDULES.setdefault(sha, schedule)
    return sha


def schedule_for(sha: str) -> ScheduleData:
    """Return the schedule a node's ``schedule`` attribute names.

    Raises:
        KeyError: If no schedule with that SHA was registered in this
            process -- the node was built somewhere else and arrived
            without the artefact it describes.

    """
    try:
        return _SCHEDULES[sha]
    except KeyError:
        msg = (
            f"no schedule registered for {sha!r}: this formula was built "
            "against a projection schedule that does not exist in this "
            "process. Build the expression from the same "
            "af.projection.set(...) that runs the frame."
        )
        raise KeyError(msg) from None


def register_rollforward(compiled: CompiledData) -> tuple[str, str]:
    """Record ``compiled`` under its run and return the run's two identities.

    The run is the machine's published fingerprint and the ``source_sha()``
    of the schedule it runs on. The fingerprint alone is not enough to
    resolve by: it leaves the schedule out, so one machine
    compiled on two schedules in one process -- last quarter's model and this
    quarter's -- shares it, and the two compiled artefacts are not
    interchangeable, because the kernel's period count is the schedule's.

    Returns:
        ``(fingerprint, schedule)``, the two attributes every rollforward
        call carries.

    """
    fingerprint = compiled.fingerprint()
    # A machine reads its schedule even when no formula requests period dates.
    # The public stub and private annotation name the same runtime class.
    schedule = register_schedule(compiled.ir.schedule)
    _ROLLFORWARDS.setdefault((fingerprint, schedule), compiled)
    return fingerprint, schedule


def rollforward_for(fingerprint: str, schedule: str) -> CompiledData:
    """Return the compiled rollforward a call's ``fingerprint`` and ``schedule`` name.

    Raises:
        KeyError: If no rollforward with that fingerprint was compiled on
            that schedule in this process.

    """
    try:
        return _ROLLFORWARDS[fingerprint, schedule]
    except KeyError:
        msg = (
            f"no compiled rollforward registered for {fingerprint!r} on the "
            f"schedule {schedule!r}: this formula reads a rollforward that was "
            "never compiled in this process. Call compile_rollforward(...) in "
            "the same process that runs the frame."
        )
        raise KeyError(msg) from None


def rollforward_named_by(column: str) -> tuple[str, str] | None:
    """Return the run of the compilation whose kernel column is ``column``.

    The other way a formula can name a compiled rollforward. A model that
    wraps an extraction in an expression of its own -- prepending an opening
    period, concatenating two states -- hands the engine a reference to the
    hidden struct column the frame materialises for the kernel, and that
    column name is all the record keeps of which compilation was read. The
    name embeds a digest of the run, truncated, so this is the reverse of
    the minting rather than a search: each registered run is asked what
    column it would mint, using the same function that mints it, so the two
    can never drift into disagreeing.

    Args:
        column: The kernel's scratch column name, as a record's formula
            names it.

    Returns:
        ``(fingerprint, schedule)`` for the compilation that column stands
        for, or None where no rollforward registered in this process would
        mint it -- which is the answer for any other column name, and for a
        rollforward compiled in a process this one is not.

    """
    # The rollforward package imports the frame, which imports this package;
    # a module-scope import here would close that cycle.
    from gaspatchio.rollforward._registry import (  # noqa: PLC0415 — import cycle
        hidden_column_name,
    )

    return next(
        (run for run in _ROLLFORWARDS if hidden_column_name(*run) == column),
        None,
    )


def register_curve(curve: CurveData) -> str:
    """Record ``curve`` under its own source SHA and return that SHA."""
    sha = curve.source_sha()
    _CURVES.setdefault(sha, curve)
    return sha


def curve_for(sha: str) -> CurveData:
    """Return the curve a node's ``curve`` attribute names.

    Raises:
        KeyError: If no curve with that SHA was built in this process.

    """
    try:
        return _CURVES[sha]
    except KeyError:
        msg = (
            f"no curve registered for {sha!r}: this formula reads a yield "
            "curve that does not exist in this process. Build the curve in "
            "the same process that runs the frame."
        )
        raise KeyError(msg) from None


def register_join_right(sorted_right: pl.DataFrame, fingerprint: str) -> str:
    """File a join's right side under the content identity its node carries.

    The fifth entry, and the one whose object is a plain frame rather than an
    artefact with a published identity of its own. A ``join`` node carries
    ``on``, ``how`` and the right side's content hash, and a consumer holding
    those three and no right side can read what the join did and cannot do it:
    the hash answers "which version?" and answers "which table?" for nobody.
    So the frame is kept here, and the exporter reads it back under the same
    hash and writes it into ``assumptions[]`` beside the tables (§11.1.2).

    **What is filed is the sorted frame, not the caller's.** The fingerprint is
    taken over the right side in canonical form -- columns ascending by name,
    rows sorted by every column (§12.3) -- and
    §13 puts the obligation on the producer to inline *exactly* the frame the
    declared fingerprint was taken over. Filing the caller's own frame and
    sorting again at export would be a second derivation of that order, over a
    frame the caller may have changed in the meantime -- and a payload that
    hashes to something other than the digest beside it is the one failure this
    section exists to make impossible. The sorted frame already exists when this
    is called, because hashing it is what produced the identity; what this costs
    is keeping it alive, not making it.

    **The cost, plainly.** One copy of each distinct right side, for the life of
    the process. A right side is a product table or a parameter set -- tens of
    rows in the models this was measured on -- and the guard at export is what
    bounds what travels in the file. A wide one is the place this strains
    *Optimize for the laptop*, and the number is the frame's own: a 100,000-row
    right side of ten float columns is about 8 MB held.

    First writer wins, as it does for the other four: two frames with the same
    content hash hold the same values and are interchangeable, which is what a
    content fingerprint means. A model joining one table twice therefore files
    it once, and the directory carries one entry for it.

    Args:
        sorted_right: The right side with its rows already sorted by every
            column -- the frame ``fingerprint`` was taken over.
        fingerprint: That frame's content hash, as the node carries it.

    Returns:
        ``fingerprint``, so a caller can file and record in one expression.

    """
    _JOIN_RIGHTS.setdefault(fingerprint, sorted_right)
    return fingerprint


def join_right_for(fingerprint: str) -> pl.DataFrame:
    """Return the right side a ``join`` node's ``right_fingerprint`` names.

    Raises:
        KeyError: If no right side with that content hash was joined in this
            process -- the record arrived from a log that crossed a process
            boundary, and the frame it names was never in front of this one.

    """
    try:
        return _JOIN_RIGHTS[fingerprint]
    except KeyError:
        msg = (
            f"no join right side registered for {fingerprint!r}: this record "
            "names a table that a join brought columns in from, and no join "
            "in this process was handed it. Run the join in the same process "
            "that exports the frame."
        )
        raise KeyError(msg) from None


def register_table(table: TableData) -> str:
    """File ``table`` under both halves of its identity and return the hash.

    The hash is the one the table computed for itself when it was
    registered -- the same string a lookup node carries as
    ``table_fingerprint``. It is read off the table rather than recomputed
    here for the reason ``frame/lowering/rules/lookup.py`` gives: the
    published ``source_sha()`` covers the name and the dimension set too
    and reserialises the frame on every call, which is far too expensive
    for the per-formula emission path.

    The name entry is the other half, and it is last writer wins where the
    content entry is first: two tables sharing a hash hold one set of
    values and are interchangeable, while two tables sharing a name hold
    two, and the one a formula being emitted now reads is the newest --
    which is the table the kernel would resolve that name to as well.

    **The newest is the condition, not a description of the caller.** An
    emission is not proof that its base is current: a formula built
    through a wrapper held past its own base's rebuild is emitted first
    and refused second, and filing it on the way through would leave the
    name pointing at a base the kernel would never resolve that name to.
    Nothing could read rates out of that -- ``Table.lookup``'s own guard
    fires on whatever ``table_named`` hands back -- but a read written
    over the base that *is* current would be refused, and refused in the
    name of a hash no live base carries. So the name entry is filed only
    when this table is what its name currently registers, which is the
    one thing the paragraph above already claims it is.

    The entry can still lag the kernel by one registration, because a
    table registered under a name and never read files nothing: the
    directory then holds a base that was current when it was filed and no
    longer is. A read resolved against it meets ``Table.lookup``'s guard
    instead of this module's, which refuses it just the same and says
    something true about why. Where the directory holds no entry for the
    name at all, ``table_named`` reads the same record this condition
    reads, rather than reporting a name this process holds as one it does
    not.
    """
    from gaspatchio.assumptions._data import (  # noqa: PLC0415 - load live registry on use
        _REGISTERED_TABLE_SHAS,
        TableSupersededError,
    )

    fingerprint: str = table._registered_sha  # noqa: SLF001 - the emitted attribute
    key_columns, value_column = table._lookup_schema()  # noqa: SLF001 - shared table data contract
    schema = (tuple(key_columns), value_column)
    identity = (table.name, fingerprint)
    pinned = _TABLE_SCHEMAS.setdefault(identity, schema)
    if pinned != schema:
        msg = (
            f"Assumption table {table.name!r} cannot give the same processed "
            f"content {fingerprint} different key/value roles: it was first "
            f"read with keys {list(pinned[0])!r} and value {pinned[1]!r}, and "
            f"this read has keys {list(schema[0])!r} and value {schema[1]!r}. "
            f"Give the differently keyed table a distinct name."
        )
        raise TableSupersededError(msg)
    _TABLES.setdefault(fingerprint, table)
    registered = _REGISTERED_TABLE_SHAS.get(table.name)
    if registered is None or registered == fingerprint:
        _TABLES_BY_NAME[table.name] = table
    return fingerprint


def table_schema(name: str, fingerprint: str) -> tuple[list[str], str]:
    """Return the one key/value meaning filed for a lookup identity pair.

    A direct or deserialized node that never passed through ``register_table``
    has no role identity in its public attributes. Deriving one from whichever
    same-named table is current would let that table reinterpret the node, so
    absence refuses instead.
    """
    try:
        keys, value = _TABLE_SCHEMAS[(name, fingerprint)]
    except KeyError:
        msg = (
            f"no key/value roles are registered for assumption table {name!r} "
            f"under {fingerprint}: build the expression through the Table "
            f"that defines those roles rather than lowering this node directly."
        )
        raise KeyError(msg) from None
    return list(keys), value


def table_schemas_for(
    fingerprint: str,
) -> frozenset[tuple[tuple[str, ...], str]]:
    """Return every key/value meaning observed for processed table content."""
    return frozenset(
        schema
        for (_name, content), schema in _TABLE_SCHEMAS.items()
        if content == fingerprint
    )


def table_for(fingerprint: str) -> TableData:
    """Return an assumption table holding the values a node's hash names.

    Raises:
        KeyError: If no table with that content hash was built in this
            process.

    """
    try:
        return _TABLES[fingerprint]
    except KeyError:
        msg = (
            f"no assumption table registered for {fingerprint!r}: this "
            "formula reads an assumption table that does not exist in this "
            "process. Build the Table(...) in the same process that runs "
            "the frame."
        )
        raise KeyError(msg) from None


def table_by_name(name: str) -> TableData | None:
    """Return the table a read last resolved under ``name``, or None.

    The by-name directory as it stands, with none of :func:`table_named`'s
    checks: a caller that only describes a table -- where it was read from --
    compares the identity itself and answers that it does not know where the
    two disagree, rather than refusing.
    """
    return _TABLES_BY_NAME.get(name)


def table_named(name: str, fingerprint: str) -> TableData:
    """Return the assumption table a node names, if it still holds what it read.

    The door for lookup and mortality lowering to answer *with the base this
    formula named* rather than with any base holding the right values.
    Both halves of the node's pair are required and both
    are used: the name selects, and the content hash checks. There is no
    third outcome where a mismatch falls back to the content-keyed
    directory, because a base resolved by content alone can be a table
    under a name the model never wrote, and a read that answers from one is
    a wrong number nothing downstream contradicts.

    **A miss in this directory is not the same fact as a name this process
    does not hold, and only one of the two is what the reader is told.**
    A base is filed here by the read that resolves it, so a name whose
    bases have all been superseded before any of them was read -- a sweep
    that stacks its batches first and runs its models afterwards -- has no
    entry at all. Reporting that as *no such table in this process* would
    be false while several of that name sit in the registry, and it would
    send the reader to build a table they have already built.

    So a miss is decided against the Python record of what the kernel
    holds by name, and the three answers are three different sentences. A
    name that record does not hold is genuinely absent, and keeps the
    message it always had. A name it holds over rates the node was not
    written over is the supersede, in the public error a caller can catch,
    whether or not any base of that name was ever read. A name it holds
    over exactly the rates the node names, with no base of that name filed
    here, has simply never been read: the values are right and there is no
    object to hand back, which is what the reader is told instead of being
    told the table does not exist.

    **What the name holds is the record's answer, not the directory's**,
    and the sentences above say so wherever the two disagree.
    ``register_table`` files the by-name entry on the read that resolves a
    base, so a base registered and never read leaves the directory one
    registration behind. A hit requires both the filed base and the registry
    record to agree with the node: otherwise a replay could pass the stale
    directory check and execute against replacement rates. The refusal takes
    its hash from the record, so it cannot report a hash the name does not
    hold. In the one state where the record agrees with the node and only
    the directory lags, the refusal says that: this door holds an earlier
    base of the name and nothing over the rates the read names.

    Args:
        name: The ``table`` attribute the node carries -- the name the
            kernel will resolve by at execution time.
        fingerprint: The ``table_fingerprint`` attribute beside it -- the
            content hash of the processed frame the read was written over.

    Returns:
        The table registered under ``name``, whose registered content hash
        is ``fingerprint``.

    Raises:
        KeyError: If this process holds no assumption table of that name at
            all -- the node was built somewhere else and arrived without
            the base it describes. Also if the name is held here over
            exactly the rates the node names but no read has resolved a
            base under it, which leaves the values right and this door
            without an object to answer with.
        TableSupersededError: If the rates ``name`` holds are not the ones
            the node was written over, whether the base that holds them was
            read here or only registered. Answering would serve rates the
            formula was never written over, which is the shape a scenario
            override is lost in and a sweep reports zero sensitivity from.
            Also in the one state where the record agrees with the node and
            the by-name directory lags it: the rates are right and the only
            base filed here under that name is an earlier one, so there is
            still nothing to answer with, and the error says which of the
            two it met.

    """
    from gaspatchio.assumptions._data import (  # noqa: PLC0415 - load live registry on use
        _REGISTERED_TABLE_SHAS,
        TableSupersededError,
    )

    table = _TABLES_BY_NAME.get(name)
    if table is not None:
        filed: str = table._registered_sha  # noqa: SLF001 - the emitted attribute
        held = _REGISTERED_TABLE_SHAS.get(name, filed)
        if filed == fingerprint and held == fingerprint:
            return table
    else:
        registered = _REGISTERED_TABLE_SHAS.get(name)
        if registered is None:
            msg = (
                f"no assumption table registered under the name {name!r}: this "
                "formula reads an assumption table that does not exist in this "
                "process. Build the Table(...) in the same process that runs "
                "the frame."
            )
            raise KeyError(msg)
        if registered == fingerprint:
            msg = (
                f"no assumption table resolved under the name {name!r}: this "
                f"process holds {name!r} over exactly the rates {fingerprint} "
                f"names, but no read has resolved a base under that name here, "
                f"so there is no Table to answer with. Build the expression "
                f"from that Table -- reading through it is what files it -- "
                f"rather than lowering this record against it."
            )
            raise KeyError(msg)
        held = registered

    if held == fingerprint:
        msg = (
            f"Assumption table {name!r} cannot answer this read: {name!r} "
            f"is held here over exactly the rates {fingerprint} names, and "
            f"the only base of that name resolved in this process is an "
            f"earlier one. A read answers from the base it names, and this "
            f"door has no object over those rates to answer with. Build "
            f"the expression from the current {name!r} Table -- reading "
            f"through it is what files it -- rather than lowering this "
            f"record against it."
        )
    else:
        msg = (
            f"Assumption table {name!r} has been superseded: this read was "
            f"built over the rates {fingerprint} names, and {name!r} now "
            f"holds {held}. A read resolves the base it names, and "
            f"answering from a base that has moved would serve rates the "
            f"model never read (a scenario override lost this way reports "
            f"zero sensitivity). Rebuild the expression from the current "
            f"{name!r} Table, or give the two sets of rates distinct names."
        )
    raise TableSupersededError(msg)


__all__ = [
    "curve_for",
    "join_right_for",
    "register_curve",
    "register_join_right",
    "register_rollforward",
    "register_schedule",
    "register_table",
    "rollforward_for",
    "rollforward_named_by",
    "schedule_for",
    "table_by_name",
    "table_for",
    "table_named",
    "table_schema",
    "table_schemas_for",
]
