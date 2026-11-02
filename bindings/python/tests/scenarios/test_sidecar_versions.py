# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""A run's own record can withhold the machine it ran on, and never does unasked.

A scenario run's sidecar states the library its numbers passed through --
core and extension versions, the extension's digest, Polars, Python, the
platform, ddsketch -- and those strings name one desk's build. A sidecar
committed as a golden therefore moved with whoever regenerated it, and
``gspio calc-graph --no-versions`` withheld the versions in the document
while the run's own record, written by the same command, went on stating
them. A committed golden must never carry a string that moves with the
machine that wrote it, so the record takes section 6.1's withheld form on
the same switch the document does: ``versions="withheld"`` on
``ScenarioRun.run`` and ``run_aggregated``, and ``--no-versions`` through
``calc-graph --scenarios``. It is never the default.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import TYPE_CHECKING, Any

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio import ActuarialFrame, ScenarioRun
from gaspatchio.cli import app
from gaspatchio.frame.graph import validate_artifact
from gaspatchio.scenarios import Sum, run_aggregated
from gaspatchio.scenarios._audit import library_versions, read_audit

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

# The seven keys a record states about the library: the result manifest's
# six, spelled as it spells them, and ddsketch beside them.
_KEYS = {
    "core_version",
    "extension_version",
    "extension_sha256",
    "polars_version",
    "python_version",
    "platform",
    "ddsketch_version",
}
_WITHHELD = {"omitted": "withheld"}


def _book() -> pl.DataFrame:
    """Return three policies."""
    return pl.DataFrame(
        {"policy_id": [1, 2, 3], "premium": [100.0, 200.0, 300.0]},
    )


def _loss(af: ActuarialFrame) -> ActuarialFrame:
    """Return the frame with the column the folds read."""
    af.loss = af.premium * 0.01
    return af


def _scenario_model(af: ActuarialFrame) -> ActuarialFrame:
    """Return the scenario model the plan runs: the model itself, unchanged."""
    return _loss(af)


def _plan() -> ScenarioRun:
    """Return a two-scenario plan over the loss."""
    return ScenarioRun(
        shocks={"BASE": [], "UP": []},
        base_tables={},
        aggregations=(Sum("loss").alias("loss").over("scenario_id"),),
    )


def _library_of(record: dict[str, Any]) -> dict[str, Any]:
    """Return the record's library keys, as its run metadata states them."""
    return {key: record["run_metadata"][key] for key in _KEYS}


def test_a_scenario_run_states_its_library_unless_asked_not_to(tmp_path: Path) -> None:
    """Recorded by default; every key the withheld form when asked."""
    stated = _plan().run(
        ActuarialFrame(_book()), _scenario_model, audit=tmp_path / "a.json"
    )
    library = _library_of(read_audit(stated.audit_path))
    assert library == library_versions()
    assert all(isinstance(value, str) for value in library.values())

    withheld = _plan().run(
        ActuarialFrame(_book()),
        _scenario_model,
        audit=tmp_path / "b.json",
        versions="withheld",
    )
    record = read_audit(withheld.audit_path)
    assert _library_of(record) == dict.fromkeys(_KEYS, _WITHHELD)
    # Nothing else about the record moves: the same plan, the same numbers.
    assert record["source_sha"] == read_audit(stated.audit_path)["source_sha"]
    assert (
        record["aggregator_outputs"]
        == read_audit(stated.audit_path)["aggregator_outputs"]
    )
    # And no string naming this machine is left anywhere in it.
    text = withheld.audit_path.read_text()
    for named in library.values():
        if named not in {"unavailable", "unknown"}:
            assert json.dumps(named) not in text, named


def test_an_aggregation_record_withholds_the_same_way(tmp_path: Path) -> None:
    """The policy axis writes the one record through the one writer."""
    result = run_aggregated(
        _loss,
        _book(),
        [Sum("loss").alias("total")],
        audit=tmp_path / "agg.json",
        versions="withheld",
    )
    assert _library_of(read_audit(result.audit_path)) == dict.fromkeys(_KEYS, _WITHHELD)


def test_withheld_is_never_the_default() -> None:
    """Both writers, and the function under them, default to stating them."""
    for signature in (
        inspect.signature(ScenarioRun.run),
        inspect.signature(run_aggregated),
        inspect.signature(library_versions),
    ):
        assert signature.parameters["versions"].default == "recorded"
    assert library_versions()["platform"] != _WITHHELD


def test_a_setting_that_is_neither_is_refused_before_the_run(tmp_path: Path) -> None:
    """A misspelt setting costs no run."""
    ran: list[bool] = []

    def model(af: ActuarialFrame) -> ActuarialFrame:
        ran.append(True)
        return _scenario_model(af)

    with pytest.raises(ValueError, match="is not a setting"):
        _plan().run(
            ActuarialFrame(_book()),
            model,
            audit=tmp_path / "c.json",
            versions="hidden",  # type: ignore[arg-type]
        )
    assert ran == []
    with pytest.raises(ValueError, match="is not a setting"):
        run_aggregated(_loss, _book(), [Sum("loss").alias("total")], versions="no")  # type: ignore[arg-type]


_MODEL = """
def main(af, params=None):
    del params
    af.loss = af.premium * 0.01
    return af
"""

_SCRIPT = """
from gaspatchio import ScenarioRun
from gaspatchio.scenarios import Sum

import sidecar_versions_model


SCENARIO_RUN = ScenarioRun(
    shocks={"BASE": [], "UP": []},
    aggregations=(Sum("loss").alias("loss").over("scenario_id"),),
)
MODEL_FN = sidecar_versions_model.main
"""


@pytest.mark.parametrize("flag", ["--versions", "--no-versions"])
def test_calc_graph_withholds_in_both_records_of_a_run(
    tmp_path: Path, flag: str
) -> None:
    """One switch, two records: the document and the run's own record agree.

    The document validates whichever way it is set, and it still names the
    record it was written beside by the digest of that record's bytes.
    """
    (tmp_path / "sidecar_versions_model.py").write_text(_MODEL)
    (tmp_path / "run_scenarios.py").write_text(_SCRIPT)
    book = tmp_path / "book.parquet"
    _book().write_parquet(book)
    out = tmp_path / "graph.json"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(tmp_path / "sidecar_versions_model.py"),
            str(book),
            "-o",
            str(out),
            "--scenarios",
            str(tmp_path / "run_scenarios.py"),
            flag,
        ],
    )
    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())
    sidecar = tmp_path / "graph.run.audit.json"
    library = _library_of(read_audit(sidecar))
    if flag == "--no-versions":
        assert document["producer"]["versions"] == _WITHHELD
        assert library == dict.fromkeys(_KEYS, _WITHHELD)
    else:
        assert document["producer"]["versions"]["platform"] == library["platform"]
        assert all(isinstance(value, str) for value in library.values())
    assert validate_artifact(document).ok
    named = document["model"]["audit"]["fingerprint"]
    assert named == "sha256:" + hashlib.sha256(sidecar.read_bytes()).hexdigest()
