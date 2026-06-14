# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Audit sidecar JSON writer/reader + schema for ScenarioRun outputs.
# ABOUTME: Completes the source_sha governance story; opt-in via audit param.

"""Audit sidecar writer/reader for GSP-101.

A single JSON file co-located with run output, containing:
    schema_version, source_sha, plan_canonical_form, run_metadata,
    aggregator_outputs, input_data_fingerprint.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

AUDIT_SCHEMA_VERSION = "2.0"


def write_audit(  # noqa: PLR0913
    path: Path,
    *,
    source_sha: str,
    plan_canonical_form: dict[str, Any],
    run_metadata: dict[str, Any],
    aggregator_outputs: dict[str, Any],
    input_data_fingerprint: dict[str, Any],
) -> None:
    """Write the audit JSON sidecar to ``path``."""
    payload = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "source_sha": source_sha,
        "plan_canonical_form": plan_canonical_form,
        "run_metadata": run_metadata,
        "aggregator_outputs": _coerce_outputs_to_json(aggregator_outputs),
        "input_data_fingerprint": input_data_fingerprint,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default),
    )


def read_audit(path: Path) -> dict[str, Any]:
    """Read the audit JSON sidecar."""
    return json.loads(path.read_text())


def _coerce_outputs_to_json(outputs: dict[str, Any]) -> dict[str, Any]:
    """Convert aggregator outputs to JSON-reloadable values (recursing containers).

    Handles numpy ndarrays (Period* vectors -> lists), dict-of-ndarray
    (PeriodQuantile -> ``{level: list}``), numpy scalars, and ``pl.DataFrame``
    (partitioned outputs -> list of row dicts). Without this, ndarray outputs fall
    through to ``json``'s ``default=str`` and are written as non-reloadable repr
    strings (with numpy ``...`` truncation for large arrays).
    """
    import numpy as np
    import polars as pl

    def _to_jsonable(val: Any) -> Any:  # noqa: ANN401
        if isinstance(val, pl.DataFrame):
            return val.to_dicts()
        if isinstance(val, np.ndarray):
            return val.tolist()
        if isinstance(val, np.generic):  # numpy scalar (np.float64, ...)
            return val.item()
        if isinstance(val, dict):
            return {k: _to_jsonable(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [_to_jsonable(x) for x in val]
        return val

    return {name: _to_jsonable(val) for name, val in outputs.items()}


def _json_default(obj: Any) -> Any:  # noqa: ANN401
    """Fallback serialiser for non-standard types (Path, tuples-as-keys, etc.)."""
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


__all__ = ["AUDIT_SCHEMA_VERSION", "read_audit", "write_audit"]
