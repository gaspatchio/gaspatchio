# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""spec_fingerprint — sha256 over canonical-form bytes.

This is the engine-portable recipe identity. Two IRs with the same
spec_fingerprint produce identical numerical output for identical inputs
on any engine that implements the closed semantic subset correctly.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from gaspatchio_core._identity import canonical_bytes
from gaspatchio_core.rollforward._canonical import canonical_form

if TYPE_CHECKING:
    from gaspatchio_core.rollforward._ir import IR


def spec_fingerprint(ir: IR) -> str:
    """Return ``"sha256:<hex>"`` over the IR's canonical-form bytes."""
    digest = hashlib.sha256(canonical_bytes(canonical_form(ir))).hexdigest()
    return f"sha256:{digest}"


__all__ = ["spec_fingerprint"]
