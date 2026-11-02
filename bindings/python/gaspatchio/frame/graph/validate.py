# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Whether an exported artifact holds together: its shape, then its structure.

An artifact is a record somebody else reads -- a reviewer this quarter, a
supervisor next year, a second implementation that has never met this one.
Everything the format claims for itself rests on that record being checkable
by whoever holds it, rather than believed because of who wrote it. This
module is what does the checking, and :func:`validate_artifact` is the whole
of its surface.

**The schema layer** resolves the artifact's own ``schema`` string through
the identifier table this package ships and validates the document against
what that table names. The string is a key and never a locator: nothing here
parses it for a version and nothing fetches it, so an identifier this build
does not carry is refused by naming the identifiers it does. A file whose
validity depended on a host still answering would be a file with an expiry
date on it.

**The structure layer** reads what a schema of this kind cannot reach --
reference within one document, and the shape of the graph those references
draw. Every name a node reads resolves to a node in the same file; every edge
runs between two accounts the file holds; **the reads and the edges say one
thing**, because they are one dependency recorded twice and a file where they
disagree can be read two ways; the dependencies do not run in a circle; a
column's definitions count from 1 without a gap; a reserved id namespace
holds nothing that is a column of the model; **a node nothing defines claims
no tier**, having nothing to execute; every id is one id; and the two facet
declaration lists say what the document actually carries -- every facet named
in ``facets_used`` is somewhere in the file and every facet in the file is
named there, every facet the producer marked *required* is one of them, and a
required facet nobody understands refuses the artifact outright.

The same layer says where a **value arrived rather than being computed**: a
definition that reads no column, names no assumption base, and reaches into
one engine's own expression language is a vector or a number handed to the
model, with nothing in the document tying it to a source. The file is honest
-- the recording door wrote down what it was given -- and the model is what
the reader is being told to look at.

**The identity layer** is what ``deep=True`` adds, and it is the layer that
stops the digests being taken on trust. Every published ``fingerprint`` is
recomputed from the ``local_fingerprint`` beside it and the fingerprints of
what the node reads; the one digest standing for the whole model is
recomputed from the published pairs, the published assumption hashes and the
published hole columns; every inlined assumption payload is re-hashed against
the fingerprint written next to it; and, where the artifact carries operation
trees, every ``local_fingerprint`` is recomputed from the tree it was taken
over. What that buys a reader is the pair of questions a quarter-over-quarter
review asks -- which node changed on its own, and which inherited a change
from upstream -- as facts they checked rather than a story the producer told
about its own file.

**And the seal, which answers the other question.** Every reading above is a
reading of the *calculation*: an identity moves when the computation moves
and at no other time, so an as-written formula edited after export leaves all
of them clean. ``document_digest`` is a hash over the document's own
canonical serialization, and recomputing it is what says whether this is the
file the producer wrote. It runs first in this layer, because everything else
here reads fields off the document and this is what says whether the document
is the one those fields were written into. A document carrying no seal is
**noted and not refused**: the member is not required under this schema
identifier, and a document written before the seal existed is a conforming
document.

**The enrichment layer** reads the values an artifact carries against the
walk-through beside them: a trace with no sample to substitute in, a trace
ending somewhere other than the number it claims to reach, a value hanging
off a definition the finished frame no longer holds, and -- where the file
carries the engine's rendering as well -- a walk-through whose first line is
not that rendering. The last of those is a consistency reading rather than a
verification, and says so where it is written.

**The portability layer** answers one question about one named engine --
which nodes it cannot run -- so that the escape hatches in a model are
countable rather than a matter of opinion. It is selected by naming the
engine and is silent otherwise, because "which engine" has no default.
Nothing here holds the engine's name against a list of engines this build
knows: the artifact is what the question is asked of, and such a list would
not be the artifact's. What the reading says instead is when nothing in the
file names that engine at all, which is where a typo stops being invisible.

**Which readings ran** is on the report itself. A section nobody asked for
produces no findings and so does a section that ran and found nothing, so
the report names the readings it gave rather than leaving one clean bill to
stand for both.

What comes back is a report rather than an exception. A validator that
crashes on a bad file has told its reader that something is wrong and nothing
about what -- and the point of the exercise is that hole-freeness and
conformance become things a pipeline can check on a schedule, rather than
things somebody reads on the morning of the meeting. That holds for what
arrives as much as for what is inside it: a string is the text of a document
or the path of a file, whichever of the two it turns out to be, and one that
is neither comes back as a finding naming both attempts rather than as a
filesystem error naming somebody's pasted document as a filename.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

import polars as pl

from gaspatchio._identity import SHA256_PREFIX, content_sha_of, source_sha_of
from gaspatchio._semantic.ir import Call
from gaspatchio.schemas import SCHEMA_IDENTIFIERS, load_schema

from .artifact import (
    _COLUMN_TRANSFORMATION_FACET,
    _LOWERED_FACET,
    DOCUMENT_DIGEST_FIELD,
    SELECTION_MEMBER,
    book_columns,
    book_of,
    document_digest_of,
)
from .fingerprint import (
    HANDED_OVER_FORMULAS_LOCAL,
    HEX_WIDTH,
    _merkle,
    _sequence,
    _text,
    formulas_digest,
    formulas_tree,
    hole_entries,
    local_fingerprint,
    selection_local,
    selection_section,
)
from .graph_models import (
    ROLLFORWARD_FINGERPRINT_ATTR,
    ROLLFORWARD_NAMESPACE,
    SELECTION_NAMESPACE,
    STATE_NAMESPACE,
)
from .op_json import op_node_from_json
from .rollforward_ir import FACET_NAME as _ROLLFORWARD_IR_FACET
from .rollforward_ir import compilation_disagreements
from .tiers import _KINDS_THAT_COMPUTE, tier_of
from .trace_generator import _minimal_clean

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from gaspatchio._semantic.ir import OpNode

__all__ = [
    "KNOWN_FACETS",
    "REPORT_VERSION",
    "Finding",
    "Section",
    "Severity",
    "ValidationReport",
    "payload_frame",
    "validate_artifact",
]

# Which reading a finding came out of. ``schema`` is the published document
# the artifact's own identifier resolves to; ``semantic`` is everything about
# the structure and the identity of the graph that document cannot express;
# ``enrichment`` is the values an artifact carries read against the
# walk-throughs beside them; ``portability`` is what one named engine cannot
# run. The identity readings sit under ``semantic`` rather than under a fifth
# name, because what they say is what the structure of the graph claims about
# itself -- checked rather than read.
Section = Literal["schema", "semantic", "enrichment", "portability"]

# What a finding costs. An ``error`` is a reason to refuse the artifact; a
# ``warning`` is something worth a reader's attention that the document is
# still readable without.
#
# Two grades and not three. An assumption payload the producer left out
# could have been an *info*-grade remark, and it is written here as a
# warning instead: what makes it worth saying is that the fingerprint beside
# it is a claim about data held elsewhere, so a reader who wants to check it
# has somewhere to go -- which is exactly "worth a reader's attention, and
# the document is readable without it". A third grade would divide the
# warnings without dividing what a consumer does about them, and every
# consumer grouping a report by severity would meet a vocabulary that had
# grown under it.
#
# **What decides the grade is whether a conforming producer could have
# written the document, not how serious the defect looks.** An error is a
# document contradicting a rule the specification states unconditionally --
# a duplicate id, an unresolved read, an ordinal gap, a leaf claiming a
# tier, a digest that will not recompute. A warning is a document that is
# honest and short: no audit surface, a payload left out, a leaf that
# cannot be verified from what the file carries.
#
# That is why the two readings of ``reads`` against ``edges`` do not carry
# the same grade even though they are two halves of one disagreement. A
# read with no edge is refused, because section 9 writes one edge per entry
# of the target's ``reads`` and puts no condition on it. An edge with no
# read is a warning, because section 9's four unemitted row-shaping
# narrowings leave a producer that shapes rows a document the section
# arguably tolerates -- and it is held open for those four rather than
# because that half is the milder one. ``_edge_and_read_findings`` says the
# same thing where a reader of the rule will meet it.
Severity = Literal["error", "warning"]

# The report's own identifier, resolved the way an artifact's is: a key, not
# a version to parse. A consumer holding a stored report reads it under the
# grammar this names rather than under whatever the reader it has now
# happens to produce.
REPORT_VERSION: Final[str] = "gaspatchio-graph-validation/v0-preview.1"

# The facets this build understands. Read off the modules that emit them
# rather than restated, because a list that can drift from what is written is
# a list that will: a facet this package emits and this set had forgotten
# would refuse an artifact this package produced.
KNOWN_FACETS: Final[frozenset[str]] = frozenset(
    {_COLUMN_TRANSFORMATION_FACET, _LOWERED_FACET, _ROLLFORWARD_IR_FACET}
)

# What each reserved id namespace names. A node found in one is not a column
# of the model at all, which is why both ``column`` and ``version`` are null
# on one -- and why a reader may take an id there for what the namespace says
# it is.
_RESERVED_NAMESPACES: Final[tuple[tuple[str, str], ...]] = (
    (STATE_NAMESPACE, "one running rollforward state"),
    (ROLLFORWARD_NAMESPACE, "one compiled rollforward"),
    (SELECTION_NAMESPACE, "one step that chose which rows the model values"),
)

# Where a finding sits when it is about the artifact as a whole rather than
# about anything inside it. Section 7's own name for the top-level object.
_ENVELOPE: Final[str] = "envelope"

# The member of the narrowing facet that says which period a read read,
# and the one narrowing it goes with. Section 9: an offset states where a
# value came from, so it belongs to the narrowing that says a value came.
_OFFSET: Final[str] = "offset"
_TRANSFORMATION: Final[str] = "TRANSFORMATION"

# The member stating which periods an aggregation read reached (section 9),
# and the two ends of a policy's run a bound may name instead of a distance.
_PERIODS: Final[str] = "periods"
_RUN_ENDS: Final[frozenset[str]] = frozenset({"first", "last"})

# The member stating the convention an accumulation ran under, the one kind
# of node that can have run one, and the two shapes section 8 defines for
# it -- one per identifier, each stating both of its settings always.
_SETTINGS: Final[str] = "settings"
_COMPUTED_KIND: Final[str] = "computed"
_SURVIVAL_SETTINGS: Final[frozenset[str]] = frozenset({"start_at", "from_survival"})
_PROSPECTIVE_SETTINGS: Final[frozenset[str]] = frozenset({"timing", "discount_kind"})
_TIMINGS: Final[frozenset[str]] = frozenset({"beginning_of_period", "end_of_period"})
_DISCOUNT_KINDS: Final[frozenset[str]] = frozenset({"rate", "factor"})

# What each setting may hold, in the words its own refusal uses, so that the
# sentence a reader is given and the check that drew it are one statement.
# ``start_at`` admits a decimal **or null**, and the null is a claim rather
# than a gap: section 11.1.19 records end-of-period timing that way, so a
# reading that took it for a missing value would refuse the very convention
# this member exists to state.
_START_AT_ADMITS: Final[str] = (
    "the value a survival fold opens the run at is a decimal or null -- null "
    "being how end-of-period timing is recorded and 1.0 how the beginning of "
    "a period is"
)
_FROM_SURVIVAL_ADMITS: Final[str] = (
    "whether the operand was already a survival rate is true or false"
)
_TIMING_ADMITS: Final[str] = (
    "a prospective value's timing is 'beginning_of_period' or 'end_of_period'"
)
_DISCOUNT_KIND_ADMITS: Final[str] = (
    "a discount operand is a 'rate' or a 'factor', and nothing in the record "
    "but this says which of the two the second operand is"
)

# The member stating what each branch of a conditional would have held, the
# three parts it states together, and the two words the branch that fired is
# named in -- the names the formula itself uses, so a reader matching the
# record against ``when(...).then(...).otherwise(...)`` matches two words
# they have already read.
_BRANCHES: Final[str] = "branches"
_BRANCH_MEMBERS: Final[frozenset[str]] = frozenset({"then", "otherwise", "fired"})
_FIRED: Final[str] = "fired"
_BRANCH_WORDS: Final[tuple[str, ...]] = ("then", "otherwise")
_LIST_SHAPE: Final[str] = "list"

# The three enrichment fields a node carries along the envelope's policy
# axis, and the width past which they are written as arrays along it. One
# policy writes each field as the value itself, which is what every document
# written before the axis existed carries and what every single-policy
# document written since carries too -- so a reading that walks the axis
# walks once over such a document and meets exactly what it always met.
_ALONG_THE_AXIS: Final[tuple[str, ...]] = ("value_sample", "trace", "branches")
_AXIS_IS_PLURAL: Final[int] = 2

# How many of the model-point values an entry carries a refusal reads back
# before it stops. Enough to show a reader what the entry does hold beside
# the policy it claims, without printing a model point at them.
_IDS_SHOWN: Final[int] = 5

# Longer than any path a filesystem addresses, and the point past which a
# string stops being offered to one. A pasted document is a plausible thing
# for a caller to hold and an implausible thing for a filename to be, and
# handing several kilobytes of it to ``open()`` would answer a reader's
# document with an error about their filenames.
_LONGEST_PATH: Final[int] = 4096

# How much of a string a finding about it quotes. A reader recognises what
# they passed from its opening; a finding that inlined a whole document
# would be a finding nobody reads to the end of.
_OPENING: Final[int] = 60

# The three states of a depth-first walk, for the cycle search below.
_UNVISITED: Final[int] = 0
_ON_THE_PATH: Final[int] = 1
_SETTLED: Final[int] = 2

# How many nodes of a loop the cycle finding names. Enough to see the shape
# of it -- where it starts, what it runs through, where it closes -- and
# short of the whole loop, because a message carrying twenty thousand ids is
# a message a reader scrolls past rather than reads.
_CYCLE_SHOWN: Final[int] = 12

# The two conformance profiles. Which one an artifact claims decides how much
# of its own identity chain it can be asked to prove: ``audit`` carries no
# operation trees, so its leaves are unverifiable by construction.
_PROFILE_AUDIT: Final[str] = "audit"

# The envelope member standing for the model's formulas with its data left
# out (section 12.6). Optional, so a document written before it is read as it
# always was.
_FORMULAS_FINGERPRINT: Final[str] = "formulas_fingerprint"

# The member that tells an inlined payload from a stood-in one. A payload
# carrying it is the producer saying a value exists and was left out, and why.
_OMITTED: Final[str] = "omitted"

# The member a source entry carries its file's text in, and the one this
# reader re-encodes to check the digest beside it.
_SOURCE_TEXT: Final[str] = "text"

# The tier of a node whose own producer could not say what it does. No engine
# can be promised a node nobody has classified, so the tier refuses them all.
_OPAQUE: Final[str] = "opaque"

# The tier of a node with a fragment of one engine's own expression language
# somewhere in its tree. Paired with a node that reads nothing at all, it is
# the shape section 8's own vocabulary has no account of: a value that
# arrived rather than a calculation that ran.
_ENGINE_NATIVE: Final[str] = "engine_native"

# The member of the lowered facet holding the engine's rendering of a node's
# calculation. It is what the walk-through beside it was generated from, so
# the two are one fact written twice.
_LOWERED_TEXT: Final[str] = "text"

# What the file says about a node the identity reading cannot recompute, and
# the three answers are not one answer. A **leaf** is a node nothing on the
# model defines, and its identity is its name and its type. A node whose
# ``provenance`` is one of the two below is a whole column of values handed
# over -- at a line inside the model, or back through an explicit re-entry:
# the model does define it, and its identity was taken over those values.
# Anything else arriving here computes and states no tree, which is a
# document somebody edited rather than a shape the producer writes.
_HANDED_OVER: Final[frozenset[str]] = frozenset({"injected", "continuation"})
_LEAF_KINDS: Final[frozenset[str]] = frozenset({"input", "hole", "state"})
_A_LEAF: Final[str] = "leaf"

# A compilation's own carried balance, and the compilation that carries it.
# Named here because three readings turn on the pair: the balance a running
# state may carry, the movements the compilation may carry, and the rule
# that neither is a column of the model and neither is asked to behave like
# one.
_A_RUNNING_STATE: Final[str] = "state"
_A_COMPILATION: Final[str] = "rollforward"

# The call a line writes a compilation's running balance onto the frame
# with, and the point that balance closes at. A column whose whole tree is
# the first IS the balance; one that wrapped it in arithmetic states the
# same extraction and is a different quantity, which is why the tree and not
# the ``extracts`` record decides.
_THE_STATE_CALL: Final[str] = "rollforward.state"
_THE_CLOSE: Final[str] = "eop"

# How far apart two balances may be before they are two runs rather than one
# number read twice. A value now reaches the wire as the full double the run
# held (§8), so the two readings of one series an honest producer writes are
# equal bit for bit -- every shipped pattern's are. The tolerance is the one
# this reading held while the wire rounded to six decimals, kept so that a
# document written then still reads as it did; anything beyond it is two runs
# rather than one number.
_THE_WIRES_LAST_DECIMAL: Final[float] = 1e-6
_AN_INJECTION: Final[str] = "injection"
_NEITHER: Final[str] = "neither"

# The one member of a node's two type fields that is not a type. Section 10
# spells out what it records -- that the producer never determined one -- and
# where that is honest: a column's superseded definitions, and a column
# defined and then dropped, where the node is the model's history rather than
# its answer.
_UNTYPED: Final[str] = "unknown"

# The two fields that say what is in a column: what its values are, and how
# many of them there are per policy. Read together because "what is in this
# column" is one question with two halves, and a node short of either half
# answers it no better than a node short of both.
_TYPE_FIELDS: Final[tuple[str, ...]] = ("dtype", "shape")

# The kinds of assumption entry, and the grammar each one's fingerprint was
# taken under. A table publishes the content hash of its processed frame and a
# join's right side the content hash of the frame it was handed, rows already
# sorted by every column; a schedule and a curve publish the recipe stamp of
# their own canonical form. The two content kinds re-hash through one function
# because they carry one form -- columns and rows -- and differ only in what
# sits beside it, which no digest is taken over.
_TABLE_KIND: Final[str] = "table"
_JOIN_KIND: Final[str] = "join"
_CONTENT_KINDS: Final[frozenset[str]] = frozenset({_TABLE_KIND, _JOIN_KIND})
_RECIPE_KINDS: Final[frozenset[str]] = frozenset({"schedule", "curve"})

# What a consumer holding a table payload builds each column back as. Neutral
# names in, storage types out: the content grammar collapses width
# deliberately, so any width carrying the same values re-derives the same
# digest. The four JSON carries as itself and no others -- a payload column
# of another type is reported as one this reader did not check rather than
# rebuilt through a branch nothing produces.
_POLARS_BY_NEUTRAL: Final[dict[str, pl.DataType]] = {
    "bool": pl.Boolean(),
    "i64": pl.Int64(),
    "f64": pl.Float64(),
    "str": pl.String(),
}

# Section 10 carries a date and an instant on the wire as ISO-8601 text: such a
# column is read as its text and then as the date or instant the text names.
_ISO_TEXT_BY_NEUTRAL: Final[frozenset[str]] = frozenset({"date", "datetime"})
_ISO_DATE: Final[str] = "%Y-%m-%d"
_ISO_INSTANT: Final[str] = "%Y-%m-%dT%H:%M:%S%.f"
# More fractional digits than a microsecond holds is an instant kept in
# nanoseconds, and is read back in them so its last digits are not cut.
_MICROSECOND_DIGITS: Final[int] = 6

# How a non-finite float travels in a column declared ``f64``, and what a
# consumer reads it back to before hashing. JSON has no token for one that a
# strict parser accepts, and null is spoken for as the missing-value marker.
_SENTINELS: Final[dict[str, float]] = {
    "NaN": float("nan"),
    "Infinity": float("inf"),
    "-Infinity": float("-inf"),
}
_FLOAT_NAME: Final[str] = "f64"


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing wrong with an artifact, where it is, and the next move.

    Attributes:
        section: Which reading found it.
        severity: Whether it refuses the artifact or only asks to be read.
        where: A node id, an edge, a JSON pointer, or ``"envelope"``.
        message: What is wrong in the model's own terms, and what to do.

    Examples:
        >>> from gaspatchio.frame.graph import Finding
        >>> finding = Finding(
        ...     section="semantic",
        ...     severity="error",
        ...     where="death_claims@1",
        ...     message="It reads a name no node in this file accounts for.",
        ... )
        >>> finding.to_dict()["where"]
        'death_claims@1'

    """

    section: Section
    severity: Severity
    where: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return the finding as four strings, for a report written to a file."""
        return {
            "section": self.section,
            "severity": self.severity,
            "where": self.where,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Everything one reading of one artifact found.

    Attributes:
        report_version: The grammar this report is written in.
        schema: The identifier the artifact claimed for itself, or the empty
            string where it claimed none. It is what the artifact said rather
            than what was resolved, so a report about a refused identifier
            still says which identifier was refused.
        sections: Which readings ran for this call, in the order they ran.
            A section nobody asked for produces no findings and so does a
            section that ran and found nothing, and this is what tells the
            two apart: ``schema`` and ``semantic`` run for every call,
            ``enrichment`` where the artifact carries values to read, and
            ``portability`` only where an engine was named. ``deep`` adds no
            name of its own -- what it recomputes is reported under
            ``semantic``, which ran either way -- so whether the digests
            were taken again is the caller's own argument and not something
            the report restates. Empty where nothing was read at all.
        findings: Every finding, in the order the readings ran.

    Examples:
        >>> from gaspatchio.frame.graph import (
        ...     REPORT_VERSION,
        ...     SCHEMA_ID,
        ...     ValidationReport,
        ... )
        >>> ValidationReport(
        ...     report_version=REPORT_VERSION,
        ...     schema=SCHEMA_ID,
        ...     sections=("schema", "semantic"),
        ...     findings=(),
        ... ).ok
        True

    """

    report_version: str
    schema: str
    sections: tuple[Section, ...]
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        """Whether the artifact may be read: no finding of severity ``error``.

        A warning is not a refusal. Something the producer left in a state
        worth mentioning is still a document that means what it says, and a
        reader who treated the two the same would have no way to say which
        artifacts are actually unreadable.
        """
        return not any(finding.severity == "error" for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        """Return the report as plain JSON data, for a pipeline that stores it."""
        return {
            "report_version": self.report_version,
            "schema": self.schema,
            "sections": list(self.sections),
            "ok": self.ok,
            "findings": [finding.to_dict() for finding in self.findings],
        }


def validate_artifact(
    artifact: dict[str, Any] | str | Path,
    *,
    deep: bool = False,
    engine: str | None = None,
    book: pl.DataFrame | pl.LazyFrame | None = None,
) -> ValidationReport:
    """Read ``artifact`` and report everything wrong with it.

    Args:
        artifact: The artifact, however the caller is holding it: the parsed
            document, the text :meth:`GraphExporter.export` returns, or the
            path of a stored file. A string beginning ``{`` or ``[`` is read
            as the text of a document and anything else as a path, so that
            neither caller has to parse or read the other's form first --
            and where that reading does not resolve the other is tried after
            it, so which of the two a string is never has to be guessed
            right. A string neither reading resolves comes back as a finding
            naming both attempts.
        deep: Whether to recompute the artifact's own digests rather than
            read them. Off by default because it costs a hash of every
            operation tree and of every inlined assumption payload, and
            because the readings below answer most of what a pipeline step
            asks. On, it is what turns "the producer says so" into something
            the holder of the file checked -- including, where the document
            carries a ``document_digest``, whether this is the file the
            producer wrote at all, which no other reading here can say.
        engine: Which engine to read the portability section against, or
            None to read none. There is no default engine, because "can this
            run somewhere else" is not a question until somewhere else has a
            name. The name is not held against any list of engines -- the
            artifact is what the question is asked of -- but an artifact
            naming that engine nowhere is said so in a warning, because a
            mistyped name otherwise reads as a portability answer.
        book: The policy data you hold, where you want to know whether this
            document was built over it. Passing it is the request, with or
            without ``deep``: the document's ``book`` digest is taken again
            over this data and held to the one the document states, so a
            quarter's filing can be matched to the in-force file it claims to
            be an account of. A document that was built over another book is
            refused, naming both digests. It costs one pass over the columns
            the document names, which is why it runs only when asked.

    Returns:
        A :class:`ValidationReport`. Its ``ok`` is what a caller checks; its
        ``findings`` are what a caller reads when ``ok`` is false; and its
        ``sections`` are which readings ran, so that "nothing found" and
        "never asked" are not one answer.

    Raises:
        OSError: If ``artifact`` is a :class:`~pathlib.Path` that cannot be
            read. A path is the caller saying which of the two readings they
            meant, so what that reading meets is what comes back; the
            ambiguous form is the string, and a string neither reading
            resolves is reported instead.
        json.JSONDecodeError: If a file that was found does not hold JSON. A
            document nothing can parse is not an artifact with something
            wrong in it, and reporting on one would be reporting on nothing.

    Examples:
        A model's own artifact passes its own reader:

        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.frame.graph import GraphExporter, validate_artifact
        >>> af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
        >>> af.death_claims = af.sum_assured * 0.00123
        >>> validate_artifact(GraphExporter(af).export()).ok
        True

        An identifier this build does not carry is refused, by name:

        >>> report = validate_artifact({"schema": "gaspatchio-graph/v9"})
        >>> report.ok
        False
        >>> report.findings[0].section
        'schema'

    """
    document = _document(artifact)
    # Nothing was read, so no reading ran and the sections say so.
    if isinstance(document, Finding):
        return ValidationReport(REPORT_VERSION, "", (), (document,))
    if not isinstance(document, dict):
        return ValidationReport(REPORT_VERSION, "", (), (_not_an_envelope(document),))

    stated = document.get("schema")
    identifier = stated if isinstance(stated, str) else ""
    # In the order a reader wants them: what the schema refuses, then what
    # the structure says, then -- where it was asked for -- what the digests
    # say when they are taken again, then the values, then the one engine.
    # ``deep`` names no section of its own: what it recomputes is reported
    # under ``semantic``, which ran either way.
    sections: list[Section] = ["schema", "semantic"]
    findings = [
        *_schema_findings(document, identifier),
        *_semantic_findings(document),
        *_path_findings(document),
        *_sources_order_findings(document),
    ]
    if deep:
        findings += _identity_findings(document)
    # Handing over the book is the request to check it: a caller who passed
    # the in-force file and not ``deep`` was told ``ok`` over the wrong book.
    if book is not None:
        findings += _book_digest_findings(document, book)
    enriched = _enriched_nodes(document)
    if enriched:
        sections.append("enrichment")
        findings += _enrichment_findings(enriched, policy_axis_width(document))
        findings += _array_of_one_findings(enriched, policy_axis_width(document))
    if engine is not None:
        sections.append("portability")
        findings += _portability_findings(document, engine)
    return ValidationReport(
        REPORT_VERSION, identifier, tuple(sections), tuple(findings)
    )


# --- what a consumer refuses outright ------------------------------------------

# The members that hold a path, each written relative to the model's root
# (section 7): where in the document they sit, and whether the string is a
# location -- a path with ``:<line>`` after it.
_PATH_MEMBERS: Final[tuple[tuple[str, ...], ...]] = (
    ("model", "source_path"),
    ("model", "model_points", "path"),
    ("model", "results", "path"),
    ("model", "audit", "path"),
    ("model", "scenarios", "path"),
)
_LISTED_PATHS: Final[tuple[tuple[str, str, bool], ...]] = (
    ("nodes", "source_location", True),
    ("sources", "path", False),
    ("selection", "source_location", True),
    ("boundaries", "source_location", True),
    ("assumptions", "source_file", False),
)


# A POSIX root, a Windows drive and a UNC share: each names a directory of the
# machine that wrote it, wherever the document is read.
_ABSOLUTE: Final = re.compile(r"/|\\\\|[A-Za-z]:[/\\]")


def _is_absolute(path: str) -> bool:
    """Return whether a written path names a directory of one machine."""
    return _ABSOLUTE.match(path) is not None


def _path_findings(document: dict[str, Any]) -> list[Finding]:
    """Return each path the document writes as an absolute path.

    Section 7: no absolute path appears anywhere in the artifact -- one names
    a directory on the exporting machine, resolves nowhere else, and would
    differ between two runs of one model that never moved. A consumer meeting
    one has met a document that does not conform.
    """
    found: list[tuple[str, str]] = []
    model = document.get("model")
    for member in _PATH_MEMBERS:
        held: Any = document
        for key in member:
            held = held.get(key) if isinstance(held, dict) else None
        if isinstance(held, str) and _is_absolute(held):
            found.append(("/" + "/".join(member), held))
    modules = model.get("modules") if isinstance(model, dict) else None
    for index, module in enumerate(modules if isinstance(modules, list) else ()):
        path = module.get("path") if isinstance(module, dict) else None
        if isinstance(path, str) and _is_absolute(path):
            found.append((f"/model/modules/{index}/path", path))
    for section, field, is_location in _LISTED_PATHS:
        for index, entry in enumerate(_objects(document.get(section))):
            held = entry.get(field)
            if not isinstance(held, str):
                continue
            path = held.rpartition(":")[0] if is_location and ":" in held else held
            if _is_absolute(path):
                found.append((f"/{section}/{index}/{field}", held))
    return [
        Finding(
            section="semantic",
            severity="error",
            where=where,
            message=(
                f"{where} is the absolute path {held!r}. No absolute path "
                "appears anywhere in an artifact (section 7): one names a "
                "directory on the exporting machine and resolves nowhere "
                "else. Export again with a model identity "
                "(ModelIdentity.of(model_file)) or a source_root, and every "
                "path is written relative to the model's root."
            ),
        )
        for where, held in found
    ]


def _sources_order_findings(document: dict[str, Any]) -> list[Finding]:
    """Return a sources section whose paths repeat or are out of order.

    Section 7.3: one entry per distinct path, ordered by ``path``. A path
    written twice is two texts for one file, and a reader showing a line of
    it cannot say which is the file the run read.
    """
    paths = [
        str(entry["path"])
        for entry in _objects(document.get("sources"))
        if isinstance(entry.get("path"), str)
    ]
    findings: list[Finding] = []
    for index, (before, after) in enumerate(itertools.pairwise(paths), start=1):
        if after == before:
            message = (
                f"The sources section names {after!r} twice. It carries one "
                "entry per distinct path (section 7.3), so two entries are two "
                "texts for one file, and a line shown from it could be either."
            )
        elif after < before:
            message = (
                f"The sources section lists {after!r} after {before!r}. Its "
                "entries are ordered by path (section 7.3)."
            )
        else:
            continue
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=f"/sources/{index}",
                message=message,
            )
        )
    return findings


def _array_of_one_findings(nodes: list[dict[str, Any]], width: int) -> list[Finding]:
    """Return each enrichment field a one-policy document wraps in an array of one.

    Section 8: a document carrying one policy writes each field as the value
    itself; a producer must not write an array of one, and a consumer meeting
    one has met a document that does not conform. A per-period value is a
    run, so its array of one is a run inside a list; a single value's is a
    list at all; a walk-through's branches are an object, so theirs is a list
    of one object.
    """
    if width != 1:
        return []
    findings: list[Finding] = []
    for node in nodes:
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        sample = node.get("value_sample")
        wrapped = isinstance(sample, list) and (
            node.get("shape") == "scalar"
            or (len(sample) == 1 and isinstance(sample[0], list))
        )
        branches = node.get("branches")
        if isinstance(branches, list) and len(branches) == 1:
            wrapped = wrapped or isinstance(branches[0], dict)
        if wrapped:
            findings.append(
                Finding(
                    section="enrichment",
                    severity="error",
                    where=where,
                    message=(
                        f"{where} carries its value in an array of one, and the "
                        "document carries one policy. A one-policy document "
                        "writes each field as the value itself (section 8): an "
                        "array of one is the shape of no conforming document, "
                        "and for a per-period column it cannot be told from a "
                        "one-period run."
                    ),
                )
            )
    return findings


# --- getting hold of the document --------------------------------------------


def _document(artifact: dict[str, Any] | str | Path) -> Any:  # noqa: ANN401
    """Return the parsed document, whichever of the three forms arrived.

    A mapping is already the document, and a path is the caller naming one
    reading of a file -- so what that reading meets is what comes back,
    including the error it raises. A string is the form that is two readings
    at once, and :func:`_from_a_string` is where that is settled.
    """
    if isinstance(artifact, dict):
        return artifact
    if isinstance(artifact, Path):
        return json.loads(artifact.read_text("utf-8"))
    return _from_a_string(artifact)


def _from_a_string(text: str) -> Any:  # noqa: ANN401
    """Return what a string holds, or the finding neither reading earns.

    A string is the text of a document or the path of a file holding one.
    The leading character says which of the two it announces itself as --
    ``{`` or ``[`` opens a document and anything else opens a path -- and
    that reading is preferred, so a stored file named for a bare JSON scalar
    is still read as a file. The other reading is what answers when the
    preferred one does not resolve, because a caller holding one form has no
    reason to know which form this reader wanted first.

    Only where neither resolves has nothing been read at all, and that is a
    finding rather than an exception: a raw filesystem error naming somebody's
    pasted document as a filename says nothing about the document, and this
    is the one input that could still get one.
    """
    opens_a_document = text.lstrip()[:1] in {"{", "["}
    document, not_a_document = _parsed(text)
    if not_a_document is None and opens_a_document:
        return document
    stored, not_a_path = _read_from_disk(text)
    if not_a_path is None:
        return stored
    if not_a_document is None:
        return document
    return _neither_reading(
        text,
        not_a_document=not_a_document,
        not_a_path=not_a_path,
        opens_a_document=opens_a_document,
    )


def _parsed(text: str) -> tuple[Any, str | None]:
    """Return what ``text`` parses to, or what the parser said about it."""
    try:
        return json.loads(text), None
    except json.JSONDecodeError as failure:
        return None, str(failure)


def _read_from_disk(text: str) -> tuple[Any, str | None]:
    """Return the document the file ``text`` names, or why none was read.

    A pasted document is never offered to ``open()``. It is longer than any
    path a filesystem addresses, or it holds a character a filename does not,
    and either way the answer coming back would be about filenames rather
    than about the document the caller is holding.

    Where a file *is* found and holds something other than JSON, the reading
    has resolved -- the string was a path -- and what the parse says about
    that file stands, exactly as it does for a path handed in as one.
    """
    if len(text) > _LONGEST_PATH:
        return None, (
            f"a name of {len(text)} characters is longer than any path a "
            "filesystem addresses, so the string was not offered to one"
        )
    if "\n" in text or "\x00" in text:
        held = "a line break" if "\n" in text else "a null character"
        return None, (
            f"the string holds {held}, which the name of a file does not, so "
            "it was not offered to the filesystem"
        )
    try:
        stored = Path(text).read_text("utf-8")
    except OSError as failure:
        return None, f"the filesystem answered {failure.strerror or failure!s}"
    return json.loads(stored), None


def _neither_reading(
    text: str, *, not_a_document: str, not_a_path: str, opens_a_document: bool
) -> Finding:
    """Return the one finding a string that is neither reading earns.

    The reading the string announced itself as is said first, because that
    is the one the caller meant and the other is the courtesy: a mistyped
    path answered by an account of JSON syntax would lead its reader away
    from the typo they made.
    """
    as_a_document = (
        f"Read as the text of a document, it does not parse as JSON: {not_a_document}."
    )
    as_a_path = f"Read as the path of a stored file, {not_a_path}."
    both = (
        (as_a_document, as_a_path) if opens_a_document else (as_a_path, as_a_document)
    )
    return Finding(
        section="schema",
        severity="error",
        where=_ENVELOPE,
        message=(
            f"What arrived is the string {_opening(text)}, and neither "
            f"reading of a string resolves it. {' '.join(both)} An artifact "
            "reaches this reader as the parsed document, as the text "
            "``GraphExporter.export`` returns, or as the path of the file "
            "that text was written to -- and this is none of the three, so "
            "nothing has been read and there is nothing here to check. Pass "
            "the exporter's own text, or the path the file was stored at."
        ),
    )


def _opening(text: str) -> str:
    """Return ``text`` quoted at its opening, however long it arrived.

    A reader recognises what they passed from the first line of it, and a
    finding that inlined a whole pasted document would be one nobody reads
    to the end of.
    """
    if len(text) <= _OPENING:
        return repr(text)
    return f"{text[:_OPENING]!r} and {len(text) - _OPENING} characters more"


def _not_an_envelope(document: Any) -> Finding:  # noqa: ANN401
    """Return the one finding a document with no envelope at all earns."""
    return Finding(
        section="schema",
        severity="error",
        where=_ENVELOPE,
        message=(
            f"This document's top level is {_json_kind(document)}, and an "
            "artifact's top level is the envelope: the object carrying the "
            "schema identifier, the producer, the model's version block, and "
            "the nodes and edges themselves. What was read is not an "
            "artifact, so there is nothing here to check. Export the model "
            "again, or point the reader at the file the exporter wrote."
        ),
    )


def _json_kind(value: Any) -> str:  # noqa: ANN401
    """Return what ``value`` is, named in JSON's own vocabulary.

    A reader of an artifact is reading a JSON document, and telling them the
    Python type they never asked about would name the reader's implementation
    where the document is what is wrong.
    """
    if value is None:
        return "a null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, (int, float)):
        return "a number"
    return f"a {type(value).__name__}"


# --- the schema layer --------------------------------------------------------


def _schema_findings(document: dict[str, Any], identifier: str) -> list[Finding]:
    """Return what the schema the artifact's identifier resolves to refuses."""
    name = SCHEMA_IDENTIFIERS.get(identifier)
    if name is None:
        return [
            Finding(
                section="schema",
                severity="error",
                where=_ENVELOPE,
                message=_unresolved_identifier(identifier),
            )
        ]

    # jsonschema is imported by nothing else in the package, and a validator
    # a run calls once or never does not belong in the import cost of every
    # model that never asks for one (*Optimize for the laptop*).
    import jsonschema  # noqa: PLC0415 — paid for by the caller who validates

    schema = load_schema(name)
    validator = jsonschema.Draft202012Validator(schema)
    deep = [
        (path, tree)
        for path, tree in _tree_roots(document)
        if _tree_depth(tree) > _WHOLE_TREE_DEPTH
    ]
    refused: list[tuple[list[str | int], str]] = []
    whole = document
    if deep:
        # A deep tree is held to the schema one tree node at a time, each
        # with its child trees stood in for, so the reading neither recurses
        # once per level nor re-reads every subtree at every level above it.
        node_validator = jsonschema.Draft202012Validator(
            {"$defs": schema.get("$defs", {}), "$ref": "#/$defs/expr"}
        )
        for path, tree in deep:
            refused.extend(_tree_node_refusals(node_validator, path, tree))
        document = _with_trees_stood_in(document, [path for path, _ in deep])
    refused.extend(
        (list(error.absolute_path), str(error.message))
        for error in validator.iter_errors(document)
    )
    return [
        *(
            Finding(
                section="schema",
                severity="error",
                where=_pointer(path),
                message=_refused_by_the_schema(identifier, path, said),
            )
            for path, said in refused
        ),
        *_stray_tree_key_findings(whole, schema),
    ]


# Trees no deeper than this are held to the schema whole, as one document.
# The schema's ``$ref`` from a tree node to its children makes the validator
# recurse about six frames per level and re-read each subtree for every
# ``oneOf`` branch above it, so a sum of two hundred terms -- one the producer
# writes from an ordinary line -- ran out of recursion, and a thousand-deep
# tree took half a minute. Deeper trees are read node by node instead
# (``_tree_node_refusals``), which reaches the same verdict on every node.
_WHOLE_TREE_DEPTH: Final = 64

# What stands in for a child tree while its parent is held to the schema: the
# smallest tree the schema accepts. The child itself is held separately.
_STAND_IN: Final = {"op": "col", "name": "-"}

# The members of each tree node that hold child trees, by its ``op``: one tree
# each, or (``args``) a list of them.
_CHILD_TREES: Final[dict[str, tuple[str, ...]]] = {
    "binop": ("left", "right"),
    "call": ("args",),
    "when_then": ("cond", "then", "otherwise"),
}


def _tree_roots(
    document: Mapping[str, Any],
) -> list[tuple[list[str | int], dict[str, Any]]]:
    """Return each operation tree the document holds, with where it sits.

    A node's ``expr``, and the ``intensity`` of each transition a node's
    ``state_graph`` states: the two places the schema puts a tree.
    """
    roots: list[tuple[list[str | int], dict[str, Any]]] = []
    nodes = document.get("nodes")
    for index, node in enumerate(nodes if isinstance(nodes, list) else ()):
        if not isinstance(node, dict):
            continue
        tree = node.get("expr")
        if isinstance(tree, dict):
            roots.append((["nodes", index, "expr"], tree))
        graph = node.get("state_graph")
        transitions = graph.get("transitions") if isinstance(graph, dict) else None
        for at, transition in enumerate(
            transitions if isinstance(transitions, list) else ()
        ):
            intensity = (
                transition.get("intensity") if isinstance(transition, dict) else None
            )
            if isinstance(intensity, dict):
                roots.append(
                    (
                        ["nodes", index, "state_graph", "transitions", at, "intensity"],
                        intensity,
                    )
                )
    return roots


def _child_trees(
    tree: dict[str, Any],
) -> list[tuple[list[str | int], dict[str, Any]]]:
    """Return a tree node's child trees, each with its place under the node."""
    named = tree.get("op")
    children: list[tuple[list[str | int], dict[str, Any]]] = []
    for key in _CHILD_TREES.get(named, ()) if isinstance(named, str) else ():
        held = tree.get(key)
        if isinstance(held, dict):
            children.append(([key], held))
        elif isinstance(held, list):
            children.extend(
                ([key, position], member)
                for position, member in enumerate(held)
                if isinstance(member, dict)
            )
    return children


def _tree_depth(tree: dict[str, Any]) -> int:
    """Return how many levels one tree nests, counted without recursion."""
    deepest = 0
    waiting = [(tree, 1)]
    while waiting:
        node, level = waiting.pop()
        deepest = max(deepest, level)
        waiting.extend((child, level + 1) for _, child in _child_trees(node))
    return deepest


def _stood_in(tree: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of one tree node with each child tree stood in for."""
    shallow = dict(tree)
    for place, _ in _child_trees(tree):
        if len(place) == 1:
            shallow[str(place[0])] = _STAND_IN
        else:
            key, position = str(place[0]), int(place[1])
            members = list(shallow[key])
            members[position] = _STAND_IN
            shallow[key] = members
    return shallow


def _tree_node_refusals(
    validator: Any,  # noqa: ANN401 -- jsonschema is imported where it is used
    path: list[str | int],
    tree: dict[str, Any],
) -> list[tuple[list[str | int], str]]:
    """Return what the schema refuses in one tree, node by node, without recursion."""
    refused: list[tuple[list[str | int], str]] = []
    waiting = [(path, tree)]
    while waiting:
        at, node = waiting.pop()
        refused.extend(
            ([*at, *error.absolute_path], str(error.message))
            for error in validator.iter_errors(_stood_in(node))
        )
        waiting.extend(
            ([*at, *place], child) for place, child in reversed(_child_trees(node))
        )
    return refused


def _with_trees_stood_in(
    document: dict[str, Any], paths: list[list[str | int]]
) -> dict[str, Any]:
    """Return the document with the trees at ``paths`` stood in for.

    Each container on the way down is copied and the rest is shared, so the
    document handed in is never changed.
    """
    copied: dict[str, Any] = dict(document)
    for path in paths:
        holder: Any = copied
        for step in path[:-1]:
            inner = holder[step]
            inner = dict(inner) if isinstance(inner, dict) else list(inner)
            holder[step] = inner
            holder = inner
        holder[path[-1]] = _STAND_IN
    return copied


def _declared_tree_keys(schema: Mapping[str, Any]) -> dict[str, frozenset[str]]:
    """Return the keys each operation-tree branch declares, by its ``op``.

    Read off the schema rather than restated here, so the branch that
    refuses a document and the finding that says why cannot name two
    different sets of keys.
    """
    branches = schema.get("$defs", {}).get("expr", {}).get("oneOf", [])
    declared: dict[str, frozenset[str]] = {}
    for branch in branches:
        properties = branch.get("properties", {})
        named = properties.get("op", {}).get("const")
        if isinstance(named, str):
            declared[named] = frozenset(properties)
    return declared


def _stray_tree_key_findings(
    document: dict[str, Any], schema: Mapping[str, Any]
) -> list[Finding]:
    """Return a finding for every key a tree node's branch does not declare.

    The seven branches are closed, so the schema refuses these; what the
    schema cannot do is say which key it refused them for. ``oneOf`` reports
    a refusal as "is not valid under any of the given schemas", which names
    no key and leaves a producer comparing its document against seven
    branches by eye. The schema is what refuses; this is what says why.

    The case this is written for is not a typo. A ``call`` relabelled to
    ``state``, with its arguments and its configuration left in place,
    validated clean before the branches were closed -- and hashed as a state
    reference, because the byte grammar reads the tag off ``op`` and a
    state's bytes are its tag and its name. Fifty-two bytes of operands and
    configuration left the digest and the document was valid on the way out.
    """
    declared = _declared_tree_keys(schema)
    findings: list[Finding] = []
    for index, node in enumerate(_objects(document.get("nodes"))):
        tree = node.get("expr")
        if not isinstance(tree, dict):
            continue
        findings.extend(_stray_keys_in(tree, declared, ["nodes", index, "expr"]))
    return findings


def _stray_keys_in(
    tree: dict[str, Any],
    declared: Mapping[str, frozenset[str]],
    path: list[str | int],
) -> list[Finding]:
    """Return the stray-key findings in one tree and everything under it.

    Walked with a stack of its own rather than by recursion, in the order a
    recursive walk visits, so a tree as deep as any the producer writes is
    read to the bottom.
    """
    findings: list[Finding] = []
    waiting: list[tuple[dict[str, Any], list[str | int]]] = [(tree, path)]
    while waiting:
        node, at = waiting.pop()
        named = node.get("op")
        keys = declared.get(named) if isinstance(named, str) else None
        if isinstance(named, str) and keys is not None:
            findings.extend(
                Finding(
                    section="schema",
                    severity="error",
                    where=_pointer([*at, stray]),
                    message=_stray_tree_key(named, stray, keys),
                )
                for stray in sorted(set(node) - keys)
            )
        below: list[tuple[dict[str, Any], list[str | int]]] = []
        for key, value in node.items():
            if isinstance(value, dict):
                below.append((value, [*at, key]))
            elif isinstance(value, list):
                below.extend(
                    (member, [*at, key, position])
                    for position, member in enumerate(value)
                    if isinstance(member, dict)
                )
        waiting.extend(reversed(below))
    return findings


def _stray_tree_key(named: str, stray: str, declared: frozenset[str]) -> str:
    """Return the refusal for one key a tree node's own branch does not declare."""
    allowed = ", ".join(sorted(declared))
    return (
        f"This {named!r} node carries the key {stray!r}, which no {named!r} "
        f"node declares: the whole of one is {allowed}. A tree node's keys are "
        "closed because its identity is not: the byte grammar reads the kind "
        "off 'op' and encodes what that kind carries, so a node relabelled to "
        "a kind that carries less keeps a valid-looking document while its "
        "operands and its configuration drop out of the digest. Either the "
        "key belongs to a different kind of node, or this node's 'op' is not "
        "the kind it was written as."
    )


def _unresolved_identifier(identifier: str) -> str:
    """Return the refusal for a ``schema`` string this build cannot resolve."""
    known = ", ".join(sorted(SCHEMA_IDENTIFIERS))
    claimed = (
        f"claims the schema identifier {identifier!r}"
        if identifier
        else "states no schema identifier at all"
    )
    return (
        f"This artifact {claimed}, and this build resolves {known}. A schema "
        "identifier is a key looked up in a table of known identifiers -- it "
        "is never parsed for a version and never fetched as a URL -- so a "
        "reader that does not carry the row cannot tell what the document "
        "means, whether the identifier is older or newer than its own. Read "
        "the file with a build whose table carries it, or export the model "
        "again from this one."
    )


def _refused_by_the_schema(
    identifier: str, path: Sequence[str | int], detail: str
) -> str:
    """Return one schema refusal, said where a reader can act on it."""
    at = "the envelope" if not path else _pointer(path)
    # The schema's own account of what is wrong is the precise half of this
    # sentence, and it is quoted rather than paraphrased. It arrives without
    # terminal punctuation, so it is given some.
    said = detail.rstrip()
    if said[-1:] not in {".", "!", "?"}:
        said = f"{said}."
    return (
        f"The schema that {identifier!r} resolves to refuses this artifact at "
        f"{at}: {said} That schema is what a second implementation reads the "
        "file under, so a field it refuses is a field nobody else can rely "
        "on. Correct the document there, or export the model again."
    )


def _pointer(path: Sequence[str | int]) -> str:
    """Return ``path`` as an RFC 6901 JSON pointer, or the envelope's name.

    An empty path is the whole document, and the artifact's whole document
    is the envelope -- which is the name section 7 gives it and a plainer
    thing for a reader to meet than the empty string RFC 6901 spells it.
    """
    if not path:
        return _ENVELOPE
    return "".join(
        "/" + str(part).replace("~", "~0").replace("/", "~1") for part in path
    )


# --- the structure layer -----------------------------------------------------


def _semantic_findings(document: dict[str, Any]) -> list[Finding]:
    """Return everything wrong with the graph the document draws.

    Read in the order a reader would want them: an id that is not one first,
    because every other reference resolves through it, then the references
    themselves and whether the two records of them agree, then what each node
    may claim about itself, then what the shape of the resolved graph says,
    then the two declaration lists, then whether a compilation's amounts are
    the run its balance came off, then the definitions that read nothing at
    all, then the retention a node claims for itself, then the answers the
    document states no type for, and last what the document as a whole is
    short of.
    """
    nodes = _objects(document.get("nodes"))
    edges = _objects(document.get("edges"))
    known = {node["id"] for node in nodes if isinstance(node.get("id"), str)}
    return [
        *_duplicate_id_findings(nodes),
        *_unresolved_read_findings(nodes, known),
        *_unresolved_edge_findings(edges, known),
        *_edge_and_read_findings(nodes, edges, known),
        *_reserved_namespace_findings(nodes),
        *_leaf_tier_findings(nodes),
        *_ordinal_findings(nodes),
        *_hole_findings(document, nodes),
        *_increment_findings(nodes),
        *_movement_findings(nodes),
        *_retrack_findings(document, nodes),
        *_extraction_findings(nodes),
        *_cycle_findings(nodes, edges, known),
        *_facet_findings(document, nodes),
        *_period_offset_findings(nodes),
        *_period_window_findings(nodes),
        *_settings_findings(nodes),
        *_axis_findings(document, nodes),
        *_branches_findings(nodes, policy_axis_width(document)),
        *_handed_over_value_findings(nodes),
        *_retention_claim_findings(nodes),
        *_untyped_answer_findings(nodes),
        *_book_findings(document, nodes),
        *_selection_findings(document, known),
        *_audit_surface_findings(document, nodes),
    ]


# Where a document's statement about its book sits, for a finding to name.
_BOOK: Final[str] = "/book"


def _book_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return what is wrong with the document's account of its book.

    The digest itself needs the book to check, and only a holder of the book
    can take it again (:func:`_book_digest_findings`). What the document alone
    can be held to is the list of columns the digest names: in name order,
    because that is the order the digest is taken in and a list out of it
    describes a digest nobody can take again; and every one of them a column
    the model reads, because a column no line reads is no part of what the
    model's numbers rest on, and a book that names one is a book somebody
    edited. The shape itself is the schema's, which has already spoken.
    """
    stated = document.get("book")
    if not isinstance(stated, dict) or not isinstance(stated.get("columns"), list):
        return []
    columns = [column for column in stated["columns"] if isinstance(column, str)]
    findings: list[Finding] = []
    if columns != sorted(columns):
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=_BOOK,
                message=(
                    "The book's columns are not in name order: "
                    f"{', '.join(repr(column) for column in columns)}. The digest "
                    "beside them is taken over the columns in name order, so a "
                    "list in any other order names a digest a reader holding the "
                    "book cannot take again. Export the model again."
                ),
            )
        )
    read = set(book_columns(nodes, _selection_steps(document)))
    arrived = {
        node.get("column")
        for node in nodes
        if node.get("kind") == "input" and node.get("provenance") == "model_points"
    }
    uncovered = sorted(
        str(column) for column in (read & arrived) - set(columns) if column
    )
    if uncovered and isinstance(stated.get("digest"), str):
        findings.append(
            Finding(
                section="semantic",
                severity="warning",
                where=_BOOK,
                message=(
                    "The model reads "
                    f"{', '.join(repr(column) for column in uncovered)}, which "
                    "arrived with the policy data, and the book's digest does "
                    "not cover it. A revision to that column would not show as "
                    "a changed book when this document is compared with "
                    "another. Export the model again from the frame built over "
                    "the data."
                ),
            )
        )
    unread = [column for column in columns if column not in read]
    if unread:
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=_BOOK,
                message=(
                    "The book names "
                    f"{', '.join(repr(column) for column in unread)}, which no "
                    "line of this model reads and the finished frame does not "
                    "hold. The book's digest is over the columns the model's "
                    "numbers rest on and nothing else, so a column that is not "
                    "one of them says the document was edited after it was "
                    "written. Export the model again."
                ),
            )
        )
    return findings


def _book_digest_findings(
    document: dict[str, Any], book: pl.DataFrame | pl.LazyFrame
) -> list[Finding]:
    """Return whether the book the holder supplied is the one the document names.

    The digest is taken again over the supplied data, under the columns the
    document names, by the function the producer took it with. Agreement is
    the document saying, and the holder checking, that it is an account of
    this book; disagreement is a refusal naming both digests, because a
    filing matched to the wrong in-force file is the mistake this reading
    exists to catch.
    """
    stated = document.get("book")
    if not isinstance(stated, dict):
        return []
    digest = stated.get("digest")
    columns = [
        column for column in stated.get("columns") or () if isinstance(column, str)
    ]
    if not isinstance(digest, str):
        detail = digest.get("detail") if isinstance(digest, dict) else None
        why = (
            f"its producer said: {detail}"
            if isinstance(detail, str) and detail
            else "its producer held no book, or could not read the one it held"
        )
        return [
            Finding(
                section="semantic",
                severity="warning",
                where=_BOOK,
                message=(
                    f"This document states no digest of its book -- {why} -- so "
                    "the book you supplied cannot be checked against it. Export "
                    "the model again from the frame built over that book."
                ),
            )
        ]
    held = set(
        book.collect_schema().names()
        if isinstance(book, pl.LazyFrame)
        else book.columns
    )
    missing = [column for column in columns if column not in held]
    if missing:
        return [
            Finding(
                section="semantic",
                severity="error",
                where=_BOOK,
                message=(
                    "The book you supplied holds no "
                    f"{', '.join(repr(column) for column in missing)}, which this "
                    "document's book was digested over, so it is not the book "
                    "this document was built over. Supply the policy data the "
                    "model was run over."
                ),
            )
        ]
    taken = book_of(
        [
            {"id": column, "kind": "input", "column": column, "in_final_schema": True}
            for column in columns
        ],
        book,
    )["digest"]
    if not isinstance(taken, str):
        return [
            Finding(
                section="semantic",
                severity="error",
                where=_BOOK,
                message=(
                    "The book you supplied could not be read under the content "
                    "grammar over the columns this document names "
                    f"({', '.join(columns) or 'none'}), so it cannot be the book "
                    "this document was built over. Supply the policy data the "
                    "model was run over."
                ),
            )
        ]
    if taken == digest:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=_BOOK,
            message=(
                f"This document was built over a book whose digest is {digest}, "
                f"and the book you supplied digests to {taken} over the same "
                f"columns ({', '.join(columns) or 'none'}). It is an account of "
                "other policy data, or the data has moved since the export. "
                "Supply the book the model was run over, or export the model "
                "again over this one."
            ),
        )
    ]


# Where a finding about the selection list sits, for a reader to find it.
_SELECTION: Final[str] = f"/{SELECTION_MEMBER}"

# The three kinds of row-selecting step, and the join type each of the two
# join kinds states in its tree.
_SELECTION_KINDS: Final[frozenset[str]] = frozenset({"filter", "semi", "anti"})


def _selection_steps(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the document's selection entries, or none where it carries none."""
    return _objects(document.get(SELECTION_MEMBER))


def _published_selection(document: dict[str, Any]) -> list[bytes] | None:
    """Return every selection step's published fingerprint, raw, or None if one is not.

    In list order, which is the order the model took the steps and the order
    section 12.4's selection section takes them in.
    """
    digests = [_digest(step.get("fingerprint")) for step in _selection_steps(document)]
    if any(digest is None for digest in digests):
        return None
    return [digest for digest in digests if digest is not None]


def _masked_selection(
    document: dict[str, Any], folded: Mapping[str, bytes]
) -> list[bytes] | None:
    """Return each step's fingerprint over its masked tree, or None if one cannot be.

    The step's local digest over its tree with every content digest masked
    (a semi or anti join's ``right_fingerprint`` is data, as a join's is),
    folded over the masked fingerprints of what it reads.
    """
    masked: list[bytes] = []
    for step in _selection_steps(document):
        tree, kind = step.get("expr"), step.get("kind")
        reads = _strings(step.get("reads"))
        if (
            not isinstance(tree, dict)
            or not isinstance(kind, str)
            or any(read not in folded for read in reads)
        ):
            return None
        try:
            local = selection_local(kind, formulas_tree(op_node_from_json(tree)))
        except (TypeError, ValueError, RecursionError):
            return None
        masked.append(_merkle(local, [folded[read] for read in reads]))
    return masked


def _selection_findings(document: dict[str, Any], known: set[str]) -> list[Finding]:
    """Return what is wrong with the document's account of which rows it valued.

    Each step is held to what section 7.6 says one is: an id counting from
    ``selection:1`` in list order; one of the three kinds, a join kind stating
    the join type it names; reads that resolve to nodes the document carries;
    a tier that is the tree's own; a ``local_fingerprint`` that is the hash of
    the kind and the tree beside it -- the tree travels in both profiles, so
    this is asked of every document -- and a ``fingerprint`` that folds it over
    the published fingerprints of what it reads. A semi or anti join's
    ``right_fingerprint`` is its tree's own, said twice so a reader of the
    list need not parse the tree.
    """
    nodes = {
        node["id"]: node
        for node in _objects(document.get("nodes"))
        if isinstance(node.get("id"), str)
    }
    findings: list[Finding] = []
    for position, step in enumerate(_selection_steps(document), start=1):
        expected = f"{SELECTION_NAMESPACE}{position}"
        where = step.get("id") if isinstance(step.get("id"), str) else expected
        findings.extend(
            Finding(
                section="semantic",
                severity="error",
                where=f"{_SELECTION}/{position - 1}",
                message=(
                    f"Selection step {where!r} {defect} A selection step is the "
                    "record of which policies the model valued, and a reader who "
                    "cannot take it at its word cannot say which rows a total is "
                    "over. Export the model again."
                ),
            )
            for defect in _selection_defects(step, expected, known, nodes)
        )
    return findings


def _selection_defects(
    step: dict[str, Any],
    expected: str,
    known: set[str],
    nodes: Mapping[str, dict[str, Any]],
) -> list[str]:
    """Return each way one selection entry departs from section 7.6, in words."""
    defects: list[str] = []
    if step.get("id") != expected:
        defects.append(
            f"stands at the position whose id is {expected!r}: ids count from "
            "selection:1 in the order the model took the steps."
        )
    kind = step.get("kind")
    tree = step.get("expr")
    if kind not in _SELECTION_KINDS:
        defects.append("states a kind that is not filter, semi or anti.")
        return defects
    reads = _strings(step.get("reads"))
    unknown = [read for read in reads if read not in known]
    if unknown:
        defects.append(
            f"reads {', '.join(repr(read) for read in unknown)}, which no node "
            "of this document is."
        )
    if not isinstance(tree, dict):
        defects.append("carries no predicate tree.")
        return defects
    try:
        decoded = op_node_from_json(tree)
    except (TypeError, ValueError, RecursionError) as refusal:
        defects.append(f"carries a predicate tree this reader cannot parse: {refusal}")
        return defects
    defects.extend(_selection_tree_defects(step, kind, decoded))
    local = selection_local(str(kind), decoded)
    if _digest(step.get("local_fingerprint")) != local:
        defects.append(
            "publishes a local_fingerprint that is not the hash of its kind and "
            "the predicate tree beside it."
        )
    published = [
        _digest(nodes[read].get("fingerprint")) for read in reads if read in nodes
    ]
    stated = _digest(step.get("fingerprint"))
    if (
        not unknown
        and all(digest is not None for digest in published)
        and stated != _merkle(local, [d for d in published if d is not None])
    ):
        defects.append(
            "publishes a fingerprint that does not follow from its "
            "local_fingerprint and the fingerprints of what it reads."
        )
    return defects


def _selection_tree_defects(
    step: dict[str, Any], kind: object, tree: OpNode
) -> list[str]:
    """Return what a step's tree says that the step's own fields contradict."""
    defects: list[str] = []
    if step.get("tier") != tier_of(tree):
        defects.append(
            f"states the tier {step.get('tier')!r}, and its tree's is "
            f"{tier_of(tree)!r}."
        )
    if kind == "filter":
        return defects
    attrs = dict(tree.attrs) if isinstance(tree, Call) and tree.name == "join" else None
    if attrs is None or attrs.get("how") != kind:
        defects.append(
            f"is a {kind} join and its tree is not the join call stating how={kind!r}."
        )
    elif step.get("right_fingerprint") != attrs.get("right_fingerprint"):
        defects.append(
            "states a right_fingerprint that is not the one its join call states."
        )
    return defects


def _audit_surface_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return a warning where an audit artifact carries no as-written formula.

    ``formula`` is the audit surface: it is what a reviewer reads to see the
    calculation, and what a comparison between two quarters is a comparison
    of. Two runs produce a document with none of it -- an export taken with
    source spans switched off, and a run whose statements have no source text
    for the exporter to read at all. Both are permitted, the nulls are honest
    in both, and the result either way is an audit-profile artifact with
    nothing in it for the profile's own reader to read.

    Which of the two happened is not on the wire, so the message names both.
    Naming only the switch would send a reader to turn on what is already on:
    a model built at a prompt or in an interactive session reaches this with
    spans fully on and nothing behind them to record.

    A null ``formula`` on one node is routine and normative: a rename, a
    join, a batch call and a timeline configuration each write one, and so
    does a definition whose source could not be resolved. So the reading is
    about the document rather than the node, and it needs a computed node to
    be about at all -- an artifact with none has no audit surface to be
    short of.
    """
    if document.get("profile") != _PROFILE_AUDIT:
        return []
    computed = [node for node in nodes if node.get("kind") == "computed"]
    if not computed or any(node.get("formula") is not None for node in computed):
        return []
    return [
        Finding(
            section="semantic",
            severity="warning",
            where=_ENVELOPE,
            message=(
                "No computed node in this artifact states a ``formula``, "
                "so the document carries no as-written calculation "
                "anywhere. Usually that is an export taken with source "
                "spans switched off (``GASPATCHIO_SOURCE_SPANS=off``); the "
                "other way to arrive here is a run whose statements have no "
                "source text for the exporter to read -- a model built at a "
                "prompt, in an interactive session, or from a string handed "
                "to ``exec`` -- where the spans are on and there is nothing "
                "behind them to record. The nulls are honest either way -- "
                "but ``formula`` is the audit surface of this profile: it "
                "is the right-hand side a reviewer reads to see the "
                "calculation, and what a comparison between two quarters "
                "is a comparison of. What is left is a graph of identities "
                "with nothing to read beside them. Export the model again "
                "from a file the statements were written in, with source "
                "spans on, if the artifact is for a reader rather than for "
                "a diff of digests."
            ),
        )
    ]


def _objects(section: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    """Return the objects in one array section, ignoring anything else in it.

    Anything else in it is already a schema finding, and a second reading
    that fell over on the same defect would report the shape of this module
    rather than the state of the artifact.
    """
    if not isinstance(section, list):
        return []
    return [entry for entry in section if isinstance(entry, dict)]


def _duplicate_id_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every id two nodes both claim."""
    counted = Counter(node["id"] for node in nodes if isinstance(node.get("id"), str))
    return [
        Finding(
            section="semantic",
            severity="error",
            where=node_id,
            message=(
                f"{count} nodes in this file claim the id {node_id!r}. An id "
                "is a position within one artifact, and it is how every "
                "``reads`` entry and every edge endpoint resolves to the "
                "account it names -- so two nodes holding one id make every "
                "reference to it ambiguous, and an impact cone drawn through "
                "one is drawn through whichever the reader happened to find "
                "first. Export the model again rather than renaming one of "
                "them here."
            ),
        )
        for node_id, count in counted.items()
        if count > 1
    ]


def _unresolved_read_findings(
    nodes: list[dict[str, Any]], known: set[str]
) -> list[Finding]:
    """Return a finding for every name a node reads that this file lacks."""
    findings: list[Finding] = []
    for node in nodes:
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        for name in _strings(node.get("reads")):
            if name in known:
                continue
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=(
                        f"Node {where!r} reads {name!r}, and no node in this "
                        "file gives any account of that name -- it is not a "
                        "column that arrived, not one a calculation defined, "
                        "and not a hole. What a node reads is the audit trail "
                        "a dependency is followed along, so a name nothing "
                        "resolves leaves the reader unable to say where the "
                        "number came from. Export the model again rather than "
                        "adding a node to make the reference resolve."
                    ),
                )
            )
    return findings


def _unresolved_edge_findings(
    edges: list[dict[str, Any]], known: set[str]
) -> list[Finding]:
    """Return a finding for every edge with an endpoint this file lacks."""
    findings: list[Finding] = []
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        missing = [
            end for end in (source, target) if isinstance(end, str) and end not in known
        ]
        if not missing:
            continue
        named = ", ".join(repr(name) for name in missing)
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=f"edge {source!r} -> {target!r}",
                message=(
                    f"The edge from {source!r} to {target!r} names {named}, "
                    "which is not a node this file carries. Every edge runs "
                    "between two accounts the artifact holds -- the node "
                    "whose value was read and the node that read it -- so an "
                    "endpoint the file does not carry leaves the dependency "
                    "dangling, and every impact cone drawn through it stops "
                    "at a name instead of a calculation. Export the model "
                    "again."
                ),
            )
        )
    return findings


def _edge_and_read_findings(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], known: set[str]
) -> list[Finding]:
    """Return a finding wherever the reads and the edges do not say one thing.

    ``reads`` is the lineage a reviewer follows down the page; ``edges`` is
    the same claim drawn as a graph, and section 9 writes one edge per entry
    of the target's ``reads``. Two records of one fact are two chances for
    the file to be read two ways -- an impact cone drawn through the edges
    and a dependency list read off the node would answer the same question
    differently, and neither reader would have any sign the other existed.

    **Presence only.** Whether the edge carries the right
    ``relationship``, and the reading node the right narrowing beside it,
    is a different question and is not asked here. This check compares
    recorded endpoints and reads; it does not recompute relationship or
    subtype from the operation tree. A structurally valid artifact is not
    proof that its dependency classifications implement section 9.

    A pair with an endpoint no node accounts for is left alone, because the
    dangling name is already an error above and a second finding on the same
    defect sends a reader to fix two things.

    **The two directions carry different grades, and the reason is section
    9 rather than the size of the disagreement.** Section 9 writes one edge
    per entry of the target's ``reads``, unconditionally, so a read with no
    edge is a file contradicting the format and is an error -- it sits
    beside two error-grade readings of these same two lists, and no
    conforming producer can emit it. An edge with no read stays a warning
    because section 9's narrowing vocabulary carries two row-shaping kinds
    (``GROUP_BY``, ``SORT``) that no emission rule
    produces yet, and a producer whose model shapes rows in one of them
    could record the dependency as an edge before that settles; refusing it
    would refuse a document the section arguably tolerates. There is no
    matching story in the other direction, and the warning is held open for
    those two rather than because the disagreement is minor. Every
    artifact this package writes states the two lists alike, in both
    directions.
    """
    read_pairs = {
        (name, node["id"])
        for node in nodes
        if isinstance(node.get("id"), str)
        for name in _strings(node.get("reads"))
    }
    edge_pairs = {
        (edge["source"], edge["target"])
        for edge in edges
        if isinstance(edge.get("source"), str) and isinstance(edge.get("target"), str)
    }
    findings = [
        Finding(
            section="semantic",
            severity="error",
            where=target,
            message=_read_with_no_edge(source, target),
        )
        for source, target in sorted(read_pairs - edge_pairs)
        if source in known and target in known
    ]
    findings += [
        Finding(
            section="semantic",
            severity="warning",
            where=f"edge {source!r} -> {target!r}",
            message=_edge_with_no_read(source, target),
        )
        for source, target in sorted(edge_pairs - read_pairs)
        if source in known and target in known
    ]
    return findings


def _read_with_no_edge(source: str, target: str) -> str:
    """Return the remark for a dependency the edge list does not carry."""
    return (
        f"Node {target!r} states that it reads {source!r}, and no edge in "
        "this file runs between the two. The same dependency is recorded "
        "twice on purpose -- once as the lineage a reviewer reads down the "
        "page, once as the graph an impact cone is drawn through -- so a "
        "reader asking what this column depends on and a reader asking what "
        "a change to it would touch get two different answers, and neither "
        "has any sign the other exists. Export the model again rather than "
        "adding the edge here: which kind of read it was is what the edge "
        "carries, and that is the producer's to say."
    )


def _edge_with_no_read(source: str, target: str) -> str:
    """Return the remark for an edge no node's own lineage accounts for."""
    return (
        f"An edge runs from {source!r} to {target!r}, and {target!r} does "
        f"not state {source!r} among what it reads. An edge is one entry of "
        "the target's own ``reads`` drawn as a graph, so an edge with no "
        "entry behind it puts a dependency into every impact cone that the "
        "column itself does not claim -- a change report built on it would "
        "flag work nobody has to do, which is the failure that gets a change "
        "report ignored. Export the model again rather than deleting the "
        "edge here: whether the read is missing or the edge is spurious is "
        "not something this file says."
    )


def _reserved_namespace_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every node in a reserved namespace that is a column."""
    findings: list[Finding] = []
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        for prefix, names in _RESERVED_NAMESPACES:
            if not node_id.startswith(prefix):
                continue
            stated = [
                f"a {field}"
                for field in ("column", "version")
                if node.get(field) is not None
            ]
            if not stated:
                continue
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=node_id,
                    message=(
                        f"Node {node_id!r} is in the reserved {prefix!r} "
                        f"namespace, which names {names}, and it states "
                        f"{' and '.join(stated)}. A node there is not a "
                        "column of the model at all, so both fields are null "
                        "on one -- and the whole point of reserving the "
                        "namespace is that a reader who finds an id in it may "
                        "trust that. A reader taking this node for a column "
                        "would be reading the artifact correctly and getting "
                        "the wrong answer. Export the model again; where a "
                        "column of the model was named into the namespace, "
                        "rename the column first -- the producer refuses one "
                        "at the door that would mint it."
                    ),
                )
            )
    return findings


def _leaf_tier_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every node whose tier contradicts what the node is.

    A tier says how much of a node's own operation tree this format can
    account for, and a leaf has no tree: an arriving column, a column nothing
    accounts for, and a running state are each a node *nothing on the model
    defines*, which is why section 8 states ``formula``, ``origin`` and
    ``tier`` null on one. A tier written there is an accountability claim
    about a calculation that is not in the file, and ``core`` in particular
    reads as the strongest such claim the format can make.

    And the other way round: section 11.2 states a tier on every node that
    has anything to execute, which is every kind but a leaf's. A calculation,
    a compiled rollforward or one of the two payload sections stating a null
    tier says nothing about how much of it the format can account for, and a
    census of the model's tiers can count it nowhere. The schema allows the
    null because a leaf needs it, so the rule is held here. A tier left out
    altogether is the schema's to name, and is not named twice.

    Keyed on what the node is and never on its null ``version``. A compiled
    rollforward and the two payload sections of section 17 also carry a null
    version, and each of them does have a tree and does state a tier -- a
    reading that went by the version would refuse three of the models this
    package ships and both of the hand-built examples.
    """
    findings = [
        Finding(
            section="semantic",
            severity="error",
            where=node["id"],
            message=_leaf_with_a_tier(node["id"], node["kind"], node["tier"]),
        )
        for node in nodes
        if isinstance(node.get("id"), str)
        and node.get("kind") in _LEAF_KINDS
        and node.get("tier") is not None
    ]
    findings.extend(
        Finding(
            section="semantic",
            severity="error",
            where=node["id"],
            message=_calculation_without_a_tier(node["id"], node["kind"]),
        )
        for node in nodes
        if isinstance(node.get("id"), str)
        and node.get("kind") in _KINDS_THAT_COMPUTE
        and "tier" in node
        and node["tier"] is None
    )
    return findings


def _leaf_with_a_tier(node_id: str, kind: Any, tier: Any) -> str:  # noqa: ANN401
    """Return the refusal for a leaf stating a tier."""
    return (
        f"Node {node_id!r} is of kind {kind!r}, which is a node nothing on "
        f"the model defines, and it states ``tier: {tier!r}``. A tier says how "
        "much of a node's operation tree this format can account for, and a "
        "leaf has no tree -- there is nothing to execute, which is why the "
        "field is null on one. What is written here is an accountability "
        "claim about a calculation this file does not carry, and a consumer "
        "counting how much of a model runs in its own engine would count "
        "this node in. Export the model again rather than clearing the "
        "field: a leaf that arrived carrying a tier is a producer disagreeing "
        "with itself about what the node is."
    )


def _calculation_without_a_tier(node_id: str, kind: Any) -> str:  # noqa: ANN401
    """Return the refusal for a node that computes and states no tier."""
    return (
        f"Node {node_id!r} is of kind {kind!r}, which has something to "
        "execute, and it states no tier: ``tier`` is null. Section 11.2 "
        "states one on every node that has anything to execute -- ``core``, "
        "``engine_native`` or ``opaque``, how much of its calculation this "
        "format can account for -- and a null tier is a leaf's, which has "
        "nothing to execute. On a calculation it says nothing about whether "
        "a second implementation could run it, and a census of the model's "
        "tiers can count it nowhere. Export the model again rather than "
        "writing a tier in by hand: a calculation that arrived without one "
        "is a producer that did not say how much of it the format can "
        "account for."
    )


def _ordinal_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every column whose definitions do not count from 1."""
    ordinals: dict[str, list[int]] = defaultdict(list)
    where: dict[str, str] = {}
    for node in nodes:
        column, version = node.get("column"), node.get("version")
        if not isinstance(column, str):
            continue
        # A node nothing defined -- an arriving column, a hole, a running
        # state -- carries a null version and is not one of a column's
        # definitions. ``True`` is an integer in Python and is not an ordinal
        # either; a node carrying one is a schema finding rather than a gap
        # in the numbering.
        if not isinstance(version, int) or isinstance(version, bool):
            continue
        ordinals[column].append(version)
        node_id = node.get("id")
        where.setdefault(column, node_id if isinstance(node_id, str) else _ENVELOPE)

    findings: list[Finding] = []
    for column, seen in ordinals.items():
        expected = list(range(1, len(seen) + 1))
        if sorted(seen) == expected:
            continue
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=where[column],
                message=(
                    f"Column {column!r} is defined here at definition "
                    f"{_ordinals(sorted(seen))}, where the definitions this "
                    "file carries should be numbered "
                    f"{', '.join(str(number) for number in expected)}: "
                    "a column's definitions count from 1 without a gap. Every "
                    "definition the model wrote is a node -- the last is what "
                    "the frame ended up holding, and the ones before it are "
                    "the history a change report is read from -- so a file "
                    "that has lost one cannot say what changed between two "
                    "quarters. Export the model again rather than renumbering "
                    "the definitions that are here."
                ),
            )
        )
    return findings


# Where a finding about the holes section as a whole sits.
_HOLES: Final[str] = "/holes"

# The reasons whose hole stands for a column that arrived, and so carries no
# version, as an arriving column does. The one other reason is a definition.
_UNVERSIONED_REASONS: Final[frozenset[str]] = frozenset({"unrecorded", "rebuilt"})


def _hole_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return what the holes section and the hole nodes say against each other.

    Section 7.1 lists one entry per name the model cannot account for, and
    the entry carries the reason of the first node standing for that name.
    The two are one account read two ways, so they must name the same
    columns, the section must name each once, and each reason must fit the
    node it describes: an overwritten hole is a definition, versioned as one,
    and an unrecorded or rebuilt one stands for a column that arrived and is
    unversioned as an arrival is (sections 7.1, 8 and 8.1).

    The line an overwritten hole carries is not required. The producer
    states it where it found the line, and a write made where no line can be
    read back -- an interactive session, code compiled from a string -- has
    none, as a definition written there has none (section 8).
    """
    first: dict[str, dict[str, Any]] = {}
    for node in nodes:
        column = node.get("column")
        if node.get("kind") == "hole" and isinstance(column, str):
            first.setdefault(column, node)

    findings: list[Finding] = []
    listed: dict[str, str] = {}
    for entry in _objects(document.get("holes")):
        column, reason = entry.get("column"), entry.get("reason")
        if not isinstance(column, str) or not isinstance(reason, str):
            continue  # a schema finding, not this one's
        if column in listed:
            findings.append(_hole_finding(_HOLES, _listed_twice(column)))
            continue
        listed[column] = reason
        standing = first.get(column)
        if standing is None:
            findings.append(_hole_finding(_HOLES, _listed_with_no_hole(column)))
            continue
        message = _reason_against_node(column, reason, standing)
        if message is not None:
            findings.append(_hole_finding(_node_where(standing), message))
    findings.extend(
        _hole_finding(_node_where(node), _hole_not_listed(column, node))
        for column, node in first.items()
        if column not in listed
    )
    return findings


def _node_where(node: dict[str, Any]) -> str:
    """Return a node's id to name in a finding, or the envelope where it has none."""
    node_id = node.get("id")
    return node_id if isinstance(node_id, str) else _ENVELOPE


def _hole_finding(where: str, message: str) -> Finding:
    """Return one semantic error about the holes section or a hole node."""
    return Finding(section="semantic", severity="error", where=where, message=message)


def _reason_against_node(column: str, reason: str, node: dict[str, Any]) -> str | None:
    """Return why ``reason`` does not fit the first hole node of ``column``, or None."""
    version = node.get("version")
    versioned = isinstance(version, int) and not isinstance(version, bool)
    node_id = node.get("id")
    if reason == "overwritten" and not versioned:
        return (
            f"The holes section says {column!r} was overwritten, and the first "
            f"node standing for it, {node_id!r}, carries no version. An "
            "overwritten hole is the definition a write past the producer's "
            "interfaces made, and carries that definition's ordinal "
            "(sections 7.1 and 8.1); an unversioned hole stands for a column "
            "that arrived. Export the model again rather than editing the "
            "reason or the node."
        )
    if reason in _UNVERSIONED_REASONS and versioned:
        return (
            f"The holes section says {column!r} is {reason}, and the first node "
            f"standing for it, {node_id!r}, carries version {version}. Only an "
            "overwritten hole is a definition with an ordinal; an unrecorded "
            "or rebuilt hole stands for a column that arrived, and is "
            "unversioned as an arriving column is (sections 7.1 and 8). Export "
            "the model again rather than editing the reason or the node."
        )
    return None


def _listed_twice(column: str) -> str:
    """Return the refusal for a holes section naming one column twice."""
    return (
        f"The holes section lists {column!r} more than once. It holds one entry "
        "per name the model cannot account for, carrying the reason of the "
        "first node standing for it (section 7.1), and the graph's identity "
        "takes each name once. Export the model again."
    )


def _listed_with_no_hole(column: str) -> str:
    """Return the refusal for an entry no hole node stands behind."""
    return (
        f"The holes section lists {column!r}, and no hole node in this file "
        "stands for that column. The section restates what the hole nodes "
        "say (section 7.1), so an entry with no node behind it is an account "
        "of a column the graph does not draw. Export the model again."
    )


def _hole_not_listed(column: str, node: dict[str, Any]) -> str:
    """Return the refusal for a hole node the holes section leaves out."""
    return (
        f"Node {node.get('id')!r} is a hole for the column {column!r}, and the "
        "holes section has no entry for it. The section lists every name the "
        "model cannot account for (section 7.1), so a reader who reads it "
        "alone would take this column as accounted for. Export the model "
        "again."
    )


def _increment_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return what is wrong with a rollforward's account of its own movements.

    Two claims the schema cannot make. The array's order is the order the
    increments apply, and ``ordinal`` restates it -- a restatement is only
    worth carrying if it is checked, so it is checked here, exactly as a
    column's definition ordinals are. And a label is a name a reader cites
    one movement by, so two movements may not share one; JSON Schema 2020-12
    has no cross-item uniqueness on a member, which is why this lives in the
    semantic layer rather than in a schema keyword that does not exist.

    Neither is a claim about the compiler. A model whose labels collide
    still compiles and still runs; what it does not get is a summary, because
    a producer omits the field rather than writing an array a reader could
    not cite one movement of.
    """
    findings: list[Finding] = []
    for node in nodes:
        increments = node.get("increments")
        if not isinstance(increments, list):
            continue
        where = node.get("id")
        where = where if isinstance(where, str) else _ENVELOPE
        findings.extend(_increment_ordinal_findings(increments, where))
        findings.extend(_increment_label_findings(increments, where))
    return findings


def _increment_ordinal_findings(increments: list[Any], where: str) -> list[Finding]:
    """Return a finding where the ordinals do not restate the array's order."""
    stated = [
        increment.get("ordinal") if isinstance(increment, dict) else None
        for increment in increments
    ]
    expected = list(range(1, len(increments) + 1))
    if stated == expected:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=where,
            message=(
                f"This compilation's movements are numbered "
                f"{stated} where the array holds them in the order "
                f"{expected}: an increment's ordinal counts from 1 in the "
                "order the increments apply, which is the order the array is "
                "in. The order is the calculation -- movement 2 lands on the "
                "balance movement 1 left -- so an ordinal disagreeing with a "
                "position leaves a reader citing one movement and reading "
                "another. The array order is what is normative; export the "
                "model again rather than renumbering what is here."
            ),
        )
    ]


def _increment_label_findings(increments: list[Any], where: str) -> list[Finding]:
    """Return a finding for every label two of one compilation's movements share."""
    seen: dict[str, int] = {}
    repeated: dict[str, list[int]] = defaultdict(list)
    for position, increment in enumerate(increments, start=1):
        if not isinstance(increment, dict):
            continue
        label = increment.get("label")
        if not isinstance(label, str):
            continue
        if label in seen:
            if not repeated[label]:
                repeated[label].append(seen[label])
            repeated[label].append(position)
        else:
            seen[label] = position
    return [
        Finding(
            section="semantic",
            severity="error",
            where=where,
            message=(
                f"Two of this compilation's movements are labelled "
                f"{label!r} -- increments "
                f"{', '.join(str(position) for position in positions)}. A "
                "label is a name a model reads one increment back by and a "
                "reader cites one movement by, so a label shared is a "
                "citation that resolves to two movements. A producer that "
                "cannot give every movement its own name omits the summary "
                "rather than writing one that cannot be cited; the "
                "compilation itself is unaffected, and a model whose labels "
                "collide still compiles and still runs."
            ),
        )
        for label, positions in repeated.items()
    ]


def _ordinals(numbers: Sequence[int]) -> str:
    """Return ``numbers`` as prose: ``ordinal 2`` or ``ordinals 1, 3``."""
    named = ", ".join(str(number) for number in numbers)
    return f"ordinal {named}" if len(numbers) == 1 else f"ordinals {named}"


def _movement_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return what is wrong with the amounts a compilation says it moved.

    One claim, and it is the claim the whole member exists to support: the
    steps a compilation carries amounts for are exactly the steps it says it
    applies. A reader closing ``closing = opening + sum of movements``
    without a residual is relying on that and on nothing else, and a member
    short of one step would let them close an arithmetic that does not add
    up while every individual number in it was quoted correctly.

    The key each step is named by is the kernel's and is derived here rather
    than trusted: the author's ``label`` where the step carries one, and
    ``{kind}@{ordinal}`` where it does not -- the operation lowercased and
    the same ordinal the summary already numbers it at. So a document whose
    movements name a step the summary does not, or omit one the summary
    does, is refused by the two reading each other.

    Checked only where the compilation states its summary. ``increments`` is
    absent in four cases (section 16) and there is then nothing to join to;
    what remains true of the member is what the schema already says of it.
    """
    findings: list[Finding] = []
    for node in nodes:
        movements = node.get("movements")
        increments = node.get("increments")
        if not isinstance(movements, dict) or not isinstance(increments, list):
            continue
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        declared = _the_kernel_names_these(increments)
        carried = set(movements)
        missing = [key for key in declared if key not in carried]
        invented = sorted(carried - set(declared))
        if missing or invented:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=_movements_and_increments_disagree(
                        where, declared, missing, invented
                    ),
                )
            )
    return findings


def _the_kernel_names_these(increments: list[Any]) -> list[str]:
    """Return the key each declared step's movement is named under."""
    named: list[str] = []
    for position, increment in enumerate(increments, start=1):
        if not isinstance(increment, dict):
            continue
        label = increment.get("label")
        if isinstance(label, str) and label:
            named.append(label)
            continue
        operation = increment.get("operation")
        kind = operation.lower() if isinstance(operation, str) else "step"
        ordinal = increment.get("ordinal")
        at = ordinal if isinstance(ordinal, int) else position
        named.append(f"{kind}@{at}")
    return named


def _movements_and_increments_disagree(
    where: str, declared: Sequence[str], missing: Sequence[str], invented: Sequence[str]
) -> str:
    """Return the refusal for movements that are not the steps of the chain."""
    said = []
    if missing:
        said.append(f"nothing is carried for {', '.join(repr(key) for key in missing)}")
    if invented:
        said.append(
            f"an amount is carried for {', '.join(repr(key) for key in invented)}, "
            "which this compilation does not apply"
        )
    return (
        f"Node {where!r} carries amounts that are not the movements it says "
        f"it applies: {'; and '.join(said)}. The steps this chain applies are "
        f"{', '.join(repr(key) for key in declared)} -- the author's label "
        "where a step carries one, and the kernel's ``{kind}@{ordinal}`` "
        "where it does not. Every step of a chain emits its movement, which "
        "is what lets a reader write ``closing = opening + sum of "
        "movements`` with no residual term; a member short of one would "
        "close that arithmetic on a number nobody accounted for. Export the "
        "model again rather than editing either list."
    )


def _retrack_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return what a compilation's movements say against the run they came off.

    **A movement on the file is a movement of the run the state came from.**
    A producer reaches the amounts by re-tracking the compiled machine, and
    the machine names its operands by column name -- so a producer that
    evaluates that expression against the finished frame, rather than against
    the versions the compilation bound, publishes a movement schedule, a
    closing balance and a check line that all agree with each other and none
    of which happened, the moment the model writes over an input after
    pulling its state back out. Every other reading in this specification
    passes such a document: the fingerprints hold, the axis is as long as the
    enrichment, and ``closing = opening + sum of movements`` closes, because
    both sides were re-computed together on the wrong values.

    The one witness left in the file is outside the re-track. A line reading
    ``compiled.expr_for("av")`` **is** that balance written onto the frame,
    by the run that actually happened, so the state's closing balance and
    that column are one series read twice and a disagreement between them is
    the producer quoting two runs. That is the reading below.

    The second is about an absence. A producer that cannot bind the versions
    honestly declines the amounts, which is the right answer and an odd
    document to meet: a compilation that says which steps it applies and
    carries none of what they moved. The warning says why, so the absence is
    a statement rather than a gap.
    """
    width = policy_axis_width(document)
    stated = {node["id"]: node for node in nodes if isinstance(node.get("id"), str)}
    return [
        *_balance_disagreement_findings(nodes, stated, width),
        *_movements_declined_findings(nodes, stated, width),
    ]


def _balance_disagreement_findings(
    nodes: list[dict[str, Any]], stated: dict[str, dict[str, Any]], width: int
) -> list[Finding]:
    """Return a finding per state whose balance its own column is not.

    Asked only of a **bare** extraction, and the operation tree is what says
    which those are. ``extracts`` records the compilation a formula reached,
    which a formula that wrapped the extraction in arithmetic reached just as
    honestly -- ``expr_for("av") + 1``, two balances added together -- and
    those columns are not the balance and must not be read as one. A document
    carrying no tree for its nodes carries nothing that tells the two apart,
    so this is a reading the ``executable`` profile earns and the ``audit``
    profile does not; the producer's own case for it is the same either way.

    Asked only where the compilation carries ``movements``, because that is
    what the reading is a falsification of: a compilation whose amounts are
    absent quotes one run and no other, and its balance stands on the
    extraction it was read from.
    """
    findings: list[Finding] = []
    for node in nodes:
        for extraction in _extractions_of(node.get("extracts")):
            if not _is_a_bare_extraction(node):
                continue
            compilation = stated.get(_text_member(extraction, "compilation"), {})
            balance = stated.get(
                f"{STATE_NAMESPACE}{_text_member(extraction, 'state')}", {}
            )
            if compilation.get("movements") is None or not balance:
                continue
            findings.extend(_one_balance_findings(node, balance, width))
    return findings


def _one_balance_findings(
    node: dict[str, Any],
    balance: dict[str, Any],
    width: int,
) -> list[Finding]:
    """Return the finding where one state and its own column disagree."""
    for position in range(width):
        held = _at(balance, "value_sample", position, width)
        wrote = _at(node, "value_sample", position, width)
        if held is None or wrote is None:
            continue
        apart = _furthest_apart(held, wrote)
        if apart is None or apart <= _THE_WIRES_LAST_DECIMAL:
            continue
        return [
            Finding(
                section="semantic",
                severity="error",
                where=str(balance.get("id")),
                message=_a_balance_its_own_column_is_not(
                    balance, node, position, apart
                ),
            )
        ]
    return []


def _is_a_bare_extraction(node: dict[str, Any]) -> bool:
    """Whether this node's whole calculation is the state call and nothing else."""
    tree = node.get("expr")
    return (
        isinstance(tree, dict)
        and tree.get("op") == "call"
        and tree.get("name") == _THE_STATE_CALL
    )


def _text_member(record: dict[str, Any], name: str) -> str:
    """Return one string member of an ``extracts`` entry, or the empty string."""
    held = record.get(name)
    return held if isinstance(held, str) else ""


def _furthest_apart(held: Any, wrote: Any) -> float | None:  # noqa: ANN401 — two sampled values, of whatever the model held
    """Return how far two sampled balances are at their furthest, or None.

    None where the two are not a pair of numbers this reading can measure --
    a null inside a timeline, two timelines of different lengths, anything
    that is not a number at all. A shape that cannot be measured is not a
    disagreement: this reading refuses on numbers it read, and the readings
    that hold a document's shapes to each other are elsewhere.
    """
    if isinstance(held, list) and isinstance(wrote, list):
        if len(held) != len(wrote):
            return None
        apart = [
            _furthest_apart(one, other) for one, other in zip(held, wrote, strict=True)
        ]
        measured = [one for one in apart if one is not None]
        return max(measured) if len(measured) == len(apart) and measured else None
    if isinstance(held, bool) or isinstance(wrote, bool):
        return None
    if not isinstance(held, (int, float)) or not isinstance(wrote, (int, float)):
        return None
    return abs(float(held) - float(wrote))


def _a_balance_its_own_column_is_not(
    balance: dict[str, Any],
    node: dict[str, Any],
    position: int,
    apart: float,
) -> str:
    """Return the refusal for a state and its own column quoting two runs."""
    return (
        f"The running state {str(balance.get('id'))!r} carries a closing "
        f"balance that {str(node.get('id'))!r} -- the column this document "
        f"says materialises it -- does not: at entry {position} of the axis "
        f"the two are {apart:.6g} apart at their furthest, where one series "
        "read twice is equal to the bit. A line assigning a compilation's state IS "
        "that balance written onto the frame, so the two are one series read "
        "twice and nothing honest can separate them. What separates them is "
        "a producer that re-tracked this compilation's movements against the "
        "finished frame instead of against the versions the compilation "
        "bound: the movements beside this state, its balance and the check "
        "line over them are then all one run and the model's own column is "
        "another, and every other reading in this specification passes the "
        "result. Export the model again with a producer that binds the "
        "re-track to the versions each compilation read, or one that "
        "declines the amounts where they cannot be bound."
    )


def _movements_declined_findings(
    nodes: list[dict[str, Any]], stated: dict[str, dict[str, Any]], width: int
) -> list[Finding]:
    """Return a warning per compilation that could be read and was not.

    ``increments`` present says the producer reached the compiled machine;
    ``movements`` absent beside it says it did not read what the steps moved.
    Both are permitted and the combination is honest, but it is the one
    absence a reader would otherwise have to guess at -- the amounts are the
    question a rollforward is audited by, and a reader who cannot tell a
    declined re-track from a producer that never implemented one is left to
    derive a waterfall from the balances, which is the identity solved for
    the terms nobody quoted.

    Asked only of a document carrying values, because ``movements`` is
    enrichment: a document stating no evaluation context carries none of it
    by rule, and a warning there would be this reading asking an audit
    structure for a number it never claimed.
    """
    findings: list[Finding] = []
    for node in nodes:
        increments = node.get("increments")
        if not isinstance(increments, list):
            continue
        if node.get("movements") is not None:
            continue
        if not _carries_a_balance(node, stated, width):
            continue
        findings.append(
            Finding(
                section="semantic",
                severity="warning",
                where=str(node.get("id")),
                message=_movements_the_producer_could_not_read(node, increments),
            )
        )
    return findings


def _carries_a_balance(
    node: dict[str, Any], stated: dict[str, dict[str, Any]], width: int
) -> bool:
    """Whether this compilation's states carry a value anywhere on the axis."""
    for state in _strings(node.get("states")):
        balance = stated.get(f"{STATE_NAMESPACE}{state}@{_THE_CLOSE}")
        if balance is None:
            continue
        if any(
            _at(balance, "value_sample", position, width) is not None
            for position in range(width)
        ):
            return True
    return False


def _movements_the_producer_could_not_read(
    node: dict[str, Any], increments: list[Any]
) -> str:
    """Explain a compilation that states its steps and none of their amounts."""
    declared = ", ".join(repr(key) for key in _the_kernel_names_these(increments))
    return (
        f"The compilation {str(node.get('id'))!r} says it applies "
        f"{declared} and carries the amount of none of them, in a document "
        "that carries this run's values. The producer reached the compiled "
        "machine -- it wrote ``increments`` -- and could not read what the "
        "steps moved off the run: either a version this compilation bound is "
        "no longer on the finished frame, because a later line wrote over a "
        "column the machine read, or the machine's own definition refused to "
        "re-compile with tracking on. The balances beside it are still this "
        "run's. The movement schedule is absent rather than derived, because "
        "a waterfall drawn from balances alone is the identity solved for "
        "the terms nobody quoted, and it would be true by construction "
        "whatever the machine did. To put the amounts on the file, run the "
        "model so that the columns the compilation reads still hold, at the "
        "end, the values it was compiled against."
    )


def _extraction_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return what is wrong with a column's account of the balance it holds.

    A column that materialises a compilation's running balance says so, and
    the saying is checked against the two records that were already there.
    It must **read** the compilation it names: ``extracts`` and the
    ``reads`` entry are one claim said twice, the second being what an edge
    walk follows, and a column pointing a reader at a node its own edges do
    not connect it to is worse than one that said nothing. And the state it
    names must be one the compilation **declares**: a compilation carries
    the balances in its ``states`` and no others.

    The second reading is skipped where the compilation states no ``states``
    -- a producer that could not reach the compiled artefact omits the field
    (§16), and a check that read the absence as an empty list would refuse
    the one document the omission exists for.
    """
    stated = {node["id"]: node for node in nodes if isinstance(node.get("id"), str)}
    findings: list[Finding] = []
    for node in nodes:
        where = node.get("id")
        for extraction in _extractions_of(node.get("extracts")):
            findings.extend(
                _one_extraction_findings(
                    extraction,
                    node,
                    stated,
                    where if isinstance(where, str) else _ENVELOPE,
                )
            )
    return findings


def _extractions_of(stated: Any) -> list[dict[str, Any]]:  # noqa: ANN401
    """Return what one node states it extracts, one or many, as a list.

    The wire writes the single case as the object it is and the plural case
    as an array, so a reading that handled only one of the two shapes would
    check half the documents and pass the other half unread.
    """
    if isinstance(stated, dict):
        return [stated]
    if isinstance(stated, list):
        return [entry for entry in stated if isinstance(entry, dict)]
    return []


def _one_extraction_findings(
    extraction: dict[str, Any],
    node: dict[str, Any],
    stated: dict[str, dict[str, Any]],
    where: str,
) -> list[Finding]:
    """Return both readings of one extraction a column states."""
    compilation = extraction.get("compilation")
    state = extraction.get("state")
    if not isinstance(compilation, str) or not isinstance(state, str):
        return []
    findings: list[Finding] = []
    if compilation not in _strings(node.get("reads")):
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=where,
                message=_extracts_what_it_does_not_read(
                    compilation, state, _strings(node.get("reads"))
                ),
            )
        )
    declared, _, _ = state.partition("@")
    carried = stated.get(compilation, {}).get("states")
    if isinstance(carried, list) and declared not in carried:
        findings.append(
            Finding(
                section="semantic",
                severity="error",
                where=where,
                message=_extracts_a_balance_the_compilation_does_not_carry(
                    compilation, state, declared, _strings(carried)
                ),
            )
        )
    return findings


def _extracts_what_it_does_not_read(
    compilation: str, state: str, reads: Sequence[str]
) -> str:
    """Explain that a column names a compilation its own edges do not reach."""
    named = ", ".join(repr(read) for read in reads) or "nothing"
    return (
        f"This column states that it materialises the running balance "
        f"{state!r} of {compilation!r}, and {compilation!r} is not among "
        f"what it reads: {named}. A column that materialises a balance "
        "reads the compilation carrying it, and the two records are one "
        "claim said twice -- the ``reads`` entry is what an edge walk "
        "follows, and this field is what says which balance came back "
        "along it. As it stands, a reviewer asking what moves when that "
        "balance moves is sent to a node this document does not connect "
        "this column to. Export the model again rather than editing "
        "either half of the claim here."
    )


def _extracts_a_balance_the_compilation_does_not_carry(
    compilation: str, state: str, declared: str, carried: Sequence[str]
) -> str:
    """Explain that a column names a balance the compilation does not declare."""
    named = ", ".join(repr(state) for state in carried) or "no states at all"
    return (
        f"This column states that it materialises the running balance "
        f"{state!r} of {compilation!r} -- the state {declared!r}, read at "
        f"the point after the '@' -- and that compilation declares "
        f"{named}. A compilation carries the balances it declares and no "
        "others, so this names a balance nothing in this document holds, "
        "and the forward audit question asked of this column would open "
        "at a state that is not there. Export the model again rather than "
        "renaming the state here: which balances a compilation carries is "
        "a fact about the compiled state machine, not about this record."
    )


def _cycle_findings(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]], known: set[str]
) -> list[Finding]:
    """Return a finding if the model's account of itself runs in a circle.

    One finding rather than one per loop. A cycle voids the evaluation order
    of everything downstream of it, so the second loop is read after the
    first has been broken and the file exported again -- and a reader handed
    a list of loops has no way to tell which of them the others are an echo
    of.
    """
    dependencies: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source, target = edge.get("source"), edge.get("target")
        if source in known and target in known:
            dependencies[str(source)].append(str(target))
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        for name in _strings(node.get("reads")):
            if name in known:
                dependencies[name].append(node_id)

    order = [node["id"] for node in nodes if isinstance(node.get("id"), str)]
    cycle = _one_cycle(order, dependencies)
    if cycle is None:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=cycle[0],
            message=(
                "The model's account of itself runs in a circle: "
                f"{_loop(cycle)}. A calculation graph is read in "
                "dependency order, so a column that reaches its own result "
                "-- directly, or round a loop of others -- has no order to be "
                "evaluated in and no answer a reviewer can follow. Where the "
                "dependency is genuinely on an earlier period, read that "
                "period rather than the column ("
                "``.projection.previous_period()``); where a within-period "
                "charge genuinely depends on the running balance, that is the "
                "case a rollforward exists for."
            ),
        )
    ]


def _loop(cycle: Sequence[str]) -> str:
    """Return the loop as prose, however many columns it runs through.

    A finding is something a reader reads, so a loop longer than a reader
    can hold is given at both ends with a count of what sits between them:
    where it starts, where it closes, and how much of the model is caught in
    it. No producer can write a loop at all, but a file is a thing that can
    be edited after it was written, and a hand-edited one has no size the
    format promises. The ends are what carry the shape -- the first id is
    where the walk met the circle and the last is that same id again, closing
    it -- so they are the half that is kept.
    """
    if len(cycle) <= _CYCLE_SHOWN:
        return " -> ".join(cycle)
    ends = _CYCLE_SHOWN // 2
    return (
        f"{' -> '.join(cycle[:ends])} -> ... and {len(cycle) - _CYCLE_SHOWN} "
        f"more in the loop ... -> {' -> '.join(cycle[-ends:])}"
    )


def _one_cycle(
    order: Sequence[str], dependencies: dict[str, list[str]]
) -> list[str] | None:
    """Return the first cycle a depth-first walk meets, or None if there is none.

    Iterative rather than recursive: a model is allowed to be a long chain of
    columns, and a reader that fell over on a deep one would refuse an
    artifact for being large rather than for being wrong.
    """
    state: dict[str, int] = {}
    for root in order:
        if state.get(root, _UNVISITED) != _UNVISITED:
            continue
        state[root] = _ON_THE_PATH
        path = [root]
        stack: list[tuple[str, Iterator[str]]] = [(root, iter(dependencies[root]))]
        while stack:
            node, remaining = stack[-1]
            stepped = False
            for nxt in remaining:
                if state.get(nxt, _UNVISITED) == _ON_THE_PATH:
                    return [*path[path.index(nxt) :], nxt]
                if state.get(nxt, _UNVISITED) == _UNVISITED:
                    state[nxt] = _ON_THE_PATH
                    path.append(nxt)
                    stack.append((nxt, iter(dependencies[nxt])))
                    stepped = True
                    break
            if not stepped:
                state[node] = _SETTLED
                path.pop()
                stack.pop()
    return None


def _facet_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return everything the two facet declaration lists get wrong.

    The required list first, because a name there this build does not know
    refuses the artifact outright: the producer has said the file does not
    mean what it appears to without that facet, and reading it anyway would
    be reading a document the producer did not write.

    Then the three ways the lists and the document can disagree, written so
    that one disagreement is one finding rather than two. Section 6 has
    ``facets_used`` naming every facet present anywhere, and anything
    required announced -- so a required facet the file announces and does not
    carry is caught as an announcement with nothing behind it, one it carries
    and does not announce is caught as a facet nobody announced, and one that
    is neither announced nor carried is the case only the required list can
    see. Between them, a required facet is announced and present, or the
    artifact is refused.
    """
    required = _strings(document.get("facets_required"))
    declared = set(_strings(document.get("facets_used")))
    carried: dict[str, str] = {}
    for name, where in _facets_carried(document, nodes):
        carried.setdefault(name, where)

    findings = [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=(
                f"The facet {name!r} is named in ``facets_required`` and this "
                "build does not understand it. The producer has said the "
                "artifact does not mean what it appears to mean without that "
                "facet, so reading it anyway would be reading a document the "
                "producer did not write. This build understands "
                f"{', '.join(sorted(KNOWN_FACETS))}. Read the file with a "
                f"consumer that understands {name!r}."
            ),
        )
        for name in required
        if name not in KNOWN_FACETS
    ]
    findings += [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=(
                f"The facet {name!r} is named in ``facets_required`` and this "
                "file neither announces it in ``facets_used`` nor carries it "
                "-- not on the envelope, and not on any node. Required is the "
                "producer saying the artifact does not mean what it appears "
                "to mean without that facet, so a reader that understands the "
                "name has nothing here to read the document under, and a "
                "reader that does not is refused the file over something that "
                "is not in it. Anything required is announced, and anything "
                "announced is carried. Export the model again."
            ),
        )
        for name in required
        if name in KNOWN_FACETS and name not in declared and name not in carried
    ]
    findings += [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=(
                f"The facet {name!r} is named in ``facets_used`` and nothing "
                "in this file carries it -- not the envelope, and not any "
                "node. That list is what a consumer reads to see what it is "
                "about to meet without walking the whole document first, so a "
                "name with nothing behind it sends a reader looking for "
                "something the file does not hold. Export the model again."
            ),
        )
        for name in sorted(declared - set(carried))
    ]
    findings += [
        Finding(
            section="semantic",
            severity="error",
            where=carried[name],
            message=(
                f"The facet {name!r} is carried at {carried[name]} and is not "
                "named in ``facets_used``. That list is read instead of the "
                "whole document, so a facet missing from it reaches no "
                "consumer that trusts the list -- and a reader that does not "
                "know the facet is also the reader obliged to carry it "
                "through a round-trip unchanged. Export the model again."
            ),
        )
        for name in sorted(set(carried) - declared)
    ]
    return findings


def _facets_carried(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> Iterator[tuple[str, str]]:
    """Yield every facet the document actually carries, and where it sits."""
    envelope = document.get("facets")
    if isinstance(envelope, dict):
        for name in envelope:
            if isinstance(name, str):
                yield name, _ENVELOPE
    for node in nodes:
        on_node = node.get("facets")
        node_id = node.get("id")
        if not isinstance(on_node, dict):
            continue
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        for name in on_node:
            if isinstance(name, str):
                yield name, where


def _period_offset_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return everything wrong with the period a read says it was read at.

    ``offset`` is the one member of the narrowing facet this specification
    adds to OpenLineage's own, and it is the answer to "this month's
    reserve reads last month's -- show me which cell". A file that
    mis-states it does not fail to answer; it answers wrongly, and points
    a reviewer at a period the model never read.

    Three ways to mis-state it, and each is refused rather than warned
    about. A distance that is not a whole number of periods is not a
    period. A zero is a read of the period being computed, which is said
    by carrying no ``offset`` -- and two spellings of the commonest read
    in any model is two shapes for a consumer to recognise where there
    should be one. And an offset says which period a *value* came from,
    so it goes with ``TRANSFORMATION`` and with nothing else: a lookup
    key, a conditional's test and an operand folded across the whole run
    are none of them a value narrowed by a distance.

    One finding per read, because the three defects are three readings of
    one field and a reader sent to fix it twice fixes it once.
    """
    findings: list[Finding] = []
    for where, source, narrowing in _narrowings_carried(nodes):
        if _OFFSET not in narrowing:
            continue
        stated = narrowing[_OFFSET]
        if isinstance(stated, bool) or not isinstance(stated, int):
            message = _offset_that_is_not_a_whole_number(source, stated)
        elif stated == 0:
            message = _offset_of_no_periods(source)
        elif narrowing.get("subtype") != _TRANSFORMATION:
            message = _offset_beside_a_narrowing_that_is_not_one(
                source, narrowing.get("subtype")
            )
        else:
            continue
        findings.append(
            Finding(section="semantic", severity="error", where=where, message=message)
        )
    return findings


def _period_window_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return every window that states no period a read could have reached.

    ``periods`` is the answer to "does this reserve read the same periods
    as the workbook's column?", and a window whose start comes after its
    end answers it with a run that holds no period at all -- a cumulative
    read written ``{from: 0, to: -1}``, or a run that starts at the last
    period and ends before it. That is a file mis-stating a read rather
    than one declining to state it, and it is refused. A bound that is
    neither a whole number nor an end of the run is the schema's to refuse,
    and is not reported a second time here.
    """
    findings: list[Finding] = []
    for where, source, narrowing in _narrowings_carried(nodes):
        window = narrowing.get(_PERIODS)
        if not isinstance(window, dict):
            continue
        start, end = window.get("from"), window.get("to")
        if not (_is_bound(start) and _is_bound(end)):
            continue
        if _runs_backwards(start, end):
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=_window_that_runs_backwards(source, start, end),
                )
            )
    return findings


def _is_bound(bound: object) -> bool:
    """Return whether ``bound`` is a whole number of periods or an end of the run."""
    if isinstance(bound, bool):
        return False
    return isinstance(bound, int) or bound in _RUN_ENDS


def _runs_backwards(start: object, end: object) -> bool:
    """Return whether a window's start comes after its end for every period."""
    if isinstance(start, int) and isinstance(end, int):
        return start > end
    return (start == "last" and end != "last") or (end == "first" and start != "first")


def _window_that_runs_backwards(source: str, start: object, end: object) -> str:
    """Return the remark for a window that holds no period."""
    return (
        f"The read of {source!r} states the periods {{from: {start!r}, to: "
        f"{end!r}}}, and that run starts after it ends, so it holds no period "
        "the read could have reached. A window is the run of the operand one "
        "period of the answer reads -- a cumulative sum's is {from: 'first', "
        "to: 0}, a remaining sum's {from: 0, to: 'last'} -- and a read of no "
        "period is not a read. Export the model again rather than editing the "
        "bounds here: which periods a read reached is the producer's to say."
    )


def _narrowings_carried(
    nodes: list[dict[str, Any]],
) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield each narrowing in the transformation facet, and the read it narrows.

    Three values: the node that did the reading, the node whose value it
    read, and the narrowing object itself. Anything not shaped like the
    facet is skipped rather than reported -- the schema reading has said
    so already, and a second finding on one defect sends a reader to fix
    two things.
    """
    for node in nodes:
        facets = node.get("facets")
        if not isinstance(facets, dict):
            continue
        facet = facets.get(_COLUMN_TRANSFORMATION_FACET)
        if not isinstance(facet, dict):
            continue
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        for read in _objects(facet.get("reads")):
            source = read.get("source")
            named = source if isinstance(source, str) else _ENVELOPE
            for narrowing in _objects(read.get("transformations")):
                yield where, named, narrowing


def _offset_that_is_not_a_whole_number(source: str, stated: Any) -> str:  # noqa: ANN401
    """Return the remark for a period distance that is not a number of periods."""
    return (
        f"The read of {source!r} states an ``offset`` of {stated!r}, and an "
        "offset is a whole number of periods: the distance from the row "
        "being computed to the row the value came from, so t-1 is -1 and "
        "t+1 is +1. Half a period, a name or a null is not a period this "
        "projection has. A null is not 'no offset' either -- a read of the "
        "period being computed carries no ``offset`` at all, and that "
        "absence is what says so. Export the model again rather than "
        "editing the value here: which period a read read is the "
        "producer's to say."
    )


def _offset_of_no_periods(source: str) -> str:
    """Return the remark for an offset of zero periods."""
    return (
        f"The read of {source!r} states an ``offset`` of 0, which is a read "
        "of the period being computed -- and that is said by carrying no "
        "``offset`` at all. Written both ways, the commonest read in any "
        "model has two shapes for a consumer to recognise, and a reviewer "
        "is left asking whether the zero meant something the absence does "
        "not. Export the model again: an offset is written only where the "
        "value came from another period."
    )


def _offset_beside_a_narrowing_that_is_not_one(source: str, subtype: Any) -> str:  # noqa: ANN401
    """Return the remark for an offset on a read whose value did not flow."""
    return (
        f"The read of {source!r} states an ``offset`` beside the narrowing "
        f"{subtype!r}, and an offset goes with 'TRANSFORMATION' and with "
        "nothing else. It says which period a value came from, and this "
        "narrowing says the value did not come that way: a lookup key "
        "found the rate rather than being in it, a conditional's test "
        "chose a branch, and an operand folded across the whole run is in "
        "every period's answer rather than in one period's. Export the "
        "model again rather than deleting the offset here -- whether the "
        "narrowing or the offset is the wrong one is not something this "
        "file says."
    )


def _settings_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return everything wrong with the convention a node says it ran under.

    ``settings`` is the timing convention of the accumulation a node's
    whole calculation is, quoted from the operation's own attributes. It
    exists because the figures alone do not say which convention a column
    was written under, and a flat-rate test can pass a model converted
    wrongly between the two: a survival curve struck on the wrong one can
    pass every test the model has, and the record is where the mistake is
    caught. A record
    that states the convention wrongly is worse than one stating none --
    a reviewer reads it, finds the arithmetic consistent with it, and has
    checked the wrong convention.

    Four readings, and each refuses rather than warns. A node with nothing
    to execute has no operation to have configured. An empty object claims
    an operation that stated no convention, which neither of the two is. A
    key set outside the two shapes is settings for an operation this
    revision does not carry -- or one of the two with a key missing or a
    key too many, which is the same sentence to a reader who cannot tell
    which. And a value outside what its own setting admits is a convention
    named in a word the format does not define.

    One finding per node, first defect only: the four are four readings of
    one object, and a reader sent to fix it four times fixes it once.
    """
    findings: list[Finding] = []
    for node in nodes:
        if _SETTINGS not in node:
            continue
        stated = node[_SETTINGS]
        # Anything but an object is a schema finding already, and a second
        # reading falling over on it would report this module rather than
        # the artifact.
        if not isinstance(stated, dict):
            continue
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        message = _settings_defect(where, node.get("kind"), stated)
        if message is None:
            continue
        findings.append(
            Finding(section="semantic", severity="error", where=where, message=message)
        )
    return findings


def _settings_defect(where: str, kind: Any, stated: dict[str, Any]) -> str | None:  # noqa: ANN401
    """Return the first thing wrong with one node's ``settings``, or None."""
    if kind != _COMPUTED_KIND:
        return _settings_on_a_node_with_nothing_to_configure(where, kind)
    if not stated:
        return _settings_stating_no_convention(where)
    if set(stated) == _SURVIVAL_SETTINGS:
        return _survival_value_defect(where, stated)
    if set(stated) == _PROSPECTIVE_SETTINGS:
        return _prospective_value_defect(where, stated)
    return _settings_of_no_operation_this_revision_carries(where, stated)


def _survival_value_defect(where: str, stated: dict[str, Any]) -> str | None:
    """Return the first survival setting outside what it admits, or None."""
    start_at = stated["start_at"]
    if not _a_decimal_or_null(start_at):
        return _a_setting_outside_what_it_admits(
            where, "start_at", start_at, _START_AT_ADMITS
        )
    from_survival = stated["from_survival"]
    if not isinstance(from_survival, bool):
        return _a_setting_outside_what_it_admits(
            where, "from_survival", from_survival, _FROM_SURVIVAL_ADMITS
        )
    return None


def _prospective_value_defect(where: str, stated: dict[str, Any]) -> str | None:
    """Return the first prospective-value setting outside what it admits, or None."""
    timing = stated["timing"]
    if timing not in _TIMINGS:
        return _a_setting_outside_what_it_admits(
            where, "timing", timing, _TIMING_ADMITS
        )
    discount_kind = stated["discount_kind"]
    if discount_kind not in _DISCOUNT_KINDS:
        return _a_setting_outside_what_it_admits(
            where, "discount_kind", discount_kind, _DISCOUNT_KIND_ADMITS
        )
    return None


def _a_decimal_or_null(value: Any) -> bool:  # noqa: ANN401
    """Return whether ``value`` is a decimal or the null a timing is recorded as."""
    return value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )


def _settings_on_a_node_with_nothing_to_configure(where: str, kind: Any) -> str:  # noqa: ANN401
    """Return the refusal for settings on a node that executes nothing."""
    return (
        f"Node {where!r} states ``settings`` and its ``kind`` is {kind!r}. "
        "Settings are the configuration of the operation a node's whole "
        "calculation is, so only a 'computed' node has one to state: a "
        "column that arrived with the data, a column nothing accounts for "
        "and a running rollforward state execute nothing at all, and a "
        "compiled rollforward's own tree is the compilation's identity "
        "rather than an accumulation configured under a convention. "
        "Export the model again rather than deleting the field here -- a "
        "convention written onto a node that computed nothing came from "
        "somewhere, and this file does not say where."
    )


def _settings_stating_no_convention(where: str) -> str:
    """Return the refusal for a settings object holding nothing."""
    return (
        f"Node {where!r} states ``settings`` and states nothing in it. "
        "Both operations that carry settings state their convention "
        "always -- a survival fold its ``start_at`` and whether it was "
        "handed survival rates, a prospective value its ``timing`` and "
        "whether the second operand is a rate or a factor -- so an empty "
        "object is an accumulation that somehow ran under no convention. "
        "A node with nothing to say about a convention carries no "
        "``settings`` at all, and that absence is the statement."
    )


def _settings_of_no_operation_this_revision_carries(
    where: str, stated: dict[str, Any]
) -> str:
    """Return the refusal for a settings object shaped like neither operation."""
    return (
        f"Node {where!r} states ``settings`` of {sorted(stated)}, which is "
        "neither of the two shapes this revision defines: "
        "['from_survival', 'start_at'] for a cumulative survival, and "
        "['discount_kind', 'timing'] for a prospective value. A key "
        "missing, a key too many and a key from an operation this "
        "revision does not carry all read the same way to a reviewer, who "
        "cannot tell which convention is being claimed or whether the one "
        "they can see belongs to it. Export the model again: what a node "
        "states here is quoted from the operation's own attributes rather "
        "than assembled."
    )


def _a_setting_outside_what_it_admits(
    where: str,
    key: str,
    value: Any,  # noqa: ANN401
    english: str,
) -> str:
    """Return the refusal for one setting whose value is not one it may hold."""
    return (
        f"Node {where!r} states {key!r} as {value!r}, and {english}. The "
        "convention is what a reviewer reads before the arithmetic: two "
        "timing conventions do not give the same numbers, even at flat rates "
        "-- a survival curve "
        "differs by one period's decrement, a prospective value by one "
        "period's discount -- and what flat rates hide is a wrong conversion "
        "between them. So a word the format does not define here leaves the "
        "one question this field exists to answer unanswered, in a record "
        "that looks as though it answered it. Export the model again rather "
        "than editing the value: the convention an accumulation ran under is "
        "the producer's to say."
    )


def policy_axis_width(document: dict[str, Any]) -> int:
    """Return how many policies this document's values are read along.

    One where the document declares no axis at all -- every artifact
    written before ``policies`` existed, and every one written since
    carrying a single policy, where each enrichment field is the value
    itself and not an array of one. So a reading that walks the axis walks
    exactly once over such a document and meets what it always met.
    """
    axis = document.get("policies")
    return len(axis) if isinstance(axis, list) and axis else 1


def _at(node: dict[str, Any], field: str, position: int, width: int) -> Any:  # noqa: ANN401 — one enrichment value, of whatever the model held
    """Return what one node stated in ``field`` at one position of the axis.

    None where the node states nothing there, and None where what it states
    is not an array as long as the axis -- a node disagreeing with the
    envelope about how many policies the file holds is reported once, by
    the reading that measures the two against each other, rather than
    misread here as a value at every position.
    """
    held = node.get(field)
    if width < _AXIS_IS_PLURAL:
        return held
    if not isinstance(held, list) or len(held) != width:
        return None
    return held[position]


def _axis_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return what the policy axis and the nodes say against each other.

    The axis is declared in the envelope and nowhere else, and a node's
    enrichment is read along it by position. So there are three ways the two
    can disagree and all three are refusals: the head of the axis is not the
    ``enrichment`` the envelope also states, an entry names a policy none of
    the model-point values beside it is, and a node's enrichment is not as
    long as the axis it is read against. Each one puts a reader on a value
    belonging to a policy other than the one they think they are reading,
    which is the failure the axis was put in the envelope to prevent.
    """
    axis = document.get("policies")
    if not isinstance(axis, list):
        return []
    width = len(axis) if axis else 1
    findings = [
        *_axis_head_findings(document, axis),
        *_an_identity_the_values_do_not_carry(axis, nodes, width),
    ]
    if width < _AXIS_IS_PLURAL:
        return findings
    for node in nodes:
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        for field in _ALONG_THE_AXIS:
            held = node.get(field)
            if held is None or (isinstance(held, list) and len(held) == width):
                continue
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=_not_as_long_as_the_axis(where, field, held, width),
                )
            )
    return findings


def _an_identity_the_values_do_not_carry(
    axis: list[Any], nodes: list[dict[str, Any]], width: int
) -> list[Finding]:
    """Return a finding per entry naming a policy its own samples are not.

    **An entry that names a policy has to be able to show it.** Where the
    document carries the model points' own values at that entry, some value
    it carries there must be the policy the entry declares -- the identifier
    is a field of the model points, and an entry that shows the model
    points' values without showing the one that is its own name is an entry
    whose values came off another row.

    **Asked of the model points and answered by any node**, and the two
    halves are deliberately different. The question is asked only where the
    model points reached the document, because that is what makes the
    identifier answerable at all; the answer is taken from anywhere in the
    entry, because a model that renames its identifier on the way in --
    ``policy_id = Policy number`` -- carries it on a computed node, and a
    reading that insisted on the arrival would refuse an honest document
    over a rename.

    This is the reading that catches a producer indexing the finished frame
    by the position it counted in the book. A model that sorts, filters or
    duplicates rows leaves the two apart, and the document that comes out is
    internally consistent in every other respect: the fingerprints hold, the
    axis is as long as the enrichment, the trace and the sample agree with
    each other, and the numbers are another policy's. The only witness left
    in the file is the id column standing beside them, so that is the
    witness this asks for.

    **Silent where there is nothing to ask.** A fold entry names no policy;
    an artifact carrying no values carries no samples; a model that hands
    back no field of its model points at all -- every one dropped, renamed
    or per-period -- leaves the question unanswerable rather than answered
    wrongly, and a refusal there would be this reading inventing evidence.
    The producer refuses that export for the same reason
    (:mod:`~gaspatchio.frame.graph.row_identity`), so the two agree about
    which documents can exist.

    A coincidence passes: a duration that happens to read ``1`` beside
    policy ``"1"`` satisfies this. It is a floor rather than a proof, and a
    floor the failure it was written for falls straight through.
    """
    carried = [
        node
        for node in nodes
        if node.get("kind") == "input" and node.get("provenance") == "model_points"
    ]
    findings: list[Finding] = []
    for position, entry in enumerate(axis):
        if not isinstance(entry, dict):
            continue
        declared = entry.get("policy_id")
        if not isinstance(declared, str):
            continue
        asked = [
            value
            for node in carried
            if _is_one_identifier(value := _at(node, "value_sample", position, width))
        ]
        answered = any(
            _is_one_identifier(value := _at(node, "value_sample", position, width))
            and _reads_as(value, declared)
            for node in nodes
        )
        if asked and not answered:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=_ENVELOPE,
                    message=_a_policy_the_samples_are_not(
                        position, declared, carried, width
                    ),
                )
            )
    return findings


def _is_one_identifier(value: Any) -> bool:  # noqa: ANN401 -- one sampled value, of whatever the model held
    """Whether one sample could be a policy identifier at all.

    One value rather than a run of them, and not a boolean: a per-period
    column is not an id column and ``True`` is not a policy number.
    """
    return isinstance(value, (int, float, str)) and not isinstance(value, bool)


def _reads_as(value: Any, declared: str) -> bool:  # noqa: ANN401 -- one sampled value, of whatever the model held
    """Whether one sampled value is the identifier ``declared`` names.

    Compared as text, because the envelope writes ``policy_id`` as a string
    whatever the column's own type is. A float that is a whole number is
    read both ways -- ``7.0`` and ``"7"`` are one policy on a book whose
    identifiers arrived as floating point, and refusing that would be this
    reading refusing an honest document over a dtype.
    """
    if isinstance(value, float) and value.is_integer():
        return str(value) == declared or str(int(value)) == declared
    return str(value) == declared


def _a_policy_the_samples_are_not(
    position: int, declared: str, carried: list[dict[str, Any]], width: int
) -> str:
    """Return the refusal for an entry naming a policy its own values are not."""
    read = ", ".join(
        f"{node.get('id')!r} reads {value!r}"
        for node in carried[:_IDS_SHOWN]
        if _is_one_identifier(value := _at(node, "value_sample", position, width))
    )
    return (
        f"Entry {position} of ``policies`` names policy {declared!r}, and no "
        f"model-point value this document carries at that entry is that "
        f"policy: {read}. A policy identifier is a field of the model "
        "points, so an entry that carries the model points' own values and "
        "not the one that names the policy is an entry whose values were "
        "read off another row -- which is what a producer indexing the "
        "finished frame by the position it counted in the book produces "
        "the moment the model sorts, filters or duplicates its rows. Every "
        "other claim in such a document holds, so this is the only reading "
        "that can catch it. Export the model again with a producer that "
        "carries the selected row's identity through the run."
    )


def _axis_head_findings(document: dict[str, Any], axis: list[Any]) -> list[Finding]:
    """Return a finding where ``enrichment`` is not the head of the axis."""
    enrichment = document.get("enrichment")
    if not axis:
        if enrichment is None:
            return []
        return [
            Finding(
                section="semantic",
                severity="error",
                where=_ENVELOPE,
                message=_an_axis_with_nothing_on_it(),
            )
        ]
    head = axis[0]
    if not isinstance(head, dict) or not isinstance(enrichment, dict):
        return []
    restated = {name: value for name, value in head.items() if name != "why"}
    if restated == enrichment:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=_a_head_that_is_not_the_enrichment(enrichment, restated),
        )
    ]


def _not_as_long_as_the_axis(
    where: str,
    field: str,
    held: Any,  # noqa: ANN401 — whatever the node wrote there
    width: int,
) -> str:
    """Return the refusal for enrichment that is not one value per policy."""
    stated = len(held) if isinstance(held, list) else "not an array"
    return (
        f"Node {where!r} carries ``{field}`` of {stated} against a "
        f"``policies`` axis of {width}. A node's enrichment is read along "
        "that axis by position and by nothing else -- no entry names a "
        "policy of its own -- so an array of any other length puts every "
        "value after the first mismatch under some other policy's name, "
        "and a reader checking one of those numbers would be checking a "
        "different model point. Export the model again, or drop the field: "
        "no value is better than a value belonging to somebody else."
    )


def _an_axis_with_nothing_on_it() -> str:
    """Return the refusal for an empty axis beside a stated context."""
    return (
        "This document states an ``enrichment`` context and an empty "
        "``policies`` axis. The axis is the list of policies the values are "
        "read along and ``enrichment`` is its first entry, so an empty axis "
        "beside a stated context is the envelope contradicting itself about "
        "whether this artifact carries any values at all. Export the model "
        "again with the frame the values were read from."
    )


def _a_head_that_is_not_the_enrichment(
    enrichment: dict[str, Any], restated: dict[str, Any]
) -> str:
    """Return the refusal where the axis head and ``enrichment`` disagree."""
    differ = sorted(
        name
        for name in set(enrichment) | set(restated)
        if enrichment.get(name) != restated.get(name)
    )
    return (
        f"The first entry of ``policies`` and the envelope's "
        f"``enrichment`` disagree on {differ}. They are one context written "
        "twice: ``enrichment`` is that entry with ``why`` left off, which "
        "is what lets a consumer written against an edition with no axis "
        "read this document as its first policy and be right about "
        "everything it reads. Two spellings of one context that do not "
        "agree mean one of them is describing values the file does not "
        "hold. Export the model again."
    )


def _branches_findings(nodes: list[dict[str, Any]], width: int = 1) -> list[Finding]:
    """Return everything wrong with what a node says its branches held.

    ``branches`` is the value each side of a conditional would have come
    to for the declared policy, with the branch the condition chose named.
    It exists because the branch that did not fire is in no column of the
    finished frame: a reviewer asking "what would this have been if the
    condition had gone the other way?" has the record or has nothing. A
    record that answers it wrongly is worse than one that does not answer
    it -- a reviewer reads a number, finds it plausible, and has read a
    branch of some other line.

    Four readings, each a refusal rather than a warning. A node with
    nothing to execute ran no conditional to have two branches of. An
    object that is not exactly the three parts states half a comparison,
    and half a comparison is not one. A branch named in a word the format
    does not define names nothing. And a ``fired`` shaped unlike the
    column it describes cannot be read against the sample beside it: one
    word for a column holding one value, one word per period for a column
    holding a run of them, and the run as long as the sample's own.

    One finding per node, first defect only: the four are four readings of
    one object, and a reader sent to fix it four times fixes it once.
    """
    findings: list[Finding] = []
    for node in nodes:
        if _BRANCHES not in node:
            continue
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        for position in range(width):
            stated = _at(node, _BRANCHES, position, width)
            # Anything but an object is a schema finding already, and a
            # second reading falling over on it would report this module
            # rather than the artifact. A null at one position of the axis
            # is the producer saying it could not evaluate that policy's
            # branches, which is an answer rather than a defect.
            if not isinstance(stated, dict):
                continue
            message = _branches_defect(
                where, node, stated, _at(node, "value_sample", position, width)
            )
            if message is None:
                continue
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=message,
                )
            )
            break
    return findings


def _branches_defect(
    where: str,
    node: dict[str, Any],
    stated: dict[str, Any],
    sample: Any,  # noqa: ANN401 — the sample at this position of the axis
) -> str | None:
    """Return the first thing wrong with one node's ``branches``, or None."""
    if node.get("kind") != _COMPUTED_KIND:
        return _branches_on_a_node_that_ran_no_conditional(where, node.get("kind"))
    if set(stated) != _BRANCH_MEMBERS:
        return _branches_that_are_not_the_three_parts(where, stated)
    fired = stated[_FIRED]
    return _fired_defect(where, node, fired, sample)


def _fired_defect(
    where: str,
    node: dict[str, Any],
    fired: Any,  # noqa: ANN401 — the branch word, or one per period
    sample: Any,  # noqa: ANN401 — the sample at this position of the axis
) -> str | None:
    """Return the first thing wrong with one node's ``fired``, or None."""
    if isinstance(fired, list):
        outside = [word for word in fired if word not in _BRANCH_WORDS]
        if outside:
            return _a_branch_named_in_a_word_that_is_not_one(where, outside[0])
        return _fired_shaped_unlike_the_column(
            where, node, fired, sample, per_period=True
        )
    if fired not in _BRANCH_WORDS:
        return _a_branch_named_in_a_word_that_is_not_one(where, fired)
    return _fired_shaped_unlike_the_column(where, node, fired, sample, per_period=False)


def _fired_shaped_unlike_the_column(
    where: str,
    node: dict[str, Any],
    fired: Any,  # noqa: ANN401 — the branch word, or one per period
    sample: Any,  # noqa: ANN401 — the sample at this position of the axis
    *,
    per_period: bool,
) -> str | None:
    """Return the refusal where ``fired`` cannot be read against the sample.

    The sample is what ``fired`` is read beside, so the sample is what it
    is measured against: a run of words needs a run of values the same
    length, and a run of values needs a run of words. A column holding one
    value per policy never has either. Where the document carries no
    sample -- an artifact exported without a frame carries none -- there is
    nothing to measure against and nothing is claimed.
    """
    if per_period and node.get("shape") != _LIST_SHAPE:
        return _a_run_of_words_for_a_column_holding_one_value(where, node.get("shape"))
    if not isinstance(sample, list):
        return None
    if not per_period:
        return _one_word_for_a_column_holding_a_run(where, len(sample))
    if len(fired) != len(sample):
        return _a_run_of_words_as_long_as_no_run_of_values(
            where, len(fired), len(sample)
        )
    return None


def _branches_on_a_node_that_ran_no_conditional(where: str, kind: Any) -> str:  # noqa: ANN401
    """Return the refusal for branches on a node that executes nothing."""
    return (
        f"Node {where!r} states ``branches`` and its ``kind`` is {kind!r}. "
        "Branches are the two values a conditional chose between, so only "
        "a 'computed' node has any: a column that arrived with the data, a "
        "column nothing accounts for and a running rollforward state "
        "execute nothing at all, and a compiled rollforward's tree is the "
        "compilation rather than a line with two sides. Export the model "
        "again rather than deleting the field here -- a branch written "
        "onto a node that computed nothing was evaluated somewhere, and "
        "this file does not say where."
    )


def _branches_that_are_not_the_three_parts(where: str, stated: dict[str, Any]) -> str:
    """Return the refusal for a branches object that is not the three members."""
    return (
        f"Node {where!r} states ``branches`` of {sorted(stated)}, and the "
        "three parts are ['fired', 'otherwise', 'then']. The value each "
        "branch would have held and the branch the condition chose are one "
        "statement: a reader holding two of the three cannot say which "
        "number the column took and which it did not, which is the whole "
        "question this member answers. Export the model again -- what is "
        "written here was evaluated by the producer against the declared "
        "policy, not assembled from the values around it."
    )


def _a_branch_named_in_a_word_that_is_not_one(where: str, word: Any) -> str:  # noqa: ANN401
    """Return the refusal for a fired branch named outside the two words."""
    return (
        f"Node {where!r} names the branch that fired as {word!r}, and a "
        "conditional has two branches: 'then' and 'otherwise', the names "
        "the formula itself uses. A third word names no branch of the line "
        "printed beside it, so a reader cannot tell which of the two "
        "values the column took -- and with both values in front of them, "
        "the wrong answer is as readable as the right one. Export the "
        "model again: which branch fired is the producer's to say, read "
        "off the condition it evaluated."
    )


def _a_run_of_words_for_a_column_holding_one_value(where: str, shape: Any) -> str:  # noqa: ANN401
    """Return the refusal for a per-period ``fired`` on a per-policy column."""
    return (
        f"Node {where!r} names the branch that fired once per period and "
        f"its ``shape`` is {shape!r}. A column holding one value per policy "
        "was decided once, so there is one branch to name; a run of words "
        "beside a single value has nothing to be read against, period by "
        "period, and invites a reader to index a timeline this column has "
        "not got. Export the model again rather than trimming the array."
    )


def _one_word_for_a_column_holding_a_run(where: str, periods: int) -> str:
    """Return the refusal for a single ``fired`` beside a per-period sample."""
    return (
        f"Node {where!r} names one branch as having fired and carries "
        f"{periods} periods of values beside it. A per-period conditional "
        "is decided period by period -- a maturity test fires in one month "
        "of the run and not in the others -- so the record names the "
        "branch for each of them. One word for a run of values says the "
        "same branch fired throughout, which is a claim about the "
        "condition rather than a shorter way of writing it. Export the "
        "model again."
    )


def _a_run_of_words_as_long_as_no_run_of_values(
    where: str, words: int, periods: int
) -> str:
    """Return the refusal for a ``fired`` run that is not the sample's length."""
    return (
        f"Node {where!r} names the branch that fired for {words} periods "
        f"and carries {periods} periods of values. The two are read "
        "against each other -- the word at a period says which of the two "
        "numbers at that period the column took -- so a run of a different "
        "length silently puts every word after the first difference "
        "against the wrong period. Export the model again: both were read "
        "from one row under the one context the envelope declares."
    )


def _strings(section: Any) -> list[str]:  # noqa: ANN401
    """Return the strings in one array section, ignoring anything else in it."""
    if not isinstance(section, list):
        return []
    return [entry for entry in section if isinstance(entry, str)]


def _handed_over_value_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every definition that reads nothing and reaches out.

    The shape: ``tier: "engine_native"`` with an empty ``reads`` and an empty
    ``reads_assumptions``. A definition wearing it computes from no column of
    the model and from no assumption base the envelope holds, and what it
    does compute from is a fragment of one engine's own expression language
    -- a whole vector, or one number, sitting inside the text. It is the
    answers with the question torn off, and it is the shape a
    paste-as-values takes when it arrives through a model file instead of a
    spreadsheet.

    Nothing in the document ties those values to a source. Not an assumption
    entry, because the node names none. Not a read, because it has none. Not
    a hole either: the assignment door recorded exactly what it was handed,
    honestly, and the file is a true account of a model whose own numbers
    have no stated origin.

    **What does and does not wear the shape**, at this build:

    - A vector built through the engine and broadcast onto the frame --
      ``pl.lit(pl.Series(...)).first()`` -- records here, whether its values
      came off a curve, out of a table, or off somebody's keyboard. That the
      reading is blind to the subject is the point: a tripwire that knew
      about discounting would let a mortality basis through.
    - **A scalar handed over the same way records here too.**
      ``pl.lit(0.05)`` reads nothing and reaches into the engine, so the
      number is inside a fragment of one engine's language with nothing
      saying where it came from -- the same class, at a smaller size.
    - A scalar written in the framework's own terms does not.
      ``af.discount_rate = 0.04`` records under this format's ``lit``
      operation at tier ``core``: the value rides inside the node's own
      canonical bytes, so the model's line is what states it and a
      fingerprint moves when it changes.
    - A column *injected* at a line does not, and deliberately. Its ``tier``
      is null because an injection is not an operation, and section 8 calls
      it located data -- strictly more than a spreadsheet's paste-as-values
      tells a reviewer, because the file says which line handed it over.
    - An engine-native line that reads a column does not. The escape hatch
      exists to be used; a rolling mean over a column of the model is a
      calculation with its inputs on the record.

    Warning rather than error, and about the model rather than the document:
    the file is telling the truth about what it was given. What it cannot
    tell a reviewer is where those numbers came from, and that is a question
    for whoever wrote the line.
    """
    return [
        Finding(
            section="semantic",
            severity="warning",
            where=node["id"],
            message=_handed_over_value(node["id"]),
        )
        for node in nodes
        if isinstance(node.get("id"), str)
        and node.get("tier") == _ENGINE_NATIVE
        and not _strings(node.get("reads"))
        and not _strings(node.get("reads_assumptions"))
    ]


def _handed_over_value(node_id: str) -> str:
    """Return the remark for a definition whose values have no stated source."""
    return (
        f"Node {node_id!r} reads no column of the model, names no assumption "
        "base, and reaches into the engine's own expression language -- a "
        "value handed over rather than computed. Nothing in this artifact "
        "ties its numbers to a source: not an assumption entry, not a read, "
        "not a hole; the recording door wrote down exactly what it was "
        "given. A reviewer who asks where the values came from has the "
        "model's line and nothing else, and next quarter's comparison sees "
        "one opaque digest move without being able to say what moved it. If "
        "they came off a curve or a table, read it through the recorded "
        "operation -- ``curve.discount_factor(af.t)``, "
        "``table.lookup(...)`` -- so that the source travels with the "
        "model. If the line determines its own values instead, write them "
        "in the framework's own terms rather than inside an engine "
        "fragment -- ``af.discount_rate = 0.04`` records under this "
        "format's own ``lit`` operation -- so that the values ride in the "
        "node's canonical bytes and the digest moves when they change."
    )


def _retention_claim_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every node claiming to retain what it never lost.

    ``retained`` is a declaration about a definition the model wrote over:
    its column was overwritten before the model finished, so its own output
    had to be carried to the export or the value beside it would be the
    successor's number. It is what lets a value hang off a node stating
    ``in_final_schema: false`` at all.

    On a node the frame *does* hold, the same word claims something that
    cannot have happened. Nothing was carried, because nothing was replaced:
    the value is read off the finished frame like every other live column's.
    A reader would take it as evidence that the number in front of them came
    out of some other frame than the one the envelope's ``enrichment``
    context names, and there is no such frame.

    Read here rather than in the enrichment section because it is a claim the
    record makes about itself. A node can carry the field with no value
    beside it, and the enrichment reading never sees a node carrying no
    values at all.
    """
    return [
        Finding(
            section="semantic",
            severity="error",
            where=node["id"],
            message=_retained_on_a_definition_the_frame_holds(node["id"]),
        )
        for node in nodes
        if isinstance(node.get("id"), str)
        and node.get("retained") is True
        and node.get("in_final_schema") is True
    ]


def _retained_on_a_definition_the_frame_holds(node_id: str) -> str:
    """Return the refusal for a live definition claiming to have been retained."""
    return (
        f"Node {node_id!r} states ``retained: true`` and "
        "``in_final_schema: true``. Retention is what a definition the model "
        "wrote over needs: its column stops existing the moment the next "
        "definition lands, so its own output has to be held to the export or "
        "the value shown beside it is the number that replaced it. The "
        "definition the column actually ends up holding is read off the "
        "finished frame like every other live column, and has nothing to "
        "hold. As written, this node says its value came out of a frame the "
        "envelope's ``enrichment`` context does not name. Drop ``retained`` "
        "from this node if it is the definition the column holds, or state "
        "``in_final_schema: false`` if it is not."
    )


def _untyped_answer_findings(nodes: list[dict[str, Any]]) -> list[Finding]:
    """Return a finding for every node in the final schema stating no type.

    ``unknown`` is not a type. Section 10 permits it where the producer never
    determined one and nothing downstream needed it -- a column's superseded
    definitions, a column defined and then dropped -- because there the node
    is the model's history. A node the frame still holds is the model's
    answer, and its type is what a reader reads that answer under: whether
    the column holds a selection or a quantity, what a consumer rebuilds its
    values as, what next quarter's comparison is comparing. A document that
    states none has no account of the column it ends on.

    Both fields are read here and both under the same rule, because "what is
    in this column" is one question: ``dtype`` says what its values are and
    ``shape`` how many of them there are per policy. **One finding per node
    rather than one per field.** The node has one defect -- the file does not
    say what it holds -- and a second finding would report the shape of this
    reading rather than the state of the artifact. The message names
    whichever of the two the node left untyped.

    Nothing this producer writes reaches here. A type it cannot name on a
    column the frame holds is a refusal at export rather than an ``unknown``,
    and a dropped arrival's leaf carries the type it arrived under. So this
    reading is for a document that came from somewhere else, or one somebody
    edited after it was written -- which is the case a validator exists for.

    Not the execution inspector's ``input_dtype_unknown`` and
    ``input_shape_unknown``, which answer a different question and keep
    theirs. Those ask whether an artifact can be *executed*, so they read
    input leaves only: an untyped input is an interface a caller has no way
    to supply. This asks whether a document can be *read*, so it reads
    whatever the frame ends up holding, of any kind. An untyped input leaf in
    the final schema is in both, for two reasons.
    """
    return [
        Finding(
            section="semantic",
            severity="error",
            where=node["id"],
            message=_untyped_in_the_final_schema(node["id"], untyped),
        )
        for node in nodes
        if isinstance(node.get("id"), str)
        and node.get("in_final_schema") is True
        and (untyped := [f for f in _TYPE_FIELDS if node.get(f) == _UNTYPED])
    ]


def _untyped_in_the_final_schema(node_id: str, untyped: Sequence[str]) -> str:
    """Return the refusal for an answer this document states no type for."""
    named = " and ".join(f"``{field}: unknown``" for field in untyped)
    return (
        f"Node {node_id!r} is in the final schema and states {named}. "
        "``unknown`` is not a type -- it records that the producer never "
        "determined one, which section 10 permits on a column the model "
        "wrote over and on a column it defined and then dropped, where the "
        "node is history and nothing reads it for an answer. This node is "
        "the answer, and the file gives its reader no account of what is in "
        "it: not whether the column holds a selection or a quantity, not "
        "what a consumer rebuilds its values as, not what a comparison "
        "against next quarter is comparing. State the type this column "
        "holds, or state ``in_final_schema: false`` where the node is "
        "history after all."
    )


# --- the identity layer ------------------------------------------------------


def _identity_findings(document: dict[str, Any]) -> list[Finding]:
    """Return what the artifact's own digests say when they are taken again.

    Six readings, and every one of them needs section 12's or section 13's
    rules and nothing the producer did not put in the file. **The document
    seal first**, because every other reading here reads fields off the
    document and this is the one that says whether the document is the one
    those fields were written into. Then the propagation, which is the
    reading an ``audit`` artifact can always be asked for; then the
    assumption payloads and the model's own source, both verifiable from
    either profile; then the local fingerprints and the formulas-only
    digest, which need the operation trees only the ``executable`` profile
    carries.

    Every digest is taken through the fingerprint module's own functions and
    the framework's own content grammar rather than through a second reading
    of the byte grammar written here. Two implementations of one grammar
    inside one package would eventually disagree, and the one that disagreed
    would be the one nobody was running when the corpus was taken.
    """
    nodes = _objects(document.get("nodes"))
    return [
        *_document_seal_findings(document),
        *_propagation_findings(document, nodes),
        *_assumption_payload_findings(document),
        *_source_payload_findings(document),
        *_local_fingerprint_findings(document, nodes),
        *_compilation_findings(document, nodes),
        *_formulas_fingerprint_findings(document, nodes),
    ]


def _compilation_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return what each compiled rollforward's published machine says when hashed again.

    A compilation's identity is the section 12.3 recipe-grammar hash of the
    body its facet publishes, less the body's ``schedule`` (section 12.1), so a
    reader holding the body recomputes the identity of the machine and holds
    the node's movement summary to it: either disagreeing is an error. A
    compilation the file does not carry -- every one, in the ``audit``
    profile -- has its identity read as published, and is named here so a
    reader knows which machine they took on trust (section 13).
    """
    facet = (document.get("facets") or {}).get(_ROLLFORWARD_IR_FACET)
    held = facet.get("compilations") if isinstance(facet, dict) else None
    bodies: dict[str, Any] = held if isinstance(held, dict) else {}
    findings: list[Finding] = []
    checked: set[str] = set()
    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.startswith(
            ROLLFORWARD_NAMESPACE
        ):
            continue
        fingerprint = _compiled_fingerprint_of(node, node_id, bodies)
        body = bodies.get(fingerprint) if fingerprint is not None else None
        if fingerprint is None or not isinstance(body, dict):
            findings.append(
                Finding(
                    section="semantic",
                    severity="warning",
                    where=node_id,
                    message=_compilation_read_as_published(node_id),
                )
            )
            continue
        checked.add(fingerprint)
        findings.extend(_compilation_disagreement_findings(node, fingerprint, body))
    for fingerprint, body in bodies.items():
        if fingerprint not in checked and isinstance(body, dict):
            findings.extend(_compilation_disagreement_findings({}, fingerprint, body))
    return findings


def _compiled_fingerprint_of(
    node: dict[str, Any], node_id: str, bodies: dict[str, Any]
) -> str | None:
    """Return the identity a compilation's node names, from its call or its id."""
    tree = node.get("expr")
    if isinstance(tree, dict):
        attrs = tree.get("attrs")
        stated = (
            attrs.get(ROLLFORWARD_FINGERPRINT_ATTR) if isinstance(attrs, dict) else None
        )
        if isinstance(stated, str):
            return stated
    # Without a tree the id names its compilation by the identity's first
    # twelve hex digits (section 8.1); a body keyed so is the one meant.
    short = node_id.removeprefix(ROLLFORWARD_NAMESPACE)
    named = [key for key in bodies if key.removeprefix(SHA256_PREFIX)[:12] == short]
    return named[0] if len(named) == 1 else None


def _compilation_disagreement_findings(
    node: dict[str, Any], fingerprint: str, body: dict[str, Any]
) -> list[Finding]:
    """Return the errors for a published machine its identity does not name."""
    where = f"/facets/{_ROLLFORWARD_IR_FACET}/compilations/{fingerprint}"
    return [
        Finding(
            section="semantic", severity="error", where=where + inside, message=message
        )
        for inside, message in compilation_disagreements(node, fingerprint, body)
    ]


def _compilation_read_as_published(node_id: str) -> str:
    """Return the note for a compilation whose machine the file does not carry."""
    return (
        f"The machine behind {node_id!r} is not in this file, so its identity "
        "was read as published rather than recomputed: the "
        "gaspatchio_rollforward_ir facet carries a compilation only in the "
        "executable profile, or where the exporting process held it. Every "
        "other digest of the node follows from that identity as stated. To "
        "check the machine itself, export the model with --profile executable "
        "and validate that file with --deep."
    )


def _document_seal_findings(document: dict[str, Any]) -> list[Finding]:
    """Return what the seal says when it is taken again.

    The identity chain answers whether this is the same calculation. It
    cannot answer whether this is the file the producer wrote: ``formula`` is
    no part of any node's canonical bytes (section 8.2), so a quotation
    edited after export recomputes clean through every reading below this
    one. ``document_digest`` is the answer to the second question, and this
    is where a reader stops taking it on trust.

    **An unsealed document is noted and not refused.** The member is not
    required under this schema identifier, so a document written before the
    seal existed is a conforming document; a reader is told what the file
    cannot tell them rather than handed a refusal it cannot act on.
    """
    if DOCUMENT_DIGEST_FIELD not in document:
        return [
            Finding(
                section="semantic",
                severity="warning",
                where=_ENVELOPE,
                message=_no_seal(),
            )
        ]
    stated = document[DOCUMENT_DIGEST_FIELD]
    if not _is_stamped_digest(stated):
        return [
            Finding(
                section="semantic",
                severity="error",
                where=_ENVELOPE,
                message=_seal_is_not_a_digest(stated),
            )
        ]
    try:
        taken = document_digest_of(document)
    except (TypeError, ValueError) as exc:
        # A report rather than an exception, which is this module's whole
        # posture: a reader holding a document the grammar refuses needs to
        # be told which reading could not be given, not to have the call die.
        return [
            Finding(
                section="semantic",
                severity="error",
                where=_ENVELOPE,
                message=_seal_cannot_be_taken(str(exc)),
            )
        ]
    if taken == stated:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=_seal_disagrees(stated, taken),
        )
    ]


def _no_seal() -> str:
    """Return the remark for a document carrying no seal at all."""
    return (
        f"This document carries no {DOCUMENT_DIGEST_FIELD!r}, so nothing in "
        "it says whether it is the file its producer wrote. The fingerprints "
        "answer a different question -- whether this is the same calculation "
        "-- and they are computed from the recorded operation rather than "
        "from the document, so an as-written formula edited after export "
        "leaves every one of them valid and every check on them clean. The "
        "document is not refused for the absence: the member is not required "
        "under this schema identifier and a document written before the seal "
        "existed is a conforming document. Export the model again from a "
        "producer that seals its documents to close the reading."
    )


def _is_stamped_digest(stamp: Any) -> bool:  # noqa: ANN401
    """Return whether a field is written the way this format stamps a digest.

    ``sha256:`` followed by sixty-four **lowercase** hex digits, which is
    section 13.1 step 4 for the seal and section 2 for every other digest
    here. Uppercase hex decodes to the same bytes and is not that form, and
    the reading it falls into matters even though the grade does not: a seal
    written some other way is a seal that cannot be read, which is a
    different finding from a seal that was read and disagreed. Only the
    second is a claim that somebody rewrote the file, and it should be made
    about a file where that was measured.
    """
    return (
        isinstance(stamp, str) and stamp == stamp.lower() and _digest(stamp) is not None
    )


def _seal_is_not_a_digest(stated: Any) -> str:  # noqa: ANN401
    """Return the refusal for a seal that is not a stamped content hash."""
    return (
        f"This document's {DOCUMENT_DIGEST_FIELD!r} is {stated!r}, which is "
        "not a stamped content hash -- ``sha256:`` followed by sixty-four "
        "lowercase hex digits, as every digest in this framework is written. "
        "A seal nobody can parse is a seal nobody can check, so the one "
        "question it exists to answer -- is this the file the producer "
        "wrote -- is unanswered here rather than answered badly. Export the "
        "model again rather than restamping the file."
    )


def _seal_cannot_be_taken(refusal: str) -> str:
    """Return the refusal for a document the canonical grammar will not encode."""
    return (
        f"This document's {DOCUMENT_DIGEST_FIELD!r} could not be recomputed, "
        f"because the document holds a value the canonical serialization "
        f"refuses: {refusal}. For a document read from a file, a non-finite "
        "float is the only value that reaches here, and it is outside the "
        "JSON grammar as well -- a strict parser refuses the whole file over "
        "one, and section 10's string sentinels are how such a value "
        "travels. A document assembled in memory can reach here carrying a "
        "value JSON has no type for at all, which is the one named above. So "
        "there is nothing to seal rather than a seal to be read carefully, "
        "and the document has to be written again before the reading can be "
        "given."
    )


def _seal_disagrees(stated: str, taken: str) -> str:
    """Return the refusal for a document that is not the one that was sealed."""
    return (
        "This is not the file the producer wrote. Its "
        f"{DOCUMENT_DIGEST_FIELD!r} states {stated}, and the same digest "
        f"taken again over the document in hand is {taken}. The seal is a "
        "hash over the document's own canonical serialization with the seal "
        "itself excluded and everything else -- every formula, every source "
        "location, every timestamp -- inside it, so a disagreement means "
        "something in the file moved after it was sealed. It need not be a "
        "calculation: the fingerprints cover what would run and the seal "
        "covers the record, so an edited quotation, a rewritten source "
        "location or a re-dated envelope reaches here and reaches no "
        "fingerprint. Compare this document against the one whose digest "
        "another record cites -- a filed change report names it -- rather "
        "than re-sealing this one, which would only make the forgery "
        "self-consistent."
    )


def _digest(stamp: Any) -> bytes | None:  # noqa: ANN401
    """Return the raw digest a stamped fingerprint carries, or None.

    None where the field is not the shape section 8 gives -- ``sha256:``
    followed by sixty-four hex digits. That is already a schema finding, and
    a second reading that guessed at what was meant would report a digest
    nobody wrote.
    """
    if not isinstance(stamp, str) or not stamp.startswith(SHA256_PREFIX):
        return None
    hexed = stamp[len(SHA256_PREFIX) :]
    if len(hexed) != HEX_WIDTH:
        return None
    try:
        return bytes.fromhex(hexed)
    except ValueError:
        return None


def _propagation_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return every node whose fingerprint does not follow from what it holds.

    A node's ``fingerprint`` is its own ``local_fingerprint`` followed by the
    fingerprints of everything it reads, in the order ``reads`` states. Both
    halves are taken as the file publishes them, which is what makes this a
    reading of the file rather than a re-run of the model: a consumer needs
    no operation tree, no engine, and nothing the producer left out.
    """
    published: dict[str, bytes] = {}
    for node in nodes:
        node_id = node.get("id")
        digest = _digest(node.get("fingerprint"))
        if isinstance(node_id, str) and digest is not None:
            published[node_id] = digest

    findings: list[Finding] = []
    for node in nodes:
        node_id = node.get("id")
        local = _digest(node.get("local_fingerprint"))
        if not isinstance(node_id, str) or local is None:
            continue
        stated = published.get(node_id)
        reads = _strings(node.get("reads"))
        if stated is None or any(read not in published for read in reads):
            # A name that resolves to nothing is already a structural
            # finding, and a fold taken with a dependency quietly dropped
            # would be sixty-four characters long and wrong.
            continue
        if _merkle(local, [published[read] for read in reads]) != stated:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=node_id,
                    message=_propagation_broken(node_id, reads),
                )
            )
    return [*findings, *_graph_fingerprint_findings(document, nodes, published)]


def _propagation_broken(node_id: str, reads: Sequence[str]) -> str:
    """Return the refusal for a fingerprint that does not follow from the file."""
    rests_on = (
        "it reads nothing, so its fingerprint is a fold of that one digest alone"
        if not reads
        else "it reads, in the order it states them, "
        + ", ".join(repr(read) for read in reads)
    )
    return (
        f"Node {node_id!r} publishes a ``fingerprint`` that does not follow "
        f"from the ``local_fingerprint`` beside it and what it reads: "
        f"{rests_on}. That fold is the whole of the propagation rule, so a "
        "fingerprint that does not reproduce means one of the two digests "
        "has moved since the other was taken -- and the reading a "
        "quarter-over-quarter review depends on, which node changed on its "
        "own and which inherited a change from upstream, cannot be trusted "
        "for this node or anything downstream of it. Export the model again "
        "rather than restamping the file."
    )


def _graph_fingerprint_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]], published: dict[str, bytes]
) -> list[Finding]:
    """Return a finding if the one digest standing for the model does not follow.

    Three counted sections, each sorted: every (node id, fingerprint) pair,
    every assumption table content hash the model reads, and every column the
    model cannot account for, each followed by its ``content`` stamp where
    the holes section gives one. All three are read off the document rather
    than off the graph, which is the point -- a consumer holding the file and
    section 12 reaches the same number without the model.
    """
    stated = _digest(document.get("graph_fingerprint"))
    named = [node["id"] for node in nodes if isinstance(node.get("id"), str)]
    if stated is None or len(published) != len(named):
        # A stamp the schema already refused, or an id two nodes both claim:
        # either way the pairs this digest is taken over are not the pairs
        # the file states, and a mismatch here would restate that.
        return []

    pairs = [_text(node_id) + published[node_id] for node_id in sorted(published)]
    tables = [
        _text(fingerprint)
        for fingerprint in sorted(
            {
                entry["fingerprint"]
                for entry in _objects(document.get("assumptions"))
                if entry.get("kind") == _TABLE_KIND
                and isinstance(entry.get("fingerprint"), str)
            }
        )
    ]
    # Each name once, as the specification takes them: the holes section
    # lists one entry per name, and a document that repeated one would
    # otherwise move the digest by restating a column rather than by holding
    # a new one. A name keeps the first entry's stamp, as the section's own
    # rule keeps the first node's reason.
    stamps: dict[str, str | None] = {}
    for hole in _objects(document.get("holes")):
        column, content = hole.get("column"), hole.get("content")
        if isinstance(column, str) and column not in stamps:
            stamps[column] = content if isinstance(content, str) else None
    holes = hole_entries(stamps)
    selected = _published_selection(document)
    if selected is None:
        # A step whose digest the schema already refused: the section this
        # digest ends with cannot be taken, and a mismatch would restate it.
        return []
    taken = hashlib.sha256(
        _sequence(pairs)
        + _sequence(tables)
        + _sequence(holes)
        + selection_section(selected)
    ).digest()
    if taken == stated:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=(
                "The envelope's ``graph_fingerprint`` does not follow from "
                f"what this file publishes: {len(pairs)} node "
                f"identities, {len(tables)} assumption table content "
                f"hashes and {len(holes)} unaccounted columns, each section "
                "sorted and counted. That digest is what one quarter's run "
                "is compared against another's, so a value that does not "
                "reproduce from the document beside it makes every such "
                "comparison a comparison of two numbers rather than of two "
                "models -- and an artifact whose nodes all check while its "
                "own identity does not is one somebody edited after it was "
                "written. Export the model again."
            ),
        )
    ]


def _assumption_payload_findings(document: dict[str, Any]) -> list[Finding]:
    """Return what each assumption entry's values say about its own fingerprint.

    An entry publishes a content identity and, where the producer carried
    them, the very values that identity was taken over. Re-hashing those
    values is the one check that makes the entry answer for itself: a reader
    holding this document and the published grammar needs no library in
    common with the producer and no copy of the base to run it.
    """
    findings: list[Finding] = []
    for index, entry in enumerate(_objects(document.get("assumptions"))):
        where = f"/assumptions/{index}"
        named = _named_entry(entry)
        payload, declared = entry.get("payload"), entry.get("fingerprint")
        if not isinstance(payload, dict) or not isinstance(declared, str):
            continue
        if _OMITTED in payload:
            findings.append(
                Finding(
                    section="semantic",
                    severity="warning",
                    where=where,
                    message=_payload_left_out(named, payload.get(_OMITTED)),
                )
            )
            continue
        taken, unreadable = _payload_digest(entry.get("kind"), payload)
        if unreadable is not None:
            findings.append(
                Finding(
                    section="semantic",
                    severity="warning",
                    where=where,
                    message=(
                        f"The inlined values of {named} were not re-hashed: "
                        f"{unreadable}. The entry's fingerprint is therefore "
                        "read as written rather than checked, which is the "
                        "one thing carrying the values was meant to avoid. "
                        "Check it against the base itself, or read the file "
                        "with a consumer that carries the grammar this one "
                        "is short of."
                    ),
                )
            )
            continue
        if taken != declared:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=_payload_disagrees(named, declared, taken),
                )
            )
    return findings


def _source_payload_findings(document: dict[str, Any]) -> list[Finding]:
    """Return what the model's own text says about the digest beside it.

    The reading section 7.3 exists to make possible. An entry publishes the
    path a node's ``source_location`` points into and the digest of that
    file's bytes, and where the producer carried the text, re-encoding it is
    the one check that lets a page say the source it is showing is the source
    that ran. Without it a viewer can print a file it was handed and call it
    the model, which is the claim nobody should be taking on trust.

    A file's digest is neither of section 12.3's grammars -- it is SHA-256
    over the bytes themselves, the stamp ``model.source_sha`` carries -- so
    the check here is an encode and a hash and needs nothing but the standard
    library.
    """
    findings: list[Finding] = []
    for index, entry in enumerate(_objects(document.get("sources"))):
        where = f"/sources/{index}"
        path = entry.get("path")
        named = f"the model source {path!r}" if isinstance(path, str) else "a source"
        payload, declared = entry.get("payload"), entry.get("fingerprint")
        if not isinstance(payload, dict):
            continue
        if _OMITTED in payload:
            findings.append(
                Finding(
                    section="semantic",
                    severity="warning",
                    where=where,
                    message=_source_left_out(named, payload.get(_OMITTED)),
                )
            )
            continue
        text = payload.get(_SOURCE_TEXT)
        if not isinstance(text, str) or not isinstance(declared, str):
            findings.append(
                Finding(
                    section="semantic",
                    severity="warning",
                    where=where,
                    message=(
                        f"The text carried for {named} was not re-hashed: the "
                        "entry states no text this reader could read, or no "
                        "digest to check it against. Its fingerprint is "
                        "therefore read as written rather than checked, which "
                        "is the one thing carrying the text was meant to "
                        "avoid. Check it against the file itself."
                    ),
                )
            )
            continue
        taken = f"{SHA256_PREFIX}{hashlib.sha256(text.encode()).hexdigest()}"
        if taken != declared:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=where,
                    message=(
                        f"The text carried for {named} hashes to {taken}, and "
                        f"the entry declares {declared}. A source entry "
                        "carries the very bytes its digest was taken over, so "
                        "the two disagreeing means the code in this file is "
                        "not the code the model was run from. Every figure a "
                        "reader traces back to a line of it would be traced "
                        "to a line somebody else wrote. Export the model "
                        "again from the tree it was run in."
                    ),
                )
            )
    return findings


def _source_left_out(named: str, reason: Any) -> str:  # noqa: ANN401
    """Return the remark a source entry with no text to re-hash earns.

    Not a refusal, on any of the three reasons. The producer said a file
    exists and its text is not here, and said why -- which is a document
    doing its job. What the reader is told is which of the three happened,
    because the next move differs: fetch it, go and ask for it, or accept
    that the account of this file stops at its digest.
    """
    because = {
        "size": ("the producer holds this file, weighed it and chose not to carry it"),
        "withheld": (
            "the producer holds this file and was asked not to disclose it, "
            "which is a decision rather than a limit"
        ),
    }.get(
        reason if isinstance(reason, str) else "",
        "the producer named this file and could not read it from here -- a "
        "path outside the model root, a file that has moved, or bytes that "
        "are not text",
    )
    return (
        f"The text of {named} is not in this file, so what it says about the "
        f"file is a path and a digest: {because}. That digest becomes a check "
        "the moment somebody puts the file in front of it. Fetch the file and "
        "hash its bytes, or export the model again from a producer that "
        "carries the text."
    )


def _named_entry(entry: dict[str, Any]) -> str:
    """Return how one assumption entry is spoken about in a finding."""
    kind = entry.get("kind")
    name = entry.get("name")
    return f"the {kind} {name!r}" if isinstance(name, str) else f"an unnamed {kind}"


def _payload_left_out(named: str, reason: Any) -> str:  # noqa: ANN401
    """Return the remark an entry with no values to re-hash earns.

    Not a refusal, on any of the three reasons. The producer said a value
    exists and was left out, and said why -- which is a document doing its
    job. What the reader is told is that this entry's fingerprint is the one
    identity in the file that nothing here checked.
    """
    because = {
        "size": (
            "the producer holds these values, weighed them and chose not to carry them"
        ),
        "withheld": (
            "the producer holds these values and was asked not to disclose "
            "them, which is a decision rather than a limit"
        ),
    }.get(
        reason if isinstance(reason, str) else "",
        "the producer named this base's identity and cannot vouch for "
        "it from here -- a base built in another process, or one that has "
        "moved off the identity the formula read it under",
    )
    return (
        f"The values of {named} are not in this file, so its fingerprint "
        f"was read rather than checked: {because}. The digest is a claim "
        "about data held elsewhere, and it becomes a check the moment "
        "somebody puts that data in front of it. Fetch the base and hash it "
        "under the published content grammar, or export the model again "
        "from the process that holds it."
    )


def _payload_disagrees(named: str, declared: str, taken: str | None) -> str:
    """Return the refusal for values that do not hash to the digest beside them."""
    return (
        f"The values inlined for {named} hash to {taken}, and the entry "
        f"declares {declared}. A payload is the very form its declared "
        "fingerprint was taken over -- not a view of it and not a re-sort of "
        "it -- so the two disagreeing means the values in this file are not "
        "the values the model was run against. Every figure resting on this "
        "base is a figure whose basis the artifact cannot vouch for. Export "
        "the model again from the process that holds the base."
    )


def _payload_digest(
    kind: Any,  # noqa: ANN401
    payload: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Return the digest re-derived from ``payload``, or why there is none.

    Which grammar depends on the kind, and the two are not
    interchangeable. A table's payload and a join right side's are frames of
    values and re-hash under the content grammar; a schedule's and a curve's
    is the canonical form its own source stamp was taken over and re-hashes
    under the recipe grammar.

    **A join re-hashes on the same bytes as a table and is checked no
    further.** The content grammar is taken over the columns and the rows,
    and a table's ``dimensions`` and ``value`` are no part of it -- so the
    two kinds meet the same function here, and a join declaring neither
    member loses nothing a digest was ever taken over. What a table gets
    beyond this and a join does not is the role check: section 15 says a
    table whose rows hash correctly is still not an executable base until
    its key and answer roles are consistent, and a join has no roles to be
    inconsistent about.
    """
    if kind in _CONTENT_KINDS:
        return _table_payload_digest(payload)
    if kind in _RECIPE_KINDS:
        try:
            return source_sha_of(payload), None
        except (TypeError, ValueError) as refusal:
            return None, f"the recipe grammar refuses it ({refusal})"
    return None, f"this reader carries no grammar for an entry of kind {kind!r}"


def _table_payload_digest(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return the content hash of the frame a table or join payload declares.

    Exactly the frame the producer hashed: those columns in the payload's own
    order, those rows in the payload's own order, no projection and no
    re-sort. A consumer that tidied it first -- sorting by the dimensions, on
    the reasonable-looking theory that a table is keyed, or dropping to the
    dimensions and the value column -- would hash a different frame and reach
    a digest that matches nothing. A join's right side arrives already sorted
    by every column, which is the producer's sort and not this reader's to
    take again.
    """
    frame, unreadable = payload_frame(payload)
    if frame is None:
        return None, unreadable
    return content_sha_of(frame), None


def payload_frame(payload: dict[str, Any]) -> tuple[pl.DataFrame | None, str | None]:
    """Return the frame a table or join payload declares, or why it cannot be built.

    Its columns in the payload's order and its rows in the payload's order,
    each column built back from its neutral type and a non-finite float from
    the text it travels as -- the frame the producer hashed, and the frame a
    replay of a semi or anti join matches against.
    """
    rows = payload.get("rows")
    schema, unreadable = _payload_schema(payload.get("columns"))
    if schema is None or not isinstance(rows, list):
        return None, unreadable or "it declares no rows this reader could read"

    floating = {name for name, dtype in schema.items() if _float_leaf(dtype)}
    rebuilt: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(schema):
            return None, "a row carries a different number of values from its columns"
        rebuilt.append(
            [
                _sentinels_read(value) if name in floating else value
                for name, value in zip(schema, row, strict=True)
            ]
        )

    try:
        frame = pl.DataFrame(rebuilt, schema=schema, orient="row")
        return _iso_text_read(frame, payload.get("columns")), None
    except (TypeError, ValueError, pl.exceptions.PolarsError) as refusal:
        return None, f"its rows do not fit the types it declares ({refusal})"


def _float_leaf(dtype: pl.DataType) -> bool:
    """Return whether ``dtype`` is ``f64`` or a list of it at any depth."""
    if isinstance(dtype, pl.List):
        return _float_leaf(dtype.inner)  # type: ignore[arg-type]
    return dtype == pl.Float64()


def _sentinels_read(value: Any) -> Any:  # noqa: ANN401
    """Return one ``f64`` or ``list[f64]`` cell with each sentinel read back.

    Section 10 writes a non-finite float as the string naming it wherever a
    value appears, a list element included, so in a column whose leaf type is
    ``f64`` the text ``"NaN"``, ``"Infinity"`` or ``"-Infinity"`` is that
    number at every depth.
    """
    if isinstance(value, list):
        return [_sentinels_read(element) for element in value]
    if isinstance(value, str) and value in _SENTINELS:
        return _SENTINELS[value]
    return value


def _rebuilt_dtype(neutral: object) -> pl.DataType | None:
    """Return the storage type a payload column of neutral type ``neutral`` is built in.

    A ``date`` or ``datetime`` is built as its text, read as what it names
    after; a ``list[T]`` is a list of ``T`` built the same way, at any depth
    the vocabulary allows. None for a name this reader does not rebuild.
    """
    if not isinstance(neutral, str):
        return None
    if neutral.startswith("list[") and neutral.endswith("]"):
        inner = _rebuilt_dtype(neutral[len("list[") : -1])
        return None if inner is None else pl.List(inner)
    if neutral in _ISO_TEXT_BY_NEUTRAL:
        return pl.String()
    return _POLARS_BY_NEUTRAL.get(neutral)


def _iso_text_read(frame: pl.DataFrame, columns: Any) -> pl.DataFrame:  # noqa: ANN401
    """Return ``frame`` with each ``date`` and ``datetime`` read from its text.

    A date is read as the calendar day its ISO text names, and an instant as
    the zone-naive instant its text names, in nanoseconds where the text
    carries more digits than a microsecond holds and in microseconds
    otherwise: the content grammar writes an instant by its microseconds and
    the nanoseconds past them, so the unit it is read back in does not move
    the digest, only whether its last digits survive. A ``list[date]`` or
    ``list[datetime]`` column is read the same way, element by element.
    """
    read: list[pl.Series] = []
    for column in columns:
        name, neutral = str(column.get("name")), str(column.get("dtype"))
        leaf = neutral.removeprefix("list[" * (depth := neutral.count("list[")))
        leaf = leaf.removesuffix("]" * depth)
        if leaf not in _ISO_TEXT_BY_NEUTRAL:
            continue
        texts = frame[name]
        for _ in range(depth):
            texts = texts.explode()
        unit: Literal["ns", "us"] = "us"
        if leaf == "datetime":
            fractions = texts.str.extract(r"\.(\d+)$").str.len_chars().max()
            if isinstance(fractions, int) and fractions > _MICROSECOND_DIGITS:
                unit = "ns"
        held = frame[name]
        read.append(
            held.list.eval(_iso_read(pl.element(), leaf, unit, depth - 1))
            if depth
            else _iso_read_of(held, leaf, unit)
        )
    return frame.with_columns(read) if read else frame


def _iso_read_of(column: pl.Series, leaf: str, unit: Literal["ns", "us"]) -> pl.Series:
    """Return a column of ISO text read as the dates or instants it names."""
    if leaf == "date":
        return column.str.to_date(_ISO_DATE, strict=True)
    return column.str.to_datetime(_ISO_INSTANT, time_unit=unit, strict=True)


def _iso_read(
    expr: pl.Expr, leaf: str, unit: Literal["ns", "us"], depth: int
) -> pl.Expr:
    """Return ``expr`` with the ISO text ``depth`` lists down read as ``leaf``."""
    if depth:
        return expr.list.eval(_iso_read(pl.element(), leaf, unit, depth - 1))
    if leaf == "date":
        return expr.str.to_date(_ISO_DATE, strict=True)
    return expr.str.to_datetime(_ISO_INSTANT, time_unit=unit, strict=True)


def _payload_schema(
    columns: Any,  # noqa: ANN401
) -> tuple[dict[str, pl.DataType] | None, str | None]:
    """Return the columns a table payload declares, in the order it declares them.

    Neutral names in, storage types out. The content grammar collapses width
    deliberately, so any width carrying the same values re-derives the same
    digest -- which is what lets a consumer rebuild the frame from JSON at
    all, holding the values and no idea what the producer stored them in.
    """
    if not isinstance(columns, list):
        return None, "it declares no columns this reader could read"
    named = [column.get("name") for column in columns if isinstance(column, dict)]
    if len(named) != len(columns) or not all(isinstance(name, str) for name in named):
        return None, "one of its columns states no name"
    if len(set(named)) != len(named):
        return None, "two of its columns claim one name"

    schema: dict[str, pl.DataType] = {}
    for column in columns:
        dtype = _rebuilt_dtype(column.get("dtype"))
        if dtype is None:
            return None, (
                f"its column {column.get('name')!r} is declared "
                f"{column.get('dtype')!r}, which this reader does not rebuild "
                "from JSON"
            )
        schema[str(column.get("name"))] = dtype
    return schema, None


def _local_fingerprint_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return every node whose tree does not hash to the digest beside it.

    And, for each shape of node, what could not be checked at all. A
    ``local_fingerprint`` is taken over a node's operation tree, so
    recomputing one needs the tree -- which the ``audit`` profile does not
    carry, which no leaf has in either profile, and which neither profile
    writes beside a column of values handed over at a line. Saying which
    reading a caller got is the difference between checking the whole chain
    and checking the joins between its links.
    """
    findings: list[Finding] = []
    unverified: list[dict[str, Any]] = []
    for node in nodes:
        node_id = node.get("id")
        published = _digest(node.get("local_fingerprint"))
        if not isinstance(node_id, str) or published is None:
            continue
        tree = node.get("expr")
        if not isinstance(tree, dict):
            unverified.append(node)
            continue
        try:
            decoded = op_node_from_json(tree)
            recomputed = local_fingerprint(decoded)
        except RecursionError:
            findings.append(_too_deep_to_read(node_id, tree))
            continue
        except (TypeError, ValueError) as refusal:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=node_id,
                    message=(
                        f"Node {node_id!r} carries an operation tree this "
                        f"reader cannot parse. {refusal} Until the tree can "
                        "be read, that node's ``local_fingerprint`` is a "
                        "digest of something nobody here can name. Export "
                        "the model again, or read the file with a consumer "
                        "holding the vocabulary the tree was written against."
                    ),
                )
            )
            continue
        if recomputed != published:
            findings.append(
                Finding(
                    section="semantic",
                    severity="error",
                    where=node_id,
                    message=(
                        f"Node {node_id!r} publishes a ``local_fingerprint`` "
                        "that is not the hash of the operation tree beside "
                        "it. Those two are the same calculation said twice, "
                        "once as bytes and once as a tree, and the whole of "
                        "what the executable profile adds is that a reader "
                        "can check one against the other. Where they "
                        "disagree, the node's identity is not the identity "
                        "of what it computes -- so a diff against last "
                        "quarter would report this node unchanged while it "
                        "computed something else. Export the model again."
                    ),
                )
            )
    return [*findings, *_unverified_findings(document, unverified, len(nodes))]


def _too_deep_to_read(node_id: str, tree: dict[str, Any]) -> Finding:
    """Return the finding for a tree nested deeper than this reader parses it.

    The schema reading holds a tree of any depth node by node; reading one
    back into operations, to take its digest again, goes one level inside the
    next and stops at Python's call depth. The producer writes nothing that
    deep -- one line stops it well short -- so a tree this deep was not written
    by one, and its digest is refused unread rather than as a traceback.
    """
    return Finding(
        section="semantic",
        severity="error",
        where=node_id,
        message=(
            f"Node {node_id!r} carries an operation tree {_tree_depth(tree)} "
            "operations deep, deeper than this reader reads one operation "
            "inside another, so its ``local_fingerprint`` cannot be taken "
            "again. No line the producer exports nests this deep. Export the "
            "model again, writing a long line as named intermediate columns."
        ),
    )


def _formulas_fingerprint_findings(
    document: dict[str, Any], nodes: list[dict[str, Any]]
) -> list[Finding]:
    """Return a finding if the formulas-only digest does not follow from the trees.

    Section 12.6's fold, taken again from the document: each node's local
    digest over its tree with every content digest masked, folded over what
    it reads in the order it reads them, then the (id, fingerprint) pairs
    and the unaccounted column names. A leaf carries no content digest, so
    its masked digest is the one it publishes; a column of values handed
    over carries no tree, and its masked bytes are the one constant both of
    its attributes masked make.

    Read rather than taken again in three cases, each saying nothing new: a
    document written before the member carries none; an ``audit`` document
    carries no trees, so the member is read as written, as its local
    fingerprints are; and a document where some node cannot be recomputed
    -- a tree this reader cannot parse, a computed node with no tree -- has
    that refusal reported by the local-fingerprint reading already.
    """
    stated = _digest(document.get(_FORMULAS_FINGERPRINT))
    if stated is None or document.get("profile") == _PROFILE_AUDIT:
        return []
    folded: dict[str, bytes] = {}
    for node in nodes:
        node_id = node.get("id")
        local = _masked_local(node)
        reads = _strings(node.get("reads"))
        if (
            not isinstance(node_id, str)
            or node_id in folded
            or local is None
            or any(read not in folded for read in reads)
        ):
            return []
        folded[node_id] = _merkle(local, [folded[read] for read in reads])
    holes = [
        hole["column"]
        for hole in _objects(document.get("holes"))
        if isinstance(hole.get("column"), str)
    ]
    selected = _masked_selection(document, folded)
    if selected is None:
        return []
    if formulas_digest(folded, holes, selected) == stated:
        return []
    return [
        Finding(
            section="semantic",
            severity="error",
            where=_ENVELOPE,
            message=(
                "The envelope's ``formulas_fingerprint`` does not follow from "
                f"the operation trees this file carries: {len(folded)} nodes "
                "folded over their trees with every content digest masked, "
                f"and {len(set(holes))} unaccounted columns. That digest is "
                "the figure a reviewer quotes to say a quarter changed no "
                "formula, so one that does not reproduce from the trees "
                "beside it says nothing about the formulas at all. Export the "
                "model again."
            ),
        )
    ]


def _masked_local(node: dict[str, Any]) -> bytes | None:
    """Return one node's local digest over its masked tree, or None if it cannot be."""
    tree = node.get("expr")
    if isinstance(tree, dict):
        try:
            return local_fingerprint(formulas_tree(op_node_from_json(tree)))
        except (TypeError, ValueError, RecursionError):
            return None
    if node.get("provenance") in _HANDED_OVER:
        return HANDED_OVER_FORMULAS_LOCAL
    if node.get("kind") in _LEAF_KINDS:
        return _digest(node.get("local_fingerprint"))
    return None


# Why one node's digest was read rather than taken again, and what the reader
# holding it can still do. The ``audit`` profile answers for the whole file;
# the other three answer for one node each, and are read in the order below
# so that a document meeting more than one shape reads the same way twice.
_NO_TREES_ANYWHERE: Final[tuple[str, str]] = (
    (
        "this artifact claims the 'audit' profile, which carries no "
        "operation trees at all"
    ),
    (
        "Export the model again under the 'executable' profile to have "
        "every computed node's tree checked as well."
    ),
)
_A_LEAF_HAS_NONE: Final[tuple[str, str]] = (
    (
        "a leaf carries no operation tree in either profile -- it is a node "
        "nothing on the model defines, an arriving column, a column nothing "
        "accounts for or a running state, and its identity is its name and "
        "its type rather than a tree"
    ),
    (
        "Check a leaf's identity against the column the data actually "
        "arrived with, which is the only place that claim can be read "
        "against anything."
    ),
)
_AN_INJECTION_HAS_NONE: Final[tuple[str, str]] = (
    (
        "a column of values handed to the model at a line carries no "
        "operation tree in either profile, and it is not a leaf either -- "
        "the model does define it, and its ``local_fingerprint`` was taken "
        "over the values themselves rather than over its name and its type, "
        "in an injection record neither profile writes beside the node"
    ),
    (
        "Read such a column against the same column in another run: the "
        "same values stamp alike wherever they were handed over and under "
        "whatever name, so what moves that digest is the data itself "
        "changing -- which is the comparison it exists for."
    ),
)
_NOTHING_EXPLAINS_IT: Final[tuple[str, str]] = (
    (
        "a node that computes states no operation tree here, where this "
        "profile writes one for everything that computes -- so there is "
        "nothing beside it for a digest to be taken over again"
    ),
    (
        "Export the model again: a node whose tree the profile promises and "
        "the file does not carry is a document edited after it was written."
    ),
)
_WHY_A_NODE_CARRIES_NO_TREE: Final[tuple[tuple[str, tuple[str, str]], ...]] = (
    (_A_LEAF, _A_LEAF_HAS_NONE),
    (_AN_INJECTION, _AN_INJECTION_HAS_NONE),
    (_NEITHER, _NOTHING_EXPLAINS_IT),
)


def _unverified_findings(
    document: dict[str, Any], unverified: list[dict[str, Any]], total: int
) -> list[Finding]:
    """Return one remark for each shape of node this reading could not reach.

    One per shape rather than one for the count, because the shapes are not
    unchecked for the same reason and the reason is what a reader acts on. A
    leaf's identity is its name and its type, and a reader can hold that
    against the column the data arrived with. A column of values handed over
    at a line has an identity taken over the values themselves, and the
    reader who went looking for the column it "arrived with" would find
    nothing to look at. A single sentence covering both would be false of
    one of them, and the count would go on being honest while the account of
    the count was not.

    The ``audit`` profile is the one remark that stays one: there the reason
    is the profile rather than the node, and it is the same reason for every
    node in the file.
    """
    if not unverified:
        return []
    if document.get("profile") == _PROFILE_AUDIT:
        return [_unverified_remark(len(unverified), total, _NO_TREES_ANYWHERE)]
    counted = Counter(_shape_of(node) for node in unverified)
    return [
        _unverified_remark(counted[shape], total, said)
        for shape, said in _WHY_A_NODE_CARRIES_NO_TREE
        if counted[shape]
    ]


def _shape_of(node: dict[str, Any]) -> str:
    """Return which account the file gives of a node carrying no tree.

    The ``provenance`` first: it is section 8's own positive claim that a
    whole column of values was handed over, and it is what tells such a node
    from an arriving column, which shares its ``kind``.
    """
    if node.get("provenance") in _HANDED_OVER:
        return _AN_INJECTION
    if node.get("kind") in _LEAF_KINDS:
        return _A_LEAF
    return _NEITHER


def _unverified_remark(count: int, total: int, said: tuple[str, str]) -> Finding:
    """Return one remark about the nodes of one shape, and the move it leaves."""
    because, next_move = said
    nodes = (
        f"One of this artifact's {total} nodes had its"
        if count == 1
        else f"{count} of this artifact's {total} nodes had their"
    )
    return Finding(
        section="semantic",
        severity="warning",
        where=_ENVELOPE,
        message=(
            f"{nodes} ``local_fingerprint`` read rather than recomputed, "
            f"because {because}. A ``local_fingerprint`` is the leaf of the "
            "identity chain; what was checked here is that every "
            "``fingerprint`` follows from the leaf published beside it and "
            "from what the node reads -- the joins between the links rather "
            f"than the links themselves. {next_move}"
        ),
    )


# --- the enrichment layer ----------------------------------------------------


def _enriched_nodes(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every node carrying a value, a walk-through of one, or both.

    The enrichment reading's own subject, read once and used twice: it is
    what that reading walks, and it is what the report names the section
    for. A document carrying no values has not been read for any, and a
    report naming the section anyway would tell a reader the numbers were
    checked where there were none to check.
    """
    return [
        node
        for node in _objects(document.get("nodes"))
        if node.get("trace") is not None or node.get("value_sample") is not None
    ]


def _enrichment_findings(nodes: list[dict[str, Any]], width: int = 1) -> list[Finding]:
    """Return what the values an artifact carries say against each other.

    Enrichment is optional and usually absent: a graph exported without a
    collected frame describes the calculation and samples nothing, and the
    places a sample and a trace would sit are then not there at all. Where
    it is present, three things have to hold or the numbers in front of a
    reader are not the numbers the model produced -- and where the artifact
    also carries the rendering the walk-through was written from, the two
    have to open on one line.

    **A superseded definition may carry a value, and only when it says so.**
    ``retained: true`` is the producer stating that it held that definition's
    own output to the export and read the number off it, which is the one
    reading under which the number is the definition's own. Without the
    declaration the refusal below is exactly what it was: a value on a
    definition the frame no longer holds is the number that replaced it. The
    declaration is what a producer that did not retain cannot accidentally
    write, which is why it lifts the refusal rather than weakening it.

    **Neither of the two nodes that are not columns is a superseded
    definition**, and the refusal does not reach either. That refusal is
    about a *column* the frame no longer holds, where the only number
    available to read is the one that replaced it. A running state and the
    compilation that carries it are not columns at all -- nothing on the
    frame ever held one, so ``in_final_schema`` is false by construction
    rather than by a later assignment -- and what they carry is the
    compilation's own output, read out of the compilation rather than off a
    column that outlived it. Requiring ``retained`` there would ask a
    producer to declare that it had held aside a column which never existed.
    """
    findings: list[Finding] = []
    for node in nodes:
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        if (
            node.get("kind") not in {_A_RUNNING_STATE, _A_COMPILATION}
            and node.get("in_final_schema") is False
            and node.get("retained") is not True
        ):
            findings.append(
                Finding(
                    section="enrichment",
                    severity="error",
                    where=where,
                    message=_value_on_a_superseded_definition(where),
                )
            )
        # Once per policy the values are read along. The three readings
        # below are about one policy's number and one policy's
        # walk-through, so an axis carrying five policies is five readings
        # of one node rather than one reading of five values.
        for position in range(width):
            trace = _at(node, "trace", position, width)
            sample = _at(node, "value_sample", position, width)
            if trace is None:
                continue
            findings += _walk_through_opening_findings(where, node, trace)
            if sample is None:
                findings.append(
                    Finding(
                        section="enrichment",
                        severity="error",
                        where=where,
                        message=_trace_with_no_sample(where),
                    )
                )
                continue
            findings += _trace_result_findings(where, trace, sample)
    return findings


def _walk_through_opening_findings(
    where: str,
    node: dict[str, Any],
    trace: Any,  # noqa: ANN401 — the walk-through at one position of the axis
) -> list[Finding]:
    """Return a finding where a walk-through does not open on what it walks.

    A trace's first line is the calculation as the walk-through shows it, and
    it is produced from one thing: the engine's rendering of that node, put
    through the producer's own cleaning. Where the artifact carries that
    rendering as well -- the ``gaspatchio_lowered`` facet, which an export
    writes when it is asked to -- the file holds one fact twice, and this
    reads the two against each other. It is the same cleaning the producer
    applied, called at its own definition rather than reimplemented here.

    **What it does not establish**, and the three limits are worth stating
    plainly:

    (i) The cleaning is **lossy** by design. A clip's bounds collapse to
    ``[clipped]`` and a lookup's internals to ``[lookup]``, so a number
    edited inside one of those regions passes this reading without a mark.

    (ii) **Tampering both records consistently passes.** Someone who edits
    the rendering and the walk-through to agree has produced a document this
    reading has nothing to say about.

    (iii) An export carrying no rendering, or no walk-through, says nothing
    at all here -- and neither is written by default.

    **It is not a reading of the as-written ``formula``.** A walk-through is
    generated from the engine's rendering, which names columns rather than
    node ids and looks nothing like the line the model's author typed;
    holding ``formula`` up against the first step would refuse every enriched
    artifact this producer has ever written. What checks the as-written text
    is the identity chain, where it rides inside the node's own bytes.

    Warning rather than error, and for a stated reason: the comparison runs
    through a cleaning that exists to make a line readable, so it may be
    changed in a later version for reasons that have nothing to do with any
    model. An error grade would turn a rendering change into a refusal of
    honest documents.

    This reading narrows the surface a misstatement can hide in. It verifies
    nothing -- the identity fields are what verify.
    """
    facets = node.get("facets")
    steps = _objects_of(trace)
    if not isinstance(facets, dict) or not steps:
        return []
    lowered = facets.get(_LOWERED_FACET)
    if not isinstance(lowered, dict):
        return []
    rendered = lowered.get(_LOWERED_TEXT)
    opening = steps[0].get("expr") if isinstance(steps[0], dict) else None
    if not isinstance(rendered, str) or not isinstance(opening, str):
        return []
    cleaned = _minimal_clean(rendered)
    if cleaned == opening:
        return []
    return [
        Finding(
            section="enrichment",
            severity="warning",
            where=where,
            message=_walk_through_opens_elsewhere(where, cleaned, opening),
        )
    ]


def _walk_through_opens_elsewhere(where: str, cleaned: str, opening: str) -> str:
    """Return the remark for a walk-through and a rendering telling two stories."""
    return (
        f"The walk-through on {where!r} opens on {opening!r}, and the "
        f"rendering this artifact carries for the same node reads {cleaned!r} "
        "once the producer's own cleaning has run over it. A walk-through's "
        "first line is that rendering and nothing else, so the two are one "
        "fact written twice and they disagree -- which of them moved is not "
        "on the wire, so neither is accused. A reviewer reading the "
        "substitution below it is being walked through a calculation that is "
        "not the one recorded beside it. Export the model again with the "
        "frame the values were read from. This is a consistency reading and "
        "not a verification: the cleaning it runs through is lossy, and the "
        "identity fields are what verify."
    )


def _trace_result_findings(where: str, trace: Any, sample: Any) -> list[Finding]:  # noqa: ANN401
    """Return a finding if a trace does not end at the value beside it.

    A trace is a substitution -- the rendered formula with each name replaced
    by the value that column held -- so its last line is the sample, and a
    trace ending anywhere else is a walk-through of a calculation the model
    did not do.

    **A per-period column's trace ends at the first period.** The sample of
    such a column is the whole run of values and the walk-through is of one
    period, so what the last line states is the run's first value. That is
    the producer's own reading and it is the one held here; comparing the
    line against the whole run would refuse every projection ever exported.

    A last line stating no result at all is not a disagreement. It is a trace
    declining to name what it reached, which is what a producer writes where
    the value it would name is null, and there is nothing there to be wrong.
    """
    steps = [step for step in _objects_of(trace) if isinstance(step, dict)]
    if not steps or "result" not in steps[-1]:
        return []
    reached = steps[-1]["result"]
    stated = sample[0] if isinstance(sample, list) and sample else sample
    if reached == stated:
        return []
    return [
        Finding(
            section="enrichment",
            severity="error",
            where=where,
            message=(
                f"The trace on {where!r} ends at {reached!r}, and the "
                f"``value_sample`` beside it is {stated!r}. A trace is the "
                "rendered formula with each name replaced by the value that "
                "column held, so its last line is the sample by "
                "construction -- and where a column holds one value per "
                "period the walk-through is of the first period, so the last "
                "line is that first value. The two disagreeing means the "
                "walk-through in front of a reader is of a calculation this "
                "model did not do, which is worse than no walk-through at "
                "all. Export the model again with the frame the values were "
                "read from."
            ),
        )
    ]


def _objects_of(section: Any) -> list[Any]:  # noqa: ANN401
    """Return the entries of one array, or nothing where it is not an array."""
    return section if isinstance(section, list) else []


def _trace_with_no_sample(where: str) -> str:
    """Return the refusal for a walk-through with no value to walk through."""
    return (
        f"Node {where!r} carries a ``trace`` and no ``value_sample``. A "
        "trace is a substitution: it is the formula with each name replaced "
        "by the value that column held, and its last line is the number the "
        "substitution reached. With no sample beside it there is nothing "
        "that number can be checked against, and a walk-through nobody can "
        "check is a walk-through nobody has to keep. Export the model again "
        "with the frame the values were read from, or drop the trace."
    )


def _value_on_a_superseded_definition(where: str) -> str:
    """Return the refusal for a value hanging off a definition nothing holds."""
    return (
        f"Node {where!r} carries enrichment and states "
        "``in_final_schema: false``. A value is read out of the finished "
        "frame, so only the definition the column actually ends up holding "
        "can honestly claim one -- a superseded definition shown carrying a "
        "value is shown carrying the number that replaced it, which is the "
        "wrong number against the right formula and worse than no number at "
        "all. A reader checking that calculation would find it correct and "
        "would be checking the wrong calculation. Export the model again "
        "with the frame the values were read from, or hold this "
        "definition's own output to the export, read the values off that, "
        "and state ``retained: true``."
    )


# --- the portability layer ---------------------------------------------------


def _portability_findings(document: dict[str, Any], engine: str) -> list[Finding]:
    """Return every node ``engine`` cannot run, one finding each.

    Three answers and they are not the same answer. A node the producer
    could not classify refuses every engine, because nothing is known about
    what it does. A node whose text needs engines and does not name this one
    refuses this one. A node that names no engines at all has made **no
    claim** -- an absent field is not an empty one, and reading it as "needs
    nothing" would turn a producer's silence into a promise it never made.

    One finding per node, and the tier is read first. A node nobody could
    classify is not additionally reported for the engines it happens to
    name: the stronger statement is already the true one, and two findings
    about one node would double-count the same escape hatch in a total whose
    whole value is that it is countable.

    Ahead of all of them, where the artifact names the engine nowhere, one
    remark saying so. It is read before the refusals rather than after them
    because it is a caveat on the question and not a summary of the answer:
    a reader who has already counted the refusals has taken the count at
    face value, which is exactly what a mistyped engine name earns.

    After all of them, the reach. ``engines`` is a node's own requirement and
    not the closure over what it reads (spec section 8.3), so a column
    composed on an escaped one states ``[]`` truthfully and is still a column
    that cannot be evaluated: the escape is upstream of it. Those nodes are
    named last and as remarks rather than refusals, because the count of
    refusals is the count of places a move to another engine has to be
    rewritten and nothing here has to be rewritten -- each of them runs as
    soon as what it reads does.
    """
    nodes = _objects(document.get("nodes"))
    findings = _unnamed_engine_findings(nodes, engine)
    for node in nodes:
        node_id = node.get("id")
        where = node_id if isinstance(node_id, str) else _ENVELOPE
        tier = node.get("tier")
        if tier is None:
            # A leaf has nothing to execute, so no engine has anything to
            # refuse. Asking whether an arriving column runs under jax is
            # asking a question about no calculation.
            continue
        if tier == _OPAQUE:
            findings.append(
                Finding(
                    section="portability",
                    severity="error",
                    where=where,
                    message=_opaque_node(where, engine),
                )
            )
            continue
        if "engines" not in node:
            findings.append(
                Finding(
                    section="portability",
                    severity="warning",
                    where=where,
                    message=_no_claim(where, engine),
                )
            )
            continue
        needs = _strings(node.get("engines"))
        if needs and engine not in needs:
            findings.append(
                Finding(
                    section="portability",
                    severity="error",
                    where=where,
                    message=_needs_another_engine(where, engine, needs),
                )
            )
    return findings + _reached_through_findings(nodes, findings, engine)


def _reached_through_findings(
    nodes: list[dict[str, Any]],
    refusals: list[Finding],
    engine: str,
) -> list[Finding]:
    """Return one remark per node that reads a refusing node, directly or not.

    The refusals above are each a node's account of its own text. This is the
    rest of the answer to the question a reader actually asked -- which
    columns of this model does ``engine`` not produce -- and it is a
    different question, because a node's ``engines`` describes the node and
    an evaluation needs the inputs too.

    Walked over ``reads`` with the visited set carried, so an artifact
    holding a cycle (a file is a thing that can be edited after it was
    written) is answered rather than recursed into forever. A node that
    refuses on its own account is not reported again here: it is already
    counted, and the stronger statement is the true one.
    """
    refusing = {
        finding.where
        for finding in refusals
        if finding.severity == "error" and finding.where != _ENVELOPE
    }
    if not refusing:
        return []
    reads = {
        node["id"]: _strings(node.get("reads"))
        for node in nodes
        if isinstance(node.get("id"), str)
    }
    findings: list[Finding] = []
    for node_id in reads:
        if node_id in refusing:
            continue
        reached = _refusing_ancestors(node_id, reads, refusing)
        if reached:
            findings.append(
                Finding(
                    section="portability",
                    severity="warning",
                    where=node_id,
                    message=_reached_through(node_id, engine, reached),
                )
            )
    return findings


def _refusing_ancestors(
    node_id: str,
    reads: dict[str, list[str]],
    refusing: set[str],
) -> list[str]:
    """Return the refusing nodes ``node_id`` reaches, nearest mention first."""
    seen = {node_id}
    frontier = list(reads.get(node_id, ()))
    reached: list[str] = []
    while frontier:
        current = frontier.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if current in refusing:
            reached.append(current)
            continue
        frontier.extend(reads.get(current, ()))
    return reached


def _unnamed_engine_findings(nodes: list[dict[str, Any]], engine: str) -> list[Finding]:
    """Return one remark where nothing in the artifact names ``engine``.

    Not a refusal, and not a claim about which engines exist. This reader
    holds no list of them -- the artifact is what the question is asked of,
    and a list kept here would refuse tomorrow's engine on the strength of
    today's build. What it can say is that the name reaches nothing in this
    file, which is the difference between "no node needs anything but the
    format's own operations" and ``engine="polar"`` for ``polars``. Both
    return the same findings, and only one of them is an answer.
    """
    named = sorted({name for node in nodes for name in _strings(node.get("engines"))})
    if engine in named:
        return []
    does_name = (
        f"The engines it does name are {', '.join(repr(name) for name in named)}."
        if named
        else (
            "No node in it names any engine at all, which is what a model "
            "written entirely in the format's own operations looks like."
        )
    )
    return [
        Finding(
            section="portability",
            severity="warning",
            where=_ENVELOPE,
            message=(
                f"No node in this artifact names {engine!r} in its "
                f"``engines``, so nothing here was read against that name. "
                f"{does_name} A reading against an engine the file never "
                "mentions cannot tell a name this model simply does not "
                "need from a name that was mistyped: both come back as "
                "every node naming some other engine refusing it and every "
                "node naming none staying silent. Check the spelling before "
                "the count is quoted, and read what follows as what it is "
                "-- the nodes written in another engine's expression "
                "language."
            ),
        )
    ]


def _opaque_node(where: str, engine: str) -> str:
    """Return the refusal for a node whose own producer could not classify it."""
    return (
        f"Node {where!r} has tier ``opaque``: somewhere in its calculation "
        "is an identifier the producer carries and cannot classify, so what "
        "the node does is not stated anywhere in this file. That refuses "
        f"{engine!r} and every other engine equally -- nothing can be asked "
        "to run a calculation nobody can name. Rewrite the line in the "
        "framework's own operations, or read the file with the producer's "
        "own engine, which is the one place the identifier means something."
    )


def _no_claim(where: str, engine: str) -> str:
    """Return the remark for a node that says nothing about what it needs."""
    return (
        f"Node {where!r} states no ``engines``, so this artifact makes no "
        f"claim about whether {engine!r} can run it. An absent field and an "
        "empty one are different statements: an empty array is the producer "
        "saying the node reaches into no engine at all, and an absent field "
        "is the producer declining to say, which is what it writes when it "
        "cannot see which engines a fragment needs. This node is neither "
        "counted as portable nor counted against the total. Export the "
        "model again from a producer that can read its own trees, or check "
        "the calculation by hand."
    )


def _needs_another_engine(where: str, engine: str, needs: Sequence[str]) -> str:
    """Return the refusal for a node written in somebody else's language."""
    named = ", ".join(repr(name) for name in needs)
    return (
        f"Node {where!r} needs {named} and not {engine!r}: part of its "
        "calculation is written in one engine's own expression language "
        "rather than in the format's operations. That is the escape hatch "
        "working as intended -- it is declared rather than hidden, which is "
        "what makes the cost of it countable -- and it is the cost: this "
        "node is where a move to another engine stops. Rewrite the line in "
        f"the framework's own operations if it has to run under {engine!r}."
    )


def _reached_through(where: str, engine: str, reached: Sequence[str]) -> str:
    """Return the remark for a node the escape hatch is upstream of."""
    named = ", ".join(repr(node_id) for node_id in reached)
    return (
        f"Node {where!r} is written entirely in the format's own operations "
        f"and still cannot be evaluated under {engine!r}, because it reads "
        f"{named}, which cannot. Its own ``engines`` is empty and that is "
        "true of it: the field is what a node's own text needs and not the "
        "closure over what it reads, so an empty array here answers for this "
        "line and not for the columns feeding it. Nothing on this line has "
        "to be rewritten -- it runs under "
        f"{engine!r} as soon as what it reads does."
    )
