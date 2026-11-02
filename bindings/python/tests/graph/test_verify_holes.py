# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``gspio verify`` never agrees over a column the record cannot account for.

A column in the holes section reaches the record by name only, so whatever
its values were read or computed from is held by no check. The commonest
case is the 0.9 setup step: collect the model points, join a file in Polars,
build a new frame. Edit the joined file and the numbers move while the model
source, the book and every assumption entry stay as recorded -- so a verify
that agreed over them vouched for a stale result. The holes line holds the
question open instead, as the modules line does for code loaded by path.
"""

from __future__ import annotations

import importlib.util
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame
from gaspatchio.cli import app
from gaspatchio.frame.graph import (
    Check,
    GraphExportConfig,
    GraphExporter,
    ModelIdentity,
    VerificationReport,
    verify_artifact,
)

if TYPE_CHECKING:
    from pathlib import Path

_HEAD = (
    "import datetime\n"
    "from pathlib import Path\n"
    "import polars as pl\n"
    "from gaspatchio import ActuarialFrame\n"
    "HERE = Path(__file__).parent\n"
    "KEEP = []\n"
)
_SET = (
    "    af = af.projection.set(valuation_date=datetime.date(2025, 1, 1), "
    "until='term_months', until_value=3, frequency='monthly')\n"
)
_TAIL = (
    "    af.prem = af.premium * af['load'] + af.month * 0.0\n"
    "    af.pv_prem = af.prem.list.sum()\n"
    "    return af\n"
)
# One model per hole reason, each writing ``load`` past the frame's record.
_MODELS: dict[str, str] = {
    "joined after collect": (
        "def main(af):\n"
        "    mp = af.collect()\n"
        "    loads = pl.read_parquet(HERE / 'loads.parquet')\n"
        "    mp = mp.join(loads, on='product', how='left')\n"
        "    af = ActuarialFrame(mp)\n" + _SET + _TAIL
    ),
    "written past the doors": (
        "def main(af):\n"
        "    af._df = af._df.with_columns(pl.lit(1.0).alias('load'))\n" + _SET + _TAIL
    ),
    "overwritten": (
        "def main(af):\n"
        "    af.load = af.premium * 0.0 + 1.0\n"
        "    af._df = af._df.with_columns(pl.lit(1.0).alias('load'))\n" + _SET + _TAIL
    ),
    "rebuilt": (
        "def main(af):\n"
        "    af.load = af.premium * 0.0 + 1.0\n"
        "    mp = af.collect()\n"
        "    KEEP.append(mp)\n"
        "    af = ActuarialFrame(mp)\n" + _SET + _TAIL
    ),
    "none": "def main(af):\n    af.load = af.premium * 0.0 + 1.0\n" + _SET + _TAIL,
}
_REASON: dict[str, str] = {
    "joined after collect": "unrecorded",
    "written past the doors": "unrecorded",
    "overwritten": "overwritten",
    "rebuilt": "rebuilt",
}

_BOOK = pl.DataFrame(
    {
        "policy_id": [1, 2, 3],
        "premium": [100.0, 400.0, 300.0],
        "product": ["A", "B", "A"],
    }
)


def _run(folder: Path, name: str, *, load_a: float = 1.0) -> dict[str, Any]:
    """Write the model and its files, run it, and export its audit file."""
    folder.mkdir(parents=True, exist_ok=True)
    model = folder / "model.py"
    model.write_text(_HEAD + _MODELS[name])
    _BOOK.write_parquet(folder / "book.parquet")
    pl.DataFrame({"product": ["A", "B"], "load": [load_a, 1.0]}).write_parquet(
        folder / "loads.parquet"
    )
    spec = importlib.util.spec_from_file_location(f"model_{id(folder)}", model)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    af = module.main(ActuarialFrame(pl.read_parquet(folder / "book.parquet")))
    result = af.collect()
    result.write_parquet(folder / "results.parquet")
    identity = ModelIdentity.of(
        model,
        model_points=folder / "book.parquet",
        results=folder / "results.parquet",
    )
    exporter = GraphExporter(af, data_columns=_BOOK.columns)
    document: dict[str, Any] = json.loads(
        exporter.export(config=GraphExportConfig(model=identity))
    )
    return {"document": document, "result": result, "model": model}


def _verify_inputs(folder: Path, document: dict[str, Any]) -> VerificationReport:
    return verify_artifact(
        document,
        results=folder / "results.parquet",
        model_points=folder / "book.parquet",
        model=folder / "model.py",
    )


def _line(report: VerificationReport) -> Check:
    return next(check for check in report.checks if check.name == "holes")


def test_a_joined_file_edited_since_is_no_longer_vouched_for(tmp_path: Path) -> None:
    """The D2-E shape: the old results, the same model and book, a moved file.

    The stamp moves the identity; it does not close the line, which stays
    open over the hole whatever the stamp says.
    """
    run = _run(tmp_path / "run", "joined after collect")
    assert run["result"]["pv_prem"].to_list() == [400.0, 1600.0, 1200.0]
    edited = _run(tmp_path / "edited", "joined after collect", load_a=1.1)
    # 100 x 1.1 over four boundaries, as doubles: 110.00000000000001 a period.
    assert edited["result"]["pv_prem"].to_list() == [440.00000000000006, 1600.0, 1320.0]
    # The joined column is a hole stamped with what it held, so the edit moves
    # the model's identity and nothing else: the book and the formulas stand.
    assert (
        edited["document"]["graph_fingerprint"] != run["document"]["graph_fingerprint"]
    )
    assert (
        edited["document"]["formulas_fingerprint"]
        == run["document"]["formulas_fingerprint"]
    )
    assert edited["document"]["book"]["digest"] == run["document"]["book"]["digest"]

    # The first run's audit file and results, the edited run's model and book.
    report = verify_artifact(
        run["document"],
        results=tmp_path / "run" / "results.parquet",
        model_points=tmp_path / "edited" / "book.parquet",
        model=tmp_path / "edited" / "model.py",
    )

    line = _line(report)
    assert line.outcome == "indeterminate"
    assert "load (unrecorded; prem and pv_prem rest on it)" in line.detail
    assert "It could not be checked." in line.detail
    # The graph the edited files rebuild carries the joined file's new values
    # in the hole's stamp, so the model is decided: it is not the one recorded.
    rebuilt = next(check for check in report.checks if check.name == "graph")
    assert rebuilt.outcome == "disagree"
    assert report.verdict == "disagree"


@pytest.mark.parametrize("name", sorted(_REASON))
def test_every_hole_reason_holds_the_line_open(tmp_path: Path, name: str) -> None:
    run = _run(tmp_path, name)
    assert [(h["column"], h["reason"]) for h in run["document"]["holes"]] == [
        ("load", _REASON[name])
    ]

    report = _verify_inputs(tmp_path, run["document"])

    assert _line(report).outcome == "indeterminate"
    assert f"load ({_REASON[name]};" in _line(report).detail
    assert report.verdict == "indeterminate"


def test_a_record_with_no_holes_agrees(tmp_path: Path) -> None:
    run = _run(tmp_path, "none")

    report = _verify_inputs(tmp_path, run["document"])

    assert _line(report).outcome == "agree"
    assert report.verdict == "agree"


def test_a_results_file_held_alone_is_not_asked_about_the_inputs(
    tmp_path: Path,
) -> None:
    """Whether this is the file the run wrote is a question a hole does not touch."""
    run = _run(tmp_path, "joined after collect")

    report = verify_artifact(run["document"], results=tmp_path / "results.parquet")

    assert _line(report).outcome == "not_asked"
    assert "load (unrecorded;" in _line(report).detail
    assert report.verdict == "agree"


def test_a_file_that_differs_still_decides_over_a_hole(tmp_path: Path) -> None:
    run = _run(tmp_path, "joined after collect")
    model = tmp_path / "model.py"
    model.write_text(model.read_text() + "# edited\n")

    report = _verify_inputs(tmp_path, run["document"])

    assert report.verdict == "disagree"


def test_the_command_exits_four_naming_the_hole(tmp_path: Path) -> None:
    run = _run(tmp_path, "joined after collect")
    audit = tmp_path / "a.json"
    audit.write_text(json.dumps(run["document"]))
    given = [
        "--results",
        str(tmp_path / "results.parquet"),
        "--model-points",
        str(tmp_path / "book.parquet"),
        "--model",
        str(tmp_path / "model.py"),
    ]

    result = CliRunner().invoke(app, ["verify", str(audit), *given])

    assert result.exit_code == 4, result.output
    assert "holes could not be checked" in " ".join(result.output.split())

    documented = CliRunner().invoke(
        app, ["verify", str(audit), *given, "--assumptions", str(tmp_path)]
    )
    assert documented.exit_code == 4, documented.output


def test_the_documented_assumptions_command_passes_on_a_table_free_model(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, "none")
    audit = tmp_path / "a.json"
    audit.write_text(json.dumps(run["document"]))

    result = CliRunner().invoke(
        app,
        [
            "verify",
            str(audit),
            "--model",
            str(tmp_path / "model.py"),
            "--model-points",
            str(tmp_path / "book.parquet"),
            "--assumptions",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
