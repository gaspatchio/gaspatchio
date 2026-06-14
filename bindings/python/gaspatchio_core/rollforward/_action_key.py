# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""action_key — minimal hermetic-run identity.

5-component closure:

    sha256(spec_fingerprint || input_data_sha || typed_input_shas
           || gaspatchio_version || git_sha)

typed_input_shas is gathered from the IR by walking Op fields and the
schedule reference. Any attribute that has a ``source_sha()`` method
contributes; the SHAs are sorted-concatenated for determinism.

``HermeticContext`` captures the fuller Bazel-style envelope (kernel
artefact SHA, Polars version, Rust target triple, fp_mode, LC_NUMERIC).
It is accepted by ``action_key()`` for forward compatibility but is
currently a no-op — its fields will be folded into the hash when a
deterministic-replay attestation pathway is needed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from gaspatchio_core._identity import canonical_bytes
from gaspatchio_core.rollforward._fingerprint import spec_fingerprint

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR


@dataclass(frozen=True)
class HermeticContext:
    """Forward-compatible envelope for hermetic-run attestation.

    Constructible today; folded into the action_key when a
    deterministic-replay attestation pathway is enabled.
    """

    engine_id: str
    engine_version: str
    kernel_artifact_sha256: str
    polars_version: str
    rust_target_triple: str
    fp_mode: str
    lc_numeric: str


def _has_source_sha(obj: Any) -> bool:  # noqa: ANN401
    return callable(getattr(obj, "source_sha", None))


def gather_typed_input_shas(ir: IR) -> list[str]:
    """Walk the IR collecting source_sha() from every typed input.

    Walks:
      - ir.schedule (always present, always has source_sha)
      - Each Op's dataclass fields (catches any Curve / Table /
        MortalityTable instance referenced as a typed attribute)

    If walking Op fields ever misses a typed input in practice, an
    explicit ``typed_inputs`` tuple field on the IR can be added.
    """
    shas: list[str] = []
    if _has_source_sha(ir.schedule):
        shas.append(ir.schedule.source_sha())
    for op in ir.transitions:
        for f in fields(op):  # type: ignore[arg-type]
            v = getattr(op, f.name)
            if _has_source_sha(v):
                shas.append(v.source_sha())
    return sorted(set(shas))


def action_key(
    ir: IR,
    *,
    input_data_sha: str,
    gaspatchio_version: str,
    git_sha: str,
    context: HermeticContext | None = None,  # noqa: ARG001 — forward-compat stub
) -> str:
    """Return ``"sha256:<hex>"`` over the 5-component closure.

    ``context`` is accepted but currently a no-op — see
    :class:`HermeticContext`.
    """
    fp = spec_fingerprint(ir)
    typed_shas = gather_typed_input_shas(ir)
    payload = {
        "spec_fingerprint": fp,
        "input_data_sha": input_data_sha,
        "typed_input_shas": typed_shas,
        "gaspatchio_version": gaspatchio_version,
        "git_sha": git_sha,
    }
    digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return f"sha256:{digest}"


__all__ = ["HermeticContext", "action_key", "gather_typed_input_shas"]
