# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""The docstring CLI exits with pytest's own code when its lint step fails.

``gp-docstrings run-print-check`` runs a structural lint through
``pytest.main`` before it checks any example. A failing lint ends the run
with pytest's exit code and the one FAILED line. It used to end it with
code 1 under a second line saying pytest could not be invoked: the
``typer.Exit`` carrying pytest's code was raised inside a ``try`` whose
``except Exception`` caught it, and ``typer.Exit`` is an ``Exception``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from gaspatchio.examples.docstrings import cli

_A_FILE = str(Path(cli.__file__).with_name("style.py"))


def _run_print_check(
    monkeypatch: pytest.MonkeyPatch, code: pytest.ExitCode
) -> tuple[int, str]:
    """Run ``run-print-check`` with the lint step's pytest answering ``code``."""
    monkeypatch.setattr(cli.pytest, "main", lambda _args: code)
    result = CliRunner().invoke(cli.app, ["run-print-check", "--file", _A_FILE])
    return result.exit_code, result.output


def test_a_failed_lint_exits_with_pytests_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A usage error from pytest is exit code 4, said once."""
    exit_code, output = _run_print_check(monkeypatch, pytest.ExitCode.USAGE_ERROR)

    assert exit_code == pytest.ExitCode.USAGE_ERROR
    assert "Structural docstring lint checks FAILED" in output
    assert "Error invoking pytest" not in output


def test_failing_lint_items_exit_with_code_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failed lint items are pytest's code 1, with no claim pytest did not run."""
    exit_code, output = _run_print_check(monkeypatch, pytest.ExitCode.TESTS_FAILED)

    assert exit_code == pytest.ExitCode.TESTS_FAILED
    assert "Error invoking pytest" not in output
