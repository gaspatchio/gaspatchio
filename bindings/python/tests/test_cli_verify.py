# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio verify``: an audit file's evidence, read back from the command line.

A pipeline step asks the question a reviewer asks -- are these the files
this audit file records? -- and branches on the exit status: 0 where every
check the given files ask for agrees, 1 where one differs, 4 where one could
not be made because nothing was recorded to check against, and 2 where a
file could not be read at all.

The checks are the library's, written once. What is asserted here is that
they arrive unaltered, that the status says what the report says, and that
the stored form is the report's own JSON.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines.protocol import digest_of_inputs
from gaspatchio.frame.graph import DOCUMENT_DIGEST_FIELD, verify_artifact
from tests.graph.test_model_identity_of import _a_checkout_at
from tests.graph.test_verify import Filing, _flip_one_byte, filed
from tests.test_cli_artifact import _needle, _reached_no_answer, _unwrapped

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()


def _verify(audit: Path, *options: str) -> Result:
    """Run ``gspio verify`` over one audit file."""
    return runner.invoke(app, ["verify", str(audit), *options])


def _everything(filing: Filing) -> list[str]:
    """Return the options naming every file the run used and wrote."""
    return [
        "--results",
        str(filing.results),
        "--model-points",
        str(filing.points),
        "--model",
        str(filing.model),
    ]


def _outcomes(stored: dict[str, Any]) -> dict[str, str]:
    """Return each check's outcome from the stored report, by the check's name."""
    return {entry["name"]: entry["outcome"] for entry in stored["checks"]}


# --- the four statuses ----------------------------------------------------------


def test_every_file_agreeing_exits_zero(tmp_path: Path) -> None:
    filing = filed(tmp_path)

    result = _verify(filing.audit, *_everything(filing))

    assert result.exit_code == 0, result.output
    assert _needle("agree") in _unwrapped(result.output)


def test_one_flipped_byte_in_the_results_exits_one_naming_the_results(
    tmp_path: Path,
) -> None:
    filing = filed(tmp_path)
    _flip_one_byte(filing.results)

    result = _verify(filing.audit, *_everything(filing))

    assert result.exit_code == 1, result.output
    assert _needle("does not match: results") in _unwrapped(result.output)


def test_an_edited_model_source_exits_one_naming_source_sha(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    filing.model.write_text(filing.model.read_text().replace("0.00123", "0.00124"))

    result = _verify(filing.audit, "--model", str(filing.model))

    assert result.exit_code == 1, result.output
    assert _needle("does not match: source_sha") in _unwrapped(result.output)


def test_other_model_points_exit_one_naming_both_book_digests(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    other = tmp_path / "other_points.parquet"
    book = pl.DataFrame({"policy_id": ["A"], "sum_assured": [250_000.0]})
    book.write_parquet(other)
    theirs = digest_of_inputs(book, filing.document["book"]["columns"])

    result = _verify(filing.audit, "--model-points", str(other))

    assert result.exit_code == 1, result.output
    said = _unwrapped(result.output)
    assert _needle(filing.document["book"]["digest"]) in said
    assert _needle(theirs) in said
    assert _needle("does not match: book") in said
    assert _needle("book, model_points") not in said


def test_the_same_book_written_as_csv_exits_zero(tmp_path: Path) -> None:
    """Another file holding the same policies is the same book."""
    filing = filed(tmp_path)
    as_csv = tmp_path / "points.csv"
    pl.read_parquet(filing.points).write_csv(as_csv)

    result = _verify(filing.audit, "--model-points", str(as_csv))

    assert result.exit_code == 0, result.output


def test_results_the_audit_file_records_nothing_for_exit_four(tmp_path: Path) -> None:
    """A check that decides, with nothing recorded to check against, is no agreement.

    The file's manifest agrees, and it still exits 4: the manifest says
    which model and book produced the file, not that it is the file this
    audit file is an account of.
    """
    filing = filed(tmp_path, name_the_results=False)

    result = _verify(filing.audit, "--results", str(filing.results))

    assert result.exit_code == 4, result.output
    said = _unwrapped(result.output)
    assert _needle("could not be checked") in said
    assert _needle("nothing ties it to this audit file") in said


def test_a_results_file_written_with_no_manifest_whose_sha_agrees_exits_zero(
    tmp_path: Path,
) -> None:
    """A plain Parquet from Python: the recorded sha256 decides, and it agrees."""
    filing = filed(tmp_path, manifest=False)

    result = _verify(filing.audit, "--results", str(filing.results))

    assert result.exit_code == 0, result.output
    assert _needle("carries no result manifest") in _unwrapped(result.output)


def test_evidence_with_nothing_to_add_moves_nothing(tmp_path: Path) -> None:
    """No file stamp recorded, and a model copy outside a checkout: still 0."""
    filing = filed(tmp_path, name_the_points=False)
    copy = tmp_path / "copy" / "model.py"
    copy.parent.mkdir()
    copy.write_bytes(filing.model.read_bytes())

    result = _verify(
        filing.audit,
        "--model-points",
        str(filing.points),
        "--model",
        str(copy),
        "--json",
    )

    assert result.exit_code == 0, result.output
    stored = json.loads(result.stdout)
    assert _outcomes(stored)["model_points"] == "not_asked"
    assert _outcomes(stored)["git"] == "not_asked"


def test_an_edited_audit_file_exits_one_naming_the_seal(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    document = json.loads(filing.audit.read_text())
    document["graph_fingerprint"] = "sha256:" + "1" * 64
    filing.audit.write_text(json.dumps(document))

    result = _verify(filing.audit)

    assert result.exit_code == 1, result.output
    assert _needle("does not match: seal") in _unwrapped(result.output)


def test_an_audit_file_that_is_not_json_is_no_answer(tmp_path: Path) -> None:
    path = tmp_path / "model.audit.json"
    path.write_text("this is not an audit file")

    result = _verify(path)

    _reached_no_answer(result, path.name)


def test_a_json_object_that_is_no_audit_file_is_no_answer(tmp_path: Path) -> None:
    """{} and a package.json once read as nothing differing, and exited 4."""
    for name, text in (("empty.json", "{}"), ("package.json", '{"name": "x"}')):
        path = tmp_path / name
        path.write_text(text)

        result = _verify(path)

        _reached_no_answer(result, "not a calculation-graph artifact")


def test_a_scenario_run_s_own_record_is_named_and_the_right_file_asked_for(
    tmp_path: Path,
) -> None:
    """Both records of a scenario run end .audit.json, and only one is an audit file."""
    from tests.graph.test_verify import _A_SCENARIO_RUN_SIDECAR

    sidecar = tmp_path / "run.audit.json"
    sidecar.write_text(json.dumps(_A_SCENARIO_RUN_SIDECAR))

    result = _verify(sidecar)

    _reached_no_answer(result, "scenario run's own record")
    assert _needle("model.audit") in _unwrapped(result.output)


def test_a_file_that_is_not_there_is_no_answer(tmp_path: Path) -> None:
    filing = filed(tmp_path)

    result = _verify(filing.audit, "--results", str(tmp_path / "missing.parquet"))

    assert result.exit_code == 2, result.output
    assert _needle("missing.parquet") in _unwrapped(result.output)


def test_policy_data_that_cannot_be_read_is_no_answer(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    broken = tmp_path / "broken.parquet"
    broken.write_bytes(b"not a parquet file")

    result = _verify(filing.audit, "--model-points", str(broken))

    _reached_no_answer(result, broken.name)


def test_a_file_that_cannot_be_read_outranks_a_difference(tmp_path: Path) -> None:
    """Two before one: a verdict reached over a file that was not read is no verdict."""
    filing = filed(tmp_path)
    _flip_one_byte(filing.results)
    broken = tmp_path / "broken.parquet"
    broken.write_bytes(b"not a parquet file")

    result = _verify(
        filing.audit, "--results", str(filing.results), "--model-points", str(broken)
    )

    _reached_no_answer(result, broken.name)


def test_the_help_says_which_checks_decide_and_which_add_evidence() -> None:
    """The exit rule is on the page a user reads before running the command."""
    result = runner.invoke(app, ["verify", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    said = _unwrapped(result.output.replace("│", ""))
    assert _needle("These checks decide") in said
    assert _needle("These add evidence") in said
    for name in (
        "seal",
        "results",
        "book",
        "model_points",
        "source_sha",
        "results_manifest",
        "git",
    ):
        assert _needle(f"{name}:") in said
    assert _needle("4 a check that decides is indeterminate") in said
    assert _needle("A recorded dirty tree moves no exit status") in said


def test_the_help_says_the_file_stamp_decides_only_in_the_books_place() -> None:
    """The file stamp stands in for the book, and is never the check left open.

    Where the audit file states a book digest, the book decides. Where it
    states none, the policy data file's own stamp decides in its place. Where
    neither is recorded, the book is the check that is indeterminate and the
    stamp is not asked (``tests/graph/test_verify.py`` holds all three), so
    the help must not list the stamp among the checks that can be.
    """
    result = runner.invoke(app, ["verify", "--help"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    said = _unwrapped(result.output.replace("│", ""))
    assert (
        _needle(
            "model_points: the policy data file's stamp, its sha256 against "
            "model.model_points, which decides in the book's place and only "
            "where no book digest is stated. It is never indeterminate: where "
            "neither is recorded, book is."
        )
        in said
    )


# --- a line not asked says why on the line -----------------------------------------


def test_the_model_points_line_says_the_book_decides_beside_the_flag_given(
    tmp_path: Path,
) -> None:
    """``--model-points`` given and ``model_points  not asked`` read as a flag ignored.

    The policy data was checked -- by the book line, which decides wherever the
    audit file states a book digest -- and the file stamp is only set beside
    it for information. The line now says so where it is read.
    """
    filing = filed(tmp_path)

    result = _verify(filing.audit, *_everything(filing))

    assert result.exit_code == 0, result.output
    said = _unwrapped(result.output)
    assert _needle("book agrees (book.digest)") in said
    assert (
        _needle(
            "model_points not asked: the book check decides "
            "(model.model_points.fingerprint) For information,"
        )
        in said
    )


def test_every_line_not_asked_carries_its_reason(tmp_path: Path) -> None:
    """With no file given, each line not asked says which file was not given."""
    filing = filed(tmp_path)

    result = _verify(filing.audit)

    assert result.exit_code == 0, result.output
    said = _unwrapped(result.output)
    for name, given in (
        ("results", "results file"),
        ("results_manifest", "results file"),
        ("book", "model points file"),
        ("model_points", "model points file"),
        ("source_sha", "model file"),
        ("modules", "model file"),
        ("git", "model file"),
        ("assumptions", "assumption files were"),
    ):
        assert _needle(f"{name} not asked: no {given}") in said, name
    assert _needle("not asked (") not in said


# --- the stored report -----------------------------------------------------------


def test_json_lists_every_check_with_its_outcome(tmp_path: Path) -> None:
    filing = filed(tmp_path)

    result = _verify(filing.audit, *_everything(filing), "--json")

    assert result.exit_code == 0, result.output
    stored = json.loads(result.stdout)
    assert (
        stored
        == verify_artifact(
            filing.audit,
            results=filing.results,
            model_points=filing.points,
            model=filing.model,
        ).to_dict()
    )
    assert _outcomes(stored) == {
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


def test_the_report_written_out_is_the_one_the_library_made(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    stored = tmp_path / "verification.json"

    result = _verify(
        filing.audit,
        "--model",
        str(filing.model),
        "--model-points",
        str(filing.points),
        "-o",
        str(stored),
    )

    assert result.exit_code == 0, result.output
    assert json.loads(stored.read_text()) == (
        verify_artifact(
            filing.audit, model=filing.model, model_points=filing.points
        ).to_dict()
    )


def test_a_verdict_that_cannot_be_stored_is_still_said_first(tmp_path: Path) -> None:
    filing = filed(tmp_path)
    nowhere = tmp_path / "no_such_directory" / "verification.json"

    result = _verify(filing.audit, "-o", str(nowhere))

    assert result.exit_code == 2, result.output
    assert _needle("agree") in _unwrapped(result.output)
    assert _needle("not stored") in _unwrapped(result.output)


# --- an audit file the command line wrote ----------------------------------------


def test_an_audit_file_calc_graph_wrote_verifies_against_its_own_run(
    tmp_path: Path,
) -> None:
    """The command line's own export, read back by the command line.

    ``calc-graph`` writes the result manifest into the results file it
    stamps, so the manifest line agrees as well: the file states the model's
    fingerprint and the book's digest its audit file states.
    """
    model, _ = _a_checkout_at(tmp_path / "repository")
    out = tmp_path / "out"
    out.mkdir()
    points = out / "points.csv"
    pl.DataFrame(
        {"policy_id": ["A", "B"], "sum_assured": [100_000, 250_000]}
    ).write_csv(points)
    exported = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(points),
            "-o",
            str(out / "model.audit.json"),
            "--results",
            str(out / "results.parquet"),
        ],
    )
    assert exported.exit_code == 0, exported.output

    result = _verify(
        out / "model.audit.json",
        "--results",
        str(out / "results.parquet"),
        "--model-points",
        str(points),
        "--model",
        str(model),
        "--json",
    )

    stored = json.loads(result.stdout)
    outcomes = _outcomes(stored)
    assert outcomes.pop("results_manifest") == "agree"
    assert outcomes.pop("model_points") == "not_asked"
    assert outcomes.pop("scenarios") == "not_asked"
    assert outcomes.pop("assumptions") == "not_asked"
    assert set(outcomes.values()) == {"agree"}
    assert stored["verdict"] == "agree"
    assert result.exit_code == 0, result.output
    assert (
        stored["artifact"]["document_digest"]
        == json.loads((out / "model.audit.json").read_text())[DOCUMENT_DIGEST_FIELD]
    )
