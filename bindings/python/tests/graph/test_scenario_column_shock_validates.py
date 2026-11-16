# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A scenario run that shocks a column exports an artifact its own validator accepts.

A ``column=`` shock rewrites the arriving column once per scenario, so the
document carries two definitions of it: the column as it arrived, which the
finished frame no longer holds (``in_final_schema: false``), and the shocked
definition that replaced it. The export used to read a value sample and a
walk-through onto the arriving definition as well -- the number that replaced
it, against the wrong formula -- and ``gspio validate`` refused the file the
export had just written. Every model that shocks a rate or an expense column
through ``column=`` could not produce an audit file that conforms.

The arrays were the policy axis's, not the scenario door's: every node was
handed one array per field as long as the axis, including a field no entry
stated, so the same refusal met any export of more than one policy over a
model that overwrites an arriving column.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph.validate import validate_artifact

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_MODEL = """
def main(af, params=None):
    del params
    af.v = 1.0 / (1.0 + af.rate)
    af.pv = af.sum_assured * af.v
    return af
"""

_SCRIPT = """
from gaspatchio import ScenarioRun
from gaspatchio.scenarios import AdditiveShock, Sum

import column_shock_model


SCENARIO_RUN = ScenarioRun(
    shocks={"BASE": [], "UP": [AdditiveShock(delta=0.01, column="rate")]},
    aggregations=(Sum("pv").alias("total_pv"),),
)
MODEL_FN = column_shock_model.main
"""


def _export(tmp_path: Path, *extra: str) -> tuple[Path, Any]:
    """Export the column-shocked plan over a one-policy book."""
    book = tmp_path / "mp.parquet"
    pl.DataFrame(
        {"Policy number": ["P1"], "sum_assured": [1000.0], "rate": [0.05]}
    ).write_parquet(book)
    # A module name of its own: the run script imports the model by name, and
    # a ``model`` another test imported first would be the one it found.
    model = tmp_path / "column_shock_model.py"
    model.write_text(_MODEL)
    script = tmp_path / "run_scenarios.py"
    script.write_text(_SCRIPT)
    out = tmp_path / "graph.json"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(book),
            "-o",
            str(out),
            "--scenarios",
            str(script),
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output
    return out, json.loads(out.read_text())


@pytest.mark.parametrize("extra", [(), ("--no-retain-superseded",)])
def test_a_column_shocked_scenario_export_validates(
    tmp_path: Path, extra: tuple[str, ...]
) -> None:
    """The export the scenario door writes is one ``validate`` accepts."""
    out, document = _export(tmp_path, *extra)
    report = validate_artifact(document)
    assert report.ok, [f.message for f in report.findings if f.severity == "error"]
    validated = runner.invoke(app, ["validate", str(out)])
    assert validated.exit_code == 0, validated.output


_OVERWRITING_MODEL = """
def main(af, params=None):
    del params
    af.rate = af.rate + 0.01
    af.pv = af.sum_assured / (1.0 + af.rate)
    return af
"""


@pytest.mark.parametrize("extra", [(), ("--no-retain-superseded",)])
def test_a_multi_policy_export_of_an_overwritten_input_validates(
    tmp_path: Path, extra: tuple[str, ...]
) -> None:
    """The same shape without a scenario: two policies, an input written over.

    The arrays come from the policy axis, not from the scenario door, so a
    model that overwrites an arriving column and is exported for more than
    one policy meets the same refusal unless the axis leaves a field nobody
    stated off the node.
    """
    book = tmp_path / "mp.parquet"
    pl.DataFrame(
        {
            "Policy number": ["P1", "P2"],
            "sum_assured": [1000.0, 2000.0],
            "rate": [0.05, 0.04],
        }
    ).write_parquet(book)
    model = tmp_path / "overwriting_model.py"
    model.write_text(_OVERWRITING_MODEL)
    out = tmp_path / "graph.json"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(book),
            "-o",
            str(out),
            "--policies",
            "all",
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output
    report = validate_artifact(json.loads(out.read_text()))
    assert report.ok, [f.message for f in report.findings if f.severity == "error"]


def test_the_arriving_column_carries_no_value_of_the_shocked_one(
    tmp_path: Path,
) -> None:
    """The superseded arriving definition states no value; the shocked one does.

    "No value" is the single null a one-policy document writes, not an array
    of nulls as long as the axis: the array is a value as far as the
    validator's refusal is concerned.
    """
    _, document = _export(tmp_path)
    nodes = {node["id"]: node for node in document["nodes"]}
    assert nodes["rate@1"]["value_sample"] == [None, 0.05]
    superseded = [
        node
        for node in nodes.values()
        if node.get("in_final_schema") is False
        and node.get("retained") is not True
        and node.get("kind") not in {"state", "rollforward"}
    ]
    assert superseded, sorted(nodes)
    for node in superseded:
        assert node.get("value_sample") is None, node["id"]
        assert node.get("trace") is None, node["id"]
