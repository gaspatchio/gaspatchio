# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio verify --model`` decides the model by the graph its files rebuild.

Every recorded stamp can agree while the numbers move: a scalar read with
``.item()`` from a parameter file, a JSON config, an environment variable, a
module imported through ``sys.path`` from outside the model's folder, a
scenario plan's shock factor, the file behind a shocked table, a model edited
in the process that exported it. Each moves a formula, so the graph rebuilt
from the files in hand moves, and the line it moved at is named. Where the
numbers cannot have moved the rebuild agrees; where a line's calculation is
a Python function no fingerprint reads inside, or the model cannot be rebuilt
here, the question stays open.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    verify_artifact,
)
from gaspatchio.frame.graph.artifact import document_digest_of
from gaspatchio.frame.graph.rollforward_ir import FACET_NAME
from gaspatchio.runner import load_model_from_path

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from click.testing import Result

runner = CliRunner()

_BOOK = pl.DataFrame(
    {"policy_id": [1, 2], "age": [40, 41], "sum_assured": [1000.0, 2000.0]}
)

_HEAD = """\
import json
import os
from pathlib import Path

import polars as pl

HERE = Path(__file__).parent
"""


def _folder_with(folder: Path, model: str) -> Path:
    """Write the book and the model, and return the model file."""
    folder.mkdir(parents=True, exist_ok=True)
    _BOOK.write_parquet(folder / "book.parquet")
    pl.DataFrame({"name": ["load"], "value": [1.10]}).write_parquet(
        folder / "params.parquet"
    )
    (folder / "basis.json").write_text('{"rate": 0.02}')
    pl.DataFrame({"age": [40, 41], "qx": [0.001, 0.002]}).write_parquet(
        folder / "mortality.parquet"
    )
    path = folder / "model.py"
    path.write_text(_HEAD + model)
    return path


def _exported(model: Path, *options: str) -> Path:
    """Export the model with ``gspio calc-graph`` and return the audit file."""
    audit = model.parent / "model.audit.json"
    done = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(model.parent / "book.parquet"),
            "-o",
            str(audit),
            *options,
        ],
    )
    assert done.exit_code == 0, done.output
    return audit


def _verify(audit: Path, model: Path, *options: str) -> Result:
    """Run ``gspio verify --model --model-points --json`` over the files in hand."""
    return runner.invoke(
        app,
        [
            "verify",
            str(audit),
            "--model",
            str(model),
            "--model-points",
            str(model.parent / "book.parquet"),
            "--json",
            *options,
        ],
    )


def _line(result: Result, name: str = "graph") -> dict[str, Any]:
    stored = json.loads(result.stdout)
    return next(check for check in stored["checks"] if check["name"] == name)


_ITEM = """
LOAD = pl.read_parquet(HERE / "params.parquet")["value"].item()


def main(af):
    af.prem = af.sum_assured * LOAD
    return af
"""


def test_a_scalar_read_from_a_parameter_file_moved_is_named_at_its_line(
    tmp_path: Path,
) -> None:
    model = _folder_with(tmp_path, _ITEM)
    audit = _exported(model)
    pl.DataFrame({"name": ["load"], "value": [1.25]}).write_parquet(
        tmp_path / "params.parquet"
    )

    result = _verify(audit, model)

    assert result.exit_code == 1, result.output
    line = _line(result)
    assert line["outcome"] == "disagree"
    assert "prem@1 (model.py:" in line["detail"]
    assert "af.sum_assured * LOAD" in line["detail"]
    assert "in this environment" in line["detail"]
    assert _line(result, "source_sha")["outcome"] == "agree"


def test_the_same_files_rebuild_the_recorded_graph(tmp_path: Path) -> None:
    model = _folder_with(tmp_path, _ITEM)
    audit = _exported(model)
    # Rewritten with the same value: the file's bytes may move, the numbers
    # cannot, and the rebuild agrees.
    pl.DataFrame({"name": ["load"], "value": [1.10]}).write_parquet(
        tmp_path / "params.parquet"
    )

    result = _verify(audit, model)

    assert result.exit_code == 0, result.output
    assert _line(result)["outcome"] == "agree"


def test_a_json_config_moved_is_named(tmp_path: Path) -> None:
    model = _folder_with(
        tmp_path,
        """
RATE = json.loads((HERE / "basis.json").read_text())["rate"]


def main(af):
    af.charge = af.sum_assured * RATE
    return af
""",
    )
    audit = _exported(model)
    (tmp_path / "basis.json").write_text('{"rate": 0.03}')

    result = _verify(audit, model)

    assert result.exit_code == 1, result.output
    assert "charge@1" in _line(result)["detail"]


def test_an_environment_variable_moved_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _folder_with(
        tmp_path,
        """
LOAD = float(os.environ.get("B3_VERIFY_LOAD", "1.10"))


def main(af):
    af.prem = af.sum_assured * LOAD
    return af
""",
    )
    monkeypatch.delenv("B3_VERIFY_LOAD", raising=False)
    audit = _exported(model)
    assert _verify(audit, model).exit_code == 0

    monkeypatch.setenv("B3_VERIFY_LOAD", "1.25")
    result = _verify(audit, model)

    assert result.exit_code == 1, result.output
    assert "prem@1" in _line(result)["detail"]


def test_a_module_from_outside_the_model_s_folder_moved_is_named(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "b3_corporate_basis.py").write_text("LOADING = 1.10\n")
    model = _folder_with(
        tmp_path / "model",
        f"""
import sys

sys.path.insert(0, {str(shared)!r})
import b3_corporate_basis


def main(af):
    af.prem = af.sum_assured * b3_corporate_basis.LOADING
    return af
""",
    )
    audit = _exported(model)
    (shared / "b3_corporate_basis.py").write_text("LOADING = 1.25\n")

    result = _verify(audit, model)

    assert result.exit_code == 1, result.output
    assert _line(result, "modules")["outcome"] == "agree"
    assert "prem@1" in _line(result)["detail"]


def test_no_policy_data_leaves_the_graph_open(tmp_path: Path) -> None:
    model = _folder_with(tmp_path, _ITEM)
    audit = _exported(model)

    result = runner.invoke(app, ["verify", str(audit), "--model", str(model), "--json"])

    assert result.exit_code == 4, result.output
    line = _line(result)
    assert line["outcome"] == "indeterminate"
    assert "--model-points" in line["detail"]


def test_a_model_that_cannot_be_rebuilt_here_is_open_naming_why(tmp_path: Path) -> None:
    model = _folder_with(tmp_path, _ITEM)
    audit = _exported(model)
    (tmp_path / "params.parquet").unlink()

    result = _verify(audit, model)

    assert result.exit_code == 4, result.output
    line = _line(result)
    assert line["outcome"] == "indeterminate"
    assert "could not be rebuilt here" in line["detail"]
    assert "params.parquet" in line["detail"]


def test_a_python_function_holds_the_model_open_naming_its_line(tmp_path: Path) -> None:
    model = _folder_with(
        tmp_path,
        """
FACTOR = 2.0


def main(af):
    af.adj = af.sum_assured.polars_native().map_batches(
        lambda s: s * FACTOR, return_dtype=pl.Float64
    )
    return af
""",
    )
    audit = _exported(model)

    result = _verify(audit, model)

    assert result.exit_code == 4, result.output
    line = _line(result)
    assert line["outcome"] == "indeterminate"
    assert "adj@1 (model.py:" in line["detail"]
    assert "Python function" in line["detail"]


def test_a_shocked_table_names_its_file_and_its_shock(tmp_path: Path) -> None:
    model = _folder_with(
        tmp_path,
        """
from gaspatchio.assumptions import Table
from gaspatchio.scenarios import MultiplicativeShock

PRUDENT = Table("b3_mortality", HERE / "mortality.parquet", {"age": "age"}, "qx").with_shock(
    MultiplicativeShock(factor=1.05), name="b3_mortality_prudent"
)


def main(af):
    af.qx = PRUDENT.lookup(age=af.age)
    af.claims = af.sum_assured * af.qx
    return af
""",
    )
    audit = _exported(model)
    entry = next(
        one
        for one in json.loads(audit.read_text())["assumptions"]
        if one.get("name") == "b3_mortality_prudent"
    )
    assert entry["source_file"] == "mortality.parquet"
    assert [step["step"] for step in entry["shaped_by"]] == ["shocked"]
    pl.DataFrame({"age": [40, 41], "qx": [0.002, 0.002]}).write_parquet(
        tmp_path / "mortality.parquet"
    )

    result = _verify(audit, model, "--assumptions", str(tmp_path))

    assert result.exit_code == 1, result.output
    assert _line(result)["outcome"] == "disagree"


_PLAN = """\
from gaspatchio.scenarios import MultiplicativeShock, ScenarioRun, Sum

import b3_plan_model

SCENARIO_RUN = ScenarioRun(
    shocks={{"BASE": [], "UP": [MultiplicativeShock(factor={factor}, table="b3_plan_mortality")]}},
    aggregations=(Sum("claims").alias("claims").over("scenario_id"),),
)
MODEL_FN = b3_plan_model.main
"""


def test_a_scenario_plan_s_record_is_rebuilt_through_its_plan(tmp_path: Path) -> None:
    folder = tmp_path / "plan"
    model = _folder_with(
        folder,
        """
from gaspatchio.assumptions import Table

MORTALITY = Table("b3_plan_mortality", HERE / "mortality.parquet", {"age": "age"}, "qx")


def main(af):
    af.qx = MORTALITY.lookup(age=af.age)
    af.claims = af.sum_assured * af.qx
    return af
""",
    )
    model = model.rename(folder / "b3_plan_model.py")
    plan = folder / "run_scenarios.py"
    plan.write_text(_PLAN.format(factor="1.2"))
    audit = _exported(model, "--scenarios", str(plan))
    recorded = json.loads(audit.read_text())["model"]["scenarios"]
    assert recorded["path"] == "run_scenarios.py"

    agreed = _verify(audit, model, "--scenarios", str(plan))
    assert agreed.exit_code == 0, agreed.output
    assert _line(agreed)["outcome"] == "agree"

    unplanned = _verify(audit, model)
    assert unplanned.exit_code == 4, unplanned.output
    assert "--scenarios" in _line(unplanned)["detail"]

    plan.write_text(_PLAN.format(factor="1.3"))
    moved = _verify(audit, model, "--scenarios", str(plan))
    assert moved.exit_code == 1, moved.output
    assert _line(moved, "scenarios")["outcome"] == "disagree"
    assert _line(moved)["outcome"] == "disagree"


def test_a_model_edited_before_an_in_process_export_is_caught(tmp_path: Path) -> None:
    """Run, edit the model, then export it in the same process.

    The record holds the first run's graph and stamps the edited file.
    """
    model = _folder_with(
        tmp_path,
        "\n\ndef main(af):\n    af.prem = af.sum_assured * 0.01\n    return af\n",
    )
    points = tmp_path / "book.parquet"
    af = load_model_from_path(model, "main")(ActuarialFrame(pl.read_parquet(points)))
    result = af.collect()
    model.write_text(model.read_text().replace("0.01", "0.02"))
    document = json.loads(
        GraphExporter(af).export(
            result,
            GraphExportConfig(model=ModelIdentity.of(model, model_points=points)),
        )
    )

    report = verify_artifact(document, model=model, model_points=points)

    assert {check.name: check.outcome for check in report.checks}[
        "source_sha"
    ] == "agree"
    assert report.verdict == "disagree"
    graph = next(check for check in report.checks if check.name == "graph")
    assert "prem@1" in graph.detail
    assert os.path.basename(model) in graph.detail  # noqa: PTH119 - the name as written


_FUND = """
import datetime

from gaspatchio import compile_rollforward


def main(af):
    af = af.projection.set(
        start_date=datetime.date(2025, 1, 31), n_periods=3, frequency="monthly"
    )
    b = af.projection.rollforward(states={"av": af["av_init"]})
    (
        b["av"]
        .grow(af["fund_return"], label="fund_return")
        .charge(af["me_charge"], label="me_charge")
        .floor(value=0.0)
    )
    af.av = compile_rollforward(b).expr_for("av")
    return af
"""


def _edit_floor(body: dict[str, Any]) -> None:
    body["increments"][2]["settings"]["value"] = 1e9


def _edit_charge(body: dict[str, Any]) -> None:
    body["increments"][1]["operation"] = "Grow"


@pytest.mark.parametrize("edit", [_edit_floor, _edit_charge])
def test_an_edited_rollforward_machine_resealed_is_named(
    tmp_path: Path, edit: Callable[[dict[str, Any]], None]
) -> None:
    # The compilation enters the graph only by its identity, so a body
    # edited after export and resealed rebuilt the same graph and verify
    # agreed while the file ran another machine. The body no longer hashes
    # to its identity (section 12.1), and the graph line says so.
    model = _folder_with(tmp_path, _FUND)
    pl.DataFrame(
        {
            "policy_id": ["VA-0001"],
            "av_init": [100_000.0],
            "fund_return": [[0.01] * 3],
            "me_charge": [[0.001] * 3],
        }
    ).write_parquet(tmp_path / "book.parquet")
    audit = _exported(model, "--profile", "executable")
    assert _verify(audit, model).exit_code == 0

    document = json.loads(audit.read_text())
    ((fingerprint, body),) = document["facets"][FACET_NAME]["compilations"].items()
    edit(body)
    document.pop("document_digest")
    document["document_digest"] = document_digest_of(document)
    audit.write_text(json.dumps(document))

    result = _verify(audit, model)

    assert result.exit_code == 1, result.output
    line = _line(result)
    assert line["outcome"] == "disagree"
    assert f"/facets/{FACET_NAME}/compilations/{fingerprint}" in line["detail"]
    assert "is not the one its identity names" in line["detail"]
    assert _line(result, "seal")["outcome"] == "agree"
