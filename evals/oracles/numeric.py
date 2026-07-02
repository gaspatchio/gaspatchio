# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""Numeric oracle: run emitted model code, reconcile to a stored reference."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import polars as pl

from evals.oracles.base import OracleResult, extract_code

_BINDINGS = Path(__file__).resolve().parents[2] / "bindings" / "python"
_TIMEOUT = 300


def grade_numeric(artifact: str, case: dict, workdir: Path) -> OracleResult:
    """Run the model, then reconcile `case["reconcile_columns"]` to the reference.

    Score = 1.0 if the worst relative difference across the reconcile columns is
    within `case["tolerance"]`, else `max(0, 1 - worst_rel)`. 0.0 if it does not
    run or a reconcile column is missing.
    """
    code = extract_code(artifact)
    if not code:
        return OracleResult(0.0, "no python code block emitted")
    (workdir / "model.py").write_text(code)
    out = workdir / "out.parquet"
    uv = shutil.which("uv") or "uv"
    try:
        proc = subprocess.run(  # noqa: S603
            [uv, "run", "gspio", "run-model", str(workdir / "model.py"),
             str(workdir / case["fixture_data"]), "--output-file", str(out),
             "--mode", "debug"],
            cwd=_BINDINGS, capture_output=True, text=True,
            timeout=_TIMEOUT, check=False,
        )
    except subprocess.TimeoutExpired:
        return OracleResult(0.0, f"run-model timed out after {_TIMEOUT}s")
    if proc.returncode != 0 or not out.exists():
        return OracleResult(0.0, f"run-model failed: {proc.stderr.strip()[-300:]}")
    got = pl.read_parquet(out)
    ref = pl.read_parquet(workdir / case["reference"])
    tol = float(case.get("tolerance", 1e-6))
    worst = 0.0
    for col in case["reconcile_columns"]:
        if col not in got.columns:
            return OracleResult(0.0, f"missing reconcile column: {col}")
        denom = ref[col].abs().max() or 1.0
        rel = (got[col] - ref[col]).abs().max() / denom
        worst = max(worst, float(rel))
    score = 1.0 if worst <= tol else max(0.0, 1.0 - worst)
    return OracleResult(score, f"worst relative diff {worst:.2e} (tol {tol:.0e})")
