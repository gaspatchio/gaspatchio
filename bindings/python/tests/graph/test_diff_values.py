# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio diff`` reads the two runs' results files: what moved, and by how much.

Seven rooms converting workbooks each wrote the same script: run ``gspio diff``,
then read the two results files and join them on the policy id to see which of
the flagged calculations actually moved a number. These fixtures are the cases
those scripts were written for, each asserted in both directions -- the later
run against the earlier and the earlier against the later -- because a
comparison that only reads one way round is two different comparisons.

Every quarter here is a real run: ``gspio calc-graph --results`` over a model
file and a book, which writes the results file and the audit file naming it, so
``gspio diff`` finds the two files the way it does for a reviewer.

- (a) a table row no policy reaches, edited: flagged, and no number moved;
- (b) a formula edited over a zero multiplicand: an edit that moved no number;
- (c) a policy added and one lapsed: joined and left, and the book named as
  what moved the numbers of the policies both books hold;
- (d) a horizon moved: the timeline's length moved, the shared periods compared;
- (e) a second producer whose arithmetic differs in the last places: moved,
  inside the band, the producer named;
- (f) a column written over around the frame's account of it: unexplained,
  and drift;
- (g) a formula times 1.000001: moved beyond the band.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines.protocol import read_manifest, write_with_manifest
from gaspatchio.frame.graph import diff_with_results
from gaspatchio.frame.graph.diff_results import page_movement

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_BOOK = pl.DataFrame(
    {
        "policy_id": ["P1", "P2", "P3"],
        "age": [30, 40, 30],
        "premium": [1_200.0, 3_400.0, 900.0],
        "sum_assured": [100_000.0, 250_000.0, 80_000.0],
        "comm_rate": [0.0, 0.0, 0.0],
    }
)

_RATES = pl.DataFrame({"age": [30, 40, 50], "rate": [0.001, 0.002, 0.003]})

_PLAIN = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.reserve = af.premium * {factor}
    af.total = af.reserve * 2
    return af
"""

_LOOKUP = """
from pathlib import Path

import polars as pl

from gaspatchio import ActuarialFrame
from gaspatchio.assumptions import Table

HERE = Path(__file__).parent


def main(af: ActuarialFrame) -> ActuarialFrame:
    rates = Table(
        name="mortality",
        source=pl.read_parquet(HERE / "mortality.parquet"),
        dimensions={"age": "age"},
        value="rate",
    )
    af.q = rates.lookup(age=af.age)
    af.claims = af.sum_assured * af.q
    af.premium_net = af.premium - af.claims
    return af
"""

_COMMISSION = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.commission = af.premium * af.comm_rate{edit}
    af.net = af.premium - af.commission
    return af
"""

_HORIZON = """
import datetime

from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af = af.projection.set(
        valuation_date=datetime.date({start}),
        until="term_years",
        until_value={term},
        frequency="annual",
    )
    af.reserve = af.premium * af.month
    return af
"""


def _version(
    folder: Path,
    source: str,
    *,
    book: pl.DataFrame = _BOOK,
    rates: pl.DataFrame | None = None,
) -> tuple[Path, Path]:
    """Run ``source`` over ``book`` with ``calc-graph``, its results file named."""
    folder.mkdir()
    model = folder / "model.py"
    model.write_text(source)
    if rates is not None:
        rates.write_parquet(folder / "mortality.parquet")
    points = folder / "book.parquet"
    book.write_parquet(points)
    audit = folder / "model.audit.json"
    results = folder / "results.parquet"
    ran = runner.invoke(
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


def _diff(before: Path, after: Path, *flags: str) -> tuple[int, dict[str, Any]]:
    """Run ``gspio diff --json`` and return its exit status and its report."""
    ran = runner.invoke(app, ["diff", str(before), str(after), "--json", *flags])
    assert ran.exit_code in (0, 1), ran.output
    return ran.exit_code, json.loads(ran.stdout)


def _lines(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the report's value lines by node."""
    return {line["node"]: line for line in report["values"]["lines"]}


def _both_ways(
    earlier: Path, later: Path, *flags: str
) -> list[tuple[int, dict[str, Any]]]:
    """Return the comparison of the two runs read each way round."""
    return [_diff(earlier, later, *flags), _diff(later, earlier, *flags)]


# --- (a) a row no policy reaches ----------------------------------------------


def test_a_an_unreached_row_flags_lines_and_moves_no_number(tmp_path: Path) -> None:
    """Re-sourcing a row no policy reaches flags every line reading the table.

    The identity cannot say whether a row is reached -- that depends on the
    book -- so the lookup and everything below it are flagged as inherited.
    The two results files say what happened: nothing moved, and those lines
    moved only in identity.
    """
    unreached = _RATES.with_columns(
        pl.when(pl.col("age") == 50).then(0.004).otherwise(pl.col("rate")).alias("rate")
    )
    q1 = _version(tmp_path / "q1", _LOOKUP, rates=_RATES)
    q2 = _version(tmp_path / "q2", _LOOKUP, rates=unreached)

    for status, report in _both_ways(q1[0], q2[0]):
        flagged = [change["node"] for change in report["calculations"]]
        head = report["values"]["headline"]
        assert flagged == ["q@1", "claims@1", "premium_net@1"]
        assert head["inherited"] == {"moved": [], "identity_only": flagged}
        assert head["edited"] == {"moved": [], "moved_no_number": []}
        assert not any(line["moved"] for line in report["values"]["lines"])
        assert report["values"]["results"]["after"]["read"] == "recorded"
        # The table moved, so this is still drift: what is drift has not changed.
        assert status == 1


# --- (b) an edit over a zero ----------------------------------------------------


def test_b_an_edit_over_a_zero_multiplicand_moves_no_number(tmp_path: Path) -> None:
    """An edited formula whose new factor multiplies a zero is an edit and no move."""
    q1 = _version(tmp_path / "q1", _COMMISSION.format(edit=""))
    q2 = _version(tmp_path / "q2", _COMMISSION.format(edit=" * 1.01"))

    for status, report in _both_ways(q1[0], q2[0]):
        head = report["values"]["headline"]
        assert head["edited"] == {"moved": [], "moved_no_number": ["commission@1"]}
        assert head["inherited"] == {"moved": [], "identity_only": ["net@1"]}
        assert status == 1


# --- (c) new business and a lapse --------------------------------------------


def test_c_a_policy_joined_and_one_left_and_the_book_moved_the_rest(
    tmp_path: Path,
) -> None:
    """Two books holding different policies are paired, never refused.

    P1 lapsed and P4 joined; P2's premium was revised. The policies both
    books hold are compared, the two counts name the others, and a line whose
    definition did not move and whose numbers did is put down to the book.
    """
    later_book = pl.DataFrame(
        {
            "policy_id": ["P2", "P3", "P4"],
            "age": [40, 30, 50],
            "premium": [3_500.0, 900.0, 2_000.0],
            "sum_assured": [250_000.0, 80_000.0, 120_000.0],
            "comm_rate": [0.0, 0.0, 0.0],
        }
    )
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.9"), book=later_book)

    (status, forward), (back_status, backward) = _both_ways(q1[0], q2[0])

    assert forward["values"]["rows"]["joined"] == {"count": 1, "policies": ["P4"]}
    assert forward["values"]["rows"]["left"] == {"count": 1, "policies": ["P1"]}
    assert backward["values"]["rows"]["joined"] == {"count": 1, "policies": ["P1"]}
    assert backward["values"]["rows"]["left"] == {"count": 1, "policies": ["P4"]}
    for report in (forward, backward):
        assert report["calculations"] == []
        assert report["values"]["rows"]["paired"] == 2
        assert report["values"]["cause"] == "book"
        moved = report["values"]["headline"]["unmoved_definitions"]["book"]
        assert moved == ["premium", "reserve@1", "total@1"]
        reserve = _lines(report)["reserve@1"]
        assert (reserve["policies_moved"], reserve["policies_compared"]) == (1, 2)
        assert reserve["worst"]["policy"] == "P2"
    assert _lines(forward)["reserve@1"]["worst"]["before"] == 3_060.0
    assert _lines(backward)["reserve@1"]["worst"]["after"] == 3_060.0
    assert status == back_status == 1


# --- (d) a horizon ---------------------------------------------------------------


def test_d_a_longer_horizon_moves_the_length_and_compares_the_shared_periods(
    tmp_path: Path,
) -> None:
    """Five annual boundaries against four: the four both hold agree."""
    q1 = _version(tmp_path / "q1", _HORIZON.format(start="2025, 1, 1", term=3))
    q2 = _version(tmp_path / "q2", _HORIZON.format(start="2025, 1, 1", term=4))

    for at, (status, report) in enumerate(_both_ways(q1[0], q2[0])):
        reserve = _lines(report)["reserve@1"]
        assert report["values"]["periods"] == {"aligned": True, "reason": None}
        assert reserve["moved"] is True
        assert reserve["cells_moved"] == 0
        assert reserve["cells_compared"] == 12
        assert reserve["first_period_moved"] == 4
        lengths = (4, 5) if at == 0 else (5, 4)
        assert reserve["length_moved"] == {
            "policies": 3,
            "policy": "P1",
            "before": lengths[0],
            "after": lengths[1],
        }
        assert reserve["within_band"] is False
        assert status == 1


def test_two_valuation_dates_compare_only_the_lines_of_one_value(
    tmp_path: Path,
) -> None:
    """A timeline starting a year later has no period t in common with the first."""
    q1 = _version(tmp_path / "q1", _HORIZON.format(start="2025, 1, 1", term=3))
    q2 = _version(tmp_path / "q2", _HORIZON.format(start="2026, 1, 1", term=3))

    for _, report in _both_ways(q1[0], q2[0]):
        periods = report["values"]["periods"]
        lines = _lines(report)
        assert periods["aligned"] is False
        assert "start on different dates for 3 of the 3 policies" in periods["reason"]
        assert lines["reserve@1"]["compared"] is False
        assert lines["projection_start_date@1"]["compared"] is True
        assert lines["projection_start_date@1"]["moved"] is True


# --- (e) another producer ------------------------------------------------------


def _rewritten(
    results: Path, to: Path, column: str, factor: float, *, producer: str | None = None
) -> Path:
    """Write ``results`` again with one column scaled, under its own manifest.

    The manifest says the file is a result of the same artifact, so the file
    stands for a run whose numbers moved with nothing in the record to say
    why -- or, given another ``producer``, a run another engine computed.
    """
    manifest = read_manifest(results)
    if producer is not None:
        manifest = dataclasses.replace(manifest, producer=producer)
    frame = pl.read_parquet(results).with_columns(pl.col(column) * factor)
    write_with_manifest(frame, manifest, to)
    return to


def test_e_another_producer_moves_lines_inside_the_band_and_is_named(
    tmp_path: Path,
) -> None:
    """A second engine's last-place differences are moves, labelled, not drift.

    The same audit file on both sides; the later results are the earlier
    ones as another producer computed them, one line a part in 1e15 away.
    """
    audit, results = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    other = _rewritten(
        results, tmp_path / "other.parquet", "reserve", 1 + 2**-50, producer="jax"
    )

    for flags in (
        ("--results", str(results), str(other)),
        ("--results", str(other), str(results)),
    ):
        status, report = _diff(audit, audit, *flags)
        values = report["values"]
        assert values["cause"] == "producer"
        assert values["headline"]["unmoved_definitions"]["producer"] == ["reserve@1"]
        assert values["headline"]["within_band"] == ["reserve@1"]
        assert _lines(report)["reserve@1"]["within_band"] is True
        assert status == 0


# --- (f) a column written around the frame -------------------------------------


def test_f_a_column_written_around_the_frame_is_unexplained_drift(
    tmp_path: Path,
) -> None:
    """The record says nothing moved; the numbers say otherwise.

    One audit file, one book, one producer, and a results file whose reserve
    is not what the recorded definition gives: no definition, book or engine
    explains it, so it is named as unexplained and the command exits 1.
    """
    audit, results = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    written = _rewritten(results, tmp_path / "written.parquet", "reserve", 1.1)

    for flags in (
        ("--results", str(results), str(written)),
        ("--results", str(written), str(results)),
    ):
        status, report = _diff(audit, audit, *flags)
        assert report["calculations"] == []
        assert report["data"] == []
        assert report["values"]["headline"]["unmoved_definitions"] == {
            "book": [],
            "hole": [],
            "producer": [],
            "unexplained": ["reserve@1"],
        }
        assert report["drift"] is True
        assert status == 1


def test_f_the_command_names_the_unexplained_line_in_a_sentence(
    tmp_path: Path,
) -> None:
    """The text says what the JSON says, and what to run to find the line."""
    audit, results = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    written = _rewritten(results, tmp_path / "written.parquet", "reserve", 1.1)

    ran = runner.invoke(
        app, ["diff", str(audit), str(audit), "--results", str(results), str(written)]
    )

    said = " ".join(ran.output.split())
    assert ran.exit_code == 1
    assert "reserve@1 moved under definitions that did not" in said
    assert "nothing in the record explains it" in said


# --- (g) the mutation control ---------------------------------------------------


@pytest.mark.parametrize(
    ("factor", "band"),
    [("0.9 * 1.000001", "beyond"), ("0.9 * (1 + 1e-14)", "inside")],
    ids=["beyond-the-band", "inside-the-band"],
)
def test_g_an_edit_moves_beyond_the_band_or_is_labelled_inside_it(
    tmp_path: Path, factor: str, band: str
) -> None:
    """A formula times 1.000001 moves; times 1 + 1e-14 is labelled, and still listed."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor=factor))

    for status, report in _both_ways(q1[0], q2[0]):
        reserve = _lines(report)["reserve@1"]
        assert reserve["change"] == "self"
        assert reserve["moved"] is True
        assert reserve["policies_moved"] == 3
        assert reserve["within_band"] is (band == "inside")
        assert report["values"]["headline"]["edited"]["moved"] == ["reserve@1"]
        assert status == 1


# --- what the report says it read ---------------------------------------------


def test_the_report_names_its_grammar_and_a_null_values_without_results(
    tmp_path: Path,
) -> None:
    """Two audit files with no results files have nothing to measure: values is null."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.8"))

    _, read = _diff(q1[0], q2[0])
    _, skipped = _diff(q1[0], q2[0], "--no-results")

    assert read["report_version"] == "gaspatchio-graph-diff/v0-preview.2"
    assert read["values"] is not None
    assert skipped["values"] is None


def test_a_results_file_rewritten_since_its_run_is_not_read_and_the_line_says_why(
    tmp_path: Path,
) -> None:
    """The checksum decides which file is the run's, and the sentence names the side."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.8"))
    _rewritten(q2[1], q2[1], "reserve", 1.0)
    pl.read_parquet(q2[1]).write_parquet(q2[1], compression="uncompressed")

    ran = runner.invoke(app, ["diff", str(q1[0]), str(q2[0])])

    said = " ".join(ran.output.split())
    assert ran.exit_code == 1
    assert "The values were not compared" in said
    assert "is not the results file the later audit file records" in said
    assert "--results EARLIER LATER" in said


def test_a_results_file_gone_from_where_it_was_written_says_where_it_looked(
    tmp_path: Path,
) -> None:
    """A recorded file that is not there is named, with the directories searched."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.8"))
    q1[1].unlink()

    ran = runner.invoke(app, ["diff", str(q1[0]), str(q2[0]), "--json"])

    assert ran.exit_code == 1
    assert json.loads(ran.stdout)["values"] is None
    said = " ".join(ran.stderr.split())
    assert "the earlier audit file records its results file at results.parquet" in said


def test_results_and_no_results_together_are_refused(tmp_path: Path) -> None:
    """Two flags asking for opposite things exit 2 before anything is read."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))

    ran = runner.invoke(
        app,
        [
            "diff",
            str(q1[0]),
            str(q1[0]),
            "--no-results",
            "--results",
            str(q1[1]),
            str(q1[1]),
        ],
    )

    assert ran.exit_code == 2
    assert "ask for opposite things" in " ".join(ran.output.split())


def test_a_named_file_of_another_artifact_exits_2_naming_its_side(
    tmp_path: Path,
) -> None:
    """Results named with --results are held to their own audit file, untraced."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.8"))

    ran = runner.invoke(
        app, ["diff", str(q1[0]), str(q2[0]), "--results", str(q2[1]), str(q1[1])]
    )

    said = " ".join(ran.output.split())
    assert ran.exit_code == 2
    assert "The earlier results are not of the earlier artifact" in said
    assert "Traceback" not in ran.output


def test_two_files_recording_no_identity_over_two_books_are_not_paired(
    tmp_path: Path,
) -> None:
    """Position pairs rows only over one book; otherwise the command asks for one."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    bare = _BOOK.rename({"policy_id": "contract"})
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.9"), book=bare.reverse())
    for results in (q1[1], q2[1]):
        manifest = read_manifest(results)
        anonymous = dataclasses.replace(manifest, row_identity=None)
        write_with_manifest(pl.read_parquet(results), anonymous, results)

    ran = runner.invoke(
        app, ["diff", str(q1[0]), str(q2[0]), "--results", str(q1[1]), str(q2[1])]
    )
    told = runner.invoke(
        app,
        [
            "diff",
            str(q1[0]),
            str(q2[0]),
            "--results",
            str(q1[1]),
            str(q2[1]),
            "--json",
            "--policy-id-column",
            "premium",
        ],
    )

    assert ran.exit_code == 2
    assert "--policy-id-column" in " ".join(ran.output.split())
    paired = json.loads(told.stdout)["values"]["rows"]
    assert paired == {
        "matched_by": "identity",
        "on": ["premium"],
        "paired": 3,
        "joined": {"count": 0, "policies": []},
        "left": {"count": 0, "policies": []},
    }


def test_the_floor_cuts_the_printed_list_and_never_the_json(tmp_path: Path) -> None:
    """A reader's floor is a reading aid: the stored report keeps every line."""
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.9 * 1.000001"))

    shown = runner.invoke(app, ["diff", str(q1[0]), str(q2[0])])
    cut = runner.invoke(app, ["diff", str(q1[0]), str(q2[0]), "--floor", "1"])
    stored = runner.invoke(
        app, ["diff", str(q1[0]), str(q2[0]), "--floor", "1", "--json"]
    )

    assert "Moved, largest relative move first" in shown.output
    assert "Moved, largest relative move first" not in cut.output
    assert "2 moved lines under the floor of 1.0% not shown" in cut.output
    assert _lines(json.loads(stored.stdout))["reserve@1"]["moved"] is True


@pytest.mark.skipif(
    importlib.util.find_spec("gaspatchio_viewer") is None,
    reason="the page is the gaspatchio-viewer distribution's; install viewer/python",
)
def test_the_page_carries_the_book_s_reading_where_the_values_were_read(
    tmp_path: Path,
) -> None:
    """``--html`` puts the values member in the page beside the two documents.

    Compact, in a block of its own; and no block where no results file was
    read, so the page shows only what it derives.
    """
    q1 = _version(tmp_path / "q1", _PLAIN.format(factor="0.9"))
    q2 = _version(tmp_path / "q2", _PLAIN.format(factor="0.8"))
    read = tmp_path / "read.html"
    unread = tmp_path / "unread.html"

    runner.invoke(app, ["diff", str(q1[0]), str(q2[0]), "--html", str(read)])
    runner.invoke(
        app, ["diff", str(q1[0]), str(q2[0]), "--no-results", "--html", str(unread)]
    )
    _, report = _diff(q1[0], q2[0])

    page = read.read_text("utf-8")
    block = json.dumps(report["values"], separators=(",", ":"))
    assert f'<script type="application/json" id="movement">{block}</script>' in page
    assert 'id="movement"' not in unread.read_text("utf-8")


# --- the two readings -------------------------------------------------------------


def test_the_declared_policy_reads_the_same_from_the_files_as_from_the_samples(
    tmp_path: Path,
) -> None:
    """The comparison page's reading of its one policy, held to the results files'.

    The page derives what moved for the policy the two artifacts carry from
    the artifacts' own values. The report states the same policy's movement
    read from the two results files. One definition, two readings: they must
    agree line for line, in which lines moved and by how much.
    """
    q1 = _version(tmp_path / "q1", _HORIZON.format(start="2025, 1, 1", term=3))
    q2_source = _HORIZON.format(start="2025, 1, 1", term=4).replace(
        "af.premium * af.month", "af.premium * af.month * 1.5"
    )
    q2 = _version(tmp_path / "q2", q2_source)
    earlier = json.loads(q1[0].read_text())
    later = json.loads(q2[0].read_text())

    report = diff_with_results(earlier, later, q1[1], q2[1])

    assert report.values is not None
    declared = report.values.declared
    assert declared is not None
    assert declared.policy == "P1"
    from_the_files = {
        line.node: (line.magnitude, line.from_zero, line.period)
        for line in declared.lines
    }
    samples = {node["id"]: node.get("value_sample") for node in earlier["nodes"]}
    from_the_samples = {}
    for node in later["nodes"]:
        if node["id"] not in samples or node["id"] not in _lines(report.to_dict()):
            continue
        moved, magnitude, period, from_zero = page_movement(
            samples[node["id"]], node.get("value_sample")
        )
        if moved:
            from_the_samples[node["id"]] = (magnitude, from_zero, period)
    assert from_the_files == from_the_samples
    assert from_the_files["reserve@1"] == (0.5, False, 1)


# --- the vector the page is held to -----------------------------------------------


def _the_vector() -> Path | None:
    """Return the committed values vector's directory, or None outside this tree."""
    from pathlib import Path

    found = Path(__file__).resolve().parents[4] / "viewer" / "fixtures" / "values"
    return found if (found / "export.py").is_file() else None


def _vector_export(where: Path) -> Any:  # noqa: ANN401 -- a module loaded by path
    """Load the vector's export script, which states how the report is taken."""
    spec = importlib.util.spec_from_file_location("values_export", where / "export.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(_the_vector() is None, reason="needs this repository's viewer/")
def test_the_committed_vector_is_the_report_diff_writes() -> None:
    """The page's tests read this report, so the report is held to the code.

    ``viewer/fixtures/values-report.json`` is taken over the two committed
    documents and the two committed results files; taken again here, it must
    be the same report, byte for byte. Written again by
    ``viewer/fixtures/values/export.py``.
    """
    where = _the_vector()
    assert where is not None
    export = _vector_export(where)

    again = json.dumps(export.report(), indent=2) + "\n"

    assert again == export.REPORT.read_text("utf-8"), (
        "the committed values report is stale: run "
        "viewer/fixtures/values/export.py from bindings/python"
    )


@pytest.mark.skipif(_the_vector() is None, reason="needs this repository's viewer/")
def test_the_vector_reads_its_policy_alike_from_the_files_and_the_samples() -> None:
    """The second reading, over the committed vector: what the page derives."""
    where = _the_vector()
    assert where is not None
    export = _vector_export(where)
    earlier, later = (
        json.loads(export.document(version).read_text("utf-8"))
        for version in export.VERSIONS
    )
    report = json.loads(export.REPORT.read_text("utf-8"))
    compared = {
        line["node"] for line in report["values"]["lines"] if line["paired_by"] == "id"
    }
    samples = {node["id"]: node.get("value_sample") for node in earlier["nodes"]}

    from_the_samples = {}
    for node in later["nodes"]:
        if node["id"] not in compared:
            continue
        moved, magnitude, period, from_zero = page_movement(
            samples[node["id"]], node.get("value_sample")
        )
        if moved:
            from_the_samples[node["id"]] = [magnitude, from_zero, period]

    declared = report["values"]["declared"]
    assert declared["policy"] == later["policies"][0]["policy_id"]
    assert from_the_samples == {
        line["node"]: [line["magnitude"], line["from_zero"], line["period"]]
        for line in declared["lines"]
    }
