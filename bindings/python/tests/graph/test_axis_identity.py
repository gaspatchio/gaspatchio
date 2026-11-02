# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A selected row's values are that row's, whatever the model did to the book.

The axis is chosen over the model points before the model runs and the values
are read off the frame the model hands back. Until 2026-09-20 the two were
joined by the row's position, on the assumption that running a model preserves
it -- and a model that sorts disproves that in one line. The document the
external review of 2026-09-20 found this in carried ``policy_id: "1"``, the
sentence *"row 0 of 2 ... selected by ':1'"*, and policy 2's numbers, and it
passed deep validation because every other claim in it was true.

So these are the four things a model can do to a selected row and what the
export says about each: move it (found, and said so), discard it (refused),
duplicate it (refused), and drop the stamp that finds it (the id stands in, or
refused). Each refusal is read as a sentence rather than as an exit code,
because a sentence nobody asserts rots into "Error: None" without anything
failing.

The last reading is the validator's. A document written by a producer that got
this wrong is internally consistent, so the only witness left in the file is
the model points' own id column standing beside the numbers -- and that is the
reading added here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import validate_artifact
from gaspatchio.frame.graph.row_identity import ROW_STAMP

if TYPE_CHECKING:
    from collections.abc import Iterator

runner = CliRunner()

# Two policies, and the model points' own order is not the order any of the
# models below leaves them in. Row 0 is policy 1; a selection by position
# lands there and an honest export quotes 100 and 200 whatever happened next.
_BOOK = {"point_id": [1, 2], "amount": [100.0, 200.0]}

_HEAD = "from gaspatchio import ActuarialFrame\nimport polars as pl\n\n\n"

# The review's own model: one supported call, and the assumption that a row
# position survives a run is gone.
_SORTS = (
    _HEAD + "def main(af, params=None):\n"
    '    af = af.sort("amount", descending=True)\n'
    "    af.result = af.amount * 2.0\n"
    "    return af\n"
)

# A Phase 1 that collects, cuts the book and rebuilds -- the shape every
# tutorial teaches, with a filter in it. The stamp travels, so the export can
# say exactly which row is gone.
_DISCARDS = (
    _HEAD + "def main(af, params=None):\n"
    "    mp = af.collect()\n"
    '    af = ActuarialFrame(mp.filter(pl.col("point_id") == 2))\n'
    "    af.result = af.amount * 2.0\n"
    "    return af\n"
)

# The same shape, doubling the book instead of cutting it -- a join against a
# table matching twice reaches the finished frame the same way.
_DUPLICATES = (
    _HEAD + "def main(af, params=None):\n"
    "    mp = af.collect()\n"
    "    af = ActuarialFrame(pl.concat([mp, mp]))\n"
    "    af.result = af.amount * 2.0\n"
    "    return af\n"
)

# A Phase 1 that names the columns it keeps. The stamp does not survive a
# select, and the id column does -- which is the fallback.
_DROPS_THE_STAMP = (
    _HEAD + "def main(af, params=None):\n"
    "    mp = af.collect()\n"
    '    af = ActuarialFrame(mp.select(["point_id", "amount"]).sort("amount", descending=True))\n'
    "    af.result = af.amount * 2.0\n"
    "    return af\n"
)

# And one that keeps neither, which is where there is nothing left to pin to.
_DROPS_EVERYTHING = (
    _HEAD + "def main(af, params=None):\n"
    "    mp = af.collect()\n"
    '    af = ActuarialFrame(mp.select(["amount"]).sort("amount", descending=True))\n'
    "    af.result = af.amount * 2.0\n"
    "    return af\n"
)


@pytest.fixture
def workshop(tmp_path: Path) -> Iterator[Path]:
    """Write the book the models below run over, and hand back its directory."""
    pl.DataFrame(_BOOK).write_parquet(tmp_path / "points.parquet")
    yield tmp_path


def _export(where: Path, model: str, *extra: str) -> Any:  # noqa: ANN401 -- the runner's own result
    """Run ``calc-graph`` over one model and return the runner's result."""
    (where / "model.py").write_text(model)
    return runner.invoke(
        app,
        [
            "calc-graph",
            str(where / "model.py"),
            str(where / "points.parquet"),
            "--profile",
            "executable",
            "--policy-id-column",
            "point_id",
            "-o",
            str(where / "artifact.json"),
            *extra,
        ],
    )


def _said(result: Any) -> str:  # noqa: ANN401 -- the runner's own result
    """Return the refusal the command said, as one line.

    A refusal is said on stderr, which keeps stdout for the command's own
    output. The terminal wraps it to its width, so a sentence read back with
    its line breaks in it matches nothing. What is being asserted is the
    words, not where the console broke them.
    """
    return " ".join(result.stderr.split())


def _document(where: Path) -> dict[str, Any]:
    """Return the artifact the export just wrote."""
    return json.loads((where / "artifact.json").read_text())


def _samples(document: dict[str, Any]) -> dict[str, Any]:
    """Return every node's sampled value, keyed by node id."""
    return {node["id"]: node.get("value_sample") for node in document["nodes"]}


# --- what the model did to the selected row -----------------------------------


def test_a_model_that_sorts_still_quotes_the_row_that_was_selected(
    workshop: Path,
) -> None:
    """A model that sorts its rows, and the property that answers it.

    ``--policies :1`` names row 0 of the book, which is policy 1 carrying
    100. The model sorts the frame descending, so row 0 of what it hands
    back is policy 2 carrying 200. The entry's samples are policy 1's, and
    deep validation agrees.
    """
    assert _export(workshop, _SORTS, "--policies", ":1").exit_code == 0

    document = _document(workshop)
    assert [entry["policy_id"] for entry in document["policies"]] == ["1"]
    assert _samples(document) == {"point_id": 1, "amount": 100.0, "result@1": 200.0}
    assert validate_artifact(document, deep=True).ok


def test_the_sentence_says_where_the_model_left_the_row(workshop: Path) -> None:
    """``why`` names the row selected and, where it moved, where it ended up.

    A sentence reading "row 0 of 2" beside a finished frame whose row 0 is
    another policy is a sentence a reader would check and find wrong. Both
    facts are true and both are said.
    """
    assert _export(workshop, _SORTS, "--policies", ":1").exit_code == 0

    why = _document(workshop)["policies"][0]["why"]
    assert "row 0 of 2 in points.parquet, selected by ':1'" in why
    assert "the model left it at row 1 of the frame it handed back" in why


def test_a_row_the_model_discarded_is_refused_rather_than_stood_in_for(
    workshop: Path,
) -> None:
    """There is no row to quote, so there is no entry to write."""
    result = _export(workshop, _DISCARDS, "--policies", ":1")

    assert result.exit_code == 3
    said = _said(result)
    assert "is not in the frame the model handed back" in said
    assert "row 0 of 2 in points.parquet, selected by ':1'" in said
    assert "--filter" in said


def test_a_row_the_model_duplicated_is_refused_as_more_than_one_answer(
    workshop: Path,
) -> None:
    """Two rows are the selected row, and taking the first is a guess."""
    result = _export(workshop, _DUPLICATES, "--policies", ":1")

    assert result.exit_code == 3
    said = _said(result)
    assert "2 rows of the frame the model handed back" in said
    assert "more than one answer" in said


def test_the_id_column_stands_in_where_the_model_dropped_the_stamp(
    workshop: Path,
) -> None:
    """A select drops the stamp, and the id the actuary would use pins the row.

    The model sorts as well, so a position would still be wrong here: what
    makes the answer right is the id, matched against the finished frame
    after the run.
    """
    assert _export(workshop, _DROPS_THE_STAMP, "--policies", ":1").exit_code == 0

    document = _document(workshop)
    assert _samples(document) == {"point_id": 1, "amount": 100.0, "result@1": 200.0}


def test_a_run_that_carries_no_identity_at_all_is_refused_in_words(
    workshop: Path,
) -> None:
    """Neither the stamp nor the id survived, so nothing names the row."""
    result = _export(workshop, _DROPS_EVERYTHING, "--policies", ":1")

    assert result.exit_code == 3
    said = _said(result)
    assert "did not hand the stamp back" in said
    assert "is not in column 'point_id' of the finished frame either" in said
    assert "--filter" in said


def test_naming_the_policy_by_id_reaches_it_on_a_model_that_sorts(
    workshop: Path,
) -> None:
    """The control the review used, and it stays correct."""
    assert _export(workshop, _SORTS, "--policies", "1").exit_code == 0

    assert _samples(_document(workshop)) == {
        "point_id": 1,
        "amount": 100.0,
        "result@1": 200.0,
    }


# --- the stamp is the export's, and it stays there ----------------------------


def test_the_row_stamp_reaches_no_part_of_the_document(workshop: Path) -> None:
    """It is scaffolding, so no node, no value and no byte of the file has it."""
    assert _export(workshop, _SORTS, "--policies", ":1").exit_code == 0

    assert ROW_STAMP not in (workshop / "artifact.json").read_text()
    assert [node["id"] for node in _document(workshop)["nodes"]] == [
        "point_id",
        "amount",
        "result@1",
    ]


def test_the_row_stamp_reaches_no_results_file(workshop: Path) -> None:
    """The numbers written beside the artifact are the model's columns only."""
    results = workshop / "results.parquet"
    assert (
        _export(
            workshop, _SORTS, "--policies", ":1", "--output-file", str(results)
        ).exit_code
        == 0
    )

    assert pl.read_parquet(results).columns == ["point_id", "amount", "result"]


def test_an_export_of_a_model_that_moves_nothing_is_what_it_always_was(
    workshop: Path,
) -> None:
    """The stamp changes no fingerprint and no sentence on an ordinary run."""
    plain = (
        _HEAD + "def main(af, params=None):\n"
        "    af.result = af.amount * 2.0\n"
        "    return af\n"
    )
    assert _export(workshop, plain, "--policies", ":1").exit_code == 0

    document = _document(workshop)
    assert document["policies"][0]["why"] == (
        "row 0 of 2 in points.parquet, selected by ':1'"
    )
    assert _samples(document) == {"point_id": 1, "amount": 100.0, "result@1": 200.0}


# --- the reading a sightless consumer has -------------------------------------


def _as_the_producer_used_to_write_it(workshop: Path) -> dict[str, Any]:
    """Return the defective document: the right id over the wrong row's values.

    Exported by this producer and then edited, because this producer no
    longer writes one. The edit is exactly what indexing the finished frame
    by the book's position produced: the entry stays policy 1 and every
    sample becomes row 1's.
    """
    assert _export(workshop, _SORTS, "--policies", "1").exit_code == 0
    document = _document(workshop)
    for node in document["nodes"]:
        node["value_sample"] = {"point_id": 2, "amount": 200.0, "result@1": 400.0}[
            node["id"]
        ]
        node["trace"] = None
    return document


def test_the_validator_refuses_an_entry_whose_values_are_another_policys(
    workshop: Path,
) -> None:
    """How that document should have failed ``gspio validate``."""
    report = validate_artifact(_as_the_producer_used_to_write_it(workshop))

    assert not report.ok
    said = [
        finding.message
        for finding in report.findings
        if "names policy" in finding.message
    ]
    assert len(said) == 1
    assert "names policy '1'" in said[0]
    assert "'point_id' reads 2" in said[0]


def test_the_validator_accepts_the_document_this_producer_writes(
    workshop: Path,
) -> None:
    """The same reading, on the export the edit above was made from."""
    assert _export(workshop, _SORTS, "--policies", "1").exit_code == 0

    report = validate_artifact(_document(workshop), deep=True)

    assert report.ok
