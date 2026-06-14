# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ruff: noqa: T201
"""Gaspatchio vs lifelib head-to-head comparison benchmark orchestrator.

Runs the L4 tutorial model against the lifelib IntegratedLife reference model
at 8 / 1K / 10K / 100K model points.  Measures wall-clock time and peak memory
for both engines, computes speedup ratios, and writes two JSON result files.

Output files (relative to this script):
    comparison_results/comparison-results.json  — full run with hardware metadata
    comparison_results/benchmark-results.json   — flat array for benchmark-action

Usage:
    cd bindings/python
    uv run --group benchmark python ../../evals/benchmarks/run_comparison_benchmarks.py
    uv run --group benchmark python ../../evals/benchmarks/run_comparison_benchmarks.py --max-scale 8
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import platform
import shutil
import signal
import sys
import time
import traceback
import tracemalloc
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BENCH_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BENCH_DIR.parent.parent
_TUTORIAL_DIR = _REPO_ROOT / "tutorial"
_GENERATED_DIR = _BENCH_DIR / "model_points"
_OUTPUT_DIR = _BENCH_DIR / "comparison_results"

_L4_MODEL_PATH = _TUTORIAL_DIR / "level-4-lifelib" / "base" / "model.py"
_L4_BASE_DIR = _TUTORIAL_DIR / "level-4-lifelib" / "base"

# Make the repo root importable so `evals.benchmarks._benchmarks_dir` resolves
# when this script is invoked from any cwd (e.g. bindings/python/ in CI).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Lifelib reference data lives in the gaspatchio-benchmarks sister repo.
# Resolved at call time via env var or sister-checkout.
from evals.benchmarks._benchmarks_dir import _resolve_benchmarks_dir


def _lifelib_model_dir() -> Path:
    return _resolve_benchmarks_dir()


def _lifelib_mp_csv() -> Path:
    # The 2023Q4IF CSV that lifelib reads for run_id=2
    return _lifelib_model_dir() / "model_point_data" / "model_point_2023Q4IF_GMXB.csv"

# Scales supported (model-point counts)
_ALL_SCALES = [8, 1_000, 10_000, 100_000]

# Default per-scale timeout in seconds (45 min)
_DEFAULT_TIMEOUT_S = 45 * 60


# ---------------------------------------------------------------------------
# Hardware metadata
# ---------------------------------------------------------------------------


def _collect_hardware_metadata() -> dict[str, Any]:
    """Collect basic hardware and environment metadata."""
    cpu_count: int | None = os.cpu_count()

    # RAM detection — os.sysconf not available on macOS
    ram_gb: float | None = None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")  # type: ignore[attr-defined]
        page_size = os.sysconf("SC_PAGE_SIZE")  # type: ignore[attr-defined]
        ram_gb = round(pages * page_size / 1024**3, 1)
    except (AttributeError, ValueError):
        pass

    return {
        "runner_name": os.environ.get("RUNNER_NAME", "local"),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cpu_count": cpu_count,
        "ram_gb": ram_gb,
    }


# ---------------------------------------------------------------------------
# Gaspatchio helpers
# ---------------------------------------------------------------------------


def _load_model_module(model_path: Path, module_name: str) -> ModuleType:
    """Load a model.py file as a named module via importlib."""
    model_dir = str(model_path.parent)
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)

    spec = importlib.util.spec_from_file_location(module_name, model_path)
    if spec is None or spec.loader is None:
        msg = f"Cannot create module spec for {model_path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _gaspatchio_setup() -> tuple[float, ModuleType]:
    """Import gaspatchio_core and load the L4 model module.

    Returns:
        A tuple of (setup_time_s, model_module).
    """
    t0 = time.perf_counter()
    from gaspatchio_core import ActuarialFrame as _AF  # noqa: F401, PLC0415

    model_module = _load_model_module(_L4_MODEL_PATH, "l4_model_comparison")
    setup_time_s = time.perf_counter() - t0
    return round(setup_time_s, 3), model_module


def _run_gaspatchio(model_module: ModuleType, mp_path: Path) -> dict[str, Any]:
    """Run gaspatchio L4 model on the given model-point parquet file.

    Args:
        model_module: The already-loaded L4 model module.
        mp_path: Path to the model-point parquet file.

    Returns:
        Dict with keys ``time_s`` and ``peak_mb``.
    """
    from gaspatchio_core import ActuarialFrame  # noqa: PLC0415

    mp = pl.read_parquet(mp_path)

    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()

    af = ActuarialFrame(mp)
    result_af = model_module.main(af)
    _ = result_af.collect()

    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {"time_s": round(elapsed, 3), "peak_mb": round(peak / 1024 / 1024, 1)}


# ---------------------------------------------------------------------------
# Model-point file resolution
# ---------------------------------------------------------------------------


def _gaspatchio_mp_path(scale: int) -> Path:
    """Resolve the gaspatchio parquet file path for the given scale."""
    if scale <= 10:
        return _L4_BASE_DIR / "model_points.parquet"
    if scale <= 1_000:
        candidate = _L4_BASE_DIR / "model_points_1k.parquet"
        if candidate.exists():
            return candidate
        return _GENERATED_DIR / "l4_1k.parquet"
    if scale <= 10_000:
        candidate = _L4_BASE_DIR / "model_points_10k.parquet"
        if candidate.exists():
            return candidate
        return _GENERATED_DIR / "l4_10k.parquet"
    return _GENERATED_DIR / "l4_100k.parquet"


def _ensure_csv_for_parquet(parquet_path: Path) -> Path:
    """Return the CSV counterpart of *parquet_path*, creating it if needed."""
    csv_path = parquet_path.with_suffix(".csv")
    if not csv_path.exists():
        print(
            f"  Converting {parquet_path.name} → {csv_path.name} …",
            file=sys.stderr,
        )
        pl.read_parquet(parquet_path).write_csv(csv_path)
    return csv_path


# ---------------------------------------------------------------------------
# Timeout helper (SIGALRM — POSIX only)
# ---------------------------------------------------------------------------


class _TimeoutError(Exception):
    """Raised when a per-scale timeout fires."""


def _alarm_handler(signum: int, frame: object) -> None:  # noqa: ARG001
    raise _TimeoutError("Per-scale timeout reached")


def _set_timeout(seconds: int) -> None:
    """Arm SIGALRM.  No-op on platforms that lack it (e.g. Windows)."""
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _alarm_handler)
        signal.alarm(seconds)


def _cancel_timeout() -> None:
    """Disarm SIGALRM."""
    if hasattr(signal, "SIGALRM"):
        signal.alarm(0)


# ---------------------------------------------------------------------------
# CSV backup / restore
# ---------------------------------------------------------------------------


def _backup_original_csv(csv_path: Path) -> Path:
    """Copy the 2023Q4IF CSV to a .orig backup and return the backup path."""
    backup = csv_path.with_suffix(".csv.orig")
    shutil.copy2(csv_path, backup)
    return backup


def _restore_original_csv(csv_path: Path, backup_path: Path) -> None:
    """Restore the original CSV from its backup."""
    shutil.copy2(backup_path, csv_path)


# ---------------------------------------------------------------------------
# Flat benchmark-action entry helpers
# ---------------------------------------------------------------------------


def _label(scale: int) -> str:
    return f"{scale // 1000}K" if scale >= 1_000 else str(scale)


def _throughput(scale: int, time_s: float) -> float:
    return round(scale / time_s, 1) if time_s > 0 else 0.0


def _speedup(gsp_time: float, lib_time: float) -> float:
    return round(lib_time / gsp_time, 2) if gsp_time > 0 else 0.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all comparison benchmarks and write JSON results."""
    parser = argparse.ArgumentParser(
        description="Gaspatchio vs lifelib head-to-head comparison benchmark"
    )
    parser.add_argument(
        "--max-scale",
        type=int,
        default=100_000,
        help="Maximum model-point scale to run (default: 100000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULT_TIMEOUT_S,
        help=f"Per-scale timeout in seconds (default: {_DEFAULT_TIMEOUT_S})",
    )
    args = parser.parse_args()

    scales = [s for s in _ALL_SCALES if s <= args.max_scale]
    timeout_s = args.timeout

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Hardware metadata
    # ------------------------------------------------------------------
    print("Collecting hardware metadata …", file=sys.stderr)
    hw = _collect_hardware_metadata()
    print(
        f"  runner={hw['runner_name']}  cpus={hw['cpu_count']}  "
        f"ram={hw['ram_gb']}GB  py={hw['python_version']}",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------
    # Setup timing
    # ------------------------------------------------------------------
    print("\n[setup] Loading gaspatchio + L4 model …", file=sys.stderr)
    t0 = time.perf_counter()
    gsp_setup_s, l4_model = _gaspatchio_setup()
    print(f"  gaspatchio setup: {gsp_setup_s}s", file=sys.stderr)

    print("[setup] Loading lifelib IntegratedLife model …", file=sys.stderr)
    # lifelib_runner lives in the same directory as this script; load it directly
    # so the import works regardless of the caller's sys.path / cwd.
    _runner_mod = _load_model_module(_BENCH_DIR / "lifelib_runner.py", "lifelib_runner")
    setup_lifelib = _runner_mod.setup_lifelib
    run_lifelib_projection = _runner_mod.run_lifelib_projection
    teardown_lifelib = _runner_mod.teardown_lifelib

    t_lib0 = time.perf_counter()
    lifelib_ctx = setup_lifelib(model_dir=_lifelib_model_dir(), num_scenarios=1)
    lib_setup_s = round(time.perf_counter() - t_lib0, 3)
    print(f"  lifelib setup: {lib_setup_s}s", file=sys.stderr)

    # ------------------------------------------------------------------
    # Backup the original 8-point CSV before any swaps
    # ------------------------------------------------------------------
    csv_backup: Path | None = None
    if any(s > 10 for s in scales):
        print(
            f"\nBacking up original 2023Q4IF CSV: {_lifelib_mp_csv()}",
            file=sys.stderr,
        )
        csv_backup = _backup_original_csv(_lifelib_mp_csv())

    # ------------------------------------------------------------------
    # Per-scale runs
    # ------------------------------------------------------------------
    scale_results: list[dict[str, Any]] = []

    try:
        for scale in scales:
            label = _label(scale)
            print(f"\n{'=' * 60}", file=sys.stderr)
            print(f"Scale: {scale:,} model points ({label})", file=sys.stderr)
            print(f"{'=' * 60}", file=sys.stderr)

            scale_entry: dict[str, Any] = {
                "scale": scale,
                "label": label,
                "gaspatchio": None,
                "lifelib": None,
                "speedup": None,
                "error": None,
            }

            # Resolve paths
            gsp_mp_path = _gaspatchio_mp_path(scale)
            if not gsp_mp_path.exists():
                print(
                    f"  SKIP — gaspatchio model points not found: {gsp_mp_path}",
                    file=sys.stderr,
                )
                scale_entry["error"] = f"missing: {gsp_mp_path}"
                scale_results.append(scale_entry)
                continue

            # Prepare lifelib CSV swap for scales > 8
            if scale > 10:
                csv_path = _ensure_csv_for_parquet(gsp_mp_path)
                print(
                    f"  Swapping lifelib CSV → {_lifelib_mp_csv().name}",
                    file=sys.stderr,
                )
                shutil.copy2(csv_path, _lifelib_mp_csv())
                # Clear modelx cache so it re-reads the new CSV
                try:
                    lifelib_ctx["model"].clear_all()
                    print("  modelx cache cleared.", file=sys.stderr)
                except Exception as exc:
                    print(f"  WARNING: clear_all() failed: {exc}", file=sys.stderr)

            # Arm timeout
            _set_timeout(timeout_s)

            try:
                # ---- Gaspatchio run ----
                print(f"  [gaspatchio/{label}] running …", file=sys.stderr, end=" ")
                gsp_metrics = _run_gaspatchio(l4_model, gsp_mp_path)
                print(
                    f"{gsp_metrics['time_s']}s  peak={gsp_metrics['peak_mb']}MB",
                    file=sys.stderr,
                )
                scale_entry["gaspatchio"] = gsp_metrics

                # ---- Lifelib run ----
                print(f"  [lifelib/{label}] running …", file=sys.stderr, end=" ")
                lib_metrics = run_lifelib_projection(lifelib_ctx, run_id=2)
                print(
                    f"{lib_metrics['time_s']}s  peak={lib_metrics['peak_mb']}MB",
                    file=sys.stderr,
                )
                scale_entry["lifelib"] = lib_metrics

                # ---- Speedup ----
                sp = _speedup(gsp_metrics["time_s"], lib_metrics["time_s"])
                scale_entry["speedup"] = sp
                print(f"  Speedup: {sp}x", file=sys.stderr)

            except _TimeoutError:
                print(f"\n  TIMEOUT after {timeout_s}s", file=sys.stderr)
                scale_entry["error"] = "timeout"

            except Exception as exc:
                print(f"\n  ERROR: {exc}", file=sys.stderr)
                print(traceback.format_exc(), file=sys.stderr)
                scale_entry["error"] = str(exc)

            finally:
                _cancel_timeout()

            scale_results.append(scale_entry)

    finally:
        # ------------------------------------------------------------------
        # Teardown lifelib
        # ------------------------------------------------------------------
        print("\n[teardown] Restoring lifelib state …", file=sys.stderr)
        try:
            teardown_lifelib(lifelib_ctx)
        except Exception as exc:
            print(f"  WARNING: teardown_lifelib() failed: {exc}", file=sys.stderr)

        # Restore the original 8-point CSV
        if csv_backup is not None and csv_backup.exists():
            print(f"  Restoring original CSV from {csv_backup.name} …", file=sys.stderr)
            _restore_original_csv(_lifelib_mp_csv(), csv_backup)
            csv_backup.unlink(missing_ok=True)
            print("  CSV restored.", file=sys.stderr)

    # ------------------------------------------------------------------
    # Build output structures
    # ------------------------------------------------------------------

    # -- Full JSON --
    full_output: dict[str, Any] = {
        "hardware": hw,
        "setup": {
            "gaspatchio_setup_s": gsp_setup_s,
            "lifelib_setup_s": lib_setup_s,
        },
        "scales": scale_results,
    }

    # -- Flat benchmark-action array --
    flat: list[dict[str, Any]] = [
        {"name": "gaspatchio-setup", "unit": "seconds", "value": gsp_setup_s},
        {"name": "lifelib-setup", "unit": "seconds", "value": lib_setup_s},
    ]

    for entry in scale_results:
        lbl = entry["label"]
        gsp = entry["gaspatchio"]
        lib = entry["lifelib"]
        sp = entry["speedup"]
        scale = entry["scale"]
        err = entry.get("error")

        if err == "timeout":
            flat.append({"name": f"gaspatchio/{lbl}-points", "unit": "seconds", "value": "timeout"})
            flat.append({"name": f"lifelib/{lbl}-points", "unit": "seconds", "value": "timeout"})
        elif err:
            flat.append({"name": f"gaspatchio/{lbl}-points", "unit": "seconds", "value": -1})
            flat.append({"name": f"lifelib/{lbl}-points", "unit": "seconds", "value": -1})
        else:
            if gsp is not None:
                flat.append({"name": f"gaspatchio/{lbl}-points", "unit": "seconds", "value": gsp["time_s"]})
                flat.append({"name": f"gaspatchio/{lbl}-throughput", "unit": "points/sec", "value": _throughput(scale, gsp["time_s"])})
            if lib is not None:
                flat.append({"name": f"lifelib/{lbl}-points", "unit": "seconds", "value": lib["time_s"]})
                flat.append({"name": f"lifelib/{lbl}-throughput", "unit": "points/sec", "value": _throughput(scale, lib["time_s"])})
            if sp is not None:
                flat.append({"name": f"speedup/{lbl}", "unit": "x", "value": sp})

    # ------------------------------------------------------------------
    # Write files
    # ------------------------------------------------------------------
    full_path = _OUTPUT_DIR / "comparison-results.json"
    flat_path = _OUTPUT_DIR / "benchmark-results.json"

    full_path.write_text(json.dumps(full_output, indent=2))
    flat_path.write_text(json.dumps(flat, indent=2))

    print(f"\nResults written to:", file=sys.stderr)
    print(f"  {full_path}", file=sys.stderr)
    print(f"  {flat_path}", file=sys.stderr)

    # Print flat array to stdout (clean, for CI piping)
    print(json.dumps(flat, indent=2))


if __name__ == "__main__":
    main()
