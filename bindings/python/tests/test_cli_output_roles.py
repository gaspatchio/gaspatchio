# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Output-role aliases write the same files without changing historical meanings."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.frame.graph import validate_artifact

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


@pytest.fixture
def model_and_book(tmp_path: Path) -> tuple[Path, Path]:
    model = tmp_path / "model.py"
    model.write_text("def main(af):\n    af.result = af.amount * 2\n    return af\n")
    book = tmp_path / "book.parquet"
    pl.DataFrame({"policy_id": ["P-1", "P-2"], "amount": [2.0, 3.0]}).write_parquet(
        book
    )
    return model, book


@pytest.mark.parametrize("command", ["run-model", "run-single-policy"])
@pytest.mark.parametrize("flag", ["--results", "--output-file", "-o"])
def test_model_commands_write_result_values(
    tmp_path: Path, model_and_book: tuple[Path, Path], command: str, flag: str
) -> None:
    model, book = model_and_book
    output = tmp_path / "results.parquet"
    arguments = [command, str(model), str(book)]
    if command == "run-single-policy":
        arguments += ["P-2", "--policy-id-column", "policy_id"]
    result = runner.invoke(app, [*arguments, "--mode", "optimize", flag, str(output)])
    assert result.exit_code == 0, result.output
    values = pl.read_parquet(output).sort("policy_id")
    assert values["result"].to_list() == (
        [6.0] if command == "run-single-policy" else [4.0, 6.0]
    )


@pytest.mark.parametrize("command", ["run-model", "run-single-policy"])
@pytest.mark.parametrize(
    ("flag", "value"),
    [("--first-n", "0"), ("--last-n", "0"), ("--rows", "0"), ("--start-at", "-1")],
)
def test_shared_display_options_preserve_their_bounds(
    model_and_book: tuple[Path, Path], command: str, flag: str, value: str
) -> None:
    model, book = model_and_book
    arguments = [command, str(model), str(book)]
    if command == "run-single-policy":
        arguments.append("P-1")
    result = runner.invoke(app, [*arguments, flag, value])
    assert result.exit_code == 2, result.output
    assert flag in result.output
    assert "Invalid value" in result.output


@pytest.mark.parametrize("artifact_flag", ["--artifact", "--output", "-o"])
@pytest.mark.parametrize("results_flag", ["--results", "--output-file"])
def test_export_keeps_artifact_and_results_distinct_and_linked(
    tmp_path: Path,
    model_and_book: tuple[Path, Path],
    artifact_flag: str,
    results_flag: str,
) -> None:
    model, book = model_and_book
    artifact, output = tmp_path / "audit.json", tmp_path / "results.parquet"
    result = runner.invoke(
        app,
        [
            "calc-graph",
            str(model),
            str(book),
            "--policies",
            "all",
            artifact_flag,
            str(artifact),
            results_flag,
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    values = pl.read_parquet(output).sort("policy_id")
    assert values["result"].to_list() == [4.0, 6.0]
    document = json.loads(artifact.read_text())
    assert document["model"]["results"]["path"] == "results.parquet"
    assert validate_artifact(artifact.read_text(), deep=True).ok


@pytest.mark.parametrize(
    "command", ["run-model", "run-single-policy", "calc-graph", "run-artifact"]
)
def test_help_names_result_role_and_execution_choice(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0
    assert "--results" in result.output
    words = " ".join(result.output.split())
    if command in {"run-model", "run-single-policy"}:
        assert "Diagnostics:" in words
        assert "Polars" in words
    elif command == "calc-graph":
        assert "--artifact" in words
    else:
        assert "JAX device selection" in words
