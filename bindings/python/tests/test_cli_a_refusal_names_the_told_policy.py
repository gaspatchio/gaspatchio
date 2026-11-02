# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Every run door names a refused policy by the ``--policy-id-column`` it was told.

``gspio run-model`` and ``run-single-policy`` named the policy by the column
the run was told; ``gspio calc-graph`` ran the model outside that telling, so
a book keyed by ``pid`` got ``Policy: row 1`` -- no identifier -- under the
same flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_MODEL = """\
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame, params=None) -> ActuarialFrame:
    af.last_av = af.av.list.get(36)
    return af
"""


def _files(tmp_path: Path) -> tuple[str, str]:
    model = tmp_path / "model.py"
    model.write_text(_MODEL)
    book = tmp_path / "book.parquet"
    pl.DataFrame(
        {"pid": ["A1", "B2", "C3"], "av": [[1.0] * 40, [2.0] * 24, [3.0] * 40]}
    ).write_parquet(book)
    return str(model), str(book)


@pytest.mark.parametrize(
    "door",
    [
        ["run-model"],
        ["calc-graph", "--artifact", "{tmp}/a.json"],
    ],
    ids=["run-model", "calc-graph"],
)
def test_the_told_column_names_the_refused_policy(
    tmp_path: Path, door: list[str]
) -> None:
    model, book = _files(tmp_path)
    command, *options = door
    arguments = [
        command,
        model,
        book,
        *(option.format(tmp=tmp_path) for option in options),
        "--policy-id-column",
        "pid",
    ]
    result = runner.invoke(app, arguments, env={"COLUMNS": "200"})

    assert result.exit_code != 0
    assert "Policy: pid=B2 (row 1)" in result.output
