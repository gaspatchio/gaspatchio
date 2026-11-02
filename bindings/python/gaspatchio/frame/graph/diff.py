# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""What moved between two artifacts of one model, and what only looks like it.

A model-change review holds two files a quarter apart and has to separate two
findings that have different owners. **The model moved**: somebody edited a
formula, added a column, stopped computing one. **The data moved**: the
mortality basis was re-sourced, a new set of policies was run, a simulation
handed over a different column of shocks. Both change the numbers. Only the
first is a change to the model, and a report that ran them together would be a
report nobody could act on.

:func:`diff_artifacts` is the whole of the surface, and its subject is two
**artifacts** rather than two graphs held in one process. That is what a
quarter-over-quarter comparison actually has: two documents, one of them
written by a release of this framework that no longer exists, neither of them
re-runnable.

## The identity core, and what is only metadata

The report compares **the identity core and never the two documents'
serialised bytes**: the envelope's ``graph_fingerprint``, each node's
``local_fingerprint`` and ``fingerprint``, the digests the assumptions section
publishes, and the content digest of the book each document was built over --
each taken over content under one byte grammar, so none of them moves with
the release that wrote it. Two exports of an untouched model differ -- they
were written at different moments and say so -- and ``created_at``, the
producing tool's version and the run's own label, source and revision are
**metadata, not drift**: none of them is read. A new release of the exporter
moves nothing in the identity core, and a report that called a release a
change to somebody's valuation would be one a reviewer learns to ignore. Two
members of the run's own block are read: the file it names for the policy
data, only where a document states no book digest to read instead, and the
digest of the results file it wrote, which is the one exception to all of
this and has a section of its own below.

The report does say which two documents it was written about -- each by its
``graph_fingerprint``, by the ``document_digest`` sealing it where it carries
one, and described by when it was written and what wrote it. A stored report
is read long after the call that produced it, by somebody who does not hold
the two files, and a report that could not say what it compared would be a
finding with no subject. That naming is written for the reader and read by
nothing: it takes no part in the comparison, and every claim below would be
the same claim without it.

**The seal is recorded here for a reason the comparison never uses.** A seal
a document carries is a digest whoever edits that document can take again, so
a forgery that re-seals itself is internally consistent and no reading of the
file alone will catch it. What catches it is a record filed elsewhere saying
what the seal was, and a filed change report is one: a document whose seal
disagrees with every report that ever cited it is a document somebody
rewrote. That is what a report is for once the two files are no longer in
anybody's hands.

## The results file, and what its digest is evidence of

A run exported with its results file named records the sha256 of that file
in ``model.results``, and where both documents record one the report compares
the two. It is the one reading here that can see a number move under a model
that did not: a column written over in a way the frame cannot see -- around
its own handle on the query plan -- moves the file and no digest in the
graph, and a comparison of the graph alone would say nothing moved over two
different sets of results. A column written over through that handle is a
hole in the graph, and moves it.

**The digest is the file's, not the numbers', and it is the one exception.**
Every other digest the report reads is taken over content under one byte
grammar; this one is taken over a file's bytes, and those move with the
writer as well as with the values -- a results file records the library
versions and platform that wrote it. So a new release of the exporter, or
the same release on another machine, can reach the report here and nowhere
else, by design: two such runs differ in this digest where every number
agrees. The entry therefore says the file moved, and whether the two results
agree is what ``gspio compare`` says, to the tolerance the specification
states. Where only one document records a results file's digest, or neither
does, nothing is compared and no entry is written, and an absent entry says
nothing about the results either way.

## Self, inherited, and the one thing that is neither

A node in both files whose **own** digest moved was edited: its formula is
not the formula it was. A node whose local digest held while its Merkle
digest moved was not touched at all -- its answer simply cannot be what it
was, because something it reads moved. That distinction is the report's
whole value, and it is why a horizon extended from 99 to 100 reads as one
edited timeline and a tail of inherited movement rather than as a model
rewritten end to end.

The third case is the one worth stating carefully. **An assumption base's
own digest is inside the node that looks it up** -- deliberately, because a
lookup against a different table is a different calculation -- so
re-sourcing a mortality basis moves the local fingerprint of every node
that reads it. Spelling that as an edit would tell a committee the model
changed in a quarter when nobody touched it. So where a node's local digest
moved, its as-written ``formula`` is the text it was, it reads what it read,
and it names an assumption entry whose digest moved, the movement is
attributed to the base: the ``data`` section names the base, and the node is
reported as having inherited the change.

Two limits of that attribution are stated rather than hidden:

- **A base named after its contents cannot be attributed.** A table keeps
  its own name across a re-sourcing, so the entry that moved and the node
  that reads it are joined by one string. A schedule and a curve state no
  name of their own and are called after what they are made of, so
  re-sourcing one renames it: no entry is held by both files, nothing pairs,
  and the node reading it is reported as having changed itself. The ``data``
  section still says which curve went and which arrived, which is what tells
  a reader what actually happened.
- **An edit written over an unchanged formula text, in the same quarter the
  base it reads was re-sourced, is attributed to the base.** The two
  movements arrive as one digest, and the artifact carries nothing that
  separates them.

A column of values handed over wholesale is the one node where the
attribution is exact. It has no formula at all: its identity was taken over
the values themselves and the container they arrived in, so nothing else is
in those bytes and a movement there is data by construction.

## Renames, and the claim this report will not make

A rename is reported as a rename **only where the framework saw one** --
where the later artifact carries a node whose ``provenance`` is the frame's
own rename record, reading exactly one node the earlier artifact holds. A column
renamed in the model's source text instead reaches the report as one
calculation removed and one added, with ``fingerprint_equal_to`` on the new
node naming the old one where the pairing is unique.

That hint is a hint and never a verdict. Fingerprints are deliberately not
unique -- two columns computed the same way share one, which is why the
graph digest hashes *pairs* of name and fingerprint -- so an asserted rename
on that evidence would be a deletion plus a coincidentally identical new
column reported as neither (*Sharp knives, no magic*). The framework does
not make a claim its own identity scheme says it cannot support; it puts the
evidence in front of the reviewer and lets the model's own record settle it.

**Where either end of that pairing is a column of values handed over at a
line, the hint is written into ``values_equal_to`` instead**, because the
digest the two share was taken over the numbers rather than over a
calculation: what it evidences is the same values arriving twice, and a
calculation under a new name is not among the things it can mean.

## Nodes whose identity is a digest with no formula beside it

Three kinds of node have no as-written formula and are identified by a
digest alone: a column the data arrived with, a column nothing in the model
accounts for, and a column of values injected at a line. They diff on
exactly that digest. A hole present in both quarters under one digest is no
change at all; a hole that appears is an addition, and the column it names
is a column somebody now has to explain; a hole that is closed is that node
removed and a computed one added in its place, which is the model gaining an
account of a column it could not account for.

**A hole the frame arrived holding also carries a stamp of what it held**,
in the holes section rather than in its node, and the graph fingerprint
folds it beside the hole's name. A file the model's setup joined in plain
Polars, edited between the quarters, therefore moves the envelope's figure
and no node digest at all. The report reads the stamps too, so that edit is
a ``data`` entry of kind ``hole`` naming the column, and never a silence
over two different fingerprints.
"""

from __future__ import annotations

import posixpath
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Final, Literal

from .artifact import DOCUMENT_DIGEST_FIELD

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from .graph_models import NodeId
    from .values_moved import ValuesReport

__all__ = [
    "DIFF_REPORT_VERSION",
    "Change",
    "ChangeKind",
    "ChangeOrigin",
    "ComparedDocument",
    "DataChange",
    "DataKind",
    "DiffReport",
    "SourceChange",
    "diff_artifacts",
]

# The report's own identifier, resolved the way an artifact's is: a key, not a
# version to parse. A consumer holding a stored report reads it under the
# grammar this names rather than under whatever reader it has to hand.
DIFF_REPORT_VERSION: Final[str] = "gaspatchio-graph-diff/v0-preview.2"

# What happened to one calculation. ``changed`` is a node both files hold
# whose digests moved; ``added`` and ``removed`` are a node only one of them
# holds; ``renamed`` is the one claim this report makes about a pair, and it
# is made only on the framework's own record of the name-move.
ChangeKind = Literal["added", "removed", "changed", "renamed"]

# Which of the two things happened to a node both files hold. ``self`` is the
# formula moving; ``inherited`` is the formula standing still while what it
# reads moves. Null on a node that is not in both files, because the question
# is about a pair.
ChangeOrigin = Literal["self", "inherited"]

# What moved besides a calculation. The first three are the assumption bases
# the artifact's own section names; ``model_points`` is the policy data the run
# consumed; ``hole`` is a column the frame arrived holding that the model cannot
# account for, compared on the stamp of what it held; ``injection`` is a whole
# column of values handed over at a line in the model; ``results`` is the
# output file the run wrote, compared only where both runs named one.
DataKind = Literal[
    "table", "schedule", "curve", "model_points", "hole", "injection", "results"
]

# The kinds of entry the assumptions section carries, which are the ones a
# node's ``reads_assumptions`` can name.
_ASSUMPTION_KINDS: Final[frozenset[str]] = frozenset({"table", "schedule", "curve"})

# What the frame writes on a node it minted for a name-move, and the only
# evidence this report accepts for a rename.
_RENAME: Final[str] = "rename"

# What a node's ``provenance`` says when the column is not computed at all
# but was handed over whole -- at a line inside the model, or back through
# an explicit re-entry. Both are values rather than formulas, so a movement
# on either is data and can be nothing else, and a reading that took only
# the first would call a re-entry's own column a calculation.
_HANDED_OVER: Final[frozenset[str]] = frozenset({"injected", "continuation"})

# How many nodes a fingerprint may stand for before the pairing hint is
# withheld. One removed and one added is a pairing; anything else is a guess.
_UNIQUE: Final[int] = 1

# How many columns a name-move reads. Exactly one: a node carrying another
# column's value under a new name reads that column and nothing else.
_ONE_COLUMN: Final[int] = 1

# The envelope member standing for a document's formulas with its data left
# out. Optional: a document written before it carries none, and a report on
# such a document says nothing about formulas it has no figure for.
_FORMULAS_FINGERPRINT: Final[str] = "formulas_fingerprint"

# How each kind of data entry is named on the formulas line.
_DATA_WORDS: Final[dict[str, str]] = {"model_points": "model points"}

# The two documents a comparison reads, as its sentences name them.
_SIDES: Final[tuple[str, str]] = ("earlier", "later")

# What a document with no book digest is said to be, in the reason an
# uncompared book's entry carries.
_WITH_NO_DIGEST: Final[str] = "states no digest of its book"

# What ``gspio diff`` prints under a results entry, and the comparison page
# beside one, in the same words (``viewer/src/reader/compare.ts``). A results
# file's digest is taken over its bytes, which move with the writer as well as
# with the values, so the sentence says the file moved and names the step that
# says whether the two results agree, to a stated tolerance. The entry's
# ``reason`` stays null: this says how to read an entry that was compared, not
# why one could not be.
_RESULTS_FILE_MOVED: Final[str] = (
    "The results file differs between the two runs. A results file also "
    "records the library versions and platform that wrote it, so this says the "
    "file moved, not that any number did. To see whether the two results agree, "
    "run gspio compare on the later audit file and the two results files."
)

# The same entry where the two runs are of two different calculations. gspio
# compare asks whether two runs of one calculation agree and refuses a results
# file whose recorded graph fingerprint is not the artifact's
# (``engines/compare.py``); what moved between two versions, and by how much,
# is what this command measures when it reads the two results files.
_RESULTS_OF_TWO_CALCULATIONS: Final[str] = (
    "The results file differs between the two runs, and so does the model: the "
    "two audit files state different graph fingerprints, so the files hold the "
    "numbers of two different calculations. The calculations listed above are "
    "the ones whose numbers can have moved. To see which did, and by how much, "
    "run gspio diff on the two audit files with --results and the two results "
    "files, earlier first."
)

# And where the calculation held and the book under it moved. The same command
# pairs the two files' rows by policy, so new business and lapses are counted
# rather than refused, and over the policies both books hold it says how far
# each line moved.
_RESULTS_OVER_TWO_BOOKS: Final[str] = (
    "The results file differs between the two runs, and so does the book the "
    "model ran over, so the numbers can have moved with the data. To see which "
    "did, and by how much, run gspio diff on the two audit files with --results "
    "and the two results files, earlier first: it pairs the two books' policies "
    "and counts those only one of them holds."
)

# Where the two results files were read and measured, the entry says so in
# place of the step that measures them: the values below it are that step.
_RESULTS_READ: Final[str] = (
    "The results file differs between the two runs. Both files were read, and the "
    "values reported here compare them line by line and policy by policy."
)


@dataclass(frozen=True, slots=True)
class Change:
    """One calculation that moved, and what kind of movement it was.

    Attributes:
        node: The node id the change is about, in the later artifact where
            there is one and in the earlier artifact for a removal.
        column: The column that node defines, or None where the node is not
            a column of the model at all.
        kind: Whether the calculation was added, removed, changed, or is the
            far side of a name-move the framework recorded.
        change_origin: For a node both files hold, whether its own formula
            moved or only what it reads. Null for every other kind, because
            the question is about a pair.
        renamed_from: The node this one's name moved from, on a ``renamed``
            change and nowhere else.
        fingerprint_equal_to: On an added node, the removed node it shares a
            fingerprint with where exactly one of each shares it. **A hint,
            never an assertion**: fingerprints are not unique by design, and
            a rename is a claim only the model's own record can support.
        values_equal_to: The same pairing, under a weaker label, where
            either end is a column of values handed over at a line. A
            computed node's fingerprint stands for a calculation, so two
            agreeing is evidence the same calculation is present under
            another name; an injected column's is a stamp over the numbers
            themselves, so two of those agreeing says the same values were
            handed over twice and nothing at all about a computation. The
            pairing is the same one either way -- what differs is what the
            evidence supports, and the reader should not have to infer that
            from the node kind.

    Examples:
        >>> from gaspatchio.frame.graph import Change
        >>> change = Change(
        ...     node="death_claims@1",
        ...     column="death_claims",
        ...     kind="changed",
        ...     change_origin="self",
        ...     renamed_from=None,
        ...     fingerprint_equal_to=None,
        ...     values_equal_to=None,
        ... )
        >>> change.to_dict()["change_origin"]
        'self'

    """

    node: NodeId
    column: str | None
    kind: ChangeKind
    change_origin: ChangeOrigin | None
    renamed_from: NodeId | None
    fingerprint_equal_to: NodeId | None
    values_equal_to: NodeId | None

    def to_dict(self) -> dict[str, Any]:
        """Return the change as plain JSON data, empty fields included.

        A field written as null is the report saying the question does not
        arise for this change; a field left out would leave a consumer to
        guess which of the two it was.
        """
        return {
            "node": self.node,
            "column": self.column,
            "kind": self.kind,
            "change_origin": self.change_origin,
            "renamed_from": self.renamed_from,
            "fingerprint_equal_to": self.fingerprint_equal_to,
            "values_equal_to": self.values_equal_to,
        }


@dataclass(frozen=True, slots=True)
class DataChange:
    """One thing besides a calculation that moved, and its digest on either side.

    Attributes:
        kind: What moved -- an assumption base of one of the three kinds, the
            policy data the run consumed, a column the frame arrived holding
            that the model cannot account for (a hole, compared on the stamp
            of what it held), a column of values handed over at a line, or
            the results file the run wrote.
        name: What it is called, or None where the thing has no name of its
            own. A table is named and a schedule and a curve are not, and
            inventing a name for one would be a claim about the model rather
            than a fact about it. Policy data and a results file are named by
            the path their run recorded, where it recorded one.
        before: The digest the earlier artifact published for it, or None
            where the earlier artifact did not read it at all.
        after: The digest the later artifact published, or None where the
            later artifact no longer reads it.
        reason: Why the two could not be compared, on an entry that says
            so, and None on every entry that reports a movement. The policy
            data carries one where a document states no digest of its book
            and the two runs did not both name a file to compare instead:
            nothing is left to say whether the policies are the same, and an
            empty ``data`` would read as "nothing moved". A hole carries one
            where one document stamps what it held and the other does not.
            The entry is written instead, naming what the documents said,
            and it counts as drift.

    Examples:
        >>> from gaspatchio.frame.graph import DataChange
        >>> moved = DataChange(
        ...     kind="table",
        ...     name="mortality",
        ...     before="sha256:aa",
        ...     after="sha256:bb",
        ... )
        >>> moved.to_dict()["name"]
        'mortality'
        >>> moved.reason is None
        True

    """

    kind: DataKind
    name: str | None
    before: str | None
    after: str | None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the entry as plain JSON data, for a report written to a file."""
        return {
            "kind": self.kind,
            "name": self.name,
            "before": self.before,
            "after": self.after,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ComparedDocument:
    """One of the two documents a report was written about.

    The caller holds both files and knows which two they are. The report
    outlives that call: it is filed, and read a quarter later by somebody
    who holds the report and nothing else. So the report says what it
    compared, and this is how it says it.

    The document is **identified** by its ``graph_fingerprint``, which is the
    identity core's own name for a document, **sealed** by its
    ``document_digest`` where it carries one, and **described** by when it was
    written and what wrote it. None of the three reaches a :class:`Change` or
    a :class:`DataChange`, and two documents agreeing on the fingerprint while
    differing in the rest are one model exported twice.

    **Recording the seal is what makes an edit-and-reseal detectable.** A seal
    inside a document is a digest whoever edits the document can recompute, so
    a forgery that re-seals itself is self-consistent and the standalone file
    cannot catch it. What catches it is a record filed elsewhere that says
    what the digest was: this field, in a report written and filed at the time
    the original was read. A document that disagrees with every report that
    ever cited it is a document somebody rewrote.

    Attributes:
        graph_fingerprint: The one digest standing for the whole model the
            document holds, or None where the document carries none.
        document_digest: The seal the document carried when it was read, or
            None where it carried none -- an unsealed document, which is a
            conforming document. It is recorded and never compared: two
            exports of an untouched model carry two seals and one
            ``graph_fingerprint``, because a seal covers the record and the
            fingerprint covers the calculation. It is null in every report
            the framework writes today, because nothing this producer
            exports is sealed unless a caller asks -- and that is a cell
            standing for a document that exists and that a caller can fill
            this afternoon, which is what separates it from a member
            invented for a record naming no document at all.
        created_at: When the document says it was written. A later stamp is
            not a later model.
        producer: What wrote it and which version that was, as one string.
            It is recorded here and never read by the comparison.
        formulas_fingerprint: The digest standing for the document's
            formulas with its data left out, or None where the document
            carries none -- one written before the member. Two documents
            agreeing on it changed no formula between them, whatever their
            ``graph_fingerprint`` says, which is the figure a reviewer quotes
            to say a quarter's movement was data alone. It takes no part in
            the comparison either: what moved is still read node by node.

    Examples:
        >>> from gaspatchio.frame.graph import ComparedDocument
        >>> ComparedDocument(
        ...     graph_fingerprint="sha256:aa",
        ...     document_digest="sha256:bb",
        ...     created_at="2026-01-01T00:00:00Z",
        ...     producer="gaspatchio 1.0.0",
        ... ).to_dict()["document_digest"]
        'sha256:bb'

    """

    graph_fingerprint: str | None
    document_digest: str | None
    created_at: str | None
    producer: str | None
    formulas_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the document's identity and seal, and its description beside them."""
        return {
            "graph_fingerprint": self.graph_fingerprint,
            "document_digest": self.document_digest,
            "created_at": self.created_at,
            "producer": self.producer,
            "formulas_fingerprint": self.formulas_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ModuleMoved:
    """One helper module whose bytes moved between the two runs.

    A helper the model imports is as much the model as the model file is, and
    an edit to it -- a comment as well as a constant -- moves its
    ``model.modules`` fingerprint. Where the edit moves a calculation, the
    calculations say so; where it moves none, this is the one place a reviewer
    sees that the file they would open is not the one the earlier run read.

    Attributes:
        path: The module's path, as the two documents' ``model.modules`` list
            it.
        before: The earlier run's fingerprint of it; None where the earlier
            run did not list it or could not read it.
        after: The later run's; None in the same two cases.

    Examples:
        >>> from gaspatchio.frame.graph import ModuleMoved
        >>> ModuleMoved("helper.py", "sha256:aa", "sha256:bb").to_dict()["path"]
        'helper.py'

    """

    path: str
    before: str | None
    after: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return the module's line as plain JSON data."""
        return {"path": self.path, "before": self.before, "after": self.after}


@dataclass(frozen=True, slots=True)
class SourceChange:
    """The model's own files, where the two runs record different bytes for them.

    ``model.source_sha`` is a hash over the model file, so it moves with any
    edit to it -- a reformatted line and a comment as well as a formula -- and
    a change report states it **on its own line, beside the findings and never
    among them**: the fingerprints are what say whether a calculation moved,
    and this says the file a reader would open is not the file it was. It is
    the one signal a model edit the fingerprints could not see leaves behind,
    and before selection entered the record an in-force definition edited in
    the model file left nothing else.

    **The helper modules the model imports are read the same way.** Each
    ``model.modules`` entry whose fingerprint moved, or which only one run
    lists, is named in ``modules``, stated and never counted, so a helper
    edited in a way that moves no calculation is still seen. Where only a
    helper moved, ``before`` and ``after`` are the model file's one digest.

    Attributes:
        path: The model file the later run recorded, or the earlier one's.
        before: The earlier run's ``source_sha``; None where it records none
            and a helper module moved.
        after: The later run's, likewise.
        modules: Each helper module whose bytes moved, ordered by path; empty
            where none did, or where either run lists no modules.

    Examples:
        >>> from gaspatchio.frame.graph import SourceChange
        >>> SourceChange("model.py", "sha256:aa", "sha256:bb").to_dict()["path"]
        'model.py'

    """

    path: str | None
    before: str | None
    after: str | None
    modules: tuple[ModuleMoved, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the line as plain JSON data."""
        return {
            "path": self.path,
            "before": self.before,
            "after": self.after,
            "modules": [module.to_dict() for module in self.modules],
        }


@dataclass(frozen=True, slots=True)
class DiffReport:
    """Everything one comparison of two artifacts found.

    Attributes:
        report_version: The grammar this report is written in.
        fingerprint_algorithm: The byte grammar both artifacts' digests were
            taken under. Every claim below is a claim about digests of that
            grammar, and two artifacts that do not share one are refused
            rather than compared.
        compared: The two documents this report is about, the earlier one
            first. A report that has been filed has to say what it compared,
            because the caller who held the two files is not the committee
            who reads the report a quarter later. It is written for that
            reader and read by nothing: this field takes no part in the
            comparison, and every claim below would be the same claim if it
            were not here.
        calculations: What moved in the model, in the later artifact's own
            order -- which is the order the model was written in -- with
            whatever the earlier artifact held and the later one does not
            after it.
        data: What moved underneath the model, and the results file the run
            wrote where both runs named one.
        values: What the two runs' numbers did, line by line, where the two
            results files were read beside the audit files
            (:func:`~gaspatchio.frame.graph.diff_with_results`); None where
            they were not, which says nothing about the numbers either way.
        source: The model's own files, where the two runs record different
            ``model.source_sha`` values or a helper module in ``model.modules``
            moved; None where nothing did, or neither can be compared. Stated
            beside the findings, never counted as drift (:class:`SourceChange`).

    Examples:
        >>> from gaspatchio.frame.graph import (
        ...     DIFF_REPORT_VERSION,
        ...     FINGERPRINT_ALGORITHM,
        ...     ComparedDocument,
        ...     DiffReport,
        ... )
        >>> report = DiffReport(
        ...     report_version=DIFF_REPORT_VERSION,
        ...     fingerprint_algorithm=FINGERPRINT_ALGORITHM,
        ...     compared=(
        ...         ComparedDocument("sha256:aa", None, "2026-01-01T00:00:00Z", None),
        ...         ComparedDocument("sha256:aa", None, "2026-04-01T00:00:00Z", None),
        ...     ),
        ...     calculations=(),
        ...     data=(),
        ... )
        >>> report.drift
        False
        >>> [document.created_at for document in report.compared]
        ['2026-01-01T00:00:00Z', '2026-04-01T00:00:00Z']

    """

    report_version: str
    fingerprint_algorithm: str
    compared: tuple[ComparedDocument, ComparedDocument]
    calculations: tuple[Change, ...]
    data: tuple[DataChange, ...]
    values: ValuesReport | None = None
    source: SourceChange | None = None

    @property
    def drift(self) -> bool:
        """Whether anything this report covers moved, calculation or data.

        The question a valuation committee asks of two quarters is "did
        anything change since last quarter", and this is the one word that
        answers it. A formula somebody edited, a formula nobody touched
        whose inputs went, a basis re-sourced, a set of policies replaced:
        each of them is a number that cannot be what it was, and each of
        them makes this True.

        **The policy data is why the word is not "did the model move".** An
        assumption base and a column of values handed over each reach this
        through the calculations that read them -- a re-sourced basis and a
        re-injected column move the digests of everything below them -- but
        the model never reads a model point by name, so a run over a new set
        of them is one entry in ``data`` and no entry in ``calculations`` at
        all. A headline answering "no" over a replaced in-force file is a
        headline a reviewer learns to distrust, and a field nobody trusts is
        worse than no field.

        **A book that could not be compared counts too.** Where neither
        a book digest nor a pair of file stamps can say whether the two
        runs read the same policies, ``data`` carries an entry saying so and
        why, because "we could not tell" answered as "no" is the same
        distrusted headline.

        **So does a results file that moved.** Where both runs recorded the
        digest of the results file they wrote and the two differ, the numbers
        in it may not be what they were with nothing in the calculations to
        say so: a column written over in a way the frame cannot see moves the
        file and no digest. The entry names the file and not the numbers,
        because the file also records the library versions and platform that
        wrote it.

        **So does a value no definition accounts for**, where the two
        results files were read: a line whose definition held and whose
        numbers moved beyond section 11.1.12's band, which is what a column
        written around the frame's own account of it looks like.

        The split that matters is not lost, because it was never carried
        here: ``calculations`` is what moved in the model and ``data`` is
        what moved underneath it. A model-change review that wants the
        narrower question reads ``bool(report.calculations)``.

        Examples:
            A quarter's new business moves nothing in the model, and is
            still something moving:

            >>> from gaspatchio.frame.graph import (
            ...     DIFF_REPORT_VERSION,
            ...     FINGERPRINT_ALGORITHM,
            ...     ComparedDocument,
            ...     DataChange,
            ...     DiffReport,
            ... )
            >>> quarter = ComparedDocument("sha256:aa", None, None, None)
            >>> report = DiffReport(
            ...     report_version=DIFF_REPORT_VERSION,
            ...     fingerprint_algorithm=FINGERPRINT_ALGORITHM,
            ...     compared=(quarter, quarter),
            ...     calculations=(),
            ...     data=(
            ...         DataChange(
            ...             "model_points", "q2.parquet", "sha256:a", "sha256:b"
            ...         ),
            ...     ),
            ... )
            >>> report.drift
            True

            The model-only reading is the calculations themselves:

            >>> bool(report.calculations)
            False

        """
        return bool(
            self.calculations
            or self.data
            or (self.values is not None and self.values.drift)
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the report as plain JSON data, for a pipeline that stores it."""
        earlier, later = self.compared
        return {
            "report_version": self.report_version,
            "fingerprint_algorithm": self.fingerprint_algorithm,
            "compared": {"before": earlier.to_dict(), "after": later.to_dict()},
            "drift": self.drift,
            "calculations": [change.to_dict() for change in self.calculations],
            "data": [change.to_dict() for change in self.data],
            "values": None if self.values is None else self.values.to_dict(),
            "source": None if self.source is None else self.source.to_dict(),
        }


def diff_artifacts(before: dict[str, Any], after: dict[str, Any]) -> DiffReport:
    """Compare two artifacts of one model and report what moved.

    Args:
        before: The earlier artifact, parsed.
        after: The later artifact, parsed.

    Returns:
        A :class:`DiffReport`. Its ``drift`` is what a pipeline step checks;
        its ``calculations`` are what a model-change review reads; its
        ``data`` is what an assumptions review reads.

    Raises:
        ValueError: If the two artifacts state different
            ``fingerprint_algorithm`` values. Every claim this report makes
            is a comparison of digests, and there is no translation between
            two byte grammars -- a digest taken under one says nothing
            whatever about a digest taken under the other.

    Examples:
        Two exports of one untouched model differ in when they were written
        and in nothing the report is about:

        >>> import json
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.frame.graph import GraphExporter, diff_artifacts
        >>> def valuation(rate: float) -> dict:
        ...     af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
        ...     af.death_claims = af.sum_assured * rate
        ...     return json.loads(GraphExporter(af).export())
        >>> diff_artifacts(valuation(0.00123), valuation(0.00123)).drift
        False

        An edited factor is reported against the line that holds it:

        >>> report = diff_artifacts(valuation(0.00123), valuation(0.00456))
        >>> [(c.node, c.kind, c.change_origin) for c in report.calculations]
        [('death_claims@1', 'changed', 'self')]

    """
    algorithm = _one_grammar(before, after)
    data = _data_changes(before, after)
    # Kind and name together, because that pair is what identifies an entry
    # of the assumptions section -- the key the data reading itself pairs on.
    # A name alone identified one only while tables were the only kind that
    # carried a name.
    re_sourced: frozenset[tuple[DataKind, str]] = frozenset(
        (change.kind, change.name)
        for change in data
        if change.kind in _ASSUMPTION_KINDS
        and change.name is not None
        and change.before is not None
        and change.after is not None
    )
    return DiffReport(
        report_version=DIFF_REPORT_VERSION,
        fingerprint_algorithm=algorithm,
        compared=(_the_document(before), _the_document(after)),
        calculations=(
            *_calculation_changes(before, after, re_sourced=re_sourced),
            *_selection_changes(before, after),
        ),
        data=data,
        source=_source_change(before, after),
    )


def _selection_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> Iterator[Change]:
    """Classify every row-selecting step the two artifacts do not hold identically.

    **A change to which policies the model values is a change to the model**,
    so it is reported among the calculations, under the step's id. Steps pair
    by id, which is their position in the model's own order, as nodes pair by
    id: a step whose own digest moved was edited (``self`` -- the in-force
    definition changed); one whose own digest held while its fingerprint moved
    reads a column whose definition moved (``inherited``). A step only one
    artifact carries was added or removed. A step carries no column, so
    ``column`` is null on every one of these.
    """
    was = {
        str(step.get("id")): step
        for step in _entries(before, "selection")
        if isinstance(step, dict)
    }
    now = {
        str(step.get("id")): step
        for step in _entries(after, "selection")
        if isinstance(step, dict)
    }

    def change(step_id: str, kind: ChangeKind, origin: ChangeOrigin | None) -> Change:
        return Change(
            node=step_id,
            column=None,
            kind=kind,
            change_origin=origin,
            renamed_from=None,
            fingerprint_equal_to=None,
            values_equal_to=None,
        )

    for step_id, step in now.items():
        earlier = was.get(step_id)
        if earlier is None:
            yield change(step_id, "added", None)
        elif earlier.get("local_fingerprint") != step.get("local_fingerprint"):
            yield change(step_id, "changed", "self")
        elif earlier.get("fingerprint") != step.get("fingerprint"):
            yield change(step_id, "changed", "inherited")
    for step_id in was:
        if step_id not in now:
            yield change(step_id, "removed", None)


def _source_change(
    before: dict[str, Any], after: dict[str, Any]
) -> SourceChange | None:
    """Return the model's own files' movement: the model file and its helpers."""
    blocks = [artifact.get("model") for artifact in (before, after)]
    was, now = (
        _stated(block.get("source_sha")) if isinstance(block, dict) else None
        for block in blocks
    )
    file_moved = was is not None and now is not None and was != now
    modules = _modules_moved(*blocks)
    if not file_moved and not modules:
        return None
    paths = [
        _stated(block.get("source_path")) if isinstance(block, dict) else None
        for block in reversed(blocks)
    ]
    return SourceChange(
        path=next((p for p in paths if p), None),
        before=was,
        after=now,
        modules=modules,
    )


def _modules_moved(was: object, now: object) -> tuple[ModuleMoved, ...]:
    """Return each helper module whose fingerprint moved, or only one run lists.

    Read only where both runs list their modules: a document written before
    the member, or naming no model source, has nothing to compare. A module
    is paired by its place beside the model file, so a model copied to another
    directory of one repository pairs its helpers with the copy's; it is named
    by the later run's path, or the earlier one's where only that run lists it.
    """
    earlier, later = (_module_fingerprints(block) for block in (was, now))
    if earlier is None or later is None:
        return ()
    moved: list[ModuleMoved] = []
    for place in sorted(earlier.keys() | later.keys()):
        was_path, was_print = earlier.get(place, (None, None))
        now_path, now_print = later.get(place, (None, None))
        if was_path is not None and now_path is not None and was_print == now_print:
            continue
        moved.append(ModuleMoved(now_path or was_path or place, was_print, now_print))
    return tuple(moved)


def _module_fingerprints(
    block: object,
) -> dict[str, tuple[str | None, str | None]] | None:
    """Return a run's modules by their place beside the model file.

    Each is keyed by its path relative to the model file's directory where the
    run names the model file, else by its path, and holds its path as written
    and its fingerprint. None where the run lists no modules.
    """
    if not isinstance(block, dict) or not isinstance(block.get("modules"), list):
        return None
    source = _stated(block.get("source_path"))
    home = PurePosixPath(source).parent if source else None
    return {
        _beside(entry["path"], home): (entry["path"], _stated(entry.get("fingerprint")))
        for entry in block["modules"]
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }


def _beside(path: str, home: PurePosixPath | None) -> str:
    """Return a module's path relative to the model file's directory, lexically."""
    if home is None:
        return path
    parts = PurePosixPath(posixpath.normpath(path)).parts
    base = PurePosixPath(posixpath.normpath(str(home))).parts
    shared = 0
    while shared < min(len(parts), len(base)) and parts[shared] == base[shared]:
        shared += 1
    return "/".join(("..",) * (len(base) - shared) + parts[shared:])


def _one_grammar(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Return the byte grammar both artifacts were written under, or refuse.

    Raises:
        ValueError: If the two do not share one.

    """
    was = _text(before.get("fingerprint_algorithm"))
    now = _text(after.get("fingerprint_algorithm"))
    if was == now:
        return now
    msg = (
        f"Cannot compare an artifact whose digests were taken under {was!r} "
        f"with one taken under {now!r}. A fingerprint algorithm is the byte "
        "grammar every digest in a document was computed under, and there is "
        "no translation between two of them -- a digest under one says "
        "nothing whatever about a digest under the other, so every finding "
        "such a comparison produced would be noise. Re-derive the "
        "fingerprints of both models from their sources under one grammar, "
        "and compare the artifacts that produces."
    )
    raise ValueError(msg)


def _text(value: object) -> str:
    """Return a string field as itself, and anything else as the empty string."""
    return value if isinstance(value, str) else ""


def _stated(value: object) -> str | None:
    """Return a string field as itself, and one the document omitted as None."""
    return value if isinstance(value, str) else None


# --- which two documents this is about --------------------------------------


def _the_document(artifact: dict[str, Any]) -> ComparedDocument:
    """Return what the report will say about one of the two files it compared.

    The identity is the envelope's own ``graph_fingerprint`` and nothing
    else. Beside it goes the seal the document carried -- read as published,
    never recomputed here, because whether a document is the file its producer
    wrote is the validator's question and not this report's -- and then the
    description a reader recognises the document by: when it was written, and
    what wrote it, read off the document itself rather than off the machine
    the comparison happens to run on.
    """
    producer = artifact.get("producer")
    wrote_it = producer if isinstance(producer, dict) else {}
    tool = " ".join(
        part
        for part in (_stated(wrote_it.get("name")), _stated(wrote_it.get("version")))
        if part
    )
    return ComparedDocument(
        graph_fingerprint=_stated(artifact.get("graph_fingerprint")),
        document_digest=_stated(artifact.get(DOCUMENT_DIGEST_FIELD)),
        created_at=_stated(artifact.get("created_at")),
        producer=tool or None,
        formulas_fingerprint=_stated(artifact.get(_FORMULAS_FINGERPRINT)),
    )


# --- what moved underneath the model ----------------------------------------


def _data_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[DataChange, ...]:
    """Return every base, data set, injected column and results file that moved.

    Read in the order a reviewer asks about them: the assumption bases the
    model rests on, then the policy data it was run over, then the columns the
    frame arrived holding that nothing accounts for, then the columns of
    values it was handed at a line -- what went into the run -- and last the
    results file it wrote.
    """
    return (
        *_assumption_changes(before, after),
        *_model_point_changes(before, after),
        *_hole_changes(before, after),
        *_injection_changes(before, after),
        *_results_changes(before, after),
    )


def _assumption_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> Iterator[DataChange]:
    """Report the assumption entries whose digests moved between the two files.

    An entry is paired by its kind and its name, and a digest that moved under
    one pair is one entry saying so. That is a table's whole story: it keeps
    the name the model gave it across a re-sourcing.

    A schedule and a curve are named after their own contents, so a re-sourced
    one arrives under a different name and pairs with nothing -- one entry
    gone and another arrived, which is the honest reading of a model that no
    longer reads what it read. The two are still told apart by name, which is
    what lets a reader follow either back to the nodes that read it.

    An entry carrying no name at all is paired by nothing, and that path is
    kept because the subject here is two *files*: a document written before a
    producer named its value objects, or by one that names them differently,
    is a document this report still has to read.

    Those two readings meet where the files were written either side of a
    producer that began naming value objects: one document states no name and
    the later one states a name, under a digest neither of them moved. Read as
    two partitions that is a base gone and another arrived for a model nobody
    touched, on the first comparison after an upgrade -- so an entry of one
    kind holding one digest on both sides of the name partition is reconciled
    to the one entry it is before anything is reported. A re-sourcing moves
    the digest and is untouched by that: it reads gone and arrived exactly as
    it did, because the two digests were never the same digest.
    """
    was, now = _named_assumptions(before), _named_assumptions(after)
    anonymous, later = _unnamed_assumptions(before), _unnamed_assumptions(after)
    carried = _digests_named_on_only_one_side(was, now, anonymous, later)

    for key in sorted({*was, *now}):
        kind, name = key
        stood, stands = was.get(key), now.get(key)
        if stood is None and stands in carried.get(kind, frozenset()):
            continue
        if stands is None and stood in carried.get(kind, frozenset()):
            continue
        if stood != stands:
            yield DataChange(kind, name, stood, stands)

    for kind in sorted(anonymous.keys() | later.keys()):
        bridged = carried.get(kind, frozenset())
        held = anonymous.get(kind, frozenset()) - bridged
        holds = later.get(kind, frozenset()) - bridged
        for digest in sorted(held - holds):
            yield DataChange(kind, None, digest, None)
        for digest in sorted(holds - held):
            yield DataChange(kind, None, None, digest)


def _digests_named_on_only_one_side(
    was: dict[tuple[DataKind, str], str],
    now: dict[tuple[DataKind, str], str],
    anonymous: dict[DataKind, frozenset[str]],
    later: dict[DataKind, frozenset[str]],
) -> dict[DataKind, frozenset[str]]:
    """Return, by kind, the digests one file names and the other leaves unnamed.

    A digest of one kind sitting unnamed in one document and named in the
    other is one base that gained or lost a label between two producers, and
    the label is not the identity -- the digest beside it is. Reporting it as
    a base gone and another arrived would accuse a model that did not move.
    """
    was_named: dict[DataKind, set[str]] = defaultdict(set)
    now_named: dict[DataKind, set[str]] = defaultdict(set)
    for (kind, _), digest in was.items():
        was_named[kind].add(digest)
    for (kind, _), digest in now.items():
        now_named[kind].add(digest)
    return {
        kind: frozenset(
            (anonymous.get(kind, frozenset()) & now_named[kind])
            | (later.get(kind, frozenset()) & was_named[kind])
        )
        for kind in anonymous.keys() | later.keys()
    }


def _named_assumptions(artifact: dict[str, Any]) -> dict[tuple[DataKind, str], str]:
    """Return the digest of every named assumption entry, keyed by kind and name."""
    return {
        (entry["kind"], entry["name"]): entry["fingerprint"]
        for entry in _assumption_entries(artifact)
        if isinstance(entry.get("name"), str)
    }


def _unnamed_assumptions(artifact: dict[str, Any]) -> dict[DataKind, frozenset[str]]:
    """Return the digests of the entries carrying no name at all, by kind.

    A set per kind rather than a list, because the section is already a
    directory of distinct bases: one curve read from four formulas is one
    entry, and two entries of one kind differ in the only thing they have.

    Nothing this producer writes reaches here any more -- it names every
    entry -- and the reading stays because a change report's subject is two
    files rather than two runs of one producer, and a null name is a shape
    the format allows and stored documents carry.
    """
    found: dict[DataKind, set[str]] = defaultdict(set)
    for entry in _assumption_entries(artifact):
        if entry.get("name") is None:
            found[entry["kind"]].add(entry["fingerprint"])
    return {kind: frozenset(digests) for kind, digests in found.items()}


def _assumption_entries(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the assumption entries that state both a kind and a digest."""
    return [
        entry
        for entry in _entries(artifact, "assumptions")
        if isinstance(entry, dict) and "kind" in entry and "fingerprint" in entry
    ]


def _model_point_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> Iterator[DataChange]:
    """Report the policy data the two runs consumed, where it is not the same data.

    **The book's own digest decides, where both documents state one.** Every
    export records a content digest of the book it was built over, taken over
    the columns the model reads, so the answer comes from the data and needs
    no argument from the caller: a run over a replaced in-force file is a
    changed book, and the same data written out again by another Parquet
    writer, or revised only in a column no line of the model reads, is not.
    Where either document states no digest -- one written before the member
    existed, or one whose producer could not read its book -- the comparison
    falls back to the file each run said it read, on its fingerprint and
    never on its path: the same data read from a new location is the same
    policies, and a report that called that a change would be reporting on
    somebody's filesystem.

    **Where neither can decide, the report says so.** A document with no
    book digest, compared with one where the two runs did not both name a
    file, leaves nothing to say whether the policies are the same. Reporting
    nothing there would read as "nothing moved", which is the answer the book
    member exists to stop a report giving by default; the entry is written
    with both sides' digests where they have one and a ``reason`` naming what
    each document said about its book, and it is drift.

    The path the run recorded is carried as the entry's name where there is
    one, because it is what a reader recognises the data by.
    """
    name = _model_points(after)[0] or _model_points(before)[0]
    was_book = _book_digest(before)
    now_book = _book_digest(after)
    if was_book is not None and now_book is not None:
        if was_book != now_book:
            yield DataChange("model_points", name, was_book, now_book)
        return
    was_file = _model_points(before)[1]
    now_file = _model_points(after)[1]
    if was_file is not None and now_file is not None:
        if was_file != now_file:
            yield DataChange("model_points", name, was_file, now_file)
        return
    yield DataChange(
        "model_points",
        name,
        was_book or was_file,
        now_book or now_file,
        reason=_why_the_books_were_not_compared(before, after),
    )


def _book_digest(artifact: dict[str, Any]) -> str | None:
    """Return the content digest of the book the document was built over, or None."""
    book = artifact.get("book")
    digest = book.get("digest") if isinstance(book, dict) else None
    return digest if isinstance(digest, str) else None


def _why_the_books_were_not_compared(
    before: dict[str, Any], after: dict[str, Any]
) -> str:
    """Return the sentence an uncompared book's entry carries.

    It names what each document said about its book, in the document's own
    words where it gave any -- the ``detail`` of its ``unavailable`` form --
    and which of the two runs named no file to fall back on, because those
    are the two things a reader has to fix to get an answer.
    """
    accounts = {
        side: account
        for side, artifact in (("earlier", before), ("later", after))
        if (account := _no_digest_because(artifact)) is not None
    }
    if len(accounts) == len(_SIDES) and len(set(accounts.values())) == 1:
        said = f"neither document states a digest of its book ({accounts['later']})"
    else:
        said = " and ".join(
            f"the {side} document {_WITH_NO_DIGEST} ({account})"
            for side, account in accounts.items()
        )
    unnamed = [
        side
        for side, artifact in (("earlier", before), ("later", after))
        if _model_points(artifact)[1] is None
    ]
    files = (
        "neither run named a file for its policy data"
        if len(unnamed) == len(_SIDES)
        else f"the {unnamed[0]} run named no file for its policy data"
    )
    return (
        f"The two books could not be compared: {said}, and {files} to compare "
        "instead. To compare them, export each model from the frame built over "
        "its book, with every column the model reads in a type the format "
        "names, or name each run's file with "
        'ModelIdentity.of("model.py", model_points="points.parquet"), passed '
        "to the export as GraphExportConfig(model=...)."
    )


def _no_digest_because(artifact: dict[str, Any]) -> str | None:
    """Return what one document said about a book it states no digest of, or None."""
    book = artifact.get("book")
    if not isinstance(book, dict):
        return "it records no book, having been written before documents did"
    digest = book.get("digest")
    if isinstance(digest, str):
        return None
    detail = digest.get("detail") if isinstance(digest, dict) else None
    if not isinstance(detail, str) or not detail:
        return "it gave no reason"
    # Carried inside a sentence, so the document's own full stop goes.
    return detail.removesuffix(".")


def _model_points(artifact: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return where the run read its policy data, and the digest it published."""
    model = artifact.get("model")
    points = model.get("model_points") if isinstance(model, dict) else None
    if not isinstance(points, dict):
        return (None, None)
    return (points.get("path"), points.get("fingerprint"))


def _hole_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> Iterator[DataChange]:
    """Report every hole both documents list whose stamp of what it held moved.

    A hole the frame arrived holding -- a column the setup joined from a file
    in plain Polars, say -- carries ``content``, the content hash of the
    column as it arrived, and section 12.4 folds that stamp into
    ``graph_fingerprint`` beside the hole's name. The hole's node carries no
    stamp, so an edit to the file moves the envelope's figure and no node
    digest at all: read node by node, two such documents moved nothing, which
    is the one answer a report over two different figures must not give. So a
    hole held by both documents under one name is compared on its stamp, and
    a stamp that moved is data that changed: ``before`` and ``after`` are the
    two stamps, the name the hole's column.

    Where one document stamps the hole and the other does not -- one written
    before holes carried a stamp, or a hole whose values one producer could
    not read -- the two cannot be compared, and the entry says so in its
    ``reason`` and counts as drift, as a book that could not be compared
    does. A hole only one document lists is a node only one of them holds,
    and the calculations already report it.
    """
    was, now = _hole_stamps(before), _hole_stamps(after)
    for column in sorted(was.keys() & now.keys()):
        (stood, stood_for), (stands, stands_for) = was[column], now[column]
        if stood == stands:
            continue
        reason = None
        if stood is None or stands is None:
            side, why = (
                (_SIDES[0], stood_for) if stood is None else (_SIDES[1], stands_for)
            )
            reason = (
                f"The hole {column} could not be compared: the {side} document "
                f"records no stamp of what the column held ({_why_unstamped(why)}), "
                "so nothing says whether it held the same values. A hole the "
                "frame arrived holding is stamped by a producer that read it; "
                "export both runs from one that does to compare them."
            )
        yield DataChange("hole", column, stood, stands, reason=reason)


def _why_unstamped(reason: str | None) -> str:
    """Return why a hole carries no stamp, from the reason its entry gives."""
    if reason == "overwritten":
        return "its hole is an overwritten definition, which holds no arriving values"
    return (
        "it was written before holes carried one, or its producer could not "
        "read the values"
    )


def _hole_stamps(
    artifact: dict[str, Any],
) -> dict[str, tuple[str | None, str | None]]:
    """Return each hole's column, with its stamp and its reason, or None for either."""
    return {
        entry["column"]: (_stated(entry.get("content")), _stated(entry.get("reason")))
        for entry in _entries(artifact, "holes")
        if isinstance(entry, dict) and isinstance(entry.get("column"), str)
    }


def _injection_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> Iterator[DataChange]:
    """Report every column of values whose contents moved between the two files.

    The digest reported is the node's own ``local_fingerprint``, because the
    artifact carries no field holding the injection's content stamp on its
    own. That fingerprint is taken over exactly the stamp and the container
    the values arrived in and nothing else, so two of them differ exactly when
    the data did.
    """
    was = _injections(before)
    now = _injections(after)
    for node_id in sorted(was.keys() & now.keys()):
        column, digest = now[node_id]
        if was[node_id][1] != digest:
            yield DataChange("injection", column, was[node_id][1], digest)


def _injections(artifact: dict[str, Any]) -> dict[str, tuple[str | None, str | None]]:
    """Return each injected column's own name and digest, keyed by node id."""
    return {
        node["id"]: (node.get("column"), node.get("local_fingerprint"))
        for node in _nodes(artifact)
        if node.get("provenance") in _HANDED_OVER
    }


def _results_changes(
    before: dict[str, Any], after: dict[str, Any]
) -> Iterator[DataChange]:
    """Report the results file the two runs wrote, where both named one and they differ.

    **Only where both documents record a results file's digest.** A run
    exported without one makes no claim about its results, so there is
    nothing to hold the other side against, and an entry there would be a
    finding invented from an absence. Where both do, the two digests are the
    whole comparison: the same bytes under a new path are the same file.

    The entry is named by the path the later run recorded, else the earlier
    one's, because that is the name a reader finds the file under. What the
    digest is evidence of, and what it is not, is in this module's own account
    of the results file.
    """
    was_path, was_file = results_file_recorded(before)
    now_path, now_file = results_file_recorded(after)
    if was_file is None or now_file is None or was_file == now_file:
        return
    name = now_path if now_path is not None else was_path
    yield DataChange("results", name, was_file, now_file)


def results_file_recorded(
    artifact: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Return where a run's results file was written, and its digest, or two Nones.

    A block stating no digest records no file a comparison could read, so it
    is read as no file at all.
    """
    model = artifact.get("model")
    results = model.get("results") if isinstance(model, dict) else None
    if not isinstance(results, dict):
        return (None, None)
    digest = _stated(results.get("fingerprint"))
    if digest is None:
        return (None, None)
    return (_stated(results.get("path")), digest)


def _results_not_compared(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    """Return the sentence saying the results files were not compared, or None.

    Written where one document records a results file's digest and the other
    does not: a reader holding one audit file that records its results
    expects them to be compared, and a silence would read as "the same". It
    names the run that recorded none -- which may still have named a path, so
    it speaks of the checksum rather than the file -- and the step that says
    whether the two results agree, for a reader who holds a results file from
    each run. Where both record one, the report's own entry says what there is
    to say. Where neither does, there is nothing to say: most exports record
    no results file, and a line over every such comparison would be a line a
    reviewer learns to skip.

    ``gspio diff`` prints this under its report, and the comparison page
    writes the same sentence; neither is part of the report, which carries no
    entry here.
    """
    was = results_file_recorded(before)[1] is not None
    now = results_file_recorded(after)[1] is not None
    if was == now:
        return None
    unrecorded = _SIDES[1] if was else _SIDES[0]
    opening = (
        f"The results files were not compared: the {unrecorded} run recorded no "
        "checksum of a results file."
    )
    if not _one_calculation(before, after):
        return (
            f"{opening} The two runs are of different calculations -- their "
            "graph fingerprints differ. If a results file from each run is to "
            "hand, gspio diff on the two audit files with --results and the two "
            "files, earlier first, says which numbers moved and by how much."
        )
    if not _one_book(before, after):
        return (
            f"{opening} The two runs are over different books. If a results "
            "file from each run is to hand, gspio diff on the two audit files "
            "with --results and the two files, earlier first, pairs the two "
            "books' policies and says how far each line moved."
        )
    return (
        f"{opening} If a results file from each run is to hand, "
        "run gspio compare on the later audit file and both of them to see whether "
        "the two results agree."
    )


def _results_file_moved(
    before: dict[str, Any], after: dict[str, Any], *, read: bool = False
) -> str:
    """Return the sentence ``gspio diff`` prints under a results entry.

    The next step that works for these two runs, and never one that refuses
    them. Where the two files were read and measured, the values below the
    entry are that step, and the sentence says so. Otherwise: where the
    calculation or the book moved, the step is this command again with the
    two results files named, which pairs the two books' policies and
    measures what moved; where neither moved, only the writer can have, and
    gspio compare says whether the two results agree -- the sentence the
    comparison page also writes.
    """
    if read:
        return _RESULTS_READ
    if not _one_calculation(before, after):
        return _RESULTS_OF_TWO_CALCULATIONS
    if not _one_book(before, after):
        return _RESULTS_OVER_TWO_BOOKS
    return _RESULTS_FILE_MOVED


# How each key of ``producer.versions`` is said on the library line, in the
# mapping's own order. The sha is named and never printed: two 64-digit
# strings on one line say less than "differs".
_LIBRARY_WORDS: Final[dict[str, str]] = {
    "core_version": "core",
    "extension_version": "extension",
    "polars_version": "polars",
    "python_version": "python",
    "platform": "platform",
}
_EXTENSION_SHA: Final[str] = "extension_sha256"


def _library_moved(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    """Return the line ``gspio diff`` prints where the library moved, or None.

    Context and never a finding: it is no ``data`` entry and moves no exit
    status. A model with one ``graph_fingerprint`` on a new library has not
    drifted -- every calculation is what it was -- and that is exactly the
    case to run ``gspio compare`` on, since only the numbers can say whether
    the library moved them. None where either document records no versions,
    or records them as withheld, and where the two state the same library.
    What the model imports from outside itself is named by distribution.
    """
    was, now = _library_of(before), _library_of(after)
    if was is None or now is None:
        return None
    moved = [
        f"{word} {was.get(key, '-')} → {now.get(key, '-')}"
        for key, word in _LIBRARY_WORDS.items()
        if was.get(key) != now.get(key)
    ]
    if was.get(_EXTENSION_SHA) != now.get(_EXTENSION_SHA):
        moved.append("extension sha differs")
    was_imports, now_imports = _imports_of(was), _imports_of(now)
    moved.extend(
        f"{name} {was_imports.get(name, '-')} → {now_imports.get(name, '-')}"
        for name in sorted(set(was_imports) | set(now_imports))
        if was_imports.get(name) != now_imports.get(name)
    )
    return f"library: {'; '.join(moved)}" if moved else None


def _formulas_said(report: DiffReport) -> str | None:
    """Return the line saying whether any formula moved, from the two figures.

    Read off the two documents' ``formulas_fingerprint`` alone, so the line
    is the comparison of two quotable figures rather than a summary of the
    node-by-node reading below it. Where the two agree, no formula changed
    between them, and the line names the data entries that moved instead;
    where they differ, a formula did. None where either document carries no
    such figure -- one written before the member -- because a line inferred
    from the node changes would be the ambiguous reading the figure exists
    to replace.

    Args:
        report: The comparison of the two documents.

    Returns:
        The line, or None where there is no figure on one side to compare.

    Examples:
        >>> from gaspatchio.frame.graph import (
        ...     DIFF_REPORT_VERSION,
        ...     FINGERPRINT_ALGORITHM,
        ...     ComparedDocument,
        ...     DataChange,
        ...     DiffReport,
        ... )
        >>> from gaspatchio.frame.graph.diff import _formulas_said
        >>> def side(graph: str, formulas: str | None) -> ComparedDocument:
        ...     return ComparedDocument(graph, None, None, None, formulas)
        >>> report = DiffReport(
        ...     report_version=DIFF_REPORT_VERSION,
        ...     fingerprint_algorithm=FINGERPRINT_ALGORITHM,
        ...     compared=(
        ...         side("sha256:aa", "sha256:ff"),
        ...         side("sha256:bb", "sha256:ff"),
        ...     ),
        ...     calculations=(),
        ...     data=(DataChange("table", "mortality", "sha256:1", "sha256:2"),),
        ... )
        >>> _formulas_said(report)
        'formulas unchanged (formulas_fingerprint equal); data changed: table mortality'

    """
    earlier, later = report.compared
    was, now = earlier.formulas_fingerprint, later.formulas_fingerprint
    if was is None or now is None:
        return None
    if was != now:
        return "formulas changed (formulas_fingerprint differs)"
    moved = [
        f"{_DATA_WORDS.get(change.kind, change.kind)} {change.name or '(unnamed)'}"
        for change in report.data
    ]
    said = "formulas unchanged (formulas_fingerprint equal)"
    return f"{said}; data changed: {', '.join(moved)}" if moved else said


def _library_of(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Return the versions a document records produced it, or None where none are."""
    producer = artifact.get("producer")
    stated = producer.get("versions") if isinstance(producer, dict) else None
    if not isinstance(stated, dict) or "omitted" in stated:
        return None
    return stated


def _imports_of(versions: Mapping[str, Any]) -> dict[str, str]:
    """Return the installed distributions a version mapping says the model imports."""
    imported = versions.get("imports")
    if not isinstance(imported, dict):
        return {}
    return {str(name): str(value) for name, value in imported.items()}


def _one_calculation(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Return whether two documents state one graph fingerprint, or cannot tell.

    The fingerprint gspio compare binds a results file to. A document stating
    none says nothing either way, and the sentence it gets is the one it got
    before this distinction existed.
    """
    was = _stated(before.get("graph_fingerprint"))
    now = _stated(after.get("graph_fingerprint"))
    return was is None or now is None or was == now


def _one_book(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Return whether two documents state one book digest, or cannot tell."""
    was, now = _book_digest(before), _book_digest(after)
    return was is None or now is None or was == now


# --- what moved in the model ------------------------------------------------


def _calculation_changes(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    re_sourced: frozenset[tuple[DataKind, str]],
) -> Iterator[Change]:
    """Classify every node the two artifacts do not hold identically.

    Args:
        before: The earlier artifact.
        after: The later artifact.
        re_sourced: The kind and name of each assumption entry both files
            carry under different digests -- what the data reading found,
            handed over so that the two readings cannot disagree about it.

    Yields:
        One change per node that moved, arrived, went, or carries a name that
        moved. The later artifact's own order first, then whatever the
        earlier one held and this one does not.

    """
    was = _by_id(before)
    now = _by_id(after)

    arrived = [node_id for node_id in now if node_id not in was]
    gone = [node_id for node_id in was if node_id not in now]
    hints = _fingerprint_hints(was, now, gone=gone, arrived=arrived)

    for node_id, node in now.items():
        if node_id in was:
            change = _movement(was[node_id], node, re_sourced=re_sourced)
            if change is not None:
                yield change
            continue
        source = _identity_source(node)
        if source is not None and source in was:
            yield Change(
                node=node_id,
                column=node.get("column"),
                kind="renamed",
                change_origin=None,
                renamed_from=source,
                fingerprint_equal_to=None,
                values_equal_to=None,
            )
            continue
        same_calculation, same_values = _labelled(
            hints.get(node_id), arrived=node, departed=was
        )
        yield Change(
            node=node_id,
            column=node.get("column"),
            kind="added",
            change_origin=None,
            renamed_from=None,
            fingerprint_equal_to=same_calculation,
            values_equal_to=same_values,
        )

    for node_id in gone:
        yield Change(
            node=node_id,
            column=was[node_id].get("column"),
            kind="removed",
            change_origin=None,
            renamed_from=None,
            fingerprint_equal_to=None,
            values_equal_to=None,
        )


def _labelled(
    paired: str | None,
    *,
    arrived: dict[str, Any],
    departed: Mapping[str, dict[str, Any]],
) -> tuple[NodeId | None, NodeId | None]:
    """Return one pairing under the label its evidence carries, and None for the other.

    The pairing itself is decided in :func:`_fingerprint_hints` and is not
    touched here: what this settles is which of the two fields it is written
    into. Where either end is a column of values handed over at a line, the
    digest the two share was taken over the numbers themselves rather than
    over a calculation, so the pairing is evidence that the same values
    arrived twice and no evidence at all of a calculation under a new name.
    """
    if paired is None:
        return None, None
    ends = (arrived.get("provenance"), departed[paired].get("provenance"))
    if _HANDED_OVER & set(ends):
        return None, paired
    return paired, None


def _movement(
    was: dict[str, Any],
    now: dict[str, Any],
    *,
    re_sourced: frozenset[tuple[DataKind, str]],
) -> Change | None:
    """Return how one node both files hold moved, or None where it did not.

    The local digest moving is the node's own account of itself moving, and
    the Merkle digest moving on its own is its answer moving under an
    untouched formula. The third case is the local digest moving because a
    base the node looks up was re-sourced -- see this module's own account of
    why that is not an edit, and of the two things it cannot separate.
    """
    local_moved = was.get("local_fingerprint") != now.get("local_fingerprint")
    merkle_moved = was.get("fingerprint") != now.get("fingerprint")
    if not local_moved and not merkle_moved:
        return None
    inherited = not local_moved or _the_data_accounts_for_it(
        was, now, re_sourced=re_sourced
    )
    return Change(
        node=now["id"],
        column=now.get("column"),
        kind="changed",
        change_origin="inherited" if inherited else "self",
        renamed_from=None,
        fingerprint_equal_to=None,
        values_equal_to=None,
    )


def _the_data_accounts_for_it(
    was: dict[str, Any],
    now: dict[str, Any],
    *,
    re_sourced: frozenset[tuple[DataKind, str]],
) -> bool:
    """Whether a node's own digest moved because the data under it moved.

    Two shapes qualify. A column of values handed over at a line has no
    formula at all -- its identity is its contents -- so nothing else can have
    moved. A computed node qualifies where it is the calculation it was, in
    the text it was written in, reading what it read, and one of the bases it
    names has been re-sourced.

    The join back from the node is by name alone, because a name is all a
    node states: ``reads_assumptions`` names entries and says nothing about
    their kinds. That is unambiguous while each kind's names are its own -- a
    table states the name the model gave it, and the other two state their
    kind and their own digest -- and a document putting two kinds under one
    name would have this reading match on either.
    """
    handed_over = (was.get("provenance"), now.get("provenance"))
    if set(handed_over) <= _HANDED_OVER:
        return True
    names = now.get("reads_assumptions") or []
    if names != (was.get("reads_assumptions") or []):
        return False
    if not set(names) & {name for _, name in re_sourced}:
        return False
    unedited = was.get("formula") == now.get("formula")
    return unedited and was.get("reads") == now.get("reads")


def _identity_source(node: dict[str, Any]) -> NodeId | None:
    """Return the node a name moved from, where the framework recorded the move.

    The frame writes a record of its own for a rename: a node whose whole
    account of itself is that it carries another column's value under a new
    name. That record is the only evidence this report accepts, and it is
    what keeps a reviewer from being told a reserve was thrown away and an
    identical one invented in the same quarter.

    A column renamed in the model's source text carries no such record and is
    not recognised here -- nor is a plain copy, which does not retire the
    column it reads and so is not a name-move at all. Both reach the report
    through :func:`_fingerprint_hints` instead, as evidence rather than as a
    finding.
    """
    if node.get("provenance") != _RENAME:
        return None
    reads = node.get("reads") or []
    if len(reads) != _ONE_COLUMN:
        return None
    source: NodeId = reads[0]
    return source


def _fingerprint_hints(
    was: Mapping[str, dict[str, Any]],
    now: Mapping[str, dict[str, Any]],
    *,
    gone: Sequence[str],
    arrived: Sequence[str],
) -> dict[str, str]:
    """Return, per arrived node, the departed node it shares a fingerprint with.

    Only where exactly one of each shares that fingerprint. Two columns
    computed the same way share one by design, so a fingerprint standing for
    more than one node on either side is evidence of nothing and the hint is
    withheld rather than guessed at.
    """
    departed: dict[str, list[str]] = defaultdict(list)
    for node_id in gone:
        departed[_text(was[node_id].get("fingerprint"))].append(node_id)
    minted: dict[str, list[str]] = defaultdict(list)
    for node_id in arrived:
        minted[_text(now[node_id].get("fingerprint"))].append(node_id)
    return {
        new[0]: departed[digest][0]
        for digest, new in minted.items()
        if len(new) == _UNIQUE and len(departed.get(digest, ())) == _UNIQUE
    }


# --- reading the two documents ----------------------------------------------


def _by_id(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the artifact's nodes keyed by id, in the order the file holds them."""
    return {node["id"]: node for node in _nodes(artifact) if "id" in node}


def _nodes(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the artifact's node records, and nothing that is not one."""
    return [node for node in _entries(artifact, "nodes") if isinstance(node, dict)]


def _entries(artifact: dict[str, Any], section: str) -> list[Any]:
    """Return one array section of an artifact, empty where it carries none."""
    found = artifact.get(section)
    return found if isinstance(found, list) else []
