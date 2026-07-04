# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests for `gspio run-model` file-loading behaviour.
# ABOUTME: Guards CSV/Parquet support and model-points paths outside the model's directory.
"""Tests for the run-model CLI command's model-points loading."""

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio_core.cli import app

runner = CliRunner()

MODEL_SRC = """
from gaspatchio_core import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.doubled = af.value * 2
    return af
"""


def _write_data(path: Path) -> None:
    df = pl.DataFrame({"policy_id": ["A", "B"], "value": [10, 20]})
    if path.suffix == ".csv":
        df.write_csv(path)
    else:
        df.write_parquet(path)


@pytest.mark.parametrize("ext", [".csv", ".parquet"])
def test_run_model_loads_data_from_separate_directory(tmp_path: Path, ext: str):
    """Model points may live in a different directory than the model file.

    Regression: the CLI previously kept only the basename of the model-points
    path and rejoined it to the model's directory, so any other location failed.
    """
    model_dir = tmp_path / "model"
    data_dir = tmp_path / "data"
    model_dir.mkdir()
    data_dir.mkdir()

    model_path = model_dir / "model.py"
    model_path.write_text(MODEL_SRC)
    data_path = data_dir / f"model_points{ext}"
    _write_data(data_path)

    result = runner.invoke(app, ["run-model", str(model_path), str(data_path)])

    assert result.exit_code == 0, result.output
    assert "doubled" in result.output


@pytest.mark.parametrize("ext", [".csv", ".parquet"])
def test_run_model_loads_colocated_data(tmp_path: Path, ext: str):
    """Model points sitting next to the model still load (both formats)."""
    model_path = tmp_path / "model.py"
    model_path.write_text(MODEL_SRC)
    data_path = tmp_path / f"model_points{ext}"
    _write_data(data_path)

    result = runner.invoke(app, ["run-model", str(model_path), str(data_path)])

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("ext", [".csv", ".parquet"])
def test_run_single_policy_auto_detects_id_column(tmp_path: Path, ext: str):
    """run-single-policy resolves the policy_id column without --policy-id-column."""
    model_path = tmp_path / "model.py"
    model_path.write_text(MODEL_SRC)
    data_path = tmp_path / f"model_points{ext}"
    _write_data(data_path)

    result = runner.invoke(
        app, ["run-single-policy", str(model_path), str(data_path), "A"]
    )

    assert result.exit_code == 0, result.output
