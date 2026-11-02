# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""spec_fingerprint — the compiled machine's identity, as a reader recomputes it.

The section 12.3 recipe-grammar hash of the compilation body the
``gaspatchio_rollforward_ir`` facet publishes, less its schedule (spec 12.1). Two
IRs with the same spec_fingerprint publish the same machine, and so produce
identical numerical output for identical inputs on any engine that implements
the closed semantic subset correctly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaspatchio.rollforward._canonical import compiled_identity, identity_form

if TYPE_CHECKING:
    from gaspatchio.rollforward._ir import IR


def spec_fingerprint(ir: IR) -> str:
    """Return ``"sha256:<hex>"`` over the machine's published body, less schedule."""
    return compiled_identity(identity_form(ir))


__all__ = ["spec_fingerprint"]
