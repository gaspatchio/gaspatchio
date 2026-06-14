# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""lifelib IntegratedLife runner module.

Provides setup, run, and teardown helpers for benchmarking the lifelib
IntegratedLife modelx model in deterministic (single-scenario) mode.

Usage:
    cd bindings/python && uv run --group benchmark python ../../evals/benchmarks/lifelib_runner.py
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
import tracemalloc
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

# Make the repo root importable so `evals.benchmarks._benchmarks_dir` resolves
# when this module is imported from any cwd (e.g. bindings/python/ in CI).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evals.benchmarks._benchmarks_dir import _resolve_benchmarks_dir

# The modelx model name on disk
_MODEL_NAME = "IntegratedLife"

# Scenarios space init file (relative to model_dir)
_SCENARIOS_INIT_REL = f"{_MODEL_NAME}/Scenarios/__init__.py"

# Regex that matches the scen_size function body, including its docstring.
# The function looks like:
#   def scen_size():
#       """The number of scenarios"""
#       return <N>
_SCEN_SIZE_RE = re.compile(
    r"(def scen_size\(\):\n(?:\s+\"\"\"[^\"]*\"\"\"\n)?\s+return\s+)\d+",
    re.MULTILINE,
)


def _patch_scen_size(model_dir: Path, num_scenarios: int) -> str:
    """Patch scen_size() return value in Scenarios/__init__.py.

    Replaces the integer literal returned by ``scen_size()`` with
    *num_scenarios* and returns the original line text so it can be
    restored later.

    Args:
        model_dir: Root directory that contains the ``IntegratedLife``
            modelx model folder.
        num_scenarios: The scenario count to inject.

    Returns:
        The original ``return <N>`` line (with leading whitespace and
        trailing newline preserved) so :func:`_restore_scen_size` can
        put it back exactly.

    Raises:
        RuntimeError: If the scen_size function cannot be located in the
            source file.
    """
    init_path = model_dir / _SCENARIOS_INIT_REL
    original_text = init_path.read_text(encoding="utf-8")

    match = _SCEN_SIZE_RE.search(original_text)
    if match is None:
        msg = f"Could not locate scen_size() in {init_path}"
        raise RuntimeError(msg)

    # Capture just the "return <N>" portion so we can restore it later.
    # The captured group ends just before the digit(s).
    full_match = match.group(0)  # e.g. "def scen_size():\n    \"\"\"...\"\"\"\n    return 100"
    # Extract the original return digit(s) from the end of the full match
    original_return_line = re.search(r"(\s+return\s+\d+)$", full_match, re.MULTILINE)
    if original_return_line is None:
        msg = "Could not extract original return line from scen_size match"
        raise RuntimeError(msg)
    original_line = original_return_line.group(1)

    # Replace with the desired scenario count
    patched_text = _SCEN_SIZE_RE.sub(
        lambda m: m.group(1) + str(num_scenarios),
        original_text,
        count=1,
    )
    init_path.write_text(patched_text, encoding="utf-8")
    return original_line


def _restore_scen_size(model_dir: Path, original_line: str) -> None:
    """Restore the original scen_size() return value.

    Args:
        model_dir: Root directory that contains the ``IntegratedLife``
            modelx model folder.
        original_line: The original ``return <N>`` line as returned by
            :func:`_patch_scen_size`.
    """
    init_path = model_dir / _SCENARIOS_INIT_REL
    current_text = init_path.read_text(encoding="utf-8")

    # Extract the target return value from original_line
    digit_match = re.search(r"\d+", original_line)
    if digit_match is None:
        msg = f"Cannot parse digit from original_line: {original_line!r}"
        raise RuntimeError(msg)
    original_count = digit_match.group(0)

    patched_text = _SCEN_SIZE_RE.sub(
        lambda m: m.group(1) + original_count,
        current_text,
        count=1,
    )
    init_path.write_text(patched_text, encoding="utf-8")


def setup_lifelib(
    model_dir: Path | None = None,
    num_scenarios: int = 1,
) -> dict[str, Any]:
    """Load the IntegratedLife modelx model.

    Patches ``scen_size()`` to *num_scenarios*, changes the working
    directory to *model_dir* (required by modelx), imports modelx, and
    reads the model.  All original state is captured so it can be
    restored by :func:`teardown_lifelib`.

    Args:
        model_dir: Directory that contains the ``IntegratedLife`` model
            folder. Defaults to the gaspatchio-benchmarks sister repository
            resolved via ``GASPATCHIO_BENCHMARKS_DIR`` or a sister-checkout
            at ``../gaspatchio-benchmarks/``. See
            :func:`evals.benchmarks._benchmarks_dir._resolve_benchmarks_dir`.
        num_scenarios: Number of stochastic scenarios to use. Pass ``1``
            for deterministic / fastest mode.

    Returns:
        A dict with the following keys:

        * ``model`` — the loaded modelx Model object.
        * ``setup_time_s`` — wall-clock seconds taken to load the model.
        * ``original_scen_line`` — the original ``return <N>`` line, for
          restoration.
        * ``original_cwd`` — the working directory before the chdir, for
          restoration.
        * ``model_dir`` — resolved Path to the model directory.
    """
    if model_dir is None:
        model_dir = _resolve_benchmarks_dir()

    model_dir = Path(model_dir).resolve()
    original_cwd = Path.cwd()

    # Patch scen_size before loading so modelx picks up the change.
    original_scen_line = _patch_scen_size(model_dir, num_scenarios)

    # modelx requires cwd to be the directory that *contains* the model folder.
    os.chdir(model_dir)

    t0 = time.perf_counter()
    import modelx as mx  # noqa: PLC0415  (deferred — benchmark group only)

    # Close any previously open model to avoid state leakage between runs.
    for existing in list(mx.get_models().values()):
        existing.close()

    model = mx.read_model(_MODEL_NAME)
    setup_time_s = time.perf_counter() - t0

    return {
        "model": model,
        "setup_time_s": round(setup_time_s, 3),
        "original_scen_line": original_scen_line,
        "original_cwd": original_cwd,
        "model_dir": model_dir,
    }


def run_lifelib_projection(
    lifelib_ctx: dict[str, Any],
    run_id: int = 2,
) -> dict[str, Any]:
    """Run a single GMXB projection and measure time + peak memory.

    Calls ``model.Run[run_id].GMXB.result_pv()`` and captures wall-clock
    time and peak RSS via :mod:`tracemalloc`.

    Args:
        lifelib_ctx: Context dict returned by :func:`setup_lifelib`.
        run_id: The run identifier to execute.  ``2`` corresponds to the
            2023Q4IF 8-point model-point set.

    Returns:
        A dict with keys:

        * ``time_s`` — elapsed seconds (float, 3 d.p.).
        * ``peak_mb`` — peak memory allocated during the call in MB
          (float, 1 d.p.).
    """
    model = lifelib_ctx["model"]

    import gc  # noqa: PLC0415

    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()

    _result = model.Run[run_id].GMXB.result_pv()

    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "time_s": round(elapsed, 3),
        "peak_mb": round(peak / 1024 / 1024, 1),
    }


def teardown_lifelib(lifelib_ctx: dict[str, Any]) -> None:
    """Restore working directory and scen_size() after a benchmark run.

    Args:
        lifelib_ctx: Context dict returned by :func:`setup_lifelib`.
    """
    model_dir: Path = lifelib_ctx["model_dir"]
    original_cwd: Path = lifelib_ctx["original_cwd"]
    original_scen_line: str = lifelib_ctx["original_scen_line"]

    # Restore scen_size() source
    _restore_scen_size(model_dir, original_scen_line)

    # Restore working directory
    os.chdir(original_cwd)


def swap_model_points_csv(
    model_dir: Path,
    csv_path: Path,
    mp_file_id: str = "bench",
) -> Path:
    """Copy a CSV into the model's ``model_point_data`` directory.

    The destination filename follows the lifelib naming convention:
    ``model_point_{mp_file_id}_GMXB.csv``.

    Args:
        model_dir: Root directory containing the ``IntegratedLife`` model.
        csv_path: Source CSV to copy.
        mp_file_id: Identifier embedded in the destination filename.
            Defaults to ``"bench"``.

    Returns:
        The resolved destination :class:`~pathlib.Path`.
    """
    dest_dir = model_dir / "model_point_data"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"model_point_{mp_file_id}_GMXB.csv"
    shutil.copy2(csv_path, dest)
    return dest


if __name__ == "__main__":
    print("=== lifelib_runner smoke test ===")
    print(f"Model directory: {_resolve_benchmarks_dir()}")

    print("\n[1/3] Setting up lifelib (loading model)…")
    ctx = setup_lifelib(num_scenarios=1)
    print(f"  Setup time: {ctx['setup_time_s']}s")

    print("\n[2/3] Running 8-point projection (run_id=2)…")
    metrics = run_lifelib_projection(ctx, run_id=2)
    print(f"  Projection time : {metrics['time_s']}s")
    print(f"  Peak memory     : {metrics['peak_mb']} MB")

    print("\n[3/3] Tearing down…")
    teardown_lifelib(ctx)
    print("  Done.")

    print("\n=== Results ===")
    print(f"setup_time_s  = {ctx['setup_time_s']}")
    print(f"time_s        = {metrics['time_s']}")
    print(f"peak_mb       = {metrics['peak_mb']}")
