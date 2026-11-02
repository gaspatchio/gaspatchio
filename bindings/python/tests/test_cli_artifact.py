# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The artifact, read and compared from the command line.

A pipeline step does not import a library and inspect a dataclass. It runs a
command and reads an exit status, and the status has to mean something a step
can branch on: an artifact that may be read, an artifact that may not, two
quarters that agree, two quarters that do not, and -- kept apart from all
four -- a file the command never managed to read at all.

The findings themselves are the library's, written once in the framework's
own voice. What is asserted here is that they arrive unaltered, that the
exit status says what the report says, and that the stored form a downstream
step reads is the report's own JSON rather than anything scraped off a
terminal.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import ConformanceProfile, _tier_line, app
from gaspatchio.frame.graph import (
    FINGERPRINT_ALGORITHM,
    PROFILE_AUDIT,
    PROFILE_EXECUTABLE,
    GraphExporter,
    TierCensus,
    build_artifact,
    diff_artifacts,
    fold,
    validate_artifact,
)
from tests.graph.test_html_export import _notices_file, _notices_in

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()

MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * 0.00123
    return af
"""


def _valuation(
    rate: float = 0.00123, sums_assured: tuple[float, ...] = (100_000.0,)
) -> dict[str, Any]:
    """Return the artifact of a one-line model, at the factor given, over a book."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": list(sums_assured)}))
    af.death_claims = af.sum_assured * rate
    return json.loads(GraphExporter(af).export())


def _stored(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document, indent=2))
    return path


def _model_and_points(tmp_path: Path) -> tuple[Path, Path]:
    model_path = tmp_path / "model.py"
    model_path.write_text(MODEL_SRC)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [100_000.0]}).write_parquet(
        points_path
    )
    return model_path, points_path


# --- gspio validate --------------------------------------------------------


def test_an_artifact_that_conforms_exits_zero_and_names_its_schema(
    tmp_path: Path,
) -> None:
    path = _stored(tmp_path / "artifact.json", _valuation())

    result = runner.invoke(app, ["validate", str(path)])

    assert result.exit_code == 0, result.output
    assert "gaspatchio-graph/v0-preview.3" in result.output


def test_an_artifact_that_is_refused_exits_one_and_says_where(
    tmp_path: Path,
) -> None:
    document = _valuation()
    document["edges"].append(
        {
            "source": "not_a_node",
            "target": "death_claims@1",
            "relationship": "DIRECT",
        }
    )
    path = _stored(tmp_path / "artifact.json", document)

    result = runner.invoke(app, ["validate", str(path)])

    assert result.exit_code == 1, result.output
    assert "not_a_node" in result.output


def test_the_report_written_out_is_the_one_the_library_made(tmp_path: Path) -> None:
    """Printed, not rewritten -- a second wording is a second thing to keep true."""
    document = _valuation()
    document["schema"] = "gaspatchio-graph/v9"
    path = _stored(tmp_path / "artifact.json", document)
    report_path = tmp_path / "report.json"

    result = runner.invoke(
        app, ["validate", str(path), "--output-file", str(report_path)]
    )

    assert result.exit_code == 1, result.output
    assert json.loads(report_path.read_text()) == validate_artifact(document).to_dict()


def test_a_warning_on_its_own_does_not_refuse_the_artifact(tmp_path: Path) -> None:
    """An engine the artifact never mentions is worth saying and is not a refusal."""
    path = _stored(tmp_path / "artifact.json", _valuation())

    result = runner.invoke(app, ["validate", str(path), "--engine", "an_engine"])

    assert result.exit_code == 0, result.output
    assert "an_engine" in result.output


def test_validate_json_goes_to_stdout_for_a_reader_that_parses_it(
    tmp_path: Path,
) -> None:
    document = _valuation()
    path = _stored(tmp_path / "artifact.json", document)

    result = runner.invoke(app, ["validate", str(path), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == validate_artifact(document).to_dict()


def test_a_file_that_holds_no_json_is_unreadable_and_not_invalid(
    tmp_path: Path,
) -> None:
    """Two is the command reaching no answer, which is neither of the other two."""
    path = tmp_path / "artifact.json"
    path.write_text("this is not an artifact")

    result = runner.invoke(app, ["validate", str(path)])

    assert result.exit_code == 2, result.output
    assert path.name in result.output


# The characters Rich draws a panel's frame with, which a fold inside the
# panel leaves in the middle of a token.
_PANEL_BORDER = str.maketrans("", "", "│─╭╮╰╯┃━┏┓┗┛")


def _unwrapped(output: str) -> str:
    """Return what the console said, with every space the console chose removed.

    Rich folds a long temporary path across lines to fit a terminal, and where
    it folds decides which spaces survive. A fold *inside* a token loses
    nothing. A break at a space takes that space away with the newline, and
    deleting newlines alone then leaves "JSON array" spelled ``JSONarray`` --
    which is what happens the moment the path gains a segment, as it does
    under a worker (``popen-gw0/``). Both breaks are the terminal's choice and
    neither is the message, so the comparison drops all whitespace from the
    output and -- through ``_needle`` -- from the text looked for in it. What
    is asserted is what the message says, never where the terminal broke it.

    A fold inside an error panel also leaves the panel's border on either side
    of the break, so a long path reads ``missing.parq││uet`` on a narrow
    terminal; a Linux runner's temporary paths are long enough to do it. The
    border is the panel's drawing and never the message, so it is dropped
    too.
    """
    return "".join(output.split()).translate(_PANEL_BORDER)


def _needle(wanted: str) -> str:
    """Return a wanted phrase in the shape ``_unwrapped`` leaves output in."""
    return "".join(wanted.split())


def _reached_no_answer(result: Result, named: str) -> None:
    """Assert one run said it reached no answer, in words rather than in a stack.

    Three things together make the status usable: it is 2, the file it is
    about is named, and the command left through its own door. An exception
    escaping instead is a status nobody chose -- and the one it lands on, 1,
    is the code this surface reserves for a finding against a model.
    """
    assert result.exit_code == 2, result.output
    assert _needle(named) in _unwrapped(result.output)
    assert isinstance(result.exception, SystemExit), result.exception


def test_a_parquet_handed_to_validate_is_no_answer_rather_than_a_refusal(
    tmp_path: Path,
) -> None:
    """The likeliest slip on this surface is the file sitting next to the model."""
    path = tmp_path / "model_points.parquet"
    pl.DataFrame({"sum_assured": [100_000.0]}).write_parquet(path)

    result = runner.invoke(app, ["validate", str(path)])

    _reached_no_answer(result, path.name)
    assert _needle("bytes") in _unwrapped(result.output)


def test_a_json_array_is_not_the_object_an_artifact_is(tmp_path: Path) -> None:
    """What a producer writing a list of artifacts hands over."""
    path = tmp_path / "artifact.json"
    path.write_text("[]")

    result = runner.invoke(app, ["validate", str(path)])

    _reached_no_answer(result, path.name)
    assert _needle("JSON array") in _unwrapped(result.output)


def test_json_null_is_not_the_object_an_artifact_is(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    path.write_text("null")

    result = runner.invoke(app, ["validate", str(path)])

    _reached_no_answer(result, path.name)
    assert _needle("JSON null") in _unwrapped(result.output)


def test_a_json_string_is_answered_at_the_door_and_not_read_a_second_time(
    tmp_path: Path,
) -> None:
    """The same rule, kept on purpose: an artifact is a JSON object, never a string.

    A top-level string used to reach the reading, which accepts a path or a
    document and so read the string's own text as though the file had named
    another file. That is a second reading nobody asked for, and it answered
    a finding against a model on the strength of it. A string is not the
    object an artifact is, and it is told so here beside the array and the
    null rather than by accident.
    """
    path = tmp_path / "artifact.json"
    path.write_text('"hello"')

    result = runner.invoke(app, ["validate", str(path)])

    _reached_no_answer(result, path.name)
    assert _needle("JSON string") in _unwrapped(result.output)


def test_a_document_too_deeply_nested_to_parse_is_no_answer_and_not_a_stack(
    tmp_path: Path,
) -> None:
    """The parse either produces a document or it does not, and that is total.

    A file nested past the parser's own depth leaves ``json.loads`` by a
    route that is not a decode error, and a named class per route means the
    routes nobody enumerated escape as a traceback -- on the exit status
    this surface reserves for a finding against a model. Nothing but a
    document can be a verdict, so every way of failing to get one leaves by
    the same door: named file, no answer, status 2.
    """
    path = tmp_path / "artifact.json"
    path.write_text("[" * 50_000 + "]" * 50_000)

    result = runner.invoke(app, ["validate", str(path)])

    _reached_no_answer(result, path.name)
    assert _needle("artifact") in _unwrapped(result.output)


def test_a_verdict_that_cannot_be_stored_is_still_said_first(tmp_path: Path) -> None:
    """A verdict reached and not stored is a job unfinished, not a refusal.

    The reading succeeded and the artifact conforms. Only the storing failed,
    so the reading is on the console where a person can read it, and the
    status says 2 -- because 1 would tell a pipeline that a finding refused
    this model, which nothing here did.
    """
    path = _stored(tmp_path / "artifact.json", _valuation())
    nowhere = tmp_path / "no_such_directory" / "report.json"

    result = runner.invoke(app, ["validate", str(path), "-o", str(nowhere)])

    assert result.exit_code == 2, result.output
    assert _needle("conforms to") in _unwrapped(result.output)
    assert _needle("not stored") in _unwrapped(result.output)
    assert isinstance(result.exception, SystemExit), result.exception


# --- gspio diff ------------------------------------------------------------


def test_two_exports_of_one_untouched_model_are_no_drift(tmp_path: Path) -> None:
    before = _stored(tmp_path / "before.json", _valuation())
    after = _stored(tmp_path / "after.json", _valuation())

    result = runner.invoke(app, ["diff", str(before), str(after)])

    assert result.exit_code == 0, result.output


def test_an_edited_factor_is_drift(tmp_path: Path) -> None:
    before = _stored(tmp_path / "before.json", _valuation(0.00123))
    after = _stored(tmp_path / "after.json", _valuation(0.00456))

    result = runner.invoke(app, ["diff", str(before), str(after)])

    assert result.exit_code == 1, result.output
    assert "death_claims@1" in result.output


def test_a_new_quarter_of_policy_data_is_drift_too(tmp_path: Path) -> None:
    """The widened reading: drift is anything the report covers, not the model alone.

    The model never reads a model point by name, so a run over a replaced
    in-force file moves no calculation at all. A command answering "nothing
    moved" over one is a command a reviewer learns to distrust -- and every
    export now records the book it was built over, so nobody has to have
    named the file for the command to see it.
    """
    earlier = _valuation(sums_assured=(100_000.0,))
    later = _valuation(sums_assured=(100_000.0, 250_000.0))
    before = _stored(tmp_path / "before.json", earlier)
    after = _stored(tmp_path / "after.json", later)

    report = diff_artifacts(earlier, later)
    assert report.calculations == ()

    result = runner.invoke(app, ["diff", str(before), str(after)])

    assert result.exit_code == 1, result.output
    assert "model_points" in result.output


def test_two_books_nothing_can_compare_are_drift_and_the_command_says_why(
    tmp_path: Path,
) -> None:
    """A document with no book digest and no file named is drift, and why is printed."""
    af = ActuarialFrame(pl.DataFrame({"sum_assured": [100_000.0]}))
    af.death_claims = af.sum_assured * 0.00123
    written = build_artifact(fold(af))
    before = _stored(tmp_path / "before.json", written)
    after = _stored(tmp_path / "after.json", written)

    result = runner.invoke(app, ["diff", str(before), str(after)])

    assert result.exit_code == 1, result.output
    said = " ".join(result.output.split())
    assert "The two books could not be compared" in said
    assert "No book was handed to the export" in said


def test_two_byte_grammars_refuse_to_be_compared_and_that_is_not_drift(
    tmp_path: Path,
) -> None:
    before = _stored(tmp_path / "before.json", _valuation())
    later = _valuation()
    later["fingerprint_algorithm"] = f"{FINGERPRINT_ALGORITHM}-and-a-half"
    after = _stored(tmp_path / "after.json", later)

    result = runner.invoke(app, ["diff", str(before), str(after)])

    assert result.exit_code == 2, result.output
    # Both tokens, because a reader told only the strange one cannot tell
    # which of the two files in front of them is the one to re-export.
    assert "and-a-half" in result.output
    assert FINGERPRINT_ALGORITHM in _unwrapped(result.output)


def test_diff_writes_the_report_it_was_asked_for(tmp_path: Path) -> None:
    earlier = _valuation(0.00123)
    later = _valuation(0.00456)
    before = _stored(tmp_path / "before.json", earlier)
    after = _stored(tmp_path / "after.json", later)
    report_path = tmp_path / "report.json"

    result = runner.invoke(
        app, ["diff", str(before), str(after), "--output-file", str(report_path)]
    )

    assert result.exit_code == 1, result.output
    assert (
        json.loads(report_path.read_text()) == diff_artifacts(earlier, later).to_dict()
    )


def test_diff_names_which_of_the_two_it_could_not_read(tmp_path: Path) -> None:
    """Two paths in, so the answer has to say which one it is about."""
    before = _stored(tmp_path / "before.json", _valuation())
    after = tmp_path / "after.json"
    after.write_text("[]")

    result = runner.invoke(app, ["diff", str(before), str(after)])

    _reached_no_answer(result, after.name)


@pytest.mark.skipif(
    importlib.util.find_spec("gaspatchio_viewer") is None,
    reason="the page is the gaspatchio-viewer distribution's; install viewer/python",
)
def test_diff_writes_a_page_carrying_both_documents(tmp_path: Path) -> None:
    """The later document first, the earlier second, both byte for byte.

    The comparison page derives what moved from the two documents rather than from the
    report, so what the command owes it is the two documents -- in an order the
    page can rely on, and unedited, because the seal the page shows has to be a
    seal over bytes a reader can take back out of it.
    """
    earlier = _valuation(0.00123)
    later = _valuation(0.00456)
    before = _stored(tmp_path / "before.json", earlier)
    after = _stored(tmp_path / "after.json", later)
    page = tmp_path / "drift.html"

    result = runner.invoke(app, ["diff", str(before), str(after), "--html", str(page)])

    # Exit 1 because something moved: the page is written either way, and the
    # status is still the report's answer and not the writing's.
    assert result.exit_code == 1, result.output
    html = page.read_text()
    blocks = re.findall(
        r'<script type="application/json" id="artifact"'
        r'(?: data-label="[^"]*")?>(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert len(blocks) == 2
    assert json.loads(blocks[0]) == later
    assert json.loads(blocks[1]) == earlier
    # Built rather than written, and this is the one place it matters: an
    # artifact carries its model's source by default, and the model here is
    # defined in this file, so a literal escape sequence written here would be
    # inside the payload and would be unescaped along with the page's own.
    escape = chr(92) + "u003c"
    assert blocks[0].replace(escape, "<") == after.read_text()
    assert blocks[1].replace(escape, "<") == before.read_text()
    assert "<title>after vs before</title>" in html
    # And the viewer's third-party notices at its end, as every page carries
    # them, read back byte for byte from the bytes on disk.
    written = page.read_bytes().decode("utf-8")
    assert _notices_in(written).encode("utf-8") == _notices_file()


def test_diff_writes_no_page_without_the_viewer_and_says_what_to_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal is calc-graph's, in the same words and with the same exit.

    The report is still printed: it is what the command was asked for, and the
    page is the second half of a request whose first half succeeded.
    """
    monkeypatch.setitem(sys.modules, "gaspatchio_viewer", None)
    before = _stored(tmp_path / "before.json", _valuation(0.00123))
    after = _stored(tmp_path / "after.json", _valuation(0.00456))
    page = tmp_path / "drift.html"

    result = runner.invoke(app, ["diff", str(before), str(after), "--html", str(page)])

    assert result.exit_code == 2, result.output
    said = _unwrapped(result.output)
    assert _needle('pip install "gaspatchio[viewer]"') in said
    # And it says what it did write, which for this command is the report and
    # not an artifact: the sentence calc-graph prints would be false here.
    assert _needle("The report above is the whole answer") in said
    assert _needle("JSON artifact was written") not in said
    assert not page.exists()


# --- gspio calc-graph --profile -------------------------------------------


def test_an_exported_artifact_claims_the_audit_profile_by_default(
    tmp_path: Path,
) -> None:
    model_path, points_path = _model_and_points(tmp_path)
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app, ["calc-graph", str(model_path), str(points_path), "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text())["profile"] == "audit"


def test_the_executable_profile_is_asked_for_and_written(tmp_path: Path) -> None:
    model_path, points_path = _model_and_points(tmp_path)
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(out),
            "--profile",
            "executable",
        ],
    )

    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())
    assert document["profile"] == "executable"
    assert any("expr" in node for node in document["nodes"])


def test_a_profile_this_format_does_not_have_is_refused(tmp_path: Path) -> None:
    model_path, points_path = _model_and_points(tmp_path)

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(tmp_path / "graph.json"),
            "--profile",
            "supervisory",
        ],
    )

    assert result.exit_code != 0
    assert "executable" in result.output


def test_the_command_line_spells_the_profiles_the_format_defines() -> None:
    """One list of names, not two -- the second would drift out of step."""
    assert [profile.value for profile in ConformanceProfile] == [
        PROFILE_AUDIT,
        PROFILE_EXECUTABLE,
    ]


# --- gspio calc-graph, one run ---------------------------------------------

# A column written twice, which the tutorials never do: every value below
# comes out of the one execution the command makes, so the definition that
# was written over can be answered for at all.
SUPERSEDING_MODEL_SRC = """
from gaspatchio import ActuarialFrame, when


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * 0.00123
    af.reserve = af.death_claims - af.premium_received
    af.reserve = when(af.reserve < 0).then(0.0).otherwise(af.reserve)
    return af
"""

# main() reads a column the model points do not carry, which is the ordinary
# way a run fails: the column is attached in a standalone block, or misspelt.
FAILING_MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * af.mortality_rate
    return af
"""


def _superseding_model_and_points(tmp_path: Path) -> tuple[Path, Path]:
    """Return a model that floors a reserve it already struck, and its points.

    The first policy is the one the floor bites on -- its reserve is struck
    negative and replaced with zero -- because with no ``--policy-id`` the
    values in the artifact are read off the first row.
    """
    model_path = tmp_path / "model.py"
    model_path.write_text(SUPERSEDING_MODEL_SRC)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame(
        {
            "policy_id": ["A", "B"],
            "sum_assured": [100_000.0, 250_000.0],
            "premium_received": [200.0, 100.0],
        }
    ).write_parquet(points_path)
    return model_path, points_path


def _node_of(document: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in document["nodes"] if node["id"] == node_id)


def _graph_of(tmp_path: Path, *options: str) -> dict[str, Any]:
    """Export the superseding model from the command line and read it back."""
    model_path, points_path = _superseding_model_and_points(tmp_path)
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app,
        ["calc-graph", str(model_path), str(points_path), "-o", str(out), *options],
    )

    assert result.exit_code == 0, result.output
    return json.loads(out.read_text())


def test_the_summary_names_what_each_sampled_calculation_reads(
    tmp_path: Path,
) -> None:
    """The terminal's sample lines say what each node reads, as the file does.

    Each line is ``node ← what it read``, and what it read is the node's own
    ``reads``. The summary used to look for a member the document does not
    write, so every line ended at the arrow on every model. Each expected line
    is taken from the file the same run wrote, which holds the terminal to the
    document rather than to a second wording of it.
    """
    model_path, points_path = _superseding_model_and_points(tmp_path)
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app, ["calc-graph", str(model_path), str(points_path), "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    sampled = [
        node
        for node in json.loads(out.read_text())["nodes"]
        if node["kind"] == "computed"
    ][:3]
    assert [node["id"] for node in sampled] == [
        "death_claims@1",
        "reserve@1",
        "reserve@2",
    ]
    assert all(node["reads"] for node in sampled)
    printed = " ".join(result.output.split())
    for node in sampled:
        assert f"• {node['id']} ← {', '.join(node['reads'])}" in printed, printed


# --- gspio calc-graph, the tier line ---------------------------------------

# A present value struck in Polars' own language rather than the framework's.
# The line is recorded, so the model accounts for every column it holds, and
# it is still a line only Polars can run -- which is what the tier line says
# and the line above it does not.
DISCOUNTED_IN_POLARS_MODEL_SRC = """
import polars as pl

from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.death_claims = af.sum_assured * 0.00123
    return af.with_columns(
        (pl.col("death_claims") * 0.95).alias("discounted_claims")
    )
"""


def test_the_summary_names_each_tier_under_the_node_count(tmp_path: Path) -> None:
    """Nothing is unaccounted for, and the next line says what is not core.

    The line is held to the file the same run wrote: the tiers the terminal
    names are the ones the document's nodes carry, so the summary and the
    document are one statement rather than two that usually agree.
    """
    model_path = tmp_path / "model.py"
    model_path.write_text(DISCOUNTED_IN_POLARS_MODEL_SRC)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [100_000.0]}).write_parquet(
        points_path
    )
    out = tmp_path / "graph.json"

    result = runner.invoke(
        app, ["calc-graph", str(model_path), str(points_path), "-o", str(out)]
    )

    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())
    assert document["holes"] == []
    assert {node["id"]: node["tier"] for node in document["nodes"] if node["tier"]} == {
        "death_claims@1": "core",
        "discounted_claims@1": "engine_native",
    }
    said = _unwrapped(result.output)
    tier_line = _needle(
        "Calculations by tier: 1 core, 1 engine_native (discounted_claims@1), 0 opaque"
    )
    assert tier_line in said, result.output
    assert (
        said.index(_needle("0 unaccounted for"))
        < said.index(tier_line)
        < said.index("Edges:")
    )


def test_a_model_written_all_in_core_says_so_on_the_tier_line(
    tmp_path: Path,
) -> None:
    """Every tier is stated, a zero included, and no calculation is named."""
    model_path, points_path = _model_and_points(tmp_path)

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(tmp_path / "g.json"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert _needle("Calculations by tier: 1 core, 0 engine_native, 0 opaque") in (
        _unwrapped(result.output)
    )


def test_a_calculation_the_document_gives_no_tier_stops_the_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tier stripped from a calculation is named, not counted as nothing.

    The summary reads the document the run wrote. A calculation there with no
    tier would otherwise vanish from the count, and a model whose every line
    lost its tier would print the all-zero line -- a claim about a model that
    computes. The command says which node, in words and with its own status.
    """
    exported = GraphExporter.export

    def without_a_tier(self: GraphExporter, *args: object, **kwargs: object) -> str:
        document = json.loads(exported(self, *args, **kwargs))
        for node in document["nodes"]:
            if node["id"] == "death_claims@1":
                node["tier"] = None
        return json.dumps(document)

    monkeypatch.setattr(GraphExporter, "export", without_a_tier)
    model_path, points_path = _model_and_points(tmp_path)

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(tmp_path / "g.json"),
        ],
    )

    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), result.exception
    said = _unwrapped(result.output)
    assert _needle("'death_claims@1' is a calculation and carries no tier") in said
    assert _needle("Calculations by tier") not in said


def test_the_tier_line_names_five_at_a_tier_and_says_how_many_more() -> None:
    """A line is for finding the calculations to read; the census holds them all."""
    census = TierCensus(
        core=("claims@1",),
        engine_native=tuple(f"loading_{year}@1" for year in range(1, 9)),
        opaque=("smoothed_claims@1",),
    )

    assert _tier_line(census) == (
        "Calculations by tier: 1 core, 8 engine_native (loading_1@1, "
        "loading_2@1, loading_3@1, loading_4@1, loading_5@1, and 3 more), "
        "1 opaque (smoothed_claims@1)"
    )


def test_five_at_a_tier_are_all_named_on_the_tier_line() -> None:
    """The cap is on what is named, so a tier at the cap needs no "more"."""
    census = TierCensus(
        core=(),
        engine_native=tuple(f"loading_{year}@1" for year in range(1, 6)),
        opaque=(),
    )

    assert _tier_line(census) == (
        "Calculations by tier: 0 core, 5 engine_native (loading_1@1, "
        "loading_2@1, loading_3@1, loading_4@1, loading_5@1), 0 opaque"
    )


def test_the_core_calculations_are_counted_and_never_named() -> None:
    """They are the ones a reader has no reason to go looking for."""
    census = TierCensus(core=("claims@1", "pv@1"), engine_native=(), opaque=())

    assert _tier_line(census) == (
        "Calculations by tier: 2 core, 0 engine_native, 0 opaque"
    )


def test_a_definition_the_model_wrote_over_reaches_the_artifact(
    tmp_path: Path,
) -> None:
    """What the command could not write while it ran the model twice.

    The values a superseded definition produced are carried through the
    collect of the frame that produced them, and an export will only file
    them beside rows that came out of the same execution. Two runs of one
    model are two executions, so the reserve struck before the floor could
    not be shown at all -- whatever either lever was set to. One run, and
    the question a reviewer asks of the file is answerable from the file.
    """
    document = _graph_of(tmp_path)

    struck = _node_of(document, "reserve@1")
    floored = _node_of(document, "reserve@2")

    assert struck["in_final_schema"] is False
    assert struck["retained"] is True
    assert struck["value_sample"] is not None
    # The honesty of it: -77.0 before the floor, 0.0 after. A value read off
    # the finished frame would report the floor's number under the strike's
    # formula, which is the wrong number against the right calculation.
    assert struck["value_sample"] != floored["value_sample"]


def test_retention_declined_writes_the_definition_as_history(
    tmp_path: Path,
) -> None:
    """``--no-retain-superseded`` asks both levers, and both answer no."""
    document = _graph_of(tmp_path, "--no-retain-superseded")

    struck = _node_of(document, "reserve@1")

    assert "retained" not in struck
    assert struck["value_sample"] is None
    assert validate_artifact(document).ok, [
        finding.message for finding in validate_artifact(document).findings
    ]


def test_the_artifact_the_command_writes_is_held_to_every_reading(
    tmp_path: Path,
) -> None:
    """Including the identity one, which is the reading retention moves under."""
    document = _graph_of(tmp_path)

    verdict = validate_artifact(document, deep=True)

    assert verdict.ok, [finding.message for finding in verdict.findings]


def test_a_model_that_raises_is_said_plainly_and_not_thrown(tmp_path: Path) -> None:
    """A run that fails is a message and a status, not a stack.

    The model now runs where the graph is built rather than in a first run
    ahead of it, so this is the same failure arriving by a different route.
    It has to leave by the route it always left by: the one red line, exit
    1, and the diagnosis that names the contract rather than reading as a
    typo hint.
    """
    model_path = tmp_path / "model.py"
    model_path.write_text(FAILING_MODEL_SRC)
    points_path = tmp_path / "model_points.parquet"
    pl.DataFrame({"policy_id": ["A"], "sum_assured": [100_000.0]}).write_parquet(
        points_path
    )

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(tmp_path / "graph.json"),
        ],
    )

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit), result.exception
    assert "Error running model" in result.output
    assert "mortality_rate" in result.output
    assert "outside main()" in result.output


def test_a_policy_the_file_does_not_hold_is_answered_before_the_model_runs(
    tmp_path: Path,
) -> None:
    """The narrowing moved into this command, and it still refuses the same.

    A policy number typed from memory used to be caught by the single-policy
    run this command no longer makes. It is caught by the selector instead,
    before the model starts, with the ids the file does hold and the size of
    the book it does not hold them in -- rather than by an empty frame
    somewhere inside the model.

    Its own exit status, and that is the point of having one: nothing ran,
    so a caller branching on the status can tell "your command line named a
    policy that is not there" from "your model raised".
    """
    model_path, points_path = _superseding_model_and_points(tmp_path)

    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model_path),
            str(points_path),
            "-o",
            str(tmp_path / "graph.json"),
            "--policy-id",
            "Z",
        ],
    )

    assert result.exit_code == 3
    assert isinstance(result.exception, SystemExit), result.exception
    assert "is not in column" in result.output
    assert "policies" in result.output
