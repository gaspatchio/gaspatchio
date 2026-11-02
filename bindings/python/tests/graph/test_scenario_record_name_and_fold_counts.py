# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The scenario run's own record is named sanely, and a fold counts what it folds.

Three independently built models exported a scenario run
to ``<o>.audit.json`` -- the name the docs give an artifact -- and found the
run's own record beside it as ``<o>.audit.audit.json``: the export appended
``.audit.json`` to whatever it was handed. And each fold's sentence counted
the book, not the cut: ul-r7's ``Sum(...).over(("scenario_id", "policy_id"))``
entries each select one policy and each said "over 2 policies"; gmdb-r3's
one-policy book read "over 1 policies".
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_MODEL = """
import polars as pl


def main(af, params=None):
    del params
    af.shocked_rate = af.base_rate * pl.when(
        pl.col("scenario_id") == "STRESS"
    ).then(1.5).otherwise(1.0)
    af.loss = af.sum_assured * af.shocked_rate
    af.size = pl.when(pl.col("sum_assured") > 200_000.0).then(
        pl.lit("large")
    ).otherwise(pl.lit("small"))
    return af
"""

_SCRIPT = """
from gaspatchio import ScenarioRun
from gaspatchio.scenarios import Sum

import fold_count_model


SCENARIO_RUN = ScenarioRun(
    shocks={{"BASE": [], "STRESS": []}},
    aggregations=({aggregations},),
)
MODEL_FN = fold_count_model.main
"""


@pytest.fixture
def book(tmp_path: Path) -> Path:
    """Write a three-policy book and return its path."""
    written = tmp_path / "book.parquet"
    pl.DataFrame(
        {
            "Policy number": ["P1", "P2", "P3"],
            "sum_assured": [100_000.0, 250_000.0, 300_000.0],
            "base_rate": [0.001, 0.002, 0.003],
        }
    ).write_parquet(written)
    return written


def _exported(tmp_path: Path, book: Path, out_name: str, aggregations: str) -> Any:  # noqa: ANN401 -- the document, as parsed
    # A module name of its own: the run script imports the model by name, and
    # a ``model`` another test imported first would be the one it found.
    (tmp_path / "fold_count_model.py").write_text(_MODEL)
    script = tmp_path / "run_scenarios.py"
    script.write_text(_SCRIPT.format(aggregations=aggregations))
    out = tmp_path / out_name
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "fold_count_model.py"),
            str(book),
            "-o",
            str(out),
            "--scenarios",
            str(script),
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(out.read_text())


_BY_SCENARIO = 'Sum("loss").alias("loss").over("scenario_id")'


@pytest.mark.parametrize(
    ("out_name", "record_name"),
    [
        ("scenario.audit.json", "scenario.run.audit.json"),
        ("graph.json", "graph.run.audit.json"),
    ],
)
def test_the_runs_own_record_is_named_once(
    tmp_path: Path, book: Path, out_name: str, record_name: str
) -> None:
    """No doubled suffix, and the document names the record it wrote."""
    document = _exported(tmp_path, book, out_name, _BY_SCENARIO)
    assert (tmp_path / record_name).exists()
    assert not list(tmp_path.glob("*.audit.audit.json"))
    assert document["model"]["audit"]["path"].endswith(record_name)


def _fold_sentences(document: dict[str, Any]) -> list[str]:
    return [
        entry["why"]
        for entry in document["policies"]
        if entry["aggregation"] is not None
    ]


def test_a_fold_over_one_scenario_counts_the_books_policies(
    tmp_path: Path, book: Path
) -> None:
    """Each scenario holds every policy once, so the count is the book's."""
    said = _fold_sentences(_exported(tmp_path, book, "g.json", _BY_SCENARIO))
    assert said == [
        'scenario_id "BASE", folded by sum over 3 policies in book.parquet',
        'scenario_id "STRESS", folded by sum over 3 policies in book.parquet',
    ]


def test_a_fold_selecting_one_policy_says_one_policy(
    tmp_path: Path, book: Path
) -> None:
    """ul-r7's shape: one scenario and one policy is a fold over one policy."""
    aggregations = 'Sum("loss").alias("loss").over(("scenario_id", "Policy number"))'
    said = _fold_sentences(_exported(tmp_path, book, "g.json", aggregations))
    assert len(said) == 6
    assert all("over 1 policy in book.parquet" in one for one in said), said


def test_a_fold_by_a_computed_column_counts_its_cut(tmp_path: Path, book: Path) -> None:
    """A cut the model computes is counted on the frame the model returned."""
    aggregations = 'Sum("loss").alias("loss").over(("scenario_id", "size"))'
    said = _fold_sentences(_exported(tmp_path, book, "g.json", aggregations))
    over = "folded by sum over {} in book.parquet"
    assert said == [
        f'scenario_id "BASE" and size "large", {over.format("2 policies")}',
        f'scenario_id "BASE" and size "small", {over.format("1 policy")}',
        f'scenario_id "STRESS" and size "large", {over.format("2 policies")}',
        f'scenario_id "STRESS" and size "small", {over.format("1 policy")}',
    ]


def test_a_fold_across_scenarios_says_so(tmp_path: Path, book: Path) -> None:
    """A fold whose cut spans the scenarios says how many it spans."""
    said = _fold_sentences(
        _exported(tmp_path, book, "g.json", 'Sum("loss").alias("loss")')
    )
    assert said == [
        (
            "the whole book, folded by sum over 3 policies in book.parquet, "
            "across 2 scenarios"
        ),
    ]


def test_a_portfolio_fold_by_a_computed_column_counts_its_cut(
    tmp_path: Path, book: Path
) -> None:
    """The book's own fold counts a model-computed cut on the model's frame."""
    model = tmp_path / "fold_count_portfolio_model.py"
    model.write_text(
        _MODEL.replace('pl.col("scenario_id") == "STRESS"', "False")
        + "\n\nfrom gaspatchio.scenarios import Sum\n\n"
        + 'AGGREGATIONS = (Sum("loss").alias("loss").over("size"),)\n'
    )
    out = tmp_path / "g.json"
    result = runner.invoke(
        app,
        ["calc-graph", str(model), str(book), "-o", str(out), "--portfolio"],
    )
    assert result.exit_code == 0, result.output
    assert _fold_sentences(json.loads(out.read_text())) == [
        'size "large", folded by sum over 2 policies in book.parquet',
        'size "small", folded by sum over 1 policy in book.parquet',
    ]
