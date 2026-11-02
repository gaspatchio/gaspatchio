# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Whether the files in hand are the ones an audit file records.

A model reviewer holding an audit file and a folder of results asks one
question before any other: is this file of results the one the model in
front of me produced? The audit file already holds the evidence -- a seal
over itself, the sha256 of the results file the run wrote, a digest of the
policy data, the sha256 of the model source and of every local module it
imports, the commit it sat at, and the content hash of every assumption table
it read -- and :func:`verify_artifact` is what reads it back, holding each
file the reviewer names against the member that records it.

Each check is one line with one of four outcomes:

- ``agree``: the file in hand is what the audit file records;
- ``disagree``: it is not, and the detail names both values;
- ``indeterminate``: a check that decides was asked for and could not be made,
  because nothing was recorded to check against -- an audit file naming no
  results file cannot vouch for one;
- ``not_asked``: the input the check needs was not given, or the condition
  a check that adds evidence rests on does not hold.

**Some checks decide, and three add evidence.** The seal, the results file's
sha256, the model source's sha256, each local module's and each assumption
table's fingerprint answer the question for the input they read, and one that
cannot be made leaves the question open. So does the holes section, read off
the document, wherever a model, its policy data or its assumption files are
given: a column the record cannot account for reached it by name only, so
whatever made its values is on no line, and agreement over the files given
would say more than was checked. The policy
data is decided as a comparison of two audit files decides it (section
14.2): by its book digest where the audit file states one, so the same
policies in another file are the same book, and by the file's own stamp
only where it states none. A results file's own manifest and the checkout's
revision sit beside those. Where their condition holds -- the file carries a
manifest, the audit file records a revision and the model sits in a
checkout -- they agree or disagree like any other check; where it does not,
they have nothing to add and are not asked. A revision the audit file says
git could not state is ``indeterminate``, naming why, and holds nothing open.

**The library versions are stated, and decide nothing.** The ``versions``
line holds what the audit file records produced its values against what this
process runs -- and, beside a results file whose manifest Polars wrote,
against what that manifest states, since one run states one set. It tells a
reviewer whether re-running here would use the same library; whatever it
finds, it moves no exit status, because the results file's sha256 and the
model's source_sha already decide whether these are the files.

**And the model is decided by the graph its files rebuild.** A stamp says
whether a file moved, not whether the numbers did: a value the model reads
from a parameter file, a config, an environment variable or a module outside
its folder moves a formula while every stamp agrees. So where a model file is
given, the ``graph`` line imports it and runs it over the policy data given
-- through the scenario plan given, for a plan's record -- in a fresh
interpreter, uncollected, and holds the graph's fingerprint against
``graph_fingerprint``, naming each line whose own calculation moved
(:mod:`._rebuilt_graph`). That line runs the model's own code, so it holds in
this environment, and it is the one check here that does.

**Paths are always explicit.** The audit file records where each file sat
when it was written, and a check prints that path for context. It never
opens it: a reviewer names each file they hold, and a check that went
looking for a recorded path would be checking whatever sits there now. Two
checks find files from what was named rather than taking each file named: a
local module is the file beside the model file given, which is where running
that model would import it from, and an assumption table is sought among the
files and directories given, by the file its entry records it was read from
or by its own name.

**A table is checked by its content, as it was stamped.** A file found for a
table is read through the keys and the answer column the entry's payload
states, by the steps ``Table`` takes, to the fingerprint
``Table.fingerprint()`` gives -- so a file re-saved in another format, or with
its columns in another order, still agrees, and a moved rate does not. A
difference decides only where the record names the file the table was a plain
read of. A table whose recipe reshaped what it read -- renamed, cast, melted,
set or computed columns, or a shock -- is never read back from a file at all,
and one the model handed a frame rather than a file's path agrees with a file
or leaves the question open: a filter in code and an edit to the file read
alike. Where no file is named for a frame-built table it is not asked.

Nothing here is a second implementation of a check the framework already
makes. The seal is the reading ``validate_artifact(deep=True)`` gives, the
policy data is held to the book by the digest reading
``validate_artifact(book=)`` makes, a results file's manifest is parsed by
``ResultManifest.from_metadata`` as ``read_manifest`` parses it -- with each
member checked first, so a damaged manifest is named rather than refused --
every file is hashed by the function that stamped it into the audit file, and
a table file is fingerprinted by the steps a table's own construction takes.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, fields
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Final, Literal

import polars as pl

from gaspatchio._beside import loads_by_path
from gaspatchio._identity import content_sha_of
from gaspatchio.engines._versions import versions_in_this_process
from gaspatchio.engines.compare import Verdict
from gaspatchio.engines.protocol import (
    _METADATA_PREFIX,
    ResultManifest,
    _identity_read,
    _member_damage,
)
from gaspatchio.schemas import SCHEMA_IDENTIFIERS

from ._model_files import book_from_file, file_sha, git_output
from ._rebuilt_graph import rebuilt_decision
from .artifact import DOCUMENT_DIGEST_FIELD, book_columns
from .validate import (
    Finding,
    _book_digest_findings,
    _compilation_findings,
    _document,
    _document_seal_findings,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = [
    "VERIFICATION_REPORT_VERSION",
    "Check",
    "CheckOutcome",
    "VerificationReport",
    "verify_artifact",
]

# What one check came to: compare's three verdicts, which carry the same exit
# statuses on both commands, and one more for a check that was not asked. A
# check nobody asked for moves nothing, so the report's verdict is only ever
# one of compare's three -- an audit file verified with nothing beside it is
# one whose seal agrees, or does not.
CheckOutcome = Literal[Verdict, "not_asked"]

# The report's own identifier, read the way the validation and comparison
# reports' are: a key naming the grammar the stored report is written in.
VERIFICATION_REPORT_VERSION: Final[str] = "gaspatchio-graph-verification/v0-preview.1"

# The checks, named for the member each holds its input against, and the
# member written out as a path into the document. ``assumptions`` is written
# once for each table the audit file records, each held against its own entry.
_SEAL: Final[str] = "seal"
_RESULTS: Final[str] = "results"
_MANIFEST: Final[str] = "results_manifest"
_BOOK_CHECK: Final[str] = "book"
_MODEL_POINTS: Final[str] = "model_points"
_SOURCE: Final[str] = "source_sha"
_MODULES: Final[str] = "modules"
_HOLES: Final[str] = "holes"
_REBUILT: Final[str] = "graph"
_PLAN: Final[str] = "scenarios"
_REVISION: Final[str] = "git"
_VERSIONS: Final[str] = "versions"
_TABLES: Final[str] = "assumptions"

# The checks that add evidence rather than decide: each disagrees where what
# it compares differs, and none holds the verdict open where it could not
# compare. ``versions`` goes further and moves the verdict not at all -- a
# library that moved is the reason to run ``compare``, not a file that is not
# the one recorded.
_ADDS_EVIDENCE: Final[frozenset[str]] = frozenset({_MANIFEST, _REVISION, _VERSIONS})
_MOVES_NOTHING: Final[frozenset[str]] = frozenset({_VERSIONS})

_AGAINST: Final[dict[str, str]] = {
    _SEAL: DOCUMENT_DIGEST_FIELD,
    _RESULTS: "model.results.fingerprint",
    _MANIFEST: "graph_fingerprint, book.digest",
    _BOOK_CHECK: "book.digest",
    _MODEL_POINTS: "model.model_points.fingerprint",
    _SOURCE: "model.source_sha",
    _MODULES: "model.modules",
    _REBUILT: "graph_fingerprint",
    _PLAN: "model.scenarios",
    _HOLES: "holes",
    _REVISION: "model.git.commit",
    _VERSIONS: "producer.versions",
    _TABLES: "assumptions",
}


@dataclass(frozen=True, slots=True)
class Check:
    """One file held against one member of an audit file, and what came of it.

    Attributes:
        name: Which check this is, named for the member it reads:
            ``seal``, ``results``, ``results_manifest``, ``book``,
            ``model_points``, ``source_sha``, ``modules``, ``scenarios``,
            ``graph``, ``holes``, ``git``, ``versions`` or ``assumptions`` --
            the last once per
            table the audit file records, its ``against`` naming the entry.
        against: The member of the audit file the input is held against,
            written as a path into the document.
        outcome: ``agree``, ``disagree``, ``indeterminate`` or ``not_asked``.
            A check that adds evidence is ``not_asked`` where it has nothing
            to add, and the one it is ever ``indeterminate`` on is ``git``,
            where the audit file says git could not state the revision --
            which holds nothing open, since that check does not decide.
        detail: What was compared, with both values where they differ, or
            why the check was not made.

    Examples:
        >>> from gaspatchio.frame.graph import Check
        >>> check = Check(
        ...     name="source_sha",
        ...     against="model.source_sha",
        ...     outcome="agree",
        ...     detail="model.py is the source the audit file records.",
        ... )
        >>> check.to_dict()["outcome"]
        'agree'

    """

    name: str
    against: str
    outcome: CheckOutcome
    detail: str

    def to_dict(self) -> dict[str, str]:
        """Return the check as four strings, for a report written to a file."""
        return {
            "name": self.name,
            "against": self.against,
            "outcome": self.outcome,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """Every check one verification made, and what they come to together.

    Attributes:
        report_version: The grammar this report is written in.
        graph_fingerprint: The model the audit file is an account of, as the
            file states it, so a stored report says which model it verified.
        document_digest: The audit file's seal as the file states it, or
            None where it carries none.
        checks: One per check, in one fixed order, the ones not asked
            included -- so "nothing was found" and "nothing was asked" are
            never one answer.

    Examples:
        >>> from gaspatchio.frame.graph import (
        ...     VERIFICATION_REPORT_VERSION,
        ...     Check,
        ...     VerificationReport,
        ... )
        >>> VerificationReport(
        ...     report_version=VERIFICATION_REPORT_VERSION,
        ...     graph_fingerprint=None,
        ...     document_digest=None,
        ...     checks=(Check("results", "model.results.fingerprint", "disagree", ""),),
        ... ).verdict
        'disagree'

    """

    report_version: str
    graph_fingerprint: str | None
    document_digest: str | None
    checks: tuple[Check, ...]

    @property
    def verdict(self) -> Verdict:
        """What the checks come to, ``disagree`` first and ``agree`` last.

        One check that differs is the answer, whatever else agrees: the file
        in hand is not the one the audit file records. Short of that, a check
        that decides and could not be made leaves the question open, which is
        not agreement. A check not asked moves nothing, and nor does a check
        that adds evidence and could not compare. The ``versions`` line moves
        nothing whatever it says: a library that moved is stated, and the
        files are decided by the checks that read them.
        """
        moving = [one for one in self.checks if one.name not in _MOVES_NOTHING]
        if any(one.outcome == "disagree" for one in moving):
            return "disagree"
        if any(
            one.outcome == "indeterminate" and one.name not in _ADDS_EVIDENCE
            for one in moving
        ):
            return "indeterminate"
        return "agree"

    def to_dict(self) -> dict[str, Any]:
        """Return the report as plain JSON data, for a pipeline that stores it."""
        return {
            "report_version": self.report_version,
            "verdict": self.verdict,
            "artifact": {
                "graph_fingerprint": self.graph_fingerprint,
                "document_digest": self.document_digest,
            },
            "checks": [check.to_dict() for check in self.checks],
        }


def verify_artifact(  # noqa: PLR0913 -- one keyword per kind of file a reviewer holds
    artifact: dict[str, Any] | str | Path,
    *,
    results: Path | str | None = None,
    model_points: Path | str | None = None,
    model: Path | str | None = None,
    assumptions: Sequence[Path | str] | None = None,
    scenarios: Path | str | None = None,
) -> VerificationReport:
    r"""Report whether each file given is the one the audit file records.

    Is this file of results the one the model in front of me produced? The
    audit file answers it, check by check. Its seal is taken again over the
    document, which shows whether it has changed since it was sealed. Each
    file named is then held against the member that records it:

    - ``results``: the file's sha256 against ``model.results``, and, where
      the file carries a result manifest, the model fingerprint and the
      policy-data digest it states against the audit file's own;
    - ``model_points``: the policy data's content against ``book.digest``,
      read as Parquet or CSV -- or, where the audit file states no book
      digest, the file's sha256 against ``model.model_points``;
    - ``model``: the model source's sha256 against ``model.source_sha``,
      and, where the audit file records a revision and the file sits in a
      git working tree, that tree's HEAD against ``model.git`` -- with the
      recorded ``dirty`` stated and what it means. A recorded dirty tree
      moves no exit status: git counts untracked files, so a results file
      written into the repository makes most exports dirty, and
      ``source_sha`` pins the model file itself. And ``modules``: each local
      module the model imports, against ``model.modules`` -- the file of
      that name beside the model file given, which is the file running it
      would import, so an edited helper fails as an edited model does.
      ``model.modules`` is read off the import statements, so where the
      model or a module of it loads code by path (``spec_from_file_location``,
      ``exec_module``, ``import_module``, ``run_path``, ``exec``) the line
      names each call as ``file:line`` and is ``indeterminate``. And
      ``graph``: the model imported and run over ``model_points`` -- composed
      through the plan ``scenarios`` names, for a scenario plan's record --
      in a fresh interpreter, without collecting, and its graph's fingerprint
      held against ``graph_fingerprint``. A graph that differs is
      ``disagree`` whatever the other lines say, naming each node whose own
      fingerprint moved with its formula and line; it holds in this
      environment, since the model's own code ran here. No ``model_points``,
      a model that cannot be rebuilt here, a plan's record with no
      ``scenarios``, or a line handing the engine a Python function or a
      compiled plugin is ``indeterminate``, naming why. A compiled
      rollforward enters the graph only by its identity, so a machine the
      file publishes whose body does not hash to that identity, or whose
      node's movement summary says another, is ``disagree`` first, naming
      the compilation, whatever the rebuild would say;
    - ``scenarios``: a scenario plan's run script, its sha256 against
      ``model.scenarios``;
    - ``assumptions``: files, and directories of them, holding the model's
      assumption tables. Each table the audit file records is found among
      them -- by the file the record says it was read from, or by its own
      name, ``<name>.parquet`` or ``<name>.csv`` -- or named outright as
      ``"NAME=FILE"``, and read as that table: through its recorded keys
      and answer column, by the steps ``Table`` takes, to the fingerprint
      ``Table.fingerprint()`` would give it. One line per table: ``agree``;
      ``disagree`` naming both fingerprints, only where the record names the
      file the table was a plain read of; ``indeterminate`` where the
      table's file is not found or cannot be read as it -- its recipe
      reshaped what it read, or its columns are not recorded -- or where a
      table the model built from a frame reads differently from the file
      matched to it, since a filter in code and an edit to the file read
      alike; and ``not_asked`` for a table built from a frame with no file
      named for it. Each join the model made has a line of its own, under
      the record's name for it (``join:<digits>``): ``agree`` where a file
      given holds the frame the model joined, and ``indeterminate``, never
      ``disagree``, where none does. ``"NAME=FILE"`` names the file for a
      join under that name, as for a table.

    ``holes`` needs no file: it reads the document's holes section (section
    7.1), and is asked wherever ``model_points``, ``model`` or
    ``assumptions`` is given. A column listed there reached the record by
    name only -- a file joined after ``collect()``, a write straight into
    the frame's query plan, a calculation on another frame -- so what made
    its values is
    held by no check, and the line is ``indeterminate``, naming each hole,
    its reason and the columns that rest on it. An empty section agrees. A
    results file held alone is asked only whether it is the file the run
    wrote, which no hole touches, and the line is not asked.

    ``versions`` needs no file: what the audit file records produced its
    values is held against what this process runs, and, beside a results
    file whose manifest Polars wrote, against that manifest's versions. It
    states what it finds and never moves the verdict.

    ``seal``, ``results``, ``source_sha``, ``modules``, ``scenarios``,
    ``graph``, ``holes`` and each table decide, and so does the policy data
    -- ``book`` where the audit file states a book digest, and
    ``model_points``, the file's own stamp, only where it states none. One
    that cannot be made because nothing was recorded, or because the file it
    needs is not there, is ``indeterminate``, which holds
    the verdict open. ``results_manifest`` and ``git`` add evidence,
    agreeing or disagreeing only where their condition holds and otherwise
    ``not_asked``, moving nothing. So a results file with no manifest whose
    sha256 agrees is agreement, and one the audit file records nothing for
    is ``indeterminate`` whatever its manifest says.

    Every check is reported, one line each, ``disagree`` naming both values.
    A recorded path is printed for context and never opened -- the file
    checked is a file you name, a file in a directory you name, or a module
    beside the model file you name.

    Args:
        artifact: The audit file, as the parsed document, the text of it, or
            the path of the stored file.
        results: A results file to check.
        model_points: A policy data file to check, ``.parquet`` or CSV.
        model: A model source file to check, with the local modules beside
            it that it imports, and the graph it rebuilds.
        assumptions: Assumption files, ``.parquet`` or CSV, and directories
            holding them, to check the recorded tables against; a string
            ``"NAME=FILE"`` names the file for table ``NAME``.
        scenarios: A scenario plan's run script, to check against
            ``model.scenarios`` and to rebuild a plan's record through.

    Returns:
        A :class:`VerificationReport`. Its ``verdict`` is what a pipeline
        branches on, and its ``checks`` are what a reviewer reads.

    Raises:
        OSError: If a file named cannot be read, or an assumption path names
            nothing.
        ValueError: If the audit file is not a calculation-graph artifact --
            not a JSON object, or one whose ``schema`` names no graph
            artifact, such as a scenario run's own record -- or if the
            policy data, or an assumption file, is neither Parquet nor CSV,
            or cannot be read as one; or if ``"NAME=FILE"`` names a table the
            audit file does not record.

    Examples:
        A model exported with its identity agrees with the files it was run
        from. Its mortality rate is read from a parameter file no stamp
        holds, so when the rate there moves, the model file still agrees and
        the graph the files rebuild does not:

        >>> import json
        >>> import shutil
        >>> import tempfile
        >>> from pathlib import Path
        >>> import polars as pl
        >>> from gaspatchio import ActuarialFrame
        >>> from gaspatchio.frame.graph import (
        ...     GraphExportConfig,
        ...     GraphExporter,
        ...     ModelIdentity,
        ...     verify_artifact,
        ... )
        >>> from gaspatchio.runner import load_model_from_path
        >>> folder = Path(tempfile.mkdtemp())
        >>> book = folder / "book.parquet"
        >>> pl.DataFrame({"sum_assured": [100_000.0]}).write_parquet(book)
        >>> _ = (folder / "basis.json").write_text('{"qx": 0.00123}')
        >>> model_file = folder / "model.py"
        >>> _ = model_file.write_text(
        ...     "import json\n"
        ...     "from pathlib import Path\n"
        ...     "HERE = Path(__file__).parent\n"
        ...     "BASIS = json.loads((HERE / 'basis.json').read_text())\n"
        ...     "def main(af):\n"
        ...     "    af.death_claims = af.sum_assured * BASIS['qx']\n"
        ...     "    return af\n"
        ... )
        >>> main = load_model_from_path(model_file, "main")
        >>> af = main(ActuarialFrame(pl.read_parquet(book)))
        >>> identity = ModelIdentity.of(model_file, model_points=book)
        >>> audit = json.loads(
        ...     GraphExporter(af).export(config=GraphExportConfig(model=identity))
        ... )
        >>> verify_artifact(audit, model=model_file, model_points=book).verdict
        'agree'
        >>> _ = (folder / "basis.json").write_text('{"qx": 0.00124}')
        >>> report = verify_artifact(audit, model=model_file, model_points=book)
        >>> [check.name for check in report.checks if check.outcome == "disagree"]
        ['graph']
        >>> shutil.rmtree(folder)

        An assumption table read from a file is checked against that file,
        which fails once a rate in it moves:

        >>> from gaspatchio.assumptions import Table
        >>> folder = Path(tempfile.mkdtemp())
        >>> rates = folder / "vbt_2015.parquet"
        >>> pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.002]}).write_parquet(rates)
        >>> mortality = Table("vbt_2015", rates, {"age": "age"}, "qx")
        >>> af = ActuarialFrame(pl.DataFrame({"age": [30, 40]}))
        >>> af.qx = mortality.lookup(age=af.age)
        >>> audit = json.loads(GraphExporter(af).export())
        >>> verify_artifact(audit, assumptions=[folder]).verdict
        'agree'
        >>> pl.DataFrame({"age": [30, 40], "qx": [0.001, 0.0025]}).write_parquet(rates)
        >>> verify_artifact(audit, assumptions=[folder]).verdict
        'disagree'
        >>> shutil.rmtree(folder)

    """
    document = _audit_document(artifact)
    block = document.get("model")
    recorded: Mapping[str, Any] = block if isinstance(block, dict) else {}
    given_results = _given(results)
    given_points = _given(model_points)
    given_model = _given(model)
    given_plan = _given(scenarios)
    tables = _table_checks(document, assumptions)
    stated_seal = document.get(DOCUMENT_DIGEST_FIELD)
    stated_fingerprint = document.get("graph_fingerprint")
    return VerificationReport(
        report_version=VERIFICATION_REPORT_VERSION,
        graph_fingerprint=(
            stated_fingerprint if isinstance(stated_fingerprint, str) else None
        ),
        document_digest=stated_seal if isinstance(stated_seal, str) else None,
        checks=(
            _seal_check(document),
            _results_check(recorded, given_results),
            _manifest_check(document, given_results),
            _book_check(document, recorded, given_points),
            _model_points_check(document, recorded, given_points),
            _source_check(recorded, given_model),
            _modules_check(recorded, given_model),
            _plan_check(recorded, given_plan),
            _rebuilt_check(document, given_model, given_points, given_plan),
            _holes_check(
                document,
                asked=any(
                    given is not None
                    for given in (given_points, given_model, assumptions)
                ),
            ),
            _revision_check(recorded, given_model),
            _versions_check(document, given_results),
            *tables,
        ),
    )


# --- reading what was handed over ----------------------------------------------


def _audit_document(artifact: dict[str, Any] | str | Path) -> dict[str, Any]:
    """Return the audit file as a document, or say why there is none.

    Read by the reader ``validate_artifact`` uses, so a string is the text of
    a document or the path of one exactly as it is there. Anything that is
    not a calculation-graph artifact -- not a JSON object, or one whose
    ``schema`` names no graph artifact this build reads -- is refused rather
    than checked: a check reads members off an audit file, and every member
    missing from something else would read as nothing recorded, which is a
    verdict about nothing. A scenario run's own record is also written under
    a name ending ``.audit.json``, so it is named for what it is.
    """
    try:
        document = _document(artifact)
    except UnicodeDecodeError as error:
        msg = f"{artifact} holds bytes rather than text, so it is not an audit file."
        raise ValueError(msg) from error
    except ValueError as error:
        msg = (
            f"{artifact} does not hold JSON, so it is not an audit file: {error}. "
            "Name the artifact calc-graph or an export wrote."
        )
        raise ValueError(msg) from error
    if isinstance(document, dict):
        if document.get("schema") in SCHEMA_IDENTIFIERS:
            return document
        raise ValueError(_not_a_graph_artifact(document))
    msg = (
        document.message
        if isinstance(document, Finding)
        else (
            "The audit file's top level is not a JSON object, so there is no "
            "version block in it to check anything against. Name the artifact "
            "calc-graph or an export wrote."
        )
    )
    raise ValueError(msg)


# The members a scenario run writes at the top of its own record, and the one
# a report every artifact command writes carries. Named so a document handed
# over as the audit file can be told for what it is.
_SIDECAR_MEMBERS: Final[frozenset[str]] = frozenset(
    {"schema_version", "plan_canonical_form"}
)
_REPORT_MEMBER: Final[str] = "report_version"


def _not_a_graph_artifact(document: dict[str, Any]) -> str:
    """Return the one sentence refusing a JSON object that is no audit file."""
    if _SIDECAR_MEMBERS.issubset(document):
        return (
            "The file given as the audit file is not a calculation-graph "
            "artifact: it is a scenario run's own record, the file that names "
            "the plan it ran, which is written under a name ending .audit.json "
            "too. Give the artifact the run exported -- it names this file in "
            "model.audit."
        )
    if _REPORT_MEMBER in document:
        return (
            "The file given as the audit file is not a calculation-graph "
            f"artifact: it is a report, {document[_REPORT_MEMBER]!r}, that an "
            "artifact command wrote. Give the artifact it was written about."
        )
    stated = document.get("schema")
    said = (
        f"its schema is {stated!r}, which names no graph artifact this build reads"
        if isinstance(stated, str)
        else "it states no schema"
    )
    return (
        f"The file given as the audit file is not a calculation-graph artifact: "
        f"{said}. Give the artifact calc-graph or an export wrote."
    )


def _given(path: Path | str | None) -> Path | None:
    """Return a file the caller named as a path, or None where they named none."""
    return None if path is None else Path(path)


def _sha_of(path: Path) -> str:
    """Return a named file's sha256, taken the way the audit file's stamps were."""
    taken = file_sha(path)
    if taken is None:
        msg = (
            f"{path} could not be read, so there is nothing to hold against the "
            "audit file. Name a file that exists and can be read."
        )
        raise OSError(msg)
    return taken


def _policy_data(path: Path) -> pl.DataFrame:
    """Return the policy data a file holds, read the way the export read it."""
    try:
        return book_from_file(path)
    except pl.exceptions.PolarsError as refused:
        said = str(refused).strip().splitlines()
        reason = said[0] if said else type(refused).__name__
        msg = (
            f"{path.name} could not be read as policy data, as Parquet or CSV "
            f"({reason}). Name the model points file the model was run over."
        )
        raise ValueError(msg) from refused


def _recorded_file(recorded: Mapping[str, Any], member: str) -> tuple[str, str] | None:
    """Return the path and fingerprint a member of the block records, if any."""
    stamped = recorded.get(member)
    if not isinstance(stamped, dict):
        return None
    fingerprint = stamped.get("fingerprint")
    if not isinstance(fingerprint, str):
        return None
    path = stamped.get("path")
    return (path if isinstance(path, str) else "an unnamed path", fingerprint)


def _check(name: str, outcome: CheckOutcome, detail: str) -> Check:
    """Return one line of the report, held against its own member."""
    return Check(name=name, against=_AGAINST[name], outcome=outcome, detail=detail)


def _not_asked(name: str, what: str) -> Check:
    """Return the line for a check whose input was not given."""
    return _check(name, "not_asked", f"No {what} was given.")


def _file_against(name: str, given: Path, recorded: tuple[str, str]) -> Check:
    """Return one file's own bytes held against the stamp the block records."""
    where, fingerprint = recorded
    taken = _sha_of(given)
    if taken == fingerprint:
        return _check(
            name,
            "agree",
            f"{given.name} is {taken}, the file the audit file records as {where}.",
        )
    return _check(
        name,
        "disagree",
        f"{given.name} is {taken}, and the audit file records {fingerprint} "
        f"for {where}: it is not the file the audit file names.",
    )


# --- the checks ------------------------------------------------------------


def _seal_check(document: dict[str, Any]) -> Check:
    """Return whether the audit file has changed since it was sealed.

    The reading ``validate_artifact(deep=True)`` gives, taken on its own:
    the seal is recomputed over the document with the seal left out, and a
    disagreement is the refusal that reading writes, naming both digests.
    An agreement says what section 13.1 says a seal shows, and no more: the
    document has not changed since it was sealed. Whoever edits a file can
    seal it again, so the seal is evidence of which file this is only against
    a digest kept independently.
    """
    if DOCUMENT_DIGEST_FIELD not in document:
        return _check(
            _SEAL,
            "indeterminate",
            f"The audit file carries no {DOCUMENT_DIGEST_FIELD}, so nothing in it "
            "shows whether it has changed since it was written. Export the "
            "model again to seal it.",
        )
    refusals = _document_seal_findings(document)
    if refusals:
        return _check(_SEAL, "disagree", " ".join(f.message for f in refusals))
    return _check(
        _SEAL,
        "agree",
        f"The document recomputes to its own {DOCUMENT_DIGEST_FIELD}, "
        f"{document[DOCUMENT_DIGEST_FIELD]}: it has not changed since it was "
        "sealed. A seal is tamper-evidence and not a signature -- whoever edits "
        "a file can seal it again -- so it shows which file this is only "
        "against a digest kept independently, such as the one a filed change "
        "report records beside it (section 13.1).",
    )


def _results_check(recorded: Mapping[str, Any], given: Path | None) -> Check:
    """Return whether a results file is the one the run wrote."""
    if given is None:
        return _not_asked(_RESULTS, "results file")
    stamp = _recorded_file(recorded, _RESULTS)
    if stamp is None:
        return _check(
            _RESULTS,
            "indeterminate",
            "The audit file records no results file: model.results is absent, "
            "which says the run it is an account of wrote none, so "
            f"{given.name} has nothing to be held against. A result manifest "
            "that agrees says only which model and which policy data produced "
            "the file: nothing ties it to this audit file. Name the results "
            "file when the model is exported -- calc-graph --results, or "
            "ModelIdentity.of(..., results=...) -- and it is recorded.",
        )
    return _file_against(_RESULTS, given, stamp)


def _manifest_check(document: dict[str, Any], given: Path | None) -> Check:
    """Return whether a results file says it came from this model and this book.

    Evidence beside the results check, which decides. A result manifest is
    the file's own statement of the model fingerprint and the policy-data
    digest it was produced from, so where the file carries one it agrees or
    disagrees: a file matching its recorded sha256 can still say it came
    from somewhere else. A file carrying no manifest key at all has nothing
    to add and the check is not asked; one carrying part of a manifest, or a
    member that does not parse, disagrees, naming what is damaged.

    **The model fingerprint is always compared. The book half is compared
    where it can be.** Where the audit file's model reads a column its book
    does not hold -- a scenario axis crossed onto the book is the ordinary
    case -- an engine handed the crossed rows records a digest of those rows,
    by design (section 7.5), so that half is not asked and the detail says
    why. Where the audit file states no book digest, there is nothing to
    compare it with.
    """
    if given is None:
        return _not_asked(_MANIFEST, "results file")
    read = _manifest_of(given)
    if isinstance(read, Check):
        return read
    stated_fingerprint = document.get("graph_fingerprint")
    fingerprint_agrees = read.graph_fingerprint == stated_fingerprint
    named = f"The file's manifest names the model {read.graph_fingerprint}"
    said = [
        f"{named}, the audit file's graph_fingerprint."
        if fingerprint_agrees
        else f"{named}, and the audit file's graph_fingerprint is {stated_fingerprint}."
    ]
    book_agrees, on_the_book = _the_manifest_s_book(document, read.inputs_digest)
    said.append(on_the_book)
    agrees = fingerprint_agrees and book_agrees
    return _check(_MANIFEST, "agree" if agrees else "disagree", " ".join(said))


def _the_manifest_s_book(
    document: dict[str, Any], inputs_digest: str
) -> tuple[bool, str]:
    """Return whether the manifest's book half agrees, and what was said of it.

    A half that cannot be compared is no disagreement: the book check is
    the one that decides whether the policy data is the book, and this
    half only adds evidence where it can be read.
    """
    crossed = _columns_crossed_onto_the_book(document)
    if crossed:
        return True, (
            f"The audit file's model reads {_named_with_where(document, crossed)}, "
            "which its book does not hold -- a column crossed onto the book, as "
            "a scenario axis is. An engine handed the crossed rows records a "
            "digest of those rows, by design, so the manifest's inputs_digest "
            f"{inputs_digest} is not held against book.digest."
        )
    stated, _ = _stated_book(document)
    if stated is None:
        return True, (
            "The audit file states no digest of its book, so the manifest's "
            f"inputs_digest {inputs_digest} is not compared."
        )
    if inputs_digest == stated:
        return True, (
            f"Its inputs_digest is {inputs_digest}, the audit file's book.digest."
        )
    return False, (
        f"Its inputs_digest is {inputs_digest}, and the audit file's book.digest "
        f"is {stated}."
    )


def _columns_crossed_onto_the_book(document: dict[str, Any]) -> list[str]:
    """Return the columns the model reads that its book does not hold.

    The inputs the model's answers rest on, read the way the book's own
    columns are (``book_columns``), less the columns the book was digested
    over: what is left was handed to the model beside the book, which is
    what a scenario axis crossed onto it is.
    """
    nodes = [node for node in document.get("nodes") or () if isinstance(node, dict)]
    book = document.get("book")
    held = book.get("columns") if isinstance(book, dict) else None
    if not isinstance(held, list):
        return []
    steps = [step for step in document.get("selection") or () if isinstance(step, dict)]
    return sorted(set(book_columns(nodes, steps)) - {str(column) for column in held})


def _named_with_where(document: dict[str, Any], columns: list[str]) -> str:
    """Return columns named with the line each was handed to the model at."""
    at = {
        node.get("column"): node.get("source_location")
        for node in document.get("nodes") or ()
        if isinstance(node, dict) and node.get("kind") == "input"
    }
    return ", ".join(
        f"{column} (handed to it at {at[column]})"
        if isinstance(at.get(column), str)
        else column
        for column in columns
    )


def _manifest_of(given: Path) -> ResultManifest | Check:
    """Return the manifest a results file carries, or the line saying why none is read.

    A file with no manifest key at all carries no manifest, and the line is
    not asked. A file carrying some of the keys was written with a manifest
    and has lost part of it, and the line disagrees, naming each member that
    is missing or does not parse.
    """
    try:
        metadata = pl.read_parquet_metadata(given)
    except pl.exceptions.PolarsError as refused:
        said = str(refused).strip().splitlines()
        reason = said[0] if said else type(refused).__name__
        return _check(
            _MANIFEST,
            "not_asked",
            "The file carries no result manifest. Its footer does not read as "
            f"Parquet ({reason}). The results check decides.",
        )
    if not any(key.startswith(_METADATA_PREFIX) for key in metadata):
        return _check(
            _MANIFEST,
            "not_asked",
            "The file carries no result manifest. It states no model and no "
            "policy data of its own to hold against the audit file. The results "
            "check decides.",
        )
    damage = _damage_to(metadata)
    if damage:
        return _check(
            _MANIFEST,
            "disagree",
            f"The file's result manifest is damaged: {'; '.join(damage)}. It "
            "was written with a manifest and no longer says in full what "
            "produced it, and a manifest partly there vouches for nothing.",
        )
    return ResultManifest.from_metadata(metadata)


def _damage_to(metadata: Mapping[str, str]) -> list[str]:
    """Return each member of a result manifest that is missing, unparsed or misshapen.

    A member that parses to a shape its writer never writes -- a list where
    the columns' mapping belongs, a number for the versions -- is damage as
    much as one that does not parse, and is named the same way rather than
    reaching the comparisons below and failing there.
    """
    damage: list[str] = []
    for member in fields(ResultManifest):
        key = f"{_METADATA_PREFIX}{member.name}"
        if key not in metadata:
            damage.append(f"{key} is missing")
            continue
        problem = _member_damage(member.name, metadata[key])
        if problem is not None:
            damage.append(problem)
            continue
        if member.name == "row_identity":
            try:
                _identity_read(json.loads(metadata[key]))
            except ValueError:
                damage.append(
                    f"{key} is neither null nor the names of the columns that "
                    "name its rows"
                )
    return damage


def _stated_book(document: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return the book digest the audit file states, or why it states none."""
    book = document.get("book")
    stated = book.get("digest") if isinstance(book, dict) else None
    if isinstance(stated, str):
        return stated, None
    why = stated.get("detail") if isinstance(stated, dict) else None
    return None, why if isinstance(why, str) and why else None


def _book_check(
    document: dict[str, Any], recorded: Mapping[str, Any], given: Path | None
) -> Check:
    """Return whether a policy data file holds the book the audit file states.

    **The book decides where the audit file states its digest**, as it
    decides a comparison of two audit files (section 14.2): the content, not
    the file, so the same policies written out again are the same book, and a
    column the model does not read is no part of it. The digest reading is
    the one ``validate_artifact(book=)`` makes, taken on its own: the digest
    is taken again over the columns the document names, by the function the
    producer took it with, and a mismatch is refused naming both digests. The
    schema and structure readings ``validate_artifact`` runs beside it answer
    whether the document is well formed -- which the seal answers for a
    document its producer wrote -- and they are most of the cost on a large
    model, so they are not run here.

    Where the audit file states no digest, the file stamp in
    ``model.model_points`` decides instead and this line is not asked; where
    it records neither, nothing was recorded to hold the data against, and
    the question is left open.
    """
    if given is None:
        return _not_asked(_BOOK_CHECK, "model points file")
    stated, why = _stated_book(document)
    if stated is None:
        unstated = "The audit file states no digest of its book" + (
            f" ({why})" if why else ""
        )
        if _recorded_file(recorded, _MODEL_POINTS) is not None:
            return _check(
                _BOOK_CHECK,
                "not_asked",
                f"The model_points check decides. {unstated}, so the file stamp "
                f"in model.model_points decides whether {given.name} is the "
                "policy data the model was run over, as it decides a comparison "
                "of two audit files.",
            )
        return _check(
            _BOOK_CHECK,
            "indeterminate",
            f"{unstated}, and it names no model points file, so nothing was "
            f"recorded to hold {given.name} against. Export the model again from "
            "the frame built over its book to record one.",
        )
    frame = _policy_data(given)
    refusals = [
        finding
        for finding in _book_digest_findings(document, frame)
        if finding.severity == "error"
    ]
    if refusals:
        return _check(_BOOK_CHECK, "disagree", " ".join(f.message for f in refusals))
    book = document.get("book")
    columns = book.get("columns") if isinstance(book, dict) else None
    over = ", ".join(str(column) for column in columns or ()) or "no columns"
    return _check(
        _BOOK_CHECK,
        "agree",
        f"{given.name} digests to {stated} over {over}, the book the audit "
        "file states.",
    )


def _model_points_check(
    document: dict[str, Any], recorded: Mapping[str, Any], given: Path | None
) -> Check:
    """Return whether a policy data file is, byte for byte, the file recorded.

    **It decides only where the audit file states no book digest**, as the
    file stamp decides a comparison of two audit files only there (section
    14.2). Where the book digest decides, a re-encoded Parquet, a CSV of the
    same data or a column the model does not read changes the file and not
    the book, so a difference in bytes is no difference in the policy data:
    the line is not asked, and says whether the bytes match, for information.
    """
    if given is None:
        return _not_asked(_MODEL_POINTS, "model points file")
    stamp = _recorded_file(recorded, _MODEL_POINTS)
    if _stated_book(document)[0] is not None:
        if stamp is None:
            return _check(
                _MODEL_POINTS,
                "not_asked",
                "The book check decides. The audit file names no model points "
                f"file whose bytes {given.name} could be set beside.",
            )
        where, fingerprint = stamp
        taken = _sha_of(given)
        said = (
            f"is byte for byte the file the audit file records as {where}"
            if taken == fingerprint
            else f"is {taken}, not byte for byte the file the audit file "
            f"records as {where} ({fingerprint}): the same policies written "
            "out again, or beside a column the model does not read, are "
            "another file and the same book"
        )
        return _check(
            _MODEL_POINTS,
            "not_asked",
            f"The book check decides. For information, {given.name} {said}.",
        )
    if stamp is None:
        return _check(
            _MODEL_POINTS,
            "not_asked",
            f"Nothing is recorded to hold {given.name} against. The audit file "
            "names no model points file and states no book digest, and the book "
            "check says the question is open.",
        )
    checked = _file_against(_MODEL_POINTS, given, stamp)
    return _check(
        _MODEL_POINTS,
        checked.outcome,
        f"{checked.detail} With no book digest in the audit file, the file's "
        "own bytes decide.",
    )


def _source_check(recorded: Mapping[str, Any], given: Path | None) -> Check:
    """Return whether a model source file is the source the audit file records."""
    if given is None:
        return _not_asked(_SOURCE, "model file")
    stated = recorded.get("source_sha")
    where = recorded.get("source_path")
    named = where if isinstance(where, str) else "the model source"
    if not isinstance(stated, str):
        return _check(
            _SOURCE,
            "indeterminate",
            "The audit file records no source_sha: its producer could not say "
            f"which model source it read, so {given.name} has nothing to be "
            "held against. Export with ModelIdentity.of naming the model file "
            "and it is recorded.",
        )
    taken = _sha_of(given)
    if taken == stated:
        return _check(
            _SOURCE,
            "agree",
            f"{given.name} is {taken}, the source the audit file records as {named}.",
        )
    return _check(
        _SOURCE,
        "disagree",
        f"{given.name} is {taken}, and the audit file records {stated} for "
        f"{named}: it is not the model source the audit file is an account of. "
        "The comparison is over the file's bytes, so a checkout that converts "
        "line endings (git's core.autocrlf) changes them without changing a "
        "line of the model.",
    )


def _plan_check(recorded: Mapping[str, Any], given: Path | None) -> Check:
    """Return whether a scenario plan's run script is the one the audit file records.

    Decides, as ``source_sha`` does: the plan is as much the run as the model
    is, since a shock factor edited in it moves every scenario it shocks.
    """
    if given is None:
        return _not_asked(_PLAN, "scenario plan's run script")
    stamped = _recorded_file(recorded, _PLAN)
    if stamped is None:
        return _check(
            _PLAN,
            "indeterminate",
            "The audit file names no scenario plan in model.scenarios: it is "
            "not a scenario plan's record, or was written before the record "
            f"named the plan, so {given.name} has nothing to be held against. "
            "The graph line still rebuilds the record through it.",
        )
    return _file_against(_PLAN, given, stamped)


def _rebuilt_check(
    document: dict[str, Any],
    given: Path | None,
    points: Path | None,
    plan: Path | None,
) -> Check:
    """Return whether the files given rebuild the graph the audit file records.

    Asked wherever a model file is given, and decides: a stamp says whether a
    file moved, and the graph says whether the calculation did, wherever the
    input that moved it came from (:mod:`._rebuilt_graph`).
    """
    if given is None:
        return _not_asked(_REBUILT, "model file")
    edited = _compilations_not_named(document)
    if edited:
        return _check(_REBUILT, "disagree", edited)
    outcome, detail = rebuilt_decision(
        document, model=given, model_points=points, scenarios=plan
    )
    return _check(_REBUILT, outcome, detail)


def _compilations_not_named(document: dict[str, Any]) -> str:
    """Return why a published rollforward machine is not the one its identity names.

    The rebuild holds the graph the files build against ``graph_fingerprint``,
    and a compilation enters both only through its identity. A body edited
    after export -- a floor, an opening value, an operation -- and resealed
    keeps that identity, so the rebuild agrees while the file runs another
    machine. The identity is the recipe-grammar hash of the body as published
    (section 12.1), so the file alone says whether the two still match: where
    they do not, or the node's movement summary disagrees with the body, the
    line disagrees, naming the compilation. Empty where every published body
    is the machine its identity names.
    """
    nodes = document.get("nodes")
    found = _compilation_findings(document, nodes if isinstance(nodes, list) else [])
    named = [
        f"{finding.where}: {finding.message}"
        for finding in found
        if finding.severity == "error"
    ]
    return " ".join(named)


def _revision_check(recorded: Mapping[str, Any], given: Path | None) -> Check:
    """Return whether the checkout the model sits in is at the recorded commit.

    Evidence beside the source_sha check, which decides: were it to decide,
    the exit status would turn on whether a reviewer's copy of the model sits
    in a checkout. Asked where the audit file records a revision and the
    model file sits in a git working tree, because both halves are needed: a
    commit to hold HEAD against, and a HEAD. Where either is missing the
    check is not asked, and the detail says which. HEAD against the recorded
    commit decides the line. Where the audit file says git could not state
    the revision, the line is indeterminate, naming git's reason, and holds
    nothing open.

    **The recorded ``dirty`` is stated, with what it means, and moves no
    exit status.** It describes the whole tree at export, and git counts an
    untracked file as a change: a results file written into the repository
    is enough to make an export dirty, so a dirty record is common and says
    only that the commit alone does not hold the model as it ran. source_sha
    pins the model file itself either way.
    """
    if given is None:
        return _not_asked(_REVISION, "model file")
    git = recorded.get("git")
    if isinstance(git, dict) and git.get("omitted") == "unavailable":
        said = git.get("detail")
        why = said if isinstance(said, str) and said else "it gave no reason"
        return _check(
            _REVISION,
            "indeterminate",
            "The audit file records that git could not state the revision "
            f"when it was written: {why}. There is no commit to hold HEAD "
            "against. That holds nothing open: the source_sha check decides.",
        )
    directory = given.resolve().parent
    head = git_output(directory, "rev-parse", "HEAD")
    commit = git.get("commit") if isinstance(git, dict) else None
    if not isinstance(git, dict) or not isinstance(commit, str) or head is None:
        return _check(
            _REVISION, "not_asked", _no_revision_to_compare(given, commit, head)
        )
    said = [
        f"HEAD is {head}, the commit the audit file records."
        if head == commit
        else f"HEAD is {head}, and the audit file records {commit}: this "
        "checkout is at another revision."
    ]
    said.append(_recorded_state(git.get("dirty")))
    said.append("source_sha pins the model file itself.")
    return _check(_REVISION, "agree" if head == commit else "disagree", " ".join(said))


def _no_revision_to_compare(given: Path, commit: object, head: str | None) -> str:
    """Return why the revision check has nothing to compare, naming each half."""
    said: list[str] = []
    if not isinstance(commit, str):
        said.append(
            "The audit file records no revision. Its model.git is null, so the "
            "model was exported outside a git working tree. Export from a git "
            "checkout to record one."
        )
    if head is None:
        said.append(
            f"There is no git HEAD beside {given.name}. It is not in a git "
            "working tree, or the tree has no commit yet."
        )
    elif not isinstance(commit, str):
        said.append(f"HEAD here is {head}.")
    said.append("The source_sha check decides.")
    return " ".join(said)


def _recorded_state(dirty: object) -> str:
    """Return what the recorded ``dirty`` says about the commit beside it."""
    if dirty is True:
        return (
            "The audit file records the tree as dirty when it was written: "
            "something in the checkout was uncommitted or untracked, or the "
            "commit did not hold the model file itself, so the commit alone "
            "does not hold the model as it ran. That moves no exit status: git "
            "counts untracked files, so a results file written into the "
            "repository is enough to make an export dirty."
        )
    if dirty is False:
        return (
            "The audit file records the tree as clean when it was written: the "
            "commit held the checkout's files, the model file among them, as "
            "the model ran."
        )
    return "The audit file does not say whether the tree was clean when it was written."


# --- what produced the values --------------------------------------------------

# How each key of the version mapping is said in a sentence, in the mapping's
# own order. A key a second engine states beyond these is said by its name.
_VERSION_WORDS: Final[dict[str, str]] = {
    "core_version": "core",
    "extension_version": "extension",
    "polars_version": "Polars",
    "python_version": "Python",
    "platform": "platform",
    "extension_sha256": "the extension's sha256",
}
_IMPORTS: Final[str] = "imports"
_OMITTED_WITHHELD: Final[str] = "withheld"


def _versions_check(document: dict[str, Any], given: Path | None) -> Check:
    """Return what the recorded library versions say beside this process's.

    Evidence, and the one line that moves nothing: it tells a reviewer
    whether re-running the model here would use the library that produced the
    audit file's values, and a library that moved is the reason to compare
    two runs' numbers, not a sign that these are the wrong files -- the
    results file's sha256 and the model's source_sha decide that. So it agrees
    where every recorded version is this process's, disagrees naming each one
    that is not, and is not asked where the audit file records none.

    The installed distributions the model imports are held against what is
    installed here, each by its version. Beside a results file whose
    manifest Polars wrote, the record's versions are held against the
    manifest's too: one run states one set, so two that differ say the files
    did not come out of one run.
    """
    producer = document.get("producer")
    stated = producer.get("versions") if isinstance(producer, dict) else None
    if isinstance(stated, dict) and stated.get("omitted") == _OMITTED_WITHHELD:
        return _check(
            _VERSIONS,
            "not_asked",
            "The audit file records its library versions as withheld. Whoever "
            "exported it chose not to carry them, so there is nothing to hold "
            "this process against.",
        )
    if not isinstance(stated, dict):
        return _check(
            _VERSIONS,
            "not_asked",
            "The audit file records no library versions. Its producer.versions "
            "is absent, as on a document written before the member. Export the "
            "model again to record them.",
        )
    recorded = {
        key: value
        for key, value in stated.items()
        if key != _IMPORTS and isinstance(value, str)
    }
    here = _differences(recorded, versions_in_this_process(), where="here")
    imported = stated.get(_IMPORTS)
    installed = _imports_against_this_process(
        imported if isinstance(imported, dict) else {}
    )
    sha = ", the extension's sha256 included" if "extension_sha256" in recorded else ""
    said = [
        f"The audit file records {_described(recorded)}"
        + (
            f", and this process runs the same{sha}."
            if not here
            else f"; this process differs: {'; '.join(here)}."
        )
    ]
    if installed:
        said.append(f"What the model imports differs here: {'; '.join(installed)}.")
    manifest = _manifest_versions_against(recorded, given)
    if manifest is not None:
        said.append(manifest[1])
    moved = bool(here or installed or (manifest is not None and not manifest[0]))
    said.append(
        "Re-running here may not use the library that produced these values; "
        "this line moves no exit status, and the results sha256 and source_sha "
        "decide whether these are the files."
        if moved
        else "Re-running here would use the same library. This line moves no "
        "exit status."
    )
    return _check(_VERSIONS, "disagree" if moved else "agree", " ".join(said))


def _described(recorded: Mapping[str, str]) -> str:
    """Return the recorded versions as one phrase, in the mapping's order."""
    words = [
        f"{_VERSION_WORDS.get(key, key)} {value}"
        for key, value in recorded.items()
        if key not in {"platform", "extension_sha256"}
    ]
    platform = recorded.get("platform")
    if platform is not None:
        words.append(f"on {platform}")
    return ", ".join(words) if words else "no library version it names"


def _differences(
    recorded: Mapping[str, str], other: Mapping[str, str], *, where: str
) -> list[str]:
    """Return each recorded version ``other`` states otherwise, both values said."""
    differ: list[str] = []
    for key, value in recorded.items():
        theirs = other.get(key)
        if theirs == value:
            continue
        stated = theirs if theirs is not None else "none"
        differ.append(
            f"{_VERSION_WORDS.get(key, key)} {value} recorded, {stated} {where}"
        )
    return differ


def _imports_against_this_process(imported: Mapping[str, Any]) -> list[str]:
    """Return each recorded distribution installed here at another version, or not."""
    differ: list[str] = []
    for name, recorded in sorted(imported.items()):
        try:
            installed: str | None = version(name)
        except PackageNotFoundError:
            installed = None
        if installed == recorded:
            continue
        differ.append(
            f"{name} {recorded} recorded, "
            + (f"{installed} installed here" if installed else "not installed here")
        )
    return differ


def _manifest_versions_against(
    recorded: Mapping[str, str], given: Path | None
) -> tuple[bool, str] | None:
    """Return whether a results file's manifest states the recorded versions.

    None where no results file was given, or it carries no manifest to read:
    the manifest check says why. A manifest a second engine wrote states that
    engine's versions, which are not the record's to agree with.
    """
    if given is None:
        return None
    read = _manifest_of(given)
    if isinstance(read, Check):
        return None
    if read.producer != "polars":
        return True, (
            f"The results file's manifest was written by {read.producer}, whose "
            "versions are its own, so they are not held against the record's."
        )
    if not read.versions:
        return True, "The results file's manifest states no library versions."
    differ = _differences(recorded, read.versions, where="in the manifest")
    if not differ:
        return True, "The results file's manifest states the same versions."
    return False, (
        f"The results file's manifest states otherwise: {'; '.join(differ)}. "
        "One run states one set, so the two files did not come out of one run."
    )


# --- the modules a model imports -------------------------------------------------


def _modules_check(recorded: Mapping[str, Any], given: Path | None) -> Check:
    """Return whether each local module the model imports is the one recorded.

    **A helper is found beside the model file named, and nowhere else.** The
    record writes each module's path against the model's root, and a module
    is always beside the model or in a package beside it, so its place
    relative to ``source_path`` is its place relative to the model file a
    reviewer holds -- which is where running that model would import it
    from. The recorded path is never opened as it stands: that is where the
    file sat on the machine that exported, and this is a check of the files
    in hand.

    Decides, as ``source_sha`` decides: one module that differs is a model
    that differs, named with both digests. A module the record names and the
    model's directory does not hold, or one the producer could not read,
    leaves the question open.
    """
    if given is None:
        return _not_asked(_MODULES, "model file")
    stated = recorded.get("modules")
    if not isinstance(stated, list):
        return _check(
            _MODULES,
            "indeterminate",
            "The audit file records no model.modules: it was written before an "
            "audit file named the local modules a model imports, or by a "
            "producer that did not, so a helper beside "
            f"{given.name} has nothing to be held against. Export the model "
            "again to record them.",
        )
    loaded = _loaded_by_path(given)
    if not stated:
        return (
            _check(_MODULES, "indeterminate", loaded)
            if loaded
            else _check(
                _MODULES,
                "agree",
                "The audit file records that the model imports no module from "
                f"beside itself, so there is nothing beside {given.name} to "
                "hold. source_sha pins the model file's own import lines.",
            )
        )
    base = recorded.get("source_path")
    model_directory = PurePosixPath(base).parent if isinstance(base, str) else None
    differ: list[str] = []
    open_: list[str] = []
    agree: list[str] = []
    for module in stated:
        said, outcome = _module_against(module, given, model_directory)
        if outcome == "disagree":
            differ.append(said)
        elif outcome == "indeterminate":
            open_.append(said)
        else:
            agree.append(said)
    if differ:
        return _check(_MODULES, "disagree", " ".join([*differ, *open_, *agree]))
    if open_ or loaded:
        return _check(
            _MODULES, "indeterminate", " ".join([*open_, *agree, *[loaded][:1]])
        )
    return _check(_MODULES, "agree", " ".join(agree))


def _loaded_by_path(given: Path) -> str:
    """Return the sentence for code the model loads past its imports, or nothing.

    ``model.modules`` is read off the model's import statements (section 7),
    so a helper loaded by its path, or by a name computed as the model runs,
    is on no list and nothing holds it. Agreement over the modules listed
    would then say more than was checked, so the line stays open and names
    each call.
    """
    calls = loads_by_path(given)
    if not calls:
        return ""
    return (
        f"{given.name} loads code its import statements do not name -- "
        f"{', '.join(calls)} -- and model.modules lists only what the import "
        "statements reach, so a helper loaded that way is not on the record "
        "and an edit to it would go unseen here. It could not be checked. "
        "Import the helper by name (with the model's directory importable, as "
        "gspio runs it) so the record lists it and this line can hold it."
    )


def _module_against(
    module: object, given: Path, model_directory: PurePosixPath | None
) -> tuple[str, Literal["agree", "disagree", "indeterminate"]]:
    """Return one recorded module held against the file beside the model."""
    if not isinstance(module, dict) or not isinstance(module.get("path"), str):
        return (
            (
                "An entry of model.modules names no path, so there is no file "
                "to find for it."
            ),
            "indeterminate",
        )
    path: str = module["path"]
    stated = module.get("fingerprint")
    if not isinstance(stated, str):
        return (
            (
                f"{path} carries no fingerprint: the producer could not read "
                "it, so nothing was recorded to hold it against."
            ),
            "indeterminate",
        )
    beside = given.parent / (
        posixpath.relpath(path, str(model_directory))
        if model_directory is not None
        else path
    )
    taken = file_sha(beside)
    if taken is None:
        return (
            (
                f"{path} is not beside {given.name}: the audit file records the "
                f"model importing it, and there is no {beside.name} where "
                "running this model would import it from, so it cannot be "
                "checked."
            ),
            "indeterminate",
        )
    # The digest is the file read here, so the line names that file; the
    # recorded path beside it where the two are spelled differently, which
    # they are whenever the model checked is not where it was exported.
    read = _as_read(beside)
    named = read if read == path else f"{read} (recorded as {path})"
    if taken == stated:
        return (f"{named} is {taken}, the module the audit file records.", "agree")
    return (
        (
            f"{named} is {taken}, and the audit file records {stated}: it is "
            "not the module the model imported when it ran."
        ),
        "disagree",
    )


def _as_read(path: Path) -> str:
    """Return a file read here as a reviewer finds it: from where they stand."""
    plain = Path(posixpath.normpath(path.as_posix()))
    if plain.is_absolute():
        try:
            return plain.relative_to(Path.cwd()).as_posix()
        except ValueError:
            return plain.as_posix()
    return plain.as_posix()


# --- the columns nothing accounts for ---------------------------------------------

# How many of the columns resting on a hole are named before the rest are counted.
_RESTING_NAMED: Final[int] = 6


def _holes_check(document: dict[str, Any], *, asked: bool) -> Check:
    """Return whether the record accounts for every column its numbers rest on.

    **A hole is an input no check here can hold.** The holes section (section
    7.1) names each column the model cannot account for, and the record
    carries it by name only: its values reach no digest, so whatever they
    were read or computed from -- a file joined after ``collect()``, a write
    straight into the frame's query plan, a calculation on another frame --
    is on no line of this report, and an edit to it moves the numbers with
    every file in hand still agreeing. Agreement over the files given would
    then say more than was checked, so the line holds the question open, as
    the modules check does for code loaded by path, naming each hole, its
    reason and the columns that rest on it. Every reason holds it open: each says the
    record lacks what made the column's values.

    Asked where the reviewer names any of the run's inputs -- the model, its
    policy data or its assumption files -- since that is the question a hole
    bears on. A results file held alone is asked only whether it is the file
    the run wrote, which a hole does not touch. An empty section agrees: it
    is the claim that every column is a recorded calculation, a column of
    the book or a column injected at a known line.
    """
    stated = document.get("holes")
    if not isinstance(stated, list):
        return _check(
            _HOLES,
            "indeterminate" if asked else "not_asked",
            "The audit file carries no holes section, so nothing in it says "
            "whether the model accounts for every column its numbers rest on. "
            "Export the model again to record one.",
        )
    holes = [
        (str(entry["column"]), str(entry.get("reason") or "unrecorded"))
        for entry in stated
        if isinstance(entry, dict) and isinstance(entry.get("column"), str)
    ]
    if not holes:
        return _check(
            _HOLES,
            "agree" if asked else "not_asked",
            (
                "The audit file lists no column the model cannot account for: "
                "every column it holds is a calculation it recorded, a column "
                "of its book or a column injected at a known line (section 7.1)."
            )
            if asked
            else "No model file, model points file or assumption file was given. "
            "The audit file lists no column the model cannot account for.",
        )
    resting = _columns_resting_on(document, {column for column, _ in holes})
    named = "; ".join(
        f"{column} ({reason}{_resting_said(resting.get(column, []))})"
        for column, reason in holes
    )
    count = "one column" if len(holes) == 1 else f"{len(holes)} columns"
    if not asked:
        return _check(
            _HOLES,
            "not_asked",
            "No model file, model points file or assumption file was given. "
            f"For information, the audit file lists {count} the model cannot "
            f"account for: {named}. They bear on whether the inputs in hand "
            "are the run's, which was not asked.",
        )
    return _check(
        _HOLES,
        "indeterminate",
        f"The audit file lists {count} the model cannot account for: {named}. "
        "The record carries each by name only, so what its values were read or "
        "computed from is on no line here -- a file joined after collect(), a "
        "write straight into the frame's query plan, a calculation on another "
        "frame -- and an edit to it would move these numbers with every file "
        "given still "
        "agreeing. It could not be checked. af.graph.holes() names the move "
        "that records each column, so the record holds it and this line can "
        "hold it.",
    )


def _columns_resting_on(
    document: dict[str, Any], holes: set[str]
) -> dict[str, list[str]]:
    """Return, for each hole, the finished columns whose values rest on it.

    Read back along ``reads`` from every hole node to the nodes the finished
    frame holds, each column named once in the document's node order.
    """
    nodes = [node for node in document.get("nodes") or () if isinstance(node, dict)]
    readers: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        for read in node.get("reads") or ():
            readers.setdefault(str(read), []).append(node)
    order = {id(node): at for at, node in enumerate(nodes)}
    resting: dict[str, list[str]] = {}
    for hole in nodes:
        column = hole.get("column")
        if hole.get("kind") != "hole" or column not in holes:
            continue
        seen: dict[int, dict[str, Any]] = {}
        frontier = list(readers.get(str(hole.get("id")), ()))
        while frontier:
            node = frontier.pop()
            if id(node) in seen:
                continue
            seen[id(node)] = node
            frontier.extend(readers.get(str(node.get("id")), ()))
        found = resting.setdefault(str(column), [])
        for node in sorted(seen.values(), key=lambda one: order[id(one)]):
            name = node.get("column")
            if (
                node.get("in_final_schema")
                and isinstance(name, str)
                and name not in found
                and name != column
            ):
                found.append(name)
    return resting


def _resting_said(columns: list[str]) -> str:
    """Return the columns resting on a hole as a phrase, the first few named."""
    if not columns:
        return ""
    named = columns[:_RESTING_NAMED]
    more = len(columns) - len(named)
    if more:
        return f"; {', '.join(named)} and {more} more rest on it"
    if len(named) == 1:
        return f"; {named[0]} rests on it"
    return f"; {', '.join(named[:-1])} and {named[-1]} rest on it"


# --- the assumption tables -------------------------------------------------------

# The files a table may be held in, by the suffix the reader takes them under.
_TABLE_SUFFIXES: Final[tuple[str, ...]] = (".parquet", ".csv")


@dataclass(frozen=True, slots=True)
class _Located:
    """Where a recorded table was looked for, and what was found there."""

    files: tuple[Path, ...]
    how: str


def _table_checks(
    document: dict[str, Any], given: Sequence[Path | str] | None
) -> tuple[Check, ...]:
    """Return one line per table the audit file records, held against a file.

    Each table is found among what was given, read through its recorded
    roles and fingerprinted as ``Table.fingerprint()`` fingerprints it, so
    two loads of one set of rates agree however the file was laid out, and
    a moved rate does not. A file named outright that names no table the
    audit file records is a line of its own: the reviewer asked for it to be
    checked, and a silent pass over it would say it had been.
    """
    if given is None:
        return (_check(_TABLES, "not_asked", "No assumption files were given."),)
    named, files, directories = _assumption_inputs(given)
    entries = _recorded_of_kind(document, "table")
    joins = _recorded_of_kind(document, "join")
    recorded_names = {entry["name"] for entry in (*entries, *joins)}
    unknown = sorted(set(named) - recorded_names)
    if unknown:
        msg = (
            f"{', '.join(unknown)} names no table the audit file records, so "
            "NAME=FILE has nothing to hold the file against. The tables it "
            f"records: {', '.join(sorted(recorded_names)) or 'none'}."
        )
        raise ValueError(msg)
    checks: list[Check] = []
    if not entries and not joins:
        # Nothing recorded is nothing to check, which is not a question left
        # open: the documented command over a directory passes on a model
        # that reads no table. A file named outright still has a line of its
        # own below, since the reviewer asked for it to be checked.
        checks.append(
            _check(
                _TABLES,
                "agree",
                "The audit file records no assumption table and no join: the "
                "model it is an account of read none through the frame, so "
                "there is nothing among the files given to hold against it.",
            )
        )
    used: set[Path] = set()
    for entry in entries:
        located = _locate(entry, named, files, directories)
        used.update(located.files)
        checks.append(_table_against(entry, located))
    for entry in joins:
        check, found = _join_against(entry, named, files, directories)
        used.update(found)
        checks.append(check)
    checks.extend(
        Check(
            name=_TABLES,
            against=_TABLES,
            outcome="indeterminate",
            detail=(
                f"{file.name} was given and names no table the audit file "
                f"records ({', '.join(sorted(recorded_names))}), so it was not "
                "checked. Name the table it holds as NAME=FILE."
                if recorded_names
                else f"{file.name} was given, and the audit file records no "
                "assumption table or join for it to be one of, so it was not "
                "checked."
            ),
        )
        for file in files
        if file not in used
    )
    return tuple(checks)


def _recorded_of_kind(document: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Return the audit file's assumption entries of one kind that carry a name."""
    return [
        entry
        for entry in document.get("assumptions") or ()
        if isinstance(entry, dict)
        and entry.get("kind") == kind
        and isinstance(entry.get("name"), str)
    ]


def _join_against(
    entry: Mapping[str, Any],
    named: Mapping[str, Path],
    files: Sequence[Path],
    directories: Sequence[Path],
) -> tuple[Check, set[Path]]:
    """Return one recorded join's right side held against the files given.

    **A join's right side is a frame the model handed over**, so the record
    names its content and no file: ``pl.read_parquet`` returns a frame, and
    nothing in it says where it came from. It is held as the producer
    fingerprinted it -- every column, in name order, rows sorted by them --
    against the file named for it as ``NAME=FILE``, or else against each
    Parquet or CSV file given and each in a directory given. A file that
    reads as it agrees. Where none does, the question stays open rather than
    failing: a frame filtered or derived in code before the join and a file
    edited since read alike from here, exactly as for a table built from a
    frame, and a reviewer told every file agrees would have been told
    something nobody checked.
    """
    name: str = entry["name"]
    against = f"assumptions[name={name}].fingerprint"
    stated = entry.get("fingerprint")
    holding = _join_columns(entry)
    what = f"Join {name}, the right side of a join the model made{holding}"
    if name in named:
        candidates = [named[name]]
        how = f"named for it as {name}=FILE"
    else:
        candidates = sorted(
            {
                *(file for file in files if file.suffix in _TABLE_SUFFIXES),
                *(
                    path.resolve()
                    for directory in directories
                    for path in directory.iterdir()
                    if path.is_file() and path.suffix in _TABLE_SUFFIXES
                ),
            }
        )
        how = "by its content among the files given"
    read = {file: _join_fingerprint_of(file) for file in candidates}
    matched = [file for file, taken in read.items() if taken == stated]
    if matched:
        file = matched[0]
        return (
            Check(
                name=_TABLES,
                against=against,
                outcome="agree",
                detail=(
                    f"{what}: {file.name}, found {how}, reads as {stated}, the "
                    "fingerprint the audit file records."
                ),
            ),
            {file},
        )
    if name in named:
        (file,) = candidates
        taken = read[file]
        reads_as = (
            f"reads as {taken}" if taken is not None else "cannot be read as a frame"
        )
        detail = (
            f"{what}: {file.name}, named for it as {name}=FILE, {reads_as}, and "
            f"the audit file records {stated}. The model handed the join a "
            "frame, and the audit file names no file it was read from, so rows "
            "filtered or values derived in code before the join and an edit to "
            "the file since read alike from here. Check the model's code that "
            "built the frame."
        )
        return Check(
            name=_TABLES, against=against, outcome="indeterminate", detail=detail
        ), {file}
    detail = (
        f"{what}: no file given reads as {stated}, the fingerprint the audit "
        f"file records ({len(candidates)} looked at). The model handed the join "
        "a frame, and the audit file names no file it was read from, so it "
        "could not be checked: the file it was read from has changed since, "
        "or the model filtered or derived the frame in code. Name the file as "
        f"{name}=FILE to hold it against the join."
    )
    return Check(
        name=_TABLES, against=against, outcome="indeterminate", detail=detail
    ), set()


def _join_columns(entry: Mapping[str, Any]) -> str:
    """Return the columns a join's inlined right side holds, as a phrase."""
    payload = entry.get("payload")
    columns = payload.get("columns") if isinstance(payload, dict) else None
    names = [
        str(column["name"])
        for column in columns or ()
        if isinstance(column, dict) and "name" in column
    ]
    return f" (holding {', '.join(names)})" if names else ""


def _join_fingerprint_of(file: Path) -> str | None:
    """Return a file's frame fingerprinted as a join's right side is, or None.

    Every column, in name order, the rows sorted by them, hashed by the
    content primitive the producer took the join's identity with. None where
    the file cannot be read as a frame at all.
    """
    from gaspatchio.assumptions._utils import _materialise  # noqa: PLC0415 -- cycle

    try:
        frame = _materialise(file)
        columns = sorted(frame.columns)
        return content_sha_of(frame.select(columns).sort(columns))
    except (pl.exceptions.PolarsError, ValueError, OSError):
        return None


def _assumption_inputs(
    given: Sequence[Path | str],
) -> tuple[dict[str, Path], list[Path], list[Path]]:
    """Return what was given, sorted into named files, files and directories.

    ``NAME=FILE`` is read as a name only where the text is not itself a path
    that exists, so a file whose name holds an ``=`` is still a file.
    """
    named: dict[str, Path] = {}
    files: list[Path] = []
    directories: list[Path] = []
    for item in given:
        text = str(item)
        if isinstance(item, str) and "=" in text and not Path(text).exists():
            name, _, where = text.partition("=")
            path = Path(where)
            if not path.is_file():
                msg = (
                    f"{where} names no file, so table {name} has nothing to be "
                    "held against. Name the file the table was read from."
                )
                raise OSError(msg)
            named[name] = path.resolve()
            continue
        path = Path(text)
        if path.is_dir():
            directories.append(path.resolve())
        elif path.is_file():
            files.append(path.resolve())
        else:
            msg = (
                f"{text} names no file or directory, so there is nothing to hold "
                "the audit file's tables against. Name the assumption files, or "
                "the directory that holds them."
            )
            raise OSError(msg)
    return named, files, directories


def _locate(
    entry: Mapping[str, Any],
    named: Mapping[str, Path],
    files: Sequence[Path],
    directories: Sequence[Path],
) -> _Located:
    """Return the files that could be ``entry``'s, and how they were sought.

    A file named for the table is the one. Otherwise a table the record says
    was read from a file is sought by that file -- its recorded path inside
    each directory given, or its name among the files and in the
    directories -- and any other table by its own name with each suffix a
    table is read from. The recorded path is never opened as it stands.
    """
    name: str = entry["name"]
    if name in named:
        return _Located((named[name],), f"named for it as {name}=FILE")
    recorded = entry.get("source_file")
    if isinstance(recorded, str):
        wanted = {PurePosixPath(recorded).name}
        inside = [directory / recorded for directory in directories]
        how = f"by the file the audit file records it was read from, {recorded}"
    else:
        wanted = {f"{name}{suffix}" for suffix in _TABLE_SUFFIXES}
        inside = []
        how = "by its name"
    found = {
        path.resolve()
        for path in [
            *inside,
            *(directory / file for directory in directories for file in wanted),
        ]
        if path.is_file()
    } | {file for file in files if file.name in wanted}
    return _Located(tuple(sorted(found)), how)


def _table_against(entry: Mapping[str, Any], located: _Located) -> Check:
    """Return one recorded table held against the file found for it."""
    name: str = entry["name"]
    against = f"assumptions[name={name}].fingerprint"
    stated: object = entry.get("fingerprint")
    recorded = entry.get("source_file")
    unread = _before_reading(entry, located, against)
    if unread is not None:
        return unread
    (file,) = located.files
    roles = _recorded_roles(entry)
    if isinstance(roles, str):
        return Check(
            name=_TABLES,
            against=against,
            outcome="indeterminate",
            detail=f"Table {name}: {roles} So {file.name} cannot be read as it.",
        )
    taken = _table_fingerprint_of(file, name, roles)
    if isinstance(taken, _CannotRead):
        return Check(
            name=_TABLES,
            against=against,
            outcome="indeterminate",
            detail=f"Table {name}: {taken.reason}",
        )
    where = f"{file.name}, found {located.how},"
    if taken == stated:
        return Check(
            name=_TABLES,
            against=against,
            outcome="agree",
            detail=(
                f"Table {name}: {where} reads as {taken}, the fingerprint the "
                "audit file records."
            ),
        )
    if not isinstance(recorded, str):
        return Check(
            name=_TABLES,
            against=against,
            outcome="indeterminate",
            detail=(
                f"Table {name}: {where} reads as {taken}, and the audit file "
                f"records {stated}. {_why_a_frame_cannot_decide(entry)}"
            ),
        )
    return Check(
        name=_TABLES,
        against=against,
        outcome="disagree",
        detail=(
            f"Table {name}: {where} reads as {taken}, and the audit file records "
            f"{stated}: the table was a plain read of that file, so its values "
            "are not the ones the model was run against."
        ),
    )


def _before_reading(
    entry: Mapping[str, Any], located: _Located, against: str
) -> Check | None:
    """Return the line for a table no file can be read as, or None to read one.

    A table whose recipe reshaped what it read is not a plain read of any
    file, so it is never read back from one -- a reshaped table must not read
    as an edited one. Otherwise the file found for it is read, unless none
    was, or more than one could be.
    """
    name: str = entry["name"]
    shaped = _shaped_by(entry)
    if shaped:
        return Check(
            name=_TABLES,
            against=against,
            outcome="indeterminate",
            detail=(
                f"Table {name}: its recipe reshaped what it read -- {shaped} -- "
                "so the table is not a plain read of any file, and no file can "
                "be read back as it: naming one as NAME=FILE names the file, "
                "not the recipe, and would not help. The values the audit file "
                "inlines are what identify it; gspio validate --deep re-hashes "
                "them."
            ),
        )
    if not located.files:
        return Check(
            name=_TABLES, against=against, **_not_found(name, entry.get("source_file"))
        )
    if len(located.files) != 1:
        return Check(
            name=_TABLES,
            against=against,
            outcome="indeterminate",
            detail=(
                f"Table {name}: {' and '.join(str(f) for f in located.files)} "
                f"could each be its file, sought {located.how}. Name the one it "
                f"was read from as {name}=FILE."
            ),
        )
    return None


def _why_a_frame_cannot_decide(entry: Mapping[str, Any]) -> str:
    """Return why a difference against a table built from a frame decides nothing.

    The model handed the table a frame, so nothing records what that frame
    was: a filter or a derivation in code before the table was built, and an
    edit to the file since, read exactly alike from here. Agreement is still
    agreement -- the file holds the table's values -- but a difference is a
    question for the model's own code.
    """
    if "source_file" in entry:
        handed = (
            "The audit file records that the model handed this table a frame "
            "rather than a file's path"
        )
    else:
        handed = "The audit file does not say what this table was read from"
    return (
        f"{handed}, so nothing records that the frame was this file as it "
        "stands: rows filtered or values derived in code before the table was "
        "built, and an edit to the file since, read alike, and naming the file "
        "as NAME=FILE does not tell them apart. Hand Table the file's path, so "
        "the audit file names it and a difference decides, or check the "
        "model's code that built the frame."
    )


def _shaped_by(entry: Mapping[str, Any]) -> str:
    """Return the recipe's reshaping steps in words, or nothing where it has none."""
    steps = entry.get("shaped_by")
    if not isinstance(steps, list):
        return ""
    return "; ".join(_step_in_words(step) for step in steps if isinstance(step, dict))


def _step_in_words(step: Mapping[str, Any]) -> str:
    """Return one reshaping step as the phrase a reader sees."""
    kind = step.get("step")
    column = step.get("column")
    source = step.get("from")
    phrases = {
        "renamed": f"{column} renamed from {source}",
        "cast": f"{column} cast to {step.get('to')}",
        "melted": f"{column} melted from the columns "
        + ", ".join(str(item) for item in source or ()),
        "set": f"{column} set to a constant in code",
        "computed": f"{column} computed in code",
        "shocked": f"{column} shocked ({step.get('by')})",
        "stacked": f"one copy per scenario stacked under {column}",
    }
    return phrases.get(str(kind), f"{column} built by {kind}")


def _not_found(name: str, recorded: object) -> dict[str, Any]:
    """Return the outcome and detail for a table no file was found for."""
    if recorded is None:
        return {
            "outcome": "not_asked",
            "detail": (
                f"No file was given for table {name}. The audit file records "
                "that the model handed it a frame rather than a file's path, and no "
                f"file named for it was given ({name}.parquet or {name}.csv), so "
                "there is no file to hold it against. If it was read from a "
                f"file, name it as {name}=FILE."
            ),
        }
    if isinstance(recorded, str):
        return {
            "outcome": "indeterminate",
            "detail": (
                f"Table {name} was not found: the audit file records it read "
                f"from {recorded}, and no file of that name is among the files "
                "and directories given, so it was not checked."
            ),
        }
    return {
        "outcome": "indeterminate",
        "detail": (
            f"Table {name} was not found: no file named for it was given "
            f"({name}.parquet or {name}.csv), and the audit file does not say "
            "whether it was read from a file, so it was not checked. Name its "
            f"file as {name}=FILE."
        ),
    }


@dataclass(frozen=True, slots=True)
class _Roles:
    """The key columns and the answer column a recorded table was keyed by."""

    keys: tuple[str, ...]
    text_keys: frozenset[str]
    value: str


def _recorded_roles(entry: Mapping[str, Any]) -> _Roles | str:
    """Return the roles a table's entry states, or why it states none.

    The payload is the table's processed frame, so its ``columns`` less the
    ``value`` are the columns a file of the table is keyed by, in the order a
    lookup binds them; a key the payload carries as text is read as text, as
    a rebuilt table keeps one. A payload left out for its size states the
    same three members as ``roles`` in its stand-in. An entry stating
    neither cannot be read from a file: nobody has said the table's columns.
    """
    payload = entry.get("payload")
    inlined = isinstance(payload, dict) and "omitted" not in payload
    stated = (
        payload
        if inlined
        else payload.get("roles")
        if isinstance(payload, dict)
        else None
    )
    if not isinstance(stated, dict):
        reason = payload.get("omitted") if isinstance(payload, dict) else None
        return (
            "the audit file carries its fingerprint and not its values "
            f"(payload omitted{f' for {reason}' if reason else ''}), and no "
            "roles beside them, so it does not say which columns the table is "
            "keyed by and answers with. Export the model again to record them."
        )
    value = stated.get("value")
    columns = [
        column
        for column in stated.get("columns") or ()
        if isinstance(column, dict) and isinstance(column.get("name"), str)
    ]
    keys = [str(column["name"]) for column in columns if column["name"] != value]
    if not keys:
        dimensions = stated.get("dimensions")
        keys = [str(key) for key in dimensions or () if isinstance(key, str)]
    if not keys or not isinstance(value, str):
        return (
            "the audit file does not state its key columns and its value "
            "column, so the columns a file of it holds are not known."
        )
    text = {column["name"] for column in columns if column.get("dtype") == "str"}
    return _Roles(
        keys=tuple(keys),
        text_keys=frozenset(key for key in keys if key in text),
        value=value,
    )


@dataclass(frozen=True, slots=True)
class _CannotRead:
    """Why a file found for a table cannot be read as that table."""

    reason: str


def _table_fingerprint_of(file: Path, name: str, roles: _Roles) -> str | _CannotRead:
    """Return a file's fingerprint read as the table ``roles`` describe.

    The reader ``Table`` reads a file with, and then the steps it takes, so a
    file the table was read from reaches the fingerprint the table carried.
    A file that does not hold the columns the record says the table was keyed
    by is one the model shaped in code -- renamed, melted, computed -- and
    the re-read cannot reach the table from it; that comes back as the
    reason, for the caller to report as a check that cannot be made.
    """
    # The assumptions package is reached from inside the call: importing it
    # loads the authoring surface, which imports this package.
    from gaspatchio.assumptions._dimensions import DataDimension  # noqa: PLC0415
    from gaspatchio.assumptions._processing import (  # noqa: PLC0415
        content_fingerprint_of,
    )
    from gaspatchio.assumptions._utils import _materialise  # noqa: PLC0415

    try:
        frame = _materialise(file)
    except (pl.exceptions.PolarsError, ValueError) as refused:
        said = str(refused).strip().splitlines()
        reason = said[0] if said else type(refused).__name__
        msg = (
            f"{file.name} could not be read as an assumption table, as Parquet "
            f"or CSV ({reason}). Name the file table {name} was read from."
        )
        raise ValueError(msg) from refused
    missing = [
        column for column in (*roles.keys, roles.value) if column not in frame.columns
    ]
    if missing:
        return _CannotRead(
            f"{file.name} does not hold "
            f"{', '.join(missing)}, which the audit file records the table "
            "keyed by or answering with: the model shaped the table in code "
            "from what it read (renamed, melted or computed columns), and the "
            "file cannot be read as the table it became. Check it by the "
            "values the audit file inlines instead."
        )
    dimensions: dict[str, str | DataDimension] = {
        key: DataDimension(column=key, dtype=pl.String())
        if key in roles.text_keys
        else key
        for key in roles.keys
    }
    try:
        return content_fingerprint_of(frame, dimensions, roles.value)
    except (pl.exceptions.PolarsError, ValueError) as refused:
        said = str(refused).strip().splitlines()
        reason = said[0] if said else type(refused).__name__
        return _CannotRead(
            f"{file.name} cannot be read as the table the audit "
            f"file records ({reason})."
        )
