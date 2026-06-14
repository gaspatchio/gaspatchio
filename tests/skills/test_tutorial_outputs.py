# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: S101, ANN201, S603, S607, INP001
"""CI test: verify all tutorial models produce expected output.

Catches API changes that silently break tutorial examples.
Runs each tutorial's model.py and diffs stdout against expected_output.txt.
"""

import subprocess
import sys
from pathlib import Path

import pytest

TUTORIALS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "bindings"
    / "python"
    / "gaspatchio_core"
    / "tutorials"
)

LEVELS = [
    "level-1-hello-world",
    "level-2-assumptions",
    "level-3-mini-va",
    "level-4-lifelib",
    "level-5-scenarios",
]


@pytest.mark.parametrize("level", LEVELS)
def test_tutorial_output_matches_expected(level: str):
    """Tutorial model output matches expected_output.txt."""
    base_dir = TUTORIALS_DIR / level / "base"
    model_file = base_dir / "model.py"
    expected_file = base_dir / "expected_output.txt"

    if not model_file.exists():
        pytest.skip(f"No model.py for {level}")
    if not expected_file.exists():
        pytest.skip(f"No expected_output.txt for {level}")

    result = subprocess.run(
        [sys.executable, str(model_file)],
        capture_output=True,
        text=True,
        cwd=str(base_dir),
    )

    assert result.returncode == 0, f"{level} model failed:\n{result.stderr}"

    expected = expected_file.read_text().strip()
    actual = result.stdout.strip()

    assert actual == expected, (
        f"{level} output mismatch.\n\n"
        f"--- Expected ---\n{expected}\n\n"
        f"--- Actual ---\n{actual}"
    )
