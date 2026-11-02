# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: `--mode` on run-model and run-single-policy is debug or optimize, or refused.
# ABOUTME: A misspelt mode used to run debug with no word.
"""``--mode`` names one of two modes; anything else is refused, not run as debug.

``gspio run-model ... --mode optimise`` (the British spelling) or ``--mode
zzz`` ran with profiling on and exit 0: the CLI replaced any value it did not
know with ``debug`` and said nothing. The two modes change diagnostics, not
numbers, so the run was right and the request silently ignored. Both run
doors now refuse it as a bad parameter, naming the two modes and the closest.
"""

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app

runner = CliRunner()

MODEL_SRC = """
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.doubled = af.value * 2
    return af
"""


def _files(tmp_path: Path) -> tuple[Path, Path]:
    model = tmp_path / "model.py"
    model.write_text(MODEL_SRC)
    book = tmp_path / "book.parquet"
    pl.DataFrame({"policy_id": ["A", "B"], "value": [10, 20]}).write_parquet(book)
    return model, book


def _door(command: str, model: Path, book: Path) -> list[str]:
    if command == "run-model":
        return ["run-model", str(model), str(book)]
    return [
        "run-single-policy",
        str(model),
        str(book),
        "A",
        "--policy-id-column",
        "policy_id",
    ]


@pytest.mark.parametrize("command", ["run-model", "run-single-policy"])
@pytest.mark.parametrize(("mode", "hint"), [("optimise", "optimize"), ("zzz", None)])
def test_an_unknown_mode_is_refused(
    tmp_path: Path, command: str, mode: str, hint: str | None
) -> None:
    model, book = _files(tmp_path)
    result = runner.invoke(app, [*_door(command, model, book), "--mode", mode])
    assert result.exit_code == 2, result.output
    said = " ".join(result.output.split())
    assert "is not a mode" in said
    if hint is not None:
        assert f"Did you mean '{hint}'?" in said


@pytest.mark.parametrize("command", ["run-model", "run-single-policy"])
@pytest.mark.parametrize("mode", ["debug", "optimize"])
def test_the_two_modes_run(tmp_path: Path, command: str, mode: str) -> None:
    model, book = _files(tmp_path)
    result = runner.invoke(app, [*_door(command, model, book), "--mode", mode])
    assert result.exit_code == 0, result.output
