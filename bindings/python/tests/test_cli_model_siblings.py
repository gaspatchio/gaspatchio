# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: A model file loaded by a gspio command imports the files beside it.
# ABOUTME: As `python model.py` does, without one model's files reaching the next.
"""A model loaded by path imports its siblings, as ``python model.py`` would.

A helper beside the model -- an accessor module, a tables module, the model
a run script imports -- is imported by its bare name at the top of the file.
Python finds it when the modeller runs the file, because the file's own
directory is first on the path. Every command that loads a model by path has
to find it too, and has to leave nothing behind for the next model loaded in
the same process: neither the directory on the path, nor its own ``helpers``
standing in for another model's.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import polars as pl
import pytest
from typer.testing import CliRunner

from gaspatchio.cli import app
from gaspatchio.runner import load_model_from_path
from gaspatchio.scenarios._graph_export import _loaded

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

runner = CliRunner()

# A name no other test, and no installed package, uses for a module.
SIBLING = "gspio_sibling_helper"

MODEL_SRC = f"""
import {SIBLING}
from gaspatchio import ActuarialFrame


def main(af: ActuarialFrame) -> ActuarialFrame:
    af.scaled = af.sum_assured * {SIBLING}.FACTOR
    return af
"""


@pytest.fixture(autouse=True)
def _forget_the_sibling() -> Iterator[None]:
    """Leave no sibling module cached for the next test on this worker."""
    yield
    for name in [n for n in sys.modules if n.partition(".")[0] == SIBLING]:
        del sys.modules[name]
    sys.modules.pop("gaspatchio._scenario_script_run_scenarios", None)


def _model_beside_a_helper(directory: Path, factor: float) -> Path:
    """Write a model that imports a helper sitting in the same directory."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{SIBLING}.py").write_text(f"FACTOR = {factor}\n")
    model = directory / "model.py"
    model.write_text(MODEL_SRC)
    return model


def _book(path: Path) -> Path:
    pl.DataFrame({"policy_id": [1, 2], "sum_assured": [100.0, 200.0]}).write_parquet(
        path
    )
    return path


@pytest.mark.parametrize(
    ("command", "extra"),
    [
        ("run-model", []),
        ("run-single-policy", ["1"]),
        ("calc-graph", ["--artifact", "{tmp}/graph.json"]),
    ],
)
def test_a_command_finds_the_helper_beside_the_model(
    tmp_path: Path, command: str, extra: list[str]
) -> None:
    """``import helper`` at the top of the model resolves, as it does when run."""
    model = _model_beside_a_helper(tmp_path / "model", 2.0)
    book = _book(tmp_path / "book.parquet")
    arguments = [a.replace("{tmp}", str(tmp_path)) for a in extra]

    result = runner.invoke(app, [command, str(model), str(book), *arguments])

    assert result.exit_code == 0, result.output
    assert f"No module named '{SIBLING}'" not in result.output


def test_the_directory_is_off_the_path_once_the_model_is_loaded(
    tmp_path: Path,
) -> None:
    """The next model loaded in this process does not find this one's files."""
    model = _model_beside_a_helper(tmp_path / "a", 2.0)
    before = list(sys.path)

    load_model_from_path(model, "main")

    assert sys.path == before


def test_a_second_model_gets_its_own_helper_not_the_first_ones(
    tmp_path: Path,
) -> None:
    """Two models, each with a ``helper`` of the same name, each run their own.

    Python caches the first model's helper under its bare name; handed to the
    second model, it would run the first model's code without a word.
    """
    first = load_model_from_path(_model_beside_a_helper(tmp_path / "a", 2.0), "main")
    second = load_model_from_path(_model_beside_a_helper(tmp_path / "b", 3.0), "main")

    assert first.__globals__[SIBLING].FACTOR == 2.0
    assert second.__globals__[SIBLING].FACTOR == 3.0


def test_a_model_loaded_again_runs_its_helper_again(tmp_path: Path) -> None:
    """Reloading from the same directory runs the helper as its file now reads.

    The model file is executed afresh on every load, and the record stamps
    the helper's bytes on disk, so a helper kept from the first load would be
    code the run used and the record does not name. A helper declaring an
    accessor declares it again as the same class statement, which is not
    refused (``test_helper_edited_between_runs.py``).
    """
    model = _model_beside_a_helper(tmp_path / "a", 2.0)

    once = load_model_from_path(model, "main")
    twice = load_model_from_path(model, "main")

    assert once.__globals__[SIBLING] is not twice.__globals__[SIBLING]
    assert twice.__globals__[SIBLING].FACTOR == 2.0


def test_a_run_script_gets_the_model_beside_it_not_another_rooms(
    tmp_path: Path,
) -> None:
    """``calc-graph --scenarios`` loads each run script with its own siblings."""
    scripts = []
    for room, factor in (("a", 2.0), ("b", 3.0)):
        _model_beside_a_helper(tmp_path / room, factor)
        script = tmp_path / room / "run_scenarios.py"
        script.write_text(f"import {SIBLING}\n")
        scripts.append(script)

    first, second = (_loaded(script) for script in scripts)

    assert getattr(first, SIBLING).FACTOR == 2.0
    assert getattr(second, SIBLING).FACTOR == 3.0
