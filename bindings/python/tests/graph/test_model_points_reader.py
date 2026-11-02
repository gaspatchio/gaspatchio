# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""One book, read one way, whichever command reads it.

``gspio run-model`` reads its model points through ``read_model_points``,
and ``gspio calc-graph`` and ``gspio verify`` read theirs through the reader
beside the version block. If the two inferred a CSV's column types
differently, one file would carry two books: a column empty for its first
rows reads as text to a reader that looks at a hundred rows and as numbers
to one that looks at ten thousand, and a check holding one against the
other would report a difference in data nobody changed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.engines.protocol import digest_of_inputs
from gaspatchio.frame.graph._model_files import book_from_file
from gaspatchio.util import read_model_points

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# The book the review probed with: a rider column nobody has taken up in
# the first half of the file, and a number from there on.
_ROWS = 300
_EMPTY_FOR = 150

_MODEL = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.loaded_claims = af.sum_assured * 0.00123 + af.rider
    return af
"""


def _a_book_whose_rider_arrives_late(path: Path) -> None:
    """Write the probe book: ``rider`` empty for its first 150 of 300 rows."""
    rows = ["policy_id,sum_assured,rider"]
    rows.extend(
        f"P{row},{100_000 + row}.0,{'' if row < _EMPTY_FOR else '1.5'}"
        for row in range(_ROWS)
    )
    path.write_text("\n".join(rows) + "\n")


def test_calc_graph_and_run_model_read_one_book_from_a_csv(tmp_path: Path) -> None:
    """One type for every column, and so one digest, whichever reader took it."""
    points = tmp_path / "points.csv"
    _a_book_whose_rider_arrives_late(points)

    exported = book_from_file(points)
    run = read_model_points(points).collect()

    assert exported.schema == run.schema
    assert exported.schema["rider"] == pl.Float64
    columns = ["policy_id", "rider", "sum_assured"]
    assert digest_of_inputs(exported, columns) == digest_of_inputs(run, columns)


def test_the_book_calc_graph_records_is_the_book_run_model_reads(
    tmp_path: Path,
) -> None:
    """The digest the audit file states is the one a run over the file digests."""
    points = tmp_path / "points.csv"
    _a_book_whose_rider_arrives_late(points)
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    audit = tmp_path / "model.audit.json"

    exported = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(audit)]
    )
    assert exported.exit_code == 0, exported.output
    document = json.loads(audit.read_text())

    run = read_model_points(points).collect()
    assert "rider" in document["book"]["columns"]
    assert document["book"]["digest"] == digest_of_inputs(
        run, document["book"]["columns"]
    )


def test_a_file_that_is_neither_parquet_nor_csv_is_refused_in_words(
    tmp_path: Path,
) -> None:
    """The reader's own refusal, the same sentence on every command."""
    points = tmp_path / "points.txt"
    _a_book_whose_rider_arrives_late(points)
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    audit = tmp_path / "model.audit.json"

    exported = runner.invoke(
        app, ["calc-graph", str(model), str(points), "-o", str(audit)]
    )

    assert exported.exit_code != 0
    assert "Unsupported model points format" in " ".join(exported.output.split())
