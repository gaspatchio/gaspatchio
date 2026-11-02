# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Fast unit tests for the probe harness internals.

Unlike `probe_emission.py`'s own `@pytest.mark.probe` tests (which run the
workload model at 100k policies and take minutes), everything here is
fast and runs as part of the default `pytest` suite: the timed-subprocess
mechanics, git-ref resolution, the two workers' stdout-JSON contract, and
where the workload directory comes from — each exercised without touching
the 100k probe.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests.probe import probe_emission, synthesize_fixture

if TYPE_CHECKING:
    from collections.abc import Sequence

# Comfortably past a typical OS pipe buffer (64 KiB on macOS/Linux) in each
# of stdout and stderr, so the deadlock this guards against would trigger
# reliably if the fix ever regressed.
FLOOD_BYTES = 4 * 1024 * 1024
DEADLOCK_GUARD_TIMEOUT_S = 30.0


def test_run_with_rss_sampling_drains_large_output_without_deadlock() -> None:
    """A child flooding stdout/stderr past the OS pipe buffer must not hang.

    Regression test for the deadlock in the original PIPE-based design:
    `_poll_peak_rss` blocks on `process.wait()` while sampling RSS, and
    nothing drained the pipes until a later `communicate()` call — a child
    writing more than the OS pipe buffer before exiting would block on its
    own `write()` forever, and `process.wait()` would never return, with no
    timeout anywhere to break it. `_run_with_rss_sampling` redirects
    stdout/stderr to files instead, which removes that backpressure
    entirely. The `threading.Thread.join(timeout=...)` below is this test's
    own safety net, not the mechanism under test — if the fix ever
    regresses, this test fails cleanly instead of hanging the suite.
    """
    flood_script = (
        "import sys\n"
        f"sys.stdout.write('x' * {FLOOD_BYTES})\n"
        f"sys.stderr.write('y' * {FLOOD_BYTES})\n"
    )
    command = [sys.executable, "-c", flood_script]
    results: list[tuple[float, int, int]] = []
    sizes: dict[str, int] = {}

    def _run() -> None:
        with tempfile.TemporaryDirectory() as capture_dir:
            stdout_path = Path(capture_dir) / "stdout.log"
            stderr_path = Path(capture_dir) / "stderr.log"
            results.append(
                probe_emission._run_with_rss_sampling(  # noqa: SLF001
                    command,
                    cwd=Path.cwd(),
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                )
            )
            sizes["stdout"] = stdout_path.stat().st_size
            sizes["stderr"] = stderr_path.stat().st_size

    worker = threading.Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout=DEADLOCK_GUARD_TIMEOUT_S)

    assert not worker.is_alive(), (
        "deadlocked: a child flooding stdout/stderr never returned from "
        "_run_with_rss_sampling"
    )
    assert results, "worker thread finished without recording a result"
    elapsed, returncode, _peak_rss = results[0]
    assert returncode == 0
    assert elapsed < DEADLOCK_GUARD_TIMEOUT_S
    assert sizes["stdout"] == FLOOD_BYTES
    assert sizes["stderr"] == FLOOD_BYTES


def test_resolve_ref_resolves_symbolic_ref_to_short_sha() -> None:
    """`_resolve_ref` must return a concrete short SHA, not echo a symbolic ref."""
    head_sha = probe_emission._resolve_ref(probe_emission.REPO_ROOT, "HEAD")  # noqa: SLF001
    assert head_sha != "HEAD"
    assert re.fullmatch(r"[0-9a-f]{7,40}", head_sha)

    current_branch = subprocess.run(
        ["git", "branch", "--show-current"],  # noqa: S607 — fixed literal argv
        cwd=probe_emission.REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if current_branch:  # a detached HEAD (some CI checkouts) has no branch name
        resolved_branch_sha = probe_emission._resolve_ref(  # noqa: SLF001
            probe_emission.REPO_ROOT, current_branch
        )
        assert resolved_branch_sha == head_sha


def test_ensure_baseline_worktree_returns_resolved_sha_not_raw_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Baseline stats must carry a resolved commit hash, not a symbolic ref.

    Exercises the exact bug this fixes: `_ensure_baseline_worktree` is
    called with a symbolic (non-sha) ref, and its returned SHA — the value
    `run_probe`/`run_microbench` store in `RunStats.sha`/`MicrobenchStats.sha`
    — must be the resolved commit, not an echo of the input. Mocks the
    git/uv subprocess calls so this runs in milliseconds instead of
    performing a real `git worktree add` + `uv sync`.
    """
    resolved = "abc1234"
    worktree_path = tmp_path / "worktree"
    worktree_path.mkdir()  # already "exists" -> exercises the staleness-check branch

    def fake_run(
        command: Sequence[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if list(command[:2]) == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=f"{resolved}\n", stderr=""
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    env_dir, returned_sha = probe_emission._ensure_baseline_worktree(  # noqa: SLF001
        worktree_path, "some-symbolic-branch-name"
    )

    assert returned_sha == resolved
    assert returned_sha != "some-symbolic-branch-name"
    assert env_dir == worktree_path / "bindings" / "python"


def test_engine_check_worker_stdout_is_pure_json() -> None:
    """The engine-check worker's stdout must be exactly one parseable JSON object."""
    workload = synthesize_fixture.resolve_workload()
    if isinstance(workload, str):
        pytest.skip(workload)
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        [
            sys.executable,
            str(probe_emission.ENGINE_CHECK_SCRIPT),
            "--model",
            str(workload.model),
            "--data",
            str(workload.model_points),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert "explain_text" in payload
    assert "explain_fallback_marker_hit" in payload


def test_workload_directory_comes_only_from_the_environment_variable(
    tmp_path: Path,
) -> None:
    """`GASPATCHIO_PROBE_WORKLOAD_DIR` names the workload; unset means None.

    The point of the second case is that there is no default: unset must
    leave the model path `None`, not resolve to some path that happens to
    exist on one machine and silently reads as "workload missing"
    everywhere else.

    The constants derived from `PROBE_WORKLOAD_DIRECTORY` are computed once
    at import time, so this has to run in a fresh subprocess per case — setting
    `os.environ` in this process and re-importing an already-imported module
    would prove nothing.
    """
    bindings_python_dir = Path(__file__).resolve().parents[2]
    probe_script = "import tests.probe.probe_emission as p; print(p.IFRS17_MODEL_PATH)"

    overridden_env = {**os.environ, "GASPATCHIO_PROBE_WORKLOAD_DIR": str(tmp_path)}
    overridden = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        [sys.executable, "-c", probe_script],
        cwd=bindings_python_dir,
        env=overridden_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert overridden.stdout.strip() == str(tmp_path.resolve() / "model_ifrs17.py")

    unset_env = {
        key: value
        for key, value in os.environ.items()
        if key != "GASPATCHIO_PROBE_WORKLOAD_DIR"
    }
    unset = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        [sys.executable, "-c", probe_script],
        cwd=bindings_python_dir,
        env=unset_env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert unset.stdout.strip() == "None"


def test_microbench_worker_stdout_is_pure_json() -> None:
    """The microbench worker's stdout must be exactly one parseable JSON object."""
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        [sys.executable, str(probe_emission.MICROBENCH_WORKER_SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload.keys() == {
        "median_assignment_s",
        "plan_build_s",
        "lower_polars_calls",
    }
