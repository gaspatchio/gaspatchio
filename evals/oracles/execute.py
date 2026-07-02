# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Execute oracle: run emitted model code via gspio and grade the output."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import polars as pl

from evals.oracles.base import OracleResult, extract_code

_BINDINGS = Path(__file__).resolve().parents[2] / "bindings" / "python"
_TIMEOUT = 300


def grade_execution(artifact: str, case: dict, workdir: Path) -> OracleResult:
    """Run the model code in `artifact` against the case fixture; grade columns.

    Score = fraction of `case["expected_columns"]` present in the output; 0.0 if
    no code, the run errors, or no output is written. The model runs in an
    isolated subprocess (`gspio run-model`) with the fixture in `workdir`.
    """
    code = extract_code(artifact)
    if not code:
        return OracleResult(0.0, "no python code block emitted")
    model_py = workdir / "model.py"
    model_py.write_text(code)
    data = workdir / case["fixture_data"]
    out = workdir / "out.parquet"
    uv_bin = shutil.which("uv") or "uv"
    try:
        proc = subprocess.run(  # noqa: S603
            [uv_bin, "run", "gspio", "run-model", str(model_py), str(data),
             "--output-file", str(out), "--mode", "debug"],
            cwd=_BINDINGS, capture_output=True, text=True,
            timeout=_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return OracleResult(0.0, f"run-model timed out after {_TIMEOUT}s")
    if proc.returncode != 0:
        return OracleResult(0.0, f"run-model failed: {proc.stderr.strip()[-300:]}")
    if not out.exists():
        return OracleResult(0.0, "no output parquet produced")
    cols = pl.read_parquet(out).columns
    expected = case["expected_columns"]
    present = [c for c in expected if c in cols]
    score = len(present) / len(expected) if expected else 1.0
    detail = f"{len(present)}/{len(expected)} expected columns present"
    return OracleResult(score, detail)
