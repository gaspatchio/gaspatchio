# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Emission-graph performance probe.

Brackets the emission-graph-core hot-path work with a reproducible timing,
peak-memory, and streaming-engine-fallback measurement, run against a
machine-local model that is not part of this repository (see
``synthesize_fixture.py``), named by the ``GASPATCHIO_PROBE_WORKLOAD_DIR``
environment variable; there is no default. Also provides an
assignment-path microbench (`run_microbench`) for a second, finer-grained
signal.

Two entry points:

* `run_probe(...)` / `run_microbench(...)` — the programmatic API, for
  comparing a candidate checkout against a baseline one.
* ``python -m tests.probe.probe_emission [--baseline-worktree PATH]
  [--microbench]`` — the CLI used to produce the machine-local reference
  JSON under ``tests/probe/reference/``.

Both instruments run the model/microbench as a subprocess against a target
environment, so the identical protocol works whether that environment is
this checkout or a ``--baseline-worktree`` with its own venv. The `probe`
pytest marker keeps both out of the default ``pytest`` run — a full 6
iteration run is minutes, not seconds, and the first iteration always pays a
warmup cost (GSP-91) that would make a single-shot run misleading. Select it
explicitly with ``pytest -m probe``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import polars as pl
import psutil
import pytest
from loguru import logger

from tests.probe import synthesize_fixture
from tests.probe._engine_check import FALLBACK_MARKERS

if TYPE_CHECKING:
    from collections.abc import Sequence

# --------------------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------------------

_THIS_FILE: Final[Path] = Path(__file__).resolve()
BINDINGS_PYTHON_DIR: Final[Path] = _THIS_FILE.parents[2]
REPO_ROOT: Final[Path] = _THIS_FILE.parents[4]

ENGINE_CHECK_SCRIPT: Final[Path] = _THIS_FILE.parent / "_engine_check.py"
MICROBENCH_WORKER_SCRIPT: Final[Path] = _THIS_FILE.parent / "_microbench_worker.py"
REFERENCE_DIR: Final[Path] = _THIS_FILE.parent / "reference"

_WORKLOAD_DIRECTORY: Final[Path | None] = synthesize_fixture.PROBE_WORKLOAD_DIRECTORY

# None whenever the workload directory was not named — there is no default
# path to fall back to, so every entry point below narrows before using it.
IFRS17_MODEL_PATH: Final[Path | None] = (
    None
    if _WORKLOAD_DIRECTORY is None
    else _WORKLOAD_DIRECTORY / synthesize_fixture.MODEL_FILE_NAME
)
FIXTURE_PATH: Final[Path] = synthesize_fixture.FIXTURE_PATH

# The commit the probe harness was written against — this repo's HEAD at the
# time. A caller pointing `--baseline-worktree` at a more recent pre-change
# commit passes its own `baseline_ref` through `run_probe`/`run_microbench`
# directly; this is only the CLI's default when a worktree path is given
# without one.
BASELINE_REF: Final[str] = "03406f7"
DEFAULT_BASELINE_WORKTREE: Final[Path] = Path(tempfile.gettempdir()) / "gspio-base"

ITERATIONS: Final[int] = 6
RSS_POLL_INTERVAL_S: Final[float] = 0.2

# The execution threshold is tighter than the microbench's: whole-model medians
# over 100k policies are far less noisy than individual assignment-path
# timings, so a smaller drift is already meaningful.
EXECUTION_REGRESSION_THRESHOLD: Final[float] = 0.05
MICROBENCH_REGRESSION_THRESHOLD: Final[float] = 0.10


@dataclass(slots=True)
class RunStats:
    """One environment's whole-model timing/memory result."""

    sha: str
    median_s: float
    peak_rss_gib: float


@dataclass(slots=True)
class ProbeReport:
    """Full-model probe result: candidate alone, or candidate vs baseline."""

    machine: dict[str, object]
    polars: str
    baseline: RunStats | None
    candidate: RunStats
    ratios: dict[str, float] | None
    engine: dict[str, object]
    verdict: str


@dataclass(slots=True)
class MicrobenchStats:
    """One environment's assignment-path microbench result."""

    sha: str
    median_assignment_s: float
    plan_build_s: float
    lower_polars_calls: int


@dataclass(slots=True)
class MicrobenchReport:
    """Microbench result: candidate alone, or candidate vs baseline."""

    machine: dict[str, object]
    polars: str
    baseline: MicrobenchStats | None
    candidate: MicrobenchStats
    ratios: dict[str, float] | None
    verdict: str


# --------------------------------------------------------------------------------------
# Shared helpers: machine info, git, verdicts
# --------------------------------------------------------------------------------------


def _machine_info() -> dict[str, object]:
    """Capture enough about this box to make a future comparison meaningful."""
    virtual_memory = psutil.virtual_memory()
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "total_memory_gib": round(virtual_memory.total / (1024**3), 2),
    }


def _git_sha(repo_dir: Path) -> str:
    """Return the short SHA HEAD resolves to in `repo_dir`."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 — fixed literal argv
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _verdict(ratios: dict[str, float] | None, threshold: float) -> str:
    """Classify a run: no baseline, within tolerance, or a regression."""
    if ratios is None:
        return "candidate-only"
    if any(ratio - 1.0 > threshold for ratio in ratios.values()):
        return "regression"
    return "within-tolerance"


def _ensure_baseline_worktree(worktree_path: Path, ref: str) -> tuple[Path, str]:
    """Ensure a git worktree at `worktree_path` checked out to `ref`.

    Idempotent: reuses an existing worktree at that path, but re-checks-out
    `ref` if a previous call left it on a different commit, so repeated runs
    against moving baseline refs can reuse one path rather than accumulating
    worktrees. Returns (its ``bindings/python`` directory — the env root
    every command below runs relative to — the short SHA `ref` resolved to),
    after syncing its own venv so it matches the lockfile pinned at `ref`.
    The caller should record the resolved SHA rather than the raw `ref` it
    passed in: `ref` may be a branch or tag name, and a saved report must
    name the actual commit measured, not a moving pointer.
    """
    target_sha = _resolve_ref(REPO_ROOT, ref)
    if not worktree_path.exists():
        logger.info("creating baseline worktree at {} ({})", worktree_path, ref)
        subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
            ["git", "worktree", "add", str(worktree_path), ref],  # noqa: S607
            cwd=REPO_ROOT,
            check=True,
        )
    elif _git_sha(worktree_path) != target_sha:
        logger.info(
            "baseline worktree at {} is stale, checking out {}", worktree_path, ref
        )
        subprocess.run(  # noqa: S603 — no shell, `ref` is caller-supplied but not shell input
            ["git", "checkout", ref],  # noqa: S607
            cwd=worktree_path,
            check=True,
        )

    env_dir = worktree_path / "bindings" / "python"
    logger.info("syncing baseline venv at {}", env_dir)
    subprocess.run(
        ["uv", "sync", "--locked"],  # noqa: S607 — fixed literal argv
        cwd=env_dir,
        check=True,
    )
    return env_dir, target_sha


def _resolve_ref(repo_dir: Path, ref: str) -> str:
    """Return the short SHA `ref` resolves to in `repo_dir`."""
    result = subprocess.run(  # noqa: S603 — no shell, `ref` is caller-supplied but not shell input
        ["git", "rev-parse", "--short", ref],  # noqa: S607
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


# --------------------------------------------------------------------------------------
# Full-model probe: timing + peak RSS + streaming-engine assertion
# --------------------------------------------------------------------------------------


def _rss_with_children(process: psutil.Process) -> int | None:
    """Sum RSS across `process` and all of its live descendants."""
    try:
        total = int(process.memory_info().rss)
        for child in process.children(recursive=True):
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                total += int(child.memory_info().rss)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    return total


def _poll_peak_rss(
    process: subprocess.Popen[bytes], *, interval_s: float = RSS_POLL_INTERVAL_S
) -> int:
    """Sample RSS (child + descendants) at `interval_s` until `process` exits.

    The peak matters, not the steady state — `uv run gspio run-model`'s
    transient materialisation spike is what risks OOM, and it can be gone by
    the time the process exits, so a background thread samples throughout
    the run and the maximum observed total is returned. Blocks until the
    process exits.
    """
    peak = 0
    stop = threading.Event()

    def _sample() -> None:
        nonlocal peak
        try:
            parent = psutil.Process(process.pid)
        except psutil.NoSuchProcess:
            return
        while not stop.is_set():
            total = _rss_with_children(parent)
            if total is not None and total > peak:
                peak = total
            if process.poll() is not None:
                return
            stop.wait(interval_s)

    sampler = threading.Thread(target=_sample, daemon=True)
    sampler.start()
    process.wait()
    stop.set()
    sampler.join(timeout=1.0)
    return peak


def _run_with_rss_sampling(
    command: list[str], *, cwd: Path, stdout_path: Path, stderr_path: Path
) -> tuple[float, int, int]:
    """Run `command` in `cwd`, sampling peak RSS.

    Returns ``(wall_s, returncode, peak_rss_bytes)``.

    stdout/stderr are redirected to `stdout_path`/`stderr_path` rather than
    ``PIPE``. `_poll_peak_rss` blocks on `process.wait()` while sampling RSS,
    and nothing drains a ``PIPE`` until a later `communicate()` call — a
    child that writes more than the OS pipe buffer before exiting (plausible
    with, say, ``LOGURU_LEVEL=TRACE`` or ``GASPATCHIO_VERBOSE=true`` set in
    the caller's environment, which the subprocess inherits) would then block
    on its own ``write()`` forever, and `process.wait()` would never return —
    a deadlock with no timeout anywhere in the path to break it. Files never
    apply that backpressure: the child's writes complete regardless of
    whether or when anyone reads them back.
    """
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        start = time.perf_counter()
        process = subprocess.Popen(  # noqa: S603 — argv is caller-controlled, not shell input
            command,
            cwd=cwd,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        peak_rss = _poll_peak_rss(process)
        elapsed = time.perf_counter() - start
    returncode = process.returncode
    assert returncode is not None  # `_poll_peak_rss` already awaited exit via `.wait()`
    return elapsed, returncode, peak_rss


def _time_one_run(
    *, env_dir: Path, model_path: Path, data_path: Path, output_path: Path
) -> tuple[float, int]:
    """Run ``uv run gspio run-model`` once as a subprocess.

    Uses ``--mode optimize`` deliberately: the CLI's default (``debug``)
    collects via `LazyFrame.profile()`, which does not take the streaming
    engine that `ActuarialFrame.collect()` defaults to and that the engine
    assertion checks — measuring debug mode would time a different code path
    than the one this probe is bracketing.

    Returns (wall_seconds, peak_rss_bytes).
    """
    command = [
        "uv",
        "run",
        "gspio",
        "run-model",
        str(model_path),
        str(data_path),
        "--mode",
        "optimize",
        "--output-file",
        str(output_path),
    ]
    with tempfile.TemporaryDirectory() as capture_dir:
        stdout_path = Path(capture_dir) / "stdout.log"
        stderr_path = Path(capture_dir) / "stderr.log"
        elapsed, returncode, peak_rss = _run_with_rss_sampling(
            command, cwd=env_dir, stdout_path=stdout_path, stderr_path=stderr_path
        )
        if returncode != 0:
            msg = (
                f"gspio run-model failed (exit {returncode}) in {env_dir}: "
                f"{stderr_path.read_text()}"
            )
            raise RuntimeError(msg)
    return elapsed, peak_rss


def _measure_run_stats(
    *,
    env_dir: Path,
    sha: str,
    model_path: Path,
    data_path: Path,
    iterations: int,
) -> RunStats:
    """Time `iterations` runs in `env_dir`, discarding the first as warmup.

    Reports the median across the remaining iterations for both wall time
    and peak RSS (GSP-91: a cold first run pays import/plan-cache costs a
    warm process does not).
    """
    wall_times: list[float] = []
    peak_rss_values: list[int] = []

    for iteration in range(iterations):
        with tempfile.TemporaryDirectory() as scratch_dir:
            output_path = Path(scratch_dir) / "probe_output.parquet"
            elapsed_s, peak_rss_bytes = _time_one_run(
                env_dir=env_dir,
                model_path=model_path,
                data_path=data_path,
                output_path=output_path,
            )
        if iteration == 0 and iterations > 1:
            # A single-iteration call (e.g. a cheap baseline-worktree smoke
            # check) has no warmup to discard — discarding it would leave
            # nothing to report on.
            logger.debug(
                "discarding iteration 0 as warmup (GSP-91): {:.2f}s", elapsed_s
            )
            continue
        logger.debug(
            "iteration {}: {:.2f}s, peak RSS {:.2f} GiB",
            iteration,
            elapsed_s,
            peak_rss_bytes / (1024**3),
        )
        wall_times.append(elapsed_s)
        peak_rss_values.append(peak_rss_bytes)

    return RunStats(
        sha=sha,
        median_s=statistics.median(wall_times),
        peak_rss_gib=statistics.median(peak_rss_values) / (1024**3),
    )


def _run_engine_check(model_path: Path, data_path: Path) -> dict[str, object]:
    """Run the streaming-engine `explain()` assertion as a subprocess.

    Captures stdout (the worker's JSON result) and stderr (the
    ``POLARS_VERBOSE=1`` engine-selection log) separately, and checks both
    for a fallback marker — `explain()` text alone does not always surface a
    silent drop to in-memory execution.
    """
    env = {**os.environ, "POLARS_VERBOSE": "1"}
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        [
            sys.executable,
            str(ENGINE_CHECK_SCRIPT),
            "--model",
            str(model_path),
            "--data",
            str(data_path),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        logger.error("engine check failed: {}", result.stderr[-4000:])
        return {
            "fallback_detected": None,
            "error": result.stderr[-4000:],
        }

    payload = json.loads(result.stdout)
    stderr_lower = result.stderr.lower()
    verbose_log_marker_hit = any(marker in stderr_lower for marker in FALLBACK_MARKERS)
    explain_marker_hit = bool(payload["explain_fallback_marker_hit"])
    # Positive confirmation, not just an absence of negative markers: a
    # broken or empty POLARS_VERBOSE capture would otherwise read as "no
    # fallback found" for the wrong reason. "polars-stream" is the engine's
    # own verbose-log prefix (observed empirically on this model/polars
    # version); its absence means the check below proved nothing.
    streaming_engine_confirmed = "polars-stream" in stderr_lower
    return {
        "fallback_detected": explain_marker_hit or verbose_log_marker_hit,
        "explain_marker_hit": explain_marker_hit,
        "verbose_log_marker_hit": verbose_log_marker_hit,
        "streaming_engine_confirmed": streaming_engine_confirmed,
        "explain_text": payload["explain_text"],
    }


def run_probe(
    baseline_ref: str | None,
    *,
    baseline_worktree: Path | None = None,
    model_path: Path | None = IFRS17_MODEL_PATH,
    fixture_path: Path = FIXTURE_PATH,
    iterations: int = ITERATIONS,
) -> ProbeReport:
    """Time the workload model @100k, candidate alone or candidate vs baseline.

    Synthesizes `fixture_path` on first use if it does not already exist —
    see `synthesize_fixture` — so both the candidate run and any
    `baseline_ref` comparison read the exact same bytes.

    Args:
        baseline_ref: A git ref to compare against, or None for a
            candidate-only run.
        baseline_worktree: Where the baseline checkout lives (created via
            `git worktree add` if missing). Defaults to a fixed temp path
            when `baseline_ref` is given but this is not.
        model_path: The workload model file, or None when the workload
            directory was never named.
        fixture_path: The synthesized 100k-policy input.
        iterations: Total timed runs per environment, including the
            discarded warmup (GSP-91).

    Raises:
        RuntimeError: `model_path` is None — there is nothing to time.

    """
    if model_path is None:
        raise RuntimeError(synthesize_fixture.WORKLOAD_NOT_CONFIGURED_MESSAGE)
    if not fixture_path.exists():
        logger.info("fixture not found at {}, synthesizing", fixture_path)
        synthesize_fixture.write_fixture(output_path=fixture_path)

    candidate = _measure_run_stats(
        env_dir=BINDINGS_PYTHON_DIR,
        sha=_git_sha(REPO_ROOT),
        model_path=model_path,
        data_path=fixture_path,
        iterations=iterations,
    )

    baseline: RunStats | None = None
    ratios: dict[str, float] | None = None
    if baseline_ref is not None:
        worktree_env, resolved_sha = _ensure_baseline_worktree(
            baseline_worktree or DEFAULT_BASELINE_WORKTREE, baseline_ref
        )
        baseline = _measure_run_stats(
            env_dir=worktree_env,
            sha=resolved_sha,
            model_path=model_path,
            data_path=fixture_path,
            iterations=iterations,
        )
        ratios = {
            "median_s": candidate.median_s / baseline.median_s,
            "peak_rss_gib": candidate.peak_rss_gib / baseline.peak_rss_gib,
        }

    return ProbeReport(
        machine=_machine_info(),
        polars=pl.__version__,
        baseline=baseline,
        candidate=candidate,
        ratios=ratios,
        engine=_run_engine_check(model_path, fixture_path),
        verdict=_verdict(ratios, EXECUTION_REGRESSION_THRESHOLD),
    )


# --------------------------------------------------------------------------------------
# Microbench: assignment-path timing
# --------------------------------------------------------------------------------------


def _measure_microbench_stats(*, python_bin: Path, sha: str) -> MicrobenchStats:
    """Run `_microbench_worker.py` once with `python_bin`; parse its JSON."""
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, all paths are ours
        [str(python_bin), str(MICROBENCH_WORKER_SCRIPT)],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    return MicrobenchStats(
        sha=sha,
        median_assignment_s=payload["median_assignment_s"],
        plan_build_s=payload["plan_build_s"],
        lower_polars_calls=payload["lower_polars_calls"],
    )


def run_microbench(
    baseline_ref: str | None,
    *,
    baseline_worktree: Path | None = None,
) -> MicrobenchReport:
    """Run the assignment-path microbench, candidate alone or vs baseline.

    Both sides run via the same subprocess-worker protocol as `run_probe`
    (the candidate uses `sys.executable`, matching whatever environment this
    process is already running in), so the measurement is symmetric rather
    than comparing an in-process candidate against a subprocess baseline.

    Args:
        baseline_ref: A git ref to compare against, or None for a
            candidate-only run.
        baseline_worktree: Where the baseline checkout lives (created via
            `git worktree add` if missing). Defaults to a fixed temp path
            when `baseline_ref` is given but this is not.

    """
    candidate = _measure_microbench_stats(
        python_bin=Path(sys.executable), sha=_git_sha(REPO_ROOT)
    )

    baseline: MicrobenchStats | None = None
    ratios: dict[str, float] | None = None
    if baseline_ref is not None:
        worktree_env, resolved_sha = _ensure_baseline_worktree(
            baseline_worktree or DEFAULT_BASELINE_WORKTREE, baseline_ref
        )
        baseline_python = worktree_env / ".venv" / "bin" / "python"
        baseline = _measure_microbench_stats(
            python_bin=baseline_python, sha=resolved_sha
        )
        ratios = {
            "median_assignment_s": (
                candidate.median_assignment_s / baseline.median_assignment_s
            ),
            "plan_build_s": candidate.plan_build_s / baseline.plan_build_s,
        }

    return MicrobenchReport(
        machine=_machine_info(),
        polars=pl.__version__,
        baseline=baseline,
        candidate=candidate,
        ratios=ratios,
        verdict=_verdict(ratios, MICROBENCH_REGRESSION_THRESHOLD),
    )


# --------------------------------------------------------------------------------------
# pytest entry (marked `probe`, excluded from the default run)
# --------------------------------------------------------------------------------------


@pytest.mark.probe
def test_probe_emission_reference() -> None:
    """Full-model probe, candidate-only — skips if the workload is absent.

    Two ways to be absent, and the skip says which: nobody named a
    directory, or the directory named is missing a file the probe reads.
    """
    workload = synthesize_fixture.resolve_workload()
    if isinstance(workload, str):
        pytest.skip(workload)
    report = run_probe(baseline_ref=None, model_path=workload.model)
    assert report.candidate.median_s > 0
    assert report.candidate.peak_rss_gib > 0
    assert report.verdict == "candidate-only"
    assert report.engine.get("fallback_detected") is False
    assert report.engine.get("streaming_engine_confirmed") is True


@pytest.mark.probe
def test_microbench_emission_reference() -> None:
    """Assignment-path microbench, candidate-only."""
    report = run_microbench(baseline_ref=None)
    assert report.candidate.median_assignment_s >= 0
    assert report.candidate.plan_build_s >= 0
    assert report.verdict == "candidate-only"


# --------------------------------------------------------------------------------------
# CLI entry: `python -m tests.probe.probe_emission`
# --------------------------------------------------------------------------------------


def _parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m tests.probe.probe_emission",
        description="Run the emission-graph performance probe.",
    )
    parser.add_argument(
        "--baseline-worktree",
        type=Path,
        default=None,
        help=(
            f"Path to a git worktree checked out at {BASELINE_REF} (created "
            "if missing, reused if present)."
        ),
    )
    parser.add_argument(
        "--microbench",
        action="store_true",
        help="Run the assignment-path microbench instead of the full-model probe.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Where to write the JSON report (default: tests/probe/reference/).",
    )
    return parser.parse_args(argv)


def _default_output_path(*, microbench: bool) -> Path:
    name = "microbench_reference.json" if microbench else "probe_reference.json"
    return REFERENCE_DIR / name


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry: run the probe (or microbench) and write its JSON report.

    Refuses with a logged sentence and a non-zero exit when the full-model
    probe is asked for and the workload is unusable.
    """
    args = _parse_cli_args(argv)
    baseline_ref = BASELINE_REF if args.baseline_worktree is not None else None

    report: ProbeReport | MicrobenchReport
    if args.microbench:
        report = run_microbench(baseline_ref, baseline_worktree=args.baseline_worktree)
    else:
        # The microbench needs no workload, so only this branch checks for
        # one — and it refuses the way the sibling CLI does, with the
        # sentence and a non-zero exit rather than a traceback.
        workload = synthesize_fixture.resolve_workload()
        if isinstance(workload, str):
            logger.error(workload)
            raise SystemExit(1)
        report = run_probe(
            baseline_ref,
            baseline_worktree=args.baseline_worktree,
            model_path=workload.model,
        )

    output_path = args.output or _default_output_path(microbench=args.microbench)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dataclasses.asdict(report), indent=2))
    logger.success("wrote {} (verdict: {})", output_path, report.verdict)


if __name__ == "__main__":
    main()
