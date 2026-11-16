# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""``import gaspatchio_core`` says what to write instead (GSP-231).

1.0 removed the deprecated alias. A model written for 0.9 meets that first, so
the failure names the move. It re-exports nothing: code cannot keep running on
the old name.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


def _importing(statement: str) -> str:
    done = subprocess.run(  # noqa: S603 -- a fixed interpreter and fixed statements
        [
            sys.executable,
            "-c",
            (
                f"try:\n    {statement}\n"
                "except ModuleNotFoundError as e:\n    print(e.name, '|', e)\n"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return done.stdout


@pytest.mark.parametrize(
    "statement",
    [
        "import gaspatchio_core",
        "from gaspatchio_core import ActuarialFrame",
        "import gaspatchio_core.assumptions",
    ],
)
def test_the_old_name_refuses_and_names_the_new_one(statement: str) -> None:
    said = _importing(statement)

    assert said.startswith("gaspatchio_core |")
    assert "import gaspatchio" in said.split("|")[1]
    assert "CHANGELOG" in said
