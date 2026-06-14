# SPDX-FileCopyrightText: 2026 Opio Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""CompiledRollforward — frozen output of compile_rollforward()."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import polars as pl

    from gaspatchio_core.rollforward._ir import IR
    from gaspatchio_core.rollforward._refs import StateRef


@dataclass(frozen=True)
class CompiledRollforward:
    """Frozen artefact carrying the compiled IR and inspection surface.

    Returned by :func:`compile_rollforward`. Carries everything the kernel
    needs to execute (``plugin_kwargs``, ``plugin_args``, ``capture_slots``)
    plus three inspection helpers for governance and audit.
    """

    ir: IR
    plugin_kwargs: dict[str, Any]
    capture_slots: tuple[StateRef, ...]
    plugin_args: tuple[pl.Expr, ...] = field(default_factory=tuple)

    def canonical_form(self) -> dict[str, Any]:
        """Return a stable, deterministic dict describing the model structure.

        Two compiled rollforwards with the same Op chain (in the same order),
        same states, same Schedule canonical-form, and same configuration
        produce equal canonical-form dicts. Column-name aliases inside Op
        expressions are reduced to ``str(expr)``, so renaming a column does
        not change the canonical form.
        """
        from gaspatchio_core.rollforward._canonical import canonical_form

        return canonical_form(self.ir)

    def fingerprint(self) -> str:
        """Return a SHA-256 fingerprint of the canonical form.

        Stable across runs and across machines for an unchanged model.
        Suitable for governance metadata and run logs.
        """
        from gaspatchio_core.rollforward._fingerprint import spec_fingerprint

        return spec_fingerprint(self.ir)

    def explain(self) -> str:
        """Return a multi-line human-readable summary of the model.

        Lists states, points, schedule, transitions in order, and the
        cross-cutting configuration (lapse, contract boundary, increment
        tracking). Plain text — fits in audit reports and TRACE logs.
        """
        from gaspatchio_core.rollforward._explain import explain

        return explain(self.ir)


__all__ = ["CompiledRollforward"]
