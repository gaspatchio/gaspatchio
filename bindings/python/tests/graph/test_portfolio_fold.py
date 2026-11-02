# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The book's own fold, and the entry of the policy axis it sits on.

An artifact carrying policies answers *how does this one differ from that
one?* and leaves *what is the BEL?* exactly where it was. ``--portfolio``
answers the second, and three things have to hold or the answer is worse than
not having one.

**The fold is the model's own, over the whole book.** Every total below is
checked against the same column of the same run's finished frame rather than
against a number written into this file. A producer that re-summed the handful
of policies the document happens to carry would publish a figure that is
nobody's under a name that says it is the book's, and the check that catches
that is the only check worth writing.

**A column no accumulator covers says nothing.** There is no portfolio value
of a monthly mortality rate. The entry carries a null at that node's position,
which is §8's own rule -- a producer with nothing to write at one position
writes a null there -- and never a figure it arrived at by summing rates.

**A refusal names what to do.** A model declaring no accumulators and a bare
``--portfolio`` is refused, because which columns a portfolio total is taken
over is an actuarial decision. Each refusal below has a test that reads the
sentence and not only the exit code: a sentence nobody asserts is a sentence
that rots into "Error: None" without anything failing.

The book these run over is the policy axis's own awkward one -- string ids,
shuffled, one id shaped like a slice, one carried by two rows -- and its
``band`` column is the cut the grouped folds are taken over. A grouped fold is
the scenario case in miniature: a scenario axis is a cross-join on the model
points and a fold over one reads each cut separately, and ``band`` exercises
the same path without a scenario frame to build.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app

if TYPE_CHECKING:
    from collections.abc import Sequence

runner = CliRunner()

# The awkward book the policy axis is tested over, carrying a two-valued
# `band` for the grouped folds to cut on.
_BOOK = Path(__file__).resolve().parents[1] / "fixtures" / "policy-axis-book.parquet"

# The exit code a refused command line carries. A fold nobody declared is the
# same kind of thing as a selection that names no honest set of model points.
_REFUSED = 3

# The model, less its accumulators, which each test supplies. `reserve` holds
# one value per period and `pv_reserve` one per policy, so both shapes of fold
# have a column to land on, and `mort_rate` is the column with no portfolio
# value that nothing ever folds.
_MODEL = """
import datetime

from gaspatchio import ActuarialFrame, when
{declaration}


def main(af, params=None):
    mp = af.collect()
    af = ActuarialFrame(mp)
    af = af.projection.set(
        valuation_date=datetime.date(2025, 1, 1),
        until="term_years",
        until_value=4,
        frequency="annual",
    )
    af.duration = af.month // 12
    af.mort_rate = 0.001 * (af.duration + 1)
    af.in_force = when(af.duration < af.policy_term).then(1.0).otherwise(0.0)
    af.reserve = af.sum_assured * 0.01 * (af.duration + 1) * af.in_force
    af.pv_reserve = af.reserve.list.sum()
    return af
"""

_DECLARES = """
from gaspatchio.scenarios import PeriodSum, Sum

AGGREGATIONS = (Sum("pv_reserve"), PeriodSum("reserve"))
"""

_DECLARES_GROUPED = """
from gaspatchio.scenarios import Sum

AGGREGATIONS = (Sum("pv_reserve").alias("pv_reserve").over("band"),)
"""

_DECLARES_A_CUT_NOBODY_HAS = """
from gaspatchio.scenarios import Sum

AGGREGATIONS = (Sum("pv_reserve").alias("pv_reserve").over("scenario_id"),)
"""


@pytest.fixture
def model(tmp_path: Path) -> Path:
    """Write the model declaring the ordinary pair, and return its path."""
    return _written(tmp_path, _DECLARES)


@pytest.fixture
def silent(tmp_path: Path) -> Path:
    """Write the same model declaring no accumulators at all."""
    return _written(tmp_path, "")


def _written(tmp_path: Path, declaration: str) -> Path:
    """Write the model with one declaration in it, and return its path."""
    written = tmp_path / "model.py"
    written.write_text(_MODEL.format(declaration=declaration))
    return written


def _export(model: Path, out: Path, *extra: str) -> Any:  # noqa: ANN401 -- the runner's own result
    """Run ``calc-graph`` over the awkward book and return the runner result."""
    return runner.invoke(
        app,
        ["calc-graph", str(model), str(_BOOK), "-o", str(out), *extra],
    )


def _folded(model: Path, out: Path, *extra: str) -> dict[str, Any]:
    """Export with a fold and return the document, refusing to guess on failure."""
    result = _export(model, out, "--portfolio", *extra)
    assert result.exit_code == 0, result.output
    return json.loads(out.read_text())


def _refusal(model: Path, out: Path, *extra: str) -> str:
    """Return the sentence one refused export was refused with."""
    result = _export(model, out, *extra)
    assert result.exit_code == _REFUSED, result.output
    return result.output


def _at(document: dict[str, Any], node_id: str, position: int) -> Any:  # noqa: ANN401 -- one sampled value, of whatever shape the column holds
    """Return what one node states at one position of the axis."""
    node = next(one for one in document["nodes"] if one["id"] == node_id)
    held = node.get("value_sample")
    assert isinstance(held, list), f"{node_id} carries no axis-aligned sample"
    assert len(held) == len(document["policies"])
    return held[position]


def _folds(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the entries of the axis that are folds of the book."""
    return [entry for entry in document["policies"] if entry["aggregation"] is not None]


def _results(model: Path, out: Path) -> pl.DataFrame:
    """Return the finished frame of a plain run of the same model over the book."""
    written = out.parent / "results.parquet"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(_BOOK),
            "-o",
            str(out),
            "--output-file",
            str(written),
        ],
    )
    assert result.exit_code == 0, result.output
    return pl.read_parquet(written)


# --- the entry ----------------------------------------------------------------


def test_the_fold_sits_at_the_head_of_the_axis(model: Path, tmp_path: Path) -> None:
    """A reader who opened a portfolio document opened it for the book's total."""
    document = _folded(model, tmp_path / "graph.json")

    axis = document["policies"]
    assert [entry["aggregation"] for entry in axis] == ["sum", "period_sum", None]
    assert axis[0]["policy_id"] is None
    assert axis[-1]["policy_id"] is not None


def test_the_envelope_restates_the_fold_as_its_enrichment(
    model: Path, tmp_path: Path
) -> None:
    """The member section 7 defined when the format was drafted, finally written.

    A consumer of the edition before the axis reads `enrichment` and nothing
    else, and what it then reads is exactly what that edition defined the two
    members for: no policy, and an aggregation naming how the values across
    policies were combined.
    """
    document = _folded(model, tmp_path / "graph.json")

    head = {
        name: value for name, value in document["policies"][0].items() if name != "why"
    }
    assert document["enrichment"] == head
    assert document["enrichment"]["aggregation"] == "sum"
    assert document["enrichment"]["policy_id"] is None


def test_every_entry_says_what_it_is_an_account_of(model: Path, tmp_path: Path) -> None:
    """``why`` is on a fold entry for the same reason it is on a policy's."""
    document = _folded(model, tmp_path / "graph.json")

    said = [entry["why"] for entry in _folds(document)]
    assert said == [
        "the whole book, folded by sum over 8 policies in policy-axis-book.parquet",
        "the whole book, folded by period_sum over 8 policies in policy-axis-book.parquet",
    ]


# --- the numbers --------------------------------------------------------------


def test_the_fold_is_the_run_s_own_total(model: Path, tmp_path: Path) -> None:
    """Checked against the column, not against a number written into this file.

    The one check worth writing: a producer that re-summed the policies the
    document carries would pass every test above and publish a total of one
    policy under the book's name.
    """
    out = tmp_path / "graph.json"
    frame = _results(model, out)
    document = _folded(model, out)

    assert _at(document, "pv_reserve@1", 0) == pytest.approx(
        frame["pv_reserve"].sum(), rel=0, abs=1e-6
    )


def test_a_per_period_column_is_folded_down_its_own_timeline(
    model: Path, tmp_path: Path
) -> None:
    """One number per period, each the book's total at that period."""
    out = tmp_path / "graph.json"
    frame = _results(model, out)
    document = _folded(model, out)

    folded = _at(document, "reserve@1", 1)
    periods = max(len(one) for one in frame["reserve"].to_list())
    assert isinstance(folded, list)
    assert len(folded) == periods
    for period in range(periods):
        down = sum(
            one[period] for one in frame["reserve"].to_list() if len(one) > period
        )
        assert folded[period] == pytest.approx(down, rel=0, abs=1e-6)


def test_the_book_is_folded_whole_however_few_policies_are_carried(
    model: Path, tmp_path: Path
) -> None:
    """A selection says what is sampled and never what is computed, or folded."""
    out = tmp_path / "graph.json"
    frame = _results(model, out)
    one = _folded(model, out, "--policies", ":1")
    several = _folded(model, tmp_path / "two.json", "--policies", ":3")

    whole = frame["pv_reserve"].sum()
    assert _at(one, "pv_reserve@1", 0) == pytest.approx(whole, rel=0, abs=1e-6)
    assert _at(several, "pv_reserve@1", 0) == pytest.approx(whole, rel=0, abs=1e-6)


# --- what the fold does not cover ---------------------------------------------


def test_a_column_no_accumulator_covers_is_null(model: Path, tmp_path: Path) -> None:
    """There is no portfolio value of a mortality rate, so the file states none."""
    document = _folded(model, tmp_path / "graph.json")

    assert _at(document, "mort_rate@1", 0) is None
    assert _at(document, "mort_rate@1", 1) is None
    # And it is a policy's own run of values again on the entry beneath them.
    assert isinstance(_at(document, "mort_rate@1", 2), list)


def test_a_fold_carries_no_walk_through_at_all(model: Path, tmp_path: Path) -> None:
    """Nothing ran once over the book for a reader to be walked through."""
    document = _folded(model, tmp_path / "graph.json")

    for node in document["nodes"]:
        trace = node.get("trace")
        if trace is None:
            continue
        assert trace[0] is None
        assert trace[1] is None
    assert _at(document, "pv_reserve@1", 0) is not None


def test_the_axis_stays_one_length_throughout(model: Path, tmp_path: Path) -> None:
    """A node shorter than the axis puts values under some other entry's name."""
    document = _folded(model, tmp_path / "graph.json")

    width = len(document["policies"])
    for node in document["nodes"]:
        for field in ("value_sample", "trace", "branches"):
            held = node.get(field)
            if held is None:
                continue
            assert isinstance(held, list), (node["id"], field)
            assert len(held) == width, (node["id"], field)


# --- a fold of one cut of the book --------------------------------------------


def test_a_grouped_fold_is_one_entry_per_cut(tmp_path: Path) -> None:
    """Each stating its cut in the member the format already defines for it."""
    grouped = _written(tmp_path, _DECLARES_GROUPED)
    out = tmp_path / "graph.json"
    frame = _results(grouped, out)
    document = _folded(grouped, out)

    entries = _folds(document)
    assert [entry["filter"] for entry in entries] == [
        'band == "preferred"',
        'band == "standard"',
    ]
    assert [entry["aggregation"] for entry in entries] == ["sum", "sum"]
    per_cut = dict(frame.group_by("band").agg(pl.col("pv_reserve").sum()).iter_rows())
    for position, entry in enumerate(entries):
        cut = entry["filter"].split('"')[1]
        assert _at(document, "pv_reserve@1", position) == pytest.approx(
            per_cut[cut], rel=0, abs=1e-6
        )


def test_a_grouped_fold_says_how_many_policies_each_cut_holds(tmp_path: Path) -> None:
    """The count is the cut's own, not the book's."""
    grouped = _written(tmp_path, _DECLARES_GROUPED)
    document = _folded(grouped, tmp_path / "graph.json")

    said = [entry["why"] for entry in _folds(document)]
    assert said == [
        'band "preferred", folded by sum over 3 policies in policy-axis-book.parquet',
        'band "standard", folded by sum over 5 policies in policy-axis-book.parquet',
    ]


# --- where the accumulators come from -----------------------------------------


def test_the_command_line_supplies_what_the_model_does_not_declare(
    silent: Path, tmp_path: Path
) -> None:
    """A model with no AGGREGATIONS is still foldable, for one run."""
    out = tmp_path / "graph.json"
    frame = _results(silent, out)
    result = _export(silent, out, "--portfolio-by", "sum:pv_reserve")
    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())

    assert [entry["aggregation"] for entry in _folds(document)] == ["sum"]
    assert _at(document, "pv_reserve@1", 0) == pytest.approx(
        frame["pv_reserve"].sum(), rel=0, abs=1e-6
    )


def test_the_command_line_overrides_what_the_model_does_declare(
    model: Path, tmp_path: Path
) -> None:
    """The model declares two columns and the flag names one; the flag wins."""
    out = tmp_path / "graph.json"
    result = _export(model, out, "--portfolio-by", "sum:pv_reserve")
    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())

    assert [entry["aggregation"] for entry in _folds(document)] == ["sum"]
    assert _at(document, "reserve@1", 0) is None


def test_the_flag_reads_a_column_s_shape_rather_than_asking_for_it(
    silent: Path, tmp_path: Path
) -> None:
    """``sum`` of a per-period column is the fold down its timeline, and says so."""
    out = tmp_path / "graph.json"
    result = _export(silent, out, "--portfolio-by", "sum:pv_reserve,reserve")
    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())

    assert [entry["aggregation"] for entry in _folds(document)] == ["sum", "period_sum"]


# --- the refusals --------------------------------------------------------------


def test_a_model_declaring_nothing_is_refused_by_name(
    silent: Path, tmp_path: Path
) -> None:
    """Naming what the model would declare, and the flag that says it instead."""
    said = _refusal(silent, tmp_path / "graph.json", "--portfolio")

    assert "declares no AGGREGATIONS" in said
    assert "AGGREGATIONS = (Sum(" in said
    assert "--portfolio-by sum:" in said


def test_a_fold_of_a_column_the_model_never_produced_is_refused(
    silent: Path, tmp_path: Path
) -> None:
    """Told before the second run rather than discovered inside it."""
    said = _refusal(
        silent, tmp_path / "graph.json", "--portfolio-by", "sum:embedded_value"
    )

    assert "'embedded_value'" in said
    # Read with the terminal's own wrapping collapsed: the sentence is one
    # sentence and the console decides where the lines fall.
    assert "Columns the run did produce include" in " ".join(said.split())


def test_a_specification_that_names_no_fold_is_refused(
    silent: Path, tmp_path: Path
) -> None:
    """The forms, and the vocabulary a command line may name."""
    said = _refusal(silent, tmp_path / "graph.json", "--portfolio-by", "total-it-up")

    assert "is not a way of naming a fold" in said
    assert "<fold>:<column>" in said
    assert "variance" in said


def test_a_cut_no_frame_can_make_is_refused_by_name(tmp_path: Path) -> None:
    """A model folding per scenario says nothing about a book with no scenarios.

    The shape this refusal exists for: a scenario axis is a cross-join on the
    model points, so the column the fold cuts on is on the frame the scenarios
    were joined onto and on no other. Told here, the caller is pointed at the
    frame they meant.
    """
    grouped = _written(tmp_path, _DECLARES_A_CUT_NOBODY_HAS)
    said = _refusal(grouped, tmp_path / "graph.json", "--portfolio")

    assert "'scenario_id'" in said
    assert "cross-join" in said


def test_an_empty_declaration_is_refused(tmp_path: Path) -> None:
    """An entry on the axis with no values under it says nothing about the book."""
    empty = _written(tmp_path, "AGGREGATIONS = ()")
    said = _refusal(empty, tmp_path / "graph.json", "--portfolio")

    assert "it is empty" in said


def test_a_declaration_of_the_wrong_shape_is_refused(tmp_path: Path) -> None:
    """Named as what it is, with the shape it has to be beside it."""
    wrong = _written(tmp_path, 'AGGREGATIONS = "pv_reserve"')
    said = _refusal(wrong, tmp_path / "graph.json", "--portfolio")

    assert "declares AGGREGATIONS as str" in said
    assert "run_aggregated takes" in " ".join(said.split())


# --- the document holds together ----------------------------------------------


def test_a_fold_carrying_document_validates(model: Path, tmp_path: Path) -> None:
    """The reading walks the axis, so the fold's entry is read rather than skipped."""
    from gaspatchio.frame.graph import validate_artifact  # noqa: PLC0415 -- one test

    out = tmp_path / "graph.json"
    _folded(model, out)

    report = validate_artifact(out, deep=True)

    assert report.schema == "gaspatchio-graph/v0-preview.3"
    assert [finding for finding in report.findings if finding.severity == "error"] == []


def test_a_pinned_period_pins_the_fold_with_it(model: Path, tmp_path: Path) -> None:
    """An entry stating one period beside a run of eighty is a contradiction."""
    document = _folded(model, tmp_path / "graph.json", "--period", "2")

    assert all(entry["periods"] == [2] for entry in document["policies"])
    folded = _at(document, "reserve@1", 1)
    assert isinstance(folded, float)


def test_a_narrowed_sample_does_not_narrow_the_fold(
    model: Path, tmp_path: Path
) -> None:
    """Each entry states the cut behind its own values, and they differ."""
    out = tmp_path / "graph.json"
    frame = _results(model, out)
    document = _folded(model, out, "--filter", "col('duration') == 1")

    entries: Sequence[dict[str, Any]] = document["policies"]
    assert [entry["filter"] for entry in entries[:2]] == [None, None]
    assert entries[-1]["filter"] == "col('duration') == 1"
    assert _at(document, "pv_reserve@1", 0) == pytest.approx(
        frame["pv_reserve"].sum(), rel=0, abs=1e-6
    )
