# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio diff`` over two audit files, each recording the results file its run wrote.

Each quarter here is a real run: ``gspio calc-graph --results`` over a model
file and a book, which writes the results file and the audit file naming it.
The second quarter runs the same model over the same book on another library
version, so the graph and the book are the ones the first quarter had and the
results file is not: a results file records the versions that wrote it, so its
bytes move while its numbers do not. The command has to say the results file
moved, exit 1, and point to ``gspio compare`` for whether the two results
agree. Where one run recorded no results file, it has nothing to compare: the
command exits on everything else and says, in one line, which run recorded
none.
"""

from __future__ import annotations

import importlib.util
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from tests.test_cli_artifact import _needle, _unwrapped

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_PLAIN = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.reserve = af.premium * 0.9
    af.total = af.reserve * 2
    return af
"""

# The reserve recorded, then written again straight into the query plan: the
# column holds what the write computed, and the audit file now says so.
_OVERWRITTEN = """
import polars as pl
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.reserve = af.premium * 0.9
    af._df = af._df.with_columns((pl.col("reserve") * 0.9).alias("reserve"))
    af.total = af.reserve * 2
    return af
"""

_MOVED = (
    "The results file differs between the two runs. A results file also "
    "records the library versions and platform that wrote it, so this says the "
    "file moved, not that any number did. To see whether the two results agree, "
    "run gspio compare on the later audit file and the two results files."
)


def _not_compared(side: str) -> str:
    """Return the line the command prints where the ``side`` run recorded none."""
    return (
        f"The results files were not compared: the {side} run recorded no "
        "checksum of a results file. If a results file from each run is to hand, "
        "run gspio compare on the later audit file and both of them to see whether "
        "the two results agree."
    )


def _quarter(folder: Path, source: str, *, results: bool = True) -> Path:
    """Run ``source`` over the book with ``calc-graph`` and return its audit file."""
    folder.mkdir()
    model = folder / "model.py"
    model.write_text(source)
    points = folder / "book.parquet"
    pl.DataFrame(
        {"policy_id": ["P1", "P2"], "premium": [1_200.0, 3_400.0]}
    ).write_parquet(points)
    audit = folder / "audit.json"
    arguments = ["calc-graph", str(model), str(points), "-o", str(audit)]
    if results:
        arguments += ["--results", str(folder / "results.parquet")]
    ran = runner.invoke(app, arguments)
    assert ran.exit_code == 0, ran.output
    return audit


def _on_another_library_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """Have every results file written from here on name another Polars version.

    A results file's manifest states the library versions and the platform
    that wrote it, so the same model over the same book, run on two versions,
    writes two files whose numbers agree and whose bytes do not. That is the
    case the comparison reads the results file for: the file moved, and
    nothing the graph or the book holds did.
    """
    from gaspatchio.engines import reference

    stated = reference.versions_in_this_process()
    another = {**stated, "polars_version": f"{stated['polars_version']}.another"}
    monkeypatch.setattr(reference, "versions_in_this_process", lambda: dict(another))


def _document(audit: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(audit.read_text())
    return document


def test_a_results_file_that_moved_under_an_unmoved_model_is_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No calculation moved and no data under them did; the results file did."""
    before = _quarter(tmp_path / "q1", _PLAIN)
    _on_another_library_version(monkeypatch)
    after = _quarter(tmp_path / "q2", _PLAIN)
    earlier, later = _document(before), _document(after)
    assert earlier["graph_fingerprint"] == later["graph_fingerprint"]
    assert earlier["book"]["digest"] == later["book"]["digest"]
    assert pl.read_parquet(tmp_path / "q1" / "results.parquet").equals(
        pl.read_parquet(tmp_path / "q2" / "results.parquet")
    )

    said = runner.invoke(app, ["diff", str(before), str(after), "--no-results"])
    read = runner.invoke(app, ["diff", str(before), str(after)])
    stored = runner.invoke(app, ["diff", str(before), str(after), "--json"])

    assert said.exit_code == 1, said.output
    printed = _unwrapped(said.output)
    assert _needle("something moved") in printed
    assert _needle("Calculations: 0 changes") in printed
    assert _needle("results results.parquet") in printed
    assert _needle(_MOVED) in printed
    assert _needle("were not compared") not in printed
    # Read, the two files say what the checksums cannot: no number moved.
    assert read.exit_code == 1, read.output
    measured = _unwrapped(read.output)
    assert _needle("Both files were read, and the values reported here") in measured
    assert _needle("unmoved definitions: no number moved") in measured

    assert stored.exit_code == 1, stored.output
    report = json.loads(stored.stdout)
    assert report["drift"] is True
    assert report["calculations"] == []
    assert report["values"]["cause"] == "producer"
    assert not any(line["moved"] for line in report["values"]["lines"])
    assert report["data"] == [
        {
            "kind": "results",
            "name": "results.parquet",
            "before": earlier["model"]["results"]["fingerprint"],
            "after": later["model"]["results"]["fingerprint"],
            "reason": None,
        }
    ]


@pytest.mark.skipif(
    importlib.util.find_spec("gaspatchio_viewer") is None,
    reason="the page is the gaspatchio-viewer distribution's; install viewer/python",
)
def test_the_page_route_exits_as_the_command_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--html`` writes the page and keeps the report's answer as its status.

    What the page itself marks is the viewer's own reading of the two
    documents, and the viewer's tests hold that to this report.
    """
    before = _quarter(tmp_path / "q1", _PLAIN)
    _on_another_library_version(monkeypatch)
    after = _quarter(tmp_path / "q2", _PLAIN)
    page = tmp_path / "drift.html"

    result = runner.invoke(app, ["diff", str(before), str(after), "--html", str(page)])

    assert result.exit_code == 1, result.output
    assert page.is_file()


def test_a_results_file_one_run_did_not_name_is_not_compared_and_a_line_says_so(
    tmp_path: Path,
) -> None:
    """No entry and no drift: the line says which run recorded no results file."""
    named = _quarter(tmp_path / "named", _PLAIN)
    unnamed = _quarter(tmp_path / "unnamed", _PLAIN, results=False)

    earlier_unnamed = runner.invoke(app, ["diff", str(unnamed), str(named)])
    later_unnamed = runner.invoke(app, ["diff", str(named), str(unnamed)])

    assert earlier_unnamed.exit_code == 0, earlier_unnamed.output
    assert _needle("nothing moved") in _unwrapped(earlier_unnamed.output)
    assert _needle(_not_compared("earlier")) in _unwrapped(earlier_unnamed.output)
    assert later_unnamed.exit_code == 0, later_unnamed.output
    assert _needle(_not_compared("later")) in _unwrapped(later_unnamed.output)


def test_the_line_stays_out_of_the_json_a_pipeline_reads(tmp_path: Path) -> None:
    """``--json`` is the report and nothing else, and the report has no entry."""
    named = _quarter(tmp_path / "named", _PLAIN)
    unnamed = _quarter(tmp_path / "unnamed", _PLAIN, results=False)

    result = runner.invoke(app, ["diff", str(unnamed), str(named), "--json"])

    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert (report["drift"], report["data"]) == (False, [])


def test_two_runs_that_wrote_the_same_results_file_say_nothing_of_it(
    tmp_path: Path,
) -> None:
    """One model over one book writes one results file, byte for byte."""
    before = _quarter(tmp_path / "q1", _PLAIN)
    after = _quarter(tmp_path / "q2", _PLAIN)
    assert (
        _document(before)["model"]["results"]["fingerprint"]
        == _document(after)["model"]["results"]["fingerprint"]
    )

    result = runner.invoke(app, ["diff", str(before), str(after)])

    assert result.exit_code == 0, result.output
    printed = _unwrapped(result.output)
    assert _needle("nothing moved") in printed
    assert _needle("were not compared") not in printed


def test_a_reserve_overwritten_in_the_plan_is_a_calculation_change(
    tmp_path: Path,
) -> None:
    """The overwrite is in the audit file now, so the comparison finds it there.

    Written straight into the query plan, the reserve is a definition the
    frame saw and could not read: a hole under the reserve's next ordinal,
    which the total reads. Against the run without the write, that is a
    calculation added and a calculation whose input moved, as well as a
    results file that moved, and the command says all three.
    """
    before = _quarter(tmp_path / "q1", _PLAIN)
    after = _quarter(tmp_path / "q2", _OVERWRITTEN)

    said = runner.invoke(app, ["diff", str(before), str(after)])
    stored = runner.invoke(app, ["diff", str(before), str(after), "--json"])

    assert said.exit_code == 1, said.output
    printed = _unwrapped(said.output)
    assert _needle("Calculations: 2 changes") in printed
    assert _needle("results results.parquet") in printed
    report = json.loads(stored.stdout)
    assert [(change["node"], change["kind"]) for change in report["calculations"]] == [
        ("reserve@2", "added"),
        ("total@1", "changed"),
    ]
    assert [entry["kind"] for entry in report["data"]] == ["results"]
