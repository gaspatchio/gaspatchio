# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Two audit files, each recording the results file its run wrote.

A reviewer compares last quarter's audit file with this quarter's. Where both
runs were exported with their results file named, each document records the
sha256 of that file in ``model.results.fingerprint``, and the comparison reads
the two: a results file that differs is a ``data`` entry of kind ``results``,
and it is drift. Before it did, two different results files under one model
and one book compared as nothing moved, whatever had moved the file: the same
numbers written out by another library version, or a file changed after the
run that wrote it.

The entry names the file and not the numbers. A results file also records the
library versions and platform that wrote it, so two runs on two versions or two
machines differ in bytes where every number agrees, and ``gspio compare`` is the
step that says whether the two results agree. Where only one run recorded a
results file's checksum there is nothing to compare and nothing is reported;
``gspio diff`` says so in a line and the comparison page in a sentence, and both
are held here to one text.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest

from gaspatchio import ActuarialFrame
from gaspatchio.frame.graph import (
    DataChange,
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    diff_artifacts,
)
from gaspatchio.frame.graph.diff import (
    _RESULTS_FILE_MOVED,
    _RESULTS_OF_TWO_CALCULATIONS,
    _RESULTS_OVER_TWO_BOOKS,
    _RESULTS_READ,
    _results_file_moved,
    _results_not_compared,
)

if TYPE_CHECKING:
    from polars._typing import ParquetCompression

# --- the valuation both quarters run -----------------------------------------

_BOOK = pl.DataFrame(
    {"policy_id": ["P1", "P2"], "premium": [1_200.0, 3_400.0]},
)

# The two results files, as a hand-built identity names them. The viewer's
# test/compare.test.ts and e2e/compare.spec.ts name the same two, because the
# report committed beside the viewer's fixtures is taken over them.
_Q1: dict[str, str] = {
    "path": "results_q1.parquet",
    "fingerprint": "sha256:" + "1" * 64,
}
_Q2: dict[str, str] = {
    "path": "results_q2.parquet",
    "fingerprint": "sha256:" + "2" * 64,
}


def _reserve_model(book: pl.DataFrame | None = None) -> ActuarialFrame:
    """Return the valuation: a reserve off the premium, and a total off the reserve."""
    af = ActuarialFrame(_BOOK if book is None else book)
    af.reserve = af.premium * 0.9
    af.total = af.reserve * 2
    return af


def _exported(
    af: ActuarialFrame, results: dict[str, str] | None = None
) -> dict[str, Any]:
    """Return the audit file for ``af``, naming ``results`` where it is given."""
    config = (
        None
        if results is None
        else GraphExportConfig(model=ModelIdentity(results=results))
    )
    document: dict[str, Any] = json.loads(GraphExporter(af).export(config=config))
    return document


# --- the entry ----------------------------------------------------------------


def test_two_results_files_that_differ_are_one_data_entry_and_drift() -> None:
    """The model and the book agree, and the two files the runs wrote do not."""
    before = _exported(_reserve_model(), _Q1)
    after = _exported(_reserve_model(), _Q2)

    report = diff_artifacts(before, after)

    assert report.calculations == ()
    assert report.data == (
        DataChange(
            "results", "results_q2.parquet", _Q1["fingerprint"], _Q2["fingerprint"]
        ),
    )
    assert report.drift is True
    assert report.to_dict()["data"] == [
        {
            "kind": "results",
            "name": "results_q2.parquet",
            "before": _Q1["fingerprint"],
            "after": _Q2["fingerprint"],
            "reason": None,
        }
    ]


def test_the_entry_is_named_by_the_later_file_then_the_earlier_one() -> None:
    """The name a reader knows the file by: the later run's, else the earlier's."""
    unnamed_q1 = {"fingerprint": _Q1["fingerprint"]}
    unnamed_q2 = {"fingerprint": _Q2["fingerprint"]}

    later_unnamed = diff_artifacts(
        _exported(_reserve_model(), _Q1), _exported(_reserve_model(), unnamed_q2)
    )
    neither_named = diff_artifacts(
        _exported(_reserve_model(), unnamed_q1), _exported(_reserve_model(), unnamed_q2)
    )

    assert [entry.name for entry in later_unnamed.data] == ["results_q1.parquet"]
    assert [entry.name for entry in neither_named.data] == [None]


def test_one_results_file_under_two_names_is_no_change() -> None:
    """The same bytes moved to another path are the same file, and say nothing."""
    moved = {"path": "archive/results_q1.parquet", "fingerprint": _Q1["fingerprint"]}
    before = _exported(_reserve_model(), _Q1)
    after = _exported(_reserve_model(), moved)

    report = diff_artifacts(before, after)

    assert (report.drift, report.data) == (False, ())
    assert _results_not_compared(before, after) is None


def test_the_results_file_is_read_after_every_other_kind_of_data() -> None:
    """What went into the run first, then what came out of it."""
    before = _exported(_reserve_model(), _Q1)
    after = _exported(_reserve_model(_BOOK.with_columns(pl.col("premium") * 2)), _Q2)

    report = diff_artifacts(before, after)

    assert [entry.kind for entry in report.data] == ["model_points", "results"]


# --- where only one run recorded a results file -------------------------------


def test_a_results_file_only_one_run_named_is_not_compared_and_says_which() -> None:
    """No entry and no drift, and a sentence naming the run that recorded none."""
    named = _exported(_reserve_model(), _Q1)
    unnamed = _exported(_reserve_model())
    assert "results" not in unnamed["model"]

    for earlier, later in ((unnamed, named), (named, unnamed)):
        report = diff_artifacts(earlier, later)
        assert (report.drift, report.data) == (False, ())

    assert _results_not_compared(unnamed, named) == (
        "The results files were not compared: the earlier run recorded no "
        "checksum of a results file. If a results file from each run is to hand, "
        "run gspio compare on the later audit file and both of them to see whether "
        "the two results agree."
    )
    assert _results_not_compared(named, unnamed) == (
        "The results files were not compared: the later run recorded no "
        "checksum of a results file. If a results file from each run is to hand, "
        "run gspio compare on the later audit file and both of them to see whether "
        "the two results agree."
    )


def test_neither_run_naming_a_results_file_is_nothing_to_say() -> None:
    """Most exports name no results file, and a line on every one would be noise."""
    before = _exported(_reserve_model())
    after = _exported(_reserve_model())

    assert diff_artifacts(before, after).data == ()
    assert _results_not_compared(before, after) is None


@pytest.mark.parametrize(
    "block",
    [
        {"path": "results_q2.parquet"},
        {"path": "results_q2.parquet", "fingerprint": None},
    ],
)
def test_a_results_block_stating_no_checksum_is_not_compared(
    block: dict[str, Any],
) -> None:
    """A block naming only a path records no checksum a comparison could read.

    The run may well have written the file it names, so the sentence says it
    recorded no checksum rather than that it named no file, which would be
    false of this very block.
    """
    before = _exported(_reserve_model(), _Q1)
    after = _exported(_reserve_model())
    after["model"]["results"] = block

    said = _results_not_compared(before, after)

    assert diff_artifacts(before, after).data == ()
    assert said is not None
    assert "the later run recorded no checksum of a results file" in said
    assert "named no" not in said


def test_the_two_newer_sentences_are_the_words_the_page_uses() -> None:
    """``viewer/test/compare.test.ts`` holds the page to these exact sentences."""
    assert _RESULTS_OF_TWO_CALCULATIONS == (
        "The results file differs between the two runs, and so does the model: the "
        "two audit files state different graph fingerprints, so the files hold the "
        "numbers of two different calculations. The calculations listed above are "
        "the ones whose numbers can have moved. To see which did, and by how much, "
        "run gspio diff on the two audit files with --results and the two results "
        "files, earlier first."
    )
    assert _RESULTS_OVER_TWO_BOOKS == (
        "The results file differs between the two runs, and so does the book the "
        "model ran over, so the numbers can have moved with the data. To see which "
        "did, and by how much, run gspio diff on the two audit files with --results "
        "and the two results files, earlier first: it pairs the two books' policies "
        "and counts those only one of them holds."
    )
    assert _RESULTS_READ == (
        "The results file differs between the two runs. Both files were read, and "
        "the values reported here compare them line by line and policy by policy."
    )


def test_the_entry_says_the_file_moved_in_the_words_the_page_uses() -> None:
    """``viewer/test/compare.test.ts`` holds the page to this exact sentence."""
    assert _RESULTS_FILE_MOVED == (
        "The results file differs between the two runs. A results file also "
        "records the library versions and platform that wrote it, so this says "
        "the file moved, not that any number did. To see whether the two results "
        "agree, run gspio compare on the later audit file and the two results "
        "files."
    )


# --- the route that produces it -----------------------------------------------


def _a_quarter(
    folder: Path, af: ActuarialFrame, *, compression: ParquetCompression = "zstd"
) -> dict[str, Any]:
    """Run ``af``, write its results, and export it naming every file it used.

    ``ModelIdentity.of`` is how a Python export names the model file, the
    policy data and the results file, so the block is the one ``calc-graph``
    writes. ``compression`` is how the results file is written out, which
    moves its bytes and none of its numbers.
    """
    folder.mkdir()
    model_file = folder / "model.py"
    model_file.write_text("# The valuation: a reserve, and a total off it.\n")
    points = folder / "book.parquet"
    _BOOK.write_parquet(points)
    result = af.collect()
    results = folder / "results.parquet"
    result.write_parquet(results, compression=compression)
    identity = ModelIdentity.of(model_file, model_points=points, results=results)
    document: dict[str, Any] = json.loads(
        GraphExporter(af).export(result, GraphExportConfig(model=identity))
    )
    return document


def test_a_results_file_written_another_way_moves_the_file_and_nothing_else(
    tmp_path: Path,
) -> None:
    """The case the comparison reads the results file for.

    One model over one book, and the same numbers written out a second way:
    the two graph fingerprints agree, the two runs read one book, and the two
    results files hold the same values in different bytes. Only the file
    moved, and the comparison says so and no more.
    """
    before = _a_quarter(tmp_path / "q1", _reserve_model())
    after = _a_quarter(tmp_path / "q2", _reserve_model(), compression="uncompressed")
    assert before["graph_fingerprint"] == after["graph_fingerprint"]
    assert before["book"]["digest"] == after["book"]["digest"]
    assert pl.read_parquet(tmp_path / "q1" / "results.parquet").equals(
        pl.read_parquet(tmp_path / "q2" / "results.parquet")
    )

    report = diff_artifacts(before, after)

    assert report.calculations == ()
    assert report.data == (
        DataChange(
            "results",
            "results.parquet",
            before["model"]["results"]["fingerprint"],
            after["model"]["results"]["fingerprint"],
        ),
    )
    assert report.drift is True


def test_a_reserve_overwritten_in_the_plan_moves_the_record_as_well(
    tmp_path: Path,
) -> None:
    """Written straight into the plan, the reserve is a definition in the audit file.

    The frame reads the write and logs it, so the export holds a hole under
    the reserve's next ordinal and the total reads it. Against the run
    without the write, the comparison names both, and the results file moved
    too because the numbers did.
    """
    overwritten = ActuarialFrame(_BOOK)
    overwritten.reserve = overwritten.premium * 0.9
    plan = overwritten._df  # noqa: SLF001 -- the route under test
    assert plan is not None
    overwritten._df = plan.with_columns((pl.col("reserve") * 0.9).alias("reserve"))  # noqa: SLF001
    overwritten.total = overwritten.reserve * 2
    before = _a_quarter(tmp_path / "q1", _reserve_model())
    after = _a_quarter(tmp_path / "q2", overwritten)

    report = diff_artifacts(before, after)

    assert [(change.node, change.kind) for change in report.calculations] == [
        ("reserve@2", "added"),
        ("total@1", "changed"),
    ]
    assert [entry.kind for entry in report.data] == ["results"]
    assert report.drift is True


# --- the step the entry points at is one that works ----------------------------

_A_VALUATION = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.reserve = af.premium * {factor}
    return af
"""


def _a_run(folder: Path, *, factor: str, book: pl.DataFrame) -> tuple[Path, Path]:
    """Export one valuation from the command line, its results file named."""
    from typer.testing import CliRunner

    from gaspatchio.cli import app

    folder.mkdir()
    model = folder / "model.py"
    model.write_text(_A_VALUATION.format(factor=factor))
    points = folder / "book.parquet"
    book.write_parquet(points)
    audit = folder / "model.audit.json"
    results = folder / "results.parquet"
    ran = CliRunner().invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(points),
            "-o",
            str(audit),
            "--results",
            str(results),
        ],
    )
    assert ran.exit_code == 0, ran.output
    return audit, results


def test_after_an_edit_the_entry_does_not_send_the_reader_to_a_refusal(
    tmp_path: Path,
) -> None:
    """Every room followed the old sentence to ``gspio compare``, and it refused.

    The model was edited, so the two results files are of two calculations,
    and compare binds a results file to one artifact's graph fingerprint.
    The entry points at what works -- this command again, with the two
    results files -- and compare's own refusal names it too.
    """
    from typer.testing import CliRunner

    from gaspatchio.cli import app

    before, before_results = _a_run(tmp_path / "q1", factor="0.9", book=_BOOK)
    after, after_results = _a_run(tmp_path / "q2", factor="0.8", book=_BOOK)
    earlier, later = json.loads(before.read_text()), json.loads(after.read_text())

    said = _results_file_moved(earlier, later)
    diffed = CliRunner().invoke(app, ["diff", str(before), str(after), "--no-results"])
    compared = CliRunner().invoke(
        app, ["compare", str(after), str(before_results), str(after_results)]
    )

    refused = " ".join(compared.output.split())
    assert "run gspio diff on the two audit files with --results" in said
    assert "pl.read_parquet" not in said
    assert "run gspio compare on" not in said
    assert "run gspio compare on" not in " ".join(diffed.output.split())
    assert "not of this artifact" in refused
    assert "gspio diff on the two versions' audit files with --results" in refused


def test_over_a_moved_book_the_entry_says_what_compare_will_and_will_not_do(
    tmp_path: Path,
) -> None:
    """One calculation over two books: the policies are paired, not refused on size."""
    grown = pl.DataFrame(
        {"policy_id": ["P1", "P2", "P3"], "premium": [1_200.0, 3_400.0, 900.0]}
    )
    before, _ = _a_run(tmp_path / "q1", factor="0.9", book=_BOOK)
    after, _ = _a_run(tmp_path / "q2", factor="0.9", book=grown)

    said = _results_file_moved(
        json.loads(before.read_text()), json.loads(after.read_text())
    )

    assert "counts those only one of them holds" in said
    assert "pl.read_parquet" not in said


def test_where_only_the_file_moved_the_entry_still_points_at_compare(
    tmp_path: Path,
) -> None:
    """The one case compare answers outright, in the words the page uses."""
    before = _a_quarter(tmp_path / "q1", _reserve_model())
    after = _a_quarter(tmp_path / "q2", _reserve_model(), compression="uncompressed")

    assert _results_file_moved(before, after) == _RESULTS_FILE_MOVED


def test_an_unrecorded_checksum_after_an_edit_does_not_point_at_compare() -> None:
    """The line for one unrecorded checksum follows the same rule."""
    named = _exported(_reserve_model(), _Q1)
    edited = ActuarialFrame(_BOOK)
    edited.reserve = edited.premium * 0.8
    edited.total = edited.reserve * 2
    unnamed = _exported(edited)

    said = _results_not_compared(named, unnamed)

    assert said is not None
    assert "gspio diff on the two audit files with --results" in said
    assert "run gspio compare on" not in said


# --- the answer the comparison page is held to --------------------------------

# What writes the committed report again, named in the failure that asks for
# it. A staleness guard that fails as a diff of two reports has said what is
# wrong and nothing about the cure.
_REGENERATION = "uv run python -m tests.graph.test_diff_results"


def _viewer_fixtures() -> Path | None:
    """Return the viewer's fixtures directory in this tree, or None outside one."""
    fixtures = Path(__file__).resolve().parents[4] / "viewer" / "fixtures"
    return fixtures if (fixtures / "compare-before.json").is_file() else None


def _with_results(document: dict[str, Any], results: dict[str, str]) -> dict[str, Any]:
    """Return ``document`` as though its run had named ``results``."""
    derived = copy.deepcopy(document)
    derived["model"] = {**derived["model"], "results": results}
    return derived


def _the_report_over_the_page_s_fixture(fixtures: Path) -> dict[str, Any]:
    """Return the report over the two documents the page's tests derive.

    One committed export of level 4, compared with itself as though each run
    had named a results file, the earlier ``results_q1.parquet`` and the later
    ``results_q2.parquet``: the pair ``viewer/test/compare.test.ts`` and
    ``viewer/e2e/compare.spec.ts`` derive from the same fixture.
    """
    document = json.loads((fixtures / "compare-before.json").read_text("utf-8"))
    report: dict[str, Any] = diff_artifacts(
        _with_results(document, _Q1), _with_results(document, _Q2)
    ).to_dict()
    return report


def _write_the_committed_report() -> None:
    """Write the committed report from the fixture it is taken over, in one place."""
    fixtures = _viewer_fixtures()
    if fixtures is None:
        msg = (
            "The viewer's fixtures are not in this tree, so there is no report "
            "to write."
        )
        raise SystemExit(msg)
    report = _the_report_over_the_page_s_fixture(fixtures)
    written = json.dumps(report, indent=2)
    (fixtures / "compare-results-report.json").write_text(f"{written}\n", "utf-8")


@pytest.mark.skipif(
    _viewer_fixtures() is None, reason="needs this repository's viewer/ tree"
)
def test_the_committed_report_is_the_report_diff_writes_over_the_page_s_fixture() -> (
    None
):
    """The page is held to this report, so the report is held to the code.

    ``viewer/test/compare.test.ts`` holds the page's reading to this committed
    report, and ``viewer/e2e/compare.spec.ts`` holds it to the command. It is
    compared here whole, the two documents it names included, so a fixture
    restamped or exported again without the report being written again fails
    here rather than leaving the report naming a seal no fixture carries.
    """
    fixtures = _viewer_fixtures()
    assert fixtures is not None
    committed = json.loads(
        (fixtures / "compare-results-report.json").read_text("utf-8")
    )

    report = _the_report_over_the_page_s_fixture(fixtures)

    assert [entry["kind"] for entry in report["data"]] == ["results"]
    assert report == committed, (
        "viewer/fixtures/compare-results-report.json is not the report "
        "diff_artifacts writes today over the fixture it was taken over. If the "
        "fixture or the report moved on purpose, write it again with "
        f"`{_REGENERATION}` from bindings/python."
    )


if __name__ == "__main__":
    _write_the_committed_report()
