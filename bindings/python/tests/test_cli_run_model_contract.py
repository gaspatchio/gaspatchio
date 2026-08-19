# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Tests the run-model contract diagnosis for columns attached outside main().
# ABOUTME: Guards the error note that separates the CLI contract from the standalone path.
"""Tests for the runner's diagnosis when main() assumes standalone-only columns."""

from pathlib import Path

import polars as pl
from typer.testing import CliRunner

from gaspatchio.cli import app

runner = CliRunner()

# The #121 shape: main() reads a column that only the __main__ block attaches,
# so the model passes standalone and dies under run-model.
STANDALONE_ONLY_MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.charge = af.derived_rate * 100.0
    return af


if __name__ == "__main__":
    af = ActuarialFrame({"policy_id": [1]})
    af.derived_rate = 0.05
    print(main(af).collect())
"""


def test_run_model_diagnoses_columns_attached_outside_main(tmp_path: Path):
    """The missing-attribute error names the run-model contract, not just a typo hint.

    Regression (#121): a model following the tutorials' standalone pattern
    failed under run-model with a bare "no attribute" error that read as a
    typo hint; the actual diagnosis is that columns attached outside main()
    are invisible to the runner.
    """
    model_path = tmp_path / "model.py"
    model_path.write_text(STANDALONE_ONLY_MODEL_SRC)
    data_path = tmp_path / "model_points.parquet"
    pl.DataFrame({"policy_id": [1, 2]}).write_parquet(data_path)

    result = runner.invoke(app, ["run-model", str(model_path), str(data_path)])

    assert result.exit_code != 0
    assert "derived_rate" in result.output
    assert "outside main()" in result.output
