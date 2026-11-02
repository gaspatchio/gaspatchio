# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""CI and the documented reproduction consume one clone-scan command."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
COMMAND = "bash scripts/check-clones.sh"
pytestmark = pytest.mark.skipif(
    not (REPO / ".git").exists(), reason="requires checkout"
)


def test_ci_and_documented_reproduction_use_the_shared_command() -> None:
    for name in (".github/workflows/CI.yml", ".github/RATCHETS.md"):
        text = (REPO / name).read_text()
        assert text.count(COMMAND) == 1
        assert "jscpd@5.1.2 bindings/python" not in text


def test_shared_scope_and_failure_propagation(tmp_path: Path) -> None:
    """Execute the real shell wrapper against an argv-recording failed scanner."""
    scanner = tmp_path / "npx"
    scanner.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 7\n')
    scanner.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", "scripts/check-clones.sh"],
        cwd=REPO,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 7
    assert result.stdout.splitlines() == [
        "--yes",
        "jscpd@5.1.2",
        "bindings/python/gaspatchio",
        "core/src",
        "engines/jax/src",
        "--min-lines",
        "12",
        "--min-tokens",
        "70",
        "--reporters",
        "console",
        "--ignore",
        "**/tutorials/**,**/__pycache__/**,**/schemas/vectors/**,**/schemas/conformance/**",
        "--baseline",
        ".github/jscpd-baseline.json",
        "--fail-on-new-clones",
    ]
