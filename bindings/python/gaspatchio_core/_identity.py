# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

# ABOUTME: Shared canonical-form encoding and source SHA helpers.
# ABOUTME: Used by Schedule, Curve, MortalityTable, Table, and ScenarioRun.

"""Deterministic JSON encoding + SHA-256 helpers for the audit chain."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _raise_on_unknown(val: Any) -> Any:  # noqa: ANN401 — signature constrained by json.dumps(default=...) API
    msg = f"canonical_bytes: cannot encode {type(val).__name__} ({val!r})"
    raise TypeError(msg)


def canonical_bytes(form: dict[str, Any]) -> bytes:
    """Deterministic JSON encoding for canonical_form dicts.

    Rules:
        - ``sort_keys=True`` at every level
        - ``separators=(',', ':')`` — no insignificant whitespace
        - ``ensure_ascii=True`` — stable bytes across platforms
        - ``allow_nan=False`` — explicit NaN raises (caller responsibility)
        - unknown types raise ``TypeError`` (no silent ``str()`` fallback)
    """
    return json.dumps(
        form,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_raise_on_unknown,
    ).encode("utf-8")


def source_sha_of(form: dict[str, Any]) -> str:
    """Return ``sha256:<hex>`` over ``canonical_bytes(form)``."""
    digest = hashlib.sha256(canonical_bytes(form)).hexdigest()
    return f"sha256:{digest}"


__all__ = ["canonical_bytes", "source_sha_of"]
