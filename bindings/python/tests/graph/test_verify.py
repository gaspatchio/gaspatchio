# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Whether the files in hand are the ones an audit file records.

A reviewer holding an audit file and a folder of results asks first whether
the results are the ones the model in front of them produced. The audit file
holds the evidence -- its own seal, the sha256 of the results file the run
wrote, the digest of the policy data, the model source's sha256 and the
commit it sat at -- and ``verify_artifact`` reads it back, one check per
member, each with one of four outcomes.

Every audit file here is a real one: the one-line model committed to a
temporary git repository, run from Python, its results written with a result
manifest, and exported with the version block ``ModelIdentity.of`` reads off
the files.
"""

from __future__ import annotations

import doctest
import io
import json
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio.engines.protocol import ResultManifest, write_with_manifest
from gaspatchio.frame.graph import (
    DOCUMENT_DIGEST_FIELD,
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    VerificationReport,
    document_digest_of,
    verify_artifact,
)
from tests.graph.test_model_identity_of import _a_checkout_at, _run_from_python
from tests.graph.test_relative_paths import _git

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class Filing:
    """One run's files, as a reviewer would be handed them."""

    repository: Path
    model: Path
    points: Path
    results: Path
    audit: Path
    document: dict[str, Any]


def _manifest_for(document: dict[str, Any], frame: pl.DataFrame) -> ResultManifest:
    """Return a manifest saying these results came from this model and this book."""
    return ResultManifest(
        scope="final-schema",
        columns={column: column for column in frame.columns},
        dtypes={column: str(dtype) for column, dtype in frame.schema.items()},
        row_identity=None,
        graph_fingerprint=document["graph_fingerprint"],
        inputs_digest=document["book"]["digest"],
        producer="polars",
        versions={},
    )


def filed(
    tmp_path: Path,
    *,
    manifest: bool = True,
    name_the_results: bool = True,
    name_the_points: bool = True,
) -> Filing:
    """Run the model, write its results and export the audit file that records them.

    The results go outside the checkout, as a valuation run's output usually
    does, so writing them leaves the tree the block reports on clean.
    """
    repository = tmp_path / "repository"
    model, points = _a_checkout_at(repository)
    out = tmp_path / "out"
    out.mkdir()
    frame, result = _run_from_python(model, points)
    exporter = GraphExporter(frame)
    results = out / "results.parquet"
    if manifest:
        unnamed = json.loads(exporter.export(result))
        write_with_manifest(result, _manifest_for(unnamed, result), results)
    else:
        result.write_parquet(results)
    identity = ModelIdentity.of(
        model,
        model_points=points if name_the_points else None,
        results=results if name_the_results else None,
    )
    document = json.loads(exporter.export(result, GraphExportConfig(model=identity)))
    audit = out / "model.audit.json"
    audit.write_text(json.dumps(document, indent=2))
    return Filing(repository, model, points, results, audit, document)


def everything(filing: Filing) -> VerificationReport:
    """Verify the audit file against every file the run was given and wrote."""
    return verify_artifact(
        filing.audit,
        results=filing.results,
        model_points=filing.points,
        model=filing.model,
    )


def outcomes(report: VerificationReport) -> dict[str, str]:
    """Return each check's outcome, by the check's name."""
    return {check.name: check.outcome for check in report.checks}


def detail(report: VerificationReport, name: str) -> str:
    """Return what one check said."""
    return next(check.detail for check in report.checks if check.name == name)


def _resealed(document: dict[str, Any]) -> dict[str, Any]:
    """Return an edited document sealed again, as a producer writing it would.

    So that a check reading the edited member is the only one that moves:
    the seal is the check that catches an edit made after the fact, and here
    the edit stands in for a document written that way.
    """
    edited = {k: v for k, v in document.items() if k != DOCUMENT_DIGEST_FIELD}
    return {**edited, DOCUMENT_DIGEST_FIELD: document_digest_of(edited)}


def _flip_one_byte(path: Path) -> None:
    """Change one byte in the middle of a file, as corruption or an edit would."""
    held = bytearray(path.read_bytes())
    held[len(held) // 2] ^= 0xFF
    path.write_bytes(bytes(held))


# --- everything agrees -------------------------------------------------------


def test_every_file_the_run_used_agrees_with_the_audit_file(tmp_path: Path) -> None:
    """The seal, the results and their manifest, the book, the source, the commit."""
    filing = filed(tmp_path)

    report = everything(filing)

    assert outcomes(report) == {
        "seal": "agree",
        "results": "agree",
        "results_manifest": "agree",
        "book": "agree",
        "model_points": "not_asked",
        "source_sha": "agree",
        "modules": "agree",
        "scenarios": "not_asked",
        "graph": "agree",
        "holes": "agree",
        "git": "agree",
        "versions": "agree",
        "assumptions": "not_asked",
    }
    assert report.verdict == "agree"


def test_the_checks_come_in_one_order_with_what_each_is_held_against(
    tmp_path: Path,
) -> None:
    """A reader of a stored report finds each check where the last one put it."""
    report = everything(filed(tmp_path))

    assert [(check.name, check.against) for check in report.checks] == [
        ("seal", "document_digest"),
        ("results", "model.results.fingerprint"),
        ("results_manifest", "graph_fingerprint, book.digest"),
        ("book", "book.digest"),
        ("model_points", "model.model_points.fingerprint"),
        ("source_sha", "model.source_sha"),
        ("modules", "model.modules"),
        ("scenarios", "model.scenarios"),
        ("graph", "graph_fingerprint"),
        ("holes", "holes"),
        ("git", "model.git.commit"),
        ("versions", "producer.versions"),
        ("assumptions", "assumptions"),
    ]


def test_only_the_audit_file_asks_for_the_seal_and_the_versions(
    tmp_path: Path,
) -> None:
    """A check whose input was not given is listed as such and moves nothing.

    The seal and the library versions need no file: one is read off the
    document, the other held against this process.
    """
    filing = filed(tmp_path)

    report = verify_artifact(filing.audit)

    assert outcomes(report) == {
        "seal": "agree",
        "results": "not_asked",
        "results_manifest": "not_asked",
        "book": "not_asked",
        "model_points": "not_asked",
        "source_sha": "not_asked",
        "modules": "not_asked",
        "scenarios": "not_asked",
        "graph": "not_asked",
        "holes": "not_asked",
        "git": "not_asked",
        "versions": "agree",
        "assumptions": "not_asked",
    }
    assert report.verdict == "agree"


# --- the results file ----------------------------------------------------------


def test_one_flipped_byte_in_the_results_file_differs(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    recorded = filing.document["model"]["results"]["fingerprint"]
    _flip_one_byte(filing.results)

    report = everything(filing)

    assert outcomes(report)["results"] == "disagree"
    assert report.verdict == "disagree"
    assert recorded in detail(report, "results")


def test_results_the_audit_file_records_nothing_for_are_not_checked(
    tmp_path: Path,
) -> None:
    """An audit file naming no results file cannot vouch for one.

    The file's own manifest agrees here -- it says this model over this book
    produced it -- and the question stays open: nothing ties the file to this
    audit file, which is what the results check asks.
    """
    filing = filed(tmp_path, name_the_results=False)

    report = verify_artifact(filing.audit, results=filing.results)

    assert "results" not in filing.document["model"]
    assert outcomes(report)["results"] == "indeterminate"
    assert outcomes(report)["results_manifest"] == "agree"
    assert "model.results" in detail(report, "results")
    assert "nothing ties it to this audit file" in detail(report, "results")
    assert report.verdict == "indeterminate"


def test_a_results_file_with_no_manifest_leaves_the_results_check_to_decide(
    tmp_path: Path,
) -> None:
    """A manifest adds evidence where the file carries one; none moves nothing."""
    filing = filed(tmp_path, manifest=False)

    report = verify_artifact(filing.audit, results=filing.results)

    assert outcomes(report)["results"] == "agree"
    assert outcomes(report)["results_manifest"] == "not_asked"
    assert detail(report, "results_manifest").startswith(
        "The file carries no result manifest"
    )
    assert report.verdict == "agree"


def test_a_manifest_is_held_to_the_fingerprint_where_the_book_has_no_digest(
    tmp_path: Path,
) -> None:
    """Evidence agrees or differs on what it can compare, and says what it could not."""
    filing = filed(tmp_path)
    document = json.loads(filing.audit.read_text())
    document["book"]["digest"] = {
        "omitted": "unavailable",
        "detail": "No book was handed to the export.",
    }

    report = verify_artifact(_resealed(document), results=filing.results)

    assert outcomes(report)["results_manifest"] == "agree"
    assert "states no digest of its book" in detail(report, "results_manifest")
    assert report.verdict == "agree"


def test_a_manifest_naming_another_model_differs(tmp_path: Path) -> None:
    """The file can match its recorded digest and still say it came from elsewhere."""
    filing = filed(tmp_path)
    result = pl.read_parquet(filing.results)
    other = {**filing.document, "graph_fingerprint": "sha256:" + "0" * 64}
    stray = filing.results.with_name("stray.parquet")
    write_with_manifest(result, _manifest_for(other, result), stray)

    report = verify_artifact(filing.audit, results=stray)

    assert outcomes(report)["results_manifest"] == "disagree"
    assert "sha256:" + "0" * 64 in detail(report, "results_manifest")
    assert filing.document["graph_fingerprint"] in detail(report, "results_manifest")


def _a_manifest_damaged(filing: Filing, damage: str, into: Path) -> Path:
    """Write the run's results again with one member of their manifest damaged."""
    result = pl.read_parquet(filing.results)
    metadata = _manifest_for(filing.document, result).to_metadata()
    key = "gaspatchio.graph_fingerprint"
    if damage == "stripped":
        del metadata[key]
    elif damage == "unparseable":
        metadata[key] = "{not json"
    else:
        metadata[key] = '["sha256:a list, where the fingerprint is text"]'
    damaged = into / f"{damage}.parquet"
    result.write_parquet(damaged, metadata=metadata)
    return damaged


@pytest.mark.parametrize("damage", ["stripped", "unparseable", "misshapen"])
def test_a_manifest_partly_there_disagrees_naming_the_damage(
    tmp_path: Path, damage: str
) -> None:
    """A manifest with a key gone or a value unreadable is damage, not absence.

    Only a file carrying no manifest at all has nothing to add. One carrying
    part of a manifest was written with one and has lost some of it, and a
    reader is told which member.
    """
    filing = filed(tmp_path)
    damaged = _a_manifest_damaged(filing, damage, tmp_path)

    report = verify_artifact(filing.audit, results=damaged)

    assert outcomes(report)["results_manifest"] == "disagree"
    assert "gaspatchio.graph_fingerprint" in detail(report, "results_manifest")


@pytest.mark.parametrize(
    ("member", "written"),
    [
        ("columns", '["a", "b"]'),
        ("dtypes", "7"),
        ("versions", "[" * 50 + "]" * 50),
        ("row_identity", '{"x": 1}'),
    ],
)
def test_a_manifest_member_of_the_wrong_shape_is_named_not_a_traceback(
    tmp_path: Path, member: str, written: str
) -> None:
    """A member parsing to a shape its writer never writes is damage, named on the line.

    It never reaches the version comparison, which read a list as a mapping
    and failed with a traceback.
    """
    filing = filed(tmp_path)
    result = pl.read_parquet(filing.results)
    metadata = _manifest_for(filing.document, result).to_metadata()
    metadata[f"gaspatchio.{member}"] = written
    damaged = tmp_path / "misshapen.parquet"
    result.write_parquet(damaged, metadata=metadata)

    report = verify_artifact(filing.audit, results=damaged)

    assert outcomes(report)["results_manifest"] == "disagree"
    assert f"gaspatchio.{member}" in detail(report, "results_manifest")
    assert "damaged" in detail(report, "results_manifest")


def test_a_manifest_over_a_book_crossed_with_scenarios_is_held_to_its_model(
    tmp_path: Path,
) -> None:
    """An engine handed the crossed book records another digest, by design.

    Crossed with a scenario axis, the rows an engine is handed carry a column
    the book does not hold, so its manifest digests those rows: the model
    fingerprint is still compared, and the book half is not asked, saying why.
    """
    from gaspatchio import ActuarialFrame
    from gaspatchio.engines.protocol import digest_of_inputs
    from gaspatchio.scenarios import with_scenarios

    frame = with_scenarios(
        ActuarialFrame(pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})),
        ["BASE", "UP"],
    )
    frame.total = frame.a + frame.b
    crossed = frame.collect()
    document = json.loads(GraphExporter(frame).export(crossed))
    handed = digest_of_inputs(crossed, ["a", "b", "scenario_id"])
    manifest = _manifest_for(
        {
            "graph_fingerprint": document["graph_fingerprint"],
            "book": {"digest": handed},
        },
        crossed,
    )
    results = tmp_path / "results.parquet"
    write_with_manifest(crossed, manifest, results)

    report = verify_artifact(document, results=results)

    assert manifest.inputs_digest != document["book"]["digest"]
    assert outcomes(report)["results_manifest"] == "agree"
    assert "scenario_id" in detail(report, "results_manifest")


def test_a_recorded_path_is_printed_and_never_opened(tmp_path: Path) -> None:
    """The file checked is the file named, wherever it has been moved to."""
    filing = filed(tmp_path)
    moved = tmp_path / "handed_over" / "q3_results.parquet"
    moved.parent.mkdir()
    shutil.move(filing.results, moved)

    report = verify_artifact(filing.audit, results=moved)

    assert outcomes(report)["results"] == "agree"
    assert filing.document["model"]["results"]["path"] in detail(report, "results")


# --- the policy data -----------------------------------------------------------


def test_other_model_points_differ_and_both_book_digests_are_named(
    tmp_path: Path,
) -> None:
    filing = filed(tmp_path)
    other = tmp_path / "other_points.parquet"
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [250_000.0]}).write_parquet(other)

    report = verify_artifact(filing.audit, model_points=other)

    assert outcomes(report)["book"] == "disagree"
    assert outcomes(report)["model_points"] == "not_asked"
    assert report.verdict == "disagree"
    assert filing.document["book"]["digest"] in detail(report, "book")
    taken = [
        word.strip(",.()")
        for word in detail(report, "book").split()
        if word.startswith("sha256:")
    ]
    assert len(set(taken)) == 2


def _rewritten(points: Path, into: Path, how: str) -> Path:
    """Write the book at ``points`` out again, one of the ways a pipeline does."""
    book = pl.read_parquet(points)
    if how == "re-encoded":
        written = into / "rewritten.parquet"
        book.write_parquet(written, compression="gzip")
    elif how == "as CSV":
        written = into / "rewritten.csv"
        book.write_csv(written)
    elif how == "with a column the model does not read":
        written = into / "rewritten.parquet"
        book.with_columns(pl.lit("unread").alias("branch")).write_parquet(written)
    else:
        written = into / "rewritten.parquet"
        book.with_columns(pl.col("sum_assured").cast(pl.Float32)).write_parquet(written)
    return written


@pytest.mark.parametrize(
    "how",
    [
        "re-encoded",
        "as CSV",
        "with a column the model does not read",
        "in a narrower type",
    ],
)
def test_the_same_book_in_another_file_agrees(tmp_path: Path, how: str) -> None:
    """The content decides, as it decides a comparison of two audit files.

    A book written out again is another file and the same policies, and a
    column the model does not read is no part of the book. The file stamp
    says so for information and moves nothing.
    """
    filing = filed(tmp_path)
    rewritten = _rewritten(filing.points, tmp_path, how)

    report = verify_artifact(filing.audit, model_points=rewritten)

    assert outcomes(report)["book"] == "agree"
    assert outcomes(report)["model_points"] == "not_asked"
    assert "not byte for byte" in detail(report, "model_points")
    assert report.verdict == "agree"


def test_the_same_file_says_so_beside_the_book(tmp_path: Path) -> None:
    filing = filed(tmp_path)

    report = verify_artifact(filing.audit, model_points=filing.points)

    assert outcomes(report)["model_points"] == "not_asked"
    assert "byte for byte the file" in detail(report, "model_points")
    assert "not byte for byte" not in detail(report, "model_points")


def _with_no_book_digest(document: dict[str, Any]) -> dict[str, Any]:
    """Return the document as one whose producer could not digest its book."""
    edited = json.loads(json.dumps(document))
    edited["book"]["digest"] = {
        "omitted": "unavailable",
        "detail": "No book was handed to the export.",
    }
    return _resealed(edited)


def test_with_no_book_digest_the_file_stamp_decides(tmp_path: Path) -> None:
    """Where the audit file states no book digest, the file's bytes decide."""
    filing = filed(tmp_path)
    document = _with_no_book_digest(filing.document)
    rewritten = _rewritten(filing.points, tmp_path, "re-encoded")

    same = verify_artifact(document, model_points=filing.points)
    other = verify_artifact(document, model_points=rewritten)

    assert outcomes(same)["book"] == "not_asked"
    assert outcomes(same)["model_points"] == "agree"
    assert same.verdict == "agree"
    assert outcomes(other)["model_points"] == "disagree"
    assert other.verdict == "disagree"


def test_with_neither_a_digest_nor_a_stamp_the_book_is_indeterminate(
    tmp_path: Path,
) -> None:
    filing = filed(tmp_path, name_the_points=False)
    document = _with_no_book_digest(filing.document)

    report = verify_artifact(document, model_points=filing.points)

    assert outcomes(report)["book"] == "indeterminate"
    assert outcomes(report)["model_points"] == "not_asked"
    assert report.verdict == "indeterminate"


def test_an_audit_file_naming_no_policy_data_file_asks_no_file_stamp(
    tmp_path: Path,
) -> None:
    """The book check decides; with no stamp recorded there are no bytes to name."""
    filing = filed(tmp_path, name_the_points=False)

    report = verify_artifact(filing.audit, model_points=filing.points)

    assert filing.document["model"]["model_points"] is None
    assert outcomes(report)["book"] == "agree"
    assert outcomes(report)["model_points"] == "not_asked"
    assert "names no model points file" in detail(report, "model_points")
    assert report.verdict == "agree"


def test_the_book_check_takes_the_digest_reading_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The book is held to its digest without reading the whole document again.

    The digest reading is the one ``validate_artifact(book=)`` makes. The
    schema and structure readings beside it answer whether the document is
    well formed, which the seal has already answered for this question, and
    on a large model they are most of the cost.
    """
    filing = filed(tmp_path)

    def the_schema_reading(*_: object) -> list[object]:
        msg = "the book check read the document against its schema"
        raise AssertionError(msg)

    monkeypatch.setattr(
        "gaspatchio.frame.graph.validate._schema_findings", the_schema_reading
    )

    report = verify_artifact(filing.audit, model_points=filing.points)

    assert outcomes(report)["book"] == "agree"


def test_policy_data_that_cannot_be_read_is_refused_by_name(tmp_path: Path) -> None:
    """A file that is not a table is not a finding against the model."""
    filing = filed(tmp_path)
    broken = tmp_path / "broken.parquet"
    broken.write_bytes(b"not a parquet file")

    with pytest.raises(ValueError, match=r"broken\.parquet"):
        verify_artifact(filing.audit, model_points=broken)


# --- the model source and its revision -----------------------------------------


def test_an_edited_model_source_differs_on_source_sha(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    filing.model.write_text(filing.model.read_text().replace("0.00123", "0.00124"))

    report = verify_artifact(filing.audit, model=filing.model)

    assert outcomes(report)["source_sha"] == "disagree"
    assert report.verdict == "disagree"
    assert filing.document["model"]["source_sha"] in detail(report, "source_sha")


def test_a_checkout_at_another_commit_differs_on_the_revision(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    (filing.repository / "README.md").write_text("A later commit.\n")
    _git(filing.repository, "add", "README.md")
    _git(
        filing.repository,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--message",
        "a later commit",
    )

    report = verify_artifact(filing.audit, model=filing.model)

    assert outcomes(report)["git"] == "disagree"
    assert outcomes(report)["source_sha"] == "agree"
    assert filing.document["model"]["git"]["commit"] in detail(report, "git")


def test_a_commit_from_a_dirty_tree_leaves_the_source_check_to_carry_it(
    tmp_path: Path,
) -> None:
    """The recorded state is said, with what it means, and it moves no status.

    git counts an untracked file as a change to the tree, so a results file
    written into the repository makes an export dirty: a dirty record is
    common, says the commit alone does not hold the model as it ran, and
    leaves source_sha to pin the model file itself.
    """
    filing = filed(tmp_path)
    document = json.loads(filing.audit.read_text())
    document["model"]["git"]["dirty"] = True

    report = verify_artifact(
        _resealed(document), model=filing.model, model_points=filing.points
    )

    said = detail(report, "git")
    assert outcomes(report)["git"] == "agree"
    assert report.verdict == "agree"
    assert "records the tree as dirty" in said
    assert "untracked" in said
    assert "moves no exit status" in said
    assert "source_sha pins the model file itself" in said


def test_a_commit_from_a_clean_tree_says_so_and_what_pins_the_source(
    tmp_path: Path,
) -> None:
    filing = filed(tmp_path)

    said = detail(verify_artifact(filing.audit, model=filing.model), "git")

    assert "records the tree as clean" in said
    assert "source_sha pins the model file itself" in said


def test_a_model_outside_a_checkout_asks_no_revision(tmp_path: Path) -> None:
    """A copy of the model held outside git is checked by its bytes alone."""
    filing = filed(tmp_path)
    copy = tmp_path / "copy" / "model.py"
    copy.parent.mkdir()
    shutil.copy(filing.model, copy)

    report = verify_artifact(filing.audit, model=copy, model_points=filing.points)

    assert outcomes(report)["source_sha"] == "agree"
    assert outcomes(report)["git"] == "not_asked"
    assert report.verdict == "agree"


def test_an_audit_file_recording_no_revision_asks_none_of_a_checkout(
    tmp_path: Path,
) -> None:
    """The revision adds evidence where one is recorded; the source check decides."""
    filing = filed(tmp_path)
    document = {**filing.document, "model": {**filing.document["model"], "git": None}}

    report = verify_artifact(
        _resealed(document), model=filing.model, model_points=filing.points
    )

    assert outcomes(report)["git"] == "not_asked"
    assert "model.git is null" in detail(report, "git")
    assert outcomes(report)["source_sha"] == "agree"
    assert report.verdict == "agree"


def test_a_copy_outside_a_checkout_recording_no_revision_says_both(
    tmp_path: Path,
) -> None:
    """Where both conditions fail, the detail names both."""
    filing = filed(tmp_path)
    document = {**filing.document, "model": {**filing.document["model"], "git": None}}
    copy = tmp_path / "copy" / "model.py"
    copy.parent.mkdir()
    shutil.copy(filing.model, copy)

    report = verify_artifact(_resealed(document), model=copy)

    assert outcomes(report)["git"] == "not_asked"
    assert "model.git is null" in detail(report, "git")
    assert "no git HEAD" in detail(report, "git")


# --- the audit file itself -------------------------------------------------------


def test_an_audit_file_edited_after_it_was_written_differs_on_the_seal(
    tmp_path: Path,
) -> None:
    filing = filed(tmp_path)
    document = json.loads(filing.audit.read_text())
    document["model"]["label"] = "the model we meant"
    filing.audit.write_text(json.dumps(document))

    report = verify_artifact(filing.audit)

    assert outcomes(report)["seal"] == "disagree"
    assert report.verdict == "disagree"


def test_a_seal_taken_again_over_an_edit_shows_only_that_nothing_moved_since(
    tmp_path: Path,
) -> None:
    """A seal is tamper-evidence, not a signature, and says so when it agrees.

    Whoever edits a file can seal it again, and the seal then agrees: what it
    shows is that the document has not changed since it was sealed, which is
    evidence of which file this is only against a digest kept elsewhere.
    """
    filing = filed(tmp_path)
    edited = json.loads(filing.audit.read_text())
    edited["model"]["label"] = "the model we meant"

    said = detail(verify_artifact(_resealed(edited)), "seal")

    assert "has not changed since it was sealed" in said
    assert "not a signature" in said
    assert "kept independently" in said
    assert "producer sealed" not in said


def test_a_source_that_differs_says_the_bytes_were_compared(tmp_path: Path) -> None:
    """Line endings a checkout converts are bytes, and the reader is told so."""
    filing = filed(tmp_path)
    filing.model.write_bytes(filing.model.read_bytes().replace(b"\n", b"\r\n"))

    said = detail(verify_artifact(filing.audit, model=filing.model), "source_sha")

    assert "bytes" in said
    assert "autocrlf" in said


def test_an_unsealed_audit_file_is_not_checked_on_the_seal(tmp_path: Path) -> None:
    document = dict(filed(tmp_path).document)
    document.pop(DOCUMENT_DIGEST_FIELD)

    report = verify_artifact(document)

    assert outcomes(report)["seal"] == "indeterminate"
    assert report.verdict == "indeterminate"


# The top level of a scenario run's own record, which is also written under a
# name ending ``.audit.json``.
_A_SCENARIO_RUN_SIDECAR: dict[str, Any] = {
    "schema_version": "2.1",
    "source_sha": "sha256:" + "a" * 64,
    "plan_canonical_form": {"shocks": {"BASE": []}},
    "run_metadata": {},
    "aggregator_outputs": {},
    "aggregator_identity": {},
    "graph_fingerprint": "sha256:" + "b" * 64,
    "graph_fingerprint_by_scenario": {},
    "input_data_fingerprint": {},
}


@pytest.mark.parametrize(
    ("given", "said"),
    [
        ({}, "states no schema"),
        ({"name": "gaspatchio-viewer", "version": "0.1.0"}, "states no schema"),
        ({"schema": "gaspatchio-graph/v9", "nodes": []}, "gaspatchio-graph/v9"),
        (_A_SCENARIO_RUN_SIDECAR, "model.audit"),
    ],
    ids=["empty", "a package manifest", "an unknown schema", "a scenario sidecar"],
)
def test_a_document_that_is_no_graph_artifact_is_refused_in_one_sentence(
    given: dict[str, Any], said: str
) -> None:
    """Nothing in a JSON object that is not an audit file can agree or differ."""
    with pytest.raises(ValueError, match="not a calculation-graph artifact") as refused:
        verify_artifact(given)

    assert said in str(refused.value)


def test_a_verification_report_is_named_for_what_it_is(tmp_path: Path) -> None:
    stored = everything(filed(tmp_path)).to_dict()

    with pytest.raises(ValueError, match="report"):
        verify_artifact(stored)


def test_an_audit_file_that_is_not_json_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "model.audit.json"
    path.write_text("not an audit file")

    with pytest.raises(ValueError, match="JSON"):
        verify_artifact(path)


# --- the report --------------------------------------------------------------------


def test_the_report_as_json_carries_every_check_and_its_outcome(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    filing.model.write_text(filing.model.read_text().replace("0.00123", "0.00124"))

    stored = everything(filing).to_dict()

    assert stored["verdict"] == "disagree"
    assert stored["artifact"] == {
        "graph_fingerprint": filing.document["graph_fingerprint"],
        "document_digest": filing.document[DOCUMENT_DIGEST_FIELD],
    }
    assert [(entry["name"], entry["outcome"]) for entry in stored["checks"]] == [
        ("seal", "agree"),
        ("results", "agree"),
        ("results_manifest", "agree"),
        ("book", "agree"),
        ("model_points", "not_asked"),
        ("source_sha", "disagree"),
        ("modules", "agree"),
        ("scenarios", "not_asked"),
        ("graph", "disagree"),
        ("holes", "agree"),
        ("git", "agree"),
        ("versions", "agree"),
        ("assumptions", "not_asked"),
    ]
    assert all(entry["detail"] for entry in stored["checks"])
    json.dumps(stored)


def test_the_documented_examples_run() -> None:
    """Every example in the module is executed, not merely displayed."""
    from gaspatchio.frame.graph import verify as verify_module

    found = [
        test for test in doctest.DocTestFinder().find(verify_module) if test.examples
    ]
    assert len(found) >= 3, "the module's examples were not found"
    report = io.StringIO()
    doctest_runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for test in found:
        doctest_runner.run(test, out=report.write)

    assert doctest_runner.failures == 0, report.getvalue()
