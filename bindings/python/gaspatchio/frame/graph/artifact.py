# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The envelope an exported calculation graph is written into.

A calculation graph on its own is a list of nodes and a list of edges. It
says how each column was made and says nothing about *which* model it is an
account of, which schema a reader should read it under, or whether it is the
same model that was read last quarter. The envelope is where all of that is
stated, and this module is what builds one.

Twenty members, all but ``sources`` required and several of them routinely
empty, because an empty section here is a claim the producer is making rather
than a value it failed to supply: ``holes: []`` says this model accounts for
every column it holds, which is exactly the sentence a reviewer wants and
exactly the one a bare node list cannot say.

One of them says which data the model was built over. ``book`` is a content
digest of the input columns the model reads, taken over the book the frame
was handed (:func:`book_of`): the digest a result manifest records as
``inputs_digest`` when the engine was handed the book itself, so two
documents -- or a document and such a result -- say whether they rest on the
same policies without anybody having named a file.

One of the seventeen is the axis the values sit on. ``policies`` is the list
of evaluation contexts this artifact carries values for, and ``enrichment``
is its first entry with ``why`` left off -- the same context said twice, once
in the place the edition before it put one. A document carrying one policy
writes every enrichment field exactly as that edition wrote it, so nothing
about a single-policy artifact has moved.

The last, ``document_digest``, seals the finished document as a written
record rather than as an identity, and it is what a reader recomputes to
learn whether this is the file the producer wrote -- a question no
fingerprint in the file was ever going to answer, since an identity moves
when the computation moves and at no other time.

The wire form is flat. In memory a node is ``{id, kind, data}`` with
everything interesting nested inside ``data``; on the wire ``kind`` carries
the account the node gives of its column and every recorded fact sits at the
top of the node object, in the order the format tabulates them, where a
consumer that has never seen this package reads it without a second level of
indirection.

The identifier in ``schema`` is a key, not a locator. A consumer resolves it
through :data:`gaspatchio.schemas.SCHEMA_IDENTIFIERS`, never by parsing the
string for a version and never by fetching it as a URL.

Every model this package ships -- the base model of each tutorial level and
each of the rollforward patterns -- is exported through here under both
profiles on every test run, and each artifact is read back against the
published schema with its own digests recomputed rather than read. A schema
is a tested contract or it is a document, and the difference is whether
anything fails when the file stops matching it: a change to the wire form
that the schema does not allow fails in this repository rather than in
somebody's pipeline a quarter later.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Any, Final, Literal, assert_never

import polars as pl
from loguru import logger

from gaspatchio._beside import imported_from_outside
from gaspatchio._dtypes import with_integers_as_i64
from gaspatchio._identity import SHA256_PREFIX, source_sha_of
from gaspatchio._semantic.ir import Call
from gaspatchio.engines._versions import installed_versions, versions_in_this_process
from gaspatchio.engines.protocol import digest_of_inputs

from .assumptions import (
    artefacts_read,
    assumptions_read_by_node,
    payload_of,
    table_source_of,
)
from .edges import Periods, ReadWay
from .facets import FacetLedger, facet
from .fingerprint import (
    formulas_fingerprint,
    graph_fingerprint,
    selection_fingerprints,
    stamp_fingerprints,
)
from .graph_models import GraphExportConfig, ModelIdentity, NodeType, _document_root
from .graph_utils import lies_outside_the_root, relative_to_root, source_location
from .holes import Hole, holes_in
from .op_json import op_node_to_json
from .rollforward_ir import FACET_NAME as _ROLLFORWARD_IR_FACET
from .rollforward_ir import rollforward_ir_for
from .selection import selection_no_replay_can_make
from .tiers import tier_of

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from gaspatchio._semantic.ir import OpNode

    from .assumptions import ArtefactReference
    from .fingerprint import NodeFingerprints
    from .graph_builder import CalcGraph
    from .graph_models import GraphEdge, GraphNode, NodeId
    from .tiers import OpTier

__all__ = [
    "ARTIFACT_FILE_NAME",
    "DOCUMENT_DIGEST_FIELD",
    "FINGERPRINT_ALGORITHM",
    "PAYLOAD_DIRECTORY",
    "PROFILE_AUDIT",
    "PROFILE_EXECUTABLE",
    "SCHEMA_ID",
    "SEAL_BY_DEFAULT",
    "SELECTION_MEMBER",
    "SOURCE_DIRECTORY",
    "TABLE_PAYLOAD_LIMIT",
    "book_columns",
    "book_of",
    "build_artifact",
    "document_digest_of",
    "payload_bytes",
    "payload_file_name",
    "source_payload_of",
]

# The identifier a consumer resolves through its own table of known
# identifiers to reach the schema document this artifact conforms to.
SCHEMA_ID: Final[str] = "gaspatchio-graph/v0-preview.3"

# The opaque token naming the byte grammar every digest in this artifact was
# taken under. Equality is the only operation defined on it: it is never
# parsed, never ordered, and two artifacts carrying different tokens must not
# be compared. Moving it is never a one-line edit: the published corpus is
# regenerated and its digests reprinted in the same breath, because a corpus
# pinning a grammar nobody emits any more proves agreement with nothing.
FINGERPRINT_ALGORITHM: Final[str] = "gspv0-preview-3"

# The two conformance profiles. ``audit`` is the envelope, the node record,
# the edges and the identity fields -- what a reviewer or a supervisor reads.
# ``executable`` is audit plus everything a consumer would need to evaluate
# the model rather than only read it: the operation tree of every node that
# has one, and a compiled rollforward's own state machine. An ``executable``
# artifact is a conforming ``audit`` artifact -- what the profile adds is
# added, and nothing an ``audit`` reader looks for moves or changes meaning.
PROFILE_AUDIT: Final[str] = "audit"
PROFILE_EXECUTABLE: Final[str] = "executable"

# The envelope member listing every step that chose which rows the model
# values (section 7.6). Written only where there is one.
SELECTION_MEMBER: Final[str] = "selection"

# What the producer says about itself. The name is the package's, and the
# version is read from the installed distribution rather than restated here,
# so the two can never drift.
_PRODUCER_NAME: Final[str] = "gaspatchio"

# The member of ``producer`` that says what produced the values, and the one
# inside it that names what the model imports from outside its directory.
# ``versions`` is the result manifest's own mapping, key for key, so a
# document and a results file of one run can be held against each other
# without translation.
_PRODUCER_VERSIONS: Final[str] = "versions"
_PRODUCER_IMPORTS: Final[str] = "imports"

# Where a reader who meets an unaccounted-for column is pointed. Documentation
# describing what closes the hole, so a reader is told what to do about one
# rather than only that it exists.
#
# The `#holes` fragment is a contract the published page meets, and not a
# description of what a renderer happens to produce: the holes section is
# §7.1, and a renderer deriving anchors from headings would number it
# `#71-the-holes-section` instead. The page declares `#holes` explicitly, and
# `spec/graph-artifact/README.md` carries that obligation for whoever
# publishes it. The direction is deliberate -- the page meets the URI rather
# than the URI meeting the page -- because artifacts carrying this string are
# already written, and an artifact a reader may still follow cannot be
# re-issued.
#
# **The counter in it moves with the identifier, and the reason is that this
# preview has published nothing.** The paragraph above is a rule for a
# released format, where an artifact carrying the `.1` form is out in the
# world and its reader must still land somewhere. No such artifact exists:
# nothing bearing any of these identifiers has shipped outside this
# repository, so there is no reader to strand and no page to keep alive for
# one. What stranding the counter here would cost is coherence -- one
# document naming `spec/graph-artifact/v0-preview.3` in every facet's
# `_producer` and `spec/graph-artifact/v0-preview.2#holes` on a hole, sending
# a reader who reads both to two editions of one specification over one
# document's own fields. `SCHEMA_URL_TEMPLATE` in `facets.py` deliberately
# does hold still, and the difference is what the two strings point at: that
# one names a facet's own schema, which did not move, and this one names the
# section of this document that says what closes a hole.
_HOLE_CLOSES_WITH: Final[str] = (
    "https://gaspatchio.dev/spec/graph-artifact/v0-preview.3#holes"
)

# RFC 3339 in UTC, with the Z designator and no numeric offset, so that two
# artifacts' timestamps compare as written.
_TIMESTAMP_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%SZ"

# The facet carrying the engine's own rendering of a node's calculation, and
# the engine that rendering is written in. It is a debugging convenience with
# no normative force: a consumer holding both it and `formula` reads
# `formula` as authoritative, which is why it is never announced as required.
_LOWERED_FACET: Final[str] = "gaspatchio_lowered"
_LOWERED_ENGINE: Final[str] = "polars"

# The facet carrying how each of a node's reads was narrowed. The core edge
# states the relationship -- whether the value flowed into the answer or only
# decided which values did -- because that is the distinction an impact cone
# is drawn through. The narrowing beside it changes no answer, so it is
# announced and never required: a consumer that has never met this name reads
# the same graph, with the same relationships.
#
# It hangs on the node that did the reading because section 6 puts facets in
# exactly two places, the envelope and a node, and an edge is neither. The
# node's own `reads` list is the index -- section 9 writes one edge per entry
# of it, in its order -- so the two are one list read twice rather than two
# lists to reconcile.
_COLUMN_TRANSFORMATION_FACET: Final[str] = "gaspatchio_column_transformation"

# The operations whose stated configuration goes onto the node as ``settings``.
# Both are accumulations, and what each one holds is a timing convention: the
# first question an actuary puts to a survival curve is whether it is
# beginning-of-period or end-of-period, and to a prospective value whether the
# current period's cashflow is discounted. The figures alone do not say which
# convention a column was written under, and a flat-rate test can pass a model
# converted wrongly between the two, so the answer has to be on the record.
#
# Two identifiers rather than every call carrying an attribute. An attribute is
# a call's own configuration and belongs to the operation tree; what these two
# hold is a convention read before the arithmetic is, and section 8 states the
# rule under which another identifier joins them.
_SETTINGS_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"projection.cumulative_survival", "projection.prospective_value"}
)

# How many policies an axis has to carry before a node's enrichment is
# written as an array along it. One policy writes the value itself, exactly
# as the edition before the axis existed wrote it, which is what makes a
# single-policy document byte for byte what it always was.
_AXIS_IS_PLURAL: Final[int] = 2

# The one enrichment member that is a mapping of values rather than a value.
# The axis goes inside it, key by key; ``_movements_along_the_axis`` says why.
_MOVEMENTS: Final[str] = "movements"

# How large an assumption's inlined values may be before the entry stands in
# for them instead. One mebibyte, and the number is a working limit rather
# than a property of the format: it is where a table stops being something a
# repository can hold a copy of per run and starts being a file that belongs
# beside the model (*Optimize for the laptop*). A caller who wants the values
# whatever they weigh lifts it; a caller committing the artifact leaves it
# where it is.
TABLE_PAYLOAD_LIMIT: Final[int] = 1_048_576

# The three reasons a value this document defines was left out, and they are
# three because they are three different sentences to a reader. ``size`` is a
# value this producer holds, weighed, and declined to carry, so the weight
# beside it says what fetching it would cost. ``unavailable`` is a value this
# producer read the identity of and cannot vouch for now -- a base built in
# another process, one that has moved off the identity the formula read it
# under, a file the process can no longer read -- and there is nothing to
# weigh, so nothing is weighed. ``withheld`` is a value this producer could
# have carried and was asked not to: a disclosure decision, taken by whoever
# ran the export, and recorded rather than left as a silence. Writing ``size``
# on either of the other two would state a reason that is false and, on
# ``unavailable``, a measurement nobody made.
_OMITTED_FOR_SIZE: Final[str] = "size"
_OMITTED_UNAVAILABLE: Final[str] = "unavailable"
_OMITTED_WITHHELD: Final[str] = "withheld"

# The member a source entry's payload carries its file's text in. Named once,
# because the call that weighs a payload, the one that files it beside a
# document and the one that writes it into the document have to spell it the
# same way, and a second literal is a second thing to keep in step.
_SOURCE_TEXT_FIELD: Final[str] = "text"

# How an inlined payload is written into the document, and therefore how one
# that is not inlined is weighed. The two have to be the same serialisation or
# the count is not the file's truth.
_DOCUMENT_INDENT: Final[int] = 2

# The envelope member that seals the document as a written record. Named once,
# because the producer that writes it and the reader that lifts it back out
# before recomputing have to agree on the spelling exactly, and a second
# literal is a second thing to keep in step.
DOCUMENT_DIGEST_FIELD: Final[str] = "document_digest"

# Where an identities-only export puts the document, and where it puts the
# values that document names but does not carry. The directory is the
# envelope section's own name, so a reader who has met the document knows
# what is in the folder beside it without being told.
ARTIFACT_FILE_NAME: Final[str] = "artifact.json"
PAYLOAD_DIRECTORY: Final[str] = "assumptions"

# And where it puts the model's own text, for the same reason under the same
# rule: the folder is the section's own name. A model's source filed among
# the rate tables would be exactly the confusion section 7.3 keeps out of the
# assumptions directory in the first place -- a consumer looking for the code
# should not have to filter a folder of bases to find it.
SOURCE_DIRECTORY: Final[str] = "sources"

# Whether a document is sealed unless the caller says otherwise.
#
# True from `gaspatchio-graph/v0-preview.2`, which is the regeneration that
# moved the byte-grammar token and the schema identifier together: the member
# was defined and optional under `v0-preview.1`, and what landed with the new
# identifier is the emission and, with it, `document_digest` in the schema's
# `required` list. The format's users were owed one loud, documented change to
# what a document carries rather than several quiet ones, and section 14.1
# carries the line.
#
# A caller who wants an unsealed document still has one: `seal=False` writes
# no member, which is the shape a holder legitimately transforming a document
# needs -- section 13.1's fourth limit -- and what a document valid under the
# earlier identifier looked like.
SEAL_BY_DEFAULT: Final[bool] = True


def document_digest_of(document: dict[str, Any]) -> str:
    """Return the seal over ``document`` -- the record, not the calculation.

    The identity chain answers "is this the same calculation?" and cannot
    answer "is this the file the producer wrote?": ``formula`` is no part of
    any node's canonical bytes, so a quotation edited after the artifact was
    written leaves every fingerprint valid and every deep check on them clean.
    That exclusion is right -- an identity moves when the computation moves
    and at no other time -- and this is the other question, asked separately.

    **The bytes are the specification's own recipe grammar**, the one
    ``source_sha`` is taken under, applied to the document rather than to a
    recipe. There is no second canon: this member is lifted out, nothing else
    is, and what is left is encoded with its keys sorted at every level, no
    insignificant whitespace, every non-ASCII character escaped, and the
    non-finite float tokens refused rather than written. A consumer holding
    the specification and the standard library of its language reaches the
    same digest with no library in common with the producer.

    **``created_at`` is inside it, deliberately.** A seal over a written
    record includes when it was written, so two exports of an untouched model
    carry two seals and one ``graph_fingerprint`` -- which is the difference
    between the two questions stated in the two fields.

    Args:
        document: The artifact, as a parsed document or as this module built
            it. A ``document_digest`` already on it is excluded rather than
            refused, so re-sealing an edited document and checking a stored
            one run through one function.

    Returns:
        The seal, as ``sha256:`` and sixty-four hex digits.

    Raises:
        ValueError: If the document holds a non-finite float. Such a value is
            outside the JSON grammar and outside the recipe grammar alike, so
            there is nothing to seal rather than a seal to be taken carefully.
        TypeError: If the document holds a value no JSON encoding names.

    Examples:
        >>> from gaspatchio.frame.graph import SCHEMA_ID, document_digest_of
        >>> one = {"schema": SCHEMA_ID, "nodes": []}
        >>> document_digest_of(one) == document_digest_of(
        ...     {"nodes": [], "schema": SCHEMA_ID}
        ... )
        True
        >>> document_digest_of(one).startswith("sha256:")
        True

    """
    sealed = {
        name: value for name, value in document.items() if name != DOCUMENT_DIGEST_FIELD
    }
    return source_sha_of(sealed)


def _hole_entry(hole: Hole) -> dict[str, str]:
    """Return one entry of the holes section (section 7.1).

    ``content`` is written only where the hole carries a stamp -- the frame
    arrived holding the column -- so a hole the producer holds no values
    for is written exactly as before, and the member's absence says so.
    """
    entry = {"column": hole.column, "reason": hole.reason}
    if hole.content is not None:
        entry["content"] = hole.content
    entry["closes_with"] = _HOLE_CLOSES_WITH
    return entry


def _relative_to_source_root(location: str | None, root: Path | None) -> str | None:
    """Return ``location`` written against ``root`` rather than against a disk.

    ``source_location`` is ``<absolute path>:<line>`` on whichever machine ran
    the model. A document published for other people to read wants where in a
    repository the model is written; whose disk it was read off is not a fact
    about the model, and two runs of one model on two machines should not
    differ in it.

    Four kinds of location, placed by :func:`_placed`: a file under the root
    is written relative to it, and one outside it with ``..`` segments; a
    file under the producer's temporary directory, where the root is not, is
    named by its file name alone; and a location that names no file -- a
    notebook cell's ``Jupyter Cell 3`` -- is written as it was recorded. Left
    exactly as it stands where ``root`` is None and where the location is
    None.
    """
    if root is None or location is None:
        return location
    path, _, line = location.rpartition(":")
    return f"{_placed(path, root)[0]}:{line}"


def _names_a_file(path: str) -> bool:
    """Return whether a location's file part is a path on a disk.

    A path is absolute, or has a directory in it. A bare name is how a
    location that is not a file is written -- ``Jupyter Cell 3`` for a
    notebook cell, ``<string>`` for compiled text -- and it is not moved.
    """
    written = PurePath(path)
    return written.is_absolute() or len(written.parts) > 1


def _placed(path: str, root: Path | None) -> tuple[str, bool]:
    """Return how a location's file is written, and whether it is under the root.

    **Under the root**, a file is written relative to it, which is what makes
    a node's location a path anybody holding the root resolves.

    **A location that names no file is written as it was recorded.** A
    notebook cell reports ``Jupyter Cell 3``, which is a place and not a path:
    written against a root it became ``models/Jupyter Cell 3``, a file nobody
    wrote.

    **A file outside the root keeps its ``..`` segments** (section 7): a
    helper module in a sibling directory of the checkout,
    ``../shared/helpers.py``, resolves for anybody with that layout. A file
    whose only climb reaches the filesystem's root is written as its name
    under ``<outside the model's root>`` instead, since that climb would name
    the machine's own directories (:func:`relative_to_root`). The root is the
    width of what the document speaks for, so neither file's text is read,
    and its sources entry says so.

    **A file under the producer's temporary directory, where the root is
    not, is named by its file name in angle brackets** -- ``<cell.py>`` -- the
    spelling Python itself uses for code with no file a reader can open. A
    notebook kernel keeps each cell in such a file, and written as a climb it
    became ``../../../../var/folders/...``: an absolute path spelled
    relatively, which names the exporting machine and resolves for nobody.
    Where the root is itself under the temporary directory, a climb to a
    sibling stays inside it and keeps its ``..`` segments like any other.

    Args:
        path: The location's file part, as the interpreter recorded it.
        root: The directory the document's paths are written against, or
            None where there is none.

    Returns:
        The file as the document writes it, and whether that file is one the
        document may read -- under the root, or with no root to be under.

    """
    if root is None or not _names_a_file(path):
        return path, True
    written = relative_to_root(path, root)
    if not _outside(written):
        return written, True
    if _a_temporary_file_beside_a_lasting_root(path, root):
        return f"<{PurePath(path).name}>", False
    return written, False


def _a_temporary_file_beside_a_lasting_root(path: str, root: Path) -> bool:
    """Return whether a file is under the temporary directory and the root is not.

    The temporary directory is resolved, so that ``/var/folders`` and
    ``/private/var/folders`` are one directory on macOS.
    """
    temporary = Path(tempfile.gettempdir()).resolve()
    return Path(path).resolve().is_relative_to(
        temporary
    ) and not root.resolve().is_relative_to(temporary)


def build_artifact(  # noqa: PLR0913 — one parameter per thing the caller may say about the document; folding them into a config object would rename the list rather than shorten it
    graph: CalcGraph,
    *,
    config: GraphExportConfig | None = None,
    profile: str = PROFILE_AUDIT,
    values_from: pl.DataFrame | None = None,
    include_lowered: bool = False,
    include_tables: bool | Literal["all"] = True,
    include_source: bool = True,
    source_root: Path | str | None = None,
    table_payload_limit: int | None = TABLE_PAYLOAD_LIMIT,
    seal: bool = SEAL_BY_DEFAULT,
    samples: Sequence[Mapping[NodeId, Mapping[str, Any]]] | None = None,
    book: pl.DataFrame | pl.LazyFrame | None = None,
    book_left_to_the_engine: bool = False,
    book_taken: Mapping[str, Any] | None = None,
    versions: Mapping[str, str] | Literal["withheld"] | None = None,
) -> dict[str, Any]:
    """Return ``graph`` as a conforming artifact, envelope and all.

    Args:
        graph: The folded calculation graph. Its nodes are stamped with their
            content identities on the way through, since an artifact whose
            identity fields were empty could not answer the one question the
            format exists for.
        config: What the caller knows about the run -- which model this is an
            account of above all. None exports a version block of nulls;
            ``ModelIdentity.of(model_file)`` fills one in from the files.
        profile: Which conformance profile the artifact claims.
            :data:`PROFILE_AUDIT` is the envelope, the node record, the edges
            and the identity fields. :data:`PROFILE_EXECUTABLE` is that same
            document with the operation tree of every node that has one
            written onto it, under ``expr`` -- a leaf carries none -- and a
            compiled rollforward's own state machine in the envelope's
            facets. The trees are what another engine runs the model from,
            and they are not yet a stable interface: until the format's
            first stable version their shape may change between releases.
        values_from: The frame the nodes' value samples were read out of,
            after any filter was applied. What makes the enrichment context
            checkable rather than merely stated: which policy a sample came
            from is a fact about that frame and nothing else.
        include_lowered: Whether every node that has one carries the engine's
            own rendering of its calculation, in the ``gaspatchio_lowered``
            facet. Off by default: that text moves whenever the engine
            changes how it prints an expression, and a base artifact that
            churns on it is one nobody can compare quarter to quarter. It is
            what a reader chasing a number asks for, and it never displaces
            the as-written formula beside it.
        include_tables: Whether each assumption entry carries the base's own
            values. True inlines everything at or under
            ``table_payload_limit`` and stands in for what is above it;
            ``"all"`` inlines regardless of weight; False stands in for every
            one of them, keeping the identities and dropping the values.
            **Both settings govern all three kinds of entry** -- a schedule's
            and a curve's canonical form are inlined, weighed and stood in for
            on exactly the terms a table's values are. The name says "tables"
            because a table is the entry whose values run to megabytes; it
            does not say the others are exempt. **It governs the sources
            section too**, for the same reason and on the same terms: a
            model's own text is a value this document carries inline, weighed
            and stood in for under one rule rather than two.
        include_source: Whether the model's own text travels in the document,
            one entry per file its nodes were written in (section 7.3). True
            by default: a reader following a node to
            ``model.py:520`` can then read line 520, and a file that discloses
            the calculation and withholds the code around it is a file that
            answers half the question. False writes every entry with
            ``{"omitted": "withheld"}`` -- the path and the fingerprint still
            travel, so a reader knows what was left out and can check a copy
            of their own against it. Leaving the text out is a decision the
            document records, never a silence::

                exporter.export()  # the model's source travels
                exporter.export(include_source=False)  # paths and digests only

        table_payload_limit: How many bytes an inlined payload may weigh,
            measured in the serialisation this document is written in. None
            lifts the guard, which for these entries is what ``"all"`` says.
            Ignored where ``include_tables`` has already settled the question.
        source_root: The directory every ``source_location`` is written
            relative to. None takes the root of ``config.model`` where
            :meth:`ModelIdentity.of` made it -- the directory the block's own
            paths were written against -- and otherwise writes the absolute
            path the model was read from, which is what a run on one machine
            wants. A published document wants a root: where in a repository
            the model is written is a fact about the model, and whose disk it
            was read off is not, so two runs of one model on two machines
            differ in nothing. A location outside the root is written with
            ``..`` segments rather than left absolute, except one in a file
            under the producer's temporary directory where the root is not
            -- a notebook kernel's cell file -- which is written as the
            file's name in angle brackets, ``<cell.py>``, since a climb to it
            names the machine; a location that names no file, such as a
            notebook cell's ``Jupyter Cell 3``, is written as it was
            recorded. A root naming another directory than the identity's is
            refused, so one document never carries two.
            **The rewrite happens before the
            seal is taken**, which is why it is a producer setting rather
            than something a publishing script does afterwards: a document
            edited after export is a document whose seal describes a file
            nobody holds, and section 13.1's fourth limit says what a holder
            who must transform one does instead.
        seal: Whether the finished document carries ``document_digest``, the
            hash over its own canonical serialization that says whether this
            is the file the producer wrote (:func:`document_digest_of`). On
            by default, because the format requires it -- see
            :data:`SEAL_BY_DEFAULT` -- and ``False`` writes a document
            carrying none, which does not validate until it is sealed.
        samples: What each node held for each policy on the axis, in the
            axis's own order -- one mapping per entry of ``config.policies``,
            keyed by node id and carrying the enrichment fields that entry
            produced. None, or a single entry, writes the enrichment fields
            as a one-policy document always has: the value itself, never an
            array of one. The graph the caller hands over already
            holds the first policy's values, so a one-policy document is
            built from it alone and this parameter only ever adds the rest.
        book: The policy data the model was built over, as the frame was
            handed it. The document records a content digest of the columns
            of it the model reads (:func:`book_of`), so a comparison of two
            documents can say whether they were built over the same book.
            None writes the digest as unavailable: a graph with no data
            beside it has no book to vouch for.
        book_left_to_the_engine: Whether the document is built to be handed
            to an engine in this process rather than filed. The engine
            digests the inputs it is handed into its own result manifest,
            so a digest here would be paid for and never read; the member
            states the columns and the unavailable form, saying the digest
            was left to the engine. Nothing that files a document sets it.
        book_taken: The member an earlier document over this same book
            wrote, whose digest is reused where it names the same columns
            (:func:`book_of`). None takes the digest here.
        versions: What produced the values, written as ``producer.versions``
            in the result manifest's own keys -- the run's own statement,
            where the caller holds one. None states this process's
            (:func:`~gaspatchio.engines._versions.versions_in_this_process`).
            ``"withheld"`` writes section 6.1's withheld form in its place,
            for a document committed as a golden that must not carry one
            machine's strings; it is never the default. Beside the mapping,
            where ``config.model`` names a model file, ``imports`` names each
            installed distribution the model imports, with its version.

    Returns:
        The artifact, ready to serialise. Every member the format defines as
        required is present; several of them are routinely empty, and an empty
        one is a claim rather than an omission. The seal is written last where
        it was asked for, because a seal is taken over a finished record.

    Raises:
        ValueError: If ``profile`` is not one of the two defined profiles,
            if ``versions`` is a string other than ``"withheld"``, if
            ``source_root`` names another directory than the one the model
            identity's paths were written against, or if the profile is
            executable and a step that chose which rows the model values is
            one no replay can apply to the book -- a condition outside the
            core vocabulary, or one over a column the model calculates.

    """
    if profile not in (PROFILE_AUDIT, PROFILE_EXECUTABLE):
        msg = (
            f"{profile!r} is not a conformance profile. An artifact claims "
            f"{PROFILE_AUDIT!r} -- the envelope, the node record, the edges and "
            f"the identity fields -- or {PROFILE_EXECUTABLE!r}, which is audit "
            "plus what a consumer would need to evaluate the model."
        )
        raise ValueError(msg)
    if isinstance(versions, str) and versions != _OMITTED_WITHHELD:
        msg = (
            f"versions={versions!r} is not a setting. Pass the mapping that "
            f"produced the values, None for this process's, or "
            f"{_OMITTED_WITHHELD!r} to record them as withheld."
        )
        raise ValueError(msg)

    config = config or GraphExportConfig()
    root = _document_root(config.model, source_root)
    # The stamp on every node and the one string standing for the whole model
    # are the same digests read twice, so they are taken once. Stamping hands
    # back what it wrote; hashing every operation tree again to reach the
    # model-level answer would be a second pass for nothing.
    prints = stamp_fingerprints(graph)
    ledger = FacetLedger(used=set(), required=set())
    axis = _policy_axis(graph, config, values_from)
    enrichment = _envelope_enrichment(axis)
    # What each node holds along that axis, or nothing where the document
    # carries one policy and the enrichment fields are written exactly as
    # the earlier edition wrote them.
    along_the_axis = _along_the_axis(samples, width=len(axis))
    # The directory of bases and each node's own names come off one walk of
    # the same trees, so a node can never name an entry the section does not
    # carry. A node with no tree -- an arriving column, a hole -- names
    # nothing, which is what the default here says.
    read_by_node = assumptions_read_by_node(graph)
    # How each read was narrowed, gathered off the edges rather than
    # recomputed: the facet is those same classifications written where a
    # reader of one node can see them, and deriving it a second way is what
    # would let the two disagree.
    narrowed_by_node = _narrowings(graph)
    nodes = [
        _wire_node(
            node,
            ledger,
            tier=_tier_of(graph, node),
            expr=_expr_of(graph, node, profile=profile),
            settings=_settings_of(graph, node),
            reads_assumptions=read_by_node.get(node.id, ()),
            narrowings=narrowed_by_node.get(node.id, ()),
            carries_values=enrichment is not None,
            along_the_axis=along_the_axis.get(node.id),
            include_lowered=include_lowered,
        )
        for node in graph.nodes.values()
    ]
    # Read off the nodes before the root is applied, because reading a file
    # needs the path the interpreter recorded and the document carries the
    # path a reader resolves. Both spellings come from one list and one
    # ``relative_to_root``, which is what makes a node's location and the
    # entry it points at the same string rather than two that usually agree.
    located = [
        wired["source_location"]
        for wired in nodes
        if isinstance(wired["source_location"], str)
    ] + [
        written
        for step in graph.selection
        if isinstance(written := source_location(step.source), str)
    ]
    # Before the seal, and before anything reads the document: a location
    # rewritten after the fact is an edit to a sealed record.
    for wired in nodes:
        wired["source_location"] = _relative_to_source_root(
            wired["source_location"], root
        )
    envelope_facets = _envelope_facets(graph, ledger, profile=profile)
    facets_used, facets_required = ledger.as_lists()
    # The steps that chose which rows the model values, each with its
    # predicate, what it read and both its digests, rooted like every other
    # location. Absent where the model selects nothing (section 7.6).
    selection = _selection_section(graph, prints, root)
    if profile == PROFILE_EXECUTABLE and selection:
        # A replay of this document applies the selection to the book before
        # it projects, so a step no replay can apply is refused here, by name,
        # rather than written into a document every engine would then value
        # the wrong policies from -- or refuse only once it held the book.
        cannot = selection_no_replay_can_make(selection, nodes)
        if cannot is not None:
            raise ValueError(cannot)
    if profile == PROFILE_EXECUTABLE:
        _refuse_a_date_keyed_lookup(graph)

    document: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "profile": profile,
        "fingerprint_algorithm": FINGERPRINT_ALGORITHM,
        "producer": _producer(versions, model_file=_model_file(config.model, root)),
        "created_at": datetime.now(UTC).strftime(_TIMESTAMP_FORMAT),
        "model": _model_block(config.model or ModelIdentity()),
        "graph_fingerprint": (
            f"{SHA256_PREFIX}{graph_fingerprint(graph, prints=prints).hex()}"
        ),
        # The same fold over trees with every content digest masked: one
        # figure that moves when a formula does and holds when only a table,
        # a curve, a schedule or a column of handed-over values does.
        "formulas_fingerprint": f"{SHA256_PREFIX}{formulas_fingerprint(graph).hex()}",
        "book": book_of(
            nodes,
            book,
            left_to_the_engine=book_left_to_the_engine,
            taken=book_taken,
            selection=selection,
        ),
        "facets_used": facets_used,
        "facets_required": facets_required,
        "nodes": nodes,
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "relationship": edge.relationship,
            }
            for edge in graph.edges
        ],
        "assumptions": [
            _assumption_entry(
                reference,
                root=root,
                include_tables=include_tables,
                table_payload_limit=table_payload_limit,
            )
            for reference in artefacts_read(graph)
        ],
        "holes": [_hole_entry(hole) for hole in holes_in(graph)],
        "boundaries": [
            {
                "ordinal": ordinal,
                "position": boundary.position,
                "source_location": _relative_to_source_root(
                    source_location(boundary.source), root
                ),
            }
            for ordinal, boundary in enumerate(graph.boundaries)
        ],
        "sources": _sources_section(
            located,
            root=root,
            include_source=include_source,
            include_tables=include_tables,
            table_payload_limit=table_payload_limit,
        ),
        "enrichment": enrichment,
        "policies": axis,
        "facets": envelope_facets,
    }
    if selection:
        document[SELECTION_MEMBER] = selection
    if seal:
        # Last, and after everything else: the seal is over the finished
        # record, and a digest taken over a document still being written
        # would be a digest of a document nobody holds.
        try:
            document[DOCUMENT_DIGEST_FIELD] = document_digest_of(document)
        except ValueError as refused:
            raise refusal_for_a_number_json_cannot_hold(document, refused) from refused
    return document


# The enrichment fields that run along the policy axis: on a document
# carrying more than one evaluation context, the first index into each is the
# position of the context it was read under.
_ALONG_THE_POLICY_AXIS: Final[frozenset[str]] = frozenset(
    {"value_sample", "trace", "branches"}
)


def refusal_for_a_number_json_cannot_hold(
    document: dict[str, Any], refused: ValueError
) -> ValueError:
    """Return the refusal naming where a NaN or an infinity was left unspelled.

    Every value this producer writes spells a non-finite float as section
    10's sentinel, so a document still holding one is a path that did not,
    and the encoder's own sentence -- "Out of range float values are not
    JSON compliant: inf" -- names neither the calculation nor the policy.
    This reads the document once more to find the first such number and
    names the node, the field, the position inside it and, on a document
    carrying several evaluation contexts, which policy or scenario it
    belongs to. Any other refusal is handed back as it came.
    """
    where = _where_a_number_json_cannot_hold(document)
    if where is None:
        return refused
    return ValueError(
        f"The calculation graph cannot be written: {where} holds a NaN or "
        "an infinity that was not written as the string section 10 of the "
        'format spells it in ("NaN", "Infinity", "-Infinity"), and JSON has '
        "no number for one. The model's numbers are not at fault; the "
        "exporter missed a value on this path, so report it with this "
        "message. Until then, export without that column, or bound it where "
        "it leaves the finite range (when(...).then(...).otherwise(...)). "
        f"The encoder said: {refused}"
    )


def _where_a_number_json_cannot_hold(document: dict[str, Any]) -> str | None:
    """Return where the first non-finite float in ``document`` sits, in words."""
    contexts = document.get("policies") or []
    for node in document.get("nodes") or []:
        for field, value in node.items():
            path = _first_non_finite(value)
            if path is None:
                continue
            where = f"node {node.get('id')!r}, {field}{_indexed(path)}"
            if (
                len(contexts) > 1
                and field in _ALONG_THE_POLICY_AXIS
                and path
                and isinstance(path[0], int)
                and path[0] < len(contexts)
            ):
                context = _context(contexts[path[0]])
                where += f" (entry {path[0]} of the policy axis: {context})"
            return where
    for field, value in document.items():
        if field == "nodes":
            continue
        path = _first_non_finite(value)
        if path is not None:
            return f"the envelope's {field}{_indexed(path)}"
    return None


def _first_non_finite(value: object) -> list[int | str] | None:
    """Return the path to the first non-finite float inside ``value``, or None."""
    if isinstance(value, float):
        return None if math.isfinite(value) else []
    items: list[tuple[int | str, object]]
    if isinstance(value, list):
        items = list(enumerate(value))
    elif isinstance(value, dict):
        items = list(value.items())
    else:
        return None
    for key, item in items:
        path = _first_non_finite(item)
        if path is not None:
            return [key, *path]
    return None


def _indexed(path: list[int | str]) -> str:
    """Return a path written the way a reader indexes the parsed document."""
    return "".join(f"[{step!r}]" for step in path)


def _context(entry: object) -> str:
    """Return one evaluation context as the axis itself describes it."""
    if not isinstance(entry, dict):
        return repr(entry)
    why = entry.get("why")
    if isinstance(why, str) and why:
        return why
    return f"policy {entry.get('policy_id')!r}"


# What stands in for the book's digest where the producer could not take one:
# section 6.1's form, with the one reason that applies. The producer held no
# book, or the content grammar or the reader refused the one it held; which
# of the two, and what the refusal said, is the form's ``detail``, so a
# comparison that cannot read the book can say why rather than only that.
_BOOK_UNAVAILABLE: Final[str] = "unavailable"

# The sentence a document written with no book beside it carries.
_NO_BOOK: Final[str] = (
    "No book was handed to the export: the graph was written from its "
    "calculations alone, with no policy data beside it."
)

# The sentence a document built to hand to an engine carries in its place.
_LEFT_TO_THE_ENGINE: Final[str] = (
    "Left to the engine this document was built to be handed to, which "
    "digests the inputs it runs over into its own result manifest."
)


def _unavailable(detail: str) -> dict[str, str]:
    """Return section 6.1's ``unavailable`` form for the book, saying why."""
    return {"omitted": _BOOK_UNAVAILABLE, "detail": detail}


def _first_sentence(refused: Exception) -> str:
    """Return the opening sentence of a refusal, for a document to carry.

    A refusal's first sentence names what was met -- the column and its type,
    the file that could not be read -- and what follows is advice for the
    person at the keyboard, or a query plan, neither of which a document
    filed for a decade should carry.
    """
    said = str(refused).strip()
    line = said.splitlines()[0].strip() if said else type(refused).__name__
    end = line.find(". ")
    return line if end < 0 else line[: end + 1]


def book_columns(
    nodes: Iterable[Mapping[str, Any]],
    selection: Iterable[Mapping[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Return the columns of the book the model reads, in name order.

    The book is the policy data the model was run over, and the part of it
    that counts is the part the model's answers can depend on: every column
    the data arrived with that the finished frame holds, or that some line of
    the model reads on the way to a column the finished frame holds. A column
    the model neither reads nor hands back cannot move a number, so a revised
    book that differs only there is the same book as far as the model is
    concerned.

    **A step that chose which rows the model values reads the book too.** The
    columns a selection's predicate reads -- back through what each one reads,
    to the columns that arrived -- are in, whether or not the finished frame
    still holds them: an in-force flag the model filters on and then drops
    decides which policies were valued, and a book revised there is another
    valuation.

    These are the required inputs an engine is handed when it runs the
    document -- reached from every node the finished frame holds and every
    selection step, back through what each one reads -- so the digest over
    them is the digest an engine's result manifest records when the engine is
    handed the book itself, and the two can be compared. An engine handed the
    book crossed with a scenario axis, or filtered, records a digest of what
    it was handed instead.

    Args:
        nodes: The document's node records, as the artifact writes them.
        selection: The document's ``selection`` entries, or None where it
            carries none.

    Returns:
        The column names, sorted, each once.

    """
    by_id = {str(node["id"]): node for node in nodes if "id" in node}
    pending = [
        node_id for node_id, node in by_id.items() if node.get("in_final_schema")
    ]
    for step in selection or ():
        pending.extend(str(read) for read in step.get("reads") or ())
    reached: set[str] = set()
    while pending:
        node_id = pending.pop()
        if node_id in reached or node_id not in by_id:
            continue
        reached.add(node_id)
        pending.extend(str(read) for read in by_id[node_id].get("reads") or ())
    return tuple(
        sorted(
            {
                column
                for node_id in reached
                if by_id[node_id].get("kind") == NodeType.INPUT.value
                and isinstance(column := by_id[node_id].get("column"), str)
            }
        )
    )


def book_of(
    nodes: Iterable[Mapping[str, Any]],
    book: pl.DataFrame | pl.LazyFrame | None,
    *,
    left_to_the_engine: bool = False,
    taken: Mapping[str, Any] | None = None,
    selection: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the ``book`` member: which columns were digested, and the digest.

    The digest is the specification's content grammar (section 12.3) over the
    columns :func:`book_columns` names, in name order, with the rows as the
    book holds them -- the digest a result manifest calls ``inputs_digest``,
    taken by the same function, and equal to it where the engine was handed
    the book itself. It answers "was this built over the same
    book?" from the data itself, never from a file's bytes: two writes of one
    table by two Parquet writers are one book, and one changed premium is
    another.

    A column the book does not hold is left out, and ``columns`` says which
    were digested, so a reader holding the book can take the digest again.
    Where there is no book to read -- a graph exported from nothing but its
    calculations -- or the grammar or the reader refuses the one there is,
    the digest is written as ``{"omitted": "unavailable", "detail": ...}``:
    the document says it could not vouch for its book rather than naming a
    digest of nothing, and ``detail`` says why -- no book was handed over, or
    the opening sentence of the refusal -- so a comparison that cannot read
    the book reports the reason and not only the gap.

    **A document built to be handed to an engine takes no digest.** The
    engine digests the inputs it is handed into its own result manifest,
    which is the record of what it ran over, so a second pass here would be
    time paid for a number nobody reads; ``left_to_the_engine`` writes the
    columns and the unavailable form saying so.

    **A digest already taken over the same columns of the same book is not
    taken again.** The digest is a function of those two things and nothing
    else, so a command that writes a results file's manifest and then the
    document of the same run -- the manifest names the book too, and is
    written first -- pays for one pass over the book rather than two.

    Args:
        nodes: The document's node records, as the artifact writes them.
        book: The data the model was built over, or None where the caller
            has none to hand.
        left_to_the_engine: Whether the digest is left to the engine the
            document is built to be handed to.
        taken: The member an earlier document over this same book wrote.
            Its digest is reused where its ``columns`` are exactly the
            columns digested here; any other member is ignored, and so is
            one that states no digest.
        selection: The document's ``selection`` entries, whose reads are
            part of the book (:func:`book_columns`).

    Returns:
        The member, ready to write: ``columns`` and ``digest``.

    """
    wanted = list(book_columns(nodes, selection))
    if book is None:
        return {"columns": wanted, "digest": _unavailable(_NO_BOOK)}
    held = set(
        book.collect_schema().names()
        if isinstance(book, pl.LazyFrame)
        else book.columns
    )
    columns = [column for column in wanted if column in held]
    if left_to_the_engine:
        return {"columns": columns, "digest": _unavailable(_LEFT_TO_THE_ENGINE)}
    if taken is not None and taken.get("columns") == columns:
        already = taken.get("digest")
        if isinstance(already, str):
            return {"columns": columns, "digest": already}
    try:
        selected = book.select(columns)
        frame = selected.collect() if isinstance(selected, pl.LazyFrame) else selected
        # A book handed over lazily reaches here with a wide integer column
        # still in its width; its values are in hand now, so it is read as
        # the frame's door reads one whose values it holds (section 10).
        digest = digest_of_inputs(with_integers_as_i64(frame), columns)
    except (pl.exceptions.PolarsError, OSError, ValueError) as refused:
        logger.warning(
            f"The book this model was built over could not be digested ({refused}); "
            "the artifact records its digest as unavailable, and says why."
        )
        detail = f"The book could not be digested: {_first_sentence(refused)}"
        return {"columns": columns, "digest": _unavailable(detail)}
    return {"columns": columns, "digest": digest}


def _selection_section(
    graph: CalcGraph,
    prints: Mapping[NodeId, NodeFingerprints],
    root: Path | None,
) -> list[dict[str, Any]]:
    """Return the document's ``selection`` list: one entry per row-selecting step.

    Each entry carries what a reviewer asks of an in-force definition and
    what a replay needs to make it again: the step's ``id`` and ``kind``, its
    predicate's op-tree under ``expr`` -- in both profiles, because a step has
    no column to show its formula on and the tree is the whole of it --
    its ``tier``, the nodes it ``reads``, both digests (section 7.6), the
    line it was written on and, for a semi or anti join, the right side's
    content identity, which the tree states too. Empty where the model chose
    no rows.
    """
    stamped = selection_fingerprints(
        graph.selection, {node_id: fps.merkle for node_id, fps in prints.items()}
    )
    entries: list[dict[str, Any]] = []
    for step, fps in zip(graph.selection, stamped, strict=True):
        entry: dict[str, Any] = {
            "id": step.id,
            "kind": step.kind,
            "expr": op_node_to_json(step.tree),
            "tier": tier_of(step.tree),
            "reads": list(step.reads),
            "local_fingerprint": f"{SHA256_PREFIX}{fps.local.hex()}",
            "fingerprint": f"{SHA256_PREFIX}{fps.merkle.hex()}",
            "source_location": _relative_to_source_root(
                source_location(step.source), root
            ),
        }
        if step.kind != "filter":
            stated = (
                dict(step.tree.attrs).get("right_fingerprint")
                if isinstance(step.tree, Call)
                else None
            )
            entry["right_fingerprint"] = stated if isinstance(stated, str) else None
        entries.append(entry)
    return entries


def _refuse_a_date_keyed_lookup(graph: CalcGraph) -> None:
    """Refuse an executable record of a lookup keyed by a date-like dimension.

    Section 11.1.24 bounds a lookup to text keys and finite numbers: a date
    or a timestamp is outside the form a consumer evaluates, and must be
    refused by it. The frame answers such a lookup within its kind; a
    document carrying one would be refused by every engine that read it, so
    it is refused here, naming the table and the dimension, rather than
    written.
    """
    from gaspatchio.frame.lowering.artefacts import (  # noqa: PLC0415 — import cycle
        table_by_name,
    )

    for reference in artefacts_read(graph):
        if reference.kind != "table":
            continue
        table = table_by_name(reference.name)
        kinds = {} if table is None else dict(table._key_kinds)  # noqa: SLF001 — the kind the table was built from
        if kinds:
            column, kind = next(iter(kinds.items()))
            msg = (
                f"Table {reference.name!r} is keyed on {column!r} by {kind}, and a "
                "lookup keyed by a date or a timestamp "
                "is outside the executable form (section 11.1.24): every engine "
                "reading the record would refuse it. Key the table by the number "
                "the dates count -- a year, a day count -- or export the audit "
                "profile, which carries no calculation to evaluate."
            )
            raise ValueError(msg)


def _model_block(model: ModelIdentity) -> dict[str, Any]:
    """Return the version block, with each written file dropped where absent.

    Most of the block is required and may be null, because most of it
    answers a question the run asked and could fail to answer: which file,
    at which revision, over which data. ``results`` and ``audit`` answer
    questions the run may never have asked -- each names a file the run
    wrote, and a run asked for neither wrote neither.

    A null there would say the run produced a file the producer could not
    identify, which is a different claim and a false one. So each is absent
    instead, and its presence is itself the statement that the file exists:
    an output file for the numbers in this document to be checked against,
    and a record of the run this document is the other half of.
    """
    block = model.model_dump(mode="json")
    for written in ("results", "audit", "scenarios"):
        if block.get(written) is None:
            block.pop(written, None)
    # Where no model file was named there is no module list to state, and
    # the member is left off rather than written null: a document of a frame
    # exported with no model block says what it said before this member was.
    if block.get("modules") is None:
        block.pop("modules", None)
    return block


def _envelope_facets(
    graph: CalcGraph, ledger: FacetLedger, *, profile: str
) -> dict[str, Any]:
    """Return the facets the artifact carries as a whole rather than per node.

    One of them, and it is where a compiled rollforward's own state machine
    travels: every operation it applies, in the order it applies them, with
    the expressions and the configuration each one takes. It rides in the
    ``executable`` profile and nowhere else, because it is precisely what
    that profile promises over ``audit`` -- what a consumer needs in order
    to evaluate the model rather than only read it.

    It is announced in ``facets_used`` and never in ``facets_required``.
    Nothing in the base record means anything different for its being
    there: the compilation's node carries its identity, what it reads and
    the states it declares either way, so a consumer that does not know
    this facet has lost the recipe rather than the record.

    Args:
        graph: The folded calculation graph, for the compilations it holds.
        ledger: The artifact's facet declarations, so that a facet emitted
            here is announced in the envelope by the same act.
        profile: The conformance profile the artifact claims.

    Returns:
        The envelope's ``facets`` object, empty where the profile carries
        none and where the model compiled no rollforward.
    """
    if profile != PROFILE_EXECUTABLE:
        return {}
    payload = rollforward_ir_for(graph)
    if payload is None:
        return {}
    ledger.record(_ROLLFORWARD_IR_FACET)
    return {_ROLLFORWARD_IR_FACET: facet(_ROLLFORWARD_IR_FACET, payload)}


def _narrowings(graph: CalcGraph) -> dict[NodeId, tuple[dict[str, Any], ...]]:
    """Return how each node's reads were narrowed, keyed by the reading node.

    The classification of a read is two words. The first is what the edge
    itself carries; this is where the second is gathered for the node that
    made the read, so that a reader holding one node can see how it read
    each of the columns it names -- which is the question the narrowing
    answers, and it is a question about a node rather than about the graph.

    Gathered off the edges in the order they were minted, which is the
    order the reading node's own ``reads`` list is in: wherever
    ``graph_builder.py`` mints a node it mints that node's edges in the
    same breath, pairing the two lists entry by entry. So the array this
    returns indexes into ``reads`` positionally as well as by name, and
    neither list is derived from the other --
    ``test_every_shipped_model_indexes_its_narrowings_by_the_reads_they_narrow``
    is where they are held to each other.

    The inner objects are OpenLineage's own, verbatim: ``transformations``
    is its array name, ``type`` and ``subtype`` are its key names, and the
    enum spellings are its own. What is not verbatim is the outer indexing
    -- OpenLineage keys by dataset and field, and this keys by node id,
    because a node id is what this format's edges name. Borrowing the outer
    shape as well would be borrowing a shape that does not fit.

    ``offset`` is this specification's own member beside those two, on the
    reads that have one: which period the value was read at, quoted from
    the operation's own attribute rather than read out of an expression's
    text. :func:`_narrowing` is where a read gets one and where nearly
    every read does not.

    ``periods`` and ``position`` are the other two members of this
    specification's own: which periods a direct read reached, for an
    aggregation, and which stored position a literal ``list.get`` read.
    A ``transformations`` array holds one entry per way a direct read was
    made (``edges.py``): a name read through two windows in one formula
    writes two, strongest narrowing first, and every other read writes
    exactly one -- the single strongest claim its reads support. A
    consumer must not read the count as a promise: the array is
    OpenLineage's, and a producer that classified each read separately
    would write one per read.

    Args:
        graph: The folded calculation graph, for its edge list.

    Returns:
        Each reading node's narrowings, by node id. A node that reads
        nothing is absent rather than present with an empty array -- there
        is no narrowing to state, and an empty array would be the node's
        empty ``reads`` said a second time.
    """
    gathered: dict[NodeId, list[dict[str, Any]]] = {}
    for edge in graph.edges:
        gathered.setdefault(edge.target, []).append(
            {"source": edge.source, "transformations": _transformations(edge)}
        )
    return {target: tuple(reads) for target, reads in gathered.items()}


def _transformations(edge: GraphEdge) -> list[dict[str, Any]]:
    """Return one read's narrowings: one per way it was made, or the one it has."""
    if not edge.ways:
        return [_narrowing(edge)]
    return [_way(edge, way) for way in edge.ways]


def _narrowing(edge: GraphEdge) -> dict[str, Any]:
    """Return one read's narrowing, and the period it was read at where there is one.

    ``offset`` is written beside OpenLineage's two members rather than
    instead of either: it says which period the value came from, and a
    read of the period being computed says so by carrying no ``offset``
    at all. Never a zero and never a null -- a reader meeting one of those
    would have a second and a third shape to recognise for the commonest
    read in any model.
    """
    stated: dict[str, Any] = {"type": edge.relationship, "subtype": edge.subtype}
    if edge.offset is not None:
        stated["offset"] = edge.offset
    return stated


def _way(edge: GraphEdge, way: ReadWay) -> dict[str, Any]:
    """Return one way a direct read was made, with the window it states.

    ``periods`` is ``{"from": ..., "to": ...}``, each bound a whole number
    of periods from the period being computed or ``"first"`` / ``"last"``,
    and ``position`` is the stored position a literal ``list.get`` named --
    both quoted from the operation's own attributes, never from an
    expression's text (section 9). The edge's ``offset`` belongs to its
    transformation, and goes on the way that states no window: the
    windowed ways each state their own periods.
    """
    stated: dict[str, Any] = {"type": edge.relationship, "subtype": way.subtype}
    if way.window is None:
        if way.subtype == edge.subtype and edge.offset is not None:
            stated["offset"] = edge.offset
    elif isinstance(way.window, Periods):
        stated["periods"] = {"from": way.window.start, "to": way.window.end}
    else:
        stated["position"] = way.window.index
    return stated


def payload_bytes(values: dict[str, Any]) -> bytes:
    """Return one assumption payload as its own document.

    The one serialisation of a payload this package writes, and therefore
    the one it measures. An entry that stands in for its values states what
    fetching them would cost, and a file written beside the document holds
    exactly those values -- so the count and the file have to come from the
    same call or the count is a guess about somebody else's serialisation.

    Indented as the document is indented, and ASCII-escaped as the document
    is, because the number is what a reader takes on by asking for the value
    and the value is written the way this producer writes JSON. A non-finite
    float is refused rather than written: the bare tokens Python would emit
    are outside JSON, a strict parser refuses the whole file, and every
    payload that can hold one states it as section 10's string sentinel
    instead. A refusal here is therefore a path nobody has written yet,
    surfacing at the producer rather than at whoever opens the file next
    quarter.

    Args:
        values: One entry's payload -- a table's frame, or a schedule's or a
            curve's canonical form.

    Returns:
        The bytes of that payload written as a standalone JSON document, with
        no trailing newline: the file's content is the value and nothing
        appended to it, so a consumer that re-serialises what it parsed
        reaches the same bytes.

    Raises:
        ValueError: If the payload holds a non-finite float.

    """
    return json.dumps(values, indent=_DOCUMENT_INDENT, allow_nan=False).encode()


def payload_file_name(fingerprint: str) -> str:
    """Return the file one entry's values are stored under, beside the document.

    **The name is the identity, and that is the whole mechanism.** An entry
    already publishes the fingerprint its values hash to (section 13), so a
    file named after that fingerprint needs no pointer in the document to
    find it and no second digest to authenticate it: a consumer fetches the
    name the entry states, re-hashes what comes back under the grammar for
    that kind, and either reaches the name or has been handed the wrong
    file. Two filings whose mortality basis did not move name one file
    between them, which is what turns "did the basis change?" from a diff of
    two payloads into a comparison of two strings.

    The one edit is the colon. A stamped digest is ``sha256:`` and sixty-four
    hex digits, and a colon is legal in a path on some systems, illegal on
    others and reserved in a URI's own grammar -- so it becomes a hyphen and
    the algorithm stays on the face of the name, where a store holding
    digests of two algorithms can never collide two of them into one file.

    Args:
        fingerprint: The entry's ``fingerprint``, as the document states it.

    Returns:
        The file name, relative to :data:`PAYLOAD_DIRECTORY`.

    Examples:
        >>> from gaspatchio.frame.graph import payload_file_name
        >>> payload_file_name("sha256:" + "b9" * 32)[:16]
        'sha256-b9b9b9b9b'

    """
    return f"{fingerprint.replace(':', '-')}.json"


def _assumption_entry(
    reference: ArtefactReference,
    *,
    root: Path | None,
    include_tables: bool | Literal["all"],
    table_payload_limit: int | None,
) -> dict[str, Any]:
    """Return one entry of the assumptions section.

    The values are read once, and they decide two members. ``payload`` is
    the values or the stand-in for them. And a table whose values are left
    out for their size still states its ``roles`` in the stand-in -- the
    ``dimensions``, the ``value`` and the typed ``columns`` the payload would
    have carried, all but the rows -- so a reviewer holding the file can
    still read it as the table: a fingerprint whose columns nobody stated is
    one no file can be checked against. The roles go with the stand-in, so a
    holder putting the values back in its place has the entry the inline
    export writes. A table entry then says where its values were read from
    (:func:`_table_source_entry`).
    """
    values = payload_of(reference)
    payload = _payload_entry(
        values,
        include_tables=include_tables,
        table_payload_limit=table_payload_limit,
    )
    entry: dict[str, Any] = {
        "kind": reference.kind,
        "name": reference.name,
        "fingerprint": reference.fingerprint,
        "payload": payload,
    }
    if reference.kind != "table":
        return entry
    if values is not None and payload.get("omitted") == _OMITTED_FOR_SIZE:
        payload["roles"] = {
            member: values[member] for member in ("dimensions", "value", "columns")
        }
    entry.update(_table_source_entry(reference, root))
    return entry


def _payload_entry(
    values: dict[str, Any] | None,
    *,
    include_tables: bool | Literal["all"],
    table_payload_limit: int | None,
) -> dict[str, Any]:
    """Return one entry's payload: the base's values, or the stand-in for them.

    The values are read and weighed before anything is decided, and weighed
    **the way this document writes them** -- indented, as
    :data:`_DOCUMENT_INDENT` says, and not in the tightest form the encoder
    could manage. The count is what a reader would take on by asking for the
    value, and a number measured under a serialisation the file does not use
    is a guess in the one field whose whole job is to be a measurement: one
    basis weighs several times more indented than it does compact, which is
    not a rounding error in a figure a reader budgets against. Serialising
    twice is the price of that, and it is paid once per base rather than once
    per read.

    **The number is the value written as its own document, not the span it
    would occupy inside this one.** Nesting indents every line again, so the
    same values take more of this file than the figure says -- about a
    quarter more for a schedule's canonical form, half as much again for a
    table of rows, where every cell is a line of its own. That is the right
    measure for what the field is asked, which is what obtaining the value
    elsewhere would cost; it is not an estimate of this file's own size, and
    a reader adding the omitted weights up to predict one will come in low.

    **Where the value is written as its own document, that document is this
    one.** An identities-only export puts each base's values in a file beside
    the artifact, and the file's bytes are :func:`payload_bytes`' bytes --
    the same call this weight is taken over. So the number an entry states is
    the size of the file a reader would fetch, exactly, rather than an
    estimate standing near it.

    An artefact this process cannot reach is not weighed at all, and stands
    in for itself under the reason that says so. The alternative is refusing
    to write the artifact because a dictionary in this interpreter is empty,
    which would lose the entire record of a model to recover one section of
    it -- and the entry still names the base and still carries its identity,
    which is the answer to "what was this run against?" whether or not the
    values came along. What it must not do is borrow the reason next door:
    "left out for its size, nought bytes" is a sentence with a false reason
    and a measurement nobody made, and a reader deciding whether to go and
    find the file is entitled to know which of the two happened.
    """
    if values is None:
        return {"omitted": _OMITTED_UNAVAILABLE}
    weight = len(payload_bytes(values))
    if include_tables is False:
        return {"omitted": _OMITTED_FOR_SIZE, "bytes": weight}
    if (
        include_tables == "all"
        or table_payload_limit is None
        or weight <= table_payload_limit
    ):
        return values
    return {"omitted": _OMITTED_FOR_SIZE, "bytes": weight}


def _table_source_entry(
    reference: ArtefactReference, root: Path | None
) -> dict[str, Any]:
    """Return a table entry's ``source_file`` and ``shaped_by``, or nothing to add.

    The file a table was read from is what a reviewer re-reads it from, so
    the entry names it: written against the document's root as every other
    path is, and by its name alone where the document has no root, since an
    absolute path would name a directory of this machine. A table built from
    a frame names none, and the member is null -- the model built it in its
    own code. ``shaped_by`` says whether the table's own recipe reshaped what
    it read -- a column renamed, melted, computed, set or cast -- each step
    one entry, empty where the processed frame is a plain read of its
    source. Where this process cannot say, both members are left off: a null
    would claim the frame, and a guess at a file would be worse.
    """
    source = table_source_of(reference)
    if source is None:
        return {}
    file = source.file
    return {
        "source_file": (
            None
            if file is None
            else file.name
            if root is None
            else relative_to_root(file, root)
        ),
        "shaped_by": [dict(step) for step in source.shaped_by],
    }


def source_payload_of(path: Path) -> tuple[str, dict[str, str]] | None:
    """Return one model source's identity and its payload, or None where it has none.

    **The digest is over the file's own bytes**, which is the same stamp
    ``model.source_sha`` carries and deliberately not either of section 12.3's
    grammars: a model file is text somebody wrote rather than a frame of
    values or a canonical recipe, and hashing a re-serialisation of it would
    move the identity whenever the reader that parsed it changed. So the
    entry for the model file re-hashes to exactly the digest the envelope
    already publishes beside it, and a page showing the source can say the
    source it shows is the source that ran.

    The text is the file's bytes decoded as UTF-8, which round-trips to those
    same bytes exactly -- so a consumer re-encoding what it read reaches the
    digest, with no rule about line endings and no normalisation on the way
    through. A file this process cannot read, and a file whose bytes are not
    UTF-8 at all, both come back None: there is a path to name and nothing
    the producer can vouch for, which is what ``unavailable`` says.

    Args:
        path: The file a node's ``source_location`` names.

    Returns:
        The digest, as ``sha256:`` and sixty-four hex digits, and the payload
        the document carries -- or None where the file could not be read.

    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    digest = f"{SHA256_PREFIX}{hashlib.sha256(raw).hexdigest()}"
    return digest, {_SOURCE_TEXT_FIELD: text}


def _outside(written: str) -> bool:
    """Return whether a path written against a root leaves that root.

    ``..`` segments are how :func:`relative_to_root` keeps a file beside the
    tree the document is published from, and a name under
    ``<outside the model's root>`` how it keeps one whose climb would reach
    the filesystem's root. Either way the file is not under the root, and the
    root is the width of what an artifact speaks for.
    """
    return lies_outside_the_root(written)


def _source_entry(  # noqa: PLR0913 — one parameter per thing the caller may say about this entry; the same list :func:`_payload_entry` takes, plus the two a file has that a base does not
    location: str,
    written: str,
    *,
    include_source: bool,
    include_tables: bool | Literal["all"],
    table_payload_limit: int | None,
    readable: bool,
) -> dict[str, Any]:
    """Return one entry of the sources section: the file's text, or a stand-in.

    The path travels whatever happens to the text, because the path is what a
    reader follows back to the file and the question "which files did this
    model's calculations come out of?" is answered by the section being
    complete rather than by every entry carrying bytes.

    **Only what is under the root.** A location resolving outside the model
    root is named with its ``..`` segments -- or, for a file in the
    producer's temporary directory, by its file name in angle brackets
    (:func:`_placed`) -- and read no further: the root is
    the width of what an artifact speaks for (section 7), and a producer that
    reached past it would be publishing a file from a tree the document does
    not account for and cannot be resolved against. That is `unavailable` --
    there is a path here whose contents this document does not vouch for --
    and the same is true of a file the process can no longer read, or one
    whose bytes are not text at all. Neither was weighed, so neither claims a
    weight, and neither claims a digest: an identity nobody took is not an
    identity to publish.

    **Withheld is a decision, and it is recorded as one.** Where the caller
    declined to disclose the text, the path and the digest still travel, so a
    reader knows what was left out and can check a copy they hold against it.
    ``size`` would be a lie there -- the values were not too large, they were
    not offered -- and a silence would be worse than either, because a section
    that quietly skipped an entry would say the model had one file fewer.

    The guard above that is the table's, unchanged: a source over the inline
    budget stands in for itself with its weight beside it, and the sidecar
    door files the text in a file named after this entry's own fingerprint.
    """
    unreachable = {
        "path": written,
        "fingerprint": None,
        "payload": {"omitted": _OMITTED_UNAVAILABLE},
    }
    if not readable:
        return unreachable
    found = source_payload_of(Path(location))
    if found is None:
        return unreachable
    digest, values = found
    return {
        "path": written,
        "fingerprint": digest,
        "payload": _payload_entry_for_source(
            values,
            include_source=include_source,
            include_tables=include_tables,
            table_payload_limit=table_payload_limit,
        ),
    }


def _payload_entry_for_source(
    values: dict[str, str],
    *,
    include_source: bool,
    include_tables: bool | Literal["all"],
    table_payload_limit: int | None,
) -> dict[str, Any]:
    """Return a readable source's payload: its text, or the stand-in for it.

    Weighed the way :func:`_payload_entry` weighs a base's values, and for the
    same reason: the number an entry states is the size of the file a reader
    would fetch, exactly, because it is taken over the very call that writes
    that file (:func:`payload_bytes`). It is larger than the file on disk --
    JSON escapes every newline and every quote in the text -- which is the
    right measure for what the field is asked.
    """
    if not include_source:
        return {"omitted": _OMITTED_WITHHELD}
    weight = len(payload_bytes(values))
    if include_tables is False:
        return {"omitted": _OMITTED_FOR_SIZE, "bytes": weight}
    if (
        include_tables == "all"
        or table_payload_limit is None
        or weight <= table_payload_limit
    ):
        return dict(values)
    return {"omitted": _OMITTED_FOR_SIZE, "bytes": weight}


def _sources_section(
    locations: Sequence[str],
    *,
    root: Path | None,
    include_source: bool,
    include_tables: bool | Literal["all"],
    table_payload_limit: int | None,
) -> list[dict[str, Any]]:
    """Return the model's own source, one entry per file its nodes were written in.

    The section is built from the locations the nodes already carry, and from
    nothing else. A file a node names is a file some calculation in this
    document was written in; a file nobody names is not part of this account,
    however near it sits on the disk. So the section can neither miss a file a
    reader will meet in a ``source_location`` nor invent one they will not.

    **The paths are the same strings the nodes carry**, by construction rather
    than by coincidence: both are ``relative_to_root`` over the same location
    against the same root, which is why a reader who has followed a node to
    ``model.py:520`` finds ``model.py`` here and not some second spelling of
    it. Ordered by that path, so two exports of one model compare as written.

    Args:
        locations: Every node's ``source_location``, as it stands before the
            root is applied -- the file and the line, absolute or as the
            interpreter recorded it.
        root: The directory every path in this document is written against,
            or None where the producer was given none and the locations
            travel as they stand.
        include_source: Whether the text travels at all.
        include_tables: The inline setting, which governs a source's text
            exactly as it governs a base's values.
        table_payload_limit: The inline budget, likewise.

    Returns:
        One entry per distinct path, ordered by it.

    """
    entries: dict[str, dict[str, Any]] = {}
    for location in locations:
        path = location.rpartition(":")[0]
        if not path:
            continue
        written, readable = _placed(path, root)
        if written in entries:
            continue
        entries[written] = _source_entry(
            path,
            written,
            include_source=include_source,
            include_tables=include_tables,
            table_payload_limit=table_payload_limit,
            readable=readable,
        )
    return [entries[written] for written in sorted(entries)]


def _producer(
    versions: Mapping[str, str] | Literal["withheld"] | None,
    *,
    model_file: Path | None,
) -> dict[str, Any]:
    """Return what wrote the document, and what produced the values it carries.

    ``name`` and ``version`` say which package wrote the file. ``versions``
    says what the numbers rest on -- the core and its compiled extension,
    each by its own version, the extension by its digest, Polars, Python and
    the platform -- because the package's version alone cannot tell an
    editable install over an older extension from a release, and a reviewer
    asking whether this library would give the same number needs all of it.
    ``imports`` beside them names each installed distribution the model
    imports, read off its import statements and its helpers', with the
    version installed here; it is absent where no model file is named.

    Withheld, the member is section 6.1's form, a decision the file records
    rather than a silence.
    """
    stated: dict[str, Any] = {"name": _PRODUCER_NAME, "version": _producer_version()}
    if isinstance(versions, str):
        stated[_PRODUCER_VERSIONS] = {"omitted": _OMITTED_WITHHELD}
        return stated
    produced: dict[str, Any] = dict(
        versions_in_this_process() if versions is None else versions
    )
    if model_file is not None:
        produced[_PRODUCER_IMPORTS] = installed_versions(
            imported_from_outside(model_file)
        )
    stated[_PRODUCER_VERSIONS] = produced
    return stated


def _model_file(model: ModelIdentity | None, root: Path | None) -> Path | None:
    """Return the model file the identity names, where this process can reach it.

    ``source_path`` is written against the document's root, so the file is
    that root joined to it; an absolute one, written where there was no root,
    is the file itself. None where the identity names no source, or the file
    is not there to read.
    """
    if model is None or model.source_path is None:
        return None
    named = Path(model.source_path)
    if not named.is_absolute():
        if root is None:
            return None
        named = root / named
    return named if named.is_file() else None


def _producer_version() -> str:
    """Return the installed package's version, or ``"unknown"`` where it has none.

    A source checkout that was never installed has no distribution metadata to
    read. Saying "unknown" is the honest answer; inventing a number would put
    a version on an artifact that no release ever produced.
    """
    try:
        return version(_PRODUCER_NAME)
    except PackageNotFoundError:
        return "unknown"


def _tree_of(graph: CalcGraph, node: GraphNode) -> OpNode | None:
    """Return the operation tree behind ``node``, or None where it has none.

    Two fields are read off one tree -- the tier and the ``expr`` -- so
    which kinds have one, and what happens to a node that should and does
    not, are decided here rather than twice. Deciding it twice is how the
    two come to disagree, and the disagreement would be invisible: whichever
    of them the caller happened to build first would settle what the file
    said about the node, and nothing pins that order.

    A leaf has nothing behind it. A column that arrived with the data, a
    column of values handed over wholesale, a column nothing accounts for
    and one running state of a compiled rollforward are all one of two
    things -- data, or an absence -- and a tree on any of them would answer
    a question that was never put to it.

    Every kind answers here deliberately, and the walk ends in
    ``assert_never`` for the same reason ``tiers.py``'s does: a kind added
    to the vocabulary without a decision about whether it carries a tree
    fails the type checkers, rather than being absorbed into "nothing to
    read" by a condition that happened to be written the other way round.

    Raises:
        ValueError: If a node that computes has none. A fold that lost a
            tree is not a node with nothing to say, and answering softly
            would write the calculation into the file with no account of
            how it is made and a tier claiming there is nothing to account
            for.

    """
    match node.kind:
        case NodeType.INPUT | NodeType.HOLE | NodeType.STATE:
            return None
        case NodeType.COMPUTED | NodeType.ROLLFORWARD:
            tree = graph.op_trees.get(node.id)
            if tree is None:
                msg = (
                    f"{node.id!r} is a {node.kind.value!r} node with no "
                    "operation tree behind it. A column the data arrived "
                    "with, a column nothing accounts for and a running "
                    "rollforward state have nothing to execute; every other "
                    "kind was folded from a tree, and one arriving here "
                    "without one is a fold that lost it. Fold the frame "
                    "again rather than exporting from this graph."
                )
                raise ValueError(msg)
            return tree
        case _ as unreachable:
            assert_never(unreachable)


def _tier_of(graph: CalcGraph, node: GraphNode) -> OpTier | None:
    """Return how much of ``node`` the format can account for, or None on a leaf.

    A leaf has nothing to execute, so there is no tier on one: the question
    is what it costs a consumer to evaluate this node, and it was never put
    to a column that arrived with the data.

    A compiled rollforward has plenty to execute and says so. Its tree is
    the one call the format names for a compilation, so it is read the way
    a computed node's is; what that tier reports is that the operation is
    in the format's own vocabulary, which is a different claim from the
    compiled recipe travelling in the file, and the profile is where that
    second question is answered.

    Which kinds have a tree, and the refusal for one that should and does
    not, are :func:`_tree_of`'s -- shared with ``expr`` so that the two
    fields cannot answer differently.
    """
    tree = _tree_of(graph, node)
    return None if tree is None else tier_of(tree)


def _expr_of(
    graph: CalcGraph, node: GraphNode, *, profile: str
) -> dict[str, Any] | None:
    """Return ``node``'s operation tree as a document, or None where none travels.

    None in the ``audit`` profile, whatever the node is: that profile is the
    account a reviewer reads, and the tree is what the profile above it adds.
    None again on a leaf in either profile -- an arriving column, a hole, a
    running state and a column of values handed over wholesale have no tree,
    and an ``expr`` on one would be an empty object claiming to be a
    calculation.

    The encoding is :func:`op_node_to_json`'s and no second one is written
    here. A consumer parses what comes back, hashes it under section 12.1's
    byte grammar, and reaches the ``local_fingerprint`` this same node
    carries -- which only holds while the tree in the file and the tree the
    digest was taken over are one object read twice.

    A node that computes and has no tree is refused rather than written
    without one, by :func:`_tree_of` and in the same breath as the tier
    beside it. The absence is the same absence, so the two fields say the
    same thing about it whichever of them the caller asks for first.
    """
    if profile != PROFILE_EXECUTABLE:
        return None
    tree = _tree_of(graph, node)
    return None if tree is None else op_node_to_json(tree)


def _settings_of(graph: CalcGraph, node: GraphNode) -> dict[str, Any] | None:
    """Return the stated settings of ``node``'s defining operation, or None.

    An accumulation's timing convention is the first thing a reviewing
    actuary asks after, and until it is written here it is nowhere a
    reviewer reads: the ``audit`` profile carries no operation tree, and the
    convention survives in the lowered text as a leading ``1.0`` and a
    ``slice``. The figures alone do not say which convention a column was
    written under, and a flat-rate test can pass a model converted wrongly
    between the two, so a model written under the wrong one can pass its own
    tests and be caught, if at all, on the proof.

    **The root operation only.** What is written here is what the node's
    whole calculation is, not something found inside it: a survival curve
    scaled by a face amount is a multiplication, and the convention belongs
    to the accumulation nested in it rather than to the node. The
    ``executable`` profile's tree holds that one, in the place a nested
    call's configuration has always lived, and a reader following the node's
    settings never has to ask which of two accumulations they describe.

    **Quoted, not re-derived.** The values are the section 11 attributes the
    call carries, written by :func:`op_node_to_json` -- the same encoding the
    ``executable`` profile's tree is written in, so the two cannot spell one
    convention two ways. Nothing here reads the formula text, and nothing
    here renames: the recorded convention is ``start_at``, and section
    11.1.19 says that null is end-of-period timing and 1.0 the beginning of
    one. A field called ``rate_timing`` here would be this producer's own
    word for a thing the format already names.

    None on every other node, which is nearly every node, and the absence is
    the statement: a node with nothing to say about a convention says
    nothing rather than saying it emptily.
    """
    tree = _tree_of(graph, node)
    if not isinstance(tree, Call) or tree.name not in _SETTINGS_OPERATIONS:
        return None
    stated = op_node_to_json(tree)["attrs"]
    return dict(stated) if stated else None


def _wire_node(  # noqa: PLR0913 — one parameter per fact the record needs and the node does not hold; a config object here would be the parameter list under another name
    node: GraphNode,
    ledger: FacetLedger,
    *,
    tier: OpTier | None,
    expr: dict[str, Any] | None,
    settings: dict[str, Any] | None,
    reads_assumptions: tuple[str, ...],
    narrowings: tuple[dict[str, Any], ...],
    carries_values: bool,
    along_the_axis: dict[str, Any] | None,
    include_lowered: bool,
) -> dict[str, Any]:
    """Return one node in its wire form: flat, and named as the format names it.

    ``kind`` is the account the node gives of its column -- computed, an
    arriving input, or a column nothing accounts for -- and ``provenance``
    is where that column's values came from or which frame operation defined
    them. In memory the first is the node's own ``kind`` and the second its
    data's; naming them apart is what lets both sit flat on one object.

    What the column *holds* is read off ``dtype``, and there is no second
    field restating it. A ``bool`` or ``list[bool]`` column holds a
    selection and any other type holds a quantity -- with the caveat the
    type vocabulary carries, that a selection may also arrive as a numeric
    0/1 mask, which every bare comparison this framework writes produces.
    A field that restated the type could disagree with it, in a document
    whose whole claim is that it can be checked.

    The fields are written in the order the format tabulates them, so that a
    reader meeting the record for the first time meets it in the order the
    format explains it.

    ``engines`` is left out of every node but a computed one. A column that
    arrived, a column nothing accounts for, a column of values handed over
    wholesale and a running rollforward state have no tree at all, so an
    empty array -- a positive claim that the node's tree reaches into no
    engine -- would be a claim about nothing. A compiled rollforward has a
    tree and still says nothing here, because that tree is the
    compilation's identity rather than its recipe: what the state machine's
    own expressions reach into is not in it, and an empty array would
    answer a question this node was never asked.

    ``tier`` is written on every node, and it is null on a leaf. The two
    fields are near neighbours and are not the same claim: ``engines``
    names what a node's text needs and may be left out altogether, while
    ``tier`` says how much of the node the format can account for and is
    stated even where the answer is "nothing to account for". A compiled
    rollforward is where they part company outright -- no ``engines`` at
    all, and a stated ``tier``.

    ``reads_assumptions`` sits beside ``reads`` and answers the same shape
    of question about the other kind of thing a formula can read. It is
    written on every node and is usually empty, because most formulas read
    columns and nothing else; empty is the node's own answer rather than a
    field left unfilled.

    ``settings`` is the timing convention an accumulation ran under, and it
    is written in both profiles because the profile that needs it most
    carries no operation tree to read it out of. It sits at the head of the
    three fields that say how the node computes rather than what it read:
    which convention, then which engines the text needs, then how much of
    the node the format can account for. Absent on every node whose whole
    calculation is not one of the two accumulations -- never an empty
    object, which would claim an operation that stated no convention.

    ``expr`` is the node's own operation tree, and it is written only where
    the ``executable`` profile asked for one. It never displaces the
    as-written ``formula`` beside it: the two are the same calculation said
    twice, once in the model author's spelling and once in the format's, and
    where they could disagree the formula is authoritative. What the tree
    adds is that it can be executed and that it can be checked -- hashing it
    reaches the ``local_fingerprint`` on the same node.

    ``states`` is written on the one node that has an answer to it -- one
    compiled rollforward, naming the running states it declares in
    declaration order -- and left off every other node, including a
    compilation whose compiled artefact this process cannot reach. Absent
    says nothing, which is what is true of a node that is not a state
    machine and of one whose state list nothing here could read; an empty
    array would say a state machine with no states in it, which no
    compilation is.

    ``extracts`` is written on a column that materialises a compilation's
    running balance, and the single case goes onto the wire as the object it
    is rather than as an array of one. The fold holds a sequence however many
    there are, because one formula may materialise two balances and they may
    come from two compilations; a reader of a column that extracts one thing
    should not have to index past a wrapper to reach it, and one that extracts
    two is reading a list because there are two. Absent on every column that
    pulls nothing out of a compilation, which is every column of a model that
    never escalated to a state machine.

    Everything else the fold recorded is lifted alongside them, including the
    fields the format does not define. A consumer must accept a field it does
    not know and pass it on unchanged, and dropping one here would hand on a
    document missing something the model actually said. Two fields are the
    exception, and both are dropped rather than lifted. The period reference
    restates in a field of its own what ``engines`` already says about the one
    node whose timing cannot be read. The engine's rendering says a second
    time, in the engine's spelling, what the as-written ``formula`` already
    says -- and says it differently every time the engine changes how it
    prints an expression, which is exactly the churn a base artifact must not
    carry. Neither is a field the format defines, and the rendering has a
    defined place to go instead: the ``gaspatchio_lowered`` facet, written
    when the caller asks for it.

    Args:
        node: The node to write out.
        ledger: The artifact's facet declarations, so that a facet put on
            this node is announced in the envelope by the same act that
            emits it.
        tier: How much of this node the format can account for, or None
            where the node has nothing to execute.
        expr: This node's operation tree as a document, or None where the
            profile carries none and where the node has no tree at all.
        settings: The section 11 attributes of the operation this node's
            whole calculation is, where that operation is one of the two
            accumulations that state a timing convention, and None on every
            other node -- including one whose accumulation is nested inside
            a larger formula, whose convention travels in the tree.
        reads_assumptions: The entries of the envelope's ``assumptions``
            section this node's own formula reads, by name. Empty for a
            node that reads none, and for one with no formula at all.
        narrowings: How each of this node's reads was narrowed, in
            ``reads`` order, as the ``gaspatchio_column_transformation``
            facet carries them. Empty for a node that reads nothing, and
            an empty one writes no facet at all: the narrowing of no reads
            is not an empty array, it is nothing to say.
        carries_values: Whether the artifact states an evaluation context at
            all. Where it does not, the places a value sample, a trace and a
            conditional's two branches would sit are absent rather than
            null: an absent field and a null are different claims, and "the
            sample is null" is not the sentence "this artifact carries no
            samples".
        along_the_axis: What this node held for each policy on the envelope's
            ``policies`` axis, one array per enrichment field, positionally
            aligned to it. None on a document carrying one policy, where each
            field is the value itself and a reader written against the
            edition before this one is not reading an array it has never met.
        include_lowered: Whether this node carries the engine's rendering of
            its calculation as a facet. It is announced in ``facets_used``
            and never in ``facets_required``: a consumer that does not
            understand it has lost a debugging convenience, not the meaning
            of the record.
    """
    data = node.data.model_dump(mode="json")
    data.pop("period_reference", None)
    lowered = data.pop("lowered", None)
    # Written only where it is true, and only beside the values it is the
    # licence for. A retention declaration on a node carrying nothing would
    # be a producer claiming to have held an output it then did not publish,
    # which says nothing a reader can act on.
    retained = bool(data.pop("retained", False)) and carries_values
    _only_the_enrichment_this_artifact_carries(data, carries_values=carries_values)
    if carries_values and along_the_axis is not None:
        data |= along_the_axis

    # A facet on a node has to reach the envelope's two declaration lists, and
    # the only way those never fall out of step with the nodes is for whatever
    # emits a facet to announce it in the same breath.
    facets: dict[str, Any] = {}
    if narrowings:
        facets[_COLUMN_TRANSFORMATION_FACET] = facet(
            _COLUMN_TRANSFORMATION_FACET, {"reads": list(narrowings)}
        )
    if include_lowered and lowered is not None:
        facets[_LOWERED_FACET] = facet(
            _LOWERED_FACET, {"engine": _LOWERED_ENGINE, "text": lowered}
        )
    for name in facets:
        ledger.record(name)

    engines = data.pop("engines")
    extracts = data.pop("extracts")
    states = data.pop("states")
    increments = data.pop("increments")
    named = {
        "id": data.pop("id"),
        "column": data.pop("column"),
        "version": data.pop("version"),
        "kind": node.kind.value,
        "dtype": data.pop("dtype"),
        "shape": data.pop("shape"),
        "provenance": data.pop("provenance"),
        "formula": data.pop("formula"),
        "reads": data.pop("reads"),
        "reads_assumptions": list(reads_assumptions),
    }
    # Beside ``reads``, because it is an account of one of them: which of the
    # things this node read is a state machine, and which balance of it the
    # column holds.
    named |= _extracted(extracts)
    # Ahead of ``engines`` and ``tier``, because the three answer one
    # question in widening order -- under which convention, needing which
    # engines, accounted for how far -- and the convention is the one of
    # them a reviewer reads before the arithmetic.
    named |= _stated_settings(settings)
    if node.kind is NodeType.COMPUTED:
        named["engines"] = engines
    named["tier"] = tier
    named |= {
        "local_fingerprint": data.pop("local_fingerprint"),
        "fingerprint": data.pop("fingerprint"),
        "in_final_schema": data.pop("in_final_schema"),
    }
    # Beside the field it qualifies, because the two are read together: one
    # says which definition the frame holds, the other says that this one's
    # own output was held long enough to be read.
    if retained:
        named["retained"] = True
    named |= {
        "materialized_at": data.pop("materialized_at"),
        "source_location": data.pop("source_location"),
        "facets": facets,
    }
    if expr is not None:
        named["expr"] = expr
    if states is not None:
        named["states"] = states
    if increments is not None:
        named["increments"] = increments
    # Everything the fold recorded that this function does not name itself,
    # and only that: a recorded field whose name collides with one written
    # above would otherwise replace it, and the reader would be handed the
    # wrong value under the format's own name.
    return {**named, **{key: value for key, value in data.items() if key not in named}}


def _extracted(stated: Sequence[Any] | None) -> dict[str, Any]:
    """Return the ``extracts`` entry one node carries, or nothing to add.

    The fold holds a sequence however many balances a column materialises,
    and the wire writes one as the object it is: a reader of a column that
    holds a single balance should not index past a wrapper to reach it, and
    one holding two is reading a list because there are two. Empty where the
    column materialises none, which is every column of a model that never
    escalated to a state machine.
    """
    if not stated:
        return {}
    return {"extracts": stated[0] if len(stated) == 1 else list(stated)}


def _only_the_enrichment_this_artifact_carries(
    data: dict[str, Any], *, carries_values: bool
) -> None:
    """Drop the enrichment fields this node has nothing to say under.

    Three fields are read only under the envelope's one evaluation
    context: what the column held, the walk-through of how it got there,
    and what each branch of a conditional would have held. An artifact
    stating no context carries none of the three, and carries them as
    *absent* rather than as nulls -- an absent field and a null are
    different claims, and "the sample is null" is not the sentence "this
    artifact carries no samples".

    ``branches`` is dropped on the same terms one step further: absent
    also where nobody asked the producer to evaluate them, where the node
    is not a conditional, and where a branch could not be evaluated. A
    null there would read as a conditional the producer looked at and
    found to have no second branch, which is not a thing a conditional
    can be.

    ``movements`` goes the same way for the same reason. It is a member of
    one kind of node -- a compiled rollforward, and only one whose
    movements this producer could read -- so a null on every column of a
    model that never escalated to a state machine would be a producer
    reporting that it went looking for a waterfall inside a multiplication.
    """
    if not carries_values:
        data.pop("value_sample", None)
        data.pop("trace", None)
        data.pop("branches", None)
        data.pop("movements", None)
    if data.get("branches") is None:
        data.pop("branches", None)
    if data.get("movements") is None:
        data.pop("movements", None)


def _stated_settings(stated: dict[str, Any] | None) -> dict[str, Any]:
    """Return the ``settings`` entry one node carries, or nothing to add.

    Nothing to add is the answer for nearly every node, and it is an answer
    rather than an omission: a node that ran no accumulation naming a
    convention has no convention, and writing an empty object would claim
    an operation that stated none. :func:`_settings_of` decides which nodes
    have one; this only puts it where the format tabulates it.
    """
    return {} if stated is None else {"settings": stated}


def _policy_axis(
    graph: CalcGraph, config: GraphExportConfig, values_from: pl.DataFrame | None
) -> list[dict[str, Any]]:
    """Return the axis of evaluation contexts this artifact's values sit on.

    Empty where the artifact carries no values at all, which is the common
    case: a graph exported without a collected frame describes the
    calculation and samples nothing. A value sample or a trace read out of a
    filtered frame means nothing without the context it was read under, so
    the two never travel apart.

    One entry per policy the export carries, in the order the selector
    produced, and the values at that position of every node's enrichment
    were read under it. **The axis is declared here and nowhere else.** A
    node carries its values in the axis's order and names no policy of its
    own: a document whose envelope says one thing and whose nodes say
    another is the failure section 8's withdrawn window warns about, and an
    axis restated on every node of every policy is where that disagreement
    would come from.

    ``periods`` is null where every period was taken, which is the default
    and is what a per-period value sample and a per-period walk-through
    both then show. A run pinned to one period names it here, so a reader
    holding two artifacts of one model can see that they were read at two
    different points of the same timeline rather than that the model moved.

    ``why`` is the sentence saying how this policy came to be in the file.
    It is on every entry, including the one an export nobody narrowed
    produces, because "row 0 of 1,000" is the fact a reader most needs and
    the one a document silent about its selection lets them assume away.

    **The book's own folds come first**, ahead of the policies. A reader who
    opened a portfolio document opened it for the book's total, and the head
    of the axis is what the envelope's ``enrichment`` restates -- so the
    ``aggregation`` the format has carried since it was drafted is written
    where a consumer of the edition before this one already reads for it.
    A fold's ``filter`` is its own cut of the book and not the export's:
    the driver folds every row of the model points, so a run narrowed for
    its samples says so on the policy entries and states the truth about
    the fold on the fold's.

    **A policy entry's ``filter`` is its own cut too, where it sits in one.**
    A row of a cross-joined scenario frame is one policy under one
    scenario, and the entry names that scenario here -- otherwise three
    entries reading ``policy_id: "1"`` would differ in nothing a reader
    could see. Where the export was also narrowed with ``--filter``, both
    are true of the rows behind that value and both are written, joined
    the way section 7 joins two cuts.
    """
    carries_values = any(
        node.data.value_sample is not None or node.data.trace is not None
        for node in graph.nodes.values()
    )
    if not carries_values:
        return []
    periods = None if config.period is None else [config.period]
    folds = [
        {
            "policy_id": None,
            "aggregation": fold.aggregation,
            "periods": periods,
            "filter": fold.filter,
            "why": fold.why,
        }
        for fold in config.folds
    ]
    if not config.policies:
        return [
            *folds,
            {
                "policy_id": _sampled_policy(config, values_from),
                "aggregation": None,
                "periods": periods,
                "filter": config.filter_expr,
                "why": _why_unselected(config),
            },
        ]
    return [
        *folds,
        *(
            {
                "policy_id": entry.policy_id,
                "aggregation": None,
                "periods": periods,
                "filter": _both_cuts(entry.cut, config.filter_expr),
                "why": entry.why,
            }
            for entry in config.policies
        ),
    ]


def _both_cuts(own: str | None, asked: str | None) -> str | None:
    """Return the cut an entry's rows carry: its own, the export's, or both.

    Two narrowings can be true of one entry at once -- the scenario its row
    sits in, and whatever ``--filter`` asked for -- and ``filter`` is the
    member that says which rows are behind a value. Writing one and
    dropping the other would make the document understate the cut, which
    is the one direction this member must never be wrong in.
    """
    if own is None:
        return asked
    if asked is None:
        return own
    return f"{own} and {asked}"


def _why_unselected(config: GraphExportConfig) -> str:
    """Return the ``why`` for an export that ran no selector over the book.

    A caller reaching the exporter directly -- a test, a library, this
    package's own accessor -- states a policy or states nothing, and neither
    is a row position it could have counted. So the sentence says what such
    an export can substantiate and no more: which policy was pinned, or that
    the values came off whichever row the frame held first. Naming a row it
    never counted would be the one thing ``why`` exists to prevent.
    """
    if config.policy_id is not None:
        return f"policy {config.policy_id!r}, pinned on the export"
    return (
        "the first row of the frame the values were read from, which is "
        "where the data happened to put it rather than a policy anybody chose"
    )


def _along_the_axis(
    samples: Sequence[Mapping[NodeId, Mapping[str, Any]]] | None, *, width: int
) -> dict[NodeId, dict[str, Any]]:
    """Return each node's enrichment gathered into one array per field.

    Nothing to gather where the document carries one policy: the fields are
    then written exactly as the edition before this one wrote them, the
    value itself and never an array of one, and a reader of such a document
    meets nothing new. That is the byte-for-byte half of the additivity
    claim, and it is why this returns an empty mapping rather than arrays of
    length one.

    Above one, every node the axis reached gets one array per field it holds
    anywhere on the axis, positionally aligned to ``policies``. A field no
    policy stated is not in the mapping at all and stays off the node; a
    field some policies stated and others could not carries a null at those
    positions, which says the producer had nothing to write for that policy
    rather than that the axis is shorter than it says.

    ``movements`` is the one field that is not one value but a mapping of
    them, and the axis goes **inside** it rather than around it: the member
    stays keyed by the step, and each step's amount is what takes the shape
    every other enrichment field takes. Wrapping the mapping instead would
    make a reader index a policy before they could name a movement, and
    would let two entries of one axis disagree about which steps the chain
    has -- which is a fact about the compilation and not about any policy.
    """
    if samples is None or width < _AXIS_IS_PLURAL:
        return {}
    gathered: dict[NodeId, dict[str, Any]] = {}
    for position, one_policy in enumerate(samples[:width]):
        for node_id, fields in one_policy.items():
            for name, value in fields.items():
                run = gathered.setdefault(node_id, {}).setdefault(name, [None] * width)
                run[position] = value
    for fields in gathered.values():
        moved = fields.get(_MOVEMENTS)
        if moved is not None:
            fields[_MOVEMENTS] = _movements_along_the_axis(moved, width=width)
    return gathered


def _movements_along_the_axis(
    entries: Sequence[Any], *, width: int
) -> dict[str, list[Any]]:
    """Turn one mapping of movements per entry into one array per movement.

    The keys are the union over the axis, in the order the entries state
    them, so a step is named once however many entries carry it. An entry
    that carried no movements at all -- a fold the identity does not hold
    under -- leaves a null at its position in every one of them, which is
    the same null section 7 writes for a column no accumulator covers.
    """
    keyed: dict[str, list[Any]] = {}
    for position, one_entry in enumerate(entries[:width]):
        if not isinstance(one_entry, dict):
            continue
        for key, amount in one_entry.items():
            keyed.setdefault(key, [None] * width)[position] = amount
    return keyed


def _envelope_enrichment(axis: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the head of the axis in the shape the earlier edition read.

    The envelope keeps ``enrichment``, and it is the first entry of
    ``policies`` with ``why`` left off -- the one member `v0-preview.2` did
    not define. A consumer written against that edition reads a multi-policy
    document as its first policy and is not wrong about anything it reads
    there, which is the whole of this change's additivity claim.

    Null where the axis is empty, because null is what that edition wrote
    for an artifact carrying no values and there is nothing here to say
    differently.
    """
    if not axis:
        return None
    return {name: value for name, value in axis[0].items() if name != "why"}


def _sampled_policy(
    config: GraphExportConfig, values_from: pl.DataFrame | None
) -> str | None:
    """Return the policy the value samples were read from, or None.

    A sample taken with no policy asked for is the first row's, which is one
    policy -- whichever one the frame happens to hold first. Recording null
    there would say the values were not taken from one policy, and that is
    the one thing that is never true of them. Null is kept for the case that
    earns it: a frame with no policy identifier in it to read.
    """
    if config.policy_id is not None:
        return config.policy_id
    if values_from is None or config.policy_id_column not in values_from.columns:
        return None
    if values_from.is_empty():
        return None
    identifier = values_from[config.policy_id_column][0]
    return None if identifier is None else str(identifier)
