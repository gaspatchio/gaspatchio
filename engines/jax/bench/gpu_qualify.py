# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Qualify the engine on a CUDA device: correctness first, timings beside it.

The engine suite's agreement ratchets are CPU records. On a card the values
are expected to move *inside* the agreement band, 1e-12 of a line's scale
(from about 2e-14 towards 1e-14 to 1e-13), so a ratchet recorded on a laptop
is not the gate here. This is. For levels 4 and 5 it takes a fresh Polars
reference, runs the committed artifact on the device twice, and requires:

- the run happened on a GPU, with float64 on -- a pass on the CPU fallback
  would qualify nothing;
- every value-bearing node the artifact carries agrees with Polars under
  the agreement rule (worst ratio below 1e-12), the compared set computed
  from the artifact;
- the two device runs of one plan are bit-identical, which is what XLA's
  deterministic-ops flag promises and the only way to know it held. The flag
  is an environment variable read when JAX starts, so it goes on the command
  line (below); without it the two runs may legitimately differ.

Wall times for the cold and warm runs are printed and written to the report
as information. A GitHub-hosted T4 runs float64 at about a thirty-second of
its single-precision rate, so they say nothing about an A100/H100 class card
and are not compared with anything.

Usage, from ``engines/jax``::

    export XLA_FLAGS=--xla_gpu_deterministic_ops=true
    .venv/bin/python -m bench.gpu_qualify --report gpu-qualification.json
    .venv/bin/python -m bench.gpu_qualify --allow-cpu   # a local dry run only

Exit status is 0 only when every requirement holds.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import jax
import polars as pl

from gaspatchio.engines import engine_named
from gaspatchio.engines.compare import compare_results
from gaspatchio.engines.protocol import VALUE_BEARING, FrameSink, read_manifest

PROJECT = Path(__file__).resolve().parents[1]
MODELS = PROJECT / "tests/models"
CORE = PROJECT.parents[1] / "bindings/python"
CORE_GSPIO = CORE / ".venv/bin/gspio"
TUTORIALS = CORE / "gaspatchio/tutorials"
FOLDER = {"level-4": "level-4-lifelib", "level-5": "level-5-scenarios"}
BOOK = "model_points_1k.parquet"
# The agreement band: 1e-12 of a line's scale (specification section 11.1.12).
AGREEMENT_BAND = 1e-12


def _device() -> dict[str, Any]:
    """Return what JAX is running on, and whether float64 is on."""
    devices = jax.devices()
    return {
        "backend": jax.default_backend(),
        "devices": [f"{one.platform}:{one.device_kind}" for one in devices],
        "x64": bool(jax.config.read("jax_enable_x64")),
        "jax": jax.__version__,
    }


def _reference(model: str, out: Path) -> None:
    """Write the model's every-node Polars answers, from the core's own venv."""
    folder = TUTORIALS / FOLDER[model] / "base"
    finished = subprocess.run(  # noqa: S603 -- the core's venv and the tree's tutorials
        [
            str(CORE_GSPIO),
            "run-model",
            "--every-node",
            str(folder / "model.py"),
            str(folder / BOOK),
            "-o",
            str(out),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=1800,
        cwd=CORE,
    )
    if finished.returncode != 0:
        msg = f"reference for {model} failed:\n{finished.stdout}{finished.stderr}"
        raise RuntimeError(msg)


def _qualify(model: str, workdir: Path) -> dict[str, Any]:
    """Run one model on the device twice and judge it against Polars."""
    artifact: dict[str, Any] = json.loads(
        (MODELS / f"{model}.artifact.json").read_text(encoding="utf-8")
    )
    book = pl.read_parquet(MODELS / f"{model}.book.parquet")
    reference_path = workdir / f"{model}.reference.parquet"
    _reference(model, reference_path)

    engine = engine_named("jax")
    started = time.perf_counter()
    first = engine.run(artifact, book, FrameSink(), every_node=True)
    cold = time.perf_counter() - started
    started = time.perf_counter()
    second = engine.run(artifact, book, FrameSink(), every_node=True)
    warm = time.perf_counter() - started

    expected = {
        str(node["id"])
        for node in artifact.get("nodes") or []
        if isinstance(node, dict) and node.get("kind") in VALUE_BEARING
    }
    report = compare_results(
        artifact,
        pl.read_parquet(reference_path),
        first.columns,
        before_manifest=read_manifest(reference_path),
        after_manifest=first.manifest,
    )
    worst_line = max(report.lines, key=lambda line: line.max_ratio or 0.0)
    worst = worst_line.max_ratio or 0.0
    checks = {
        "every_value_bearing_node_answered": set(first.manifest.columns) == expected,
        "nothing_missing": report.missing == (),
        "same_inputs": bool(report.same_inputs),
        "verdict_agree": report.verdict == "agree",
        "worst_inside_agreement_band": worst < AGREEMENT_BAND,
        "same_plan_bit_identical": first.columns.equals(second.columns),
    }
    return {
        "model": model,
        "nodes": len(expected),
        "worst_ratio": worst,
        "worst_node": worst_line.node_id,
        "disagreeing": [
            line.node_id for line in report.lines if line.verdict != "agree"
        ],
        "seconds": {"cold": round(cold, 3), "warm": round(warm, 3)},
        "checks": checks,
        "passed": all(checks.values()),
    }


def main(argv: list[str] | None = None) -> int:
    """Run the qualification and return the process exit status."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--allow-cpu",
        action="store_true",
        help="run on whatever device JAX has; for a local dry run, never a gate",
    )
    args = parser.parse_args(argv)

    # Loading the engine is what turns float64 on; read the device after it.
    engine_named("jax")
    device = _device()
    on_gpu = device["backend"] == "gpu"
    with tempfile.TemporaryDirectory() as scratch:
        results = [_qualify(model, Path(scratch)) for model in FOLDER]

    passed = (
        (on_gpu or args.allow_cpu)
        and device["x64"]
        and all(one["passed"] for one in results)
    )
    summary = {
        "device": device,
        "on_gpu": on_gpu,
        "agreement_band": AGREEMENT_BAND,
        "models": results,
        "passed": passed,
        "note": "timings are information; a T4 runs float64 at ~1/32 rate",
    }
    text = json.dumps(summary, indent=2)
    print(text)  # noqa: T201 -- the report is the output
    if args.report is not None:
        args.report.write_text(text + "\n", encoding="utf-8")
    if not on_gpu and not args.allow_cpu:
        print("refused: JAX is not on a GPU, so nothing was qualified", file=sys.stderr)  # noqa: T201
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
